# job_portal_service/query_generators.py
import re 
from typing import Optional, List, Dict, Any # Ensure these are imported

# JOB_FIELD_MAP definition (ensure it's complete and accurate as per previous steps)
JOB_FIELD_MAP = {
    "board_id": "JDC.BOARD_IDX",
    "title": "JDC.TITLE",
    "content_semantic": "JDC.CLEAN_CONTENT", 
    "specialty": "JS.SPECIALTIES", 
    "salary_min": "JDC.PAY_DETAILS", 
    "salary_max": "JDC.PAY_DETAILS", 
    "location": "JDC.REGION_NAME", 
    "organization_name": "JDC.ORGANIZATION_NAME",
    "org_type": "JDC.ORG_TYPE_NAME",
    "night_work": "JDC.NIGHT_WORK_STATUS", 
    "weekend_work": "JDC.WEEKEND_WORK_STATUS", 
    "holiday_work": "JDC.H_WORK_STATUS", 
    "employment_type": "JDC.REGULAR_STATUS", 
    # Add other fields as needed, e.g., the vector field name if it's static
    # "vector_field": "your_actual_vector_field_name_in_opensearch" # Example
}

# --- generate_job_search_query function ---
def generate_job_search_query(
    text_query: str, 
    filters: dict,
    query_vector: Optional[List[float]] = None, 
    vector_field_name: Optional[str] = None, 
    default_knn_k: int = 10 
) -> dict:
    """
    Generates an OpenSearch search query.
    Supports hybrid search (vector KNN + metadata filters) if query_vector is provided.
    Falls back to text match + metadata filters otherwise.
    Salary filters are currently excluded.
    """
    
    bool_query_parts: Dict[str, List[Dict[str, Any]]] = {
        "must": [],
        "filter": [],
        "should": [], # Not used in current logic but good to have for future
        "must_not": [] # Not used in current logic
    }
    
    # 1. Metadata Filters (excluding salary)
    # These field names come directly from OpenSearch mapping, not the simple filter keys
    salary_os_fields = []
    if JOB_FIELD_MAP.get("salary_min"): salary_os_fields.append(JOB_FIELD_MAP["salary_min"])
    if JOB_FIELD_MAP.get("salary_max"): salary_os_fields.append(JOB_FIELD_MAP["salary_max"])
    # Remove duplicates if salary_min and salary_max map to the same OS field
    salary_os_fields = list(set(salary_os_fields)) 
    
    for key, value in filters.items():
        if key not in JOB_FIELD_MAP:
            print(f"Warning (generate_job_search_query): Unmapped filter key '{key}'")
            continue
        
        field_name = JOB_FIELD_MAP[key]
        
        if field_name in salary_os_fields: # Check against the OpenSearch field name
            print(f"Info (generate_job_search_query): Salary filter for '{key}' (maps to OS field '{field_name}') is being skipped as per current configuration.")
            continue 

        if key in ["night_work", "weekend_work"]: 
            bool_query_parts["filter"].append({"term": {field_name: str(value).upper()}})
        elif key in ["specialty", "location", "org_type"]: 
             bool_query_parts["filter"].append({"match": {field_name: value}})
        else: 
            bool_query_parts["filter"].append({"term": {field_name: value}})

    # 2. Semantic Search Part (Vector KNN or Text Match)
    meaningful_text_query = ""
    if text_query and text_query.strip():
        temp_text_query = text_query
        common_leftovers = ["공고만 보고 싶어", "공고만 보여줘", "만 보고 싶어", "만 보여줘", "보고 싶어", "보여줘", "찾아줘", "알려줘"]
        # Remove common trailing phrases that don't add semantic value
        for phrase in common_leftovers:
            if temp_text_query.endswith(phrase):
                temp_text_query = temp_text_query[:-len(phrase)].strip()
        if temp_text_query and not temp_text_query.isdigit(): # Avoid using if only digits remain
            meaningful_text_query = temp_text_query

    if query_vector and vector_field_name:
        knn_clause = {
            "knn": {
                vector_field_name: {
                    "vector": query_vector,
                    "k": default_knn_k 
                }
            }
        }
        bool_query_parts["must"].append(knn_clause)
        
        # If meaningful_text_query also exists, add it for hybrid keyword + vector search
        if meaningful_text_query:
            bool_query_parts["must"].append({"match": {JOB_FIELD_MAP["content_semantic"]: meaningful_text_query}})
                
    elif meaningful_text_query: # Fallback to text match if no vector but meaningful text exists
        bool_query_parts["must"].append({"match": {JOB_FIELD_MAP["content_semantic"]: meaningful_text_query}})

    # Construct final query
    final_query_bool: Dict[str, Any] = {}
    for part_name, clauses in bool_query_parts.items():
        if clauses:
            final_query_bool[part_name] = clauses
            
    if not final_query_bool: # If bool is empty (no filters, no semantic search part)
        return {"query": {"match_all": {}}} # Match all documents
    else:
        return {"query": {"bool": final_query_bool}}


# --- generate_user_profile_query function ---
# (Keep existing definition from query_generators.py)
USER_TO_JOB_FILTER_MAP = {
    "희망_근무지역": "location", 
    "희망_근무형태": "employment_type",
    "전문과목": "specialty",
}
USER_SEMANTIC_FIELDS = {
    "핵심_술기": "skills",
}
def generate_user_profile_query(user_id: str) -> dict:
    return {"query": {"term": {"ID": user_id}}}

# --- generate_user_preference_based_job_query function ---
# (Keep existing definition from query_generators.py, it uses generate_job_search_query internally)
def generate_user_preference_based_job_query(user_profile: dict, semantic_query_parts: list) -> dict:
    filters = {}
    current_semantic_texts = list(semantic_query_parts)
    if user_profile.get("전문과목 및 진료분야"):
        filters[USER_TO_JOB_FILTER_MAP["전문과목"]] = user_profile["전문과목 및 진료분야"]
    hopeful_conditions = user_profile.get("희망 근무조건", {})
    if isinstance(hopeful_conditions, dict):
        if hopeful_conditions.get("근무지역"):
            filters[USER_TO_JOB_FILTER_MAP["희망_근무지역"]] = hopeful_conditions["근무지역"]
        if hopeful_conditions.get("근무형태"):
            filters[USER_TO_JOB_FILTER_MAP["희망_근무형태"]] = hopeful_conditions["근무형태"]
    core_skills = user_profile.get("핵심 술기", [])
    if isinstance(core_skills, list):
        for skill_entry in core_skills:
            if isinstance(skill_entry, dict) and skill_entry.get("술기명"):
                current_semantic_texts.append(skill_entry["술기명"])
    combined_text_query = " ".join(current_semantic_texts)
    # This will now call the updated generate_job_search_query.
    # If vector search is desired for this path, this function would also need to handle vector generation
    # and pass query_vector & vector_field_name to generate_job_search_query.
    # For now, it will use the text-based fallback within generate_job_search_query.
    job_query = generate_job_search_query(text_query=combined_text_query, filters=filters)
    return job_query

# --- generate_similar_users_query function ---
# (Keep existing definition from query_generators.py)
def generate_similar_users_query(user_profile: dict) -> dict:
    should_clauses = []
    must_not_clauses = [{"term": {"ID": user_profile.get("ID", "")}}] 
    if user_profile.get("전문과목 및 진료분야"):
        should_clauses.append({"match": {"전문과목 및 진료분야": user_profile["전문과목 및 진료분야"]}})
    hopeful_conditions = user_profile.get("희망 근무조건", {})
    if isinstance(hopeful_conditions, dict):
        if hopeful_conditions.get("근무지역"):
            should_clauses.append({"match": {"희망 근무조건.근무지역": hopeful_conditions["근무지역"]}})
        if hopeful_conditions.get("진료과목"):
            should_clauses.append({"match": {"희망 근무조건.진료과목": hopeful_conditions["진료과목"]}})
    query = {
        "query": {
            "bool": {
                "should": should_clauses,
                "must_not": must_not_clauses,
                "minimum_should_match": 1 if should_clauses else 0
            }
        }
    }
    return query

# generate_similar_job_query (from original job_search_tool.py content, ensure it's here)
# This was defined in query_generators.py in a previous step.
def generate_similar_job_query(board_id: str, job_details: dict) -> dict:
    must_clauses = []
    should_clauses = []
    if job_details.get(JOB_FIELD_MAP["specialty"]):
        should_clauses.append({
            "match": {JOB_FIELD_MAP["specialty"]: job_details[JOB_FIELD_MAP["specialty"]]}
        })
    if job_details.get(JOB_FIELD_MAP["location"]):
        should_clauses.append({
            "match": {JOB_FIELD_MAP["location"]: job_details[JOB_FIELD_MAP["location"]]}
        })
    if job_details.get(JOB_FIELD_MAP["org_type"]):
        should_clauses.append({
            "term": {JOB_FIELD_MAP["org_type"]: job_details[JOB_FIELD_MAP["org_type"]]}
        })
    if job_details.get(JOB_FIELD_MAP["content_semantic"]):
        should_clauses.append({
            "more_like_this": {
                "fields": [JOB_FIELD_MAP["content_semantic"], JOB_FIELD_MAP["title"]],
                "like": job_details[JOB_FIELD_MAP["content_semantic"]],
                "min_term_freq": 1,
                "max_query_terms": 12
            }
        })
    query = {
        "query": {
            "bool": {
                "must": must_clauses,
                "should": should_clauses,
                "must_not": [
                    {"term": {JOB_FIELD_MAP["board_id"]: board_id}}
                ],
                "minimum_should_match": 1 if should_clauses else 0 
            }
        }
    }
    return query
