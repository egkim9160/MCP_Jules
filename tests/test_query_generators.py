import unittest
import sys
import os

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from job_portal_service.query_generators import generate_user_preference_based_job_query, USER_TO_JOB_FILTER_MAP

class TestQueryGenerators(unittest.TestCase):

    def test_generate_user_preference_based_job_query_all_fields(self):
        # Test case 1: Profile with all preference fields
        user_profile = {
            "metadata": {
                "USER_SPECIALTY": "Cardiology",
                "USER_DESIRED_LOCATION": "Seoul",
                "USER_EMPLOYMENT_TYPE": "Full-time",
                "USER_SKILLS": ["echo", "stent"]
            }
        }
        semantic_query_parts = ["general doctor"]
        
        result = generate_user_preference_based_job_query(user_profile, semantic_query_parts)
        
        expected_filters = {
            USER_TO_JOB_FILTER_MAP["metadata.USER_SPECIALTY"]: "Cardiology",
            USER_TO_JOB_FILTER_MAP["metadata.USER_DESIRED_LOCATION"]: "Seoul",
            USER_TO_JOB_FILTER_MAP["metadata.USER_EMPLOYMENT_TYPE"]: "Full-time",
        }
        self.assertEqual(result['filters'], expected_filters)
        
        # Order of semantic text parts might vary, so check for inclusion
        self.assertIn("general doctor", result['semantic_text'])
        self.assertIn("echo", result['semantic_text'])
        self.assertIn("stent", result['semantic_text'])
        # Check for combined string with spaces
        self.assertTrue(all(skill in result['semantic_text'].split() for skill in ["general", "doctor", "echo", "stent"]))


    def test_generate_user_preference_based_job_query_missing_fields(self):
        # Test case 2: Profile with some missing fields (no USER_SKILLS)
        user_profile = {
            "metadata": {
                "USER_SPECIALTY": "Pediatrics",
                "USER_DESIRED_LOCATION": "Busan",
                # "USER_EMPLOYMENT_TYPE": "Part-time", # Missing employment type
            }
        }
        semantic_query_parts = ["child specialist"]
        
        result = generate_user_preference_based_job_query(user_profile, semantic_query_parts)
        
        expected_filters = {
            USER_TO_JOB_FILTER_MAP["metadata.USER_SPECIALTY"]: "Pediatrics",
            USER_TO_JOB_FILTER_MAP["metadata.USER_DESIRED_LOCATION"]: "Busan",
        }
        self.assertEqual(result['filters'], expected_filters)
        self.assertEqual(result['semantic_text'], "child specialist")

    def test_generate_user_preference_based_job_query_skills_as_string(self):
        # Test case 3: Profile with skills as a string
        user_profile = {
            "metadata": {
                "USER_SPECIALTY": "Emergency",
                "USER_SKILLS": "critical care"
            }
        }
        semantic_query_parts = ["ER physician"]
        
        result = generate_user_preference_based_job_query(user_profile, semantic_query_parts)
        
        expected_filters = {
            USER_TO_JOB_FILTER_MAP["metadata.USER_SPECIALTY"]: "Emergency",
        }
        self.assertEqual(result['filters'], expected_filters)
        self.assertTrue(all(skill in result['semantic_text'].split() for skill in ["ER", "physician", "critical", "care"]))

    def test_generate_user_preference_based_job_query_empty_initial_semantic_parts(self):
        # Test case 4: Empty initial semantic_query_parts
        user_profile = {
            "metadata": {
                "USER_DESIRED_LOCATION": "Jeju",
                "USER_SKILLS": ["relaxing", "healing"]
            }
        }
        semantic_query_parts = []
        
        result = generate_user_preference_based_job_query(user_profile, semantic_query_parts)
        
        expected_filters = {
            USER_TO_JOB_FILTER_MAP["metadata.USER_DESIRED_LOCATION"]: "Jeju",
        }
        self.assertEqual(result['filters'], expected_filters)
        self.assertTrue(all(skill in result['semantic_text'].split() for skill in ["relaxing", "healing"]))
        self.assertFalse(" " in result['semantic_text'].strip().split() if not result['semantic_text'].strip() else False)


    def test_generate_user_preference_based_job_query_no_metadata_in_profile(self):
        # Additional test: user_profile without "metadata" key
        user_profile = {
            "SOME_OTHER_FIELD": "some_value"
            # "metadata" key is missing
        }
        semantic_query_parts = ["search term"]
        
        result = generate_user_preference_based_job_query(user_profile, semantic_query_parts)
        
        self.assertEqual(result['filters'], {}) # No filters should be generated
        self.assertEqual(result['semantic_text'], "search term")

    def test_generate_user_preference_based_job_query_empty_profile_and_parts(self):
        # Additional test: empty user_profile and empty semantic_query_parts
        user_profile = {}
        semantic_query_parts = []
        
        result = generate_user_preference_based_job_query(user_profile, semantic_query_parts)
        
        self.assertEqual(result['filters'], {})
        self.assertEqual(result['semantic_text'], "")

if __name__ == '__main__':
    unittest.main()
