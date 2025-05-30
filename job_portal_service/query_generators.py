# job_portal_service/query_generators.py
import re 
from typing import Optional, List, Dict, Any 

JOB_FIELD_MAP = {
    "board_id": "metadata.BOARD_IDX", "title": "metadata.TITLE", 
    "specialty": "metadata.SPECIALTIES", "salary_min": "metadata.PAY_DETAILS", 
    "salary_max": "metadata.PAY_DETAILS", "pay_details_text": "metadata.PAY_DETAILS", 
    "location": "metadata.REGION_NAME", "organization_name": "metadata.ORGANIZATION_NAME",
    "org_type": "metadata.ORG_TYPE_NAME", "night_work": "metadata.NIGHT_WORK_STATUS", 
    "weekend_work": "metadata.WEEKEND_WORK_STATUS", "holiday_work": "metadata.H_WORK_STATUS", 
    "employment_type": "metadata.REGULAR_STATUS", "nego_status": "metadata.NEGO_STATUS", 
    "incentive_status": "metadata.INCENTIVE_STATUS", "work_hour_details": "metadata.WORK_HOUR_DETAILS", 
    "s_work_status": "metadata.S_WORK_STATUS", "labor_law_status": "metadata.LABOR_LAW_STATUS",
    "meal_house_status": "metadata.MEAL_HOUSE_STATUS", "attend_status": "metadata.ATTEND_STATUS",
    "insu_status": "metadata.INSU_STATUS", "address": "metadata.ADDRESS",
    "job_reg_date": "metadata.JOB_REG_DATE", "content_semantic": "text", 
}

def generate_job_search_query(
    text_query: str,  # Original raw query, used for fallback text search if no vector
    filters: dict,
    query_vector: Optional[List[float]] = None, 
    vector_field_name: Optional[str] = None, 
    default_knn_k: int = 10 
) -> dict:
    bool_query_parts: Dict[str, List[Dict[str, Any]]] = {
        "must": [],
        "filter": [],
        "should": [],
        "must_not": []
    }
    
    # 1. Metadata Filters (excluding salary)
    salary_os_fields = []
    if JOB_FIELD_MAP.get("salary_min"): salary_os_fields.append(JOB_FIELD_MAP["salary_min"])
    if JOB_FIELD_MAP.get("salary_max"): salary_os_fields.append(JOB_FIELD_MAP["salary_max"])
    salary_os_fields = list(set(salary_os_fields)) 
    
    for key, value in filters.items():
        if key not in JOB_FIELD_MAP:
            print(f"Warning (generate_job_search_query): Unmapped filter key '{key}'")
            continue
        
        field_name = JOB_FIELD_MAP[key]
        
        if field_name in salary_os_fields: 
            print(f"Info (generate_job_search_query): Salary filter for '{key}' (maps to OS field '{field_name}') is being skipped.")
            continue 

        if key in ["specialty", "location", "org_type", "employment_type", "organization_name", "title", "work_hour_details", "pay_details_text", "address"]:
             bool_query_parts["filter"].append({"match": {field_name: value}})
        elif key in ["night_work", "weekend_work", "s_work_status", "nego_status", "incentive_status", "labor_law_status", "meal_house_status", "attend_status", "insu_status", "holiday_work"]:
            bool_query_parts["filter"].append({"term": {field_name: str(value).upper() if isinstance(value, str) else value }})
        else: 
            bool_query_parts["filter"].append({"term": {field_name: value}})

    # 2. Semantic Search Part
    if query_vector and vector_field_name:
        # If vector is provided, use KNN as the primary semantic search component.
        # The text_query (original raw query) is NOT used for an additional "match" query here.
        knn_clause = {
            "knn": {
                vector_field_name: {
                    "vector": query_vector,
                    "k": default_knn_k 
                }
            }
        }
        bool_query_parts["must"].append(knn_clause)
        print("Info (generate_job_search_query): Vector search active. Semantic matching via KNN.")
                
    elif text_query and text_query.strip(): # Fallback to text match if no vector
        meaningful_text_query = text_query
        common_leftovers = ["공고만 보고 싶어", "공고만 보여줘", "만 보고 싶어", "만 보여줘", "보고 싶어", "보여줘", "찾아줘", "알려줘"]
        for phrase in common_leftovers: 
            meaningful_text_query = meaningful_text_query.replace(phrase, "").strip()
        meaningful_text_query = re.sub(r'\s+', ' ', meaningful_text_query).strip() 

        if meaningful_text_query and not meaningful_text_query.isdigit():
            # Use the JOB_FIELD_MAP["content_semantic"] which should map to "text" (the concatenated field)
            bool_query_parts["must"].append({"match": {JOB_FIELD_MAP["content_semantic"]: meaningful_text_query}})
            print(f"Info (generate_job_search_query): Fallback text search active on '{JOB_FIELD_MAP['content_semantic']}' with: '{meaningful_text_query}'")
        else:
            print(f"Info (generate_job_search_query): No vector and no meaningful text_query ('{text_query}') for content_semantic match.")

    # Construct final query
    final_query_bool: Dict[str, Any] = {}
    for part_name, clauses in bool_query_parts.items():
        if clauses:
            final_query_bool[part_name] = clauses
            
    if not final_query_bool: 
        return {"query": {"match_all": {}}} 
    else:
        return {"query": {"bool": final_query_bool}}

# (Other functions like generate_user_profile_query, generate_user_preference_based_job_query, 
#  generate_similar_users_query, and generate_similar_job_query remain unchanged)
# Make sure they are present in the actual file if they were there before.
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
    # For vector search through this path, this function would need to generate embeddings for combined_text_query
    # and pass query_vector & vector_field_name. Currently, it will rely on text-based fallback.
    job_query = generate_job_search_query(text_query=combined_text_query, filters=filters)
    return job_query

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
    semantic_content_for_mlt = job_details.get(JOB_FIELD_MAP["content_semantic"]) 
    if semantic_content_for_mlt:
        should_clauses.append({
            "more_like_this": {
                "fields": [JOB_FIELD_MAP["title"], JOB_FIELD_MAP["content_semantic"]], 
                "like": semantic_content_for_mlt,
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
