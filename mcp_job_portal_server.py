# mcp_job_portal_server.py
import asyncio 
import logging
import sys
import os
import json
from typing import Any, List, Dict, Optional # Ensure typing imports are present for type hints

# MCP imports
from mcp.server.fastmcp import FastMCP
# import mcp.types as types # Likely not needed for simple returns with FastMCP

# Project specific imports
from job_portal_service.opensearch_service import OpenSearchService
from job_portal_service.query_generators import (
    generate_job_search_query, 
    generate_similar_job_query,
    JOB_FIELD_MAP
)

# (Keep logging setup, os_service, mcp instance, JOB_INDEX_NAME, USER_INDEX_NAME)
logger = logging.getLogger('mcp_job_portal_server')
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s') # Ensure this is here
logger.info("Initializing MCP Job Portal Server with FastMCP (OpenSearch)")

os_service = OpenSearchService()
mcp = FastMCP("JobPortalService")

JOB_INDEX_NAME = os.getenv("JOB_INDEX_NAME", "job_postings_alias")
USER_INDEX_NAME = os.getenv("USER_INDEX_NAME", "user_profiles_alias")


# --- Tool Definitions using @mcp.tool() ---

@mcp.tool(description="Fetches the full details of a specific job posting using its board_id.")
async def get_job_details(board_id: str) -> Dict[str, Any]:
    logger.info(f"Tool 'get_job_details' called with board_id: {board_id}")
    if not os_service.is_connected():
        return {"error": "OpenSearch service is not connected."}
    try:
        if not board_id:
            # FastMCP might do some validation based on type hints, but explicit checks are good.
            logger.warning("board_id is missing for get_job_details")
            return {"error": "Missing required argument: board_id"} # Should not happen if schema is enforced by FastMCP
        
        query = {"query": {"term": {JOB_FIELD_MAP["board_id"]: board_id}}}
        results = os_service.execute_query(index_name=JOB_INDEX_NAME, query=query)
        return results[0] if results else {"error": f"Job with board_id {board_id} not found."}
    except Exception as e:
        logger.error(f"Exception in get_job_details: {e}")
        return {"error": f"An unexpected error occurred: {str(e)}"}

@mcp.tool(description="Searches for job postings based on various criteria like location, salary, keywords, etc.")
async def search_jobs_by_criteria(filters: Optional[Dict[str, Any]] = None, text_query: Optional[str] = "", size: Optional[int] = 10) -> List[Dict[str, Any]]:
    logger.info(f"Tool 'search_jobs_by_criteria' called with filters: {filters}, text_query: '{text_query}', size: {size}")
    if not os_service.is_connected():
        return [{"error": "OpenSearch service is not connected."}] # Return list with error dict
    
    filters = filters or {}
    text_query = text_query or ""

    try:
        query = generate_job_search_query(text_query=text_query, filters=filters)
        query["size"] = size
        results = os_service.execute_query(index_name=JOB_INDEX_NAME, query=query)
        return results
    except Exception as e:
        logger.error(f"Exception in search_jobs_by_criteria: {e}")
        return [{"error": f"An unexpected error occurred: {str(e)}"}]

@mcp.tool(description="Finds job postings similar to a given job posting ID.")
async def find_similar_jobs_to_posting(board_id: str, original_job_details: Optional[Dict[str, Any]] = None, size: Optional[int] = 5) -> List[Dict[str, Any]]:
    logger.info(f"Tool 'find_similar_jobs_to_posting' called for board_id: {board_id}, size: {size}")
    if not os_service.is_connected():
        return [{"error": "OpenSearch service is not connected."}]

    try:
        if not board_id:
             return [{"error": "Missing required argument: board_id"}]

        if not original_job_details:
            logger.info(f"Original job details not provided for {board_id}, fetching...")
            details_query = {"query": {"term": {JOB_FIELD_MAP["board_id"]: board_id}}}
            details_results = os_service.execute_query(index_name=JOB_INDEX_NAME, query=details_query)
            if not details_results:
                return [{"error": f"Original job with board_id {board_id} not found."}]
            original_job_details = details_results[0]
        
        query = generate_similar_job_query(board_id=board_id, job_details=original_job_details)
        query["size"] = size
        results = os_service.execute_query(index_name=JOB_INDEX_NAME, query=query)
        return results
    except Exception as e:
        logger.error(f"Exception in find_similar_jobs_to_posting: {e}")
        return [{"error": f"An unexpected error occurred: {str(e)}"}]

@mcp.tool(description="Summarizes the main points of a job posting.")
async def summarize_job_posting_main_points(board_id: str) -> str: # Returns a string for this tool
    logger.info(f"Tool 'summarize_job_posting_main_points' called for board_id: {board_id}")
    if not os_service.is_connected():
        return json.dumps({"error": "OpenSearch service is not connected."}) # String return, so dump error

    try:
        if not board_id:
            return json.dumps({"error": "Missing required argument: board_id"})

        details_query = {"query": {"term": {JOB_FIELD_MAP["board_id"]: board_id}}}
        details_results = os_service.execute_query(index_name=JOB_INDEX_NAME, query=details_query)
        if not details_results:
            return json.dumps({"error": f"Job with board_id {board_id} not found for summarization."})
        job = details_results[0]

        summary_points = [
            f"Title: {job.get(JOB_FIELD_MAP.get('title'), 'N/A')}",
            f"Organization: {job.get(JOB_FIELD_MAP.get('organization_name'), 'N/A')}",
            f"Location: {job.get(JOB_FIELD_MAP.get('location'), 'N/A')}",
            f"Salary Details: {job.get(JOB_FIELD_MAP.get('salary_min'), 'N/A')}",
            f"Specialty: {job.get(JOB_FIELD_MAP.get('specialty'), 'N/A')}",
            f"Employment Type: {job.get(JOB_FIELD_MAP.get('employment_type'), 'N/A')}"
        ]
        return "\n".join(summary_points)
    except Exception as e:
        logger.error(f"Exception in summarize_job_posting_main_points: {e}")
        return json.dumps({"error": f"An unexpected error occurred: {str(e)}"})

@mcp.tool(description="Fetches a user's profile data for recommendations. (Currently placeholder).")
async def get_user_profile_for_recommendations(user_id: str) -> Dict[str, Any]:
    logger.info(f"Tool 'get_user_profile_for_recommendations' for user_id: {user_id}. Returning placeholder data.")
    # This tool is a placeholder and does not interact with OpenSearch yet.
    # When User Profile DB is ready, this will query USER_INDEX_NAME.
    if not user_id: # Still good to check
        return {"error": "Missing required argument: user_id"}
        
    mock_profile = {
        "user_id": user_id,
        "profile_status": "placeholder_data",
        "preferred_specialties": ["Pulmonology", "Rheumatology"],
        "preferred_locations": ["Busan", "Gyeonggi-do"],
        "experience_years": 3,
        "skills_keywords": ["bronchoscopy", "arthritis management"],
        "desired_employment_type": "Part-time",
        "desired_salary_range": "60000000-90000000",
        "resume_summary": "Dedicated physician with 3 years of experience in internal medicine."
    }
    return mock_profile

# (Keep Main Server Execution block)
if __name__ == "__main__":
    # (Keep stdio encoding fix)
    if sys.platform == "win32" and os.environ.get('PYTHONIOENCODING') is None:
        sys.stdin.reconfigure(encoding="utf-8")
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")

    if os_service.is_connected():
        logger.info("OpenSearch connection successful. Starting FastMCP server.")
    else:
        logger.warning("OpenSearch connection failed. FastMCP server starting but OpenSearch dependent tools will not work.")
    
    mcp.run(transport="stdio")
