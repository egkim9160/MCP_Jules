from fastapi import FastAPI, HTTPException, Query, Body
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from collections import Counter # For aggregating applied jobs

from mcp_server.tools import job_search_tool, user_search_tool, query_executor_tool, formatting_tool
from .os_client import init_opensearch_client, get_opensearch_client
from .judgment_utils import analyze_request, RequestContext # New import

# --- Pydantic Models ---
class JobSearchRequest(BaseModel):
    raw_query: str # User's natural language query
    current_url: Optional[str] = None # URL of the page where the agent is invoked
    # Specific filters can still be passed if a more structured search is initiated by the client
    location: Optional[str] = None
    salary_min: Optional[int] = None
    specialty: Optional[str] = None

class JobPostSummary(BaseModel): # Keep as is, or refine based on actual fields from OpenSearch
    board_id: str
    title: str
    organization_name: Optional[str] = None
    location: Optional[str] = None
    specialty: Optional[str] = None
    pay_details: Optional[str] = None 
    # Add _score if returning it
    score: Optional[float] = Field(None, alias="_score")


class ScenarioAResponse(BaseModel):
    message: str
    request_context: Optional[Dict[str, Any]] = None # To show the analyzed context
    query_generated: Optional[dict] = None
    results_count: int
    # results_summary: Optional[str] = None # Text summary might be less relevant for API
    results_json: Optional[List[JobPostSummary]] = None # Use a list of structured job posts


# (Other models for B, C, D remain placeholders)
# class ScenarioBRequest(BaseModel): # Will be replaced by the new definition below
#     # For Scenario B, the board_id is key, usually from context (URL)
#     # If triggered explicitly, client might send it.
#     # If implicit from URL, analyze_request will pick it up.
#     raw_query: Optional[str] = "이 공고와 비슷한 공고 찾아줘" # Default or user's actual query
#     current_url: str # URL like "www.medigate.net/recruit/1172769"

# New/Updated Pydantic Models for Scenario B
class ScenarioBRequest(BaseModel):
    raw_query: Optional[str] = "이 공고와 비슷한 공고 찾아줘"
    current_url: str = Field(..., description="URL of the page containing the currently viewed job posting, e.g., www.medigate.net/recruit/1172769")

class ScenarioBResponse(BaseModel):
    message: str
    request_context: Optional[Dict[str, Any]] = None
    original_job_id: Optional[str] = None
    query_generated: Optional[dict] = None
    results_count: int
    results_json: Optional[List[JobPostSummary]] = None

# New Pydantic Models for Scenario C
class ScenarioCRequest(BaseModel):
    user_id: str = Field(..., description="The ID of the user for whom to find popular jobs based on similar users.")
    raw_query: Optional[str] = "나와 비슷한 사람들이 많이 지원한 공고 찾아줘" # Or user's actual query
    current_url: Optional[str] = None # For context logging

class ScenarioCResponse(BaseModel):
    message: str
    request_context: Optional[Dict[str, Any]] = None
    target_user_id: str
    similar_users_found: int
    popular_job_ids_found: int
    # query_for_similar_users: Optional[dict] = None # Optional: for debugging
    # query_for_popular_jobs: Optional[dict] = None # Optional: for debugging
    results_json: Optional[List[JobPostSummary]] = None

class ScenarioDRequest(BaseModel):
    user_id: str = Field(..., description="The ID of the user for whom to find suitable jobs.")
    raw_query: str = Field(..., description="User's query, e.g., '내 조건에 맞는 초음파 가능한 내과 공고 찾아줘' or '초음파 gastroenterology jobs'.")
    current_url: Optional[str] = None # For context logging

class ScenarioDResponse(BaseModel):
    message: str
    request_context: Optional[Dict[str, Any]] = None
    target_user_id: str
    query_generated: Optional[dict] = None
    results_count: int
    results_json: Optional[List[JobPostSummary]] = None


app = FastAPI(title="MCP Doctor Job Search API")
JOB_INDEX_NAME = "job_postings_alias" # Define globally or pass as dependency
USER_INDEX_NAME = "user_profiles_alias" # Define globally or pass as dependency

@app.on_event("startup")
async def startup_event():
    print("Application startup: Initializing OpenSearch client...")
    init_opensearch_client()
    try:
        get_opensearch_client().ping()
        print("OpenSearch client connected successfully at startup.")
    except Exception as e:
        print(f"Failed to connect to OpenSearch at startup: {e}")


def original_handle_scenario_a(text_query: str, location: Optional[str], salary_min: Optional[int], specialty: Optional[str], job_index_name: str) -> Dict[str, Any]:
    filters = {}
    # text_query from request.raw_query, other params from specific request fields
    if location: filters["location"] = location
    if salary_min is not None: filters["salary_min"] = salary_min
    if specialty: filters["specialty"] = specialty
    
    # If text_query is very generic like "find jobs" but specific filters are provided,
    # those filters should take precedence.
    # If raw_query is specific, e.g., "서울 지역 마취과", it might override/supplement parameters.
    # For now, use raw_query for semantic and other params for filters.
    
    search_query = job_search_tool.generate_job_search_query(text_query=text_query, filters=filters)
    
    results_raw = query_executor_tool.execute_opensearch_query(index_name=job_index_name, query=search_query)
    
    # Transform raw results into JobPostSummary model instances
    # This assumes JOB_FIELD_MAP keys are used in results_raw
    # and Pydantic model fields align or use aliases.
    # Example: result_raw might have 'JDC.BOARD_IDX', model expects 'board_id'.
    # This needs careful mapping if not using aliases in Pydantic models.
    # For now, let's assume direct mapping or that execute_opensearch_query massages keys.
    # A simple transformation example:
    job_summaries = []
    for res in results_raw:
        summary = JobPostSummary(
            board_id=str(res.get(job_search_tool.JOB_FIELD_MAP["board_id"], res.get("_id", "N/A"))), # Prefer mapped field, ensure string
            title=str(res.get(job_search_tool.JOB_FIELD_MAP["title"], "N/A")),
            organization_name=str(res.get(job_search_tool.JOB_FIELD_MAP["organization_name"])) if res.get(job_search_tool.JOB_FIELD_MAP["organization_name"]) else None,
            location=str(res.get(job_search_tool.JOB_FIELD_MAP["location"])) if res.get(job_search_tool.JOB_FIELD_MAP["location"]) else None,
            specialty=str(res.get(job_search_tool.JOB_FIELD_MAP["specialty"])) if res.get(job_search_tool.JOB_FIELD_MAP["specialty"]) else None, # This is JS.SPECIALTIES
            pay_details=str(res.get(job_search_tool.JOB_FIELD_MAP["salary_min"])) if res.get(job_search_tool.JOB_FIELD_MAP["salary_min"]) else None, # JDC.PAY_DETAILS, simplify
            score=res.get("_score") # Pydantic will handle alias _score
        )
        job_summaries.append(summary)

    return {
        "query_generated": search_query,
        "results_count": len(results_raw),
        "results_json": job_summaries 
    }

# --- API Endpoints ---
@app.post("/scenario/a/search_jobs", response_model=ScenarioAResponse)
async def api_scenario_a(request: JobSearchRequest = Body(...)):
    """
    Scenario A: Direct job search.
    Processes a job search request based on raw query and optional structured filters.
    Incorporates context analysis from the provided URL.
    """
    JOB_INDEX_NAME = "job_postings_alias" # Replace with actual index name or alias from config

    try:
        # 1. Analyze request context
        req_context = analyze_request(raw_query=request.raw_query, url=request.current_url)
        print(f"RequestContext: {req_context}") # Log for debugging

        # For Scenario A, the primary input is often the raw_query or structured filters.
        # If req_context.is_detail_view is true, and raw_query is generic,
        # it might imply a different scenario (like B), but this endpoint is for A.
        # We use req_context.raw_query as the main text_query.
        # Structured filters from the request (request.location, etc.) are also used.

        text_for_semantic_search = req_context.raw_query
        
        # If specific filters are not in raw_query, use the ones from request body
        # This logic might need refinement: how to combine raw_query interpretation vs explicit filters.
        # For now, assume explicit filters complement or specify parts of raw_query.
        
        handler_result = original_handle_scenario_a(
            text_query=text_for_semantic_search, # Parsed from raw_query or directly from it
            location=request.location,           # Explicit filter
            salary_min=request.salary_min,       # Explicit filter
            specialty=request.specialty,         # Explicit filter
            job_index_name=JOB_INDEX_NAME
        )
        
        # RequestContext is not a Pydantic model, so use __dict__
        return ScenarioAResponse(
            message="Scenario A processed.",
            request_context=req_context.__dict__, 
            **handler_result
        )
    except ConnectionError as e:
        raise HTTPException(status_code=503, detail=f"Database connection error: {e}")
    except Exception as e:
        # Log the exception e
        print(f"Error in /scenario/a/search_jobs: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

# (Keep other scenario endpoints as placeholders)
@app.post("/scenario/b/similar_jobs", response_model=ScenarioBResponse)
async def api_scenario_b(request: ScenarioBRequest = Body(...)):
    """
    Scenario B: Find jobs similar to the one currently being viewed.
    Relies on board_id extracted from current_url.
    """
    try:
        # 1. Analyze request to get board_id from URL
        req_context = analyze_request(raw_query=request.raw_query, url=request.current_url)
        print(f"Scenario B - RequestContext: {req_context}")

        if not req_context.board_id or not req_context.is_detail_view:
            raise HTTPException(status_code=400, detail="Board ID could not be determined from the provided URL for Scenario B.")

        current_board_id = req_context.board_id

        # 2. Fetch details of the original job posting
        original_job_query = {
            "query": {
                "term": {
                    job_search_tool.JOB_FIELD_MAP["board_id"]: current_board_id
                }
            },
            "size": 1 # We only need one document
        }
        
        original_job_results = query_executor_tool.execute_opensearch_query(
            index_name=JOB_INDEX_NAME, 
            query=original_job_query
        )

        if not original_job_results:
            raise HTTPException(status_code=404, detail=f"Original job posting with board_id '{current_board_id}' not found.")
        
        original_job_details = original_job_results[0] # Get the first (and only) result

        # 3. Generate query for similar jobs
        similar_jobs_query = job_search_tool.generate_similar_job_query(
            board_id=current_board_id,
            job_details=original_job_details # Pass the whole document source
        )
        print(f"Scenario B - Similar Jobs Query: {similar_jobs_query}")

        # 4. Execute query for similar jobs
        similar_job_results_raw = query_executor_tool.execute_opensearch_query(
            index_name=JOB_INDEX_NAME,
            query=similar_jobs_query
        )

        # 5. Format results (similar to Scenario A's output formatting)
        job_summaries = []
        for res in similar_job_results_raw:
            summary = JobPostSummary(
                board_id=str(res.get(job_search_tool.JOB_FIELD_MAP["board_id"], res.get("_id", "N/A"))),
                title=str(res.get(job_search_tool.JOB_FIELD_MAP["title"], "N/A")),
                organization_name=res.get(job_search_tool.JOB_FIELD_MAP["organization_name"]),
                location=res.get(job_search_tool.JOB_FIELD_MAP["location"]),
                specialty=res.get(job_search_tool.JOB_FIELD_MAP["specialty"]),
                pay_details=str(res.get(job_search_tool.JOB_FIELD_MAP["salary_min"])), # Simplified
                score=res.get("_score")
            )
            job_summaries.append(summary)
            
        return ScenarioBResponse(
            message="Scenario B processed: Found jobs similar to the one viewed.",
            request_context=req_context.__dict__,
            original_job_id=current_board_id,
            query_generated=similar_jobs_query,
            results_count=len(job_summaries),
            results_json=job_summaries
        )
    except ConnectionError as e:
        raise HTTPException(status_code=503, detail=f"Database connection error: {e}")
    except HTTPException: # Re-raise HTTPExceptions directly
        raise
    except Exception as e:
        print(f"Error in /scenario/b/similar_jobs: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.post("/scenario/c/popular_jobs_for_similar_users", response_model=ScenarioCResponse)
async def api_scenario_c(request: ScenarioCRequest = Body(...)):
    """
    Scenario C: Find job postings popular among users similar to the target user.
    """
    try:
        req_context = analyze_request(raw_query=request.raw_query, url=request.current_url)
        print(f"Scenario C - RequestContext: {req_context}")

        # 1. Fetch Target User's Profile
        target_user_profile_query = user_search_tool.generate_user_profile_query(user_id=request.user_id)
        
        target_user_results = query_executor_tool.execute_opensearch_query(
            index_name=USER_INDEX_NAME,
            query=target_user_profile_query
        )
        if not target_user_results:
            raise HTTPException(status_code=404, detail=f"Target user with ID '{request.user_id}' not found.")
        target_user_profile = target_user_results[0]

        # 2. Find Similar Users
        similar_users_query = user_search_tool.generate_similar_users_query(user_profile=target_user_profile)
        # For debugging: print(f"Similar Users Query: {similar_users_query}")
        
        similar_users_results = query_executor_tool.execute_opensearch_query(
            index_name=USER_INDEX_NAME,
            query=similar_users_query
        )
        
        if not similar_users_results:
            return ScenarioCResponse(
                message="No similar users found for the target user.",
                request_context=req_context.__dict__,
                target_user_id=request.user_id,
                similar_users_found=0,
                popular_job_ids_found=0,
                results_json=[]
            )

        # 3. Aggregate Applied Jobs from Similar Users
        all_applied_job_ids = []
        # Assume user documents have a field like 'applied_jobs': ['id1', 'id2']
        # This field name ('applied_jobs') needs to match the actual User DB structure.
        for user_doc in similar_users_results:
            applied_ids = user_doc.get("applied_jobs") # Or "applied_job_ids", "지원한공고ID목록" etc.
            if isinstance(applied_ids, list):
                all_applied_job_ids.extend(applied_ids)
        
        if not all_applied_job_ids:
            return ScenarioCResponse(
                message="Similar users found, but they have not applied to any jobs or applied job data is missing.",
                request_context=req_context.__dict__,
                target_user_id=request.user_id,
                similar_users_found=len(similar_users_results),
                popular_job_ids_found=0,
                results_json=[]
            )

        # Count frequency of each board_id
        job_id_counts = Counter(all_applied_job_ids)
        # Get top N most popular job IDs, e.g., top 5
        TOP_N_POPULAR_JOBS = 5 # This N should be configurable.
        popular_job_ids = [item[0] for item in job_id_counts.most_common(TOP_N_POPULAR_JOBS)]

        if not popular_job_ids:
             return ScenarioCResponse( # Should not happen if all_applied_job_ids was not empty
                message="No popular job IDs derived from similar users' applications.",
                request_context=req_context.__dict__,
                target_user_id=request.user_id,
                similar_users_found=len(similar_users_results),
                popular_job_ids_found=0,
                results_json=[]
            )

        # 4. Fetch Popular Job Postings from Job DB
        popular_jobs_query = {
            "query": {
                "terms": {
                    job_search_tool.JOB_FIELD_MAP["board_id"]: popular_job_ids
                }
            },
            "size": len(popular_job_ids) # Fetch details for all popular IDs found
        }
        # For debugging: print(f"Popular Jobs Query: {popular_jobs_query}")

        popular_job_results_raw = query_executor_tool.execute_opensearch_query(
            index_name=JOB_INDEX_NAME,
            query=popular_jobs_query
        )

        # 5. Format results
        job_summaries = []
        for res in popular_job_results_raw:
            summary = JobPostSummary(
                board_id=str(res.get(job_search_tool.JOB_FIELD_MAP["board_id"], res.get("_id", "N/A"))),
                title=str(res.get(job_search_tool.JOB_FIELD_MAP["title"], "N/A")),
                organization_name=res.get(job_search_tool.JOB_FIELD_MAP["organization_name"]),
                location=res.get(job_search_tool.JOB_FIELD_MAP["location"]),
                specialty=res.get(job_search_tool.JOB_FIELD_MAP["specialty"]),
                pay_details=str(res.get(job_search_tool.JOB_FIELD_MAP["salary_min"])), # Simplified
                score=res.get("_score")
            )
            job_summaries.append(summary)

        return ScenarioCResponse(
            message="Scenario C processed: Found jobs popular among similar users.",
            request_context=req_context.__dict__,
            target_user_id=request.user_id,
            similar_users_found=len(similar_users_results),
            popular_job_ids_found=len(job_summaries),
            results_json=job_summaries
        )
    except ConnectionError as e:
        raise HTTPException(status_code=503, detail=f"Database connection error: {e}")
    except HTTPException: # Re-raise HTTPExceptions directly
        raise
    except Exception as e:
        print(f"Error in /scenario/c/popular_jobs_for_similar_users: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.post("/scenario/d/personalized_search", response_model=ScenarioDResponse)
async def api_scenario_d(request: ScenarioDRequest = Body(...)):
    """
    Scenario D: Find job postings suitable for the user's conditions,
    combining profile data with additional query text.
    """
    try:
        # `request.raw_query` is the main input here for additional criteria.
        # `request.user_id` identifies the user profile to use.
        req_context = analyze_request(raw_query=request.raw_query, url=request.current_url)
        print(f"Scenario D - RequestContext: {req_context}")

        # 1. Fetch User's Profile
        user_profile_query = user_search_tool.generate_user_profile_query(user_id=request.user_id)
        
        user_profile_results = query_executor_tool.execute_opensearch_query(
            index_name=USER_INDEX_NAME,
            query=user_profile_query
        )
        if not user_profile_results:
            raise HTTPException(status_code=404, detail=f"User with ID '{request.user_id}' not found.")
        user_profile = user_profile_results[0]

        # 2. Generate Personalized Job Search Query
        # The user's raw_query is treated as additional semantic criteria.
        # generate_user_preference_based_job_query is designed to take profile + semantic parts.
        # It will extract structured preferences from user_profile and combine with raw_query.
        
        # We pass raw_query as a list containing one string, or split it if it makes sense.
        # The current generate_user_preference_based_job_query joins list of semantic_query_parts.
        # So, passing [request.raw_query] is appropriate if it's a single block of text.
        semantic_parts_from_raw_query = [request.raw_query] if request.raw_query.strip() else []

        personalized_job_query = user_search_tool.generate_user_preference_based_job_query(
            user_profile=user_profile,
            semantic_query_parts=semantic_parts_from_raw_query 
        )
        print(f"Scenario D - Personalized Job Query: {personalized_job_query}")
        
        # 3. Execute Query against Job DB
        job_results_raw = query_executor_tool.execute_opensearch_query(
            index_name=JOB_INDEX_NAME,
            query=personalized_job_query
        )

        # 4. Format Results
        job_summaries = []
        for res in job_results_raw:
            summary = JobPostSummary(
                board_id=str(res.get(job_search_tool.JOB_FIELD_MAP["board_id"], res.get("_id", "N/A"))),
                title=str(res.get(job_search_tool.JOB_FIELD_MAP["title"], "N/A")),
                organization_name=res.get(job_search_tool.JOB_FIELD_MAP["organization_name"]),
                location=res.get(job_search_tool.JOB_FIELD_MAP["location"]),
                specialty=res.get(job_search_tool.JOB_FIELD_MAP["specialty"]),
                pay_details=str(res.get(job_search_tool.JOB_FIELD_MAP["salary_min"])), # Simplified
                score=res.get("_score")
            )
            job_summaries.append(summary)

        return ScenarioDResponse(
            message="Scenario D processed: Found personalized job recommendations.",
            request_context=req_context.__dict__,
            target_user_id=request.user_id, # Corrected field name from target__user_id
            query_generated=personalized_job_query,
            results_count=len(job_summaries),
            results_json=job_summaries
        )
    except ConnectionError as e:
        raise HTTPException(status_code=503, detail=f"Database connection error: {e}")
    except HTTPException: # Re-raise HTTPExceptions directly
        raise
    except Exception as e:
        print(f"Error in /scenario/d/personalized_search: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


if __name__ == '__main__':
    # This block is for conceptual testing if running app.py directly.
    # For FastAPI, you'd use: uvicorn mcp_server.server.app:app --reload
    print("MCP Server (FastAPI) - Conceptual")
    print("To run the FastAPI server, use: uvicorn mcp_server.server.app:app --reload --host 0.0.0.0 --port 8000")
    
    # Example direct call to conceptual handler (for testing logic without server)
    # init_opensearch_client() # Ensure client is attempted to init for direct test
    # if get_opensearch_client(): # Check if client is available
    #     print("\n--- Testing Scenario A Handler (Direct Call) ---")
    #     # Ensure JOB_INDEX_NAME is defined if you uncomment this test block
    #     # JOB_INDEX_NAME_TEST = "job_postings_alias" 
    #     test_result_a = original_handle_scenario_a(
    #         text_query="", 
    #         location="Seoul", 
    #         salary_min=30000000, 
    #         specialty="Anesthesiology",
    #         job_index_name="job_postings_alias" # Or JOB_INDEX_NAME_TEST
    #     )
    #     print(f"Handler Result A: {test_result_a}")
    # else:
    #     print("Skipping direct call test as OpenSearch client is not available.")
