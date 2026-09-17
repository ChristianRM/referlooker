import unittest
import json
import sys
import os

# Add src directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from dashboard import app, queue_manager
from database import init_db, create_vacancy, get_vacancies, get_vacancy_by_id

class CopilotEndpointsTestCase(unittest.TestCase):
    def setUp(self):
        init_db()
        self.app = app.test_client()
        self.app.testing = True

        # Ensure we have at least one test vacancy
        vacs = get_vacancies(status="all")
        if not vacs:
            v_id = create_vacancy(
                title="Staff AI/ML Engineer",
                target_country="Mexico",
                description="Looking for a Staff AI/ML Engineer with deep experience in PyTorch, Python, LLMs, and distributed training."
            )
            self.vacancy_id = v_id
        else:
            self.vacancy_id = vacs[0]["id"]

    def test_copilot_initial_endpoint(self):
        response = self.app.post(
            '/api/copilot/initial',
            data=json.dumps({"vacancy_id": self.vacancy_id}),
            content_type='application/json'
        )
        data = response.get_json()
        print("\n[Test Copilot Initial Response]:", data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(data.get("success"))
        self.assertIn("search_query", data)
        self.assertIn("reply", data)
        self.assertTrue(len(data.get("search_query", "")) > 0)

    def test_copilot_chat_endpoint(self):
        # Multi-turn refinement test
        history = [
            {"role": "assistant", "content": "Hello! I have analyzed the Job Description..."}
        ]
        msg = "Please focus strictly on candidates with PyTorch expertise and eliminate any mentions of TensorFlow."
        response = self.app.post(
            '/api/copilot/chat',
            data=json.dumps({
                "vacancy_id": self.vacancy_id,
                "message": msg,
                "history": history,
                "current_query": 'site:linkedin.com/in ("AI Engineer" OR "ML Engineer")'
            }),
            content_type='application/json'
        )
        data = response.get_json()
        print("\n[Test Copilot Chat Response]:", data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(data.get("success"))
        self.assertIn("reply", data)
        self.assertIn("search_query", data)
        self.assertTrue(len(data.get("reply", "")) > 0)

    def test_run_search_with_custom_query(self):
        custom_q = 'site:linkedin.com/in ("Staff AI" OR "Principal AI") "PyTorch" "Mexico"'
        response = self.app.post(
            f'/api/vacancies/{self.vacancy_id}/run-search',
            data=json.dumps({
                "target_count": 1,
                "custom_query": custom_q
            }),
            content_type='application/json'
        )
        data = response.get_json()
        print("\n[Test Run Search with Custom Query]:", data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(data.get("success"))
        
        # Cancel search immediately so it doesn't run full scraping in test
        self.app.post(f'/api/vacancies/{self.vacancy_id}/cancel-search')

if __name__ == '__main__':
    unittest.main()
