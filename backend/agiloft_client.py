"""
Agiloft REST API Client Module
Based on OpenAPI spec from user's Agiloft instance
"""
import os
import asyncio
import httpx
import logging
from typing import List, Dict, Optional, Any, Set
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
    
    Uses REST API endpoints:
    - POST /login - authenticate and get Bearer token
    - POST /clause/search - search Clause Library with field array
    """
    
    def __init__(self, config: AgiloftConfig):
        self.config = config
        self.token: Optional[str] = None
        self.base_url = self._build_base_url()
    
    def _build_base_url(self) -> str:
        """Build the base REST API URL."""
        kb_url = self.config.kb_url.rstrip('/')
        
        # Remove common trailing paths that users might accidentally include
        paths_to_remove = ['/ui', '/ewws', '/ewws/login', '/ewws/alrest', '/login']
        for path in paths_to_remove:
            if kb_url.lower().endswith(path.lower()):
                kb_url = kb_url[:-len(path)]
        
        # Also remove any path with /ewws in it
        if '/ewws' in kb_url:
            idx = kb_url.find('/ewws')
            kb_url = kb_url[:idx]
        
        kb_url = kb_url.rstrip('/')
        
        # Build REST API path - note: kb_name is lowercase in URL
        base = f"{kb_url}/ewws/alrest/{self.config.kb_name.lower()}"
        logger.info(f"Built Agiloft base URL: {base}")
        return base
    
    async def login(self) -> bool:
        """
        Authenticate with Agiloft and get Bearer token.
        
        POST /login
        Body: {"login": "...", "password": "...", "KB": "...", "lang": "EN"}
        Response: {"result": {"access_token": "..."}}
        
        Returns True if successful, False otherwise.
        """
        url = f"{self.base_url}/login"
        
        payload = {
            "login": self.config.username,
            "password": self.config.password,
            "KB": self.config.kb_name,
            "lang": "EN"
        }
        
        logger.info(f"Agiloft login to: {url}")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(
                    url,
                    json=payload,
                    headers={
                        "Accept": "application/json",
                        "Content-Type": "application/json"
                    }
                )
                
                logger.info(f"Login response status: {response.status_code}")
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get("success") or data.get("result"):
                        # Token is in result.access_token
                        result = data.get("result", {})
                        self.token = result.get("access_token")
                        if self.token:
                            logger.info("Agiloft login successful, got access_token")
                            return True
                        else:
                            logger.error(f"No access_token in response: {data}")
                    else:
                        logger.error(f"Agiloft login failed: {data}")
                else:
                    logger.error(f"Agiloft login failed: HTTP {response.status_code} - {response.text[:200]}")
            except Exception as e:
                logger.error(f"Agiloft login error: {e}")
        
        return False
    
    def _get_auth_headers(self) -> Dict[str, str]:
        """Get headers with Bearer token."""
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}"
        }
    
    async def get_clause_numbers(self) -> Set[str]:
        """
        Retrieve all existing Clause Numbers from Agiloft Clause Library.
        
        Uses POST /clause/search with body:
        {
            "search": "",
            "field": ["clause_number"],
            "query": ""
        }
        
        Filters out null/empty values and returns a set of unique clause numbers.
        
        Returns:
            Set of clause number strings like {"52.203-12", "252.204-7012", ...}
        """
        if not self.token:
            if not await self.login():
                raise Exception("Failed to authenticate with Agiloft")
        
        url = f"{self.base_url}/clause/search"
        
        # Use the exact body format specified
        # DO NOT request clause_type - it causes HTTP 400
        payload = {
            "search": "",
            "field": ["clause_number"],
            "query": ""
        }
        
        logger.info(f"Searching Agiloft clauses: {url}")
        logger.info(f"Payload: {payload}")
        
        clause_numbers: Set[str] = set()
        
        async with httpx.AsyncClient(timeout=60.0) as client:
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
                    
                    # Response: {"result": [{"clause_number": "52.203-12"}, {"clause_number": null}, ...]}
                    result = data.get("result", [])
                    
                    if isinstance(result, list):
                        total_records = len(result)
                        logger.info(f"Got {total_records} total records from Agiloft")
                        
                        # Filter out null/empty values
                        for record in result:
                            val = record.get("clause_number")
                            
                            # Skip if null/None
                            if not val:
                                continue
                            
                            # Convert to string and strip whitespace
                            val = str(val).strip()
                            
                            # Skip if empty after strip
                            if not val:
                                continue
                            
                            # Add to set (automatically handles duplicates)
                            clause_numbers.add(val)
                        
                        logger.info(f"Found {len(clause_numbers)} valid clause numbers (filtered out {total_records - len(clause_numbers)} null/empty)")
                        
                        # Log sample
                        sample = list(clause_numbers)[:10]
                        logger.info(f"Sample clause numbers: {sample}")
                    else:
                        logger.warning(f"Unexpected result format: {type(result)}")
                else:
                    logger.error(f"Search failed: {response.status_code} - {response.text[:500]}")
                    
            except Exception as e:
                logger.error(f"Search error: {e}")
                raise
        
        return clause_numbers
    
    async def search_clauses(self, select_fields: Optional[List[str]] = None, 
                             top: int = 5000) -> List[Dict]:
        """
        Search Clause Library and return clause records.
        This is a wrapper for backward compatibility.
        """
        clause_numbers = await self.get_clause_numbers()
        
        # Convert to list of dicts for compatibility
        return [{"clause_number": num} for num in clause_numbers]
    
    async def create_clause(self, clause_data: Dict) -> Dict:
        """
        Create a new clause in Agiloft.
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