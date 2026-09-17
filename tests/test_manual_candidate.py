import unittest
import json
import sys
import os

# Add src directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from dashboard import app
from database import init_db, create_vacancy, get_vacancies, get_candidate_by_id, delete_candidate

class ManualCandidateTestCase(unittest.TestCase):
    def setUp(self):
        init_db()
        self.app = app.test_client()
        self.app.testing = True

        # Ensure we have a test vacancy
        vacs = get_vacancies(status="all")
        if not vacs:
            v_id = create_vacancy(
                title="Lead Mobile Architect",
                target_country="Mexico",
                description="Lead Mobile Architect position looking for iOS and Android experts."
            )
            self.vacancy_id = v_id
        else:
            self.vacancy_id = vacs[0]["id"]
            
        self.created_cand_ids = []

    def tearDown(self):
        for cid in self.created_cand_ids:
            delete_candidate(cid)

    def test_create_candidate_success(self):
        payload = {
            "vacancy_id": self.vacancy_id,
            "name": "Alex Mercer",
            "linkedin_url": "https://www.linkedin.com/in/alex-mercer-test-12345/",
            "headline": "Senior Staff Architect | Cloud & AI",
            "location": "Mexico City, Mexico",
            "status": "contacted",
            "score": 92,
            "open_to_work": True,
            "location_compatible": True,
            "notes": "Spoke at PyCon, excellent communication and portfolio.",
            "suggested_message": "Hi Alex, great connecting with you!"
        }
        
        response = self.app.post(
            '/api/candidates',
            data=json.dumps(payload),
            content_type='application/json'
        )
        data = response.get_json()
        print("\n[Test Manual Candidate Creation Response]:", data)
        self.assertEqual(response.status_code, 201)
        self.assertTrue(data.get("success"))
        
        cand_id = data.get("candidate_id")
        self.assertIsNotNone(cand_id)
        self.created_cand_ids.append(cand_id)
        
        # Verify in database
        cand = get_candidate_by_id(cand_id)
        self.assertIsNotNone(cand)
        self.assertEqual(cand["name"], "Alex Mercer")
        self.assertEqual(cand["score"], 92)
        self.assertEqual(cand["status"], "contacted")
        self.assertTrue(bool(cand["open_to_work"]))
        self.assertTrue(bool(cand["location_compatible"]))
        self.assertEqual(cand["notes"], "Spoke at PyCon, excellent communication and portfolio.")
        # Verify automatic subscore distribution
        self.assertEqual(cand["technical_score"], 37)  # round(92 * 0.4)
        self.assertEqual(cand["experience_score"], 37) # round(92 * 0.4)
        self.assertEqual(cand["auxiliary_score"], 18)  # 92 - 37 - 37

    def test_create_candidate_validation_missing_fields(self):
        # Missing name
        res1 = self.app.post(
            '/api/candidates',
            data=json.dumps({"linkedin_url": "https://linkedin.com/in/test"}),
            content_type='application/json'
        )
        self.assertEqual(res1.status_code, 400)
        self.assertFalse(res1.get_json().get("success"))
        
        # Missing URL
        res2 = self.app.post(
            '/api/candidates',
            data=json.dumps({"name": "Test User"}),
            content_type='application/json'
        )
        self.assertEqual(res2.status_code, 400)
        self.assertFalse(res2.get_json().get("success"))

if __name__ == '__main__':
    unittest.main()
