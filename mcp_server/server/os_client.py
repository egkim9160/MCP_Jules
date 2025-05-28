import os
import ssl
from opensearchpy import OpenSearch
from dotenv import load_dotenv

_opensearch_client = None

def init_opensearch_client():
    global _opensearch_client
    if _opensearch_client is None:
        load_dotenv() # Ensure .env file is loaded for environment variables like OPENAI_API_KEY if SearchResult uses it.
                      # Though for OpenSearch auth, direct env vars or config might be better.
        
        # For OpenSearch connection, user provided direct credentials.
        # Consider security implications for production (e.g., use environment variables for credentials).
        OPENSEARCH_HOST = os.getenv("OPENSEARCH_HOST", 'opensearch.medigate.net')
        OPENSEARCH_PORT = int(os.getenv("OPENSEARCH_PORT", 9200))
        OPENSEARCH_USER = os.getenv("OPENSEARCH_USER", 'medigate')
        OPENSEARCH_PASSWORD = os.getenv("OPENSEARCH_PASSWORD", 'Soakaeofh12!@')

        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        try:
            _opensearch_client = OpenSearch(
                hosts=[{'host': OPENSEARCH_HOST, 'port': OPENSEARCH_PORT}],
                http_auth=(OPENSEARCH_USER, OPENSEARCH_PASSWORD),
                use_ssl=True,
                verify_certs=False, # Should be True in production with proper certs
                ssl_context=ssl_context, # For development if using self-signed or problematic certs
                ssl_show_warn=False,
                # ssl_assert_hostname=False, # Already covered by check_hostname = False
                timeout=30
            )
            # Verify connection
            if not _opensearch_client.ping():
                raise ConnectionError("Failed to connect to OpenSearch.")
            print("Successfully connected to OpenSearch.")
        except Exception as e:
            print(f"Error connecting to OpenSearch: {e}")
            _opensearch_client = None # Ensure client is None if connection failed
            # Depending on desired behavior, might re-raise or handle gracefully
    return _opensearch_client

def get_opensearch_client():
    if _opensearch_client is None:
        # Attempt to initialize if not already done.
        # In a FastAPI app, this would typically be called at startup.
        init_opensearch_client()
    if _opensearch_client is None:
        # If still None after init attempt, means connection failed.
        raise ConnectionError("OpenSearch client is not available. Connection might have failed.")
    return _opensearch_client

# Example of SearchResult class if it's to be used by query_executor_tool
# However, query_executor_tool.py currently returns raw dicts.
# For now, keep it simple and let query_executor_tool handle its return types.
# class SearchResult:
#     def __init__(self, doc_id: str, score: float, text: str):
#         self.doc_id = doc_id
#         self.score = score
#         self.text = text
