# mcp_test_client.py
import asyncio
import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple 
import traceback
import argparse 
import re 

# MCP Client imports
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import mcp.types as types

# Project service imports
from job_portal_service.context_utils import analyze_request, RequestContext, QueryType # Added QueryType

logger = logging.getLogger('mcp_test_client')
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

SERVER_SCRIPT_PATH = Path(__file__).parent / "mcp_job_portal_server.py"

# (map_query_to_tool_call function remains as implemented in the previous step)
def map_query_to_tool_call(req_context: RequestContext) -> Optional[Tuple[str, Dict[str, Any]]]:
    logger.info(f"Attempting to map query: '{req_context.raw_query}' with context: {req_context}")
    tool_name: Optional[str] = None
    arguments: Dict[str, Any] = {"filters": {}}
    if req_context.query_type == "job_posting_question": # Compare with the string value for Literal
        tool_name = "search_jobs_by_criteria"
        salary_match = re.search(r"월급\s*(\d+)\s*만?\s*(이상|부터)", req_context.raw_query)
        if salary_match:
            salary_amount = int(salary_match.group(1))
            if salary_amount == 1500: arguments["filters"]["salary_min"] = 15000000
            logger.info(f"Extracted salary_min: {arguments['filters'].get('salary_min')}")
        if "상급종합병원" in req_context.raw_query:
            arguments["filters"]["org_type"] = "상급종합병원"
            logger.info(f"Extracted org_type: {arguments['filters']['org_type']}")
        if "서울" in req_context.raw_query and "location" not in arguments["filters"]:
             arguments["filters"]["location"] = "서울"
             logger.info(f"Extracted location: {arguments['filters']['location']}")
        processed_query = req_context.raw_query
        if arguments["filters"].get("salary_min"): processed_query = re.sub(r"월급\s*\d+\s*만?\s*(이상|부터)", "", processed_query).strip()
        if arguments["filters"].get("org_type"): processed_query = processed_query.replace("상급종합병원", "").strip()
        if arguments["filters"].get("location"): processed_query = processed_query.replace("서울", "").strip()
        processed_query = re.sub(r'\s+', ' ', processed_query).strip()
        common_leftovers = ["공고만 보고 싶어", "공고만 보여줘", "만 보고 싶어", "만 보여줘", "보고 싶어", "보여줘", "찾아줘", "알려줘"]
        if processed_query and processed_query not in common_leftovers and not processed_query.isdigit(): arguments["text_query"] = processed_query
        else: arguments["text_query"] = ""
        arguments["size"] = arguments.get("size", 10) 
    if tool_name:
        if not arguments["filters"] and not arguments.get("text_query"): del arguments["filters"]
        elif not arguments["filters"]: del arguments["filters"]
        if "text_query" in arguments and not arguments["text_query"] and arguments.get("filters"): del arguments["text_query"]
        return tool_name, arguments
    else:
        logger.warning("Could not map query to a known tool call.")
        return None

async def main(user_query: str, page_url: Optional[str]):
    logger.info("MCP Test Client starting...")
    logger.info(f"Received User Query: '{user_query}'")
    if page_url:
        logger.info(f"Received Page URL: '{page_url}'")
    
    req_context: Optional[RequestContext] = None
    try:
        req_context = analyze_request(raw_query=user_query, url=page_url)
        logger.info(f"Analyzed Request Context results: {req_context}") # Using __repr__ from RequestContext
    except Exception as e_context:
        logger.error(f"Error during context analysis: {e_context}")
        logger.error(traceback.format_exc())
        return

    tool_call_info: Optional[Tuple[str, Dict[str, Any]]] = None
    if req_context:
        tool_call_info = map_query_to_tool_call(req_context)

    tool_name_to_call: Optional[str] = None
    tool_args_to_call: Optional[Dict[str, Any]] = None

    if tool_call_info:
        tool_name_to_call, tool_args_to_call = tool_call_info
        logger.info(f"Determined tool call: Tool Name='{tool_name_to_call}', Arguments='{json.dumps(tool_args_to_call, ensure_ascii=False, indent=2)}'")
    else:
        logger.warning("Test client could not determine a tool to call for the given query. Attempting fallback general search.")
        tool_name_to_call = "search_jobs_by_criteria" # Default tool
        tool_args_to_call = {"text_query": user_query, "size": 3} # Default args
        logger.info(f"Using fallback: Tool Name='{tool_name_to_call}', Arguments='{json.dumps(tool_args_to_call, ensure_ascii=False, indent=2)}'")
    
    server_params = StdioServerParameters(command=sys.executable, args=[str(SERVER_SCRIPT_PATH)])
    
    session = None 
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
                    
                    # Tool listing (can be kept for verbosity or commented out if not needed every run)
                    # logger.info("Listing tools from server...") 
                    # list_tools_result: types.ListToolsResult = await session.list_tools() # type: ignore
                    # ... (tool listing logging)
                    # logger.info("Tool listing complete.")

                    # --- Actually call the determined tool ---
                    if tool_name_to_call and tool_args_to_call is not None: # Ensure not None before calling
                        logger.info(f"--- Attempting to call dynamically determined tool: '{tool_name_to_call}' ---")
                        try:
                            call_tool_result: types.CallToolResult = await session.call_tool(tool_name_to_call, tool_args_to_call) # type: ignore
                            actual_contents: List[types.Content] = []
                            if call_tool_result and hasattr(call_tool_result, 'contents'):
                                actual_contents = call_tool_result.contents

                            logger.info(f"'{tool_name_to_call}' response items: {len(actual_contents)}")
                            for content_item in actual_contents:
                                if isinstance(content_item, types.TextContent):
                                    try:
                                        # Attempt to parse as JSON, as most tools return JSON strings
                                        parsed_text = json.loads(content_item.text)
                                        logger.info(f"  Result from '{tool_name_to_call}': {json.dumps(parsed_text, ensure_ascii=False, indent=2)}")
                                    except json.JSONDecodeError:
                                        # If not JSON, it might be plain text (e.g., summary tool) or a JSON-dumped error string
                                        logger.info(f"  Result (plain text or JSON error string) from '{tool_name_to_call}':\n{content_item.text}")
                                else:
                                    logger.info(f"  Received unexpected content type: {type(content_item)}")
                        except Exception as e_call:
                            logger.error(f"Error calling '{tool_name_to_call}': {e_call}")
                            logger.error(traceback.format_exc())
                    else:
                         logger.info("--- No valid tool call determined, skipping dynamic tool call section ---")

                except Exception as e_init: 
                    logger.error(f"Error during MCP session initialization or subsequent operations: {e_init}")
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
