# --- Content from mcp_server/tools/job_search_tool.py ---

# Expected structure for job posting data (example):
# {
#     "board_id": "12345",
#     "title": "Cardiologist Position in Seoul",
#     "hospital_name": "Seoul Central Hospital",
#     "location": "Seoul", # 지역
#     "specialty": "Cardiology", # 전문과
#     "salary": 50000000, # 연봉
#     "description": "Looking for an experienced cardiologist...",
#     "requirements": "MD, Cardiology Specialization",
# }

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
}

def generate_job_search_query(text_query: str, filters: dict) -> dict:
    """
    Generates a search query for job postings using specific field names.
    - text_query: Natural language query for semantic search part (targets JDC.CLEAN_CONTENT).
    - filters: Dictionary of specific criteria (e.g., {"location": "Seoul", "salary_min": 30000000}).
    Returns an OpenSearch query dictionary.
    """
    query = {
        "query": {
            "bool": {
                "must": [],
                "filter": []
            }
        }
    }

    if text_query:
        query["query"]["bool"]["must"].append({
            "match": {
                JOB_FIELD_MAP["content_semantic"]: text_query
            }
        })

    for key, value in filters.items():
        if key not in JOB_FIELD_MAP:
            print(f"Warning: Unmapped filter key '{key}'")
            continue
        
        field_name = JOB_FIELD_MAP[key]

        if key == "salary_min":
            query["query"]["bool"]["filter"].append({
                "range": { field_name: {"gte": value} }
            })
        elif key == "salary_max":
            query["query"]["bool"]["filter"].append({
                "range": { field_name: {"lte": value} }
            })
        elif key in ["night_work", "weekend_work"]:
            query["query"]["bool"]["filter"].append({
                "term": {field_name: value.upper()}
            })
        elif key == "specialty":
             query["query"]["bool"]["filter"].append({
                "match": {field_name: value}
            })
        elif key == "location":
            query["query"]["bool"]["filter"].append({
                "match": {field_name: value}
            })
        else:
            query["query"]["bool"]["filter"].append({
                "term": {field_name: value}
            })
            
    return query

def generate_similar_job_query(board_id: str, job_details: dict) -> dict:
    """
    Generates a query to find jobs similar to the one specified by board_id.
    - board_id: The ID of the job posting to find similar ones for.
    - job_details: The details of the job posting (using new field names).
    Returns an OpenSearch query dictionary for similar jobs.
    """
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

# --- Content from mcp_server/tools/user_search_tool.py ---

# Mapping from user profile keys (simplified) to job search filter keys or direct values
USER_TO_JOB_FILTER_MAP = {
    "희망_근무지역": "location", 
    "희망_근무형태": "employment_type",
    "전문과목": "specialty",
}

# User fields that contribute to semantic query text
USER_SEMANTIC_FIELDS = {
    "핵심_술기": "skills",
}

def generate_user_profile_query(user_id: str) -> dict:
    """
    Generates a query to fetch a specific user's profile.
    - user_id: The ID of the user.
    Returns an OpenSearch query dictionary.
    """
    return {"query": {"term": {"ID": user_id}}}

def generate_user_preference_based_job_query(user_profile: dict, semantic_query_parts: list) -> dict:
    """
    Generates a job search query based on user preferences and additional semantic parts.
    - user_profile: Dictionary containing the user's information.
    - semantic_query_parts: List of additional terms for semantic search.
    Returns an OpenSearch query dictionary for jobs.
    """
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
    
    # Call generate_job_search_query directly as it's in the same module now
    job_query = generate_job_search_query(text_query=combined_text_query, filters=filters)
    return job_query

def generate_similar_users_query(user_profile: dict) -> dict:
    """
    Generates a query to find users with profiles similar to the given user_profile.
    - user_profile: Dictionary containing the user's information.
    Returns an OpenSearch query dictionary for users.
    """
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
