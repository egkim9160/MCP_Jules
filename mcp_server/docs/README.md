# MCP Server for Doctor Job Matching

## Project Description

This project is an MCP (Multi-Agent Conversational Platform) server designed to help doctors find relevant job postings. It acts as a backend for an agent that doctors can interact with to search for jobs, get recommendations, and find postings based on various criteria.

The service interfaces with a Job Postings DB and a User DB (conceptually using OpenSearch) to retrieve and filter information.

## Purpose

The main purpose of this server is to provide intelligent and flexible job searching capabilities for medical professionals, leveraging both structured filtering and semantic search.

## Core Features & Tools

The server will implement the following core functionalities, exposed through specific tools:

1.  **Job Posting Search & Semantic Query Generation (`job_search_tool.py`)**:
    *   Allows searching for job postings based on specific criteria (location, salary, specialty).
    *   Supports semantic search for more nuanced queries.
    *   Can generate queries to find jobs similar to an existing one.

2.  **User-Based Search & Semantic Query Generation (`user_search_tool.py`)**:
    *   Allows searching based on user profiles and preferences.
    *   Can generate queries to find jobs suitable for a user's qualifications and desired attributes (e.g., skills like "ultrasound," "colonoscopy").
    *   (Future) Can identify users similar to a given profile to find jobs popular among them.

3.  **Query Execution (`query_executor_tool.py`)**:
    *   Handles the actual interaction with the backend databases (OpenSearch).
    *   Executes queries against the Job DB and User DB.

4.  **Content Summarization & Formatting (`formatting_tool.py`)**:
    *   Formats the raw search results into user-friendly outputs.
    *   Supports different formatting flags (e.g., summary, detailed list).

## Scenarios Handled

The server is designed to handle various interaction scenarios, including:
*   Direct keyword-based job searches (e.g., "Find Anesthesiology jobs in Seoul with salary > X").
*   Finding jobs similar to one currently being viewed.
*   Finding jobs suitable for the current user's profile.
*   Finding jobs that users with similar profiles have applied to.

## Future Development
*   Implementation of a RESTful API (e.g. using Flask/FastAPI).
*   Direct integration with OpenSearch.
*   Refinement of semantic search capabilities.
*   Implementation of the Human/AI Judgement Structure.
