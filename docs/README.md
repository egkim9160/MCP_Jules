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

## Future Development
- Implementation of more tools from the user's comprehensive list (advanced search, filtering, analytics, recommendations).
- Integration with a fully defined User Profile DB in OpenSearch.
- Refinement of error handling and input validation.
- More sophisticated summarization capabilities.
- Investigation of how Prompts and Resources can be effectively utilized with the FastMCP structure, if needed.
