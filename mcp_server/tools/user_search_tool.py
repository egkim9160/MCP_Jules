# (Keep existing comments about user data structure for context)
# Import JOB_FIELD_MAP from job_search_tool or redefine/extend if necessary for clarity
from .job_search_tool import JOB_FIELD_MAP # Assuming it's made available or copied

# Mapping from user profile keys (simplified) to job search filter keys or direct values
USER_TO_JOB_FILTER_MAP = {
    "희망_근무지역": "location", # Maps to JDC.REGION_NAME via JOB_FIELD_MAP
    "희망_근무형태": "employment_type", # Maps to JDC.REGULAR_STATUS
    "전문과목": "specialty", # Maps to JS.SPECIALTIES
    # 희망_급여 needs parsing similar to job_search_tool's salary filters
}

# User fields that contribute to semantic query text
USER_SEMANTIC_FIELDS = {
    "핵심_술기": "skills", # e.g. "초음파", "대장 내시경"
    # "자기소개서" could also be a source if available and relevant
}


def generate_user_profile_query(user_id: str) -> dict:
    """
    Generates a query to fetch a specific user's profile.
    - user_id: The ID of the user.
    Returns an OpenSearch query dictionary. (Assuming user_id is the document ID or a unique field)
    """
    # This field name 'user_id' for user DB needs to be confirmed from user's table structure.
    # For now, using a generic "user_id_field". User provided "ID" for 회원 정보.
    return {"query": {"term": {"ID": user_id}}}


def generate_user_preference_based_job_query(user_profile: dict, semantic_query_parts: list) -> dict:
    """
    Generates a job search query based on user preferences and additional semantic parts.
    - user_profile: Dictionary containing the user's information (using keys from user's table, e.g., '희망 근무조건', '전문과목 및 진료분야', '핵심 술기').
    - semantic_query_parts: List of additional terms for semantic search (e.g., ["cardiac arrest management"]).
    Returns an OpenSearch query dictionary for jobs.
    """
    filters = {}
    current_semantic_texts = list(semantic_query_parts) # Copy

    # Extract structured preferences from user_profile
    # Example: user_profile might look like:
    # {
    #   "ID": "user001",
    #   "전문과목 및 진료분야": "Cardiology",
    #   "희망 근무조건": {"근무지역": "Seoul", "급여": "연봉 1억", "근무형태": "봉직의"},
    #   "핵심 술기": [{"술기명": "Angioplasty"}, {"술기명": "Echocardiography"}]
    # }

    if user_profile.get("전문과목 및 진료분야"):
        filters[USER_TO_JOB_FILTER_MAP["전문과목"]] = user_profile["전문과목 및 진료분야"]

    hopeful_conditions = user_profile.get("희망 근무조건", {})
    if isinstance(hopeful_conditions, dict):
        if hopeful_conditions.get("근무지역"):
            filters[USER_TO_JOB_FILTER_MAP["희망_근무지역"]] = hopeful_conditions["근무지역"]
        if hopeful_conditions.get("근무형태"):
            filters[USER_TO_JOB_FILTER_MAP["희망_근무형태"]] = hopeful_conditions["근무형태"]
        # Add salary parsing from "급여" if feasible

    # Extract semantic parts from user profile (e.g., skills)
    core_skills = user_profile.get("핵심 술기", [])
    if isinstance(core_skills, list):
        for skill_entry in core_skills:
            if isinstance(skill_entry, dict) and skill_entry.get("술기명"):
                current_semantic_texts.append(skill_entry["술기명"])
    
    combined_text_query = " ".join(current_semantic_texts)

    # Reuse job_search_tool.generate_job_search_query logic
    # Need to import it or have access to it. For now, assume it's available.
    from . import job_search_tool 
    job_query = job_search_tool.generate_job_search_query(text_query=combined_text_query, filters=filters)
    return job_query


def generate_similar_users_query(user_profile: dict) -> dict:
    """
    Generates a query to find users with profiles similar to the given user_profile.
    - user_profile: Dictionary containing the user's information.
    Returns an OpenSearch query dictionary for users.
    """
    # This needs to be based on the actual User DB fields.
    # Example: Find users with same "전문과목 및 진료분야" and "희망 근무조건 > 근무지역"
    # User fields: "전문과목 및 진료분야", "기초의학", "희망 근무조건" (근무형태, 급여, 근무지역, 진료과목)
    
    should_clauses = []
    must_not_clauses = [{"term": {"ID": user_profile.get("ID", "")}}] # Exclude self

    if user_profile.get("전문과목 및 진료분야"):
        should_clauses.append({"match": {"전문과목 및 진료분야": user_profile["전문과목 및 진료분야"]}})
    
    hopeful_conditions = user_profile.get("희망 근무조건", {})
    if isinstance(hopeful_conditions, dict):
        if hopeful_conditions.get("근무지역"):
            should_clauses.append({"match": {"희망 근무조건.근무지역": hopeful_conditions["근무지역"]}}) # Assuming dot notation for nested field
        if hopeful_conditions.get("진료과목"): # 희망 진료과목
            should_clauses.append({"match": {"희망 근무조건.진료과목": hopeful_conditions["진료과목"]}})
            
    # Add more fields for similarity as needed, e.g., "핵심 술기" using more_like_this if skills are indexed well.

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
