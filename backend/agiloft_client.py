"""
Agiloft REST API Client Module
Based on OpenAPI spec from user's Agiloft instance
"""
import os
import httpx
import logging
from typing import List, Dict, Optional, Any
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class AgiloftConfig(BaseModel):
    """Agiloft connection configuration"""
    kb_url: str  # e.g., "https://yourkb.agiloft.com"
    kb_name: str  # e.g., "yourKBname"
    username: str
    password: str


class AgiloftClient:
    """
    Agiloft REST API Client
    
    Based on OpenAPI spec endpoints:
    - POST /login - authenticate and get token
    - POST /clause/search - search Clause Library
    - POST /clause - create clause
    - POST /clause/upsert - create or update clause
    - PUT /clause/{id} - update clause
    """
    
    def __init__(self, config: AgiloftConfig):
        self.config = config
        self.token: Optional[str] = None
        self.base_url = self._build_base_url()
    
    def _build_base_url(self) -> str:
        """Build the base REST API URL."""
        kb_url = self.config.kb_url.rstrip('/')
        # Remove /ui if present
        if kb_url.endswith('/ui'):
            kb_url = kb_url[:-3]
        # Build REST API path
        return f"{kb_url}/ewws/alrest/{self.config.kb_name}"
    
    async def login(self) -> bool:
        """
        Authenticate with Agiloft and store token.
        
        Returns True if successful, False otherwise.
        """
        url = f"{self.base_url}/login"
        
        payload = {
            "login": self.config.username,
            "password": self.config.password,
            "KB": self.config.kb_name,
            "lang": "en"
        }
        
        logger.info(f"Agiloft login to: {url}")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(
                    url,
                    json=payload,
                    headers={"Content-Type": "application/json"}
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get("success"):
                        self.token = data.get("result", {}).get("access_token")
                        if self.token:
                            logger.info("Agiloft login successful")
                            return True
                        else:
                            logger.error("No access token in response")
                    else:
                        logger.error(f"Agiloft login failed: {data.get('message', 'Unknown error')}")
                else:
                    logger.error(f"Agiloft login failed: HTTP {response.status_code}")
            except Exception as e:
                logger.error(f"Agiloft login error: {e}")
        
        return False
    
    def _get_auth_headers(self) -> Dict[str, str]:
        """Get headers with auth token."""
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}"
        }
    
    async def search_clauses(self, select_fields: Optional[List[str]] = None, 
                             top: int = 5000) -> List[Dict]:
        """
        Search Clause Library and return all clauses.
        
        Args:
            select_fields: Fields to return (default: clause_number, clause_title, clause_type)
            top: Maximum records to return
        
        Returns:
            List of clause records
        """
        if not self.token:
            if not await self.login():
                raise Exception("Failed to authenticate with Agiloft")
        
        url = f"{self.base_url}/clause/search"
        
        # Default fields based on OpenAPI spec
        if select_fields is None:
            select_fields = ["id", "clause_number", "clause_title", "clause_type", "clause_text"]
        
        payload = {
            "$select": ",".join(select_fields),
            "$top": top
        }
        
        logger.info(f"Searching Agiloft clauses: {url}")
        logger.info(f"Payload: {payload}")
        
        async with httpx.AsyncClient(timeout=120.0) as client:
            try:
                response = await client.post(
                    url,
                    params={"lang": "en"},
                    json=payload,
                    headers=self._get_auth_headers()
                )
                
                logger.info(f"Search response status: {response.status_code}")
                
                if response.status_code == 200:
                    data = response.json()
                    logger.info(f"Search response keys: {list(data.keys()) if isinstance(data, dict) else 'list'}")
                    
                    # Handle Agiloft's response format
                    clauses = self._extract_records(data)
                    logger.info(f"Extracted {len(clauses)} clause records")
                    
                    # Log sample to see field structure
                    if clauses:
                        sample = clauses[0]
                        logger.info(f"Sample clause fields: {list(sample.keys())}")
                        logger.info(f"Sample clause_number: {sample.get('clause_number', 'N/A')}")
                        logger.info(f"Sample clause_title: {str(sample.get('clause_title', 'N/A'))[:50]}")
                    
                    return clauses
                else:
                    logger.error(f"Search failed: {response.status_code} - {response.text[:500]}")
                    return []
                    
            except Exception as e:
                logger.error(f"Search error: {e}")
                return []
    
    def _extract_records(self, data: Any) -> List[Dict]:
        """
        Extract records from Agiloft's nested response format.
        
        Agiloft wraps results in various structures:
        - {result: [{DAOclause: {...}}, ...]}
        - {result: {value: [...]}}
        - {value: [...]}
        - etc.
        """
        records = []
        
        if isinstance(data, list):
            records = data
        elif isinstance(data, dict):
            # Try different response formats
            if "result" in data:
                result = data["result"]
                if isinstance(result, list):
                    records = result
                elif isinstance(result, dict):
                    if "value" in result:
                        records = result["value"]
                    else:
                        records = [result]
            elif "value" in data:
                records = data["value"]
            elif "records" in data:
                records = data["records"]
        
        # Extract from DAO wrapper if present
        extracted = []
        for record in records:
            if isinstance(record, dict):
                # Check for DAOclause wrapper
                dao_key = next((k for k in record.keys() if k.startswith("DAO")), None)
                if dao_key and isinstance(record[dao_key], dict):
                    clause_data = record[dao_key].copy()
                    # Include id from parent if not in nested
                    if "id" not in clause_data and "id" in record:
                        clause_data["id"] = record["id"]
                    extracted.append(clause_data)
                else:
                    extracted.append(record)
        
        return extracted
    
    async def create_clause(self, clause_data: Dict) -> Dict:
        """
        Create a new clause in Agiloft.
        
        Args:
            clause_data: Dict with clause_number, clause_title, clause_text, etc.
        
        Returns:
            Response dict with success status and created record
        """
        if not self.token:
            if not await self.login():
                return {"success": False, "error": "Authentication failed"}
        
        url = f"{self.base_url}/clause"
        
        logger.info(f"Creating clause: {clause_data.get('clause_number', 'N/A')}")
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                response = await client.post(
                    url,
                    params={"lang": "en"},
                    json=clause_data,
                    headers=self._get_auth_headers()
                )
                
                if response.status_code in [200, 201]:
                    data = response.json()
                    return {
                        "success": data.get("success", True),
                        "data": data,
                        "clause_number": clause_data.get("clause_number")
                    }
                else:
                    return {
                        "success": False,
                        "error": response.text[:200],
                        "clause_number": clause_data.get("clause_number")
                    }
                    
            except Exception as e:
                return {
                    "success": False,
                    "error": str(e),
                    "clause_number": clause_data.get("clause_number")
                }
    
    async def upsert_clause(self, clause_data: Dict, query_field: str = "clause_number") -> Dict:
        """
        Create or update a clause (upsert).
        
        Uses the query parameter to find existing record by field value.
        If found, updates; if not found, creates.
        
        Args:
            clause_data: Dict with clause data
            query_field: Field to match on (default: clause_number)
        
        Returns:
            Response dict
        """
        if not self.token:
            if not await self.login():
                return {"success": False, "error": "Authentication failed"}
        
        url = f"{self.base_url}/clause/upsert"
        
        # Build query string for matching
        query_value = clause_data.get(query_field, "")
        query = f"{query_field}~='{query_value}'"
        
        logger.info(f"Upserting clause: {query_value}")
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                response = await client.post(
                    url,
                    params={"lang": "en", "query": query},
                    json=clause_data,
                    headers=self._get_auth_headers()
                )
                
                if response.status_code in [200, 201]:
                    data = response.json()
                    return {
                        "success": data.get("success", True),
                        "data": data,
                        "clause_number": clause_data.get("clause_number"),
                        "action": "upserted"
                    }
                else:
                    return {
                        "success": False,
                        "error": response.text[:200],
                        "clause_number": clause_data.get("clause_number")
                    }
                    
            except Exception as e:
                return {
                    "success": False,
                    "error": str(e),
                    "clause_number": clause_data.get("clause_number")
                }
    
    async def get_clause_numbers(self) -> set:
        """
        Get all clause numbers from Agiloft Clause Library.
        
        Returns:
            Set of normalized clause numbers
        """
        from acqgov_scraper import normalize_clause_id
        
        clauses = await self.search_clauses(
            select_fields=["id", "clause_number", "clause_title"],
            top=10000
        )
        
        numbers = set()
        for clause in clauses:
            # Try clause_number field first
            clause_num = clause.get("clause_number", "")
            
            # If empty, try to extract from clause_title
            if not clause_num:
                from acqgov_scraper import SECTION_RE
                title = clause.get("clause_title", "")
                m = SECTION_RE.search(title)
                if m:
                    clause_num = m.group(1)
            
            if clause_num:
                normalized = normalize_clause_id(clause_num)
                numbers.add(normalized)
        
        logger.info(f"Found {len(numbers)} unique clause numbers in Agiloft")
        return numbers
