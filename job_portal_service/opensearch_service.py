import os
import ssl
from typing import Optional # Add this import
from opensearchpy import OpenSearch # Ensure this import is present
from dotenv import load_dotenv

class OpenSearchService:
    def __init__(self, hosts=None, http_auth=None, use_ssl=True, verify_certs=False, ssl_show_warn=False, timeout=30):
        load_dotenv() # Load .env file if OpenSearch credentials are there

        self.client = None
        self._connect(hosts, http_auth, use_ssl, verify_certs, ssl_show_warn, timeout)

    def _connect(self, hosts, http_auth, use_ssl, verify_certs, ssl_show_warn, timeout):
        # Use provided params or defaults from user's original os_client.py example
        opensearch_host = os.getenv("OPENSEARCH_HOST", 'opensearch.medigate.net')
        opensearch_port = int(os.getenv("OPENSEARCH_PORT", 9200))
        # User's example hardcoded credentials; use env vars as a better practice if available,
        # but fall back to their provided ones if not set.
        opensearch_user = os.getenv("OPENSEARCH_USER", 'medigate')
        opensearch_password = os.getenv("OPENSEARCH_PASSWORD", 'Soakaeofh12!@')

        actual_hosts = hosts or [{'host': opensearch_host, 'port': opensearch_port}]
        actual_auth = http_auth or (opensearch_user, opensearch_password)
        
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False # As per user's original ssl settings
        ssl_context.verify_mode = ssl.CERT_NONE # As per user's original ssl settings

        try:
            self.client = OpenSearch(
                hosts=actual_hosts,
                http_auth=actual_auth,
                use_ssl=use_ssl,
                verify_certs=verify_certs, # Should be True in production with proper certs
                ssl_context=ssl_context,
                ssl_show_warn=ssl_show_warn,
                timeout=timeout
            )
            if not self.client.ping():
                # Log this error appropriately
                print("Failed to connect to OpenSearch. Client ping failed.")
                self.client = None # Ensure client is None if connection failed
            else:
                print("Successfully connected to OpenSearch.")
        except Exception as e:
            # Log this error
            print(f"Error connecting to OpenSearch: {e}")
            self.client = None

    def is_connected(self) -> bool:
        return self.client is not None and self.client.ping()

    def fetch_user_data_by_uid(self, uid: str) -> Optional[dict]:
        if not self.is_connected():
            print("OpenSearch client is not available. Cannot fetch user data.")
            return None

        index_name = "resume_text-embedding-3-large_3072_100000_300_20250221_175445"
        query = {
            "query": {
                "match": {
                    "metadata.U_ID": uid
                }
            }
        }

        try:
            response = self.client.search(
                index=index_name,
                body=query
            )
            
            if response['hits']['hits']:
                return response['hits']['hits'][0]['_source']
            else:
                print(f"No document found with U_ID: {uid} in index {index_name}")
                return None
        except Exception as e:
            print(f"Error fetching user data by UID '{uid}' from index '{index_name}': {e}")
            return None

    def execute_query(self, index_name: str, query: dict) -> list:
        if not self.is_connected():
            print("OpenSearch client is not available. Cannot execute query.")
            # Or raise an exception: raise ConnectionError("OpenSearch client not available")
            return []

        try:
            response = self.client.search(
                index=index_name,
                body=query,
                _source_excludes=["vector_field"] # Exclude the vector_field
            )
            results = []
            if not response['hits']['hits']:
                print(f"No results found in index '{index_name}' for the given query.")
                return []
            for hit in response['hits']['hits']:
                result_doc = hit['_source']
                # Ensure _id and _score are added only if they exist, though they typically do.
                if '_id' in hit:
                    result_doc['_id'] = hit['_id']
                if '_score' in hit:
                    result_doc['_score'] = hit['_score']
                results.append(result_doc)
            return results
        except Exception as e:
            print(f"Error executing OpenSearch query on index '{index_name}': {e}")
            # print(f"Failed query: {query}") # For debugging, consider more structured logging
            return []
