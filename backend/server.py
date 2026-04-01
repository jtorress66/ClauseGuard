from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, UploadFile, File, Depends
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import re
import unicodedata
import asyncio
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timezone, timedelta
import httpx
import io
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.units import inch

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Create the main app
app = FastAPI()

# Create routers
api_router = APIRouter(prefix="/api")
auth_router = APIRouter(prefix="/api/auth")
clauses_router = APIRouter(prefix="/api/clauses")
contracts_router = APIRouter(prefix="/api/contracts")
flowdown_router = APIRouter(prefix="/api/flowdown")
user_router = APIRouter(prefix="/api/user")
agiloft_router = APIRouter(prefix="/api/agiloft")
export_router = APIRouter(prefix="/api/export")

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ==================== Models ====================

class User(BaseModel):
    model_config = ConfigDict(extra="ignore")
    user_id: str
    email: str
    name: str
    picture: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class UserSession(BaseModel):
    model_config = ConfigDict(extra="ignore")
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    session_token: str
    expires_at: datetime
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class Clause(BaseModel):
    model_config = ConfigDict(extra="ignore")
    clause_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    number: str  # e.g., "52.212-4" or "252.204-7012"
    title: str
    type: str  # FAR, DFARS, Agency-specific
    text: str
    summary: Optional[str] = None
    flowdown_required: bool = False
    contract_types: List[str] = []  # e.g., ["Fixed-Price", "Cost-Reimbursement"]
    threshold_amount: Optional[float] = None
    last_updated: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    effective_date: Optional[datetime] = None
    keywords: List[str] = []

class Contract(BaseModel):
    model_config = ConfigDict(extra="ignore")
    contract_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    name: str
    filename: str
    content: str
    clauses_found: List[str] = []
    analysis_result: Optional[Dict[str, Any]] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class SavedSearch(BaseModel):
    model_config = ConfigDict(extra="ignore")
    search_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    query: str
    filters: Dict[str, Any] = {}
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class Annotation(BaseModel):
    model_config = ConfigDict(extra="ignore")
    annotation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    clause_id: str
    note: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class Favorite(BaseModel):
    model_config = ConfigDict(extra="ignore")
    favorite_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    clause_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class ComplianceChecklist(BaseModel):
    model_config = ConfigDict(extra="ignore")
    checklist_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    contract_id: str
    items: List[Dict[str, Any]] = []
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

# ==================== Request/Response Models ====================

class SessionRequest(BaseModel):
    session_id: str

class SearchRequest(BaseModel):
    query: str
    clause_type: Optional[str] = None
    limit: int = 20

class ContractUploadResponse(BaseModel):
    contract_id: str
    name: str
    clauses_found: List[str]

class AnnotationCreate(BaseModel):
    clause_id: str
    note: str

class FlowdownRequest(BaseModel):
    contract_type: str
    contract_value: float
    clauses: List[str]

# ==================== Helper Functions ====================

async def get_current_user(request: Request) -> Optional[User]:
    """Extract and validate user from session token"""
    session_token = request.cookies.get("session_token")
    if not session_token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            session_token = auth_header.split(" ")[1]

    if not session_token:
        return None

    session_doc = await db.user_sessions.find_one({"session_token": session_token}, {"_id": 0})
    if not session_doc:
        return None

    expires_at = session_doc.get("expires_at")
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        return None

    user_doc = await db.users.find_one({"user_id": session_doc["user_id"]}, {"_id": 0})
    if not user_doc:
        return None

    return User(**user_doc)

async def require_auth(request: Request) -> User:
    """Require authentication - raises HTTPException if not authenticated"""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user

async def get_ai_response(prompt: str, system_message: str = "You are a helpful assistant specialized in Federal Acquisition Regulations.") -> str:
    """Get AI response using OpenAI via emergentintegrations"""
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage

        api_key = os.environ.get("EMERGENT_LLM_KEY")
        logger.info(f"AI request - EMERGENT_LLM_KEY present: {bool(api_key)}")
        
        if not api_key:
            logger.warning("EMERGENT_LLM_KEY not found, returning placeholder response")
            return "AI analysis not available - API key not configured."

        chat = LlmChat(
            api_key=api_key,
            session_id=f"clause-analysis-{uuid.uuid4()}",
            system_message=system_message
        ).with_model("openai", "gpt-5.2")

        user_message = UserMessage(text=prompt)
        logger.info("Sending AI request...")
        response = await chat.send_message(user_message)
        logger.info(f"AI response received - length: {len(response)}")
        return response
    except Exception as e:
        logger.error(f"AI response error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return f"AI analysis temporarily unavailable: {str(e)}"

# ==================== Acquisition.gov Integration ====================

_dfars_page_cache: Dict[str, Any] = {}

async def _get_dfars_page_soup():
    """Fetch and cache the DFARS Part 252 page (single large page with all clauses)."""
    from bs4 import BeautifulSoup
    
    cache_key = "dfars_part_252"
    if cache_key in _dfars_page_cache:
        cache_entry = _dfars_page_cache[cache_key]
        age = (datetime.now(timezone.utc) - cache_entry["fetched_at"]).total_seconds()
        if age < 3600:  # Cache for 1 hour
            return cache_entry["soup"]
    
    dfars_url = "https://www.acquisition.gov/dfars/part-252-solicitation-provisions-and-contract-clauses"
    logger.info(f"Fetching DFARS Part 252 page: {dfars_url}")
    
    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
        client.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })
        response = await client.get(dfars_url)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            _dfars_page_cache[cache_key] = {
                "soup": soup,
                "fetched_at": datetime.now(timezone.utc)
            }
            return soup
    return None


async def fetch_clause_from_acquisition_gov(clause_number: str) -> Optional[Dict[str, Any]]:
    """Fetch clause details from acquisition.gov with proper formatting preservation.
    
    - FAR clauses: fetched from individual pages (e.g., /far/52.212-5)
    - DFARS clauses: extracted from the combined Part 252 page using anchor IDs
    """
    try:
        from bs4 import BeautifulSoup, Tag
        import re

        INDENT_SPACES = 4
        
        def _norm_spaces(s: str) -> str:
            return s.replace('\u00A0', ' ').replace('\u202F', ' ').replace('\xa0', ' ')
        
        def _get_list_depth(tag: Tag) -> int:
            depth = 0
            parent = tag.parent
            while parent:
                if parent.name in ('ul', 'ol', 'dl'):
                    depth += 1
                parent = parent.parent
            return depth
        
        def _get_style_indent(tag: Tag) -> int:
            style = tag.get('style', '')
            if not style:
                return 0
            indent = 0
            margin_match = re.search(r'margin-left:\s*(\d+(?:\.\d+)?)(em|px)', style)
            if margin_match:
                value = float(margin_match.group(1))
                unit = margin_match.group(2)
                if unit == 'em':
                    indent = int(value)
                elif unit == 'px':
                    indent = int(value / 16)
            return indent
        
        def _get_class_indent(tag: Tag) -> int:
            classes = tag.get('class', [])
            if isinstance(classes, str):
                classes = classes.split()
            for cls in classes:
                match = re.search(r'(?:indent|list)(\d+)', cls)
                if match:
                    return int(match.group(1))
            return 0
        
        def text_with_indents(root: Tag) -> str:
            lines = []
            
            def process_element(elem, base_indent=0):
                if isinstance(elem, str):
                    text = _norm_spaces(elem.strip())
                    if text:
                        lines.append(' ' * (base_indent * INDENT_SPACES) + text)
                    return
                
                if not isinstance(elem, Tag):
                    return
                
                if elem.name in ('script', 'style', 'nav', 'aside', 'footer', 'button'):
                    return
                
                list_depth = _get_list_depth(elem)
                style_indent = _get_style_indent(elem)
                class_indent = _get_class_indent(elem)
                indent = base_indent + max(list_depth, style_indent, class_indent)
                
                if elem.name in ('ul', 'ol'):
                    for li in elem.find_all('li', recursive=False):
                        process_element(li, indent)
                
                elif elem.name == 'li':
                    direct_text = []
                    for child in elem.children:
                        if isinstance(child, str):
                            text = _norm_spaces(child.strip())
                            if text:
                                direct_text.append(text)
                        elif child.name not in ('ul', 'ol', 'dl'):
                            text = _norm_spaces(child.get_text(' ', strip=True))
                            if text:
                                direct_text.append(text)
                    
                    if direct_text:
                        lines.append(' ' * (indent * INDENT_SPACES) + ' '.join(direct_text))
                    
                    for nested in elem.find_all(['ul', 'ol'], recursive=False):
                        process_element(nested, indent + 1)
                
                elif elem.name == 'p':
                    text = _norm_spaces(elem.get_text(' ', strip=True))
                    if text:
                        lines.append(' ' * (indent * INDENT_SPACES) + text)
                        lines.append('')
                
                elif elem.name in ('div', 'section', 'article'):
                    for child in elem.children:
                        if isinstance(child, Tag):
                            process_element(child, indent)
                
                elif elem.name in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
                    text = _norm_spaces(elem.get_text(' ', strip=True))
                    if text:
                        lines.append('')
                        lines.append(text)
                        lines.append('')
                
                elif elem.name == 'br':
                    lines.append('')
                
                elif elem.name == 'table':
                    for row in elem.find_all('tr'):
                        cells = [_norm_spaces(td.get_text(' ', strip=True)) for td in row.find_all(['td', 'th'])]
                        if any(cells):
                            lines.append(' ' * (indent * INDENT_SPACES) + ' | '.join(cells))
                
                else:
                    text = _norm_spaces(elem.get_text(' ', strip=True))
                    if text and len(text) > 5:
                        lines.append(' ' * (indent * INDENT_SPACES) + text)
            
            process_element(root)
            
            result = '\n'.join(lines)
            result = re.sub(r'\n{3,}', '\n\n', result)
            return result.strip()

        is_dfars = clause_number.startswith("252")
        clause_type = "DFARS" if is_dfars else "FAR"
        clause_url = f"https://www.acquisition.gov/dfars/part-252-solicitation-provisions-and-contract-clauses#DFARS_{clause_number}" if is_dfars else f"https://www.acquisition.gov/far/{clause_number.lower()}"

        logger.info(f"Fetching clause {clause_number} ({clause_type}) from acquisition.gov")

        if is_dfars:
            # DFARS: all clauses are on a single combined page, find by anchor ID
            soup = await _get_dfars_page_soup()
            if not soup:
                logger.warning(f"Failed to fetch DFARS Part 252 page")
                return None
            
            # Find the article element with id="DFARS_{clause_number}"
            anchor_id = f"DFARS_{clause_number}"
            clause_article = soup.find('article', id=anchor_id)
            
            if not clause_article:
                logger.warning(f"DFARS clause {clause_number} not found on page (anchor: {anchor_id})")
                return None
            
            # Extract title from the heading inside the article
            title = ""
            heading = clause_article.find(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
            if heading:
                title = _norm_spaces(heading.get_text(' ', strip=True))
                # Remove the clause number prefix
                title = re.sub(r'^\d+\.\d+-\d+\s*', '', title).strip()
                title = re.sub(r'^[-–—.]\s*', '', title).strip()
            
            # Extract text from the body div
            full_text = ""
            body_div = clause_article.find('div', class_='body')
            if body_div:
                full_text = text_with_indents(body_div)
            else:
                full_text = text_with_indents(clause_article)
        else:
            # FAR: each clause has its own page
            async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
                client.headers.update({
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                })
                
                response = await client.get(clause_url)
                logger.info(f"FAR response status: {response.status_code}")

                if response.status_code != 200:
                    logger.warning(f"Failed to fetch {clause_number}: HTTP {response.status_code}")
                    return None
                
                soup = BeautifulSoup(response.text, 'html.parser')

                title = ""
                page_title = soup.find('title')
                if page_title:
                    title_text = page_title.get_text().strip()
                    title = re.sub(r'^(FAR|DFARS)\s*', '', title_text)
                    title = re.sub(r'^\d+\.\d+-\d+\s*', '', title)
                    title = title.replace('| Acquisition.GOV', '').strip()
                    title = re.sub(r'^[-–—]\s*', '', title).strip()

                if not title:
                    h1 = soup.find('h1')
                    if h1:
                        title = h1.get_text().strip()
                        title = re.sub(r'^\d+\.\d+-\d+\s*', '', title)

                main_article = soup.find('article', class_='nested0')
                if not main_article:
                    main_article = soup.find('article')
                
                full_text = ""
                if main_article:
                    body_div = main_article.find('div', class_='body')
                    if body_div:
                        full_text = text_with_indents(body_div)
                    else:
                        full_text = text_with_indents(main_article)
                
                if not full_text or len(full_text) < 100:
                    text_parts = []
                    for p in soup.find_all('p'):
                        text = _norm_spaces(p.get_text(' ', strip=True))
                        if text and len(text) > 20:
                            text_parts.append(text)
                    full_text = '\n\n'.join(text_parts)

        # Limit size
        full_text = full_text[:50000]

        logger.info(f"Extracted title: {title[:80] if title else 'N/A'}...")
        logger.info(f"Extracted text length: {len(full_text)} chars")
        
        # Skip reserved clauses
        title_lower = title.lower() if title else ""
        is_reserved = (
            title_lower.endswith("reserved") or
            title_lower.endswith("[reserved]") or
            title_lower == "reserved" or
            "is reserved" in title_lower
        )
        
        if is_reserved:
            logger.info(f"Clause {clause_number} is reserved - skipping")
            return None

        # Extract keywords
        keywords = []
        keyword_patterns = [
            r'small business', r'cybersecurity', r'NIST', r'compliance',
            r'subcontract', r'flowdown', r'disclosure', r'payment',
            r'equal opportunity', r'Buy American', r'domestic', r'foreign',
            r'technical data', r'intellectual property', r'CUI', r'classified'
        ]
        for pattern in keyword_patterns:
            if re.search(pattern, full_text, re.IGNORECASE):
                keywords.append(pattern.replace(r'\s+', ' '))

        flowdown_required = bool(re.search(
            r'flow.?down|subcontract|lower.?tier|prime contractor shall',
            full_text, re.IGNORECASE
        ))

        return {
            "clause_id": str(uuid.uuid4()),
            "number": clause_number,
            "title": title or f"Clause {clause_number}",
            "type": clause_type,
            "text": full_text if full_text and len(full_text) > 100 else f"Content available at: {clause_url}",
            "summary": None,
            "flowdown_required": flowdown_required,
            "contract_types": [],
            "threshold_amount": None,
            "keywords": keywords[:10],
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "source": "acquisition.gov",
            "source_url": clause_url
        }

    except Exception as e:
        logger.error(f"Error fetching from acquisition.gov: {e}")
        import traceback
        traceback.print_exc()
        return None



# ---------- DITA Text Formatting Functions (based on user's desktop app) ----------
import html as _html

# Regex patterns for parsing
_P_TAG_RE = re.compile(r"(<p\b[^>]*>)(.*?)(</p>)", re.IGNORECASE | re.DOTALL)
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
_TAG_STRIP_RE = re.compile(r"<[^>]+>")
_NBSP_MULTI_RE = re.compile(r"(?:\s|&nbsp;)+", re.IGNORECASE)


def _inner_text_simple(inner_html):
    """Strips HTML tags and normalizes whitespace to get plain text."""
    if inner_html is None:
        return ""
    s = _TAG_STRIP_RE.sub("", inner_html)
    s = s.replace("\u00a0", " ")
    s = _NBSP_MULTI_RE.sub(" ", s)
    return (s or "").strip()


def _strip_leading_nbsp(html_text):
    """Removes leading non-breaking spaces and counts them."""
    if not html_text:
        return 0, html_text
    s = html_text.lstrip()
    cnt = 0
    while s.startswith("&nbsp;"):
        cnt += 1
        s = s[len("&nbsp;"):]
        s = s.lstrip()
    return cnt, s


def _detect_level_from_prefix(inner_html):
    """
    Detects the indentation level of a paragraph based on its prefix (e.g., (a), (1)).
    Returns an integer representing the level (0-4).
    """
    _, s = _strip_leading_nbsp(inner_html)
    s = (s or "").lstrip()

    # remove leading inline wrappers when checking token
    s_plain = re.sub(r"^\s*(?:</?(?:em|i|strong|b)\b[^>]*>\s*)+", "", s, flags=re.IGNORECASE)

    if re.match(r"^\([a-z]\)\s*", s_plain):  # (a)
        return 1
    if re.match(r"^\(\d+\)\s*", s_plain):    # (1)
        return 2
    if re.match(r"^\([ivxlcdm]+\)\s*", s_plain, flags=re.IGNORECASE):  # (i)
        return 3
    if re.match(r"^\([A-Z]\)\s*", s_plain):  # (A)
        return 4

    # fallback: existing nbsp indent
    nbsp_count, _ = _strip_leading_nbsp(inner_html)
    if nbsp_count >= 12: return 4
    if nbsp_count >= 9:  return 3
    if nbsp_count >= 6:  return 2
    if nbsp_count >= 3:  return 1
    return 0


def _indent_style_for_level(level):
    """
    Generates CSS 'style' attribute for indentation based on list level.
    Level 0 returns "" so we don't force blocky paragraphs.
    """
    hanging = "1.6em"
    pads = {
        1: "1.6em",  # (a)
        2: "3.1em",  # (1)
        3: "4.6em",  # (i)
        4: "6.1em",  # (A)
    }
    lvl = int(level or 0)
    if lvl <= 0:
        return ""
    pad = pads.get(lvl, "0em")
    return f"margin:0 0 10px 0; padding-left:{pad}; text-indent:-{hanging};"


def _append_or_add_style(open_p_tag, style_to_add):
    """Appends a new style to an existing 'style' attribute or adds a new one."""
    if not style_to_add:
        return open_p_tag

    if re.search(r'\bstyle\s*=\s*["\']', open_p_tag, flags=re.IGNORECASE):
        def _append_style(m):
            existing = (m.group(1) or "").strip()
            if existing and not existing.endswith(";"):
                existing += ";"
            return f'style="{existing} {style_to_add}"'
        return re.sub(
            r'\bstyle\s*=\s*["\']([^"\']*)["\']',
            _append_style,
            open_p_tag,
            count=1,
            flags=re.IGNORECASE
        )

    return open_p_tag[:-1] + f' style="{style_to_add}">'


def _should_center_end_marker(inner_html):
    """Checks if the text is an 'End of clause' marker."""
    t = _inner_text_simple(inner_html).lower()
    return t in ("(end of clause)", "(end of provision)")


def _add_inline_indent_and_alignment(open_p_tag, inner_html):
    """Applies indentation and text alignment styles to an opening <p> tag."""
    level = _detect_level_from_prefix(inner_html)
    indent_style = _indent_style_for_level(level)
    if indent_style:
        open_p_tag = _append_or_add_style(open_p_tag, indent_style)

    if _should_center_end_marker(inner_html):
        open_p_tag = _append_or_add_style(open_p_tag, "text-align:center;")

    return open_p_tag


def _ensure_paragraphs(html):
    """
    CRITICAL FOR THE 'BLOCK WALL OF TEXT' ISSUE:
    If the HTML comes without <p> tags (or with <br> only),
    this converts <br>/newlines into <p> blocks.
    """
    if not html:
        return html

    # If <p> tags are already present, assume it's structured
    if re.search(r"<p\b", html, flags=re.IGNORECASE):
        return html

    # Replace <br> and newlines with a single newline character
    s = _BR_RE.sub("\n", html)
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    parts = [p.strip() for p in s.split("\n") if p.strip()]

    if len(parts) <= 1:
        return html

    # Wrap each non-empty part in <p> tags
    return "".join([f"<p>{p}</p>" for p in parts])


def _normalize_clause_indent_html(html):
    """
    Processes raw HTML to ensure proper paragraph structure and applies indentation.
    This is the core HTML formatting logic for clauses.
    """
    if not html:
        return html

    # First, ensure all content is wrapped in <p> tags
    html = _ensure_paragraphs(html)

    def _repl(m):
        p_open = m.group(1)
        inner = m.group(2) or ""
        p_close = m.group(3)

        new_open = _add_inline_indent_and_alignment(p_open, inner)
        return new_open + inner + p_close

    return _P_TAG_RE.sub(_repl, html)


def format_dita_html_for_agiloft(html_content):
    """
    Main function to format DITA HTML for proper display in Agiloft and web display.
    Uses the desktop app's formatting approach plus class-based detection.
    """
    if not html_content:
        return html_content
    
    from bs4 import BeautifulSoup
    
    # First apply class-based indentation for acquisition.gov HTML structure
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Map ListL classes to indentation levels
    class_to_level = {
        'ListL1': 1,
        'ListL2': 2,
        'ListL3': 3,
        'ListL4': 4,
    }
    
    # Classes that should be centered
    centered_classes = {'Ctr_SmCaps', 'Ctr', 'Endofclause'}
    
    for p in soup.find_all('p'):
        classes = p.get('class', [])
        if isinstance(classes, str):
            classes = classes.split()
        
        # Detect level from class name
        level = 0
        for cls in classes:
            if cls in class_to_level:
                level = class_to_level[cls]
                break
        
        # Also detect from prefix patterns if no class-based level
        if level == 0:
            text = p.get_text().strip()
            level = _detect_level_from_prefix(text)
        
        # Apply indentation style if needed
        if level > 0:
            indent_style = _indent_style_for_level(level)
            existing_style = p.get('style', '')
            if existing_style and not existing_style.endswith(';'):
                existing_style += ';'
            p['style'] = f"{existing_style} {indent_style}".strip()
        
        # Check for centered classes (Ctr_SmCaps, Endofclause, etc.)
        should_center = any(cls in centered_classes for cls in classes)
        
        # Also check for "(End of clause)" text markers
        text = p.get_text().strip().lower()
        if text in ['(end of clause)', '(end of provision)']:
            should_center = True
        
        # Apply centering if needed
        if should_center:
            existing_style = p.get('style', '')
            if existing_style and not existing_style.endswith(';'):
                existing_style += ';'
            p['style'] = f"{existing_style} text-align:center;".strip()
    
    return str(soup)


async def fetch_clause_dita_from_acquisition_gov(clause_number: str) -> Optional[str]:
    """
    Fetch raw DITA XML for a clause from acquisition.gov.
    Agiloft renders DITA XML properly when uploaded to clause_text field.
    Also removes <ol>/<ul>/<li> tags to prevent Agiloft from adding duplicate numbering.
    """
    import zipfile
    import io
    
    try:
        # Determine part number from clause number (e.g., 52.203-12 -> part_52)
        part_num = clause_number.split('.')[0]
        
        # FAR clauses are in Part 52, DFARS in Part 252
        if clause_number.startswith("252"):
            zip_url = "https://www.acquisition.gov/sites/default/files/current/dfars/compiled_dita/part_252.zip"
            folder_name = "part_252"
        else:
            zip_url = f"https://www.acquisition.gov/sites/default/files/current/far/compiled_dita/part_{part_num}.zip"
            folder_name = f"part_{part_num}"
        
        logger.info(f"Fetching DITA ZIP from: {zip_url}")
        
        async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
            response = await client.get(zip_url)
            
            if response.status_code == 200:
                # Read ZIP file from response
                zip_data = io.BytesIO(response.content)
                
                with zipfile.ZipFile(zip_data, 'r') as zip_ref:
                    # Look for the specific clause file
                    # File naming varies: 52.203-12.dita or 52.203-12.dita
                    possible_names = [
                        f"{folder_name}/{clause_number}.dita",
                        f"{folder_name}/{clause_number.lower()}.dita",
                        f"{folder_name}/{clause_number.upper()}.dita",
                    ]
                    
                    dita_content = None
                    for name in possible_names:
                        try:
                            dita_content = zip_ref.read(name).decode('utf-8')
                            logger.info(f"Found DITA file: {name}")
                            break
                        except KeyError:
                            continue
                    
                    if dita_content:
                        # Remove <ol>, <ul>, <li> tags to prevent Agiloft from adding duplicate numbering
                        # Agiloft renders these as numbered lists, but DITA already has (a), (b), (1), (2)
                        dita_content = _suppress_dita_list_tags(dita_content)
                        
                        logger.info(f"Extracted and processed DITA XML length: {len(dita_content)} chars")
                        return dita_content
                    else:
                        # List available files for debugging
                        available = [f for f in zip_ref.namelist() if clause_number.split('-')[0] in f]
                        logger.warning(f"Clause {clause_number} not found. Available similar files: {available[:5]}")
            else:
                logger.warning(f"Failed to download DITA ZIP: HTTP {response.status_code}")
        
        return None
        
    except Exception as e:
        logger.error(f"Error fetching DITA from acquisition.gov: {e}")
        import traceback
        traceback.print_exc()
        return None


def _suppress_dita_list_tags(dita_content: str) -> str:
    """
    Remove <ol>, <ul> tags and convert <li> to styled <div> tags to prevent Agiloft 
    from adding its own numbering, while preserving indentation via margin-left.
    """
    if not dita_content:
        return dita_content
    
    from bs4 import BeautifulSoup
    
    soup = BeautifulSoup(dita_content, 'html.parser')
    
    def get_nesting_level(element):
        """Count how many ol/ul ancestors an element has."""
        level = 0
        parent = element.parent
        while parent:
            if parent.name in ['ol', 'ul']:
                level += 1
            parent = parent.parent
        return level
    
    # Process all list items first (before removing ol/ul)
    for li in soup.find_all('li'):
        level = get_nesting_level(li)
        # Create a new div with appropriate margin
        margin = f"{level * 2}em"  # 2em per nesting level
        
        # Create new div tag
        new_div = soup.new_tag('div')
        new_div['style'] = f'margin-left: {margin}; margin-bottom: 0.5em;'
        
        # Move all children to new div
        for child in list(li.children):
            new_div.append(child.extract() if hasattr(child, 'extract') else child)
        
        li.replace_with(new_div)
    
    # Now remove ol and ul tags but keep their content
    for ol in soup.find_all(['ol', 'ul']):
        ol.unwrap()  # Remove tag but keep content
    
    return str(soup)


async def fetch_clause_html_from_acquisition_gov(clause_number: str) -> Optional[str]:
    """
    Fetch clause content as DITA-style HTML from acquisition.gov for proper formatting in Agiloft.
    - FAR clauses: fetched from individual pages
    - DFARS clauses: extracted from combined Part 252 page using anchor IDs
    """
    from bs4 import BeautifulSoup
    
    try:
        is_dfars = clause_number.startswith("252")

        if is_dfars:
            soup = await _get_dfars_page_soup()
            if not soup:
                logger.warning(f"Failed to fetch DFARS Part 252 page for HTML extraction")
                return None
            
            anchor_id = f"DFARS_{clause_number}"
            clause_article = soup.find('article', id=anchor_id)
            if not clause_article:
                logger.warning(f"DFARS clause {clause_number} not found (anchor: {anchor_id})")
                return None
            
            body_div = clause_article.find('div', class_='body')
            if body_div:
                for tag in body_div.find_all(['script', 'style', 'nav', 'aside', 'button']):
                    tag.decompose()
                html_content = str(body_div)
                html_content = format_dita_html_for_agiloft(html_content)
                logger.info(f"Extracted DFARS DITA HTML length: {len(html_content)} chars")
                return html_content
            return None
        else:
            clause_url = f"https://www.acquisition.gov/far/{clause_number.lower()}"
            logger.info(f"Fetching DITA HTML from: {clause_url}")

            async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
                client.headers.update({
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                })
                
                response = await client.get(clause_url)

                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, 'html.parser')

                    body_div = soup.find('div', class_='body')
                    if not body_div:
                        article = soup.find('article', class_='nested0')
                        if article:
                            body_div = article.find('div', class_='body')
                    
                    if body_div:
                        for tag in body_div.find_all(['script', 'style', 'nav', 'aside', 'button']):
                            tag.decompose()
                        html_content = str(body_div)
                        html_content = format_dita_html_for_agiloft(html_content)
                        logger.info(f"Extracted and formatted DITA HTML length: {len(html_content)} chars")
                        return html_content
                
                logger.warning(f"Failed to fetch HTML for {clause_number}: HTTP {response.status_code}")
                return None
            
    except Exception as e:
        logger.error(f"Error fetching DITA HTML from acquisition.gov: {e}")
        return None


async def fetch_far_index() -> List[Dict[str, str]]:
    """Fetch FAR clause index from acquisition.gov - improved to match reference implementation"""
    clauses = []
    SECTION_RE = re.compile(r"(?<!\d)(\d{1,4}\.\d{1,4}(?:[-–—](?=\d)\d{1,6})*)(?!\d)")
    
    try:
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            client.headers.update({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            })
            
            # Fetch Part 52 index (main FAR contract clauses)
            part_urls = [
                "https://www.acquisition.gov/far/part-52"
            ]
            
            # First, get the main FAR page to discover all Part 52 subsections
            main_response = await client.get("https://www.acquisition.gov/far/part-52")
            if main_response.status_code == 200:
                from bs4 import BeautifulSoup
                main_soup = BeautifulSoup(main_response.text, 'html.parser')
                
                # Find all links to subparts of Part 52
                for link in main_soup.find_all('a', href=True):
                    href = link.get('href', '')
                    if '/far/part-52' in href.lower() and href not in part_urls:
                        full_url = f"https://www.acquisition.gov{href}" if href.startswith('/') else href
                        if full_url.startswith('https://www.acquisition.gov/far/'):
                            part_urls.append(full_url)
            
            # Limit to prevent too many requests
            part_urls = list(set(part_urls))[:20]
            
            for part_url in part_urls:
                try:
                    response = await client.get(part_url)
                    
                    if response.status_code == 200:
                        from bs4 import BeautifulSoup
                        soup = BeautifulSoup(response.text, 'html.parser')
                        
                        # Extract clauses from headings (h2, h3, h4, h5, h6)
                        for heading in soup.find_all(['h2', 'h3', 'h4', 'h5', 'h6']):
                            text = heading.get_text(' ', strip=True)
                            match = SECTION_RE.search(text)
                            if match:
                                clause_num = normalize_clause_number_acqgov(match.group(1))
                                # Extract title after the clause number
                                title = text.split(match.group(0), 1)[-1].strip()
                                title = title.lstrip(' .-–—:').strip()
                                
                                if clause_num and clause_num.startswith('52.'):
                                    clauses.append({
                                        "number": clause_num,
                                        "title": title or f"FAR Clause {clause_num}",
                                        "type": "FAR"
                                    })
                        
                        # Also check links that might contain clause references
                        for link in soup.find_all('a'):
                            link_text = link.get_text(' ', strip=True)
                            match = SECTION_RE.search(link_text)
                            if match:
                                clause_num = normalize_clause_number_acqgov(match.group(1))
                                title = link_text.split(match.group(0), 1)[-1].strip()
                                title = title.lstrip(' .-–—:').strip()
                                
                                if clause_num and clause_num.startswith('52.'):
                                    clauses.append({
                                        "number": clause_num,
                                        "title": title or f"FAR Clause {clause_num}",
                                        "type": "FAR"
                                    })
                    
                    await asyncio.sleep(0.2)  # Be respectful to the server
                    
                except Exception as e:
                    logger.warning(f"Error fetching {part_url}: {e}")
                    continue
            
            # Remove duplicates, keeping the one with the longest title
            clause_map = {}
            for c in clauses:
                num = c["number"]
                if num not in clause_map or len(c["title"]) > len(clause_map[num]["title"]):
                    clause_map[num] = c
            
            return list(clause_map.values())
    
    except Exception as e:
        logger.error(f"Error fetching FAR index: {e}")
    
    return clauses

def normalize_clause_number_acqgov(clause_id: str) -> str:
    """Normalize clause number from acquisition.gov - handles dashes and formatting"""
    if not clause_id:
        return clause_id
    
    # Replace en-dash, em-dash with regular hyphen
    _DASHES = "\u2010\u2011\u2012\u2013\u2014\u2212"
    s = unicodedata.normalize("NFKC", str(clause_id))
    s = re.sub(f"[{re.escape(_DASHES)}]", "-", s)
    s = s.replace("\u00A0", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s

async def fetch_dfars_index() -> List[Dict[str, str]]:
    """Fetch DFARS clause index from acquisition.gov"""
    clauses = []
    SECTION_RE = re.compile(r"(?<!\d)(\d{1,4}\.\d{1,4}(?:[-–—](?=\d)\d{1,6})*)(?!\d)")
    
    try:
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            client.headers.update({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            })
            
            # DFARS Part 252 contains the clauses
            part_urls = ["https://www.acquisition.gov/dfars/part-252"]
            
            # First, discover all Part 252 subsections
            main_response = await client.get("https://www.acquisition.gov/dfars/part-252")
            if main_response.status_code == 200:
                from bs4 import BeautifulSoup
                main_soup = BeautifulSoup(main_response.text, 'html.parser')
                
                for link in main_soup.find_all('a', href=True):
                    href = link.get('href', '')
                    if '/dfars/part-252' in href.lower() or '/dfars/252' in href.lower():
                        full_url = f"https://www.acquisition.gov{href}" if href.startswith('/') else href
                        if full_url.startswith('https://www.acquisition.gov/dfars/'):
                            part_urls.append(full_url)
            
            # Limit to prevent too many requests
            part_urls = list(set(part_urls))[:20]
            
            for part_url in part_urls:
                try:
                    response = await client.get(part_url)
                    
                    if response.status_code == 200:
                        from bs4 import BeautifulSoup
                        soup = BeautifulSoup(response.text, 'html.parser')
                        
                        # Extract clauses from headings
                        for heading in soup.find_all(['h2', 'h3', 'h4', 'h5', 'h6']):
                            text = heading.get_text(' ', strip=True)
                            match = SECTION_RE.search(text)
                            if match:
                                clause_num = normalize_clause_number_acqgov(match.group(1))
                                title = text.split(match.group(0), 1)[-1].strip()
                                title = title.lstrip(' .-–—:').strip()
                                
                                if clause_num and clause_num.startswith('252.'):
                                    clauses.append({
                                        "number": clause_num,
                                        "title": title or f"DFARS Clause {clause_num}",
                                        "type": "DFARS"
                                    })
                        
                        # Also check links
                        for link in soup.find_all('a'):
                            link_text = link.get_text(' ', strip=True)
                            match = SECTION_RE.search(link_text)
                            if match:
                                clause_num = normalize_clause_number_acqgov(match.group(1))
                                title = link_text.split(match.group(0), 1)[-1].strip()
                                title = title.lstrip(' .-–—:').strip()
                                
                                if clause_num and clause_num.startswith('252.'):
                                    clauses.append({
                                        "number": clause_num,
                                        "title": title or f"DFARS Clause {clause_num}",
                                        "type": "DFARS"
                                    })
                    
                    await asyncio.sleep(0.2)
                    
                except Exception as e:
                    logger.warning(f"Error fetching {part_url}: {e}")
                    continue
            
            # Remove duplicates
            clause_map = {}
            for c in clauses:
                num = c["number"]
                if num not in clause_map or len(c["title"]) > len(clause_map[num]["title"]):
                    clause_map[num] = c
            
            return list(clause_map.values())
    
    except Exception as e:
        logger.error(f"Error fetching DFARS index: {e}")
    
    return clauses

# ==================== Initialize Sample Data ====================

async def init_sample_clauses():
    """Initialize sample FAR/DFARS clauses if not exists"""
    count = await db.clauses.count_documents({})
    if count > 0:
        return

    sample_clauses = [
        {
            "clause_id": str(uuid.uuid4()),
            "number": "52.212-4",
            "title": "Contract Terms and Conditions—Commercial Products and Commercial Services",
            "type": "FAR",
            "text": "This clause sets forth the terms and conditions applicable to the acquisition of commercial products and commercial services. It includes provisions for inspection and acceptance, invoicing and payment, changes, disputes, and other standard commercial terms.",
            "summary": "Standard terms for commercial acquisitions",
            "flowdown_required": True,
            "contract_types": ["Fixed-Price", "Time-and-Materials"],
            "threshold_amount": 0,
            "keywords": ["commercial", "terms", "conditions", "payment", "disputes"],
            "last_updated": datetime.now(timezone.utc).isoformat()
        },
        {
            "clause_id": str(uuid.uuid4()),
            "number": "252.204-7012",
            "title": "Safeguarding Covered Defense Information and Cyber Incident Reporting",
            "type": "DFARS",
            "text": "This clause requires contractors to provide adequate security on all covered contractor information systems and to report cyber incidents within 72 hours. Contractors must implement NIST SP 800-171 requirements.",
            "summary": "Cybersecurity requirements for defense contractors",
            "flowdown_required": True,
            "contract_types": ["All"],
            "threshold_amount": 0,
            "keywords": ["cybersecurity", "NIST", "defense", "CUI", "incident reporting"],
            "last_updated": datetime.now(timezone.utc).isoformat()
        },
        {
            "clause_id": str(uuid.uuid4()),
            "number": "52.219-8",
            "title": "Utilization of Small Business Concerns",
            "type": "FAR",
            "text": "This clause requires contractors to provide maximum practicable opportunities to small business concerns, veteran-owned small business concerns, service-disabled veteran-owned small business concerns, HUBZone small business concerns, small disadvantaged business concerns, and women-owned small business concerns.",
            "summary": "Small business subcontracting requirements",
            "flowdown_required": True,
            "contract_types": ["All"],
            "threshold_amount": 750000,
            "keywords": ["small business", "subcontracting", "HUBZone", "SDVOSB", "WOSB"],
            "last_updated": datetime.now(timezone.utc).isoformat()
        },
        {
            "clause_id": str(uuid.uuid4()),
            "number": "52.222-26",
            "title": "Equal Opportunity",
            "type": "FAR",
            "text": "This clause prohibits discrimination and requires contractors to take affirmative action to ensure equal opportunity in employment without regard to race, color, religion, sex, sexual orientation, gender identity, national origin, disability, or status as a protected veteran.",
            "summary": "Equal employment opportunity requirements",
            "flowdown_required": True,
            "contract_types": ["All"],
            "threshold_amount": 10000,
            "keywords": ["equal opportunity", "discrimination", "affirmative action", "EEO"],
            "last_updated": datetime.now(timezone.utc).isoformat()
        },
        {
            "clause_id": str(uuid.uuid4()),
            "number": "52.223-3",
            "title": "Hazardous Material Identification and Material Safety Data",
            "type": "FAR",
            "text": "This clause requires contractors to identify hazardous materials delivered under the contract and provide Safety Data Sheets (SDS) for those materials in accordance with 29 CFR 1910.1200.",
            "summary": "Hazardous material disclosure requirements",
            "flowdown_required": False,
            "contract_types": ["Supply", "Services"],
            "threshold_amount": 0,
            "keywords": ["hazardous", "safety", "SDS", "OSHA", "materials"],
            "last_updated": datetime.now(timezone.utc).isoformat()
        },
        {
            "clause_id": str(uuid.uuid4()),
            "number": "252.225-7001",
            "title": "Buy American and Balance of Payments Program",
            "type": "DFARS",
            "text": "This clause implements the Buy American statute and the Balance of Payments Program for defense acquisitions. It requires delivery of domestic end products unless specified exceptions apply.",
            "summary": "Buy American requirements for defense contracts",
            "flowdown_required": True,
            "contract_types": ["Supply"],
            "threshold_amount": 0,
            "keywords": ["Buy American", "domestic", "defense", "foreign"],
            "last_updated": datetime.now(timezone.utc).isoformat()
        },
        {
            "clause_id": str(uuid.uuid4()),
            "number": "52.232-40",
            "title": "Providing Accelerated Payments to Small Business Subcontractors",
            "type": "FAR",
            "text": "This clause requires prime contractors to make accelerated payments to small business subcontractors to the maximum extent practicable when the Government makes accelerated payments to the prime contractor.",
            "summary": "Accelerated payment flow-down to small business",
            "flowdown_required": True,
            "contract_types": ["All"],
            "threshold_amount": 0,
            "keywords": ["payment", "small business", "accelerated", "subcontractor"],
            "last_updated": datetime.now(timezone.utc).isoformat()
        },
        {
            "clause_id": str(uuid.uuid4()),
            "number": "52.244-6",
            "title": "Subcontracts for Commercial Products and Commercial Services",
            "type": "FAR",
            "text": "This clause applies to subcontracts for commercial products or commercial services. It specifies which FAR clauses must be flowed down to subcontractors at all tiers.",
            "summary": "Commercial subcontract flow-down requirements",
            "flowdown_required": True,
            "contract_types": ["All"],
            "threshold_amount": 0,
            "keywords": ["subcontract", "commercial", "flow-down", "tiers"],
            "last_updated": datetime.now(timezone.utc).isoformat()
        },
        {
            "clause_id": str(uuid.uuid4()),
            "number": "252.227-7013",
            "title": "Rights in Technical Data—Noncommercial Items",
            "type": "DFARS",
            "text": "This clause governs the Government's rights in technical data pertaining to noncommercial items. It establishes categories of data rights including unlimited rights, government purpose rights, and limited rights.",
            "summary": "Technical data rights for noncommercial defense items",
            "flowdown_required": True,
            "contract_types": ["R&D", "Supply"],
            "threshold_amount": 0,
            "keywords": ["technical data", "rights", "IP", "noncommercial", "defense"],
            "last_updated": datetime.now(timezone.utc).isoformat()
        },
        {
            "clause_id": str(uuid.uuid4()),
            "number": "52.203-13",
            "title": "Contractor Code of Business Ethics and Conduct",
            "type": "FAR",
            "text": "This clause requires contractors to have a written code of business ethics and conduct, and an employee business ethics and compliance training program and internal control system that facilitate timely discovery and disclosure of improper conduct.",
            "summary": "Ethics and compliance program requirements",
            "flowdown_required": True,
            "contract_types": ["All"],
            "threshold_amount": 6000000,
            "keywords": ["ethics", "compliance", "conduct", "training", "disclosure"],
            "last_updated": datetime.now(timezone.utc).isoformat()
        }
    ]

    await db.clauses.insert_many(sample_clauses)
    logger.info(f"Initialized {len(sample_clauses)} sample clauses")

# ==================== Auth Routes ====================

from passlib.context import CryptContext

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    """Hash a password for storing."""
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a stored password against a provided password."""
    return pwd_context.verify(plain_password, hashed_password)

class RegisterRequest(BaseModel):
    """User registration request"""
    email: str
    password: str
    name: str

class LoginRequest(BaseModel):
    """User login request"""
    email: str
    password: str

@auth_router.post("/register")
async def register_user(request: RegisterRequest, response: Response):
    """Register a new user with email and password"""
    # Validate email format
    import re
    if not re.match(r"[^@]+@[^@]+\.[^@]+", request.email):
        raise HTTPException(status_code=400, detail="Invalid email format")
    
    # Check password strength
    if len(request.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    
    # Check if email already exists
    existing_user = await db.users.find_one({"email": request.email.lower()}, {"_id": 0})
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Create user
    user_id = f"user_{uuid.uuid4().hex[:12]}"
    hashed_password = hash_password(request.password)
    
    new_user = {
        "user_id": user_id,
        "email": request.email.lower(),
        "name": request.name,
        "password_hash": hashed_password,
        "picture": None,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.users.insert_one(new_user)
    
    # Create session
    session_token = str(uuid.uuid4())
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    
    session_doc = {
        "session_id": str(uuid.uuid4()),
        "user_id": user_id,
        "session_token": session_token,
        "expires_at": expires_at.isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.user_sessions.insert_one(session_doc)
    
    # Set cookie
    response.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        secure=True,
        samesite="none",
        path="/",
        max_age=7 * 24 * 60 * 60
    )
    
    # Return user without password
    return {
        "user_id": user_id,
        "email": request.email.lower(),
        "name": request.name,
        "picture": None
    }

@auth_router.post("/login")
async def login_user(request: LoginRequest, response: Response):
    """Login with email and password"""
    # Find user
    user_doc = await db.users.find_one({"email": request.email.lower()})
    if not user_doc:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    # Verify password
    if not user_doc.get("password_hash"):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    if not verify_password(request.password, user_doc["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    # Create new session
    session_token = str(uuid.uuid4())
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    
    session_doc = {
        "session_id": str(uuid.uuid4()),
        "user_id": user_doc["user_id"],
        "session_token": session_token,
        "expires_at": expires_at.isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.user_sessions.insert_one(session_doc)
    
    # Set cookie
    response.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        secure=True,
        samesite="none",
        path="/",
        max_age=7 * 24 * 60 * 60
    )
    
    # Return user without password
    return {
        "user_id": user_doc["user_id"],
        "email": user_doc["email"],
        "name": user_doc["name"],
        "picture": user_doc.get("picture")
    }

@auth_router.post("/session")
async def create_session(request: SessionRequest, response: Response):
    """Exchange session_id for session_token (legacy Google OAuth - kept for compatibility)"""
    try:
        async with httpx.AsyncClient() as client:
            auth_response = await client.get(
                "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
                headers={"X-Session-ID": request.session_id}
            )

            if auth_response.status_code != 200:
                raise HTTPException(status_code=401, detail="Invalid session")

            auth_data = auth_response.json()
    except httpx.HTTPError as e:
        logger.error(f"Auth service error: {e}")
        raise HTTPException(status_code=500, detail="Authentication service unavailable")

    # Find or create user
    user_id = f"user_{uuid.uuid4().hex[:12]}"
    existing_user = await db.users.find_one({"email": auth_data["email"]}, {"_id": 0})

    if existing_user:
        user_id = existing_user["user_id"]
        await db.users.update_one(
            {"user_id": user_id},
            {"$set": {"name": auth_data["name"], "picture": auth_data.get("picture")}}
        )
    else:
        new_user = {
            "user_id": user_id,
            "email": auth_data["email"],
            "name": auth_data["name"],
            "picture": auth_data.get("picture"),
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db.users.insert_one(new_user)

    # Create session
    session_token = auth_data["session_token"]
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)

    session_doc = {
        "session_id": str(uuid.uuid4()),
        "user_id": user_id,
        "session_token": session_token,
        "expires_at": expires_at.isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.user_sessions.insert_one(session_doc)

    # Set cookie
    response.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        secure=True,
        samesite="none",
        path="/",
        max_age=7 * 24 * 60 * 60
    )

    user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    return user_doc

@auth_router.get("/me")
async def get_current_user_info(request: Request):
    """Get current authenticated user info"""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user.model_dump()

@auth_router.post("/logout")
async def logout(request: Request, response: Response):
    """Logout user and clear session"""
    session_token = request.cookies.get("session_token")
    if session_token:
        await db.user_sessions.delete_one({"session_token": session_token})

    response.delete_cookie(key="session_token", path="/")
    return {"message": "Logged out successfully"}

# ==================== Clauses Routes ====================

@clauses_router.get("/search")
async def search_clauses(query: str, clause_type: Optional[str] = None, limit: int = 20):
    """Search clauses with optional AI enhancement"""
    filter_query = {}

    if clause_type and clause_type != "All":
        filter_query["type"] = clause_type

    # Text search on multiple fields
    if query:
        filter_query["$or"] = [
            {"number": {"$regex": query, "$options": "i"}},
            {"title": {"$regex": query, "$options": "i"}},
            {"text": {"$regex": query, "$options": "i"}},
            {"keywords": {"$elemMatch": {"$regex": query, "$options": "i"}}}
        ]

    clauses = await db.clauses.find(filter_query, {"_id": 0}).limit(limit).to_list(limit)
    return {"clauses": clauses, "total": len(clauses)}

@clauses_router.get("/ai-search")
async def ai_search_clauses(query: str, request: Request, clause_type: Optional[str] = None):
    """AI-powered intelligent clause search - ONLY searches indexed acquisition.gov data
    
    This endpoint:
    - Searches ONLY clauses already indexed in our database from acquisition.gov
    - Does NOT generate or fabricate clause text
    - Uses AI to understand query intent and match to relevant existing clauses
    """
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required for AI search")

    # Build filter based on query and clause_type parameter
    filter_query = {}
    
    # Detect clause type from query if not explicitly provided
    detected_type = None
    if query.strip().startswith("252.") or "DFARS" in query.upper():
        detected_type = "DFARS"
    elif query.strip().startswith("52.") or "FAR" in query.upper():
        detected_type = "FAR"
    
    # Use explicit clause_type parameter if provided, otherwise use detected type
    effective_type = clause_type if clause_type and clause_type != "All" else detected_type
    
    if effective_type:
        filter_query["type"] = effective_type
        logger.info(f"AI Search filtering by type: {effective_type}")

    # Get indexed clauses from our database (sourced from acquisition.gov)
    # Increased limit to ensure all relevant clauses are included
    all_clauses = await db.clauses.find(
        filter_query, 
        {"_id": 0, "clause_id": 1, "number": 1, "title": 1, "type": 1, "summary": 1, "keywords": 1, "text": 1}
    ).to_list(1000)
    
    if not all_clauses:
        return {
            "clauses": [],
            "ai_analysis": "No clauses indexed yet. Please sync from acquisition.gov first.",
            "total": 0,
            "source": "acquisition.gov"
        }

    # Build context from indexed clauses - include text snippets for better matching
    clauses_context = "\n".join([
        f"- {c['number']}: {c['title']} ({c['type']}) | Keywords: {', '.join(c.get('keywords', [])[:5])} | Summary: {(c.get('summary') or 'N/A')[:150]}"
        for c in all_clauses
    ])

    prompt = f"""You are a Federal Acquisition Regulation (FAR/DFARS) expert assistant. 
Your task is to identify which clauses from our INDEXED database are most relevant to the user's query.

IMPORTANT RULES:
1. ONLY recommend clauses that appear in the "Available Clauses" list below
2. DO NOT invent or fabricate clause numbers that are not in the list
3. DO NOT generate clause text - only explain why each existing clause is relevant
4. If no clauses match, say "No matching clauses found in the indexed database"

Available Clauses (from acquisition.gov):
{clauses_context}

User Query: {query}

Respond with ONLY a JSON object in this exact format:
{{"relevant_clauses": ["52.xxx-x", "252.xxx-xxxx"], "explanations": {{"52.xxx-x": "Brief explanation of relevance", "252.xxx-xxxx": "Brief explanation"}}}}

If no clauses match the query, respond with: {{"relevant_clauses": [], "explanations": {{}}}}"""

    ai_response = await get_ai_response(prompt, 
        system_message="You are a FAR/DFARS clause expert. You ONLY recommend clauses from the provided list - never invent clauses. Keep explanations brief and accurate.")

    # Parse AI response and get full clause details
    relevant_numbers = []
    explanations = {}
    
    try:
        import json
        # Try to extract JSON from response
        json_start = ai_response.find('{')
        json_end = ai_response.rfind('}') + 1
        if json_start >= 0 and json_end > json_start:
            ai_result = json.loads(ai_response[json_start:json_end])
            relevant_numbers = ai_result.get("relevant_clauses", [])
            explanations = ai_result.get("explanations", {})
    except Exception as e:
        logger.warning(f"Failed to parse AI response: {e}")
        relevant_numbers = []
        explanations = {}

    # CRITICAL: Only fetch clauses that actually exist in our database
    # This ensures we never return fabricated data
    clauses = []
    valid_clause_numbers = {c["number"] for c in all_clauses}
    
    for number in relevant_numbers:
        # Verify the clause exists in our indexed data
        if number in valid_clause_numbers:
            clause = await db.clauses.find_one({"number": number}, {"_id": 0})
            if clause:
                clause["ai_explanation"] = explanations.get(number, "Relevant to your query")
                clauses.append(clause)
        else:
            logger.warning(f"AI suggested non-existent clause: {number}")

    return {
        "clauses": clauses,
        "ai_analysis": f"Found {len(clauses)} relevant clauses from acquisition.gov indexed data.",
        "total": len(clauses),
        "source": "acquisition.gov",
        "query_understood": query
    }

@clauses_router.get("/{clause_id}")
async def get_clause(clause_id: str):
    """Get a specific clause by ID"""
    clause = await db.clauses.find_one({"clause_id": clause_id}, {"_id": 0})
    if not clause:
        raise HTTPException(status_code=404, detail="Clause not found")
    return clause

@clauses_router.get("/by-number/{clause_number:path}")
async def get_clause_by_number(clause_number: str):
    """Get a specific clause by number"""
    clause = await db.clauses.find_one({"number": clause_number}, {"_id": 0})
    if not clause:
        raise HTTPException(status_code=404, detail="Clause not found")
    return clause

@clauses_router.get("/fetch-live/{clause_number:path}")
async def fetch_live_clause(clause_number: str, request: Request, force: bool = False, format: str = "text"):
    """Fetch a clause directly from acquisition.gov and store it.
    
    Query params:
    - force: If True, re-fetch even if cached
    - format: "text" (plain), "dita" (formatted DITA XML), or "html" (formatted HTML)
    """
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required to fetch live data")

    # Check if we already have this clause with valid text (not placeholder)
    if not force:
        existing = await db.clauses.find_one({"number": clause_number}, {"_id": 0})
        if existing:
            text = existing.get("text", "")
            # Only use cached data if it has real text (not placeholder)
            if text and len(text) > 500 and "Full text available" not in text and "See acquisition.gov" not in text:
                # If requesting formatted output, get DITA
                if format in ["dita", "html"]:
                    dita_content = await fetch_clause_dita_from_acquisition_gov(clause_number)
                    if dita_content:
                        existing["formatted_text"] = dita_content
                return existing

    # Fetch fresh from acquisition.gov
    logger.info(f"Fetching {clause_number} fresh from acquisition.gov...")
    clause_data = await fetch_clause_from_acquisition_gov(clause_number)

    if clause_data:
        # Also fetch DITA if requested
        if format in ["dita", "html"]:
            dita_content = await fetch_clause_dita_from_acquisition_gov(clause_number)
            if dita_content:
                clause_data["formatted_text"] = dita_content
        
        # Store in database
        await db.clauses.update_one(
            {"number": clause_number},
            {"$set": clause_data},
            upsert=True
        )
        return clause_data
    else:
        raise HTTPException(status_code=404, detail=f"Could not fetch clause {clause_number} from acquisition.gov")


@clauses_router.get("/formatted/{clause_number:path}")
async def get_formatted_clause(clause_number: str):
    """Get clause with formatted HTML content for proper display.
    Returns the clause data with a formatted_text field containing processed HTML
    that renders with proper indentation.
    """
    # First check if we have the clause in DB
    clause = await db.clauses.find_one({"number": clause_number}, {"_id": 0})
    
    if not clause:
        # Try to fetch from acquisition.gov
        clause = await fetch_clause_from_acquisition_gov(clause_number)
        if clause:
            await db.clauses.update_one(
                {"number": clause_number},
                {"$set": clause},
                upsert=True
            )
    
    if not clause:
        raise HTTPException(status_code=404, detail="Clause not found")
    
    # Fetch HTML from acquisition.gov and format it for display
    # This uses format_dita_html_for_agiloft which preserves indentation properly
    html_content = await fetch_clause_html_from_acquisition_gov(clause_number)
    if html_content:
        clause["formatted_text"] = html_content
    else:
        # Fallback: try DITA and convert to displayable format
        dita_content = await fetch_clause_dita_from_acquisition_gov(clause_number)
        if dita_content:
            # The DITA is already processed by _suppress_dita_list_tags with margin-left styles
            # Apply the paragraph normalization for proper text display
            clause["formatted_text"] = _normalize_clause_indent_html(dita_content)
    
    return clause


async def fetch_raw_dita_from_acquisition_gov(clause_number: str) -> Optional[str]:
    """
    Fetch RAW DITA XML for a clause from acquisition.gov (without modifications).
    """
    import zipfile
    import io
    
    try:
        part_num = clause_number.split('.')[0]
        
        if clause_number.startswith("252"):
            zip_url = "https://www.acquisition.gov/sites/default/files/current/dfars/compiled_dita/part_252.zip"
            folder_name = "part_252"
        else:
            zip_url = f"https://www.acquisition.gov/sites/default/files/current/far/compiled_dita/part_{part_num}.zip"
            folder_name = f"part_{part_num}"
        
        async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
            response = await client.get(zip_url)
            
            if response.status_code == 200:
                zip_data = io.BytesIO(response.content)
                
                with zipfile.ZipFile(zip_data, 'r') as zip_ref:
                    possible_names = [
                        f"{folder_name}/{clause_number}.dita",
                        f"{folder_name}/{clause_number.lower()}.dita",
                        f"{folder_name}/{clause_number.upper()}.dita",
                    ]
                    
                    for name in possible_names:
                        try:
                            return zip_ref.read(name).decode('utf-8')
                        except KeyError:
                            continue
        return None
    except Exception as e:
        logger.error(f"Error fetching raw DITA: {e}")
        return None


def convert_dita_to_display_html(dita_content: str) -> str:
    """
    Convert DITA XML to HTML that renders properly with indentation like acquisition.gov.
    This is for display in the app and PDF export.
    """
    from bs4 import BeautifulSoup
    
    if not dita_content:
        return ""
    
    soup = BeautifulSoup(dita_content, 'html.parser')
    
    # Build output HTML with proper indentation
    output_lines = []
    
    def process_element(element, level=0):
        """Process an element and return HTML with proper indentation."""
        if element.name is None:  # Text node
            text = str(element).strip()
            if text:
                return text
            return None
        
        # Calculate indentation based on nesting
        margin = level * 2  # 2em per level
        
        if element.name == 'p':
            # Get the text content
            text_parts = []
            for child in element.children:
                if child.name == 'ph' and 'autonumber' in str(child.get('props', '')):
                    # This is the autonumber (a), (b), (1), (2)
                    text_parts.append(child.get_text())
                elif child.name is None:
                    text_parts.append(str(child))
                else:
                    text_parts.append(child.get_text())
            
            text = ''.join(text_parts).strip()
            if text:
                # Check if it's an end marker
                if text.lower() in ['(end of clause)', '(end of provision)']:
                    return f'<p style="text-align:center; margin:15px 0; font-style:italic;">{text}</p>'
                else:
                    return f'<p style="margin:0 0 8px {margin}em; text-indent:-1.5em; padding-left:1.5em;">{text}</p>'
            return None
        
        elif element.name in ['ol', 'ul']:
            # Process list - increase nesting level
            items = []
            for child in element.children:
                if child.name == 'li':
                    li_content = process_li(child, level + 1)
                    if li_content:
                        items.append(li_content)
            return '\n'.join(items) if items else None
        
        elif element.name == 'li':
            return process_li(element, level)
        
        elif element.name in ['concept', 'conbody', 'body', 'dita', 'title']:
            # Container elements - process children
            items = []
            for child in element.children:
                result = process_element(child, level)
                if result:
                    items.append(result)
            return '\n'.join(items) if items else None
        
        else:
            # Other elements - just get text
            text = element.get_text().strip()
            if text:
                return f'<p style="margin:0 0 8px {margin}em;">{text}</p>'
            return None
    
    def process_li(li_element, level):
        """Process a list item with proper indentation."""
        margin = level * 2
        items = []
        
        for child in li_element.children:
            result = process_element(child, level)
            if result:
                items.append(result)
        
        return '\n'.join(items) if items else None
    
    # Process the entire document
    result = process_element(soup)
    
    # Wrap in a container
    return f'<div class="dita-content">{result or ""}</div>'

@clauses_router.post("/sync-from-acquisition-gov")
async def sync_clauses_from_acquisition_gov(
    request: Request,
    clause_type: Optional[str] = None,
    force_refresh: bool = False
):
    """Sync clause index from acquisition.gov to local database.
    
    Query params:
    - clause_type: "FAR", "DFARS", or None for both
    - force_refresh: If True, re-scrape even if we have cached data
    
    This uses the new scraper module for robust extraction.
    """
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Check if new scraper modules are available
    if not AGILOFT_CLIENT_AVAILABLE:
        # Fall back to old method
        logger.info("Using legacy fetch_far_index for sync")
        far_clauses = await fetch_far_index()
        clauses_to_sync = far_clauses
    else:
        # Use new scraper module
        logger.info(f"Using new scraper module for sync. Type: {clause_type}, Force refresh: {force_refresh}")
        clauses_to_sync = []
        
        if clause_type is None or clause_type.upper() == "FAR":
            far_clauses = await scrape_far_clauses()
            logger.info(f"Scraped {len(far_clauses)} FAR clauses from acquisition.gov")
            clauses_to_sync.extend(far_clauses)
        
        if clause_type is None or clause_type.upper() == "DFARS":
            dfars_clauses = await scrape_dfars_clauses()
            logger.info(f"Scraped {len(dfars_clauses)} DFARS clauses from acquisition.gov")
            clauses_to_sync.extend(dfars_clauses)

    synced_count = 0
    updated_count = 0
    
    for clause_info in clauses_to_sync:
        # Normalize the clause number field
        clause_number = clause_info.get("clause_number") or clause_info.get("number", "")
        if not clause_number:
            continue
        
        # Check if we already have this clause
        existing = await db.clauses.find_one({"number": clause_number})
        
        if not existing:
            # Create new entry
            clause_doc = {
                "clause_id": str(uuid.uuid4()),
                "number": clause_number,
                "title": clause_info.get("title", ""),
                "type": clause_info.get("type", "FAR"),
                "text": clause_info.get("text") or f"Full text available at acquisition.gov. Search for {clause_number}",
                "summary": None,
                "flowdown_required": False,
                "contract_types": [],
                "threshold_amount": None,
                "keywords": [],
                "last_updated": datetime.now(timezone.utc).isoformat(),
                "source": "acquisition.gov",
                "url": clause_info.get("url", "")
            }
            await db.clauses.insert_one(clause_doc)
            synced_count += 1
        elif force_refresh:
            # Update existing entry
            await db.clauses.update_one(
                {"number": clause_number},
                {"$set": {
                    "title": clause_info.get("title", existing.get("title", "")),
                    "type": clause_info.get("type", existing.get("type", "FAR")),
                    "last_updated": datetime.now(timezone.utc).isoformat(),
                    "source": "acquisition.gov",
                    "url": clause_info.get("url", "")
                }}
            )
            updated_count += 1

    return {
        "success": True,
        "message": f"Synced {synced_count} new clauses, updated {updated_count} existing clauses from acquisition.gov",
        "total_new": synced_count,
        "total_updated": updated_count,
        "total_processed": len(clauses_to_sync),
        "clause_type": clause_type or "all"
    }

@clauses_router.post("/sync-full-text")
async def sync_clauses_full_text(request: Request, limit: int = 50):
    """Sync full text for clauses from acquisition.gov.
    
    This fetches the complete clause text for clauses that are missing it.
    Call this to ensure PDF exports have full text content.
    
    Args:
        limit: Maximum number of clauses to sync in one call (default 50)
    """
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    # Find clauses missing full text
    clauses_without_text = await db.clauses.find({
        "$or": [
            {"text": {"$exists": False}},
            {"text": None},
            {"text": ""},
            {"text": {"$regex": "^Full text available"}},
            {"text": {"$regex": "^See acquisition.gov"}}
        ]
    }, {"_id": 0, "number": 1, "title": 1, "type": 1}).to_list(limit)
    
    if not clauses_without_text:
        return {
            "success": True,
            "message": "All clauses already have full text",
            "synced": 0,
            "failed": 0,
            "total_checked": 0
        }
    
    synced_count = 0
    failed_count = 0
    failed_clauses = []
    
    for clause in clauses_without_text:
        clause_num = clause.get("number")
        if not clause_num:
            continue
            
        try:
            logger.info(f"Fetching full text for {clause_num}...")
            live_clause = await fetch_clause_from_acquisition_gov(clause_num)
            
            if live_clause and live_clause.get("text"):
                await db.clauses.update_one(
                    {"number": clause_num},
                    {"$set": {
                        "text": live_clause.get("text", ""),
                        "title": live_clause.get("title", clause.get("title", "")),
                        "last_updated": datetime.now(timezone.utc).isoformat()
                    }}
                )
                synced_count += 1
                logger.info(f"Successfully synced full text for {clause_num}")
            else:
                failed_count += 1
                failed_clauses.append(clause_num)
                logger.warning(f"No text found for {clause_num}")
        except Exception as e:
            failed_count += 1
            failed_clauses.append(clause_num)
            logger.error(f"Failed to sync {clause_num}: {e}")
    
    return {
        "success": True,
        "message": f"Synced full text for {synced_count} clauses, {failed_count} failed",
        "synced": synced_count,
        "failed": failed_count,
        "total_checked": len(clauses_without_text),
        "failed_clauses": failed_clauses[:10]  # Only return first 10 failed
    }

# ==================== Contracts Routes ====================

@contracts_router.post("/upload")
async def upload_contract(request: Request, file: UploadFile = File(...)):
    """Upload and analyze a contract"""
    user = await require_auth(request)

    content = await file.read()
    text_content = ""

    # Try to extract text from PDF or treat as text
    if file.filename.endswith('.pdf'):
        try:
            import pdfplumber
            
            # CID to character mapping for common fonts
            # CID codes are font-specific, but for number/period, common patterns exist
            def decode_cid_text(text: str) -> str:
                """Decode CID-encoded text commonly found in OCR'd PDFs."""
                import re
                
                # Common CID mappings for digits and punctuation
                cid_map = {
                    # Numbers (many fonts use these codes)
                    '(cid:15)': '5', '(cid:12)': '2', '(cid:8)': '.', 
                    '(cid:11)': '1', '(cid:7)': '-', '(cid:14)': '4',
                    '(cid:13)': '3', '(cid:16)': '6', '(cid:17)': '7',
                    '(cid:18)': '8', '(cid:19)': '9', '(cid:10)': '0',
                    # Try alternative number mappings
                    '(cid:20)': '0', '(cid:21)': '1', '(cid:22)': '2',
                    '(cid:23)': '3', '(cid:24)': '4', '(cid:25)': '5',
                    '(cid:26)': '6', '(cid:27)': '7', '(cid:28)': '8',
                    '(cid:29)': '9',
                }
                
                # Replace known CID codes
                for cid, char in cid_map.items():
                    text = text.replace(cid, char)
                
                # Remove remaining (cid:XX) patterns that we couldn't decode
                text = re.sub(r'\(cid:\d+\)', '', text)
                
                return text
            
            with pdfplumber.open(io.BytesIO(content)) as pdf:
                all_text = []
                for page in pdf.pages:
                    # Extract regular text
                    page_text = page.extract_text() or ""
                    
                    # Decode CID-encoded text
                    page_text = decode_cid_text(page_text)
                    all_text.append(page_text)
                    
                    # Also extract tables (important for clause lists)
                    tables = page.extract_tables()
                    for table in tables:
                        if table:
                            for row in table:
                                if row:
                                    # Join cells with space, filter out None values
                                    row_text = " ".join([str(cell) if cell else "" for cell in row])
                                    row_text = decode_cid_text(row_text)
                                    if row_text.strip():
                                        all_text.append(row_text)
                
                text_content = "\n".join(all_text)
                logger.info(f"PDF extraction: {len(text_content)} chars from {len(pdf.pages)} pages")
        except Exception as e:
            logger.error(f"PDF extraction error: {e}")
            text_content = content.decode('utf-8', errors='ignore')
    else:
        text_content = content.decode('utf-8', errors='ignore')

    # Find clause HEADERS in the contract (not just any mention)
    # A clause header typically appears at the start of a line or section, often followed by a title
    clauses_found = _detect_clause_headers(text_content)
    
    logger.info(f"Detected {len(clauses_found)} clause headers in uploaded contract")

    # Create contract record - store more content for potential rescanning
    contract = Contract(
        user_id=user.user_id,
        name=file.filename,
        filename=file.filename,
        content=text_content[:200000],  # Store more content for rescanning
        clauses_found=clauses_found
    )

    contract_dict = contract.model_dump()
    contract_dict["created_at"] = contract_dict["created_at"].isoformat()
    await db.contracts.insert_one(contract_dict)

    return ContractUploadResponse(
        contract_id=contract.contract_id,
        name=contract.name,
        clauses_found=clauses_found
    )


def _detect_clause_headers(text_content: str) -> List[str]:
    """
    Detect actual clauses in a contract document.
    
    Clauses can appear in two ways:
    1. In "incorporated by reference" sections - listed clause numbers
    2. In "incorporated by full text" sections - clause headers followed by full text
    
    This function EXCLUDES:
    - Clause numbers mentioned as references INSIDE another clause's body text
      (e.g., 52.212-5 listing 52.203-19, 52.204-23 in checkbox format)
    """
    import re
    
    # Regex pattern for clause numbers (FAR: 52.xxx-xx, DFARS: 252.xxx-xxxx)
    CLAUSE_NUM_PATTERN = r'((?:52|252)\.\d{3}(?:-\d{1,4})?)'
    
    detected_clauses = set()
    
    # Split text into lines for analysis
    lines = text_content.split('\n')
    
    # Track if we're inside a "problematic" clause that has checkbox lists
    # (like 52.212-5 which lists many clauses as references)
    inside_checkbox_section = False
    checkbox_depth = 0
    
    # Track sections - "incorporated by reference" sections are safe to extract from
    in_incorporated_section = False
    
    for i, line in enumerate(lines):
        line_stripped = line.strip()
        line_lower = line_stripped.lower()
        
        # Check for section markers - but DON'T skip this line if it also has a clause
        is_section_marker = any(phrase in line_lower for phrase in [
            'incorporated by reference',
            'incorporated by full text',
            'clauses incorporated',
            'contract clauses',
        ])
        
        # Only skip for pure section headers (like "SECTION I - CONTRACT CLAUSES")
        # NOT for clauses that contain these phrases in their title
        if is_section_marker:
            in_incorporated_section = True
            inside_checkbox_section = False
            # Don't continue - check if this line also has a clause to detect
        
        # Detect when we enter a checkbox section (like in 52.212-5)
        # These sections have patterns like "[_]" or "[X]" or "( )" checkboxes
        if re.search(r'\[\s*[_xX✓]?\s*\]|\(\s*[_xX]?\s*\)', line_stripped):
            inside_checkbox_section = True
            checkbox_depth = 3  # Stay in checkbox mode for a few more lines
        elif inside_checkbox_section:
            checkbox_depth -= 1
            if checkbox_depth <= 0:
                inside_checkbox_section = False
        
        # Detect if line contains a clause number
        clause_matches = re.findall(CLAUSE_NUM_PATTERN, line_stripped)
        
        for clause_num in clause_matches:
            # Normalize the clause number
            clause_num = clause_num.replace('–', '-').replace('—', '-')
            
            # SKIP if we're inside a checkbox section (these are references within a clause)
            if inside_checkbox_section:
                continue
            
            # SKIP if the clause appears after common reference phrases on the same line
            reference_patterns = [
                rf'see\s+(?:FAR\s+)?{re.escape(clause_num)}',
                rf'per\s+(?:FAR\s+)?{re.escape(clause_num)}',
                rf'pursuant\s+to\s+(?:FAR\s+)?{re.escape(clause_num)}',
                rf'in\s+accordance\s+with\s+(?:FAR\s+)?{re.escape(clause_num)}',
                rf'as\s+required\s+by\s+{re.escape(clause_num)}',
                rf'reference\s+(?:to\s+)?{re.escape(clause_num)}',
                rf'regulation\s+{re.escape(clause_num)}',  # "Regulation 52.216-7"
                rf'clause\s+{re.escape(clause_num)}',  # "clause 52.216-7"
                rf'far\s+{re.escape(clause_num)}',  # "FAR 52.216-7" in middle of text
                rf'dfars\s+{re.escape(clause_num)}',  # "DFARS 252.xxx" in middle of text
            ]
            
            is_reference = False
            for ref_pattern in reference_patterns:
                if re.search(ref_pattern, line_stripped, re.IGNORECASE):
                    is_reference = True
                    break
            
            if is_reference:
                continue
            
            # Check if clause number is in a list format like "(1) 52.203-19" or "XX (1) 52.203-19"
            # These could be either:
            # A) Actual clause headers in a contract document (ACCEPT these)
            # B) References within 52.212-5 checkbox sections (REJECT these)
            list_format_match = re.search(rf'(?:XX|___?|____)?\s*\(\s*\d+\s*\)\s*{re.escape(clause_num)}', line_stripped)
            if list_format_match:
                # If in a checkbox section, skip (these are references)
                if inside_checkbox_section:
                    continue
                # Otherwise, this is likely an actual clause header - ACCEPT it
                # This handles formats like "XX (1) 52.203-6, Restrictions on..." 
                # or "___ (2) 52.204-23, Prohibition on..."
                detected_clauses.add(clause_num)
                continue
            
            # SKIP if the clause number is in a lettered list format like "(a) 52.203-19"
            # BUT only if we're in a checkbox section
            if inside_checkbox_section and re.search(rf'\(\s*[a-z]\s*\)\s*{re.escape(clause_num)}', line_stripped, re.IGNORECASE):
                continue
            
            # SKIP if the clause number is in a Roman numeral list format like "(ii) 52.203-19"
            # BUT only if we're in a checkbox section
            if inside_checkbox_section and re.search(rf'\(\s*[ivxlcdm]+\s*\)\s*{re.escape(clause_num)}', line_stripped, re.IGNORECASE):
                continue
            
            # ACCEPT: Clause number appears at the start of a line (with optional whitespace)
            # This catches both "52.203-3 Gratuities" and "    52.203-3 Gratuities"
            if re.match(rf'^\s*{re.escape(clause_num)}\s', line_stripped):
                detected_clauses.add(clause_num)
                continue
            
            # ACCEPT: Clause number appears after a bullet point or dash
            # This catches "• 52.203-3" or "- 52.203-3"
            if re.match(rf'^[\s•\-\*]+{re.escape(clause_num)}\s', line_stripped):
                detected_clauses.add(clause_num)
                continue
            
            # ACCEPT: In an "incorporated by reference" section, any clause number is valid
            if in_incorporated_section:
                # But still skip if it looks like it's part of prose
                words_before = len(line_stripped.split(clause_num)[0].split())
                if words_before <= 2:  # Clause number appears near start of line
                    detected_clauses.add(clause_num)
                continue
            
            # ACCEPT: Clause number followed by a title pattern (uppercase words or quoted text)
            if re.search(rf'{re.escape(clause_num)}\s+[A-Z][A-Za-z\s\-]+(?:\(|$)', line_stripped):
                detected_clauses.add(clause_num)
                continue
            
            # ACCEPT: Clause number followed by a comma and title (common format in contracts)
            # e.g., "52.203-6, Restrictions on Subcontractor Sales to the Government"
            if re.search(rf'{re.escape(clause_num)},\s+[A-Z]', line_stripped):
                detected_clauses.add(clause_num)
                continue
    
    return sorted(list(detected_clauses))

@contracts_router.get("/")
async def get_contracts(request: Request):
    """Get all contracts for current user"""
    user = await require_auth(request)
    contracts = await db.contracts.find(
        {"user_id": user.user_id},
        {"_id": 0, "content": 0}
    ).to_list(100)
    return {"contracts": contracts}

@contracts_router.get("/{contract_id}")
async def get_contract(contract_id: str, request: Request):
    """Get a specific contract"""
    user = await require_auth(request)
    contract = await db.contracts.find_one(
        {"contract_id": contract_id, "user_id": user.user_id},
        {"_id": 0}
    )
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")
    return contract

@contracts_router.delete("/{contract_id}")
async def delete_contract(contract_id: str, request: Request):
    """Delete a contract"""
    user = await require_auth(request)
    
    result = await db.contracts.delete_one(
        {"contract_id": contract_id, "user_id": user.user_id}
    )
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Contract not found")
    
    logger.info(f"Contract {contract_id} deleted by user {user.user_id}")
    return {"message": "Contract deleted successfully", "contract_id": contract_id}

@contracts_router.post("/{contract_id}/rescan")
async def rescan_contract_clauses(contract_id: str, request: Request):
    """Re-scan a contract to detect clause headers with improved algorithm.
    Note: If the contract was uploaded before the content storage limit was increased,
    the stored content may be truncated and re-upload is required.
    """
    user = await require_auth(request)
    
    contract = await db.contracts.find_one(
        {"contract_id": contract_id, "user_id": user.user_id}
    )
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")
    
    # Get the contract content
    text_content = contract.get("content", "")
    if not text_content:
        raise HTTPException(status_code=400, detail="Contract has no content to scan")
    
    # Check if content is truncated (old contracts had 50KB limit)
    content_length = len(text_content)
    content_warning = None
    needs_reupload = False
    
    if content_length <= 51000:  # Old 50KB limit
        needs_reupload = True
        content_warning = "This contract was uploaded with an older version that stored limited content. Please DELETE this contract and RE-UPLOAD it to get accurate clause detection."
    elif content_length >= 199000:  # Near current 200KB limit
        content_warning = "Contract content may be partially truncated. Results should be mostly accurate."
    
    # Re-detect clauses with improved algorithm
    old_clauses = contract.get("clauses_found", [])
    new_clauses = _detect_clause_headers(text_content)
    
    # Update the contract record
    await db.contracts.update_one(
        {"contract_id": contract_id},
        {"$set": {"clauses_found": new_clauses}}
    )
    
    logger.info(f"Contract {contract_id} rescanned: {len(old_clauses)} -> {len(new_clauses)} clauses (content: {content_length} chars)")
    
    result = {
        "contract_id": contract_id,
        "previous_count": len(old_clauses),
        "new_count": len(new_clauses),
        "clauses_found": new_clauses,
        "removed_clauses": [c for c in old_clauses if c not in new_clauses],
        "message": f"Contract rescanned. Found {len(new_clauses)} actual clause headers (was {len(old_clauses)})",
        "needs_reupload": needs_reupload
    }
    
    if content_warning:
        result["warning"] = content_warning
    
    return result


def _extract_clauses_with_checkboxes(text_content: str) -> Dict[str, Any]:
    """
    Extract ALL clauses from contract document with checkbox detection.
    
    Identifies:
    1. ALL clauses in checkbox format (XX or ___ prefix)
    2. Clauses marked as SELECTED (X or XX)
    3. Clauses marked as UNSELECTED (___)
    4. Reference-only mentions (in prose text)
    
    Returns structured data for Agiloft KB upload.
    """
    import re
    
    CLAUSE_NUM_PATTERN = r'((?:52|252)\.\d{3}(?:-\d{1,4})?)'
    
    result = {
        "all_clauses": [],  # ALL unique clauses found
        "top_level_clauses": [],  # Clauses that are explicitly selected/incorporated
        "selected_sub_clauses": [],  # Clauses marked with X or XX
        "unselected_sub_clauses": [],  # Clauses marked with ___
        "reference_mentions": [],  # Clauses mentioned in prose (not checkbox)
        "parent_clauses_with_selections": {},
        "summary": {}
    }
    
    lines = text_content.split('\n')
    seen_clauses = set()  # Track unique clauses
    seen_selected = set()  # Track what we've already added to selected
    current_parent_clause = None
    
    for i, line in enumerate(lines):
        line_stripped = line.strip()
        
        # Find clause numbers on this line
        clause_matches = re.findall(CLAUSE_NUM_PATTERN, line_stripped)
        
        if not clause_matches:
            continue
        
        for clause_num in clause_matches:
            clause_num = clause_num.replace('–', '-').replace('—', '-')
            
            # Extract title if present (text after clause number, comma, then title)
            title_match = re.search(
                rf'{re.escape(clause_num)}[,\s]+([A-Z][^(\n]+?)(?:\s*\(|\s*$)',
                line_stripped
            )
            title = title_match.group(1).strip() if title_match else ""
            
            # Clean up title - remove trailing dates like "(Jun 2020)"
            title = re.sub(r'\s*\([A-Z][a-z]{2}\s+\d{4}\)\s*$', '', title).strip()
            
            # Check if this is a SELECTED clause (marked with X or XX at the start)
            # Pattern: "XX (1) 52.xxx-xx" or "X (1) 52.xxx-xx"
            is_selected = bool(re.search(
                rf'^XX?\s+(?:\(\d+\)\s*(?:\([ivx]+\)\s*)?)?{re.escape(clause_num)}',
                line_stripped
            ))
            
            # Also check for checkmark patterns
            if not is_selected:
                is_selected = bool(re.search(
                    rf'^(?:✓|✔)\s*(?:\(\d+\)\s*)?{re.escape(clause_num)}',
                    line_stripped
                ))
            
            # Check if this is an UNSELECTED checkbox clause (marked with ___ or [ ])
            is_checkbox_unselected = bool(re.search(
                rf'^(?:_{{2,4}})\s*(?:\(\d+\)\s*(?:\([ivx]+\)\s*)?)?{re.escape(clause_num)}',
                line_stripped
            ))
            
            # Check if this is a checkbox clause at all (either selected or unselected)
            is_checkbox_clause = is_selected or is_checkbox_unselected
            
            # Check if this is just a reference in prose (no checkbox marker)
            is_prose_reference = not is_checkbox_clause and bool(re.search(
                rf'(?:at|in|see|per|clause|far|dfars)\s+{re.escape(clause_num)}',
                line_stripped,
                re.IGNORECASE
            ))
            
            # Check if this looks like a standalone parent clause header
            # Format: "52.212-5 Contract Terms and Conditions..." at start of line
            is_standalone_header = bool(re.match(
                rf'^\s*{re.escape(clause_num)}\s+[A-Z]',
                line_stripped
            )) and not is_checkbox_clause
            
            clause_data = {
                "number": clause_num,
                "title": title,
                "is_selected": is_selected,
                "is_checkbox_clause": is_checkbox_clause,
                "source_line": line_stripped[:250]
            }
            
            # Track all unique clauses (not references)
            if clause_num not in seen_clauses and not is_prose_reference:
                seen_clauses.add(clause_num)
                result["all_clauses"].append(clause_data.copy())
            
            # If this is a standalone header, track it as parent
            if is_standalone_header:
                current_parent_clause = clause_num
                result["top_level_clauses"].append(clause_data.copy())
                
                if clause_num not in result["parent_clauses_with_selections"]:
                    result["parent_clauses_with_selections"][clause_num] = {
                        "title": title,
                        "selected_sub_clauses": [],
                        "unselected_sub_clauses": []
                    }
            
            # Process checkbox clauses
            if is_checkbox_clause:
                parent = current_parent_clause or "checkbox_list"
                
                if parent not in result["parent_clauses_with_selections"]:
                    result["parent_clauses_with_selections"][parent] = {
                        "title": "",
                        "selected_sub_clauses": [],
                        "unselected_sub_clauses": []
                    }
                
                if is_selected:
                    # Only add if not already added (avoid duplicates)
                    if clause_num not in seen_selected:
                        seen_selected.add(clause_num)
                        result["selected_sub_clauses"].append(clause_data.copy())
                        result["parent_clauses_with_selections"][parent]["selected_sub_clauses"].append(clause_data.copy())
                        # Selected checkbox clauses are also top-level (they're in the contract)
                        result["top_level_clauses"].append(clause_data.copy())
                elif is_checkbox_unselected:
                    result["unselected_sub_clauses"].append(clause_data.copy())
                    result["parent_clauses_with_selections"][parent]["unselected_sub_clauses"].append(clause_data.copy())
            
            # Track prose references separately
            elif is_prose_reference:
                result["reference_mentions"].append(clause_data.copy())
    
    # Generate summary
    result["summary"] = {
        "total_all_clauses": len(result["all_clauses"]),
        "total_top_level_clauses": len(result["top_level_clauses"]),
        "total_selected_sub_clauses": len(result["selected_sub_clauses"]),
        "total_unselected_sub_clauses": len(result["unselected_sub_clauses"]),
        "total_reference_mentions": len(result["reference_mentions"]),
        "parent_clauses_count": len(result["parent_clauses_with_selections"])
    }
    
    return result


@contracts_router.post("/{contract_id}/extract-for-agiloft")
async def extract_clauses_for_agiloft(contract_id: str, request: Request):
    """
    Extract clauses from contract with checkbox detection for Agiloft KB upload.
    
    Returns JSON with:
    - ALL clauses found in the document
    - Top-level/standalone clauses (like 52.212-5)
    - Selected sub-clauses (marked with X or XX)
    - Unselected sub-clauses (marked with ___)
    """
    user = await require_auth(request)
    
    contract = await db.contracts.find_one(
        {"contract_id": contract_id, "user_id": user.user_id}
    )
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")
    
    text_content = contract.get("content", "")
    if not text_content:
        raise HTTPException(status_code=400, detail="Contract has no content to analyze")
    
    # Extract clauses with checkbox detection
    extraction_result = _extract_clauses_with_checkboxes(text_content)
    
    # Also add clauses from the contract's detected list that might not be in checkbox format
    # These are standalone clause headers like "52.212-5 Contract Terms..."
    detected_clauses = set(contract.get("clauses_found", []))
    extracted_numbers = {c["number"] for c in extraction_result["all_clauses"]}
    
    # Add standalone detected clauses to the results
    for clause_num in detected_clauses:
        if clause_num not in extracted_numbers:
            # This clause was detected by _detect_clause_headers but not the checkbox extraction
            # It's likely a standalone clause header (like 52.212-5 in a table)
            clause_data = {
                "number": clause_num,
                "title": "",
                "is_selected": True,  # It's in the contract
                "is_checkbox_clause": False,
                "source_line": f"Detected as standalone clause: {clause_num}"
            }
            extraction_result["all_clauses"].append(clause_data)
            extraction_result["top_level_clauses"].append(clause_data)
    
    # Enrich with clause details from our database
    for clause_list in [extraction_result["all_clauses"], 
                        extraction_result["top_level_clauses"],
                        extraction_result["selected_sub_clauses"]]:
        for clause_data in clause_list:
            db_clause = await db.clauses.find_one({"number": clause_data["number"]}, {"_id": 0})
            if db_clause:
                clause_data["db_title"] = db_clause.get("title", "")
                clause_data["type"] = db_clause.get("type", "")
                clause_data["url"] = db_clause.get("url", "")
    
    # Build Agiloft-ready data: Combine top-level and selected sub-clauses (deduplicated)
    seen_numbers = set()
    agiloft_clauses = []
    
    # Add all top-level clauses
    for c in extraction_result["top_level_clauses"]:
        if c["number"] not in seen_numbers:
            seen_numbers.add(c["number"])
            agiloft_clauses.append({
                "clause_number": c["number"],
                "clause_title": c.get("db_title") or c.get("title", ""),
                "clause_type": c.get("type", "FAR" if c["number"].startswith("52.") else "DFARS"),
                "category": "top_level",
                "is_selected": True
            })
    
    # Add selected sub-clauses that aren't already in top-level
    for c in extraction_result["selected_sub_clauses"]:
        if c["number"] not in seen_numbers:
            seen_numbers.add(c["number"])
            agiloft_clauses.append({
                "clause_number": c["number"],
                "clause_title": c.get("db_title") or c.get("title", ""),
                "clause_type": c.get("type", "FAR" if c["number"].startswith("52.") else "DFARS"),
                "category": "selected_sub_clause",
                "is_selected": True
            })
    
    # Add any remaining detected clauses from clauses_found
    detected_clauses = contract.get("clauses_found", [])
    for clause_num in detected_clauses:
        if clause_num not in seen_numbers:
            seen_numbers.add(clause_num)
            db_clause = await db.clauses.find_one({"number": clause_num}, {"_id": 0})
            agiloft_clauses.append({
                "clause_number": clause_num,
                "clause_title": db_clause.get("title", "") if db_clause else "",
                "clause_type": "FAR" if clause_num.startswith("52.") else "DFARS",
                "category": "detected",
                "is_selected": True
            })
    
    return {
        "contract_id": contract_id,
        "filename": contract.get("filename", ""),
        "extraction": extraction_result,
        "agiloft_upload_ready": {
            "clauses": agiloft_clauses
        }
    }


@contracts_router.get("/{contract_id}/export-clauses-json")
async def export_clauses_json(contract_id: str, request: Request):
    """
    Export extracted clauses as downloadable JSON file for Agiloft KB upload.
    
    Format matches Agiloft KB structure:
    - Type (FAR/DFARS)
    - Number (clause number)
    - Date (effective date)
    - Clause Title
    - Clause Text
    """
    from fastapi.responses import JSONResponse
    
    user = await require_auth(request)
    
    contract = await db.contracts.find_one(
        {"contract_id": contract_id, "user_id": user.user_id}
    )
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")
    
    text_content = contract.get("content", "")
    if not text_content:
        raise HTTPException(status_code=400, detail="Contract has no content to analyze")
    
    # Extract clauses
    extraction_result = _extract_clauses_with_checkboxes(text_content)
    
    # Also add clauses from the contract's detected list (standalone headers like 52.212-5)
    detected_clauses = set(contract.get("clauses_found", []))
    extracted_numbers = {c["number"] for c in extraction_result["top_level_clauses"]}
    
    for clause_num in detected_clauses:
        if clause_num not in extracted_numbers:
            clause_data = {
                "number": clause_num,
                "title": "",
                "is_selected": True,
                "source_line": ""
            }
            extraction_result["top_level_clauses"].append(clause_data)
    
    def _extract_date_from_clause_text(text: str) -> str:
        """Extract the effective date from clause text (e.g., 'JAN 2025' from the centered title line)."""
        if not text:
            return ""
        # Search within the first 600 chars where the title line with date typically appears
        search_text = text[:600]
        # Match patterns like (JAN 2025), (Jan 2025), ( MAY 2024), (  NOV 2023  )
        # Allow flexible whitespace inside parentheses and between month and year
        month_pattern = r'(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|JANUARY|FEBRUARY|MARCH|APRIL|JUNE|JULY|AUGUST|SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER)'
        date_match = re.search(rf'\(\s*({month_pattern})\s+(\d{{4}})\s*\)', search_text)
        if date_match:
            return f"{date_match.group(1)} {date_match.group(2)}"
        return ""

    # Build Agiloft KB-compatible JSON
    agiloft_data = {
        "contract_reference": contract.get("filename", ""),
        "extraction_date": datetime.now(timezone.utc).isoformat(),
        "clauses": []
    }
    
    # Get the selected and unselected sub-clauses
    selected_sub_nums = {c["number"] for c in extraction_result["selected_sub_clauses"]}
    unselected_sub_nums = {c["number"] for c in extraction_result.get("unselected_sub_clauses", [])}
    
    # Build a map of parent clauses to their selected sub-clauses
    parent_selected_map = {}
    for parent_num, data in extraction_result.get("parent_clauses_with_selections", {}).items():
        if data.get("selected_sub_clauses"):
            parent_selected_map[parent_num] = data["selected_sub_clauses"]
    
    seen_numbers = set()
    detected_clauses = contract.get("clauses_found", [])
    
    # First, add parent clauses (like 52.212-5) with their selected sub-clauses in Clause_Text
    # If we have a "checkbox_list" parent, find the real parent from detected_clauses
    if "checkbox_list" in parent_selected_map:
        selected_subs = parent_selected_map["checkbox_list"]
        
        # Look for parent clauses like 52.212-5 in detected_clauses
        parent_clause_patterns = ['52.212-5', '52.212-4', '52.244-6', '252.212-7001', '252.212-7000']
        
        for potential_parent in parent_clause_patterns:
            if potential_parent in detected_clauses and potential_parent not in selected_sub_nums:
                seen_numbers.add(potential_parent)
                db_clause = await db.clauses.find_one({"number": potential_parent}, {"_id": 0})
                
                # Build Clause_Text with ONLY the selected sub-clauses
                selected_text_parts = []
                for sub in selected_subs:
                    sub_db = await db.clauses.find_one({"number": sub["number"]}, {"_id": 0})
                    sub_title = sub_db.get("title", sub.get("title", "")) if sub_db else sub.get("title", "")
                    date_match = re.search(r'\(([A-Z][a-z]{2}\s+\d{4})\)', sub.get("source_line", ""))
                    sub_date = f" ({date_match.group(1)})" if date_match else ""
                    selected_text_parts.append(f"- {sub['number']}, {sub_title}{sub_date}")
                
                clause_text = f"The Contracting Officer has selected the following clauses:\n\n" + "\n".join(selected_text_parts)
                
                agiloft_data["clauses"].append({
                    "Type": "FAR" if potential_parent.startswith("52.") else "DFARS",
                    "Number": potential_parent,
                    "Date": _extract_date_from_clause_text(db_clause.get("text", "")) if db_clause else "",
                    "Clause_Title": db_clause.get("title", "") if db_clause else "",
                    "Clause_Text": clause_text,
                    "Selected_Sub_Clauses": [s["number"] for s in selected_subs]
                })
                break
    
    # Add all SELECTED sub-clauses as individual entries
    for clause in extraction_result["selected_sub_clauses"]:
        if clause["number"] in seen_numbers:
            continue
        seen_numbers.add(clause["number"])
        
        db_clause = await db.clauses.find_one({"number": clause["number"]}, {"_id": 0})
        
        # Get clause text - fetch from acquisition.gov if not in DB or if it's a placeholder
        clause_text = db_clause.get("text", "") if db_clause else ""
        clause_title = db_clause.get("title", clause.get("title", "")) if db_clause else clause.get("title", "")
        
        # Check if text is missing, a placeholder, or too short to be real clause text
        is_placeholder = not clause_text or "Full text available at" in clause_text or "Content available at" in clause_text or len(clause_text) < 500
        
        if is_placeholder:
            # Try to fetch from acquisition.gov
            try:
                acq_data = await fetch_clause_from_acquisition_gov(clause["number"])
                if acq_data and acq_data.get("text") and len(acq_data.get("text", "")) > 100:
                    clause_text = acq_data.get("text", "")
                    if not clause_title:
                        clause_title = acq_data.get("title", "")
                    # Update the database with the fetched text
                    await db.clauses.update_one(
                        {"number": clause["number"]},
                        {"$set": {"text": clause_text, "title": clause_title}},
                        upsert=True
                    )
            except Exception as e:
                logger.warning(f"Could not fetch clause {clause['number']} from acquisition.gov: {e}")
        
        date_match = re.search(r'\(([A-Z][a-z]{2}\s+\d{4})\)', clause.get("source_line", ""))
        clause_date = date_match.group(1) if date_match else _extract_date_from_clause_text(clause_text)
        
        agiloft_data["clauses"].append({
            "Type": "FAR" if clause["number"].startswith("52.") else "DFARS",
            "Number": clause["number"],
            "Date": clause_date,
            "Clause_Title": clause_title,
            "Clause_Text": clause_text
        })
    
    # Add all OTHER detected clauses (not checkbox sub-clauses)
    for clause_num in detected_clauses:
        # Skip if already added
        if clause_num in seen_numbers:
            continue
        # Skip UNSELECTED sub-clauses (the ones marked with ___)
        if clause_num in unselected_sub_nums:
            continue
        
        seen_numbers.add(clause_num)
        db_clause = await db.clauses.find_one({"number": clause_num}, {"_id": 0})
        
        # Get clause text - fetch from acquisition.gov if not in DB or if it's a placeholder
        clause_text = db_clause.get("text", "") if db_clause else ""
        clause_title = db_clause.get("title", "") if db_clause else ""
        
        # Check if text is missing, a placeholder, or too short to be real clause text
        is_placeholder = not clause_text or "Full text available at" in clause_text or "Content available at" in clause_text or len(clause_text) < 500
        
        if is_placeholder:
            # Try to fetch from acquisition.gov
            try:
                acq_data = await fetch_clause_from_acquisition_gov(clause_num)
                if acq_data and acq_data.get("text") and len(acq_data.get("text", "")) > 100:
                    clause_text = acq_data.get("text", "")
                    if not clause_title:
                        clause_title = acq_data.get("title", "")
                    # Update the database with the fetched text
                    await db.clauses.update_one(
                        {"number": clause_num},
                        {"$set": {"text": clause_text, "title": clause_title}},
                        upsert=True
                    )
            except Exception as e:
                logger.warning(f"Could not fetch clause {clause_num} from acquisition.gov: {e}")
        
        agiloft_data["clauses"].append({
            "Type": "FAR" if clause_num.startswith("52.") else "DFARS",
            "Number": clause_num,
            "Date": _extract_date_from_clause_text(clause_text),
            "Clause_Title": clause_title,
            "Clause_Text": clause_text
        })
    
    agiloft_data["summary"] = {
        "total_clauses": len(agiloft_data["clauses"]),
        "far_clauses": len([c for c in agiloft_data["clauses"] if c["Type"] == "FAR"]),
        "dfars_clauses": len([c for c in agiloft_data["clauses"] if c["Type"] == "DFARS"])
    }
    
    return JSONResponse(
        content=agiloft_data,
        headers={
            "Content-Disposition": f'attachment; filename="agiloft_clauses_{contract_id}.json"'
        }
    )


@contracts_router.get("/{contract_id}/export-clauses-pdf")
async def export_clauses_pdf(contract_id: str, request: Request):
    """
    Export extracted clauses as PDF, matching the same filtering as the JSON export.
    Only includes selected sub-clauses and standalone clauses — not unselected checkbox items.
    Each clause gets full text fetched from acquisition.gov.
    """
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_LEFT, TA_JUSTIFY, TA_CENTER
    
    user = await require_auth(request)
    
    contract = await db.contracts.find_one(
        {"contract_id": contract_id, "user_id": user.user_id}
    )
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")
    
    text_content = contract.get("content", "")
    if not text_content:
        raise HTTPException(status_code=400, detail="Contract has no content to analyze")
    
    # ---- Use the exact same clause filtering logic as export_clauses_json ----
    extraction_result = _extract_clauses_with_checkboxes(text_content)
    
    detected_clauses_set = set(contract.get("clauses_found", []))
    extracted_numbers = {c["number"] for c in extraction_result["top_level_clauses"]}
    
    for clause_num in detected_clauses_set:
        if clause_num not in extracted_numbers:
            extraction_result["top_level_clauses"].append({
                "number": clause_num, "title": "", "is_selected": True, "source_line": ""
            })
    
    def _extract_date_from_clause_text(text: str) -> str:
        if not text:
            return ""
        search_text = text[:600]
        month_pattern = r'(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)'
        date_match = re.search(rf'\(\s*({month_pattern})\s+(\d{{4}})\s*\)', search_text)
        return f"{date_match.group(1)} {date_match.group(2)}" if date_match else ""

    selected_sub_nums = {c["number"] for c in extraction_result["selected_sub_clauses"]}
    unselected_sub_nums = {c["number"] for c in extraction_result.get("unselected_sub_clauses", [])}
    
    parent_selected_map = {}
    for parent_num, data in extraction_result.get("parent_clauses_with_selections", {}).items():
        if data.get("selected_sub_clauses"):
            parent_selected_map[parent_num] = data["selected_sub_clauses"]
    
    # Build the filtered clause list (same logic as JSON export)
    filtered_clauses = []  # list of dicts with Number, Title, Date, Text, Type
    seen_numbers = set()
    detected_clauses = contract.get("clauses_found", [])
    
    # 1. Parent clauses with selected sub-clauses
    if "checkbox_list" in parent_selected_map:
        selected_subs = parent_selected_map["checkbox_list"]
        parent_clause_patterns = ['52.212-5', '52.212-4', '52.244-6', '252.212-7001', '252.212-7000']
        for potential_parent in parent_clause_patterns:
            if potential_parent in detected_clauses and potential_parent not in selected_sub_nums:
                seen_numbers.add(potential_parent)
                db_clause = await db.clauses.find_one({"number": potential_parent}, {"_id": 0})
                selected_text_parts = []
                for sub in selected_subs:
                    sub_db = await db.clauses.find_one({"number": sub["number"]}, {"_id": 0})
                    sub_title = sub_db.get("title", sub.get("title", "")) if sub_db else sub.get("title", "")
                    date_match = re.search(r'\(([A-Z][a-z]{2}\s+\d{4})\)', sub.get("source_line", ""))
                    sub_date = f" ({date_match.group(1)})" if date_match else ""
                    selected_text_parts.append(f"- {sub['number']}, {sub_title}{sub_date}")
                clause_text = "The Contracting Officer has selected the following clauses:\n\n" + "\n".join(selected_text_parts)
                filtered_clauses.append({
                    "Number": potential_parent,
                    "Type": "FAR" if potential_parent.startswith("52.") else "DFARS",
                    "Clause_Title": db_clause.get("title", "") if db_clause else "",
                    "Date": _extract_date_from_clause_text(db_clause.get("text", "")) if db_clause else "",
                    "Clause_Text": clause_text,
                })
                break
    
    # 2. Selected sub-clauses
    for clause in extraction_result["selected_sub_clauses"]:
        if clause["number"] in seen_numbers:
            continue
        seen_numbers.add(clause["number"])
        db_clause = await db.clauses.find_one({"number": clause["number"]}, {"_id": 0})
        clause_text = db_clause.get("text", "") if db_clause else ""
        clause_title = db_clause.get("title", clause.get("title", "")) if db_clause else clause.get("title", "")
        if not clause_text or "Full text available at" in clause_text or "Content available at" in clause_text or len(clause_text) < 500:
            try:
                acq_data = await fetch_clause_from_acquisition_gov(clause["number"])
                if acq_data and acq_data.get("text") and len(acq_data["text"]) > 100:
                    clause_text = acq_data["text"]
                    if not clause_title:
                        clause_title = acq_data.get("title", "")
                    await db.clauses.update_one({"number": clause["number"]}, {"$set": {"text": clause_text, "title": clause_title}}, upsert=True)
            except Exception as e:
                logger.warning(f"PDF export: Could not fetch clause {clause['number']}: {e}")
        date_match = re.search(r'\(([A-Z][a-z]{2}\s+\d{4})\)', clause.get("source_line", ""))
        clause_date = date_match.group(1) if date_match else _extract_date_from_clause_text(clause_text)
        filtered_clauses.append({
            "Number": clause["number"],
            "Type": "FAR" if clause["number"].startswith("52.") else "DFARS",
            "Clause_Title": clause_title,
            "Date": clause_date,
            "Clause_Text": clause_text,
        })
    
    # 3. Other detected clauses (standalone, not unselected)
    for clause_num in detected_clauses:
        if clause_num in seen_numbers or clause_num in unselected_sub_nums:
            continue
        seen_numbers.add(clause_num)
        db_clause = await db.clauses.find_one({"number": clause_num}, {"_id": 0})
        clause_text = db_clause.get("text", "") if db_clause else ""
        clause_title = db_clause.get("title", "") if db_clause else ""
        if not clause_text or "Full text available at" in clause_text or "Content available at" in clause_text or len(clause_text) < 500:
            try:
                acq_data = await fetch_clause_from_acquisition_gov(clause_num)
                if acq_data and acq_data.get("text") and len(acq_data["text"]) > 100:
                    clause_text = acq_data["text"]
                    if not clause_title:
                        clause_title = acq_data.get("title", "")
                    await db.clauses.update_one({"number": clause_num}, {"$set": {"text": clause_text, "title": clause_title}}, upsert=True)
            except Exception as e:
                logger.warning(f"PDF export: Could not fetch clause {clause_num}: {e}")
        filtered_clauses.append({
            "Number": clause_num,
            "Type": "FAR" if clause_num.startswith("52.") else "DFARS",
            "Clause_Title": clause_title,
            "Date": _extract_date_from_clause_text(clause_text),
            "Clause_Text": clause_text,
        })
    
    # ---- Generate PDF ----
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle('ClauseTitle', parent=styles['Heading2'], alignment=TA_CENTER, spaceBefore=15, spaceAfter=5)
    date_style = ParagraphStyle('ClauseDate', parent=styles['Normal'], alignment=TA_CENTER, spaceBefore=2, spaceAfter=10, fontSize=10, textColor='gray')
    body_style = ParagraphStyle('ClauseBody', parent=styles['Normal'], alignment=TA_JUSTIFY, spaceBefore=3, spaceAfter=3, fontSize=10)
    meta_style = ParagraphStyle('ClauseMeta', parent=styles['Normal'], fontSize=9, textColor='gray', spaceBefore=2, spaceAfter=2)
    
    indent_styles = {}
    for level in range(5):
        indent_styles[level] = ParagraphStyle(
            f'Indent{level}', parent=styles['Normal'],
            leftIndent=level * 25 + (15 if level > 0 else 0),
            firstLineIndent=-15 if level > 0 else 0,
            spaceBefore=3, spaceAfter=3, alignment=TA_JUSTIFY, fontSize=10
        )
    centered_style = ParagraphStyle('EndOfClause', parent=styles['Normal'], alignment=TA_CENTER, spaceBefore=15, spaceAfter=15, fontStyle='italic')
    
    story = []
    story.append(Paragraph("Contract Clause Export", styles['Title']))
    story.append(Spacer(1, 0.3 * inch))
    story.append(Paragraph(f"Contract: {contract.get('filename', 'N/A')}", styles['Normal']))
    story.append(Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}", styles['Normal']))
    story.append(Paragraph(f"Total Clauses: {len(filtered_clauses)} (FAR: {sum(1 for c in filtered_clauses if c['Type']=='FAR')}, DFARS: {sum(1 for c in filtered_clauses if c['Type']=='DFARS')})", styles['Normal']))
    story.append(Spacer(1, 0.5 * inch))
    
    for clause in filtered_clauses:
        safe_title = (clause.get("Clause_Title") or "").replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        safe_number = clause.get("Number", "")
        clause_date = clause.get("Date", "")
        
        story.append(Paragraph(f"{safe_number}: {safe_title}", title_style))
        type_label = clause.get("Type", "")
        if clause_date:
            story.append(Paragraph(f"{type_label} - {clause_date}", date_style))
        else:
            story.append(Paragraph(f"{type_label}", date_style))
        story.append(Spacer(1, 0.1 * inch))
        
        clause_text = clause.get("Clause_Text", "")
        if clause_text:
            # For parent clauses with selected sub-clause summaries, render plain text
            # (don't re-fetch HTML which would include all unselected items)
            is_summary_clause = "The Contracting Officer has selected the following clauses" in clause_text
            
            rendered_html = False
            if not is_summary_clause:
                # Try to render via HTML parsing for proper indentation
                try:
                    html_content = await fetch_clause_html_from_acquisition_gov(safe_number)
                    if html_content:
                        text_paragraphs = _extract_pdf_paragraphs_from_dita(html_content)
                        for para_data in text_paragraphs:
                            para_text = para_data[0]
                            level = para_data[1]
                            is_centered = para_data[2] if len(para_data) > 2 else False
                            if para_text.strip():
                                safe_text = para_text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                                if is_centered:
                                    story.append(Paragraph(safe_text, centered_style))
                                else:
                                    style = indent_styles.get(min(level, 4), indent_styles[0])
                                    story.append(Paragraph(safe_text, style))
                        rendered_html = True
                except Exception:
                    pass
            
            if not rendered_html:
                # Render plain text line by line (used for summary clauses and fallback)
                for line in clause_text.split('\n'):
                    line = line.rstrip()
                    if not line.strip():
                        story.append(Spacer(1, 0.1 * inch))
                        continue
                    safe_line = line.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                    leading_spaces = len(line) - len(line.lstrip())
                    indent_level = min(leading_spaces // 4, 4)
                    style = indent_styles.get(indent_level, indent_styles[0])
                    story.append(Paragraph(safe_line, style))
        else:
            story.append(Paragraph("<i>Full text not available.</i>", styles['Normal']))
        
        story.append(Spacer(1, 0.4 * inch))
    
    doc.build(story)
    buffer.seek(0)
    
    filename = f"clause_export_{contract.get('filename', 'contract').replace('.pdf', '')}_{datetime.now().strftime('%Y%m%d')}.pdf"
    
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )



@contracts_router.post("/{contract_id}/analyze")
async def analyze_contract(contract_id: str, request: Request):
    """AI-powered contract analysis against FAR/DFARS requirements"""
    user = await require_auth(request)

    contract = await db.contracts.find_one(
        {"contract_id": contract_id, "user_id": user.user_id},
        {"_id": 0}
    )
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    # Get clause details for found clauses
    clauses_details = []
    for clause_num in contract.get("clauses_found", []):
        clause = await db.clauses.find_one({"number": clause_num}, {"_id": 0})
        if clause:
            clauses_details.append(f"{clause['number']}: {clause['title']}")

    prompt = f"""Analyze this government contract against FAR/DFARS requirements:

Contract Content (excerpt):
{contract.get('content', '')[:5000]}

Clauses Referenced in Contract:
{chr(10).join(clauses_details) if clauses_details else 'No standard clauses found'}

Provide a compliance analysis including:
1. Missing required clauses based on contract type
2. Potential compliance gaps
3. Recommendations for improvement
4. Risk assessment (High/Medium/Low)

Format as JSON:
{{"missing_clauses": [], "compliance_gaps": [], "recommendations": [], "risk_level": "Medium", "summary": ""}}"""

    ai_response = await get_ai_response(prompt)

    # Parse and store analysis
    try:
        import json
        json_start = ai_response.find('{')
        json_end = ai_response.rfind('}') + 1
        if json_start >= 0 and json_end > json_start:
            analysis = json.loads(ai_response[json_start:json_end])
        else:
            analysis = {"raw_analysis": ai_response}
    except:
        analysis = {"raw_analysis": ai_response}

    await db.contracts.update_one(
        {"contract_id": contract_id},
        {"$set": {"analysis_result": analysis}}
    )

    return {"contract_id": contract_id, "analysis": analysis}

@contracts_router.post("/compare")
async def compare_contracts(contract_id_1: str, contract_id_2: str, request: Request):
    """Compare two contracts"""
    user = await require_auth(request)

    contract1 = await db.contracts.find_one(
        {"contract_id": contract_id_1, "user_id": user.user_id},
        {"_id": 0}
    )
    contract2 = await db.contracts.find_one(
        {"contract_id": contract_id_2, "user_id": user.user_id},
        {"_id": 0}
    )

    if not contract1 or not contract2:
        raise HTTPException(status_code=404, detail="One or both contracts not found")

    prompt = f"""Compare these two government contracts:

Contract 1 ({contract1.get('name', 'Unknown')}):
Clauses: {', '.join(contract1.get('clauses_found', []))}
Content excerpt: {contract1.get('content', '')[:2000]}

Contract 2 ({contract2.get('name', 'Unknown')}):
Clauses: {', '.join(contract2.get('clauses_found', []))}
Content excerpt: {contract2.get('content', '')[:2000]}

Provide a comparison including:
1. Clauses present in Contract 1 but not in Contract 2
2. Clauses present in Contract 2 but not in Contract 1
3. Key differences in terms and conditions
4. Recommendations

Format as JSON:
{{"only_in_contract_1": [], "only_in_contract_2": [], "common_clauses": [], "key_differences": [], "recommendations": []}}"""

    ai_response = await get_ai_response(prompt)

    try:
        import json
        json_start = ai_response.find('{')
        json_end = ai_response.rfind('}') + 1
        if json_start >= 0 and json_end > json_start:
            comparison = json.loads(ai_response[json_start:json_end])
        else:
            comparison = {"raw_comparison": ai_response}
    except:
        comparison = {"raw_comparison": ai_response}

    return {"comparison": comparison}

# ==================== Flowdown Routes ====================

@flowdown_router.post("/analyze")
async def analyze_flowdown(flowdown_request: FlowdownRequest, request: Request):
    """Analyze which clauses must flow down to subcontractors"""
    user = await require_auth(request)

    # Get all flowdown-required clauses
    flowdown_clauses = await db.clauses.find(
        {"flowdown_required": True},
        {"_id": 0}
    ).to_list(100)

    # Filter by threshold and contract type
    applicable_clauses = []
    for clause in flowdown_clauses:
        threshold = clause.get("threshold_amount", 0) or 0
        contract_types = clause.get("contract_types", [])

        if flowdown_request.contract_value >= threshold:
            if "All" in contract_types or flowdown_request.contract_type in contract_types or not contract_types:
                applicable_clauses.append(clause)

    # Check which are in the provided clauses list
    in_contract = []
    missing = []
    for clause in applicable_clauses:
        if clause["number"] in flowdown_request.clauses:
            in_contract.append(clause)
        else:
            missing.append(clause)

    return {
        "required_flowdown_clauses": [c["number"] for c in applicable_clauses],
        "present_in_contract": [c["number"] for c in in_contract],
        "missing_from_contract": [c["number"] for c in missing],
        "clause_details": applicable_clauses
    }

# ==================== User Routes ====================

@user_router.get("/saved-searches")
async def get_saved_searches(request: Request):
    """Get user's saved searches"""
    user = await require_auth(request)
    searches = await db.saved_searches.find(
        {"user_id": user.user_id},
        {"_id": 0}
    ).to_list(100)
    return {"saved_searches": searches}

@user_router.post("/saved-searches")
async def save_search(request: Request, query: str = None, filters: Dict[str, Any] = {}):
    """Save a search"""
    user = await require_auth(request)
    if not query:
        raise HTTPException(status_code=400, detail="Query parameter required")
    search = SavedSearch(user_id=user.user_id, query=query, filters=filters)
    search_dict = search.model_dump()
    search_dict["created_at"] = search_dict["created_at"].isoformat()
    await db.saved_searches.insert_one(search_dict)
    # Remove MongoDB _id before returning
    search_dict.pop("_id", None)
    return search_dict

@user_router.delete("/saved-searches/{search_id}")
async def delete_saved_search(search_id: str, request: Request):
    """Delete a saved search"""
    user = await require_auth(request)
    result = await db.saved_searches.delete_one(
        {"search_id": search_id, "user_id": user.user_id}
    )
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Saved search not found")
    return {"message": "Search deleted"}

@user_router.get("/favorites")
async def get_favorites(request: Request):
    """Get user's favorite clauses"""
    user = await require_auth(request)
    favorites = await db.favorites.find(
        {"user_id": user.user_id},
        {"_id": 0}
    ).to_list(100)

    # Get full clause details
    result = []
    for fav in favorites:
        clause = await db.clauses.find_one({"clause_id": fav["clause_id"]}, {"_id": 0})
        if clause:
            result.append({**fav, "clause": clause})

    return {"favorites": result}

@user_router.post("/favorites")
async def add_favorite(clause_id: str, request: Request):
    """Add a clause to favorites"""
    user = await require_auth(request)

    # Check if already favorited
    existing = await db.favorites.find_one(
        {"user_id": user.user_id, "clause_id": clause_id},
        {"_id": 0}
    )
    if existing:
        return existing

    favorite = Favorite(user_id=user.user_id, clause_id=clause_id)
    fav_dict = favorite.model_dump()
    fav_dict["created_at"] = fav_dict["created_at"].isoformat()
    await db.favorites.insert_one(fav_dict)
    # Remove MongoDB _id before returning
    fav_dict.pop("_id", None)
    return fav_dict

@user_router.delete("/favorites/{clause_id}")
async def remove_favorite(clause_id: str, request: Request):
    """Remove a clause from favorites"""
    user = await require_auth(request)
    result = await db.favorites.delete_one(
        {"clause_id": clause_id, "user_id": user.user_id}
    )
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Favorite not found")
    return {"message": "Favorite removed"}

@user_router.get("/annotations")
async def get_annotations(request: Request, clause_id: Optional[str] = None):
    """Get user's annotations"""
    user = await require_auth(request)
    filter_query = {"user_id": user.user_id}
    if clause_id:
        filter_query["clause_id"] = clause_id

    annotations = await db.annotations.find(filter_query, {"_id": 0}).to_list(100)
    return {"annotations": annotations}

@user_router.post("/annotations")
async def create_annotation(annotation_data: AnnotationCreate, request: Request):
    """Create a new annotation"""
    user = await require_auth(request)
    annotation = Annotation(
        user_id=user.user_id,
        clause_id=annotation_data.clause_id,
        note=annotation_data.note
    )
    ann_dict = annotation.model_dump()
    ann_dict["created_at"] = ann_dict["created_at"].isoformat()
    await db.annotations.insert_one(ann_dict)
    # Remove MongoDB _id before returning
    ann_dict.pop("_id", None)
    return ann_dict

@user_router.delete("/annotations/{annotation_id}")
async def delete_annotation(annotation_id: str, request: Request):
    """Delete an annotation"""
    user = await require_auth(request)
    result = await db.annotations.delete_one(
        {"annotation_id": annotation_id, "user_id": user.user_id}
    )
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Annotation not found")
    return {"message": "Annotation deleted"}

# ==================== Export Routes ====================

@api_router.post("/export/pdf")
async def export_to_pdf(request: Request):
    """Export clauses to PDF with full text (DITA formatted)"""
    user = await require_auth(request)
    
    # Parse request body
    try:
        body = await request.json()
        clauses = body.get("clauses", [])
    except:
        raise HTTPException(status_code=400, detail="Invalid request body")

    # Get clause details with DITA formatting
    clause_docs = []
    for clause_num in clauses:
        clause = await db.clauses.find_one({"number": clause_num}, {"_id": 0})
        
        # If clause not in DB or missing text, fetch from acquisition.gov
        if not clause or not clause.get("text"):
            try:
                live_clause = await fetch_clause_from_acquisition_gov(clause_num)
                if live_clause:
                    if clause:
                        clause["text"] = live_clause.get("text", "")
                    else:
                        clause = live_clause
                    # Update DB with fetched text
                    await db.clauses.update_one(
                        {"number": clause_num},
                        {"$set": {"text": live_clause.get("text", "")}},
                        upsert=True
                    )
            except Exception as e:
                logger.warning(f"Failed to fetch clause {clause_num} from acquisition.gov: {e}")
        
        # Fetch HTML content for formatted display in PDF (same source as UI display)
        if clause:
            try:
                html_content = await fetch_clause_html_from_acquisition_gov(clause_num)
                if html_content:
                    clause["formatted_text"] = html_content
                else:
                    # Fallback to DITA with normalization
                    dita_content = await fetch_clause_dita_from_acquisition_gov(clause_num)
                    if dita_content:
                        clause["formatted_text"] = _normalize_clause_indent_html(dita_content)
            except Exception as e:
                logger.warning(f"Failed to fetch content for {clause_num}: {e}")
            
            clause_docs.append(clause)

    # Generate PDF
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    
    # Create custom styles for indentation based on list level
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_LEFT, TA_JUSTIFY, TA_CENTER
    
    # Style for clause titles (centered)
    title_centered_style = ParagraphStyle(
        'TitleCentered',
        parent=styles['Heading2'],
        alignment=TA_CENTER,
        spaceBefore=15,
        spaceAfter=10
    )
    
    # Indent styles for different list levels with hanging indent
    indent_styles = {}
    for level in range(5):
        indent_styles[level] = ParagraphStyle(
            f'Indent{level}',
            parent=styles['Normal'],
            leftIndent=level * 25 + (15 if level > 0 else 0),  # Hanging indent
            firstLineIndent=-15 if level > 0 else 0,
            spaceBefore=3,
            spaceAfter=3,
            alignment=TA_JUSTIFY,
            fontSize=10
        )
    
    # Centered style for "(End of clause)" markers
    centered_style = ParagraphStyle(
        'Centered',
        parent=styles['Normal'],
        alignment=TA_CENTER,
        spaceBefore=15,
        spaceAfter=15,
        fontStyle='italic'
    )
    
    story = []

    # Title
    story.append(Paragraph("Federal Clause Report", styles['Title']))
    story.append(Spacer(1, 0.5*inch))
    story.append(Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}", styles['Normal']))
    story.append(Paragraph(f"Exported by: {user.name}", styles['Normal']))
    story.append(Spacer(1, 0.5*inch))

    for clause in clause_docs:
        # Clause title - CENTERED
        clause_title = f"{clause.get('number', 'N/A')}: {clause.get('title', 'Untitled')}"
        story.append(Paragraph(clause_title, title_centered_style))
        story.append(Paragraph(f"Type: {clause.get('type', 'N/A')}", styles['Normal']))
        story.append(Paragraph(f"Flowdown Required: {'Yes' if clause.get('flowdown_required') else 'No'}", styles['Normal']))
        story.append(Spacer(1, 0.2*inch))
        
        # Include summary if available
        if clause.get('summary'):
            story.append(Paragraph("<b>Summary:</b>", styles['Normal']))
            story.append(Paragraph(clause['summary'], styles['Normal']))
            story.append(Spacer(1, 0.2*inch))
        
        # Include full text with DITA formatting
        story.append(Paragraph("<b>Full Text:</b>", styles['Normal']))
        
        formatted_text = clause.get('formatted_text') or clause.get('text')
        if formatted_text:
            # Parse DITA/HTML and extract text with indentation
            text_paragraphs = _extract_pdf_paragraphs_from_dita(formatted_text)
            centered_count = 0
            for para_data in text_paragraphs:
                para_text = para_data[0]
                level = para_data[1]
                is_centered = para_data[2] if len(para_data) > 2 else False
                
                if is_centered:
                    centered_count += 1
                    logger.info(f"PDF: Using centered style for: {para_text[:50]}...")
                
                if para_text.strip():
                    # Escape special characters for ReportLab
                    safe_text = para_text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                    
                    # Use centered style for titles and "(End of clause)" markers
                    if is_centered:
                        story.append(Paragraph(safe_text, centered_style))
                    else:
                        style = indent_styles.get(min(level, 4), indent_styles[0])
                        story.append(Paragraph(safe_text, style))
            
            logger.info(f"PDF: Total centered paragraphs: {centered_count}")
        else:
            story.append(Paragraph("<i>Full text not available. Visit acquisition.gov for complete clause text.</i>", styles['Normal']))
        
        story.append(Spacer(1, 0.5*inch))

    doc.build(story)
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=clause_report.pdf"}
    )


def _extract_pdf_paragraphs_from_dita(dita_content: str) -> list:
    """
    Extract paragraphs from DITA/HTML content with their indentation levels.
    Uses the same prefix detection logic that works for Agiloft formatting.
    Returns list of tuples: (text, level, is_centered)
    """
    from bs4 import BeautifulSoup
    
    paragraphs = []
    seen_texts = set()  # Track seen text to avoid duplicates
    
    try:
        soup = BeautifulSoup(dita_content, 'html.parser')
        
        # Find all paragraph-like elements
        for p in soup.find_all(['p', 'div']):
            # Skip if this element contains other p/div elements (parent container)
            if p.find(['p', 'div']):
                continue
            
            # Get text content
            text = p.get_text(separator=' ', strip=True)
            if not text:
                continue
            
            # Skip duplicates
            text_key = text[:100]  # Use first 100 chars as key
            if text_key in seen_texts:
                continue
            seen_texts.add(text_key)
            
            # Use the same prefix-based indentation detection that works for Agiloft
            # This detects (a), (1), (i), (A) patterns
            level = _detect_level_from_prefix(text)
            
            # Check if text should be centered - from style, class, or content
            text_lower = text.lower().strip()
            style = p.get('style', '')
            classes = p.get('class', [])
            if isinstance(classes, str):
                classes = classes.split()
            
            # Check for centered indicators
            is_centered = (
                'text-align:center' in style or
                'text-align: center' in style or
                'Ctr_SmCaps' in classes or  # Centered clause title class
                'Ctr' in classes or  # Generic centered class
                'Endofclause' in classes or  # End of clause marker
                text_lower in ['(end of clause)', '(end of provision)', 'end of clause', 'end of provision']
            )
            
            paragraphs.append((text, min(level, 4), is_centered))
    
    except Exception as e:
        logger.error(f"Error parsing DITA for PDF: {e}")
        # Fallback: split by lines and detect indentation from prefix
        for line in dita_content.split('\n'):
            clean = re.sub(r'<[^>]+>', '', line).strip()
            if clean and clean not in seen_texts:
                seen_texts.add(clean)
                level = _detect_level_from_prefix(clean)
                text_lower = clean.lower()
                is_centered = text_lower in ['(end of clause)', '(end of provision)']
                paragraphs.append((clean, level, is_centered))
    
    return paragraphs

# ==================== Compliance Checklist Routes ====================

@api_router.post("/checklist/generate")
async def generate_checklist(contract_id: str, request: Request):
    """Generate a compliance checklist for a contract"""
    user = await require_auth(request)

    contract = await db.contracts.find_one(
        {"contract_id": contract_id, "user_id": user.user_id},
        {"_id": 0}
    )
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    # Get clause details
    checklist_items = []
    for clause_num in contract.get("clauses_found", []):
        clause = await db.clauses.find_one({"number": clause_num}, {"_id": 0})
        if clause:
            checklist_items.append({
                "clause_number": clause["number"],
                "clause_title": clause["title"],
                "requirement": clause.get("summary", clause["title"]),
                "status": "pending",
                "notes": ""
            })

    checklist = ComplianceChecklist(
        user_id=user.user_id,
        contract_id=contract_id,
        items=checklist_items
    )

    checklist_dict = checklist.model_dump()
    checklist_dict["created_at"] = checklist_dict["created_at"].isoformat()
    await db.checklists.insert_one(checklist_dict)
    
    # Remove _id added by MongoDB insert_one to avoid serialization error
    checklist_dict.pop("_id", None)

    return checklist_dict

@api_router.get("/checklist/{checklist_id}")
async def get_checklist(checklist_id: str, request: Request):
    """Get a compliance checklist"""
    user = await require_auth(request)
    checklist = await db.checklists.find_one(
        {"checklist_id": checklist_id, "user_id": user.user_id},
        {"_id": 0}
    )
    if not checklist:
        raise HTTPException(status_code=404, detail="Checklist not found")
    return checklist

@api_router.put("/checklist/{checklist_id}/item/{item_index}")
async def update_checklist_item(
    checklist_id: str,
    item_index: int,
    status: str,
    notes: str = "",
    request: Request = None
):
    """Update a checklist item status"""
    user = await require_auth(request)

    result = await db.checklists.update_one(
        {"checklist_id": checklist_id, "user_id": user.user_id},
        {"$set": {f"items.{item_index}.status": status, f"items.{item_index}.notes": notes}}
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Checklist not found")

    return {"message": "Checklist item updated"}

# ==================== Root Route ====================

@api_router.get("/")
async def root():
    return {"message": "Federal Clause Management API", "version": "1.0.0"}

# ==================== Agiloft Integration Routes ====================

class AgiloftConfig(BaseModel):
    """Agiloft KB configuration
    
    Expected URL format: https://yourinstance.saas.agiloft.com
    The full path /ewws/alrest/{KB}/endpoint is constructed automatically.
    """
    kb_url: str  # Base Agiloft URL, e.g., https://elitebcopartnerkb.saas.agiloft.com
    username: str
    password: str
    kb_name: str  # Knowledge base name (required)

class AgiloftSyncRequest(BaseModel):
    """Request to sync clauses from Agiloft"""
    config: AgiloftConfig
    table_name: str = "clause"  # Agiloft table name - "clause" per OpenAPI spec
    field_mapping: Dict[str, str] = {}  # Map Agiloft fields to our clause fields

# Agiloft field mapping - maps our internal field names to Agiloft's field names
# Based on OpenAPI spec: clause_title, clause_text, clause_type, etc.
AGILOFT_CLAUSE_FIELD_MAPPING = {
    "number": "clause_title",        # Our clause number goes to clause_title
    "title": "clause_text",          # Our title could go to guidance or a custom field
    "text": "clause_text",           # Full text of the clause
    "type": "clause_type",           # FAR/DFARS type
    "summary": "guidance",           # Summary/guidance text
    "flowdown_required": "boilerplate",  # Boolean as string
    "keywords": "condition",         # Keywords as comma-separated
}

def _norm_agiloft_base(url: str) -> str:
    """Normalize Agiloft base URL - remove trailing slashes and paths"""
    url = (url or "").strip().rstrip("/")
    # Remove any path suffixes like /ewws/alrest/KB or /ewws/EWRESTful/v1
    if "/ewws/" in url:
        url = url.split("/ewws/")[0]
    return url

def _build_agiloft_url(base_url: str, kb_name: str, endpoint: str) -> str:
    """Build Agiloft REST API URL
    
    Format: {base_url}/ewws/alrest/{kb_name}/{endpoint}
    Example: https://elitebcopartnerkb.saas.agiloft.com/ewws/alrest/elitebcoPartnerKB/login
    """
    base = _norm_agiloft_base(base_url)
    return f"{base}/ewws/alrest/{kb_name}/{endpoint}"

async def agiloft_login(client: httpx.AsyncClient, config: AgiloftConfig) -> Dict[str, Any]:
    """
    Agiloft REST API login.
    
    URL format: {base_url}/ewws/alrest/{KB}/login
    Example: https://elitebcopartnerkb.saas.agiloft.com/ewws/alrest/elitebcoPartnerKB/login
    
    JSON body: {login, password, KB, lang}
    
    Response: {"result": {"access_token": "..."}}
    Token is nested under result.access_token
    """
    login_url = _build_agiloft_url(config.kb_url, config.kb_name, "login")
    
    # JSON payload 
    payload = {
        "login": config.username,
        "password": config.password,
        "KB": config.kb_name,
        "lang": "en"
    }
    
    logger.info(f"Attempting Agiloft login to: {login_url}")
    
    try:
        resp = await client.post(
            login_url, 
            json=payload,
            headers={"Content-Type": "application/json"}
        )
    except httpx.ConnectError as e:
        logger.error(f"Agiloft connection failed: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"Cannot connect to Agiloft server at {login_url}. This may be because: 1) The URL is incorrect, 2) The Agiloft instance is on a private network, or 3) IP whitelisting is blocking this connection. Error: {str(e)}"
        )
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail="Agiloft server connection timed out. Please try again."
        )
    
    raw_text = resp.text or ""
    logger.info(f"Agiloft login response status: {resp.status_code}")
    logger.info(f"Agiloft login response body: {raw_text[:500]}")
    
    # Try to parse JSON response
    try:
        data = resp.json()
    except Exception:
        logger.error(f"Agiloft returned non-JSON response: {raw_text[:300]}")
        raise HTTPException(
            status_code=401, 
            detail=f"Agiloft authentication failed - invalid response format. Check your API URL."
        )
    
    # Handle HTTP error status codes
    if resp.status_code >= 400:
        error_msg = data.get("message", data.get("error", raw_text[:300]))
        logger.error(f"Agiloft login HTTP error {resp.status_code}: {error_msg}")
        raise HTTPException(
            status_code=resp.status_code,
            detail=f"Agiloft login failed: {error_msg}"
        )
    
    # Check for explicit error in response body (Agiloft may return 200 with error)
    if isinstance(data, dict):
        # Check for success:false pattern
        if data.get("success") is False:
            errors = data.get("errors", [])
            if errors and isinstance(errors, list):
                if isinstance(errors[0], dict):
                    error_msg = errors[0].get("message", "Authentication failed")
                else:
                    error_msg = str(errors[0])
            else:
                error_msg = data.get("message", "Authentication failed")
            logger.error(f"Agiloft login error: {error_msg}")
            raise HTTPException(status_code=401, detail=f"Agiloft authentication failed: {error_msg}")
        
        # Check for error field
        if "error" in data:
            error_msg = data.get("error", "Unknown error")
            logger.error(f"Agiloft login error field: {error_msg}")
            raise HTTPException(status_code=401, detail=f"Agiloft authentication failed: {error_msg}")
    
    # CRITICAL: Extract access_token - it's nested under "result" in Agiloft response
    # Response format: {"result": {"access_token": "..."}}
    token = None
    
    # First try nested under "result"
    if isinstance(data.get("result"), dict):
        token = data["result"].get("access_token")
    
    # Fall back to top-level
    if not token:
        token = data.get("access_token") or data.get("token") or data.get("auth_token")
    
    if not token:
        logger.error(f"Agiloft login: No access_token in response. Response: {data}")
        raise HTTPException(
            status_code=401, 
            detail="Agiloft authentication failed: No access token received. Check username/password."
        )
    
    logger.info(f"Agiloft login successful, token received (length: {len(token)})")
    
    # Return normalized data with token at top level for easier access
    return {"access_token": token, "raw_response": data}

@agiloft_router.post("/test-connection")
async def test_agiloft_connection(config: AgiloftConfig, request: Request):
    """Test connection to Agiloft knowledge base"""
    user = await require_auth(request)

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            login_data = await agiloft_login(client, config)
            token = login_data.get("access_token")
            
            # Construct the URL we used for reference
            login_url = _build_agiloft_url(config.kb_url, config.kb_name, "login")

            return {
                "success": True,
                "message": "Successfully connected to Agiloft KB",
                "kb_name": config.kb_name,
                "token_preview": f"{token[:20]}..." if token and len(token) > 20 else token,
                "api_url_used": login_url
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Agiloft connection error: {e}")
        raise HTTPException(status_code=500, detail=f"Agiloft connection error: {str(e)}")

@agiloft_router.post("/sync-clauses")
async def sync_clauses_from_agiloft(sync_request: AgiloftSyncRequest, request: Request):
    """Sync clauses from Agiloft knowledge base (legacy - kept for compatibility)"""
    user = await require_auth(request)
    return {"success": False, "message": "Use /push-clauses to push clauses TO Agiloft"}

class AgiloftPushRequest(BaseModel):
    """Request to push clauses to Agiloft"""
    config: AgiloftConfig
    source: str = "database"  # database or acquisition

@agiloft_router.post("/push-clauses")
async def push_clauses_to_agiloft(push_request: AgiloftPushRequest, request: Request):
    """Push clauses from our database to Agiloft knowledge base
    
    Uses the /clause endpoint (singular, lowercase) per OpenAPI spec.
    Field mapping based on AL_Clause_Library_Request schema.
    """
    user = await require_auth(request)

    config = push_request.config

    # Get clauses to push
    if push_request.source == "acquisition":
        far_clauses = await fetch_far_index()
        clauses_to_push = []
        for clause_info in far_clauses[:50]:
            clause_data = await fetch_clause_from_acquisition_gov(clause_info["number"])
            if clause_data:
                clauses_to_push.append(clause_data)
    else:
        clauses_to_push = await db.clauses.find({}, {"_id": 0}).to_list(500)

    if not clauses_to_push:
        return {"success": False, "message": "No clauses found to push"}

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            login_data = await agiloft_login(client, config)
            token = login_data.get("access_token")
            
            if not token:
                return {"success": False, "message": "Authentication failed - no token received"}

            auth_headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}"
            }

            created_count = 0
            updated_count = 0
            errors_list = []
            
            # Table name is "clause" (lowercase, singular) per OpenAPI spec
            clause_table = "clause"

            for clause in clauses_to_push:
                # Map our fields to Agiloft's field names per AL_Clause_Library_Request schema
                agiloft_data = {
                    "clause_title": f"{clause.get('number', '')} - {clause.get('title', '')}",
                    "clause_text": clause.get("text", "")[:32000],  # Agiloft may have text limits
                    "guidance": clause.get("summary", ""),
                    "boilerplate": "Yes" if clause.get("flowdown_required") else "No",
                    "condition": ", ".join(clause.get("keywords", [])),
                }
                
                # Add clause_type if it maps to an Agiloft type ID (you may need to configure this)
                clause_type = clause.get("type", "FAR")
                if clause_type:
                    agiloft_data["clause_usage"] = clause_type  # FAR or DFARS

                try:
                    # First, search if clause already exists using /{table}/search endpoint
                    search_url = _build_agiloft_url(config.kb_url, config.kb_name, f"{clause_table}/search")
                    search_payload = {
                        "query": f"clause_title LIKE '%{clause.get('number', '')}%'"
                    }
                    
                    search_response = await client.post(
                        search_url,
                        params={"lang": "en"},
                        json=search_payload,
                        headers=auth_headers
                    )

                    existing_records = []
                    if search_response.status_code == 200:
                        try:
                            search_data = search_response.json()
                            # Response could be a list or have a records/result field
                            if isinstance(search_data, list):
                                existing_records = search_data
                            elif isinstance(search_data.get("result"), list):
                                existing_records = search_data["result"]
                            else:
                                existing_records = search_data.get("records", search_data.get("result", []))
                        except Exception as e:
                            logger.warning(f"Failed to parse search response: {e}")

                    if existing_records and len(existing_records) > 0:
                        # Update existing record using PUT /{table}/{id}
                        record_id = existing_records[0].get("id", existing_records[0].get("$id"))
                        if record_id:
                            update_url = _build_agiloft_url(config.kb_url, config.kb_name, f"{clause_table}/{record_id}")
                            update_response = await client.put(
                                update_url,
                                params={"lang": "en"},
                                json=agiloft_data,
                                headers=auth_headers
                            )
                            if update_response.status_code == 200:
                                updated_count += 1
                            else:
                                errors_list.append(f"Failed to update {clause.get('number')}: {update_response.status_code}")
                    else:
                        # Create new record using POST /{table}
                        create_url = _build_agiloft_url(config.kb_url, config.kb_name, clause_table)
                        create_response = await client.post(
                            create_url,
                            params={"lang": "en"},
                            json=agiloft_data,
                            headers=auth_headers
                        )
                        if create_response.status_code in [200, 201]:
                            created_count += 1
                        else:
                            errors_list.append(f"Failed to create {clause.get('number')}: {create_response.status_code}")

                except Exception as e:
                    logger.error(f"Error pushing clause {clause.get('number')}: {e}")
                    errors_list.append(f"Error with {clause.get('number')}: {str(e)}")

            result = {
                "success": True,
                "message": f"Pushed {created_count + updated_count} clauses to Agiloft",
                "pushed_count": created_count + updated_count,
                "created_count": created_count,
                "updated_count": updated_count
            }
            
            if errors_list:
                result["errors"] = errors_list[:10]  # Limit error list
                result["total_errors"] = len(errors_list)
            
            return result

    except HTTPException as e:
        raise
    except Exception as e:
        logger.error(f"Agiloft push error: {e}")
        return {"success": False, "message": f"Push failed: {str(e)}"}

class AgiloftContractsRequest(BaseModel):
    """Request to fetch/search Agiloft contracts"""
    config: AgiloftConfig
    table_name: str = "contract"  # Agiloft table name - lowercase per OpenAPI spec
    search_query: Optional[str] = None  # Search term for contract title
    contract_type: Optional[str] = None  # Filter by contract type
    contract_id: Optional[str] = None  # Search by specific contract ID
    limit: int = 50  # Max results to return

@agiloft_router.post("/contracts")
async def get_agiloft_contracts(contracts_request: AgiloftContractsRequest, request: Request):
    """Fetch and search contracts from Agiloft
    
    Supports searching by:
    - Contract Title (partial match)
    - Contract Type (exact match)
    - Contract ID (exact match)
    """
    user = await require_auth(request)

    config = contracts_request.config

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            login_data = await agiloft_login(client, config)
            
            token = login_data.get("access_token")
            if not token:
                raise HTTPException(status_code=401, detail="Authentication failed - no token received")
            
            auth_headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}"
            }

            # Build search query based on filters
            # Agiloft search uses SQL-like syntax with internal field names
            # Note: contract_title might not be searchable directly, but id is
            search_conditions = []
            
            if contracts_request.contract_id:
                # Search by exact ID - this works reliably
                search_conditions.append(f"id = {contracts_request.contract_id}")
            
            # Note: Text search on contract_title may not work directly in Agiloft
            # The title is stored in a related table (DAOcontract_to_contract)
            # For now, we'll fetch all and filter on our side for text searches
            
            client_side_filter = None
            if contracts_request.search_query and not contracts_request.contract_id:
                client_side_filter = contracts_request.search_query.lower()
            
            if contracts_request.contract_type and not contracts_request.contract_id:
                # Try to filter by contract type
                search_conditions.append(f"contract_type LIKE '%{contracts_request.contract_type}%'")
            
            # Build the search payload
            search_payload = {}
            if search_conditions:
                search_payload["query"] = " AND ".join(search_conditions)
            
            # Add limit
            search_payload["$limit"] = contracts_request.limit
            
            contracts_url = _build_agiloft_url(config.kb_url, config.kb_name, f"{contracts_request.table_name}/search")
            
            logger.info(f"Searching Agiloft contracts: {contracts_url}")
            logger.info(f"Search payload: {search_payload}")
            
            search_response = await client.post(
                contracts_url,
                params={"lang": "en"},
                json=search_payload,
                headers=auth_headers
            )
            
            logger.info(f"Agiloft contracts response status: {search_response.status_code}")
            logger.info(f"Agiloft contracts response: {search_response.text[:1000]}")

            contracts = []

            if search_response.status_code == 200:
                try:
                    data = search_response.json()
                    
                    # Handle different response formats
                    if isinstance(data, list):
                        records = data
                    elif isinstance(data.get("result"), list):
                        records = data["result"]
                    else:
                        records = data.get("records", data.get("result", []))
                    
                    logger.info(f"Found {len(records) if records else 0} contract records")

                    # The search endpoint returns limited data, we need to fetch each contract's details
                    contracts = []
                    
                    for record in records[:contracts_request.limit]:  # Limit how many we fetch in detail
                        contract_id = str(record.get("id", record.get("$id", "")))
                        
                        # Fetch full contract details
                        detail_url = _build_agiloft_url(config.kb_url, config.kb_name, f"contract/{contract_id}")
                        detail_response = await client.get(
                            detail_url,
                            params={"lang": "en"},
                            headers=auth_headers
                        )
                        
                        if detail_response.status_code == 200:
                            detail_data = detail_response.json()
                            full_record = detail_data.get("result", detail_data) if isinstance(detail_data, dict) else detail_data
                        else:
                            full_record = record  # Fall back to search data
                        
                        # Extract data from nested DAO objects
                        contract_title = ""
                        if isinstance(full_record.get("DAOcontract_to_contract"), dict):
                            contract_title = full_record["DAOcontract_to_contract"].get("root_contract_title", "")
                        if not contract_title:
                            contract_title = full_record.get("contract_title", full_record.get("title", full_record.get("name", "")))
                        
                        contract_type = full_record.get("contract_type", "")
                        if not contract_type and isinstance(full_record.get("DAOcontract_to_contract_type"), dict):
                            contract_type = full_record["DAOcontract_to_contract_type"].get("contract_type", "")
                        
                        company_name = ""
                        if isinstance(full_record.get("DAOcontract_to_company"), dict):
                            company_name = full_record["DAOcontract_to_company"].get("company_name", "")
                        if not company_name:
                            company_name = full_record.get("company_name", full_record.get("company", ""))
                        
                        status = full_record.get("wfstate", full_record.get("status", ""))
                        contract_end_date = full_record.get("contract_end_date", full_record.get("end_date", ""))
                        date_created = full_record.get("date_created", full_record.get("created", ""))
                        
                        contract_value = full_record.get("contract_value", full_record.get("value", full_record.get("amount", 0)))
                        try:
                            contract_value = float(contract_value) if contract_value else 0
                        except:
                            contract_value = 0
                        
                        clauses_str = full_record.get("clauses", full_record.get("contract_clauses", full_record.get("clause_list", "")))
                        clauses = [c.strip() for c in str(clauses_str).split(",") if c.strip()] if clauses_str else []

                        contract_data = {
                            "id": contract_id,
                            "name": contract_title or f"Contract #{contract_id}",
                            "contract_title": contract_title,
                            "type": contract_type,
                            "contract_type": contract_type,
                            "company_name": company_name,
                            "value": contract_value,
                            "clauses": clauses,
                            "status": status,
                            "contract_end_date": contract_end_date,
                            "date_created": date_created
                        }
                        
                        # Apply client-side text filter if needed
                        if client_side_filter:
                            # Search in title, company name, and type
                            searchable_text = f"{contract_title} {company_name} {contract_type}".lower()
                            if client_side_filter in searchable_text:
                                contracts.append(contract_data)
                        else:
                            contracts.append(contract_data)
                        
                except Exception as e:
                    logger.error(f"Error parsing Agiloft contracts: {e}")
                    return {
                        "success": False,
                        "message": f"Failed to parse contract data: {str(e)}",
                        "contracts": [],
                        "raw_response": search_response.text[:500]
                    }
            else:
                logger.error(f"Agiloft contracts search failed: {search_response.status_code}")
                return {
                    "success": False,
                    "message": f"Failed to fetch contracts: HTTP {search_response.status_code}",
                    "contracts": [],
                    "raw_response": search_response.text[:500]
                }

            return {
                "success": True,
                "contracts": contracts,
                "total": len(contracts),
                "search_applied": bool(search_conditions)
            }

    except Exception as e:
        logger.error(f"Agiloft contracts error: {e}")
        return {"success": False, "message": str(e)}

class AgiloftGetContractRequest(BaseModel):
    """Request to get a single contract by ID"""
    config: AgiloftConfig
    contract_id: str

@agiloft_router.post("/contract/{contract_id}")
async def get_agiloft_contract(contract_id: str, get_request: AgiloftGetContractRequest, request: Request):
    """Get a single contract with all fields from Agiloft"""
    user = await require_auth(request)
    
    config = get_request.config
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            login_data = await agiloft_login(client, config)
            token = login_data.get("access_token")
            
            if not token:
                raise HTTPException(status_code=401, detail="Authentication failed")
            
            auth_headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}"
            }
            
            # Get single contract by ID
            contract_url = _build_agiloft_url(config.kb_url, config.kb_name, f"contract/{contract_id}")
            
            logger.info(f"Fetching contract: {contract_url}")
            
            response = await client.get(
                contract_url,
                params={"lang": "en"},
                headers=auth_headers
            )
            
            if response.status_code == 200:
                data = response.json()
                record = data.get("result", data) if isinstance(data, dict) else data
                
                logger.info(f"Contract {contract_id} fields: {list(record.keys()) if isinstance(record, dict) else 'not a dict'}")
                
                return {
                    "success": True,
                    "contract": record,
                    "available_fields": list(record.keys()) if isinstance(record, dict) else []
                }
            else:
                return {
                    "success": False,
                    "message": f"Failed to fetch contract: HTTP {response.status_code}",
                    "raw_response": response.text[:500]
                }
                
    except Exception as e:
        logger.error(f"Error fetching contract: {e}")
        return {"success": False, "message": str(e)}

class AgiloftAnalyzeRequest(BaseModel):
    """Request to analyze an Agiloft contract"""
    config: AgiloftConfig
    contract_id: str
    contract_clauses: List[str]
    contract_type: str = "Fixed-Price"
    contract_value: float = 0

@agiloft_router.post("/analyze-contract")
async def analyze_agiloft_contract(analyze_request: AgiloftAnalyzeRequest, request: Request):
    """Analyze an Agiloft contract for clause compliance"""
    user = await require_auth(request)

    contract_clauses = analyze_request.contract_clauses
    contract_type = analyze_request.contract_type
    contract_value = analyze_request.contract_value

    all_clauses = await db.clauses.find({}, {"_id": 0}).to_list(500)
    flowdown_clauses = [c for c in all_clauses if c.get("flowdown_required")]

    applicable_flowdown = []
    for clause in flowdown_clauses:
        threshold = clause.get("threshold_amount", 0) or 0
        contract_types = clause.get("contract_types", [])

        if contract_value >= threshold:
            if "All" in contract_types or contract_type in contract_types or not contract_types:
                applicable_flowdown.append(clause["number"])

    correct_clauses = []
    missing_clauses = []
    needs_update = []

    all_clause_numbers = [c["number"] for c in all_clauses]

    for clause_num in contract_clauses:
        if clause_num in all_clause_numbers:
            correct_clauses.append(clause_num)
        else:
            needs_update.append(clause_num)

    for required in applicable_flowdown:
        if required not in contract_clauses:
            missing_clauses.append(required)

    if missing_clauses:
        compliance_status = "non-compliant"
    elif needs_update:
        compliance_status = "warning"
    else:
        compliance_status = "compliant"

    return {
        "success": True,
        "contract_id": analyze_request.contract_id,
        "compliance_status": compliance_status,
        "correct_clauses": correct_clauses,
        "missing_clauses": missing_clauses,
        "needs_update": needs_update,
        "required_flowdown": applicable_flowdown,
        "total_checked": len(contract_clauses),
        "recommendations": [f"Add missing clause {c}" for c in missing_clauses[:5]]
    }

class AgiloftUpdateRequest(BaseModel):
    """Request to update an Agiloft contract"""
    config: AgiloftConfig
    contract_id: str
    updates: Dict[str, Any]

@agiloft_router.post("/update-contract")
async def update_agiloft_contract(update_request: AgiloftUpdateRequest, request: Request):
    """Update a contract in Agiloft with compliance fixes
    
    Uses PUT /contract/{id} endpoint per OpenAPI spec.
    """
    user = await require_auth(request)

    config = update_request.config

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            login_data = await agiloft_login(client, config)
            token = login_data.get("access_token")
            
            if not token:
                raise HTTPException(status_code=401, detail="Authentication failed - no token received")

            auth_headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}"
            }

            update_data = {}

            missing = update_request.updates.get("missing_clauses", [])
            flowdown = update_request.updates.get("flowdown_clauses", [])

            if missing:
                update_data["missing_clauses_flag"] = "Yes"
                update_data["missing_clauses_list"] = ", ".join(missing)

            if flowdown:
                update_data["flowdown_clauses"] = ", ".join(flowdown)

            update_data["compliance_checked"] = datetime.now(timezone.utc).isoformat()
            update_data["compliance_checker"] = user.name

            # Use new URL builder for correct path format
            update_url = _build_agiloft_url(config.kb_url, config.kb_name, f"contract/{update_request.contract_id}")
            update_response = await client.put(
                update_url,
                params={"lang": "en"},
                json=update_data,
                headers=auth_headers
            )

            if update_response.status_code == 200:
                return {
                    "success": True,
                    "message": "Contract updated in Agiloft",
                    "updated_fields": list(update_data.keys())
                }
            else:
                error_detail = ""
                try:
                    error_data = update_response.json()
                    error_detail = error_data.get("message", error_data.get("error", ""))
                except:
                    error_detail = update_response.text[:200]
                
                return {
                    "success": False,
                    "message": f"Failed to update contract: HTTP {update_response.status_code}",
                    "detail": error_detail
                }

    except HTTPException as e:
        logger.error(f"Agiloft update auth error: {e.detail}")
        return {"success": False, "message": str(e.detail)}
    except Exception as e:
        logger.error(f"Agiloft update error: {e}")
        return {"success": False, "message": str(e)}

# ==================== Agiloft Field Mapping Configuration ====================

@agiloft_router.get("/field-mapping")
async def get_agiloft_field_mapping(request: Request):
    """Get the current Agiloft field mapping configuration
    
    Returns the mapping between our internal field names and Agiloft's field names.
    Based on Agiloft OpenAPI spec for the 'clause' table (Clause Library).
    """
    user = await require_auth(request)
    
    return {
        "success": True,
        "table_name": "clause",  # Agiloft logical table name
        "field_mapping": {
            "our_fields": {
                "number": "Clause number (e.g., 52.212-4)",
                "title": "Clause title",
                "text": "Full clause text",
                "type": "FAR or DFARS",
                "summary": "Clause summary/guidance",
                "flowdown_required": "Boolean - flowdown to subcontractors",
                "keywords": "Comma-separated keywords",
                "threshold_amount": "Dollar threshold for applicability"
            },
            "agiloft_fields": {
                "clause_title": "Main title field in Agiloft - we put 'number - title' here",
                "clause_text": "Full text of the clause",
                "clause_type": "Reference to Clause Type table (may need ID)",
                "guidance": "Guidance/summary text",
                "boilerplate": "Yes/No - indicates flowdown requirement",
                "condition": "Additional conditions - we put keywords here",
                "clause_usage": "FAR or DFARS type indicator",
                "source_contract_type": "Reference to source contract type",
                "language_id": "Language reference",
                "default_risk_rating": "Risk rating field",
                "clause_owner_id": "Owner reference",
                "owned_by_team_id": "Team reference",
                "fingerprint": "Unique identifier/hash",
                "source_clause_id": "Reference to source clause"
            },
            "current_mapping": AGILOFT_CLAUSE_FIELD_MAPPING
        },
        "endpoints": {
            "login": "POST /login - JSON body with login, password, KB, lang",
            "create_clause": "POST /clause - Create new clause record",
            "get_clause": "GET /clause/{id} - Get clause by ID",
            "update_clause": "PUT /clause/{id} - Update existing clause",
            "delete_clause": "DELETE /clause/{id} - Delete clause",
            "search_clauses": "POST /clause/search - Search clause library",
            "upsert_clause": "POST /clause/upsert - Create or update clause"
        }
    }

class AgiloftFieldMappingUpdate(BaseModel):
    """Request to update field mapping"""
    mapping: Dict[str, str]

@agiloft_router.post("/field-mapping")
async def update_agiloft_field_mapping(mapping_update: AgiloftFieldMappingUpdate, request: Request):
    """Update the Agiloft field mapping configuration
    
    Note: This updates the in-memory mapping. For persistent changes,
    the mapping should be stored in the database.
    """
    user = await require_auth(request)
    
    global AGILOFT_CLAUSE_FIELD_MAPPING
    
    # Validate that the mapping keys are valid
    valid_our_fields = ["number", "title", "text", "type", "summary", "flowdown_required", "keywords", "threshold_amount"]
    
    for key in mapping_update.mapping.keys():
        if key not in valid_our_fields:
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid field name: {key}. Valid fields: {valid_our_fields}"
            )
    
    # Update the mapping
    AGILOFT_CLAUSE_FIELD_MAPPING.update(mapping_update.mapping)
    
    # Optionally store in database for persistence
    await db.settings.update_one(
        {"key": "agiloft_field_mapping"},
        {"$set": {"value": AGILOFT_CLAUSE_FIELD_MAPPING, "updated_by": user.user_id, "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True
    )
    
    return {
        "success": True,
        "message": "Field mapping updated",
        "new_mapping": AGILOFT_CLAUSE_FIELD_MAPPING
    }

# ==================== Clause Comparison Routes ====================

def normalize_clause_number(text: str) -> Optional[str]:
    """
    Normalize a clause number to a standard format for comparison.
    
    Handles variations like:
    - "52.209-12" (standard)
    - "52.209-12." (trailing period)
    - "52.209-12 (JAN 2021)" (with date)
    - "FAR 52.209-12" (with prefix)
    - "52.209–12" (en-dash instead of hyphen)
    - "52.209 - 12" (spaces around hyphen)
    - "52.209-012" (leading zeros in last segment)
    
    Returns normalized format: "52.209-12" or None if no match
    """
    import re
    
    if not text:
        return None
    
    # Replace en-dash, em-dash with hyphen
    text = text.replace('–', '-').replace('—', '-')
    
    # Remove common prefixes
    text = re.sub(r'^(FAR|DFARS|DFAR)\s*', '', text, flags=re.IGNORECASE)
    
    # Try to extract the clause number pattern
    # Pattern: 2-3 digits, period, 3 digits, hyphen, 1+ digits
    # Examples: 52.209-12, 252.204-7012
    match = re.search(r'(\d{2,3})\s*\.\s*(\d{3})\s*-\s*(\d+)', text)
    
    if match:
        part1 = match.group(1)
        part2 = match.group(2)
        part3 = match.group(3).lstrip('0') or '0'  # Remove leading zeros but keep at least one digit
        return f"{part1}.{part2}-{part3}"
    
    return None

class ClauseComparisonRequest(BaseModel):
    """Request to compare FAR/DFARS clauses with Agiloft KB"""
    config: AgiloftConfig
    clause_type: Optional[str] = None  # "FAR", "DFARS", or None for all
    source: str = "acquisition_gov"  # "acquisition_gov" or "local_db"

class ClauseComparisonResult(BaseModel):
    """Result of clause comparison"""
    total_local_clauses: int
    total_agiloft_clauses: int
    missing_in_agiloft: List[Dict[str, Any]]
    missing_in_local: List[Dict[str, Any]]
    matched_clauses: List[Dict[str, Any]]

@agiloft_router.post("/compare-clauses")
async def compare_clauses_with_agiloft(comparison_request: ClauseComparisonRequest, request: Request):
    """Compare FAR/DFARS clauses between acquisition.gov and Agiloft KB
    
    This identifies:
    1. Clauses from acquisition.gov missing from Agiloft
    2. Clauses in Agiloft but not in acquisition.gov index  
    3. Matched clauses present in both
    
    Uses the new AgiloftClient with the correct API format:
    POST /clause/search with body {"search": "", "field": ["clause_number"], "query": ""}
    """
    user = await require_auth(request)
    
    config = comparison_request.config
    
    # Check if new modules are available
    if not AGILOFT_CLIENT_AVAILABLE:
        raise HTTPException(status_code=500, detail="Agiloft client module not available")
    
    # Step 1: Get source clauses (acquisition.gov or local DB)
    source_clauses = []
    source_name = "acquisition.gov"
    
    if comparison_request.source == "local_db":
        # Use local database
        local_filter = {}
        if comparison_request.clause_type:
            local_filter["type"] = comparison_request.clause_type
        source_clauses = await db.clauses.find(local_filter, {"_id": 0}).to_list(1000)
        source_name = "local database"
        
        # Convert to expected format
        for clause in source_clauses:
            if "number" in clause and "clause_number" not in clause:
                clause["clause_number"] = clause["number"]
    else:
        # Fetch from acquisition.gov using the new scraper module
        logger.info("Fetching clause index from acquisition.gov using new scraper...")
        
        # Fetch FAR clauses (Part 52)
        if not comparison_request.clause_type or comparison_request.clause_type == "FAR":
            far_clauses = await scrape_far_clauses()
            logger.info(f"Fetched {len(far_clauses)} FAR clauses from acquisition.gov")
            source_clauses.extend(far_clauses)
        
        # Fetch DFARS clauses (Part 252)
        if not comparison_request.clause_type or comparison_request.clause_type == "DFARS":
            dfars_clauses = await scrape_dfars_clauses()
            logger.info(f"Fetched {len(dfars_clauses)} DFARS clauses from acquisition.gov")
            source_clauses.extend(dfars_clauses)
        
        logger.info(f"Total fetched {len(source_clauses)} clauses from acquisition.gov")
    
    # Build normalized source clause map
    source_clause_map = {}  # normalized_number -> clause
    source_original_numbers = {}  # normalized_number -> original_number
    
    for clause in source_clauses:
        # Use clause_number field from new scraper format
        original_num = clause.get("clause_number", clause.get("number", ""))
        normalized = normalize_clause_id(original_num)
        if normalized:
            source_clause_map[normalized] = clause
            source_original_numbers[normalized] = original_num
    
    source_clause_numbers = set(source_clause_map.keys())
    
    logger.info(f"Source ({source_name}) clauses loaded: {len(source_clauses)}, Normalized unique: {len(source_clause_numbers)}")
    if source_clause_numbers:
        sample = list(source_clause_numbers)[:5]
        logger.info(f"Sample source clause numbers: {sample}")
    
    try:
        # Create new AgiloftClient with the correct API format
        agiloft_config = NewAgiloftConfig(
            kb_url=config.kb_url,
            kb_name=config.kb_name,
            username=config.username,
            password=config.password
        )
        agiloft_client = AgiloftClient(agiloft_config)
        
        # Login to Agiloft
        if not await agiloft_client.login():
            raise HTTPException(status_code=401, detail="Failed to authenticate with Agiloft")
        
        logger.info("Agiloft login successful")
        
        # Get clause numbers using the correct API format:
        # POST /clause/search with body {"search": "", "field": ["clause_number"], "query": ""}
        agiloft_clause_numbers_raw = await agiloft_client.get_clause_numbers()
        logger.info(f"Got {len(agiloft_clause_numbers_raw)} clause numbers from Agiloft")
        
        # Sample for debugging
        sample_agiloft_raw = list(agiloft_clause_numbers_raw)[:10]
        logger.info(f"Sample raw Agiloft clause numbers: {sample_agiloft_raw}")
        
        # Normalize Agiloft clause numbers for comparison
        agiloft_clause_map = {}  # normalized_number -> original_number
        for clause_num in agiloft_clause_numbers_raw:
            normalized = normalize_clause_id(clause_num)
            if normalized:
                agiloft_clause_map[normalized] = clause_num
        
        agiloft_clause_numbers = set(agiloft_clause_map.keys())
        logger.info(f"Normalized Agiloft clause numbers: {len(agiloft_clause_numbers)}")
        
        # Compare using normalized numbers
        matched_numbers = source_clause_numbers.intersection(agiloft_clause_numbers)
        missing_in_agiloft_numbers = source_clause_numbers - agiloft_clause_numbers
        missing_in_source_numbers = agiloft_clause_numbers - source_clause_numbers
        
        logger.info(f"Matched: {len(matched_numbers)}, Missing in Agiloft: {len(missing_in_agiloft_numbers)}, Missing in source: {len(missing_in_source_numbers)}")
        
        # Build result lists
        missing_in_agiloft = []
        for normalized_num in sorted(missing_in_agiloft_numbers):
            clause = source_clause_map.get(normalized_num, {})
            original_num = source_original_numbers.get(normalized_num, normalized_num)
            missing_in_agiloft.append({
                "number": original_num,
                "normalized": normalized_num,
                "title": clause.get("title", ""),
                "type": clause.get("type", ""),
                "flowdown_required": clause.get("flowdown_required", False),
                "source": source_name
            })
        
        missing_in_source = []
        for normalized_num in sorted(missing_in_source_numbers):
            original_num = agiloft_clause_map.get(normalized_num, normalized_num)
            missing_in_source.append({
                "agiloft_id": None,
                "clause_number": original_num,
                "normalized": normalized_num,
                "clause_title": "",
                "note": "In Agiloft but not in acquisition.gov index"
            })
        
        matched_clauses = []
        for normalized_num in sorted(matched_numbers):
            source_clause = source_clause_map.get(normalized_num, {})
            source_original = source_original_numbers.get(normalized_num, normalized_num)
            agiloft_original = agiloft_clause_map.get(normalized_num, "")
            
            matched_clauses.append({
                "number": source_original,
                "normalized": normalized_num,
                "source_title": source_clause.get("title", ""),
                "agiloft_number": agiloft_original,
                "type": source_clause.get("type", "")
            })
        
        return {
            "success": True,
            "source": source_name,
            "total_source_clauses": len(source_clauses),
            "total_agiloft_clauses": len(agiloft_clause_numbers_raw),
            "missing_in_agiloft": missing_in_agiloft,
            "missing_in_agiloft_count": len(missing_in_agiloft),
            "missing_in_source": missing_in_source,
            "missing_in_source_count": len(missing_in_source),
            # Keep old key names for frontend compatibility
            "missing_in_local": missing_in_source,
            "missing_in_local_count": len(missing_in_source),
            "matched_clauses": matched_clauses,
            "matched_count": len(matched_clauses),
            "debug": {
                "source_normalized_count": len(source_clause_numbers),
                "agiloft_normalized_count": len(agiloft_clause_numbers),
                "agiloft_raw_count": len(agiloft_clause_numbers_raw),
                "sample_source_numbers": list(source_clause_numbers)[:5],
                "sample_agiloft_numbers": list(agiloft_clause_numbers)[:5],
                "sample_agiloft_raw": sample_agiloft_raw,
                "normalization_note": "Using new AgiloftClient with POST /clause/search and field: ['clause_number']"
            }
        }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Clause comparison error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Comparison failed: {str(e)}")

class UploadMissingClausesRequest(BaseModel):
    """Request to upload missing clauses to Agiloft"""
    config: AgiloftConfig
    clause_numbers: List[str]  # List of clause numbers to upload
    fetch_fresh: bool = False  # Whether to fetch fresh from acquisition.gov

@agiloft_router.post("/upload-missing-clauses")
async def upload_missing_clauses_to_agiloft(upload_request: UploadMissingClausesRequest, request: Request):
    """Upload specified missing clauses to Agiloft KB using POST /clause endpoint.
    
    This endpoint:
    1. Takes a list of clause numbers identified as missing in Agiloft
    2. Fetches full clause data from acquisition.gov (using HTTP, not Playwright)
    3. Creates the clauses in Agiloft using POST /clause with required fields
    
    Required fields for POST /clause: clause_number, clause_title, clause_text, clause_date
    """
    user = await require_auth(request)
    
    config = upload_request.config
    clauses_to_upload = []
    skipped_clauses = []
    
    logger.info(f"=== UPLOAD MISSING CLAUSES REQUEST ===")
    logger.info(f"Requested clauses: {upload_request.clause_numbers}")
    
    for clause_number in upload_request.clause_numbers:
        # Skip "Reserved" clauses - they are empty placeholders
        if "reserved" in clause_number.lower():
            skipped_clauses.append(f"{clause_number}: Skipped - Reserved clause")
            logger.info(f"Skipping reserved clause: {clause_number}")
            continue
        
        # Always fetch fresh from acquisition.gov for uploads
        logger.info(f"Fetching {clause_number} from acquisition.gov...")
        try:
            clause_data = await fetch_clause_from_acquisition_gov(clause_number)
            
            if clause_data:
                clause_title = clause_data.get("title", "")
                clause_text = clause_data.get("text", "")
                
                # Fetch DITA XML for proper formatting in Agiloft
                dita_content = await fetch_clause_dita_from_acquisition_gov(clause_number)
                if dita_content:
                    clause_data["dita_text"] = dita_content
                    logger.info(f"Got DITA content for {clause_number}: {len(dita_content)} chars")
                else:
                    # Fallback to HTML if DITA not available
                    html_text = await fetch_clause_html_from_acquisition_gov(clause_number)
                    if html_text:
                        clause_data["html_text"] = html_text
                
                # Skip if title or text contains "Reserved"
                if "reserved" in clause_title.lower() or "[reserved]" in clause_text.lower():
                    skipped_clauses.append(f"{clause_number}: Skipped - Reserved clause (from acquisition.gov)")
                    logger.info(f"Skipping {clause_number} - Reserved clause detected in content")
                    continue
                
                # Skip if text is too short (likely not real content)
                if len(clause_text) < 100:
                    skipped_clauses.append(f"{clause_number}: Skipped - Text too short ({len(clause_text)} chars)")
                    logger.info(f"Skipping {clause_number} - Text too short: {len(clause_text)} chars")
                    continue
                
                clauses_to_upload.append(clause_data)
                logger.info(f"Fetched {clause_number}: title='{clause_title[:50]}...', text={len(clause_text)} chars")
            else:
                skipped_clauses.append(f"{clause_number}: Could not fetch from acquisition.gov")
                logger.warning(f"Could not fetch {clause_number} from acquisition.gov")
        except Exception as e:
            skipped_clauses.append(f"{clause_number}: Error - {str(e)}")
            logger.error(f"Error fetching {clause_number}: {e}")
    
    if not clauses_to_upload:
        return {
            "success": False,
            "message": "No valid clauses to upload",
            "uploaded": 0,
            "skipped": skipped_clauses,
            "errors": []
        }
    
    try:
        # Check if new modules are available
        if not AGILOFT_CLIENT_AVAILABLE:
            raise HTTPException(status_code=500, detail="Agiloft client module not available")
        
        # Create new AgiloftClient with the correct API format
        agiloft_config = NewAgiloftConfig(
            kb_url=config.kb_url,
            kb_name=config.kb_name,
            username=config.username,
            password=config.password
        )
        agiloft_client = AgiloftClient(agiloft_config)
        
        # Login to Agiloft
        if not await agiloft_client.login():
            raise HTTPException(status_code=401, detail="Failed to authenticate with Agiloft")
        
        logger.info("Agiloft login successful for upload")
        
        uploaded_count = 0
        errors_list = []
        
        from datetime import datetime
        
        # Helper to extract date string from clause title (e.g., "(May 2014)" -> "MAY 2014")
        def extract_clause_date(title: str, text: str) -> str:
            """Extract date from clause title or text in original format (e.g., 'MAY 2014')."""
            import re
            
            # Pattern to find date like "(May 2014)" or "(JUN 2020)"
            date_pattern = r'\(?\s*([A-Za-z]{3,9})\s+(\d{4})\s*\)?'
            
            for source in [title, text]:
                match = re.search(date_pattern, source)
                if match:
                    month_str = match.group(1).upper()  # Convert to uppercase
                    year = match.group(2)
                    return f"{month_str} {year}"
            
            # Fallback if no date found - return current month/year
            now = datetime.now()
            return now.strftime("%b %Y").upper()
        
        # Agiloft automatically derives Clause Type from Clause Number via internal rules
        # DO NOT send: clause_type, clause_type_id, clause_to_clause_type, or any type fields
        
        for clause in clauses_to_upload:
            clause_number = clause.get('number', '')
            clause_title = clause.get('title', f"Clause {clause_number}")
            # Priority: DITA XML > HTML > Plain text
            clause_text = clause.get('dita_text') or clause.get('html_text') or clause.get('text', '')
            
            # Extract clause date from title or text (e.g., "MAY 2014")
            extracted_date = extract_clause_date(clause_title, clause.get('text', ''))
            
            # Build payload with ONLY core fields - Agiloft handles classification
            agiloft_payload = {
                "clause_number": clause_number,
                "clause_title": clause_title,
                "clause_text": clause_text,
                "clause_date": extracted_date
            }
            
            # Log which format is being used
            text_format = "DITA" if clause.get('dita_text') else ("HTML" if clause.get('html_text') else "Plain")
            
            logger.info(f"=== UPLOADING {clause_number} ===")
            logger.info(f"Payload keys: {list(agiloft_payload.keys())}")
            logger.info(f"Title: {clause_title[:80]}...")
            logger.info(f"Text length: {len(clause_text)} chars")
            logger.info(f"Text format: {text_format}")
            logger.info(f"Date: {extracted_date}")
            
            try:
                # Use create_clause to POST to /clause endpoint
                result = await agiloft_client.create_clause(agiloft_payload)
                
                if result.get("success"):
                    uploaded_count += 1
                    logger.info(f"SUCCESS: Uploaded {clause_number}")
                else:
                    # Capture FULL Agiloft error details
                    error_msg = result.get("error", "Unknown error")
                    agiloft_status = result.get("agiloft_status", "N/A")
                    agiloft_response = result.get("agiloft_response", "")
                    
                    error_entry = {
                        "clause_number": clause_number,
                        "error": error_msg,
                        "agiloft_status": agiloft_status,
                        "agiloft_response": agiloft_response
                    }
                    errors_list.append(error_entry)
                    
                    # Log full error to stderr
                    import sys
                    print(f"UPLOAD FAILED for {clause_number}:", file=sys.stderr)
                    print(f"  Error: {error_msg}", file=sys.stderr)
                    print(f"  Agiloft Status: {agiloft_status}", file=sys.stderr)
                    print(f"  Agiloft Response: {agiloft_response}", file=sys.stderr)
                    
                    logger.error(f"FAILED: {clause_number} - {error_msg}")
                    logger.error(f"Agiloft Status: {agiloft_status}")
                    logger.error(f"Agiloft Response: {agiloft_response}")
            except Exception as e:
                import traceback
                tb = traceback.format_exc()
                errors_list.append({
                    "clause_number": clause_number,
                    "error": str(e),
                    "traceback": tb
                })
                logger.error(f"EXCEPTION uploading {clause_number}: {e}")
                print(f"EXCEPTION uploading {clause_number}: {e}\n{tb}", file=sys.stderr)
        
        return {
            "success": uploaded_count > 0,
            "message": f"Uploaded {uploaded_count} of {len(clauses_to_upload)} clauses to Agiloft",
            "uploaded": uploaded_count,
            "total_requested": len(upload_request.clause_numbers),
            "total_valid": len(clauses_to_upload),
            "skipped": skipped_clauses,
            "errors": errors_list  # Now contains full Agiloft error details
        }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload to Agiloft error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

# ==================== Batch Export Routes ====================

class BatchExportRequest(BaseModel):
    """Request for batch export"""
    clause_numbers: List[str] = []
    clause_ids: List[str] = []
    include_full_text: bool = True
    include_flowdown_info: bool = True
    format: str = "pdf"  # pdf, json, csv

@export_router.post("/batch")
async def batch_export(export_request: BatchExportRequest, request: Request):
    """Batch export multiple clauses to PDF, JSON, or CSV"""
    user = await require_auth(request)

    clause_docs = []

    for clause_num in export_request.clause_numbers:
        clause = await db.clauses.find_one({"number": clause_num}, {"_id": 0})
        
        # If include_full_text is requested and clause is missing or has only summary text, fetch from acquisition.gov
        # Short text (<1000 chars) likely indicates it's just a summary
        text = clause.get("text", "") if clause else ""
        needs_fetch = (
            not clause or 
            not text or 
            len(text) < 1000 or
            text.startswith("Full text available") or
            text.startswith("See acquisition.gov") or
            text.startswith("This clause")  # Summary pattern
        )
        
        if export_request.include_full_text and needs_fetch:
            try:
                logger.info(f"Fetching full text for {clause_num} from acquisition.gov (existing text: {len(text)} chars)...")
                live_clause = await fetch_clause_from_acquisition_gov(clause_num)
                if live_clause and live_clause.get("text") and len(live_clause.get("text", "")) > len(text):
                    if clause:
                        clause["text"] = live_clause.get("text", "")
                    else:
                        clause = live_clause
                    # Cache the fetched text
                    await db.clauses.update_one(
                        {"number": clause_num},
                        {"$set": {"text": live_clause.get("text", ""), "title": live_clause.get("title", clause.get("title", ""))}},
                        upsert=True
                    )
                    logger.info(f"Updated {clause_num} with {len(live_clause.get('text', ''))} chars of full text")
            except Exception as e:
                logger.warning(f"Failed to fetch clause {clause_num}: {e}")
        
        if clause:
            clause_docs.append(clause)

    for clause_id in export_request.clause_ids:
        clause = await db.clauses.find_one({"clause_id": clause_id}, {"_id": 0})
        
        # If include_full_text is requested and clause is missing or has only summary text, fetch from acquisition.gov
        if clause:
            text = clause.get("text", "")
            needs_fetch = (
                not text or 
                len(text) < 1000 or
                text.startswith("Full text available") or
                text.startswith("See acquisition.gov") or
                text.startswith("This clause")
            )
            
            if export_request.include_full_text and needs_fetch:
                clause_num = clause.get("number")
                if clause_num:
                    try:
                        logger.info(f"Fetching full text for {clause_num} from acquisition.gov...")
                        live_clause = await fetch_clause_from_acquisition_gov(clause_num)
                        if live_clause and live_clause.get("text") and len(live_clause.get("text", "")) > len(text):
                            clause["text"] = live_clause.get("text", "")
                            # Cache the fetched text
                            await db.clauses.update_one(
                                {"clause_id": clause_id},
                                {"$set": {"text": live_clause.get("text", "")}}
                            )
                    except Exception as e:
                        logger.warning(f"Failed to fetch clause {clause_num}: {e}")
        
        if clause and clause not in clause_docs:
            clause_docs.append(clause)

    if not clause_docs:
        raise HTTPException(status_code=404, detail="No clauses found for export")

    if export_request.format == "json":
        return {
            "export_date": datetime.now(timezone.utc).isoformat(),
            "total_clauses": len(clause_docs),
            "clauses": clause_docs
        }

    elif export_request.format == "csv":
        import csv

        buffer = io.StringIO()
        writer = csv.writer(buffer)

        headers = ["Number", "Title", "Type", "Flowdown Required"]
        if export_request.include_full_text:
            headers.append("Text")
        writer.writerow(headers)

        for clause in clause_docs:
            row = [
                clause.get("number", ""),
                clause.get("title", ""),
                clause.get("type", ""),
                "Yes" if clause.get("flowdown_required") else "No"
            ]
            if export_request.include_full_text:
                row.append(clause.get("text", "")[:5000])
            writer.writerow(row)

        csv_content = buffer.getvalue()

        return StreamingResponse(
            io.BytesIO(csv_content.encode('utf-8')),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=clauses_export.csv"}
        )

    else:
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=72,
            leftMargin=72,
            topMargin=72,
            bottomMargin=72
        )
        styles = getSampleStyleSheet()
        
        # Import styles for proper formatting (same as single clause export)
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.enums import TA_LEFT, TA_JUSTIFY, TA_CENTER

        title_style = styles['Title']
        heading_style = styles['Heading2']
        normal_style = styles['Normal']
        
        # Style for clause titles (centered) - same as single export
        title_centered_style = ParagraphStyle(
            'TitleCentered',
            parent=styles['Heading2'],
            alignment=TA_CENTER,
            spaceBefore=15,
            spaceAfter=10
        )
        
        # Indent styles for different list levels with hanging indent
        indent_styles = {}
        for level in range(5):
            indent_styles[level] = ParagraphStyle(
                f'BatchIndent{level}',
                parent=styles['Normal'],
                leftIndent=level * 25 + (15 if level > 0 else 0),
                firstLineIndent=-15 if level > 0 else 0,
                spaceBefore=3,
                spaceAfter=3,
                alignment=TA_JUSTIFY,
                fontSize=10
            )
        
        # Centered style for "(End of clause)" and clause titles
        centered_style = ParagraphStyle(
            'BatchCentered',
            parent=styles['Normal'],
            alignment=TA_CENTER,
            spaceBefore=15,
            spaceAfter=15,
        )

        story = []

        story.append(Paragraph("Federal Clause Export Report", title_style))
        story.append(Spacer(1, 0.3*inch))
        story.append(Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", normal_style))
        story.append(Paragraph(f"Total Clauses: {len(clause_docs)}", normal_style))
        story.append(Paragraph(f"Exported by: {user.name}", normal_style))
        story.append(Spacer(1, 0.5*inch))

        story.append(Paragraph("Table of Contents", heading_style))
        story.append(Spacer(1, 0.2*inch))
        for i, clause in enumerate(clause_docs, 1):
            story.append(Paragraph(f"{i}. {clause.get('number', 'N/A')} - {clause.get('title', 'Untitled')}", normal_style))
        story.append(Spacer(1, 0.5*inch))

        for clause in clause_docs:
            # Clause number and title - CENTERED like single export
            clause_title = f"{clause.get('number', 'N/A')}: {clause.get('title', 'Untitled')}"
            story.append(Paragraph(clause_title, title_centered_style))
            story.append(Spacer(1, 0.1*inch))

            story.append(Paragraph(f"<b>Type:</b> {clause.get('type', 'N/A')}", normal_style))

            if export_request.include_flowdown_info:
                flowdown = "Yes" if clause.get('flowdown_required') else "No"
                story.append(Paragraph(f"<b>Flowdown Required:</b> {flowdown}", normal_style))

                if clause.get('threshold_amount'):
                    story.append(Paragraph(f"<b>Threshold:</b> ${clause['threshold_amount']:,.0f}", normal_style))

                if clause.get('contract_types'):
                    story.append(Paragraph(f"<b>Contract Types:</b> {', '.join(clause['contract_types'])}", normal_style))

            if clause.get('source'):
                story.append(Paragraph(f"<b>Source:</b> {clause['source']}", normal_style))

            story.append(Spacer(1, 0.2*inch))

            if clause.get('summary'):
                story.append(Paragraph("<b>Summary:</b>", normal_style))
                story.append(Paragraph(clause['summary'], normal_style))
                story.append(Spacer(1, 0.1*inch))

            # Full Text with DITA formatting - SAME as single clause export
            if export_request.include_full_text:
                story.append(Paragraph("<b>Full Text:</b>", normal_style))
                
                # Fetch formatted HTML from acquisition.gov (same as single export)
                clause_num = clause.get('number')
                formatted_text = None
                
                try:
                    html_content = await fetch_clause_html_from_acquisition_gov(clause_num)
                    if html_content:
                        formatted_text = html_content
                    else:
                        # Fallback to DITA with normalization
                        dita_content = await fetch_clause_dita_from_acquisition_gov(clause_num)
                        if dita_content:
                            formatted_text = _normalize_clause_indent_html(dita_content)
                except Exception as e:
                    logger.warning(f"Failed to fetch formatted content for {clause_num}: {e}")
                
                if formatted_text:
                    # Parse DITA/HTML and extract text with indentation - SAME as single export
                    text_paragraphs = _extract_pdf_paragraphs_from_dita(formatted_text)
                    for para_data in text_paragraphs:
                        para_text = para_data[0]
                        level = para_data[1]
                        is_centered = para_data[2] if len(para_data) > 2 else False
                        
                        if para_text.strip():
                            # Escape special characters for ReportLab
                            safe_text = para_text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                            
                            # Use centered style for titles and "(End of clause)" markers
                            if is_centered:
                                story.append(Paragraph(safe_text, centered_style))
                            else:
                                style = indent_styles.get(min(level, 4), indent_styles[0])
                                story.append(Paragraph(safe_text, style))
                elif clause.get('text'):
                    # Fallback to raw text if formatted not available
                    text = clause['text'][:10000]
                    for para in text.split('\n\n'):
                        if para.strip():
                            story.append(Paragraph(para.strip(), normal_style))
                            story.append(Spacer(1, 0.1*inch))

            if clause.get('keywords'):
                story.append(Paragraph(f"<b>Keywords:</b> {', '.join(clause['keywords'])}", normal_style))

            story.append(Spacer(1, 0.4*inch))

        doc.build(story)
        buffer.seek(0)

        filename = f"clause_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"

        return StreamingResponse(
            buffer,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

class FlowdownReportRequest(BaseModel):
    """Request for flowdown report"""
    contract_type: str
    contract_value: float
    clauses: List[str]

@export_router.post("/flowdown-report")
async def export_flowdown_report(report_request: FlowdownReportRequest, request: Request):
    """Export a flowdown analysis report as PDF"""
    user = await require_auth(request)

    contract_type = report_request.contract_type
    contract_value = report_request.contract_value
    clauses = report_request.clauses

    flowdown_clauses = await db.clauses.find(
        {"flowdown_required": True},
        {"_id": 0}
    ).to_list(100)

    applicable = []
    for clause in flowdown_clauses:
        threshold = clause.get("threshold_amount", 0) or 0
        contract_types = clause.get("contract_types", [])

        if contract_value >= threshold:
            if "All" in contract_types or contract_type in contract_types or not contract_types:
                applicable.append(clause)

    present = [c for c in applicable if c["number"] in clauses]
    missing = [c for c in applicable if c["number"] not in clauses]

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph("Flowdown Analysis Report", styles['Title']))
    story.append(Spacer(1, 0.3*inch))
    story.append(Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}", styles['Normal']))
    story.append(Paragraph(f"Contract Type: {contract_type}", styles['Normal']))
    story.append(Paragraph(f"Contract Value: ${contract_value:,.2f}", styles['Normal']))
    story.append(Spacer(1, 0.5*inch))

    story.append(Paragraph("Summary", styles['Heading2']))
    story.append(Paragraph(f"Total Required Flowdown Clauses: {len(applicable)}", styles['Normal']))
    story.append(Paragraph(f"Present in Contract: {len(present)}", styles['Normal']))
    story.append(Paragraph(f"Missing from Contract: {len(missing)}", styles['Normal']))
    story.append(Spacer(1, 0.3*inch))

    if missing:
        story.append(Paragraph("MISSING CLAUSES (Action Required)", styles['Heading2']))
        for clause in missing:
            story.append(Paragraph(f"• {clause['number']}: {clause['title']}", styles['Normal']))
        story.append(Spacer(1, 0.3*inch))

    if present:
        story.append(Paragraph("Compliant Clauses", styles['Heading2']))
        for clause in present:
            story.append(Paragraph(f"✓ {clause['number']}: {clause['title']}", styles['Normal']))

    doc.build(story)
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=flowdown_report.pdf"}
    )


# ==================== Agiloft Contract Clause Upload Endpoints ====================

@agiloft_router.post("/upload-and-extract")
async def agiloft_upload_and_extract(request: Request, file: UploadFile = File(...)):
    """
    Upload a PDF/document and extract clauses for Agiloft linking.
    Returns the filtered clause list (same logic as JSON export).
    """
    user = await require_auth(request)

    content = await file.read()
    text_content = ""

    if file.filename.endswith('.pdf'):
        try:
            import pdfplumber

            def decode_cid_text(text: str) -> str:
                cid_map = {
                    '(cid:15)': '5', '(cid:12)': '2', '(cid:8)': '.',
                    '(cid:11)': '1', '(cid:7)': '-', '(cid:14)': '4',
                    '(cid:13)': '3', '(cid:16)': '6', '(cid:17)': '7',
                    '(cid:18)': '8', '(cid:19)': '9', '(cid:10)': '0',
                    '(cid:20)': '0', '(cid:21)': '1', '(cid:22)': '2',
                    '(cid:23)': '3', '(cid:24)': '4', '(cid:25)': '5',
                    '(cid:26)': '6', '(cid:27)': '7', '(cid:28)': '8',
                    '(cid:29)': '9',
                }
                for cid, char in cid_map.items():
                    text = text.replace(cid, char)
                text = re.sub(r'\(cid:\d+\)', '', text)
                return text

            with pdfplumber.open(io.BytesIO(content)) as pdf:
                all_text = []
                for page in pdf.pages:
                    page_text = page.extract_text() or ""
                    page_text = decode_cid_text(page_text)
                    all_text.append(page_text)
                    tables = page.extract_tables()
                    for table in tables:
                        if table:
                            for row in table:
                                if row:
                                    row_text = " ".join([str(cell) if cell else "" for cell in row])
                                    row_text = decode_cid_text(row_text)
                                    if row_text.strip():
                                        all_text.append(row_text)
                text_content = "\n".join(all_text)
        except Exception as e:
            logger.error(f"PDF extraction error: {e}")
            text_content = content.decode('utf-8', errors='ignore')
    else:
        text_content = content.decode('utf-8', errors='ignore')

    # Detect clause headers
    clauses_found = _detect_clause_headers(text_content)
    logger.info(f"Agiloft upload: detected {len(clauses_found)} clause headers")

    # Run the same extraction logic as JSON export
    extraction_result = _extract_clauses_with_checkboxes(text_content)

    detected_clauses_set = set(clauses_found)
    extracted_numbers = {c["number"] for c in extraction_result["top_level_clauses"]}
    for clause_num in detected_clauses_set:
        if clause_num not in extracted_numbers:
            extraction_result["top_level_clauses"].append({
                "number": clause_num, "title": "", "is_selected": True, "source_line": ""
            })

    # Extract date helper
    def _extract_date(text):
        if not text:
            return ""
        search_text = text[:600]
        month_pattern = r'(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)'
        date_match = re.search(rf'\(\s*({month_pattern})\s+(\d{{4}})\s*\)', search_text)
        return f"{date_match.group(1)} {date_match.group(2)}" if date_match else ""

    selected_sub_nums = {c["number"] for c in extraction_result["selected_sub_clauses"]}
    unselected_sub_nums = {c["number"] for c in extraction_result.get("unselected_sub_clauses", [])}

    parent_selected_map = {}
    for parent_num, data in extraction_result.get("parent_clauses_with_selections", {}).items():
        if data.get("selected_sub_clauses"):
            parent_selected_map[parent_num] = data["selected_sub_clauses"]

    filtered_clauses = []
    seen_numbers = set()

    # 1. Parent clauses with selected sub-clauses
    if "checkbox_list" in parent_selected_map:
        selected_subs = parent_selected_map["checkbox_list"]
        parent_clause_patterns = ['52.212-5', '52.212-4', '52.244-6', '252.212-7001', '252.212-7000']
        for potential_parent in parent_clause_patterns:
            if potential_parent in detected_clauses_set and potential_parent not in selected_sub_nums:
                seen_numbers.add(potential_parent)
                db_clause = await db.clauses.find_one({"number": potential_parent}, {"_id": 0})
                sub_details = []
                for sub in selected_subs:
                    sub_db = await db.clauses.find_one({"number": sub["number"]}, {"_id": 0})
                    sub_title = sub_db.get("title", sub.get("title", "")) if sub_db else sub.get("title", "")
                    date_match = re.search(r'\(([A-Z][a-z]{2}\s+\d{4})\)', sub.get("source_line", ""))
                    sub_date = f" ({date_match.group(1)})" if date_match else ""
                    sub_details.append({"number": sub["number"], "title": sub_title, "date": sub_date.strip(" ()")})
                filtered_clauses.append({
                    "number": potential_parent,
                    "type": "FAR" if potential_parent.startswith("52.") else "DFARS",
                    "title": db_clause.get("title", "") if db_clause else "",
                    "date": _extract_date(db_clause.get("text", "")) if db_clause else "",
                    "is_parent": True,
                    "selected_sub_clauses": sub_details,
                })
                break

    # 2. Selected sub-clauses
    for clause in extraction_result["selected_sub_clauses"]:
        if clause["number"] in seen_numbers:
            continue
        seen_numbers.add(clause["number"])
        db_clause = await db.clauses.find_one({"number": clause["number"]}, {"_id": 0})
        clause_title = db_clause.get("title", clause.get("title", "")) if db_clause else clause.get("title", "")
        clause_text = db_clause.get("text", "") if db_clause else ""
        date_match = re.search(r'\(([A-Z][a-z]{2}\s+\d{4})\)', clause.get("source_line", ""))
        clause_date = date_match.group(1) if date_match else _extract_date(clause_text)
        filtered_clauses.append({
            "number": clause["number"],
            "type": "FAR" if clause["number"].startswith("52.") else "DFARS",
            "title": clause_title,
            "date": clause_date,
            "is_parent": False,
            "selected_sub_clauses": [],
        })

    # 3. Other detected clauses (standalone, not unselected)
    for clause_num in clauses_found:
        if clause_num in seen_numbers or clause_num in unselected_sub_nums:
            continue
        seen_numbers.add(clause_num)
        db_clause = await db.clauses.find_one({"number": clause_num}, {"_id": 0})
        clause_title = db_clause.get("title", "") if db_clause else ""
        clause_text = db_clause.get("text", "") if db_clause else ""
        filtered_clauses.append({
            "number": clause_num,
            "type": "FAR" if clause_num.startswith("52.") else "DFARS",
            "title": clause_title,
            "date": _extract_date(clause_text),
            "is_parent": False,
            "selected_sub_clauses": [],
        })

    return {
        "success": True,
        "filename": file.filename,
        "total_detected": len(clauses_found),
        "total_filtered": len(filtered_clauses),
        "clauses": filtered_clauses,
    }


class VerifyLibraryRequest(BaseModel):
    config: AgiloftConfig
    clause_numbers: List[str]

@agiloft_router.post("/verify-library-clauses")
async def verify_library_clauses(verify_request: VerifyLibraryRequest, request: Request):
    """
    Check which clause numbers exist in the Agiloft Clause Library.
    Returns found (with IDs) and missing lists.
    """
    user = await require_auth(request)
    config = verify_request.config

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            login_data = await agiloft_login(client, config)
            token = login_data.get("access_token")
            if not token:
                raise HTTPException(status_code=401, detail="Authentication failed")

            auth_headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}"
            }

            # Fetch all clause numbers from Agiloft library
            search_url = _build_agiloft_url(config.kb_url, config.kb_name, "clause/search")
            search_payload = {
                "search": "",
                "field": ["clause_number", "id"],
                "query": ""
            }

            response = await client.post(
                search_url,
                params={"lang": "en"},
                json=search_payload,
                headers=auth_headers
            )

            agiloft_clauses = {}
            if response.status_code == 200:
                data = response.json()
                result = data.get("result", [])
                if isinstance(result, list):
                    for record in result:
                        cn = str(record.get("clause_number", "")).strip()
                        cid = record.get("id", record.get("$id"))
                        if cn:
                            agiloft_clauses[cn] = cid

            logger.info(f"Agiloft library has {len(agiloft_clauses)} clauses")

            found = []
            missing = []
            for num in verify_request.clause_numbers:
                if num in agiloft_clauses:
                    found.append({"number": num, "agiloft_id": agiloft_clauses[num]})
                else:
                    missing.append({"number": num})

            return {
                "success": True,
                "total_checked": len(verify_request.clause_numbers),
                "found_count": len(found),
                "missing_count": len(missing),
                "found": found,
                "missing": missing,
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Verify library error: {e}")
        return {"success": False, "message": str(e)}


class LinkClausesRequest(BaseModel):
    config: AgiloftConfig
    contract_id: str
    clause_ids: List[int]  # Agiloft Clause Library record IDs
    clause_numbers: List[str]  # For logging/display
    clause_titles: List[str] = []  # Optional titles

@agiloft_router.post("/link-clauses-to-contract")
async def link_clauses_to_contract(link_request: LinkClausesRequest, request: Request):
    """
    Link clauses to a contract by creating records in the contract_clause_modification table.
    """
    user = await require_auth(request)
    config = link_request.config
    TABLE_NAME = "contract_clause_modification"

    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            login_data = await agiloft_login(client, config)
            token = login_data.get("access_token")
            if not token:
                raise HTTPException(status_code=401, detail="Authentication failed")

            auth_headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}"
            }

            contract_id_int = int(link_request.contract_id)

            # Step 1: Discover actual field names by fetching an existing record
            search_url = _build_agiloft_url(config.kb_url, config.kb_name, f"{TABLE_NAME}/search")
            field_names = []
            sample_record = None
            try:
                search_resp = await client.post(
                    search_url,
                    params={"lang": "en"},
                    json={"search": "", "numberOfRows": 1},
                    headers=auth_headers
                )
                logger.info(f"Field discovery response: {search_resp.status_code}")
                if search_resp.status_code == 200:
                    search_data = search_resp.json()
                    results = search_data.get("result", [])
                    if isinstance(results, list) and results:
                        sample_record = results[0]
                        field_names = list(sample_record.keys())
                        logger.info(f"Discovered {len(field_names)} fields: {field_names}")
            except Exception as e:
                logger.warning(f"Field discovery error: {e}")

            # Step 2: Identify linked fields from discovered field names
            # Agiloft linked fields follow pattern: {table_name}_to_{target_table}
            # or {table_name}_go_{target_table}
            contract_link_field = "contract_clause_modification_to_contract"  # Known from error messages
            clause_lib_field = None

            if field_names:
                # Verify / find the contract link field
                for f in field_names:
                    fl = f.lower()
                    if ("_to_contract" in fl or "_go_contract" in fl) and "contract_clause" in fl:
                        contract_link_field = f
                        break

                # Find clause library link field
                # Pattern: contract_clause_modification_to_* with "clause" but NOT "type" or "contract"
                for f in field_names:
                    fl = f.lower()
                    if f.startswith("contract_clause_modification") and ("_to_" in fl or "_go_" in fl):
                        # Skip the contract link and clause_type link
                        if "_to_contract" in fl or "_go_contract" in fl:
                            continue
                        if "clause_type" in fl or "type" in fl:
                            continue
                        # This should be the clause library link
                        clause_lib_field = f
                        break

                if not clause_lib_field:
                    # Broader search
                    for f in field_names:
                        fl = f.lower()
                        if "clause" in fl and "library" in fl and "type" not in fl:
                            clause_lib_field = f
                            break

            logger.info(f"Contract link field: {contract_link_field}")
            logger.info(f"Clause library link field: {clause_lib_field}")
            logger.info(f"All discovered fields: {field_names}")

            # Step 3: Create junction records
            create_url = _build_agiloft_url(config.kb_url, config.kb_name, TABLE_NAME)
            linked = []
            failed = []
            working_payload_format = None  # Once we find a format that works, reuse it

            for idx, (clause_id, clause_num) in enumerate(zip(link_request.clause_ids, link_request.clause_numbers)):
                clause_title = link_request.clause_titles[idx] if idx < len(link_request.clause_titles) else clause_num

                if working_payload_format:
                    # Reuse the format that worked for the first clause
                    payload = dict(working_payload_format)
                    # Update clause-specific values
                    for k, v in payload.items():
                        if k != contract_link_field:
                            if isinstance(v, dict) and "id" in v:
                                payload[k] = {"id": int(clause_id)}
                            elif isinstance(v, int):
                                payload[k] = int(clause_id)
                else:
                    # Build payload: linked fields use {"id": X} format only
                    payload = {
                        contract_link_field: {"id": contract_id_int},
                    }
                    if clause_lib_field:
                        payload[clause_lib_field] = {"id": int(clause_id)}

                resp = await client.post(
                    create_url,
                    params={"lang": "en"},
                    json=payload,
                    headers=auth_headers
                )

                if resp.status_code in [200, 201]:
                    if not working_payload_format:
                        working_payload_format = dict(payload)
                    resp_data = resp.json() if resp.text else {}
                    new_id = None
                    if isinstance(resp_data, dict):
                        result = resp_data.get("result", resp_data)
                        new_id = result.get("id") if isinstance(result, dict) else None
                    linked.append({"number": clause_num, "clause_library_id": clause_id, "contract_clause_id": new_id})
                    logger.info(f"Linked {clause_num} (lib_id={clause_id}) to contract {contract_id_int}")
                else:
                    error_text = resp.text[:500]
                    logger.warning(f"Failed to link {clause_num}: HTTP {resp.status_code} - {error_text}")

                    # On first failure, try alternative payload formats
                    if idx == 0 and not working_payload_format:
                        alt_payloads = []
                        # Try different clause library field names with {"id": X}
                        clause_candidates = [clause_lib_field] if clause_lib_field else []
                        clause_candidates += ["clause_library", "clause", "library_clause",
                                              "contract_clause_modification_to_clause_library",
                                              "contract_clause_modification_to_clause",
                                              "contract_clause_modification_go_clause_library",
                                              "contract_clause_modification_go_clause"]
                        # Remove duplicates and None
                        clause_candidates = list(dict.fromkeys([c for c in clause_candidates if c]))

                        for cc in clause_candidates:
                            alt_payloads.append({
                                contract_link_field: {"id": contract_id_int},
                                cc: {"id": int(clause_id)},
                            })

                        alt_success = False
                        for alt in alt_payloads:
                            alt_resp = await client.post(
                                create_url,
                                params={"lang": "en"},
                                json=alt,
                                headers=auth_headers
                            )
                            logger.info(f"Alt payload {list(alt.keys())}: {alt_resp.status_code} - {alt_resp.text[:300]}")
                            if alt_resp.status_code in [200, 201]:
                                working_payload_format = dict(alt)
                                for k in alt:
                                    if k != contract_link_field:
                                        clause_lib_field = k
                                resp_data = alt_resp.json() if alt_resp.text else {}
                                new_id = None
                                if isinstance(resp_data, dict):
                                    result = resp_data.get("result", resp_data)
                                    new_id = result.get("id") if isinstance(result, dict) else None
                                linked.append({"number": clause_num, "clause_library_id": clause_id, "contract_clause_id": new_id})
                                alt_success = True
                                logger.info(f"Working format found! Clause lib field: {clause_lib_field}")
                                break

                        if not alt_success:
                            failed.append({
                                "number": clause_num,
                                "error": error_text,
                                "available_fields": field_names,
                            })
                    else:
                        failed.append({"number": clause_num, "error": error_text})

            return {
                "success": len(linked) > 0,
                "linked_count": len(linked),
                "failed_count": len(failed),
                "linked": linked,
                "failed": failed,
                "table_used": TABLE_NAME,
                "clause_lib_field": clause_lib_field,
                "message": f"Created {len(linked)} Contract Clause records linking to contract {contract_id_int}" if linked else "Could not create records - check field details in errors",
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Link clauses error: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "message": str(e)}


class CreateAndLinkRequest(BaseModel):
    config: AgiloftConfig
    contract_id: str
    clauses: List[Dict[str, Any]]  # [{number, title, date, type}, ...]

@agiloft_router.post("/create-missing-and-link")
async def create_missing_and_link(create_request: CreateAndLinkRequest, request: Request):
    """
    Create missing clauses in Agiloft Clause Library (with full text from acquisition.gov),
    then link them to the contract.
    """
    user = await require_auth(request)
    config = create_request.config

    try:
        agiloft_client = AgiloftClient(AgiloftConfig(
            kb_url=config.kb_url,
            kb_name=config.kb_name,
            username=config.username,
            password=config.password
        )) if AGILOFT_CLIENT_AVAILABLE else None

        if not agiloft_client:
            return {"success": False, "message": "Agiloft client not available"}

        logged_in = await agiloft_client.login()
        if not logged_in:
            return {"success": False, "message": "Failed to authenticate with Agiloft"}

        created = []
        failed = []

        for clause in create_request.clauses:
            clause_num = clause["number"]
            clause_type = clause.get("type", "FAR" if clause_num.startswith("52.") else "DFARS")

            # Fetch full text from acquisition.gov
            acq_data = await fetch_clause_from_acquisition_gov(clause_num)
            clause_text = acq_data.get("text", "") if acq_data else ""
            clause_title = acq_data.get("title", clause.get("title", "")) if acq_data else clause.get("title", "")
            clause_date = clause.get("date", "")

            # Fetch HTML version for rich text
            html_content = await fetch_clause_html_from_acquisition_gov(clause_num)

            # Build clause data for Agiloft
            clause_data = {
                "clause_number": clause_num,
                "clause_title": clause_title,
                "clause_text": html_content if html_content else clause_text,
            }
            if clause_date:
                clause_data["clause_date"] = clause_date

            # Get clause type ID
            type_id = await agiloft_client.get_clause_type_id(clause_type)
            if type_id:
                clause_data["clause_to_clause_type"] = {"id": type_id}

            result = await agiloft_client.upsert_clause(clause_data, clause_num)

            if result.get("success"):
                new_id = result.get("data", {}).get("result", {}).get("id") if isinstance(result.get("data"), dict) else None
                created.append({"number": clause_num, "agiloft_id": new_id})
            else:
                failed.append({"number": clause_num, "error": result.get("error", "Unknown error")})

        return {
            "success": len(created) > 0,
            "created_count": len(created),
            "failed_count": len(failed),
            "created": created,
            "failed": failed,
            "message": f"Created {len(created)} clauses in Agiloft Library" if created else "Failed to create clauses",
        }

    except Exception as e:
        logger.error(f"Create and link error: {e}")
        return {"success": False, "message": str(e)}


# ==================== Include Routers ====================

# Import the new comparison routes module
try:
    from comparison_routes import comparison_router
    app.include_router(comparison_router)
    logger.info("Comparison routes loaded successfully")
except ImportError as e:
    logger.warning(f"Could not load comparison_routes: {e}")

# Import the new Agiloft client and scraper modules
try:
    from agiloft_client import AgiloftClient, AgiloftConfig as NewAgiloftConfig
    from acqgov_scraper import scrape_far_clauses, scrape_dfars_clauses, normalize_clause_id
    AGILOFT_CLIENT_AVAILABLE = True
    logger.info("Agiloft client module loaded successfully")
except ImportError as e:
    AGILOFT_CLIENT_AVAILABLE = False
    logger.warning(f"Could not load agiloft_client module: {e}")

app.include_router(api_router)
app.include_router(auth_router)
app.include_router(clauses_router)
app.include_router(contracts_router)
app.include_router(flowdown_router)
app.include_router(user_router)
app.include_router(agiloft_router)
app.include_router(export_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    await init_sample_clauses()

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
