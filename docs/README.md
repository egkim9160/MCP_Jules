# MCP Server for Doctor Job Matching (OpenSearch Backend)

## Project Description

This project is an MCP (Model Context Protocol) server designed to help doctors find relevant job postings. It acts as a backend for an intelligent agent that doctors can interact with to search for jobs, get recommendations, and find postings based on various criteria.

The server interfaces with an **OpenSearch** database for job postings and (in the future) user profiles. It is built using the `mcp.server.fastmcp.FastMCP` framework for streamlined tool definition.

## Purpose

The main purpose of this server is to provide a standardized interface for an AI agent to access job searching capabilities, leveraging both structured filtering and semantic search over an OpenSearch backend.

## Architecture

The server consists of:
- **`mcp_job_portal_server.py`**: The main server script that initializes the `FastMCP` server and defines tools as decorated Python functions. It manages the stdio communication loop via `mcp.run()`.
- **`job_portal_service/`**: A Python package containing the core logic:
    - `opensearch_service.py`: Manages the connection to OpenSearch and executes queries.
    - `query_generators.py`: Contains functions to generate OpenSearch query DSL based on input criteria.
    - `context_utils.py`: Provides utilities for parsing request context (intended for use by the agent calling this server).
    - `text_formatters.py`: (Currently holds basic text formatting, role may evolve).

This server communicates over stdio using the MCP protocol.

## Implemented MCP Tools

The server currently exposes the following tools, which can be called by an MCP-compliant agent:

1.  **`get_job_details`**:
    *   Description: Fetches the full details of a specific job posting.
    *   Input: `board_id: str`
    *   Output: JSON string of the job details or null.

2.  **`search_jobs_by_criteria`**:
    *   Description: Searches for job postings based on various criteria.
    *   Input: `filters: dict` (for structured data like location, specialty), `text_query: Optional[str]` (for semantic parts), `size: Optional[int]`.
    *   Output: JSON string of a list of job summaries.

3.  **`find_similar_jobs_to_posting`**:
    *   Description: Finds job postings similar to a given job posting.
    *   Input: `board_id: str`, `original_job_details: Optional[dict]`, `size: Optional[int]`.
    *   Output: JSON string of a list of similar job summaries.

4.  **`summarize_job_posting_main_points`**:
    *   Description: Provides a basic summary of a job posting by extracting key fields.
    *   Input: `board_id: str`.
    *   Output: Plain text summary.

5.  **`get_user_profile_for_recommendations` (Placeholder)**:
    *   Description: Fetches a user's profile data, structured for recommendations. **Currently returns placeholder/mock data.**
    *   Input: `user_id: str`.
    *   Output: JSON string of a mock user profile.

## How to Run

1.  Ensure OpenSearch is running and accessible with the credentials and host specified in `job_portal_service/opensearch_service.py` (ideally, configure these via environment variables).
2.  The necessary Python packages (like `mcp.server`, `opensearch-py`, `python-dotenv`, `pydantic`) must be installed.
3.  Run the server from the project root directory:
    ```bash
    python mcp_job_portal_server.py
    ```
    The server will then listen for MCP messages on stdio.

### Running the Test Client

A test client script, `mcp_test_client.py`, is included in the project root. It demonstrates how an agent might interact with the MCP server by taking a natural language query and an optional URL, processing them, and dynamically calling an appropriate server tool.

**To use the test client:**

1.  Ensure the MCP server (`mcp_job_portal_server.py`) is **not** already running separately, as the client will attempt to start it as a subprocess.
2.  Open a terminal at the project root.
3.  Run the client using command-line arguments:
    *   `--query "YOUR_NATURAL_LANGUAGE_QUERY"` (Required): The user's question.
    *   `--url "OPTIONAL_URL_CONTEXT"` (Optional): The URL of the page the user is currently viewing, if relevant.

    **Example (based on user's test case):**
    ```bash
    python mcp_test_client.py --query "월급 1500 이상 공고만 보고 싶어 상급종합병원 공고만 보여줘" --url "https://s-new.medigate.net/recruit/1172037"
    ```
    Or, for a query not dependent on a specific URL:
    ```bash
    python mcp_test_client.py --query "서울 지역 마취과 공고 찾아주세요"
    ```

**What the Test Client Does:**

-   Starts the `mcp_job_portal_server.py` as a subprocess.
-   Takes the `--query` and optional `--url` from command-line arguments.
-   Uses `job_portal_service.context_utils.analyze_request` to process these inputs into a structured `RequestContext` (identifying `board_id` from URL, classifying query type, etc.). This is logged to the client's console.
-   Implements a basic `map_query_to_tool_call` function that attempts to:
    -   Determine the appropriate MCP server tool to call (e.g., `search_jobs_by_criteria`).
    -   Extract simple arguments for the tool from the natural language query (e.g., parsing "월급 1500 이상" into a salary filter and "상급종합병원" into an organization type filter for the `search_jobs_by_criteria` tool). This simulates a very basic NLU step.
    -   The determined tool and its arguments are logged.
-   Establishes an MCP session with the server and initializes it.
-   (Optionally, can list tools, though this part might be commented out in the client for cleaner output during specific query tests).
-   Dynamically calls the determined MCP tool on the server with the extracted arguments.
-   Prints the response received from the tool call to the client's console.

**Observing Server-Side Query Flow:**

The `mcp_job_portal_server.py` has been enhanced with logging to show how client requests are processed:
-   When `mcp_test_client.py` (or any MCP agent) calls tools like `get_job_details` or `search_jobs_by_criteria`, the **server's console output** will display:
    1.  The arguments received by the tool function.
    2.  The full OpenSearch query (in JSON format) generated based on those arguments before it's sent to OpenSearch.

This allows you to see the translation from a tool call and its parameters into a specific database query, fulfilling the request to demonstrate input/output flow.

**Note on Tool Outputs:**
The test client's `map_query_to_tool_call` function implements very basic NLU for specific examples. If your query structure significantly differs, it might fall back to a general search or not extract detailed filters. The actual data returned by tools will depend on your OpenSearch index (e.g., the one specified by `JOB_INDEX_NAME` in the server) containing matching data for the criteria extracted by the client's NLU and sent to the server.

## Future Development
- Implementation of more tools from the user's comprehensive list (advanced search, filtering, analytics, recommendations).
- Integration with a fully defined User Profile DB in OpenSearch.
- Refinement of error handling and input validation.
- More sophisticated summarization capabilities.
- Investigation of how Prompts and Resources can be effectively utilized with the FastMCP structure, if needed.
