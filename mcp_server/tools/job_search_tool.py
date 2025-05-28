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
#     # ... other fields
# }

# Mapping from simple filter keys to OpenSearch field names (and potential type/handling)
JOB_FIELD_MAP = {
    "board_id": "JDC.BOARD_IDX",
    "title": "JDC.TITLE",
    "content_semantic": "JDC.CLEAN_CONTENT", # For semantic search
    "specialty": "JS.SPECIALTIES", # Assuming this is an array or text field suitable for term/match query
    "salary_min": "JDC.PAY_DETAILS", # This will likely need careful handling if PAY_DETAILS is complex
    "salary_max": "JDC.PAY_DETAILS", # Same as above
    "location": "JDC.REGION_NAME", # 시/도, 시/군/구
    "organization_name": "JDC.ORGANIZATION_NAME",
    "org_type": "JDC.ORG_TYPE_NAME",
    "night_work": "JDC.NIGHT_WORK_STATUS", # Y/N
    "weekend_work": "JDC.WEEKEND_WORK_STATUS", # Y/N
    "holiday_work": "JDC.H_WORK_STATUS", # 휴무, 순번근무, 근무
    "employment_type": "JDC.REGULAR_STATUS", # 정규직, 계약직 (JDC.REGULAR_STATUS seems to be for 정규직)
    # Add other important fields from user's list:
    # JDC.INCENTIVE_STATUS, JDC.WORK_HOUR_DETAILS, JDC.MEAL_HOUSE_STATUS, 
    # JDC.ATTEND_STATUS, JDC.INSU_STATUS
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

    # Semantic part
    if text_query:
        query["query"]["bool"]["must"].append({
            "match": {
                JOB_FIELD_MAP["content_semantic"]: text_query
            }
        })

    # Structured filters
    for key, value in filters.items():
        if key not in JOB_FIELD_MAP:
            # Maybe log a warning for unmapped keys, or handle as generic text search if desired
            print(f"Warning: Unmapped filter key '{key}'")
            continue
        
        field_name = JOB_FIELD_MAP[key]

        if key == "salary_min":
            # This is a simplification. JDC.PAY_DETAILS needs proper parsing if it's not a simple number.
            # Assuming for now that a numeric comparison can be made.
            # User mentioned "gross, net (radio), 시행 술기 추가에 따라 인상 가능 (checkbox)"
            # This implies JDC.PAY_DETAILS might be text or a structured object.
            # For this step, we'll assume a numeric sub-field or direct numeric value for range queries.
            # This part will likely need refinement once the exact structure of JDC.PAY_DETAILS is known.
            query["query"]["bool"]["filter"].append({
                "range": {
                    field_name: {"gte": value} # Placeholder if JDC.PAY_DETAILS is directly numeric
                    # Example if it's an object: "JDC.PAY_DETAILS.amount_gross_min": {"gte": value}
                }
            })
        elif key == "salary_max":
            query["query"]["bool"]["filter"].append({
                "range": {
                    field_name: {"lte": value} # Placeholder
                }
            })
        elif key in ["night_work", "weekend_work"]: # Assuming 'Y' or 'N' values
            query["query"]["bool"]["filter"].append({
                "term": {field_name: value.upper()} # Ensure value is 'Y' or 'N'
            })
        elif key == "specialty": # JS.SPECIALTIES might be an array or a delimited string
             query["query"]["bool"]["filter"].append({
                "match": {field_name: value} # Using match for potentially analyzed text or array elements
            })
        elif key == "location": # JDC.REGION_NAME
            query["query"]["bool"]["filter"].append({
                "match": {field_name: value} # Using match for region names
            })
        else: # Default to term query for exact matches on keyword fields
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
    # Placeholder for query generation logic
    # Example: use job_details's specialty, location, etc.
    # job_details should contain keys like JS.SPECIALTIES, JDC.REGION_NAME
    
    must_clauses = []
    should_clauses = []

    # Key fields for similarity
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

    # More sophisticated: Use "more_like_this" query on JDC.CLEAN_CONTENT
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
                "must_not": [ # Exclude the original document
                    {"term": {JOB_FIELD_MAP["board_id"]: board_id}}
                ],
                "minimum_should_match": 1 if should_clauses else 0 
            }
        }
    }
    return query
