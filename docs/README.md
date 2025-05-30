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
    - `query_generators.py`: Contains functions to generate OpenSearch query DSL (e.g., `generate_job_search_query`). These can be used by server tools (if complex internal generation is needed) or by the client/agent after obtaining structured conditions from server tools like `generate_search_conditions`.
    - `context_utils.py`: Provides utilities for parsing request context (intended for use by the agent calling this server).
    - `text_formatters.py`: (Currently holds basic text formatting, role may evolve).

This server communicates over stdio using the MCP protocol.

## Implemented MCP Tools

The server currently exposes the following more atomic and utility-like tools, designed to be orchestrated by an intelligent agent:

1.  **`generate_search_conditions`**:
    *   Description: Analyzes a raw natural language query and an optional URL context to generate structured search conditions (filters, semantic text components, and context information) suitable for building an OpenSearch query for job postings. This tool incorporates basic Natural Language Understanding (NLU) for query parsing.
    *   Input: `raw_query: str`, `url_context: Optional[str]`
    *   Output: JSON string containing a dictionary with keys like `filters` (dict), `semantic_text` (str), `source_context` (str), `board_id` (Optional[str]), `is_detail_view` (bool), `classified_query_type` (str).

2.  **`opensearch_query_executor`**:
    *   Description: Executes a raw OpenSearch Query DSL against a specified index. This is the primary tool for data retrieval.
    *   Input: `index_name: str`, `query_dsl: Dict[str, Any]`, `size: Optional[int]`
    *   Output: JSON string of a list of raw OpenSearch result documents, or an error dictionary.

3.  **`format_job_summary`**:
    *   Description: Formats a single raw job document (as returned by OpenSearch) into a user-friendly text summary, extracting key fields.
    *   Input: `job_document: Dict[str, Any]`
    *   Output: Plain text summary string, or an error message string.

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
-   Takes the `--query` (natural language) and optional `--url` from command-line arguments.
-   **Calls the server's `generate_search_conditions` tool:** Passes the raw query and URL to the server to get structured search conditions (filters, semantic text, context). This step demonstrates offloading NLU/query parsing to a server tool.
-   Logs the conditions received from the server.
-   **Locally generates an OpenSearch Query DSL:** Uses the `generate_job_search_query` function from `job_portal_service.query_generators` with the conditions received from the server. This demonstrates client-side logic for preparing the final database query.
-   **Calls the server's `opensearch_query_executor` tool:** Sends the target index name (e.g., for jobs) and the locally generated OpenSearch Query DSL to the server for execution.
-   Logs the search results (raw documents from OpenSearch).
-   **If results are found, calls the server's `format_job_summary` tool:** Passes the first job document received from the search results to get a formatted text summary.
-   Logs the summary.
-   (The client also lists available server tools upon connection for diagnostic purposes).

**Observing Server-Side Query Flow:**

The `mcp_job_portal_server.py` has been enhanced with logging to show how client requests are processed:
-   When `mcp_test_client.py` (or any MCP agent) calls tools like `generate_search_conditions` or `opensearch_query_executor`, the **server's console output** will display:
    1.  The arguments received by the tool function.
    2.  For `opensearch_query_executor`, the full OpenSearch query (in JSON format) generated based on those arguments before it's sent to OpenSearch.

This allows you to see the translation from a tool call and its parameters into a specific database query, fulfilling the request to demonstrate input/output flow.

**Note on Tool Outputs:**
The test client's interaction with `generate_search_conditions` (which uses basic NLU) means that if your query structure significantly differs from the example, it might not extract detailed filters and might pass more of the query as `semantic_text`. The actual data returned by `opensearch_query_executor` will depend on your OpenSearch index containing matching data for the criteria.

## Future Development
- Implementation of more tools from the user's comprehensive list (advanced search, filtering, analytics, recommendations).
- Integration with a fully defined User Profile DB in OpenSearch.
- Refinement of error handling and input validation.
- More sophisticated summarization capabilities.
- Investigation of how Prompts and Resources can be effectively utilized with the FastMCP structure, if needed.
