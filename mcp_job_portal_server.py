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
    JOB_FIELD_MAP, # Still needed for format_job_summary
    generate_user_preference_based_job_query # Added for personalization
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
    original_query_dsl_for_debug = json.dumps(query_dsl, indent=2) # For logging original
    logger.debug(f"Original Query DSL: {original_query_dsl_for_debug}")

    if not os_service.is_connected():
        return [{"error": "OpenSearch service is not connected."}]

    # Logic to modify _source to exclude "vector_field"
    vector_field_to_exclude = "vector_field"
    modified_source = False

    if "_source" not in query_dsl:
        query_dsl["_source"] = {"excludes": [vector_field_to_exclude]}
        logger.info(f"Applied '{vector_field_to_exclude}' exclusion: No existing '_source' key, added new one.")
        modified_source = True
    else:
        source_config = query_dsl["_source"]
        if isinstance(source_config, dict):
            if "excludes" in source_config:
                if isinstance(source_config["excludes"], list):
                    if vector_field_to_exclude not in source_config["excludes"]:
                        source_config["excludes"].append(vector_field_to_exclude)
                        logger.info(f"Applied '{vector_field_to_exclude}' exclusion: Appended to existing 'excludes' list.")
                        modified_source = True
                    else:
                        logger.info(f"'{vector_field_to_exclude}' exclusion: Already present in 'excludes' list.")
                else:
                    # excludes is not a list, this is unusual. Log and don't modify.
                    logger.warning(f"Cannot apply '{vector_field_to_exclude}' exclusion: '_source.excludes' is not a list. Current value: {source_config['excludes']}")
            else: # No "excludes" key in _source dictionary
                source_config["excludes"] = [vector_field_to_exclude]
                logger.info(f"Applied '{vector_field_to_exclude}' exclusion: Added 'excludes' key to existing '_source' dict.")
                modified_source = True
        elif isinstance(source_config, list):
            logger.warning(f"Cannot apply '{vector_field_to_exclude}' exclusion: '_source' is an include list. Modifying it could override explicit field selection. Query DSL not modified for _source.")
        elif isinstance(source_config, bool):
            if source_config is True:
                query_dsl["_source"] = {"excludes": [vector_field_to_exclude]}
                logger.info(f"Applied '{vector_field_to_exclude}' exclusion: Changed '_source: true' to exclude config.")
                modified_source = True
            else: # _source is False
                logger.info(f"No action for '{vector_field_to_exclude}' exclusion: '_source' is already false.")
        elif isinstance(source_config, str):
            logger.warning(f"Cannot apply '{vector_field_to_exclude}' exclusion: '_source' is a string pattern ('{source_config}'). Modifying it could override explicit field selection. Query DSL not modified for _source.")
        else:
            logger.warning(f"Cannot apply '{vector_field_to_exclude}' exclusion: '_source' is of an unexpected type ('{type(source_config)}'). Query DSL not modified for _source.")

    if modified_source:
        logger.debug(f"Modified Query DSL after _source processing: {json.dumps(query_dsl, indent=2)}")
    
    try:
        if size is not None:
            query_dsl['size'] = size
        
        results = os_service.execute_query(index_name=index_name, query=query_dsl) # execute_query itself also excludes "vector_field" by default now. This tool-level modification makes it explicit for direct DSL calls.
        if not results:
            logger.warning(f"No results from opensearch_query_executor for index '{index_name}'. Query (after potential _source mod): {json.dumps(query_dsl)}")
        return results
    except Exception as e:
        logger.error(f"Exception in opensearch_query_executor: {e}")
        return [{"error": f"An unexpected error occurred during query execution: {str(e)}"}]

@mcp.tool(description="Analyzes raw query and URL to generate structured search conditions (filters, semantic text) for job searches. Optionally accepts a 'uid' to personalize conditions based on user profile.")
async def generate_search_conditions(raw_query: str, url_context: Optional[str] = None, uid: Optional[str] = None) -> Dict[str, Any]:
    logger.info(f"Tool 'generate_search_conditions' called with raw_query: '{raw_query}', url_context: '{url_context}', uid: '{uid}'")
    try:
        req_context = analyze_request(raw_query=raw_query, url=url_context)
        logger.info(f"RequestContext for generate_search_conditions: {req_context}")

        conditions: Dict[str, Any] = {"filters": {}, "semantic_text": "", "personalization_applied": False}
        
        # Initialize semantic_text with raw_query if it exists
        if req_context.raw_query and req_context.raw_query.strip():
            conditions["semantic_text"] = req_context.raw_query.strip()
            logger.info(f"Initialized semantic_text with raw_query: '{conditions['semantic_text']}'")

        # Personalization based on UID
        if uid:
            logger.info(f"UID '{uid}' provided, attempting to fetch user profile for personalization.")
            user_profile_data = os_service.fetch_user_data_by_uid(uid) # This is a synchronous call

            if user_profile_data:
                # Log the fetched user profile metadata
                user_metadata_for_log = user_profile_data.get('metadata', {})
                logger.info(f"Fetched user profile for UID '{uid}'. Metadata used for personalization: {user_metadata_for_log}")
                
                # The original log message about successful fetch can be kept or removed if the new one is sufficient.
                # For clarity, let's assume the new one replaces the previous generic "Successfully fetched..." message.
                # logger.info(f"Successfully fetched user profile data for UID '{uid}'.") # This line can be removed or kept. Let's remove for less verbose logs.

                # Prepare semantic_query_parts for generate_user_preference_based_job_query
                # Use existing semantic_text (derived from raw_query) as a base
                semantic_query_parts_from_raw_query = [conditions["semantic_text"]] if conditions["semantic_text"] else []
                
                try:
                    user_personalized_components = generate_user_preference_based_job_query(
                        user_profile=user_profile_data, 
                        semantic_query_parts=semantic_query_parts_from_raw_query
                    )
                    # user_personalized_components is expected to be {'filters': {...}, 'semantic_text': "..."}
                    
                    # Merge filters (user profile filters take precedence)
                    if user_personalized_components.get("filters"):
                        logger.info(f"Original filters from NLU (before merge): {conditions['filters']}")
                        logger.info(f"Filters from user profile: {user_personalized_components['filters']}")
                        conditions["filters"].update(user_personalized_components["filters"])
                        logger.info(f"Merged filters: {conditions['filters']}")
                    
                    # Refined semantic text combination
                    original_semantic_text_from_raw_query = conditions["semantic_text"].strip() # Already initialized from raw_query
                    user_derived_semantic_text = user_personalized_components.get("semantic_text", "").strip()

                    if not user_derived_semantic_text or user_derived_semantic_text == original_semantic_text_from_raw_query:
                        logger.info(f"User profile semantic content ('{user_derived_semantic_text}') is similar to or derived from raw query ('{original_semantic_text_from_raw_query}'); using original semantic text.")
                        # conditions["semantic_text"] remains original_semantic_text_from_raw_query (already set and stripped)
                        conditions["semantic_text"] = original_semantic_text_from_raw_query # Ensure it's the stripped version
                    else:
                        logger.info(f"Augmenting semantic text with user profile keywords. Original: '{original_semantic_text_from_raw_query}', User-derived: '{user_derived_semantic_text}'")
                        if original_semantic_text_from_raw_query: # Avoid leading space if original is empty
                            conditions["semantic_text"] = f"{original_semantic_text_from_raw_query} {user_derived_semantic_text}".strip()
                        else:
                            conditions["semantic_text"] = user_derived_semantic_text
                        logger.info(f"Final combined semantic_text: '{conditions['semantic_text']}'")
                    
                    conditions["personalization_applied"] = True
                    logger.info(f"Personalization applied for UID '{uid}'.")
                except Exception as e_pref:
                    logger.error(f"Error during generate_user_preference_based_job_query for UID '{uid}': {e_pref}")
                    # Proceed without personalization if this step fails
            else:
                logger.warning(f"No user profile data found for UID '{uid}'. Proceeding without personalization.")

        # NLU for filters (runs regardless of personalization, but personalized filters take precedence if keys overlap)
        if req_context.query_type == "job_posting_question":
            # Salary extraction
            # Check if salary_min is already set by personalization. If so, NLU might not overwrite or could be additive.
            # For now, NLU will attempt to extract. If personalization set it, it might be overwritten if NLU finds one too.
            # A more robust strategy would be to check if the filter is already set.
            if "salary_min" not in conditions["filters"]: # Only run NLU for salary if not already set by user profile
                salary_match = re.search(r"월급\s*(\d+)\s*만?\s*(이상|부터)", req_context.raw_query)
                if salary_match:
                    salary_amount = int(salary_match.group(1))
                    # Assuming salary is in 10k KRW units if "만" is present or implied.
                    # Example: "월급 1500" -> 15,000,000. "월급 500만" -> 5,000,000
                    # This logic might need refinement based on common patterns.
                    # For "월급 1500 이상" -> 15,000,000 (as per original example)
                    # For "월급 500만 이상" -> 5,000,000
                    if "만" in salary_match.group(0) or salary_amount < 1000: # Heuristic: if "만" or small number, assume unit is 만원
                         conditions["filters"]["salary_min"] = salary_amount * 10000
                    else: # Larger numbers might be full amounts
                         conditions["filters"]["salary_min"] = salary_amount 
                    logger.info(f"NLU Extracted salary_min: {conditions['filters'].get('salary_min')}")
            
            # Generic Organization Type Extraction
            if "org_type" not in conditions["filters"]: # Only run NLU if not set by user profile
                found_org_types = []
                for org_type in KNOWN_ORG_TYPES:
                    if org_type in req_context.raw_query:
                        found_org_types.append(org_type)
                if found_org_types:
                    if "상급종합병원" in found_org_types:
                         conditions["filters"]["org_type"] = "상급종합병원"
                    elif found_org_types:
                         conditions["filters"]["org_type"] = found_org_types[0] 
                    logger.info(f"NLU Extracted org_type: {conditions['filters'].get('org_type')}")
            
            # Generic Location Extraction
            if "location" not in conditions["filters"]: # Only run NLU if not set by user profile
                found_locations = []
                for loc in KNOWN_LOCATIONS:
                    if loc in req_context.raw_query:
                        found_locations.append(loc)
                if found_locations:
                    conditions["filters"]["location"] = found_locations[0]
                    logger.info(f"NLU Extracted location: {conditions['filters'].get('location')}")
        
        # Include other context info that might be useful for the agent
        conditions["source_context"] = req_context.source_context
        conditions["board_id"] = req_context.board_id 
        conditions["is_detail_view"] = req_context.is_detail_view
        conditions["classified_query_type"] = req_context.query_type
        
        # Clean up: Remove filters key if it's empty
        if not conditions.get("filters"):
            del conditions["filters"]
        # Clean up: Remove semantic_text if it's empty
        if not conditions.get("semantic_text", "").strip():
            if "semantic_text" in conditions:
                 del conditions["semantic_text"]
        
        logger.info(f"Final conditions: {conditions}")
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
