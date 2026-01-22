"""
Clause Comparison Routes
Compares acquisition.gov clauses with Agiloft Clause Library
"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import logging
from datetime import datetime, timezone

# Import our modules
from acqgov_scraper import (
    scrape_all_clauses, 
    scrape_far_clauses, 
    scrape_dfars_clauses,
    normalize_clause_id
)
from agiloft_client import AgiloftClient, AgiloftConfig

logger = logging.getLogger(__name__)

# Create router
comparison_router = APIRouter(prefix="/api/comparison")


class CompareRequest(BaseModel):
    """Request for clause comparison"""
    config: AgiloftConfig
    clause_type: Optional[str] = None  # "FAR", "DFARS", or None for both
    source: str = "acquisition_gov"  # "acquisition_gov" or "local_db"


class UploadRequest(BaseModel):
    """Request to upload clauses to Agiloft"""
    config: AgiloftConfig
    clause_numbers: List[str]
    fetch_text: bool = False  # Whether to fetch full text from acquisition.gov


class ClauseData(BaseModel):
    """Clause data structure"""
    clause_number: str
    title: str
    type: str  # FAR or DFARS
    date: Optional[str] = None
    text: Optional[str] = None
    html: Optional[str] = None


# In-memory cache for scraped clauses
_clause_cache: Dict[str, List[Dict]] = {
    "FAR": [],
    "DFARS": [],
    "last_updated": None
}


@comparison_router.get("/acqgov/clauses")
async def get_acqgov_clauses(
    request: Request,
    clause_type: Optional[str] = None,
    refresh: bool = False
):
    """
    GET /api/comparison/acqgov/clauses
    
    Fetch clauses from acquisition.gov (FAR and/or DFARS index).
    Results are cached to avoid repeated scraping.
    
    Query params:
    - clause_type: "FAR", "DFARS", or omit for both
    - refresh: true to force refresh from acquisition.gov
    """
    global _clause_cache
    
    # Check if we need to refresh
    needs_refresh = refresh or not _clause_cache.get("FAR") or not _clause_cache.get("DFARS")
    
    if needs_refresh:
        logger.info("Refreshing clause cache from acquisition.gov...")
        
        if clause_type is None or clause_type.upper() == "FAR":
            far_clauses = await scrape_far_clauses()
            _clause_cache["FAR"] = far_clauses
            logger.info(f"Cached {len(far_clauses)} FAR clauses")
        
        if clause_type is None or clause_type.upper() == "DFARS":
            dfars_clauses = await scrape_dfars_clauses()
            _clause_cache["DFARS"] = dfars_clauses
            logger.info(f"Cached {len(dfars_clauses)} DFARS clauses")
        
        _clause_cache["last_updated"] = datetime.now(timezone.utc).isoformat()
    
    # Return requested clauses
    clauses = []
    if clause_type is None or clause_type.upper() == "FAR":
        clauses.extend(_clause_cache.get("FAR", []))
    if clause_type is None or clause_type.upper() == "DFARS":
        clauses.extend(_clause_cache.get("DFARS", []))
    
    return {
        "success": True,
        "total": len(clauses),
        "clauses": clauses,
        "source": "acquisition.gov",
        "last_updated": _clause_cache.get("last_updated")
    }


@comparison_router.post("/agiloft/clauses/search")
async def search_agiloft_clauses(request: Request, config: AgiloftConfig):
    """
    POST /api/comparison/agiloft/clauses/search
    
    Fetch all clauses from Agiloft Clause Library.
    Returns clause_number and clause_title for each clause.
    """
    try:
        client = AgiloftClient(config)
        
        if not await client.login():
            raise HTTPException(status_code=401, detail="Agiloft authentication failed")
        
        clauses = await client.search_clauses()
        
        # Normalize clause numbers
        for clause in clauses:
            if clause.get("clause_number"):
                clause["clause_number_normalized"] = normalize_clause_id(clause["clause_number"])
        
        return {
            "success": True,
            "total": len(clauses),
            "clauses": clauses,
            "source": "agiloft"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Agiloft search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@comparison_router.post("/compare")
async def compare_clauses(compare_request: CompareRequest):
    """
    POST /api/comparison/compare
    
    Compare clauses between acquisition.gov and Agiloft Clause Library.
    
    Returns:
    - total_acqgov: total clauses from acquisition.gov
    - total_agiloft: total clauses in Agiloft
    - matched: clauses in both
    - missing_in_agiloft: clauses in acquisition.gov but not in Agiloft
    - missing_in_acqgov: clauses in Agiloft but not in acquisition.gov
    """
    global _clause_cache
    
    try:
        # Step 1: Get acquisition.gov clauses from cache or scrape
        logger.info(f"Starting comparison, clause_type={compare_request.clause_type}")
        
        # Check if we need to refresh cache
        clause_type = compare_request.clause_type
        
        if clause_type is None or clause_type.upper() == "FAR":
            if not _clause_cache.get("FAR"):
                logger.info("Refreshing FAR clause cache from acquisition.gov...")
                far_clauses = await scrape_far_clauses()
                _clause_cache["FAR"] = far_clauses
                logger.info(f"Cached {len(far_clauses)} FAR clauses")
        
        if clause_type is None or clause_type.upper() == "DFARS":
            if not _clause_cache.get("DFARS"):
                logger.info("Refreshing DFARS clause cache from acquisition.gov...")
                dfars_clauses = await scrape_dfars_clauses()
                _clause_cache["DFARS"] = dfars_clauses
                logger.info(f"Cached {len(dfars_clauses)} DFARS clauses")
        
        # Collect clauses based on filter
        acqgov_clauses = []
        if clause_type is None or clause_type.upper() == "FAR":
            acqgov_clauses.extend(_clause_cache.get("FAR", []))
        if clause_type is None or clause_type.upper() == "DFARS":
            acqgov_clauses.extend(_clause_cache.get("DFARS", []))
        
        logger.info(f"Got {len(acqgov_clauses)} clauses from acquisition.gov cache")
        
        # Build normalized set of acquisition.gov clause numbers
        acqgov_map = {}  # normalized_number -> clause
        for clause in acqgov_clauses:
            normalized = normalize_clause_id(clause.get("clause_number", ""))
            if normalized:
                acqgov_map[normalized] = clause
        
        acqgov_numbers = set(acqgov_map.keys())
        logger.info(f"Unique normalized acquisition.gov clause numbers: {len(acqgov_numbers)}")
        
        # Sample for debugging
        sample_acqgov = list(acqgov_numbers)[:5]
        logger.info(f"Sample acquisition.gov numbers: {sample_acqgov}")
        
        # Step 2: Get Agiloft clause numbers using REST API
        client = AgiloftClient(compare_request.config)
        
        if not await client.login():
            raise HTTPException(status_code=401, detail="Agiloft authentication failed")
        
        # Get clause numbers from Agiloft using the correct API format
        agiloft_clause_numbers_raw = await client.get_clause_numbers()
        logger.info(f"Got {len(agiloft_clause_numbers_raw)} clause numbers from Agiloft")
        
        # Normalize Agiloft clause numbers for comparison
        agiloft_map = {}  # normalized_number -> original_number
        for clause_num in agiloft_clause_numbers_raw:
            normalized = normalize_clause_id(clause_num)
            if normalized:
                agiloft_map[normalized] = clause_num
        
        agiloft_numbers = set(agiloft_map.keys())
        logger.info(f"Unique normalized Agiloft clause numbers: {len(agiloft_numbers)}")
        
        # Sample for debugging
        sample_agiloft = list(agiloft_numbers)[:5]
        logger.info(f"Sample Agiloft numbers: {sample_agiloft}")
        
        # Step 3: Compare
        matched_numbers = acqgov_numbers.intersection(agiloft_numbers)
        missing_in_agiloft_numbers = acqgov_numbers - agiloft_numbers
        missing_in_acqgov_numbers = agiloft_numbers - acqgov_numbers
        
        logger.info(f"Matched: {len(matched_numbers)}")
        logger.info(f"Missing in Agiloft: {len(missing_in_agiloft_numbers)}")
        logger.info(f"Missing in acquisition.gov: {len(missing_in_acqgov_numbers)}")
        
        # Build result lists
        missing_in_agiloft = []
        for num in sorted(missing_in_agiloft_numbers):
            clause = acqgov_map.get(num, {})
            missing_in_agiloft.append({
                "clause_number": clause.get("clause_number", num),
                "normalized": num,
                "title": clause.get("title", ""),
                "type": clause.get("type", ""),
            })
        
        matched_clauses = []
        for num in sorted(matched_numbers):
            acqgov_clause = acqgov_map.get(num, {})
            agiloft_clause = agiloft_map.get(num, {})
            matched_clauses.append({
                "clause_number": acqgov_clause.get("clause_number", num),
                "normalized": num,
                "acqgov_title": acqgov_clause.get("title", ""),
                "agiloft_title": agiloft_clause.get("clause_title", ""),
                "type": acqgov_clause.get("type", ""),
            })
        
        missing_in_acqgov = []
        for num in sorted(missing_in_acqgov_numbers):
            clause = agiloft_map.get(num, {})
            missing_in_acqgov.append({
                "clause_number": clause.get("clause_number", num),
                "normalized": num,
                "clause_title": clause.get("clause_title", ""),
                "agiloft_id": clause.get("id"),
            })
        
        return {
            "success": True,
            "source": "acquisition.gov",
            "total_acqgov": len(acqgov_clauses),
            "total_agiloft": len(agiloft_clauses),
            "matched_count": len(matched_numbers),
            "missing_in_agiloft_count": len(missing_in_agiloft),
            "missing_in_acqgov_count": len(missing_in_acqgov),
            "matched": matched_clauses,
            "missing_in_agiloft": missing_in_agiloft,
            "missing_in_acqgov": missing_in_acqgov,
            "debug": {
                "acqgov_normalized_count": len(acqgov_numbers),
                "agiloft_normalized_count": len(agiloft_numbers),
                "sample_acqgov": sample_acqgov,
                "sample_agiloft": sample_agiloft,
            }
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Comparison error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@comparison_router.post("/upload")
async def upload_clauses(upload_request: UploadRequest):
    """
    POST /api/comparison/upload
    
    Upload selected clauses to Agiloft Clause Library.
    
    Request body:
    - config: Agiloft credentials
    - clause_numbers: List of clause numbers to upload
    - fetch_text: Whether to fetch full text from acquisition.gov
    
    Returns:
    - results: Per-clause upload status
    """
    global _clause_cache
    
    try:
        # Get clause data from cache
        all_clauses = []
        all_clauses.extend(_clause_cache.get("FAR", []))
        all_clauses.extend(_clause_cache.get("DFARS", []))
        
        acqgov_clauses = {
            normalize_clause_id(c.get("clause_number", "")): c 
            for c in all_clauses
        }
        
        # Initialize Agiloft client
        client = AgiloftClient(upload_request.config)
        
        if not await client.login():
            raise HTTPException(status_code=401, detail="Agiloft authentication failed")
        
        results = []
        uploaded_count = 0
        error_count = 0
        
        for clause_number in upload_request.clause_numbers:
            normalized = normalize_clause_id(clause_number)
            clause_data = acqgov_clauses.get(normalized)
            
            if not clause_data:
                results.append({
                    "clause_number": clause_number,
                    "success": False,
                    "error": "Clause not found in acquisition.gov data"
                })
                error_count += 1
                continue
            
            # Prepare Agiloft clause record
            agiloft_data = {
                "clause_number": clause_data.get("clause_number", ""),
                "clause_title": f"{clause_data.get('clause_number', '')} - {clause_data.get('title', '')}",
                "clause_type": clause_data.get("type", "FAR"),
                "clause_text": clause_data.get("text") or f"See acquisition.gov for full text of {clause_data.get('clause_number', '')}"
            }
            
            # Upload using upsert
            result = await client.upsert_clause(agiloft_data)
            
            if result.get("success"):
                uploaded_count += 1
            else:
                error_count += 1
            
            results.append({
                "clause_number": clause_number,
                "success": result.get("success", False),
                "action": result.get("action", "unknown"),
                "error": result.get("error")
            })
        
        return {
            "success": uploaded_count > 0 or error_count == 0,
            "total_requested": len(upload_request.clause_numbers),
            "uploaded_count": uploaded_count,
            "error_count": error_count,
            "results": results
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
