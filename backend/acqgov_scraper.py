"""
acquisition.gov Scraper Module
Ported from Federal_Clauses_Downloader.py
"""
import re
import unicodedata
import asyncio
from typing import List, Dict, Optional
import httpx
from bs4 import BeautifulSoup, NavigableString, Tag
import logging

logger = logging.getLogger(__name__)

# -------------------- Constants from Federal_Clauses_Downloader.py --------------------
BASE = "https://www.acquisition.gov"

# Pattern to match clause numbers like 52.204-17, 252.204-7012
SECTION_RE = re.compile(
    r"(?<!\d)(\d{1,4}\.\d{1,4}(?:[-–—](?=\d)\d{1,6})*)(?!\d)"
)

# Various dash characters to normalize
_DASHES = "\u2010\u2011\u2012\u2013\u2014\u2212"


def normalize_clause_id(s: str) -> str:
    """
    Normalize a clause ID to standard format.
    Ported directly from Federal_Clauses_Downloader.py
    
    Handles:
    - Unicode normalization (NFKC)
    - Various dash characters -> standard hyphen
    - Non-breaking spaces -> regular spaces
    - Multiple whitespace -> single space
    """
    if s is None:
        return s
    s = unicodedata.normalize("NFKC", str(s))
    s = re.sub(f"[{re.escape(_DASHES)}]", "-", s)
    s = s.replace("\u00A0", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def clause_id_no_dash(s: str) -> str:
    """
    Remove dashes, dots, and spaces for comparison.
    Ported from Federal_Clauses_Downloader.py
    """
    s = normalize_clause_id(s or "")
    return re.sub(r"[-.\s]", "", s)


def normalize_dashes_in_text(s: str) -> str:
    """Normalize dash characters in text."""
    if s is None:
        return s
    s = unicodedata.normalize("NFKC", str(s))
    return re.sub(f"[{re.escape(_DASHES)}]", "-", s)


def canonicalize_url(url: str) -> str:
    """Ensure URL uses https."""
    return "https://" + url[len("http://"):] if url.startswith("http://") else url


def make_soup(html_bytes: bytes) -> BeautifulSoup:
    """Create BeautifulSoup object from HTML bytes."""
    text = html_bytes.decode("utf-8", errors="ignore")
    try:
        return BeautifulSoup(text, "lxml")
    except:
        return BeautifulSoup(text, "html.parser")


def extract_main_region(soup: BeautifulSoup):
    """Extract main content region from page."""
    return (soup.find("article")
            or soup.find("div", id="block-acqgov-content")
            or soup.find("div", class_="region-content")
            or soup)


def parse_heading_for_code_and_title(heading: str):
    """
    Parse a heading to extract clause code and title.
    Returns (code, title) tuple.
    """
    t = (heading or "").strip()
    m = SECTION_RE.search(t)
    if not m:
        return "", t
    code = normalize_clause_id(m.group(1))
    # Extract title after the clause number
    title = t[m.end():].strip()
    title = title.lstrip(' .-–—:').strip()
    return code, title


def clean_text(node) -> str:
    """Extract clean text from HTML node."""
    for t in node.find_all(["nav", "aside", "footer", "script", "style"]):
        t.decompose()
    text = node.get_text("\n", strip=True)
    text = text.replace("\u00A0", " ").replace("\u202F", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


# Date extraction regex
MONTH_ALT = r"(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
DATE_ANY = re.compile(rf"(?i)({MONTH_ALT})\D{{0,20}}([12]\d{{3}})")


def extract_date_from_text(text: str) -> Optional[str]:
    """Extract date string from text (e.g., 'Apr 2021')."""
    m = DATE_ANY.search(text or "")
    if m:
        month = m.group(1)[:3].upper()
        year = m.group(2)
        return f"{month} {year}"
    return None


async def fetch_page(client: httpx.AsyncClient, url: str) -> Optional[bytes]:
    """Fetch a page with error handling."""
    try:
        url = canonicalize_url(url)
        response = await client.get(url, timeout=60.0, follow_redirects=True)
        if response.status_code == 200:
            return response.content
    except Exception as e:
        logger.warning(f"Error fetching {url}: {e}")
    return None


async def find_part_urls(client: httpx.AsyncClient, part_type: str = "far") -> List[Dict]:
    """
    Find all clause URLs for a given part type (far/dfars).
    Returns list of {url, code, title} dicts.
    """
    clauses = []
    
    if part_type.lower() == "far":
        index_url = f"{BASE}/far/part-52"
    elif part_type.lower() == "dfars":
        index_url = f"{BASE}/dfars/part-252"
    else:
        return clauses
    
    logger.info(f"Fetching index from: {index_url}")
    
    html = await fetch_page(client, index_url)
    if not html:
        return clauses
    
    soup = make_soup(html)
    main_region = extract_main_region(soup)
    
    # Find all links and headings that contain clause numbers
    seen_codes = set()
    
    # Check links
    for link in main_region.find_all('a', href=True):
        href = link.get('href', '')
        text = link.get_text(' ', strip=True)
        
        m = SECTION_RE.search(text)
        if m:
            code = normalize_clause_id(m.group(1))
            
            # For FAR, codes start with 52.
            # For DFARS, codes start with 252.
            prefix = "52." if part_type.lower() == "far" else "252."
            if not code.startswith(prefix):
                continue
            
            if code in seen_codes:
                continue
            seen_codes.add(code)
            
            # Extract title
            title = text[m.end():].strip().lstrip(' .-–—:').strip()
            
            # Skip "Reserved" clauses - they are empty placeholders
            if title.lower().startswith("reserved") or "[reserved]" in title.lower():
                continue
            
            # Build full URL
            if href.startswith('/'):
                full_url = f"{BASE}{href}"
            elif href.startswith('http'):
                full_url = href
            else:
                full_url = f"{BASE}/{href}"
            
            clauses.append({
                "url": full_url,
                "clause_number": code,
                "title": title or f"Clause {code}",
                "type": "FAR" if part_type.lower() == "far" else "DFARS"
            })
    
    # Also check headings
    for heading in main_region.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
        text = heading.get_text(' ', strip=True)
        m = SECTION_RE.search(text)
        if m:
            code = normalize_clause_id(m.group(1))
            prefix = "52." if part_type.lower() == "far" else "252."
            if not code.startswith(prefix):
                continue
            
            if code in seen_codes:
                continue
            seen_codes.add(code)
            
            title = text[m.end():].strip().lstrip(' .-–—:').strip()
            
            # Skip "Reserved" clauses - they are empty placeholders
            if title.lower().startswith("reserved") or "[reserved]" in title.lower():
                continue
            
            # Look for a link in or near the heading
            link = heading.find('a', href=True)
            if link:
                href = link.get('href', '')
                if href.startswith('/'):
                    full_url = f"{BASE}{href}"
                elif href.startswith('http'):
                    full_url = href
                else:
                    full_url = f"{BASE}/{href}"
            else:
                # Construct URL based on clause number
                full_url = f"{BASE}/{part_type.lower()}/{code}"
            
            clauses.append({
                "url": full_url,
                "clause_number": code,
                "title": title or f"Clause {code}",
                "type": "FAR" if part_type.lower() == "far" else "DFARS"
            })
    
    logger.info(f"Found {len(clauses)} {part_type.upper()} clauses from index")
    return clauses


async def scrape_clause_detail(client: httpx.AsyncClient, url: str, clause_number: str) -> Optional[Dict]:
    """
    Scrape full clause details from a clause page.
    Returns dict with text, html, date fields.
    """
    html_bytes = await fetch_page(client, url)
    if not html_bytes:
        return None
    
    soup = make_soup(html_bytes)
    main_region = extract_main_region(soup)
    
    # Extract plain text
    text = clean_text(main_region)
    
    # Extract date from text
    date = extract_date_from_text(text)
    
    # Get HTML of main content
    html_content = str(main_region)
    
    return {
        "text": text,
        "html": html_content,
        "date": date
    }


async def scrape_far_clauses(limit: int = 0) -> List[Dict]:
    """
    Scrape FAR clauses from acquisition.gov.
    
    Returns list of dicts with:
    - clause_number: e.g., "52.204-17"
    - title: clause title
    - type: "FAR"
    - date: date string if found
    - text: plain text content
    - html: HTML content
    """
    clauses = []
    
    async with httpx.AsyncClient(
        timeout=60.0,
        follow_redirects=True,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
    ) as client:
        # Get index of FAR clauses
        index_clauses = await find_part_urls(client, "far")
        
        if limit > 0:
            index_clauses = index_clauses[:limit]
        
        logger.info(f"Scraping details for {len(index_clauses)} FAR clauses...")
        
        for i, clause in enumerate(index_clauses):
            # For speed, we'll return index data without full scraping
            # Full scraping can be done on demand
            clauses.append({
                "clause_number": clause["clause_number"],
                "title": clause["title"],
                "type": "FAR",
                "date": None,
                "text": None,
                "html": None,
                "url": clause["url"]
            })
            
            # Rate limiting
            if (i + 1) % 50 == 0:
                logger.info(f"Processed {i + 1}/{len(index_clauses)} FAR clauses")
                await asyncio.sleep(0.1)
    
    return clauses


async def scrape_dfars_clauses(limit: int = 0) -> List[Dict]:
    """
    Scrape DFARS clauses from acquisition.gov.
    
    Returns list of dicts with:
    - clause_number: e.g., "252.204-7012"
    - title: clause title
    - type: "DFARS"
    """
    clauses = []
    
    async with httpx.AsyncClient(
        timeout=60.0,
        follow_redirects=True,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
    ) as client:
        # DFARS Part 252 - correct URL
        index_urls = [
            "https://www.acquisition.gov/dfars/part-252-solicitation-provisions-and-contract-clauses"
        ]
        
        seen_codes = set()
        
        for index_url in index_urls:
            logger.info(f"Fetching DFARS index from: {index_url}")
            
            html = await fetch_page(client, index_url)
            if not html:
                logger.warning(f"Failed to fetch {index_url}")
                continue
            
            soup = make_soup(html)
            main_region = extract_main_region(soup)
            
            # Find all links and headings that contain DFARS clause numbers (252.xxx-xxxx)
            for link in main_region.find_all('a', href=True):
                href = link.get('href', '')
                text = link.get_text(' ', strip=True)
                
                m = SECTION_RE.search(text)
                if m:
                    code = normalize_clause_id(m.group(1))
                    
                    # DFARS clauses start with 252.
                    if not code.startswith('252.'):
                        continue
                    
                    if code in seen_codes:
                        continue
                    seen_codes.add(code)
                    
                    # Extract title
                    title = text[m.end():].strip().lstrip(' .-–—:').strip()
                    
                    # Build full URL
                    if href.startswith('/'):
                        full_url = f"{BASE}{href}"
                    elif href.startswith('http'):
                        full_url = href
                    else:
                        full_url = f"{BASE}/{href}"
                    
                    clauses.append({
                        "clause_number": code,
                        "title": title or f"DFARS Clause {code}",
                        "type": "DFARS",
                        "date": None,
                        "text": None,
                        "html": None,
                        "url": full_url
                    })
            
            # Also check headings
            for heading in main_region.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
                text = heading.get_text(' ', strip=True)
                m = SECTION_RE.search(text)
                if m:
                    code = normalize_clause_id(m.group(1))
                    if not code.startswith('252.'):
                        continue
                    
                    if code in seen_codes:
                        continue
                    seen_codes.add(code)
                    
                    title = text[m.end():].strip().lstrip(' .-–—:').strip()
                    
                    clauses.append({
                        "clause_number": code,
                        "title": title or f"DFARS Clause {code}",
                        "type": "DFARS",
                        "date": None,
                        "text": None,
                        "html": None,
                        "url": f"{BASE}/dfars/{code}"
                    })
        
        logger.info(f"Found {len(clauses)} DFARS clauses from index")
    
    return clauses


async def scrape_all_clauses(clause_type: Optional[str] = None, limit: int = 0) -> List[Dict]:
    """
    Scrape all clauses from acquisition.gov.
    
    Args:
        clause_type: "FAR", "DFARS", or None for both
        limit: max clauses to return (0 for unlimited)
    
    Returns list of clause dicts.
    """
    clauses = []
    
    if clause_type is None or clause_type.upper() == "FAR":
        far_clauses = await scrape_far_clauses(limit)
        clauses.extend(far_clauses)
    
    if clause_type is None or clause_type.upper() == "DFARS":
        dfars_clauses = await scrape_dfars_clauses(limit)
        clauses.extend(dfars_clauses)
    
    logger.info(f"Total scraped: {len(clauses)} clauses")
    return clauses
