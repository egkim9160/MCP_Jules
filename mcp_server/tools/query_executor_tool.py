from mcp_server.server.os_client import get_opensearch_client # Corrected import path

def execute_opensearch_query(index_name: str, query: dict) -> list:
    """
    Executes a query against the specified OpenSearch index using the initialized client.
    - index_name: The name of the OpenSearch index ("job_db" or "user_db").
    - query: The OpenSearch query dictionary.
    Returns a list of results (documents).
    """
    try:
        os_client = get_opensearch_client()
        # print(f"Executing query on index '{index_name}': {query}") # Keep for debugging if needed
        
        # The user's OpenSearch setup uses specific index names.
        # These should come from config or be passed accurately.
        # For now, let's assume index_name matches what's in OpenSearch.
        
        response = os_client.search(
            index=index_name,
            body=query
        )
        
        results = []
        for hit in response['hits']['hits']:
            # By default, return the source document, could also include _score or other metadata
            result_doc = hit['_source']
            result_doc['_id'] = hit['_id'] # Often useful to have the document ID
            result_doc['_score'] = hit['_score'] # And the score
            results.append(result_doc)
        
        return results
    except ConnectionError as ce:
        print(f"Connection Error during OpenSearch query: {ce}")
        # Depending on desired error handling, could return empty list or re-raise
        return [] 
    except Exception as e:
        print(f"Error executing OpenSearch query on index '{index_name}': {e}")
        # Log the query that failed for debugging: print(f"Failed query: {query}")
        return [] # Return empty list on error for now
