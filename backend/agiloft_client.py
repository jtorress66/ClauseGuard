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
    
    async def check_clause_exists(self, clause_number: str) -> bool:
        """
        Check if a clause with the given clause_number exists in Agiloft.
        Uses POST /clause/search with query for the specific clause number.
        """
        if not self.token:
            if not await self.login():
                return False
        
        url = f"{self.base_url}/clause/search"
        
        # Search for this specific clause number
        payload = {
            "search": "",
            "field": ["clause_number"],
            "query": f"clause_number~='{clause_number}'"
        }
        
        logger.info(f"Checking if clause {clause_number} exists in Agiloft...")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(
                    url,
                    params={"lang": "en"},
                    json=payload,
                    headers=self._get_auth_headers()
                )
                
                if response.status_code == 200:
                    data = response.json()
                    success = data.get("success", False)
                    
                    if success:
                        result = data.get("result", [])
                        # Check if any records returned
                        if isinstance(result, list) and len(result) > 0:
                            logger.info(f"Clause {clause_number} EXISTS in Agiloft ({len(result)} records found)")
                            return True
                        elif isinstance(result, dict):
                            # Single record or nested structure
                            logger.info(f"Clause {clause_number} EXISTS in Agiloft (dict result)")
                            return True
                    
                    logger.info(f"Clause {clause_number} does NOT exist in Agiloft")
                    return False
                else:
                    logger.warning(f"Check clause exists failed: {response.status_code}")
                    return False
                    
            except Exception as e:
                logger.error(f"Error checking clause exists: {e}")
                return False
    
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
        Uses the same format as the search endpoint - POST /clause with JSON body.
        """
        if not self.token:
            if not await self.login():
                return {"success": False, "error": "Authentication failed"}
        
        url = f"{self.base_url}/clause"
        
        logger.info(f"Creating clause in Agiloft: {clause_data.get('clause_number', 'N/A')}")
        logger.info(f"Payload: {clause_data}")
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                response = await client.post(
                    url,
                    params={"lang": "en"},
                    json=clause_data,
                    headers=self._get_auth_headers()
                )
                
                logger.info(f"Agiloft create clause response status: {response.status_code}")
                logger.info(f"Agiloft create clause response (first 500 chars): {response.text[:500]}")
                
                if response.status_code in [200, 201]:
                    try:
                        data = response.json()
                        # Check for success in response body
                        if isinstance(data, dict):
                            # Agiloft returns {"success": true, "result": {...}} on success
                            api_success = data.get("success", True)
                            if api_success:
                                return {
                                    "success": True,
                                    "data": data,
                                    "clause_number": clause_data.get("clause_number"),
                                    "id": data.get("result", {}).get("id") if isinstance(data.get("result"), dict) else None
                                }
                            else:
                                error_msg = data.get("message", data.get("error", "API returned success=false"))
                                return {
                                    "success": False,
                                    "error": error_msg,
                                    "clause_number": clause_data.get("clause_number")
                                }
                        else:
                            return {
                                "success": True,
                                "data": data,
                                "clause_number": clause_data.get("clause_number")
                            }
                    except Exception as json_err:
                        logger.warning(f"Failed to parse Agiloft response as JSON: {json_err}")
                        return {
                            "success": True,
                            "data": response.text,
                            "clause_number": clause_data.get("clause_number")
                        }
                else:
                    error_text = response.text[:500]
                    logger.error(f"Agiloft create clause failed: HTTP {response.status_code} - {error_text}")
                    return {
                        "success": False,
                        "error": f"HTTP {response.status_code}: {error_text}",
                        "clause_number": clause_data.get("clause_number")
                    }
                    
            except Exception as e:
                logger.error(f"Exception creating clause in Agiloft: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "clause_number": clause_data.get("clause_number")
                }
    
    async def upsert_clause(self, clause_data: Dict, clause_number: str) -> Dict:
        """
        Create or update a clause using upsert endpoint.
        
        Uses: POST /clause/upsert?lang=en&query=clause_number~='<value>'
        
        The clause_number is passed in the query parameter, not the body.
        Body contains the fields to set: clause_text, clause_date, etc.
        """
        # Ensure we have a valid token (re-login if needed)
        if not self.token:
            if not await self.login():
                return {"success": False, "error": "Authentication failed"}
        
        url = f"{self.base_url}/clause/upsert"
        
        # Build query string in format: clause_number~='52.225-24'
        query = f"clause_number~='{clause_number}'"
        
        logger.info(f"=== AGILOFT UPSERT ===")
        logger.info(f"URL: {url}")
        logger.info(f"Query param: {query}")
        logger.info(f"Clause number: {clause_number}")
        logger.info(f"Body keys: {list(clause_data.keys())}")
        logger.info(f"clause_text length: {len(clause_data.get('clause_text', ''))} chars")
        logger.info(f"clause_date: {clause_data.get('clause_date')}")
        
        async with httpx.AsyncClient(timeout=120.0) as client:
            try:
                response = await client.post(
                    url,
                    params={"lang": "en", "query": query},
                    json=clause_data,
                    headers=self._get_auth_headers()
                )
                
                logger.info(f"Agiloft upsert response status: {response.status_code}")
                logger.info(f"Agiloft upsert response (first 1000 chars): {response.text[:1000]}")
                
                if response.status_code in [200, 201]:
                    try:
                        data = response.json()
                        api_success = data.get("success", True)
                        if api_success:
                            logger.info(f"SUCCESS: Clause {clause_number} upserted to Agiloft")
                            return {
                                "success": True,
                                "data": data,
                                "clause_number": clause_number,
                                "action": "upserted"
                            }
                        else:
                            error_msg = data.get("message", str(data.get("errors", "Unknown error")))
                            logger.error(f"FAILED: Agiloft returned success=false: {error_msg}")
                            return {
                                "success": False,
                                "error": error_msg,
                                "clause_number": clause_number
                            }
                    except Exception as json_err:
                        logger.warning(f"Response not JSON but status was OK: {json_err}")
                        return {
                            "success": True,
                            "data": response.text,
                            "clause_number": clause_number,
                            "action": "upserted"
                        }
                else:
                    error_text = response.text[:500]
                    logger.error(f"FAILED: HTTP {response.status_code} - {error_text}")
                    return {
                        "success": False,
                        "error": f"HTTP {response.status_code}: {error_text}",
                        "clause_number": clause_number
                    }
                    
            except Exception as e:
                logger.error(f"Exception in upsert: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "clause_number": clause_number
                }