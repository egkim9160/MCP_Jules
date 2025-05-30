# mcp_test_client.py
import asyncio
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
                    conditions_args = {"raw_query": user_query}
                    if page_url: conditions_args["url_context"] = page_url
                    
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
                        logger.info(f"Locally generated query_dsl (with vector integration): {json.dumps(query_dsl, indent=2, ensure_ascii=False)}")
                        
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
                                logger.info(f"Received payload from 'opensearch_query_executor': {json.dumps(job_results_payload, ensure_ascii=False, indent=2)}")
                            except json.JSONDecodeError: logger.error(f"Failed to parse JSON from opensearch_query_executor: {job_results_text}")
                        
                        if isinstance(job_results_payload, list) and job_results_payload:
                            first_job_doc = job_results_payload[0]
                            if not isinstance(first_job_doc, dict) or not first_job_doc.get("error"):
                                logger.info(f"--- Calling 'format_job_summary' for first result ---")
                                summary_args = {"job_document": first_job_doc}
                                call_fjs_result: types.CallToolResult = await session.call_tool("format_job_summary", summary_args) # type: ignore
                                
                                summary_text_payload: Optional[str] = None
                                if call_fjs_result and call_fjs_result.content:
                                    content_to_parse_fjs = None
                                    if isinstance(call_fjs_result.content, list):
                                        if call_fjs_result.content and isinstance(call_fjs_result.content[0], types.TextContent):
                                            content_to_parse_fjs = call_fjs_result.content[0]
                                    elif isinstance(call_fjs_result.content, types.TextContent):
                                        content_to_parse_fjs = call_fjs_result.content
                                    if content_to_parse_fjs: summary_text_payload = content_to_parse_fjs.text
                                    else: logger.warning(f"Could not extract TextContent from 'format_job_summary'. Full result: {call_fjs_result}")
                                else: logger.warning(f"No content in CallToolResult from 'format_job_summary'. Full result: {call_fjs_result}")
                                if summary_text_payload is not None: logger.info(f"Job Summary:\n{summary_text_payload}")
                        elif isinstance(job_results_payload, dict) and job_results_payload.get("error"):
                             logger.warning(f"Search execution via 'opensearch_query_executor' returned an error: {job_results_payload['error']}")
                        else: logger.info("No job results to summarize from 'opensearch_query_executor'.")

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
    args = parser.parse_args()
    asyncio.run(main(user_query=args.query, page_url=args.url))
