# mcp_test_client.py
import asyncio
import copy # Added for deepcopy
import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional 
import traceback
import argparse 

# MCP Client imports
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import mcp.types as types

# Langchain import for embeddings
from langchain_community.embeddings import OpenAIEmbeddings 
import os 

# Project service imports
from job_portal_service.query_generators import generate_job_search_query, JOB_FIELD_MAP 

logger = logging.getLogger('mcp_test_client')
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

SERVER_SCRIPT_PATH = Path(__file__).parent / "mcp_job_portal_server.py"
JOB_INDEX_NAME_CLIENT = "recruit_text-embedding-3-small_1536_100000_300_20250529_150924" # Updated to user's actual index name
# This should match the field name used in the OpenSearch index mapping for KNN search
DEFAULT_VECTOR_FIELD_NAME = "vector_field" # Changed as per user instruction

async def main(user_query: str, page_url: Optional[str]):
    logger.info("MCP Test Client starting...")
    logger.info(f"Received User Query: '{user_query}'")
    if page_url:
        logger.info(f"Received Page URL: '{page_url}'")

    if not os.getenv("OPENAI_API_KEY"):
        logger.warning("OPENAI_API_KEY environment variable not set. Embedding generation will likely fail.")

    server_params = StdioServerParameters(command=sys.executable, args=[str(SERVER_SCRIPT_PATH)])
    
    try:
        async with stdio_client(server_params) as (read_stream, write_stream):
            logger.info("Successfully started MCP server subprocess and obtained streams.")
            async with ClientSession(read_stream, write_stream) as session: 
                logger.info("MCP Client session context established.")
                try:
                    logger.info("Attempting MCP Session initialization (session.initialize())...")
                    initialization_result = await session.initialize() # type: ignore 
                    server_name_to_log = "N/A"; server_version_to_log = "N/A"
                    if initialization_result.serverInfo:
                        server_name_to_log = initialization_result.serverInfo.name
                        if initialization_result.serverInfo.version: server_version_to_log = initialization_result.serverInfo.version
                    logger.info(f"MCP Session initialized. Server name: '{server_name_to_log}', Version: '{server_version_to_log}'")
                    
                    # (Tool listing logic can be kept or commented out)

                    logger.info(f"--- Calling 'generate_search_conditions' tool on server ---")
                    conditions_args: Dict[str, Any] = {"raw_query": user_query}
                    if page_url: 
                        conditions_args["url_context"] = page_url
                    
                    # Access the uid from the global args parsed in __main__
                    if hasattr(args, 'uid') and args.uid:
                        conditions_args["uid"] = args.uid
                        logger.info(f"Using UID: {args.uid} for personalized search conditions.")
                    
                    call_gsc_result: types.CallToolResult = await session.call_tool("generate_search_conditions", conditions_args) # type: ignore
                    
                    search_conditions_text: Optional[str] = None
                    if call_gsc_result and call_gsc_result.content:
                        content_to_parse_gsc = None
                        if isinstance(call_gsc_result.content, list):
                            if call_gsc_result.content and isinstance(call_gsc_result.content[0], types.TextContent):
                                content_to_parse_gsc = call_gsc_result.content[0]
                        elif isinstance(call_gsc_result.content, types.TextContent):
                            content_to_parse_gsc = call_gsc_result.content
                        if content_to_parse_gsc: search_conditions_text = content_to_parse_gsc.text
                        else: logger.warning(f"Could not extract TextContent from 'generate_search_conditions'. Full result: {call_gsc_result}")
                    else: logger.warning(f"No content in CallToolResult from 'generate_search_conditions'. Full result: {call_gsc_result}")

                    search_conditions: Optional[Dict[str, Any]] = None
                    if search_conditions_text:
                        try:
                            search_conditions = json.loads(search_conditions_text)
                            logger.info(f"Received search conditions from server: {json.dumps(search_conditions, ensure_ascii=False, indent=2)}")
                        except json.JSONDecodeError: logger.error(f"Failed to parse JSON from generate_search_conditions: {search_conditions_text}")
                    
                    if search_conditions and not search_conditions.get("error"):
                        filters = search_conditions.get("filters", {})
                        semantic_text_for_embedding = search_conditions.get("semantic_text", user_query) 
                        
                        query_vector: Optional[List[float]] = None
                        if semantic_text_for_embedding:
                            logger.info(f"Attempting to generate embedding for text: '{semantic_text_for_embedding}'")
                            try:
                                embeddings_model = OpenAIEmbeddings(
                                    model="text-embedding-3-large",
                                    request_timeout=30
                                )
                                query_vector = embeddings_model.embed_query(semantic_text_for_embedding)
                                logger.info(f"Successfully generated query vector (dimension: {len(query_vector)}). First few elements: {query_vector[:3]}...")
                            except Exception as e_embed:
                                logger.error(f"Failed to generate embedding: {e_embed}")
                        
                        logger.info("Client generating OpenSearch DSL using 'generate_job_search_query' locally...")
                        query_dsl = generate_job_search_query(
                            text_query=semantic_text_for_embedding, 
                            filters=filters,
                            query_vector=query_vector, # Pass the generated vector
                            vector_field_name=DEFAULT_VECTOR_FIELD_NAME # Pass the target vector field name
                        )

                        # Redact vector for logging
                        query_dsl_for_log = copy.deepcopy(query_dsl)
                        try:
                            # The path to the vector is query_dsl["query"]["bool"]["must"][0]["knn"][DEFAULT_VECTOR_FIELD_NAME]["vector"]
                            # generate_job_search_query structure might place knn directly in must if no other must clauses,
                            # or it could be within a bool query. The provided generate_job_search_query seems to create a bool query.
                            if query_dsl_for_log.get("query", {}).get("bool", {}).get("must"):
                                must_clauses = query_dsl_for_log["query"]["bool"]["must"]
                                if isinstance(must_clauses, list):
                                    for clause in must_clauses:
                                        if isinstance(clause, dict) and "knn" in clause:
                                            knn_clause = clause.get("knn")
                                            if isinstance(knn_clause, dict) and DEFAULT_VECTOR_FIELD_NAME in knn_clause:
                                                if "vector" in knn_clause[DEFAULT_VECTOR_FIELD_NAME]:
                                                    knn_clause[DEFAULT_VECTOR_FIELD_NAME]["vector"] = "[redacted due to length]"
                                                    logger.debug(f"Redacted vector in KNN clause for field '{DEFAULT_VECTOR_FIELD_NAME}' for logging.")
                                                break # Assuming only one knn clause with the target vector field
                            # Check if the top level query is a KNN query (if no text_query and only vector)
                            elif query_dsl_for_log.get("knn", {}).get(DEFAULT_VECTOR_FIELD_NAME, {}).get("vector"):
                                query_dsl_for_log["knn"][DEFAULT_VECTOR_FIELD_NAME]["vector"] = "[redacted due to length]"
                                logger.debug(f"Redacted vector in top-level KNN query for field '{DEFAULT_VECTOR_FIELD_NAME}' for logging.")

                        except Exception as e_redact:
                            logger.warning(f"Could not redact vector from query_dsl for logging: {e_redact}")
                        
                        logger.info(f"Locally generated query_dsl (with vector integration): {json.dumps(query_dsl_for_log, indent=2, ensure_ascii=False)}")
                        
                        query_size = search_conditions.get("size", 10)
                        
                        logger.info(f"--- Calling 'opensearch_query_executor' tool on server ---")
                        executor_args = {
                            "index_name": JOB_INDEX_NAME_CLIENT,
                            "query_dsl": query_dsl, 
                            "size": query_size 
                        }
                        
                        call_oqe_result: types.CallToolResult = await session.call_tool("opensearch_query_executor", executor_args) # type: ignore
                        
                        job_results_text: Optional[str] = None
                        if call_oqe_result and call_oqe_result.content:
                            content_to_parse_oqe = None
                            if isinstance(call_oqe_result.content, list):
                                if call_oqe_result.content and isinstance(call_oqe_result.content[0], types.TextContent):
                                    content_to_parse_oqe = call_oqe_result.content[0]
                            elif isinstance(call_oqe_result.content, types.TextContent):
                                content_to_parse_oqe = call_oqe_result.content
                            if content_to_parse_oqe: job_results_text = content_to_parse_oqe.text
                            else: logger.warning(f"Could not extract TextContent from 'opensearch_query_executor'. Full result: {call_oqe_result}")
                        else: logger.warning(f"No content in CallToolResult from 'opensearch_query_executor'. Full result: {call_oqe_result}")

                        job_results_payload: Any = None
                        if job_results_text:
                            try:
                                job_results_payload = json.loads(job_results_text)
                                # The direct payload is logged by the new logic below if not None.
                                # logger.info(f"Received payload from 'opensearch_query_executor': {json.dumps(job_results_payload, ensure_ascii=False, indent=2)}")
                            except json.JSONDecodeError: 
                                logger.error(f"Failed to parse JSON from opensearch_query_executor: {job_results_text}")
                                job_results_payload = None # Ensure it's None if parsing fails
                        
                        # --- New result processing logic ---
                        if job_results_payload:
                            logger.info(f"Processing {len(job_results_payload) if isinstance(job_results_payload, list) else 1} document(s) from opensearch_query_executor.")
                            logger.debug(f"Full payload from opensearch_query_executor: {json.dumps(job_results_payload, ensure_ascii=False, indent=2)}")

                            job_documents_to_summarize = job_results_payload if isinstance(job_results_payload, list) else [job_results_payload]

                            if not job_documents_to_summarize:
                                logger.info("No job documents returned from opensearch_query_executor.")
                            else:
                                all_summaries_text: List[str] = [] # Store all summaries
                                processed_count = 0
                                for doc_index, job_document in enumerate(job_documents_to_summarize):
                                    if not isinstance(job_document, dict):
                                        logger.warning(f"Item at index {doc_index} is not a dictionary, skipping: {job_document}")
                                        continue
                                    
                                    if job_document.get("error"):
                                        error_message = f"Document at index {doc_index} contains an error: {job_document.get('error')}"
                                        logger.error(error_message)
                                        all_summaries_text.append(f"Error for document {doc_index + 1}: {job_document.get('error')}")
                                        continue 

                                    # Assuming a valid job document has an '_id' or 'metadata' field
                                    # The 'metadata' field is more common in the project's context for job postings.
                                    # '_id' is a general OpenSearch field.
                                    if '_id' not in job_document and 'metadata' not in job_document.get('metadata', {}): # Check nested metadata too
                                        logger.warning(f"Document at index {doc_index} (ID: {job_document.get('_id', 'N/A')}) does not appear to be a valid job document, skipping summarization. Document: {job_document}")
                                        continue
                                        
                                    logger.info(f"Summarizing job document {doc_index + 1}/{len(job_documents_to_summarize)} (ID: {job_document.get('_id', job_document.get('metadata', {}).get('BOARD_IDX', 'N/A'))})...")
                                    try:
                                        summary_args = {"job_document": job_document}
                                        call_fjs_result: types.CallToolResult = await session.call_tool("format_job_summary", summary_args) # type: ignore
                                        
                                        summary_text_payload: Optional[str] = None
                                        if call_fjs_result and call_fjs_result.content:
                                            content_to_parse_fjs = None
                                            if isinstance(call_fjs_result.content, list):
                                                if call_fjs_result.content and isinstance(call_fjs_result.content[0], types.TextContent):
                                                    content_to_parse_fjs = call_fjs_result.content[0]
                                            elif isinstance(call_fjs_result.content, types.TextContent):
                                                content_to_parse_fjs = call_fjs_result.content
                                            
                                            if content_to_parse_fjs: 
                                                summary_text_payload = content_to_parse_fjs.text
                                                all_summaries_text.append(f"Summary for job {doc_index + 1} (ID: {job_document.get('_id', job_document.get('metadata', {}).get('BOARD_IDX', 'N/A'))}):\n{summary_text_payload}")
                                                logger.info(f"Summary for job {doc_index + 1}:\n{summary_text_payload}")
                                                processed_count +=1
                                            else: 
                                                logger.warning(f"Could not extract TextContent from 'format_job_summary' for doc ID {job_document.get('_id', 'N/A')}. Full result: {call_fjs_result}")
                                                all_summaries_text.append(f"Could not get summary for doc ID {job_document.get('_id', 'N/A')}")
                                        else: 
                                            logger.warning(f"No content in CallToolResult from 'format_job_summary' for doc ID {job_document.get('_id', 'N/A')}. Full result: {call_fjs_result}")
                                            all_summaries_text.append(f"No summary content for doc ID {job_document.get('_id', 'N/A')}")

                                    except Exception as e_summary:
                                        error_msg = f"Error calling format_job_summary for document ID {job_document.get('_id', 'N/A')}: {e_summary}"
                                        logger.error(error_msg)
                                        all_summaries_text.append(error_msg)
                                
                                if processed_count == 0 and not any("Error for document" in s for s in all_summaries_text):
                                     logger.info("No valid job documents were found to summarize from the results.")
                                elif all_summaries_text:
                                    logger.info("\n--- All Processed Summaries/Errors ---\n" + "\n---\n".join(all_summaries_text))
                        else:
                            # This case handles if results_payload is None or empty (e.g. if tool itself failed or returned nothing)
                            logger.info("No results payload received from 'opensearch_query_executor' to summarize.")

                    elif search_conditions and search_conditions.get("error"):
                        logger.error(f"Failed to generate search conditions on server: {search_conditions.get('error')}")
                    else:
                        logger.warning("Could not obtain valid search conditions from server.")

                except Exception as e_init: 
                    logger.error(f"Error during MCP session operations: {e_init}")
                    logger.error(traceback.format_exc())
    except ConnectionRefusedError: logger.error("Connection refused by server process.")
    except asyncio.TimeoutError: logger.error("Connection attempt to server process timed out.")
    except Exception as e_outer: 
        logger.error(f"An error occurred with the MCP server process or client connection: {e_outer}")
        logger.error(traceback.format_exc())
        logger.error(f"Ensure the server script ({SERVER_SCRIPT_PATH}) is executable and has no critical startup errors.")
    
    logger.info("MCP Test Client finished.")

if __name__ == "__main__":
    if not SERVER_SCRIPT_PATH.exists():
        logger.error(f"Server script not found at: {SERVER_SCRIPT_PATH}")
        sys.exit(1)
    parser = argparse.ArgumentParser(description="MCP Test Client for Job Portal Server")
    parser.add_argument("--query", type=str, required=True, help="The natural language query for the agent.")
    parser.add_argument("--url", type=str, required=False, default=None, help="Optional: The URL of the page context (e.g., a specific job posting).")
    parser.add_argument("--uid", type=str, default=None, help="User ID for personalized search.") # Added UID argument
    
    global args # Make args global so main can access it
    args = parser.parse_args()
    
    asyncio.run(main(user_query=args.query, page_url=args.url))
