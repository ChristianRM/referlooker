import os
import sys
import json
import shutil
import pandas as pd

# Ensure sibling modules can be imported
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from query_generator import generate_search_query
from evaluator import evaluate_candidate
from main import update_excel_report, regenerate_reports

def run_mock_integration_test():
    """
    Runs a simulated full system integration test without requiring external APIs or LinkedIn cookies.
    Uses the local Ollama model for candidate evaluation and generates actual output reports.
    """
    print("=" * 60)
    print("STARTING MOCKED INTEGRATION TEST (MOCK TEST)")
    print("=" * 60)
    
    # 1. Prepare directories and mock configurations
    os.makedirs("vacancies", exist_ok=True)
    os.makedirs("output", exist_ok=True)
    os.makedirs("processed/archived_vacancies", exist_ok=True)
    
    config = {
        "ollama": {
            "model": "llama3.1:8b",
            "host": "http://localhost:11434"
        },
        "evaluation": {
            "min_score": 80
        }
    }
    
    # Load mock vacancy description
    vacancy_file = os.path.join("vacancies", "backend_sr.txt")
    if not os.path.exists(vacancy_file):
        # Create fallback file if it does not exist
        with open(vacancy_file, "w", encoding="utf-8") as f:
            f.write("Mock Vacancy: Senior Python Developer (FastAPI, Docker, AWS, PostgreSQL)")
            
    with open(vacancy_file, "r", encoding="utf-8") as f:
        vacancy_text = f.read().strip()
        
    print(f"[1/4] Mock vacancy loaded: {vacancy_file}")
    
    # 2. Generate search query using Ollama
    print("\n[2/4] Generating simulated X-Ray search query with Ollama...")
    query_data = generate_search_query(vacancy_text, config)
    print(f"-> Extracted Role: {query_data.get('role')}")
    print(f"-> Generated X-Ray Query: {query_data.get('search_query')}")
    
    # 3. Mock Candidate Profiles
    print("\n[3/4] Loading simulated LinkedIn profiles...")
    mock_profiles = [
        {
            "url": "https://www.linkedin.com/in/john-doe-backend",
            "name": "John Doe",
            "headline": "Senior Backend Developer | Django | FastAPI | Cloud Architect",
            "about": "Passionate backend developer with 6+ years of experience building scalable and robust APIs using Python, Django, and FastAPI. Actively looking for new professional challenges (Open to Work).",
            "experience": "Senior Backend Engineer at Tech Solutions (2021 - Present).\nLed migration of monolithic microservices to FastAPI and Docker on AWS cloud.\nBackend Developer at Software Factory (2018 - 2021).\nDeveloped REST APIs with Python and PostgreSQL databases.",
            "skills": "Python, FastAPI, Django, PostgreSQL, Docker, AWS, Git, Scrum",
            "status": "success"
        },
        {
            "url": "https://www.linkedin.com/in/mary-smith-data-eng",
            "name": "Mary Smith",
            "headline": "Lead Data Engineer | Spark | Snowflake",
            "about": "Data engineer with extensive experience leading technical teams and designing complex ETL pipelines and modern data infrastructure in Snowflake and Spark.",
            "experience": "Lead Data Engineer at Data Corp (2020 - Present).\nDistributed data modeling using Spark on AWS.\nData Engineer at Analytics Inc (2017 - 2020).\nCreated ETLs in Python and optimized data warehouses.",
            "skills": "Spark, Snowflake, SQL, Python, ETL, AWS",
            "status": "success"
        }
    ]
    
    # 4. Process and Evaluate Candidates
    excel_path = "output/desirable_candidates.xlsx"
    txt_path = "output/desirable_candidates.txt"
    min_score = config["evaluation"]["min_score"]
    
    # Initialize or load simulated processed history logs
    history_path = "output/processed_urls.json"
    processed_history = {}
    if os.path.exists(history_path):
        try:
            with open(history_path, "r", encoding="utf-8") as f:
                processed_history = json.load(f)
        except Exception:
            pass
            
    print(f"\n[4/4] Evaluating {len(mock_profiles)} mock candidates with Ollama...")
    
    for profile in mock_profiles:
        url = profile["url"]
        
        # Evaluate candidate using local Ollama model
        print(f"\nEvaluating candidate: '{profile['name']}' ({profile['headline']})")
        evaluation = evaluate_candidate(profile, vacancy_text, config)
        score = evaluation["match_score"]
        open_to_work = evaluation["open_to_work"]
        eval_summary = evaluation["evaluation_summary"]
        
        print(f"--> Match Score (Ollama): {score}% | OpenToWork: {open_to_work}")
        print(f"--> Summary: {eval_summary}")
        
        # Update history
        processed_history[url] = {
            "vacancy": "backend_sr.txt",
            "status": "success",
            "name": profile["name"],
            "timestamp": pd.Timestamp.now().isoformat()
        }
        
        if score >= min_score:
            print(f"[Accepted] Candidate qualifies for the report ({score}% >= {min_score}%)")
            candidate_record = {
                "Associated Vacancy": "backend_sr.txt",
                "Candidate / Headline": f"{profile['name']} | {profile['headline']}",
                "Score": f"{score}%",
                "Score Breakdown": f"Tech: {evaluation.get('technical_score', 0)}/40 | Exp: {evaluation.get('experience_score', 0)}/40 | Aux: {evaluation.get('auxiliary_score', 0)}/20",
                "Evaluation Summary (LLM)": eval_summary,
                "LinkedIn URL": url,
                "Status": "Pending"
            }
            update_excel_report(candidate_record, excel_path)
        else:
            print(f"[Discarded] Candidate score is below minimum threshold.")
            
    # Save history logs
    with open(history_path, "w", encoding="utf-8") as f:
        json.dump(processed_history, f, indent=2, ensure_ascii=False)
        
    # Copy processed vacancy to archived history
    dest_path = os.path.join("processed/archived_vacancies", "backend_sr.txt")
    try:
        if os.path.exists(dest_path):
            os.remove(dest_path)
        shutil.copy(vacancy_file, dest_path)  # Copy instead of move for tests to preserve mock source file
        print(f"\n[Test] Copy of mock vacancy archived to: {dest_path}")
    except Exception as e:
        print(f"[Warning] Could not archive vacancy file: {e}")
        
    # Regenerate reports consolidating information
    regenerate_reports(excel_path, txt_path)
    
    print("\n" + "=" * 60)
    print("TEST COMPLETED SUCCESSFULLY.")
    print("Please check the 'output/' directory to validate results:")
    print(f"- Excel Report: {os.path.abspath(excel_path)}")
    print(f"- Plain Text Report: {os.path.abspath(txt_path)}")
    print("=" * 60)

if __name__ == "__main__":
    run_mock_integration_test()
