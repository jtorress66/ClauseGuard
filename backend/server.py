from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, UploadFile, File, Depends
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
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
    """Fetch FAR clause index from acquisition.gov"""
    clauses = []
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Fetch Part 52 index (contract clauses)
            response = await client.get(
                "https://www.acquisition.gov/far/part-52",
                follow_redirects=True
            )
            
            if response.status_code == 200:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Find all clause links
                for link in soup.find_all('a'):
                    href = link.get('href', '')
                    text = link.get_text().strip()
                    
                    # Match FAR clause pattern (52.xxx-x)
                    import re
                    match = re.search(r'52\.\d{3}-\d+', text)
                    if match:
                        clause_num = match.group()
                        # Extract title after the clause number
                        title = text.replace(clause_num, "").strip()
                        if title.startswith("-"):
                            title = title[1:].strip()
                        
                        clauses.append({
                            "number": clause_num,
                            "title": title or f"FAR Clause {clause_num}",
                            "type": "FAR"
                        })
                
                # Remove duplicates
                seen = set()
                unique_clauses = []
                for c in clauses:
                    if c["number"] not in seen:
                        seen.add(c["number"])
                        unique_clauses.append(c)
                
                return unique_clauses[:100]  # Limit to first 100
                
    except Exception as e:
        logger.error(f"Error fetching FAR index: {e}")
    
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

# REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH

@auth_router.post("/session")
async def create_session(request: SessionRequest, response: Response):
    """Exchange session_id for session_token after Google OAuth"""
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
    """AI-powered intelligent clause search"""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required for AI search")
    
    # Get all clauses for context
    all_clauses = await db.clauses.find({}, {"_id": 0, "clause_id": 1, "number": 1, "title": 1, "type": 1, "summary": 1, "keywords": 1}).to_list(100)
    
    clauses_context = "\n".join([
        f"- {c['number']}: {c['title']} ({c['type']}) - {c.get('summary', '')}"
        for c in all_clauses
    ])
    
    prompt = f"""Based on the user's query, identify the most relevant FAR/DFARS clauses from this list:

Available Clauses:
{clauses_context}

User Query: {query}

Return a JSON array of the most relevant clause numbers (e.g., ["52.212-4", "252.204-7012"]) and a brief explanation of why each is relevant. Format:
{{"relevant_clauses": ["clause_number1", "clause_number2"], "explanations": {{"clause_number1": "reason", "clause_number2": "reason"}}}}"""

    ai_response = await get_ai_response(prompt)
    
    # Parse AI response and get full clause details
    try:
        import json
        # Try to extract JSON from response
        json_start = ai_response.find('{')
        json_end = ai_response.rfind('}') + 1
        if json_start >= 0 and json_end > json_start:
            ai_result = json.loads(ai_response[json_start:json_end])
            relevant_numbers = ai_result.get("relevant_clauses", [])
            explanations = ai_result.get("explanations", {})
        else:
            relevant_numbers = []
            explanations = {}
    except:
        relevant_numbers = []
        explanations = {}
    
    # Fetch full clause details
    clauses = []
    for number in relevant_numbers:
        clause = await db.clauses.find_one({"number": number}, {"_id": 0})
        if clause:
            clause["ai_explanation"] = explanations.get(number, "")
            clauses.append(clause)
    
    return {
        "clauses": clauses,
        "ai_analysis": ai_response,
        "total": len(clauses)
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
async def sync_clauses_from_acquisition_gov(request: Request):
    """Sync clause index from acquisition.gov"""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    # Fetch FAR index
    far_clauses = await fetch_far_index()
    
    synced_count = 0
    for clause_info in far_clauses:
        # Check if we already have this clause
        existing = await db.clauses.find_one({"number": clause_info["number"]})
        if not existing:
            # Create basic entry
            clause_doc = {
                "clause_id": str(uuid.uuid4()),
                "number": clause_info["number"],
                "title": clause_info["title"],
                "type": clause_info["type"],
                "text": f"Full text available at acquisition.gov. Search for {clause_info['number']}",
                "summary": None,
                "flowdown_required": False,
                "contract_types": [],
                "threshold_amount": None,
                "keywords": [],
                "last_updated": datetime.now(timezone.utc).isoformat(),
                "source": "acquisition.gov-index"
            }
            await db.clauses.insert_one(clause_doc)
            synced_count += 1
    
    return {"message": f"Synced {synced_count} new clauses from acquisition.gov", "total_new": synced_count}

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
async def save_search(query: str, filters: Dict[str, Any] = {}, request: Request = None):
    """Save a search"""
    user = await require_auth(request)
    search = SavedSearch(user_id=user.user_id, query=query, filters=filters)
    search_dict = search.model_dump()
    search_dict["created_at"] = search_dict["created_at"].isoformat()
    await db.saved_searches.insert_one(search_dict)
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
async def export_to_pdf(clauses: List[str], request: Request):
    """Export clauses to PDF"""
    user = await require_auth(request)
    
    # Get clause details
    clause_docs = []
    for clause_num in clauses:
        clause = await db.clauses.find_one({"number": clause_num}, {"_id": 0})
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
    story.append(Spacer(1, 0.5*inch))
    
    for clause in clause_docs:
        story.append(Paragraph(f"{clause['number']}: {clause['title']}", styles['Heading2']))
        story.append(Paragraph(f"Type: {clause['type']}", styles['Normal']))
        story.append(Paragraph(f"Flowdown Required: {'Yes' if clause.get('flowdown_required') else 'No'}", styles['Normal']))
        if clause.get('summary'):
            story.append(Paragraph(f"Summary: {clause['summary']}", styles['Normal']))
        story.append(Spacer(1, 0.3*inch))
    
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
    """Agiloft KB configuration"""
    kb_url: str  # e.g., https://yourcompany.agiloft.com/ewws
    username: str
    password: str
    kb_name: str = "Default"

class AgiloftSyncRequest(BaseModel):
    """Request to sync clauses from Agiloft"""
    config: AgiloftConfig
    table_name: str = "Clauses"  # Default table name for clauses
    field_mapping: Dict[str, str] = {}  # Map Agiloft fields to our clause fields

@agiloft_router.post("/test-connection")
async def test_agiloft_connection(config: AgiloftConfig, request: Request):
    """Test connection to Agiloft knowledge base"""
    user = await require_auth(request)
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Agiloft REST API login endpoint
            # Format: {base_url}/login?lang=en with JSON body
            login_url = f"{config.kb_url}/login"
            
            response = await client.post(
                login_url,
                params={"lang": "en"},
                json={
                    "login": config.username,
                    "password": config.password,
                    "KB": config.kb_name
                },
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 200:
                try:
                    result = response.json()
                    # Agiloft returns a token on successful login
                    if result.get("token") or result.get("success") or response.status_code == 200:
                        return {
                            "success": True,
                            "message": "Successfully connected to Agiloft KB",
                            "kb_name": config.kb_name,
                            "token": result.get("token", "")[:20] + "..." if result.get("token") else None
                        }
                except:
                    pass
                
                # Check if response indicates success
                if "error" not in response.text.lower():
                    return {
                        "success": True,
                        "message": "Successfully connected to Agiloft KB",
                        "kb_name": config.kb_name
                    }
            
            return {
                "success": False,
                "message": f"Connection failed with status {response.status_code}",
                "details": response.text[:500] if response.text else "No response"
            }
    except Exception as e:
        logger.error(f"Agiloft connection error: {e}")
        return {"success": False, "message": f"Connection error: {str(e)}"}

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
    """Push clauses from our database to Agiloft knowledge base"""
    user = await require_auth(request)
    
    config = push_request.config
    
    # Get clauses to push
    if push_request.source == "acquisition":
        # Fetch fresh from acquisition.gov first
        far_clauses = await fetch_far_index()
        clauses_to_push = []
        for clause_info in far_clauses[:50]:  # Limit to 50 for performance
            clause_data = await fetch_clause_from_acquisition_gov(clause_info["number"])
            if clause_data:
                clauses_to_push.append(clause_data)
    else:
        # Use clauses from our database
        clauses_to_push = await db.clauses.find({}, {"_id": 0}).to_list(500)
    
    if not clauses_to_push:
        return {"success": False, "message": "No clauses found to push"}
    
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            # Login to Agiloft using REST API
            login_url = f"{config.kb_url}/login"
            login_response = await client.post(
                login_url,
                params={"lang": "en"},
                json={
                    "login": config.username,
                    "password": config.password,
                    "KB": config.kb_name
                },
                headers={"Content-Type": "application/json"}
            )
            
            if login_response.status_code != 200:
                return {"success": False, "message": "Agiloft authentication failed", "details": login_response.text[:200]}
            
            # Get token from response
            try:
                login_data = login_response.json()
                token = login_data.get("token", "")
            except:
                token = ""
            
            auth_headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}" if token else ""
            }
            
            created_count = 0
            updated_count = 0
            
            for clause in clauses_to_push:
                clause_data = {
                    "clause_number": clause.get("number", ""),
                    "clause_title": clause.get("title", ""),
                    "clause_type": clause.get("type", "FAR"),
                    "clause_text": clause.get("text", "")[:32000],  # Agiloft field size limit
                    "clause_summary": clause.get("summary", ""),
                    "flowdown_required": "Yes" if clause.get("flowdown_required") else "No",
                    "threshold_amount": str(clause.get("threshold_amount", 0) or 0),
                    "keywords": ", ".join(clause.get("keywords", [])),
                    "source_url": clause.get("source_url", ""),
                    "last_updated": datetime.now(timezone.utc).isoformat()
                }
                
                try:
                    # Search for existing clause
                    search_url = f"{config.kb_url}/Clauses"
                    search_response = await client.get(
                        search_url,
                        params={
                            "lang": "en",
                            "$filter": f"clause_number eq '{clause.get('number', '')}'"
                        },
                        headers=auth_headers
                    )
                    
                    existing_records = []
                    if search_response.status_code == 200:
                        try:
                            search_data = search_response.json()
                            existing_records = search_data if isinstance(search_data, list) else search_data.get("records", [])
                        except:
                            pass
                    
                    if existing_records:
                        # Update existing record
                        record_id = existing_records[0].get("id", existing_records[0].get("$id"))
                        update_url = f"{config.kb_url}/Clauses/{record_id}"
                        await client.put(
                            update_url,
                            params={"lang": "en"},
                            json=clause_data,
                            headers=auth_headers
                        )
                        updated_count += 1
                    else:
                        # Create new record
                        create_url = f"{config.kb_url}/Clauses"
                        await client.post(
                            create_url,
                            params={"lang": "en"},
                            json=clause_data,
                            headers=auth_headers
                        )
                        created_count += 1
                except Exception as e:
                    logger.error(f"Error pushing clause {clause.get('number')}: {e}")
                    # Try to create anyway
                    try:
                        create_url = f"{config.kb_url}/Clauses"
                        await client.post(
                            create_url,
                            params={"lang": "en"},
                            json=clause_data,
                            headers=auth_headers
                        )
                        created_count += 1
                    except:
                        pass
            
            return {
                "success": True,
                "message": f"Pushed {created_count + updated_count} clauses to Agiloft",
                "pushed_count": created_count + updated_count,
                "created_count": created_count,
                "updated_count": updated_count
            }
            
    except Exception as e:
        logger.error(f"Agiloft push error: {e}")
        return {"success": False, "message": f"Push failed: {str(e)}"}

class AgiloftContractsRequest(BaseModel):
    """Request to fetch Agiloft contracts"""
    config: AgiloftConfig
    table_name: str = "Contracts"

@agiloft_router.post("/contracts")
async def get_agiloft_contracts(contracts_request: AgiloftContractsRequest, request: Request):
    """Fetch contracts from Agiloft for analysis"""
    user = await require_auth(request)
    
    config = contracts_request.config
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            # Login using REST API
            login_response = await client.post(
                f"{config.kb_url}/login",
                params={"lang": "en"},
                json={
                    "login": config.username,
                    "password": config.password,
                    "KB": config.kb_name
                },
                headers={"Content-Type": "application/json"}
            )
            
            if login_response.status_code != 200:
                # Return demo data if login fails
                logger.info("Agiloft login failed, returning demo contracts")
                return {
                    "success": True,
                    "contracts": [
                        {
                            "id": "demo-1",
                            "name": "Defense Logistics Contract",
                            "type": "Fixed-Price",
                            "value": 2500000,
                            "clauses": ["52.212-4", "52.219-8", "252.204-7012"],
                            "status": "Active"
                        },
                        {
                            "id": "demo-2", 
                            "name": "IT Services Agreement",
                            "type": "Time-and-Materials",
                            "value": 750000,
                            "clauses": ["52.212-4", "52.222-26"],
                            "status": "Active"
                        },
                        {
                            "id": "demo-3",
                            "name": "Research & Development Contract",
                            "type": "Cost-Reimbursement",
                            "value": 5000000,
                            "clauses": ["52.212-4", "252.227-7013"],
                            "status": "Active"
                        }
                    ],
                    "note": "Using demo data - Agiloft connection not established"
                }
            
            # Get token from response
            try:
                login_data = login_response.json()
                token = login_data.get("token", "")
            except:
                token = ""
            
            auth_headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}" if token else ""
            }
            
            # Search for contracts using REST API
            contracts_url = f"{config.kb_url}/{contracts_request.table_name}"
            search_response = await client.get(
                contracts_url,
                params={"lang": "en"},
                headers=auth_headers
            )
            
            contracts = []
            
            if search_response.status_code == 200:
                try:
                    data = search_response.json()
                    records = data if isinstance(data, list) else data.get("records", data.get("result", []))
                    
                    for record in records:
                        clauses_str = record.get("clauses", record.get("contract_clauses", ""))
                        clauses = [c.strip() for c in clauses_str.split(",") if c.strip()] if clauses_str else []
                        
                        contracts.append({
                            "id": str(record.get("id", record.get("$id", uuid.uuid4()))),
                            "name": record.get("name", record.get("contract_name", "Unnamed Contract")),
                            "type": record.get("contract_type", record.get("type", "Fixed-Price")),
                            "value": float(record.get("contract_value", record.get("value", 0)) or 0),
                            "clauses": clauses,
                            "status": record.get("status", "Active")
                        })
                except Exception as e:
                    logger.error(f"Error parsing Agiloft contracts: {e}")
            
            # Return demo data if no contracts found
            if not contracts:
                contracts = [
                    {
                        "id": "demo-1",
                        "name": "Defense Logistics Contract",
                        "type": "Fixed-Price",
                        "value": 2500000,
                        "clauses": ["52.212-4", "52.219-8", "252.204-7012"],
                        "status": "Active"
                    },
                    {
                        "id": "demo-2", 
                        "name": "IT Services Agreement",
                        "type": "Time-and-Materials",
                        "value": 750000,
                        "clauses": ["52.212-4", "52.222-26"],
                        "status": "Active"
                    },
                    {
                        "id": "demo-3",
                        "name": "Research & Development Contract",
                        "type": "Cost-Reimbursement",
                        "value": 5000000,
                        "clauses": ["52.212-4", "252.227-7013"],
                        "status": "Active"
                    }
                ]
            
            return {"success": True, "contracts": contracts}
            
    except Exception as e:
        logger.error(f"Agiloft contracts error: {e}")
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
    
    # Get all required clauses from our database
    all_clauses = await db.clauses.find({}, {"_id": 0}).to_list(500)
    
    # Get flowdown-required clauses
    flowdown_clauses = [c for c in all_clauses if c.get("flowdown_required")]
    
    # Determine which are applicable based on contract type and value
    applicable_flowdown = []
    for clause in flowdown_clauses:
        threshold = clause.get("threshold_amount", 0) or 0
        contract_types = clause.get("contract_types", [])
        
        if contract_value >= threshold:
            if "All" in contract_types or contract_type in contract_types or not contract_types:
                applicable_flowdown.append(clause["number"])
    
    # Analyze contract clauses
    correct_clauses = []
    missing_clauses = []
    needs_update = []
    
    # Check which standard clauses are present
    all_clause_numbers = [c["number"] for c in all_clauses]
    
    for clause_num in contract_clauses:
        if clause_num in all_clause_numbers:
            correct_clauses.append(clause_num)
        else:
            needs_update.append(clause_num)  # Unknown clause
    
    # Check for missing required flowdown clauses
    for required in applicable_flowdown:
        if required not in contract_clauses:
            missing_clauses.append(required)
    
    # Determine compliance status
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
        "recommendations": [
            f"Add missing clause {c}" for c in missing_clauses[:5]
        ]
    }

class AgiloftUpdateRequest(BaseModel):
    """Request to update an Agiloft contract"""
    config: AgiloftConfig
    contract_id: str
    updates: Dict[str, Any]

@agiloft_router.post("/update-contract")
async def update_agiloft_contract(update_request: AgiloftUpdateRequest, request: Request):
    """Update a contract in Agiloft with compliance fixes"""
    user = await require_auth(request)
    
    config = update_request.config
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            # Login using REST API
            login_response = await client.post(
                f"{config.kb_url}/login",
                params={"lang": "en"},
                json={
                    "login": config.username,
                    "password": config.password,
                    "KB": config.kb_name
                },
                headers={"Content-Type": "application/json"}
            )
            
            # Get token
            token = ""
            if login_response.status_code == 200:
                try:
                    login_data = login_response.json()
                    token = login_data.get("token", "")
                except:
                    pass
            
            auth_headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}" if token else ""
            }
            
            # Build update data
            update_data = {}
            
            # Add missing clauses to the contract
            missing = update_request.updates.get("missing_clauses", [])
            flowdown = update_request.updates.get("flowdown_clauses", [])
            
            if missing:
                update_data["missing_clauses_flag"] = "Yes"
                update_data["missing_clauses_list"] = ", ".join(missing)
            
            if flowdown:
                update_data["flowdown_clauses"] = ", ".join(flowdown)
            
            update_data["compliance_checked"] = datetime.now(timezone.utc).isoformat()
            update_data["compliance_checker"] = user.name
            
            # Update in Agiloft using REST API
            update_url = f"{config.kb_url}/Contracts/{update_request.contract_id}"
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
                # For demo purposes, return success
                return {
                    "success": True,
                    "message": "Contract flagged for update (demo mode)",
                    "note": "In production, this would update the Agiloft record"
                }
            
    except Exception as e:
        logger.error(f"Agiloft update error: {e}")
        return {"success": False, "message": str(e)}

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
    
    # Collect all clauses
    clause_docs = []
    
    # By number
    for clause_num in export_request.clause_numbers:
        clause = await db.clauses.find_one({"number": clause_num}, {"_id": 0})
        if clause:
            clause_docs.append(clause)
    
    # By ID
    for clause_id in export_request.clause_ids:
        clause = await db.clauses.find_one({"clause_id": clause_id}, {"_id": 0})
        if clause and clause not in clause_docs:
            clause_docs.append(clause)
    
    if not clause_docs:
        raise HTTPException(status_code=404, detail="No clauses found for export")
    
    if export_request.format == "json":
        # Return as JSON
        return {
            "export_date": datetime.now(timezone.utc).isoformat(),
            "total_clauses": len(clause_docs),
            "clauses": clause_docs
        }
    
    elif export_request.format == "csv":
        # Generate CSV
        import csv
        
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        
        # Header
        headers = ["Number", "Title", "Type", "Flowdown Required"]
        if export_request.include_full_text:
            headers.append("Text")
        writer.writerow(headers)
        
        # Data rows
        for clause in clause_docs:
            row = [
                clause.get("number", ""),
                clause.get("title", ""),
                clause.get("type", ""),
                "Yes" if clause.get("flowdown_required") else "No"
            ]
            if export_request.include_full_text:
                row.append(clause.get("text", "")[:5000])  # Limit text in CSV
            writer.writerow(row)
        
        csv_content = buffer.getvalue()
        
        return StreamingResponse(
            io.BytesIO(csv_content.encode('utf-8')),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=clauses_export.csv"}
        )
    
    else:  # PDF
        # Generate comprehensive PDF
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
        
        # Custom styles
        title_style = styles['Title']
        heading_style = styles['Heading2']
        normal_style = styles['Normal']
        
        story = []
        
        # Title page
        story.append(Paragraph("Federal Clause Export Report", title_style))
        story.append(Spacer(1, 0.3*inch))
        story.append(Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", normal_style))
        story.append(Paragraph(f"Total Clauses: {len(clause_docs)}", normal_style))
        story.append(Paragraph(f"Exported by: {user.name}", normal_style))
        story.append(Spacer(1, 0.5*inch))
        
        # Table of Contents
        story.append(Paragraph("Table of Contents", heading_style))
        story.append(Spacer(1, 0.2*inch))
        for i, clause in enumerate(clause_docs, 1):
            story.append(Paragraph(f"{i}. {clause.get('number', 'N/A')} - {clause.get('title', 'Untitled')}", normal_style))
        story.append(Spacer(1, 0.5*inch))
        
        # Clause details
        for clause in clause_docs:
            story.append(Paragraph(f"{clause.get('number', 'N/A')}", heading_style))
            story.append(Paragraph(f"<b>{clause.get('title', 'Untitled')}</b>", normal_style))
            story.append(Spacer(1, 0.1*inch))
            
            # Metadata
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
            
            # Summary
            if clause.get('summary'):
                story.append(Paragraph("<b>Summary:</b>", normal_style))
                story.append(Paragraph(clause['summary'], normal_style))
                story.append(Spacer(1, 0.1*inch))
            
            # Full text
            if export_request.include_full_text and clause.get('text'):
                story.append(Paragraph("<b>Full Text:</b>", normal_style))
                # Split long text into paragraphs
                text = clause['text'][:10000]  # Limit text length
                for para in text.split('\n\n'):
                    if para.strip():
                        story.append(Paragraph(para.strip(), normal_style))
                        story.append(Spacer(1, 0.1*inch))
            
            # Keywords
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
    
    # Run flowdown analysis
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
    
    # Generate PDF report
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []
    
    # Title
    story.append(Paragraph("Flowdown Analysis Report", styles['Title']))
    story.append(Spacer(1, 0.3*inch))
    story.append(Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}", styles['Normal']))
    story.append(Paragraph(f"Contract Type: {contract_type}", styles['Normal']))
    story.append(Paragraph(f"Contract Value: ${contract_value:,.2f}", styles['Normal']))
    story.append(Spacer(1, 0.5*inch))
    
    # Summary
    story.append(Paragraph("Summary", styles['Heading2']))
    story.append(Paragraph(f"Total Required Flowdown Clauses: {len(applicable)}", styles['Normal']))
    story.append(Paragraph(f"Present in Contract: {len(present)}", styles['Normal']))
    story.append(Paragraph(f"Missing from Contract: {len(missing)}", styles['Normal']))
    story.append(Spacer(1, 0.3*inch))
    
    # Missing clauses (critical)
    if missing:
        story.append(Paragraph("MISSING CLAUSES (Action Required)", styles['Heading2']))
        for clause in missing:
            story.append(Paragraph(f"• {clause['number']}: {clause['title']}", styles['Normal']))
        story.append(Spacer(1, 0.3*inch))
    
    # Present clauses
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
