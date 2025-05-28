# MCP Server Scenarios

This file describes various scenarios for using the MCP server.

# Scenario Flowcharts

## Scenario A: Direct Job Search

**Query:** "서울 지역에 연봉 3000만원 이상 마취통증의학과 공고 찾아줘"
(Find job postings in Seoul, salary >= 30,000,000 KRW, specialty: Anesthesiology)

**Flow:**

1.  **User Request Received (Agent Interface)**
    *   Input: "서울 지역에 연봉 3000만원 이상 마취통증의학과 공고 찾아줘"
    *   (Agent/Frontend parses this into structured data + optional free text)
    *   Example Parsed Input for `handle_scenario_a`:
        *   `text_query`: "" (or could be "마취통증의학과" if not fully structured)
        *   `location`: "Seoul"
        *   `salary_min`: 30000000
        *   `specialty`: "Anesthesiology"

2.  **MCP Server: `handle_scenario_a` function invoked**
    *   Receives parsed parameters.

3.  **Tool 1: Job Search Query Generation (`job_search_tool.generate_job_search_query`)**
    *   Input: `text_query` and `filters` (e.g., `{"location": "Seoul", "salary_min": 30000000, "specialty": "Anesthesiology"}`)
    *   Action: Constructs an OpenSearch query.
        *   Uses "term" filters for exact matches (location, specialty).
        *   Uses "range" filter for salary (gte salary_min).
        *   Potentially uses "match" for `text_query` if provided.
    *   Output: OpenSearch query JSON.

4.  **Tool 3: Query Execution (`query_executor_tool.execute_opensearch_query`)**
    *   Input: `index_name="job_db"`, OpenSearch query JSON from Step 3.
    *   Action: Executes the query against the Job Postings Database (OpenSearch).
    *   Output: List of job posting documents matching the criteria. (Mocked for now)

5.  **Tool 4: Content Formatting (`formatting_tool.format_results`)**
    *   Input: List of job posting documents, `format_flag` (e.g., "summary").
    *   Action: Formats the documents into a user-friendly string.
    *   Output: Formatted string of job postings.

6.  **MCP Server: `handle_scenario_a` returns**
    *   Returns the formatted string to the Agent/Frontend.

7.  **User Receives Formatted Results (Agent Interface)**
    *   Displays the summary of matching job postings.
