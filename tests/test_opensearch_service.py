import unittest
from unittest.mock import patch, MagicMock
import sys
import os

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from job_portal_service.opensearch_service import OpenSearchService

class TestOpenSearchService(unittest.TestCase):

    @patch('job_portal_service.opensearch_service.OpenSearch')
    def setUp(self, mock_opensearch_constructor):
        # Mock the OpenSearch client connection itself to avoid actual connections
        self.mock_os_client_instance = MagicMock()
        mock_opensearch_constructor.return_value = self.mock_os_client_instance
        
        # Instantiate the service. This will use the mocked OpenSearch constructor
        self.service = OpenSearchService(hosts=[{'host': 'testhost', 'port': 1234}], http_auth=('user', 'pass'))
        # Ensure the client is set to the mocked instance
        self.service.client = self.mock_os_client_instance

    def test_fetch_user_data_by_uid_success(self):
        # Test case 1: Successful fetch
        mock_response = {
            'hits': {
                'hits': [
                    {'_source': {'metadata': {'U_ID': 'test_uid_123'}, 'other_data': 'some_value'}}
                ]
            }
        }
        self.service.client.search = MagicMock(return_value=mock_response)
        self.service.is_connected = MagicMock(return_value=True)

        result = self.service.fetch_user_data_by_uid('test_uid_123')
        self.assertIsNotNone(result)
        self.assertEqual(result, {'metadata': {'U_ID': 'test_uid_123'}, 'other_data': 'some_value'})
        self.service.client.search.assert_called_once()
        args, kwargs = self.service.client.search.call_args
        self.assertEqual(kwargs['index'], "resume_text-embedding-3-large_3072_100000_300_20250221_175445")
        self.assertEqual(kwargs['body']['query']['match']['metadata.U_ID'], 'test_uid_123')

    def test_fetch_user_data_by_uid_not_found(self):
        # Test case 2: User not found
        mock_response = {'hits': {'hits': []}}
        self.service.client.search = MagicMock(return_value=mock_response)
        self.service.is_connected = MagicMock(return_value=True)

        result = self.service.fetch_user_data_by_uid('unknown_uid')
        self.assertIsNone(result)
        self.service.client.search.assert_called_once()

    @patch('builtins.print') # To capture log output
    def test_fetch_user_data_by_uid_client_error(self, mock_print):
        # Test case 3: OpenSearch client error
        self.service.client.search = MagicMock(side_effect=Exception("OpenSearch down"))
        self.service.is_connected = MagicMock(return_value=True)

        result = self.service.fetch_user_data_by_uid('test_uid_error')
        self.assertIsNone(result)
        self.service.client.search.assert_called_once()
        mock_print.assert_any_call("Error fetching user data by UID 'test_uid_error' from index 'resume_text-embedding-3-large_3072_100000_300_20250221_175445': OpenSearch down")

    @patch('builtins.print')
    def test_fetch_user_data_by_uid_not_connected(self, mock_print):
        # Test case 4: OpenSearch not connected
        self.service.is_connected = MagicMock(return_value=False)
        # We also need to mock self.client.search because is_connected might be called,
        # then the code proceeds to call self.client.search if not handled correctly.
        self.service.client.search = MagicMock()


        result = self.service.fetch_user_data_by_uid('test_uid_noconn')
        self.assertIsNone(result)
        # search should not be called if not connected
        self.service.client.search.assert_not_called()
        mock_print.assert_any_call("OpenSearch client is not available. Cannot fetch user data.")

    def test_execute_query_source_excludes(self):
        # Test `execute_query` for `_source_excludes`
        self.service.client.search = MagicMock(return_value={'hits': {'hits': []}})
        self.service.is_connected = MagicMock(return_value=True)
        
        test_index = "my_test_index"
        test_query = {"query": {"match_all": {}}}
        self.service.execute_query(test_index, test_query)

        self.service.client.search.assert_called_once()
        args, kwargs = self.service.client.search.call_args
        self.assertEqual(kwargs['index'], test_index)
        self.assertEqual(kwargs['body'], test_query)
        self.assertIn("_source_excludes", kwargs)
        self.assertEqual(kwargs["_source_excludes"], ["vector_field"])

if __name__ == '__main__':
    unittest.main()
