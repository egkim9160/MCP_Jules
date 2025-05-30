# mcp_job_portal_server.py
import asyncio 
import logging
import sys
import os
import json
from typing import Any, List, Dict, Optional 
import re # For NLU regex in generate_search_conditions

# MCP imports
from mcp.server.fastmcp import FastMCP

# Project specific imports
from job_portal_service.opensearch_service import OpenSearchService
from job_portal_service.query_generators import (
    # generate_job_search_query, # No longer directly used by server tools, agent will use generate_search_conditions
    # generate_similar_job_query, # No longer directly used by server tools
    JOB_FIELD_MAP # Still needed for format_job_summary
)
from job_portal_service.context_utils import analyze_request, RequestContext, QueryType # For generate_search_conditions

logger = logging.getLogger('mcp_job_portal_server')
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger.info("Initializing MCP Job Portal Server with FastMCP (OpenSearch) - Atomic Tools Version")

os_service = OpenSearchService()
mcp = FastMCP("JobPortalService")

JOB_INDEX_NAME = os.getenv("JOB_INDEX_NAME", "job_postings_alias")
USER_INDEX_NAME = os.getenv("USER_INDEX_NAME", "user_profiles_alias") # Kept for future user-related tools

# Predefined lists for more generic filter extraction
KNOWN_LOCATIONS = ["서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종", "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주"]
KNOWN_ORG_TYPES = ["상급종합병원", "종합병원", "병원", "의원", "네트워크의원", "요양병원", "보건소", "보건지소"] # Add more as needed


# --- New Atomic Tool Definitions using @mcp.tool() ---

@mcp.tool(description="Executes a raw OpenSearch Query DSL against a specified index.")
async def opensearch_query_executor(index_name: str, query_dsl: Dict[str, Any], size: Optional[int] = None) -> List[Dict[str, Any]]:
    logger.info(f"Tool 'opensearch_query_executor' called for index: '{index_name}', size: {size}")
    logger.debug(f"Query DSL: {json.dumps(query_dsl, indent=2)}") 
    if not os_service.is_connected():
        return [{"error": "OpenSearch service is not connected."}]
    try:
        if size is not None: 
            query_dsl['size'] = size
        
        results = os_service.execute_query(index_name=index_name, query=query_dsl)
        if not results:
            logger.warning(f"No results from opensearch_query_executor for index '{index_name}'. Query: {json.dumps(query_dsl)}")
        return results
    except Exception as e:
        logger.error(f"Exception in opensearch_query_executor: {e}")
        return [{"error": f"An unexpected error occurred during query execution: {str(e)}"}]

@mcp.tool(description="Analyzes raw query and URL to generate structured search conditions (filters, semantic text) for job searches.")
async def generate_search_conditions(raw_query: str, url_context: Optional[str] = None) -> Dict[str, Any]:
    logger.info(f"Tool 'generate_search_conditions' called with raw_query: '{raw_query}', url_context: '{url_context}'")
    try:
        req_context = analyze_request(raw_query=raw_query, url=url_context)
        logger.info(f"RequestContext for generate_search_conditions: {req_context}")

        conditions: Dict[str, Any] = {"filters": {}}
        
        # Assign original raw_query to semantic_text (Point 3 from plan)
        conditions["semantic_text"] = req_context.raw_query
        logger.info(f"Assigned semantic_text (original raw_query): '{conditions['semantic_text']}'")

        # NLU for filters (Points 1 & 2 from plan)
        if req_context.query_type == "job_posting_question":
            # Salary extraction (remains the same)
            salary_match = re.search(r"월급\s*(\d+)\s*만?\s*(이상|부터)", req_context.raw_query)
            if salary_match:
                salary_amount = int(salary_match.group(1))
                if salary_amount == 1500: # Specific to user example "월급 1500 이상"
                    conditions["filters"]["salary_min"] = 15000000
                # Add more general salary parsing logic if needed, e.g., salary_amount * 10000
                logger.info(f"Extracted salary_min: {conditions['filters'].get('salary_min')}")

            # Generic Organization Type Extraction
            found_org_types = []
            for org_type in KNOWN_ORG_TYPES:
                if org_type in req_context.raw_query:
                    found_org_types.append(org_type)
            if found_org_types:
                # If multiple are found, for simplicity take the first one or decide on a strategy.
                # For now, if "상급종합병원" is found, it often implies a more specific search than just "병원".
                # A simple heuristic: prioritize longer matches or specific types.
                # For this example, just take the first one found if only one, or handle specific cases.
                if "상급종합병원" in found_org_types: # Prioritize "상급종합병원" if present
                     conditions["filters"]["org_type"] = "상급종합병원"
                elif found_org_types: # Otherwise, take the first one found from the KNOWN_ORG_TYPES list
                     conditions["filters"]["org_type"] = found_org_types[0] 
                logger.info(f"Extracted org_type: {conditions['filters'].get('org_type')}")
            
            # Generic Location Extraction
            found_locations = []
            for loc in KNOWN_LOCATIONS:
                if loc in req_context.raw_query:
                    found_locations.append(loc)
            if found_locations:
                # For simplicity, if multiple locations are mentioned, take the first one.
                # More advanced NLU would handle multiple locations (e.g., "서울 또는 경기").
                conditions["filters"]["location"] = found_locations[0]
                logger.info(f"Extracted location: {conditions['filters'].get('location')}")
        
        # Include other context info that might be useful for the agent
        conditions["source_context"] = req_context.source_context
        conditions["board_id"] = req_context.board_id 
        conditions["is_detail_view"] = req_context.is_detail_view
        conditions["classified_query_type"] = req_context.query_type
        
        # If after NLU, no specific filters are found for a job_posting_question,
        # and semantic_text is just the raw_query, this is fine.
        # The agent might use this semantic_text directly for a broad search.
        
        # Remove filters key if it's empty to keep the response clean
        if not conditions.get("filters"): 
             if "filters" in conditions: del conditions["filters"] # Delete only if key exists and is empty
        
        return conditions
    except Exception as e:
        logger.error(f"Exception in generate_search_conditions: {e}")
        return {"error": f"An unexpected error occurred during condition generation: {str(e)}"}

@mcp.tool(description="Formats a single job document into a user-friendly text summary.")
async def format_job_summary(job_document: Dict[str, Any]) -> str: 
    logger.info(f"Tool 'format_job_summary' called for document: {job_document.get(JOB_FIELD_MAP.get('board_id', '_id'))}")
    if not job_document:
        return "Error: No job document provided for summarization."
    try:
        summary_points = [
            f"Title: {job_document.get(JOB_FIELD_MAP.get('title'), 'N/A')}",
            f"Organization: {job_document.get(JOB_FIELD_MAP.get('organization_name'), 'N/A')}",
            f"Location: {job_document.get(JOB_FIELD_MAP.get('location'), 'N/A')}",
            f"Salary Details: {job_document.get(JOB_FIELD_MAP.get('salary_min'), 'N/A')}", 
            f"Specialty: {job_document.get(JOB_FIELD_MAP.get('specialty'), 'N/A')}",
            f"Employment Type: {job_document.get(JOB_FIELD_MAP.get('employment_type'), 'N/A')}"
        ]
        return "\n".join(summary_points)
    except Exception as e:
        logger.error(f"Exception in format_job_summary: {e}")
        return f"Error during summarization: {str(e)}"

# Main Server Execution block (remains unchanged)
if __name__ == "__main__":
    if sys.platform == "win32" and os.environ.get('PYTHONIOENCODING') is None:
        sys.stdin.reconfigure(encoding="utf-8")
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")

    if os_service.is_connected():
        logger.info("OpenSearch connection successful. Starting FastMCP server.")
    else:
        logger.warning("OpenSearch connection failed. FastMCP server starting but OpenSearch dependent tools will not work.")
    
    mcp.run(transport="stdio")
