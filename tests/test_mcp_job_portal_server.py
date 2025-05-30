import unittest
from unittest.mock import patch, MagicMock, AsyncMock
import sys
import os
import asyncio

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Temporarily mock OpenSearchService and its methods before mcp_job_portal_server is imported
# This is to prevent actual OpenSearch client instantiation during module import
mock_os_service_instance = MagicMock()
mock_os_service_instance.fetch_user_data_by_uid = MagicMock()

# Check if job_portal_service.opensearch_service is already in sys.modules to avoid re-patching issues
# if 'job_portal_service.opensearch_service' not in sys.modules:
#     mock_opensearch_service_module = MagicMock()
#     mock_opensearch_service_module.OpenSearchService.return_value = mock_os_service_instance
#     sys.modules['job_portal_service.opensearch_service'] = mock_opensearch_service_module

# Mock query_generators before importing mcp_job_portal_server
mock_query_generators_module = MagicMock()
mock_query_generators_module.generate_user_preference_based_job_query = MagicMock()
sys.modules['job_portal_service.query_generators'] = mock_query_generators_module


# Now import the server module. It will use the mocked OpenSearchService.
import mcp_job_portal_server # This line will now use the mocked os_service

# After mcp_job_portal_server is imported, we can specifically patch its global os_service
# and the imported generate_user_preference_based_job_query from query_generators
patch_os_service = patch('mcp_job_portal_server.os_service', mock_os_service_instance)
# The query_generators module itself is mocked, so we patch the reference within mcp_job_portal_server
patch_generate_user_preference = patch('mcp_job_portal_server.generate_user_preference_based_job_query', mock_query_generators_module.generate_user_preference_based_job_query)


class TestMCPServerTools(unittest.TestCase):

    def setUp(self):
        # Apply the patches
        self.patch_os = patch_os_service.start()
        self.mock_os_service = self.patch_os # Get the MagicMock instance
        
        self.patch_gen_pref = patch_generate_user_preference.start()
        self.mock_generate_user_preference = self.patch_gen_pref

        # Reset mocks for each test
        self.mock_os_service.reset_mock()
        self.mock_generate_user_preference.reset_mock()
        
        # Ensure analyze_request is not mocked, or provide a real/simple implementation if needed
        # For these tests, the default analyze_request should be fine.

    def tearDown(self):
        patch_os_service.stop()
        patch_generate_user_preference.stop()

    def run_async(self, coro):
        return asyncio.run(coro)

    def test_generate_search_conditions_no_uid(self):
        # Test case 1: No uid provided
        raw_query = "서울 상급종합병원 의사 월급 1500 이상"
        expected_filters_nlu = {
            "location": "서울",
            "org_type": "상급종합병원",
            "salary_min": 15000000 
        }
        
        conditions = self.run_async(mcp_job_portal_server.generate_search_conditions(raw_query=raw_query))
        
        self.assertEqual(conditions.get("filters"), expected_filters_nlu)
        self.assertEqual(conditions.get("semantic_text"), raw_query)
        self.assertFalse(conditions.get("personalization_applied"))
        self.mock_os_service.fetch_user_data_by_uid.assert_not_called()
        self.mock_generate_user_preference.assert_not_called()

    def test_generate_search_conditions_uid_found_profile(self):
        # Test case 2: uid provided, user data found
        uid = "test_user_1"
        raw_query = "부산 내과 의사" # NLU should extract location: 부산
        
        mock_user_profile = {"metadata": {"U_ID": uid, "USER_SPECIALTY": "Internal Medicine"}}
        self.mock_os_service.fetch_user_data_by_uid.return_value = mock_user_profile
        
        mock_preference_output = {
            "filters": {"specialty": "Internal Medicine"}, # Corresponds to USER_TO_JOB_FILTER_MAP
            "semantic_text": "내과 전문의" # Skills or processed preferences
        }
        self.mock_generate_user_preference.return_value = mock_preference_output
        
        conditions = self.run_async(mcp_job_portal_server.generate_search_conditions(raw_query=raw_query, uid=uid))
        
        self.assertTrue(conditions.get("personalization_applied"))
        
        # Verify filters: NLU (location) + User Profile (specialty)
        # User profile 'specialty' should take precedence or be added.
        # NLU 'location' should remain if not set by user profile.
        expected_filters = {
            "location": "부산", # From NLU
            "specialty": "Internal Medicine" # From user profile
        }
        self.assertEqual(conditions.get("filters"), expected_filters)
        
        # Verify semantic text: raw_query + user profile semantic text
        expected_semantic_text = f"{raw_query} {mock_preference_output['semantic_text']}".strip()
        self.assertEqual(conditions.get("semantic_text"), expected_semantic_text)
        
        self.mock_os_service.fetch_user_data_by_uid.assert_called_once_with(uid)
        self.mock_generate_user_preference.assert_called_once()
        # Check that raw_query was passed as part of semantic_query_parts
        args, kwargs = self.mock_generate_user_preference.call_args
        self.assertEqual(kwargs['user_profile'], mock_user_profile)
        self.assertIn(raw_query, kwargs['semantic_query_parts'])


    def test_generate_search_conditions_uid_not_found(self):
        # Test case 3: uid provided, but user data not found
        uid = "unknown_user"
        raw_query = "제주도 의원" # NLU: location: 제주
        
        self.mock_os_service.fetch_user_data_by_uid.return_value = None # Simulate user not found
        
        conditions = self.run_async(mcp_job_portal_server.generate_search_conditions(raw_query=raw_query, uid=uid))
        
        self.assertFalse(conditions.get("personalization_applied"))
        expected_filters_nlu = {"location": "제주"} # Only NLU filters
        self.assertEqual(conditions.get("filters"), expected_filters_nlu)
        self.assertEqual(conditions.get("semantic_text"), raw_query)
        
        self.mock_os_service.fetch_user_data_by_uid.assert_called_once_with(uid)
        self.mock_generate_user_preference.assert_not_called()

    def test_generate_search_conditions_uid_found_empty_raw_query(self):
        # Test case 4: uid provided, user data found, but raw_query is empty
        uid = "test_user_2"
        raw_query = "" 
        
        mock_user_profile = {"metadata": {"U_ID": uid, "USER_DESIRED_LOCATION": "경기"}}
        self.mock_os_service.fetch_user_data_by_uid.return_value = mock_user_profile
        
        mock_preference_output = {
            "filters": {"location": "경기"}, 
            "semantic_text": "경기 지역 선호"
        }
        self.mock_generate_user_preference.return_value = mock_preference_output
        
        conditions = self.run_async(mcp_job_portal_server.generate_search_conditions(raw_query=raw_query, uid=uid))
        
        self.assertTrue(conditions.get("personalization_applied"))
        expected_filters = {"location": "경기"}
        self.assertEqual(conditions.get("filters"), expected_filters)
        self.assertEqual(conditions.get("semantic_text"), mock_preference_output['semantic_text']) # Should be only user's semantic text
        
        self.mock_os_service.fetch_user_data_by_uid.assert_called_once_with(uid)
        # semantic_query_parts passed to generate_user_preference should be empty or contain an empty string
        args, kwargs = self.mock_generate_user_preference.call_args
        self.assertEqual(kwargs['user_profile'], mock_user_profile)
        self.assertTrue(not kwargs['semantic_query_parts'] or kwargs['semantic_query_parts'] == [''])


    def test_generate_search_conditions_nlu_filter_precedence(self):
        # Test that NLU filters are applied if not set by user profile
        uid = "test_user_3"
        raw_query = "서울 영상의학과" # NLU: location: 서울
        
        # User profile only has specialty, no location preference
        mock_user_profile = {"metadata": {"U_ID": uid, "USER_SPECIALTY": "Radiology"}}
        self.mock_os_service.fetch_user_data_by_uid.return_value = mock_user_profile
        
        mock_preference_output = {
            "filters": {"specialty": "Radiology"}, 
            "semantic_text": "영상의학"
        }
        self.mock_generate_user_preference.return_value = mock_preference_output
        
        conditions = self.run_async(mcp_job_portal_server.generate_search_conditions(raw_query=raw_query, uid=uid))
        
        self.assertTrue(conditions.get("personalization_applied"))
        expected_filters = {
            "location": "서울",       # From NLU
            "specialty": "Radiology"  # From user profile
        }
        self.assertEqual(conditions.get("filters"), expected_filters)


    def test_generate_search_conditions_user_filter_overwrites_nlu(self):
        # Test that user profile filters overwrite NLU filters for the same key
        uid = "test_user_4"
        raw_query = "서울 내과 의사" # NLU: location: 서울, (potentially specialty if NLU was more advanced)
        
        # User profile has a different location preference
        mock_user_profile = {"metadata": {"U_ID": uid, "USER_DESIRED_LOCATION": "부산", "USER_SPECIALTY": "Internal Medicine"}}
        self.mock_os_service.fetch_user_data_by_uid.return_value = mock_user_profile
        
        mock_preference_output = {
            "filters": {"location": "부산", "specialty": "Internal Medicine"}, 
            "semantic_text": "부산 내과 선호"
        }
        self.mock_generate_user_preference.return_value = mock_preference_output
        
        conditions = self.run_async(mcp_job_portal_server.generate_search_conditions(raw_query=raw_query, uid=uid))
        
        self.assertTrue(conditions.get("personalization_applied"))
        expected_filters = {
            "location": "부산",               # Overwritten by user profile
            "specialty": "Internal Medicine"  # From user profile
        }
        # NLU might have tried to set location to 서울, but user's 부산 should win.
        self.assertEqual(conditions.get("filters"), expected_filters)

if __name__ == '__main__':
    unittest.main()
