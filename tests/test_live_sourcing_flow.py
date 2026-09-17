import unittest
import json
import sys
import os
import threading
import time

# Add src directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from dashboard import app, queue_manager, sourcing_jobs
from database import init_db, create_vacancy, get_vacancies

class LiveSourcingFlowTestCase(unittest.TestCase):
    def setUp(self):
        init_db()
        self.app = app.test_client()
        self.app.testing = True

        vacs = get_vacancies(status="all")
        if not vacs:
            self.vacancy_id = create_vacancy(
                title="Senior Data Scientist",
                target_country="Mexico",
                description="Senior Data Scientist proficient with Python, NLP, PyTorch and AWS."
            )
        else:
            self.vacancy_id = vacs[0]["id"]

    def test_search_status_structure(self):
        # Even when no active search, status should return valid structure inside "job"
        response = self.app.get(f'/api/vacancies/{self.vacancy_id}/search-status')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data.get("success"))
        self.assertIn("job", data)
        job = data["job"]
        self.assertIn("running", job)
        self.assertIn("matched_candidates", job)
        self.assertIn("discarded_candidates", job)
        self.assertIn("discard_stats", job)
        self.assertIn("is_paused", job)
        self.assertIn("custom_query", job)

    def test_pause_resume_endpoints(self):
        # Simulate an active search state in sourcing_jobs dict
        sourcing_jobs[self.vacancy_id] = {
            "title": "Senior Data Scientist",
            "logs": ["Starting test search"],
            "running": True,
            "paused": False,
            "pause_event": threading.Event(),
            "custom_query": 'site:linkedin.com/in "Senior Data Scientist" "Mexico"',
            "progress": 2,
            "target": 5,
            "matched_candidates": [
                {
                    "name": "Jane Doe",
                    "headline": "Lead AI Scientist",
                    "location": "Mexico City, Mexico",
                    "match_score": 92,
                    "linkedin_url": "https://linkedin.com/in/janedoe"
                }
            ],
            "discarded_candidates": [
                {
                    "name": "John Smith",
                    "headline": "Marketing Specialist",
                    "location": "Madrid, Spain",
                    "reason": "Location mismatch (Expected: Mexico, Found: Spain)"
                }
            ],
            "discard_stats": {
                "total_discarded": 1,
                "location_mismatch": 1,
                "error": 0,
                "low_score": 0
            }
        }
        sourcing_jobs[self.vacancy_id]["pause_event"].set()

        try:
            # 1. Check status reflects simulated active items
            res = self.app.get(f'/api/vacancies/{self.vacancy_id}/search-status')
            data = res.get_json()
            self.assertTrue(data["success"])
            job = data["job"]
            self.assertTrue(job["running"])
            self.assertFalse(job["is_paused"])
            self.assertEqual(len(job["matched_candidates"]), 1)
            self.assertEqual(len(job["discarded_candidates"]), 1)
            self.assertEqual(job["discard_stats"]["location_mismatch"], 1)

            # 2. Pause search
            pause_res = self.app.post(f'/api/vacancies/{self.vacancy_id}/pause-search')
            self.assertEqual(pause_res.status_code, 200)
            pause_data = pause_res.get_json()
            self.assertTrue(pause_data.get("success"))

            # Check status confirms paused
            res_after_pause = self.app.get(f'/api/vacancies/{self.vacancy_id}/search-status')
            self.assertTrue(res_after_pause.get_json()["job"]["is_paused"])

            # 3. Resume search with refined query
            updated_query = 'site:linkedin.com/in "Senior Data Scientist" "CDMX" OR "Guadalajara"'
            resume_res = self.app.post(
                f'/api/vacancies/{self.vacancy_id}/resume-search',
                data=json.dumps({"custom_query": updated_query}),
                content_type='application/json'
            )
            self.assertEqual(resume_res.status_code, 200)
            resume_data = resume_res.get_json()
            self.assertTrue(resume_data.get("success"))
            self.assertEqual(resume_data.get("current_query"), updated_query)

            # Check status confirms unpaused and updated query
            res_after_resume = self.app.get(f'/api/vacancies/{self.vacancy_id}/search-status')
            self.assertFalse(res_after_resume.get_json()["job"]["is_paused"])
            self.assertEqual(res_after_resume.get_json()["job"]["custom_query"], updated_query)

        finally:
            # Clean up sourcing_jobs
            if self.vacancy_id in sourcing_jobs:
                del sourcing_jobs[self.vacancy_id]

    def test_diagnose_search_copilot_endpoint(self):
        discarded_sample = [
            {"name": "Profile 1", "location": "Madrid, Spain", "reason": "Location mismatch (Expected: Mexico, Found: Spain)"},
            {"name": "Profile 2", "location": "London, UK", "reason": "Location mismatch (Expected: Mexico, Found: UK)"},
            {"name": "Profile 3", "location": "Bogota, Colombia", "reason": "Location mismatch (Expected: Mexico, Found: Colombia)"}
        ]
        response = self.app.post(
            '/api/copilot/diagnose-search',
            data=json.dumps({
                "vacancy_id": self.vacancy_id,
                "current_query": 'site:linkedin.com/in ("Senior Data Scientist") "Remote"',
                "discarded_sample": discarded_sample,
                "discard_stats": {"location_mismatch": 3, "total_discarded": 3}
            }),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        print("\n[Test Diagnose Search Copilot Response]:", data)
        self.assertTrue(data.get("success"))
        self.assertIn("reply", data)
        self.assertIn("search_query", data)
        self.assertTrue(len(data.get("reply", "")) > 0)
        self.assertTrue(len(data.get("search_query", "")) > 0)

if __name__ == '__main__':
    unittest.main()

