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

# Updated mapping based on actual field names observed in user profile metadata.
# Keys are field names from user_profile.metadata, values are target filter keys for job search.
USER_TO_JOB_FILTER_MAP = {
    "SPECIALTY": "specialty",          # User's specialty, e.g., '산부인과'
    "WORK_TYPE": "employment_type",    # User's work type, e.g., '교직'
    "OFFICE_ADDR_REGION": "location",  # Extracted region from user's OFFICE_ADDR
    # Add other direct mappings here if available and desired, e.g.:
    # "USER_DESIRED_SALARY_MIN": "salary_min", # If user profile has such a field
}

# Name of the field in user_profile.metadata that contains skills.
# If not present in the example log for gabrielle83, this will extract nothing for her.
USER_SKILLS_FIELD_NAME_IN_PROFILE = "USER_SKILLS" # Or "SKILLS" if that's the actual field name

def generate_user_profile_query(user_id: str) -> dict:
    # This function is assumed to be for a different user index/schema or purpose.
    # It remains unchanged as per the subtask instructions.
    return {"query": {"term": {"ID": user_id}}}

def generate_user_preference_based_job_query(user_profile: dict, semantic_query_parts: list) -> dict:
    filters = {}
    current_semantic_texts = list(semantic_query_parts) # Start with externally provided semantic parts

    user_metadata = user_profile.get("metadata", {})

    for user_profile_key, job_filter_key in USER_TO_JOB_FILTER_MAP.items():
        user_value = None
        if user_profile_key == "OFFICE_ADDR_REGION":
            full_address = user_metadata.get("OFFICE_ADDR")
            if full_address and isinstance(full_address, str):
                # Simple extraction: take the first part of the address (e.g., "경기도")
                # This is a naive approach and might need refinement for robustness.
                user_value = full_address.split(" ")[0]
                if user_value:
                    print(f"Info: Extracted region '{user_value}' from OFFICE_ADDR for location filter.")
        else:
            user_value = user_metadata.get(user_profile_key)

        if user_value:
            filters[job_filter_key] = user_value
            print(f"Info: Applied filter from user profile: {job_filter_key} = {user_value}")
        else:
            print(f"Info: No value found in user profile for '{user_profile_key}' (maps to job filter '{job_filter_key}').")


    # Handle user skills for semantic text
    # Correctly use the constant and provide a default empty list
    user_skills = user_metadata.get(USER_SKILLS_FIELD_NAME_IN_PROFILE, []) 
    # Removed the erroneous line: user_skills = user_metadata.get(user_skills_field_in_profile)
    
    if user_skills: # user_skills will be an empty list if key not found, so this check is fine.
        if isinstance(user_skills, list):
            current_semantic_texts.extend(user_skills)
        elif isinstance(user_skills, str):
            current_semantic_texts.append(user_skills)
        else:
            # Correctly use the constant in the warning message
            print(f"Warning: User skills field '{USER_SKILLS_FIELD_NAME_IN_PROFILE}' is neither a list nor a string. Skills not added.")
            
    # Remove duplicates while preserving order (Python 3.7+)
    current_semantic_texts = list(dict.fromkeys(current_semantic_texts))
    combined_text_query = " ".join(current_semantic_texts).strip()
    
    # This will now call the updated generate_job_search_query.
    # For vector search through this path, this function would need to generate embeddings for combined_text_query
    # and pass query_vector & vector_field_name. Currently, it will rely on text-based fallback.
    # job_query = generate_job_search_query(text_query=combined_text_query, filters=filters) # Original line
    # return job_query # Original line

    # Modified return value as per subtask instructions
    return {'filters': filters, 'semantic_text': combined_text_query}

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
