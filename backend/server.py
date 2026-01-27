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
        if not api_key:
            logger.warning("EMERGENT_LLM_KEY not found, returning placeholder response")
            return "AI analysis not available - API key not configured."

        chat = LlmChat(
            api_key=api_key,
            session_id=f"clause-analysis-{uuid.uuid4()}",
            system_message=system_message
        ).with_model("openai", "gpt-5.2")

        user_message = UserMessage(text=prompt)
        response = await chat.send_message(user_message)
        return response
    except Exception as e:
        logger.error(f"AI response error: {e}")
        return f"AI analysis temporarily unavailable: {str(e)}"

# ==================== Acquisition.gov Integration ====================

async def fetch_clause_from_acquisition_gov(clause_number: str) -> Optional[Dict[str, Any]]:
    """Fetch clause details from acquisition.gov with full text extraction"""
    try:
        from bs4 import BeautifulSoup
        import re

        # Determine if FAR or DFARS and build the direct clause URL
        if clause_number.startswith("252"):
            # DFARS clause - format: 252.xxx-xxxx
            clause_type = "DFARS"
            # DFARS clauses are at acquisition.gov/dfars/252.xxx-xxxx
            clause_url = f"https://www.acquisition.gov/dfars/{clause_number.lower()}"
        else:
            # FAR clause - format: 52.xxx-xx
            clause_type = "FAR"
            # FAR clauses are at acquisition.gov/far/52.xxx-xx
            clause_url = f"https://www.acquisition.gov/far/{clause_number.lower()}"

        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            # Try direct clause URL first
            response = await client.get(clause_url)

            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')

                # Extract title from page title or h1
                title = ""
                page_title = soup.find('title')
                if page_title:
                    title_text = page_title.get_text().strip()
                    # Remove "FAR" or "DFARS" prefix and clause number
                    title = re.sub(r'^(FAR|DFARS)\s*', '', title_text)
                    title = re.sub(r'^\d+\.\d+-\d+\s*', '', title)
                    title = title.replace('| Acquisition.GOV', '').strip()

                if not title:
                    h1 = soup.find('h1')
                    if h1:
                        title = h1.get_text().strip()
                        title = re.sub(r'^\d+\.\d+-\d+\s*', '', title)

                # Extract full clause text from the main content area
                text_parts = []

                # Look for the main content div
                main_content = soup.find('div', class_='field--name-body') or \
                               soup.find('article') or \
                               soup.find('main') or \
                               soup.find('div', class_='content')

                if main_content:
                    # Get all paragraphs, lists, and text content
                    for elem in main_content.find_all(['p', 'li', 'div', 'span']):
                        text = elem.get_text().strip()
                        if text and len(text) > 10:  # Filter out very short fragments
                            text_parts.append(text)

                # If no main content found, try getting all paragraphs
                if not text_parts:
                    for p in soup.find_all('p'):
                        text = p.get_text().strip()
                        if text and len(text) > 20:
                            text_parts.append(text)

                # Join and clean up text
                full_text = "\n\n".join(text_parts)

                # Remove duplicate lines
                lines = full_text.split('\n')
                seen = set()
                unique_lines = []
                for line in lines:
                    line_clean = line.strip()
                    if line_clean and line_clean not in seen:
                        seen.add(line_clean)
                        unique_lines.append(line)
                full_text = "\n".join(unique_lines)[:50000]  # Limit to 50KB

                # Extract keywords from text
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

                # Determine flowdown requirement (common indicators)
                flowdown_required = bool(re.search(
                    r'flow.?down|subcontract|lower.?tier|prime contractor shall',
                    full_text, re.IGNORECASE
                ))

                return {
                    "clause_id": str(uuid.uuid4()),
                    "number": clause_number,
                    "title": title or f"Clause {clause_number}",
                    "type": clause_type,
                    "text": full_text or f"Content available at: {clause_url}",
                    "summary": None,
                    "flowdown_required": flowdown_required,
                    "contract_types": [],
                    "threshold_amount": None,
                    "keywords": keywords[:10],
                    "last_updated": datetime.now(timezone.utc).isoformat(),
                    "source": "acquisition.gov",
                    "source_url": clause_url
                }

            # If direct URL fails, try the part page
            logger.info(f"Direct URL failed for {clause_number}, trying part page")

        return None
    except Exception as e:
        logger.error(f"Error fetching from acquisition.gov: {e}")
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
async def ai_search_clauses(query: str, request: Request):
    """AI-powered intelligent clause search - ONLY searches indexed acquisition.gov data
    
    This endpoint:
    - Searches ONLY clauses already indexed in our database from acquisition.gov
    - Does NOT generate or fabricate clause text
    - Uses AI to understand query intent and match to relevant existing clauses
    """
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required for AI search")

    # Get all indexed clauses from our database (sourced from acquisition.gov)
    all_clauses = await db.clauses.find(
        {}, 
        {"_id": 0, "clause_id": 1, "number": 1, "title": 1, "type": 1, "summary": 1, "keywords": 1, "text": 1}
    ).to_list(500)
    
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
async def fetch_live_clause(clause_number: str, request: Request):
    """Fetch a clause directly from acquisition.gov and store it"""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required to fetch live data")

    # Check if we already have this clause
    existing = await db.clauses.find_one({"number": clause_number}, {"_id": 0})
    if existing and existing.get("source") == "acquisition.gov":
        return existing

    # Fetch from acquisition.gov
    clause_data = await fetch_clause_from_acquisition_gov(clause_number)

    if clause_data:
        # Store in database
        await db.clauses.update_one(
            {"number": clause_number},
            {"$set": clause_data},
            upsert=True
        )
        return clause_data
    else:
        raise HTTPException(status_code=404, detail=f"Could not fetch clause {clause_number} from acquisition.gov")

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
            with pdfplumber.open(io.BytesIO(content)) as pdf:
                text_content = "\n".join([page.extract_text() or "" for page in pdf.pages])
        except Exception as e:
            logger.error(f"PDF extraction error: {e}")
            text_content = content.decode('utf-8', errors='ignore')
    else:
        text_content = content.decode('utf-8', errors='ignore')

    # Find clause references in the contract
    all_clauses = await db.clauses.find({}, {"_id": 0, "number": 1}).to_list(1000)
    clauses_found = []
    for clause in all_clauses:
        if clause["number"] in text_content:
            clauses_found.append(clause["number"])

    # Create contract record
    contract = Contract(
        user_id=user.user_id,
        name=file.filename,
        filename=file.filename,
        content=text_content[:50000],  # Limit stored content
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
    """Export clauses to PDF with full text"""
    user = await require_auth(request)
    
    # Parse request body
    try:
        body = await request.json()
        clauses = body.get("clauses", [])
    except:
        raise HTTPException(status_code=400, detail="Invalid request body")

    # Get clause details
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
        
        if clause:
            clause_docs.append(clause)

    # Generate PDF
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []

    # Title
    story.append(Paragraph("Federal Clause Report", styles['Title']))
    story.append(Spacer(1, 0.5*inch))
    story.append(Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}", styles['Normal']))
    story.append(Paragraph(f"Exported by: {user.name}", styles['Normal']))
    story.append(Spacer(1, 0.5*inch))

    for clause in clause_docs:
        story.append(Paragraph(f"{clause.get('number', 'N/A')}: {clause.get('title', 'Untitled')}", styles['Heading2']))
        story.append(Paragraph(f"Type: {clause.get('type', 'N/A')}", styles['Normal']))
        story.append(Paragraph(f"Flowdown Required: {'Yes' if clause.get('flowdown_required') else 'No'}", styles['Normal']))
        story.append(Spacer(1, 0.2*inch))
        
        # Include summary if available
        if clause.get('summary'):
            story.append(Paragraph("<b>Summary:</b>", styles['Normal']))
            story.append(Paragraph(clause['summary'], styles['Normal']))
            story.append(Spacer(1, 0.2*inch))
        
        # Include full text
        if clause.get('text'):
            story.append(Paragraph("<b>Full Text:</b>", styles['Normal']))
            # Split text into paragraphs and limit to avoid huge PDFs
            text = clause['text'][:20000]  # Limit to 20000 chars per clause
            for para in text.split('\n\n'):
                if para.strip():
                    # Clean up the paragraph
                    clean_para = para.strip().replace('\n', ' ')
                    story.append(Paragraph(clean_para, styles['Normal']))
                    story.append(Spacer(1, 0.1*inch))
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
    """Upload specified missing clauses from acquisition.gov to Agiloft KB
    
    This endpoint:
    1. Takes a list of clause numbers identified as missing in Agiloft
    2. Fetches fresh data from acquisition.gov if requested
    3. Creates the clauses in Agiloft's clause library using the new AgiloftClient
    """
    user = await require_auth(request)
    
    config = upload_request.config
    clauses_to_upload = []
    
    for clause_number in upload_request.clause_numbers:
        if upload_request.fetch_fresh:
            # Fetch directly from acquisition.gov
            clause_data = await fetch_clause_from_acquisition_gov(clause_number)
            if clause_data:
                clauses_to_upload.append(clause_data)
                # Also update our local database
                await db.clauses.update_one(
                    {"number": clause_number},
                    {"$set": clause_data},
                    upsert=True
                )
        else:
            # Use existing data from our database
            clause = await db.clauses.find_one({"number": clause_number}, {"_id": 0})
            if clause:
                clauses_to_upload.append(clause)
    
    if not clauses_to_upload:
        return {
            "success": False,
            "message": "No clauses found to upload",
            "uploaded": 0,
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
        
        for clause in clauses_to_upload:
            # Map fields to Agiloft format based on OpenAPI spec
            # Fields: clause_number, clause_title, clause_text, clause_type
            agiloft_payload = {
                "clause_number": clause.get('number', ''),  # Critical field for matching
                "clause_title": clause.get('title', ''),  # Just the title, without number prefix
                "clause_text": clause.get("text", "") if clause.get("text") else f"See acquisition.gov for full text of {clause.get('number', '')}",
                "clause_type": clause.get("type", "FAR"),  # FAR or DFARS
            }
            
            # Remove any fields with empty values to avoid API errors
            agiloft_payload = {k: v for k, v in agiloft_payload.items() if v}
            
            try:
                # Use create_clause to POST directly to /clause endpoint
                result = await agiloft_client.create_clause(agiloft_payload)
                
                if result.get("success"):
                    uploaded_count += 1
                    logger.info(f"Successfully uploaded clause {clause.get('number')} to Agiloft (action: {result.get('action', 'unknown')})")
                else:
                    error_msg = result.get("error", "Unknown error")
                    errors_list.append({
                        "clause_number": clause.get("number"),
                        "error": error_msg
                    })
                    logger.error(f"Failed to upload clause {clause.get('number')}: {error_msg}")
            except Exception as e:
                errors_list.append({
                    "clause_number": clause.get("number"),
                    "error": str(e)
                })
                logger.error(f"Exception uploading clause {clause.get('number')}: {e}")
        
        return {
            "success": uploaded_count > 0,
            "message": f"Uploaded {uploaded_count} of {len(clauses_to_upload)} clauses to Agiloft",
            "uploaded": uploaded_count,
            "total_requested": len(clauses_to_upload),
            "errors": errors_list
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
        if clause:
            clause_docs.append(clause)

    for clause_id in export_request.clause_ids:
        clause = await db.clauses.find_one({"clause_id": clause_id}, {"_id": 0})
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

        title_style = styles['Title']
        heading_style = styles['Heading2']
        normal_style = styles['Normal']

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
            story.append(Paragraph(f"{clause.get('number', 'N/A')}", heading_style))
            story.append(Paragraph(f"<b>{clause.get('title', 'Untitled')}</b>", normal_style))
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

            if export_request.include_full_text and clause.get('text'):
                story.append(Paragraph("<b>Full Text:</b>", normal_style))
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
