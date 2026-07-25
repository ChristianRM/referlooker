import os
import sys
import json
import shutil
import pandas as pd

# Add current directory to path just in case
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from query_generator import generate_search_query, generate_refined_search_query
from search_engine import search_candidates
from linkedin_scraper import scrape_linkedin_profile, ensure_linkedin_session
from evaluator import evaluate_candidate
from cli import run_cli

class Tee:
    def __init__(self, filename, mode="a"):
        self.file = open(filename, mode, encoding="utf-8")
        self.stdout = sys.stdout
        self.stderr = sys.stderr

    def write(self, message):
        self.stdout.write(message)
        self.file.write(message)
        self.file.flush()

    def flush(self):
        self.stdout.flush()
        self.file.flush()

def load_config():
    """Loads config.json if it exists."""
    config_path = "config.json"
    if not os.path.exists(config_path):
        print(f"[Error] Configuration file not found at {config_path}")
        sys.exit(1)
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)

def setup_directories():
    """Creates the necessary directories if they do not exist."""
    os.makedirs("vacancies", exist_ok=True)
    os.makedirs("processed/archived_vacancies", exist_ok=True)
    os.makedirs("output", exist_ok=True)

def load_processed_urls() -> dict:
    """Loads the history of processed URLs to avoid duplicates."""
    history_path = "output/processed_urls.json"
    if os.path.exists(history_path):
        try:
            with open(history_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            print("[Warning] Could not read processed_urls.json. A new one will be created.")
            return {}
    return {}

def save_processed_urls(processed_dict: dict):
    """Saves the history of processed URLs."""
    history_path = "output/processed_urls.json"
    with open(history_path, "w", encoding="utf-8") as f:
        json.dump(processed_dict, f, indent=2, ensure_ascii=False)

def update_excel_report(candidate_info: dict, excel_path: str):
    """Inserts or updates a candidate in the Excel report."""
    columns = ["Associated Vacancy", "Candidate / Headline", "Score", "Score Breakdown", "Evaluation Summary (LLM)", "LinkedIn URL", "Status"]
    
    if os.path.exists(excel_path):
        try:
            df = pd.read_excel(excel_path)
            # Ensure missing columns are added if the file existed previously
            for col in columns:
                if col not in df.columns:
                    df[col] = None
        except Exception:
            df = pd.DataFrame(columns=columns)
    else:
        df = pd.DataFrame(columns=columns)
        
    url = candidate_info.get("LinkedIn URL")
    if not url:
        return
        
    exists = df["LinkedIn URL"] == url
    new_row = pd.DataFrame([candidate_info])
    
    if exists.any():
        # Update existing row
        idx = df[exists].index[0]
        for col in columns:
            df.at[idx, col] = candidate_info[col]
    else:
        # Append the new row
        df = pd.concat([df, new_row], ignore_index=True)
        
    df.to_excel(excel_path, index=False)

def regenerate_reports(excel_path: str, txt_path: str):
    """
    Sorts and regenerates the reports based on the Excel file.
    """
    if not os.path.exists(excel_path):
        return
        
    try:
        df = pd.read_excel(excel_path)
        if df.empty:
            return
            
        # Create a temporary numeric column for sorting the Score (e.g., "94%" -> 94.0)
        df["Score_Num"] = df["Score"].astype(str).str.rstrip("%").astype(float, errors="ignore")
        
        # Sort by Vacancy (alphabetical) and then by Score_Num (descending)
        df = df.sort_values(by=["Associated Vacancy", "Score_Num"], ascending=[True, False])
        df = df.drop(columns=["Score_Num"])
        
        # Save sorted Excel file
        df.to_excel(excel_path, index=False)
        
        # Write consolidated report in TXT format
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write("============================================================\n")
            f.write("      CONSOLIDATED REPORT OF DESIRABLE CANDIDATES\n")
            f.write("============================================================\n")
            f.write(f"Total Candidates: {len(df)}\n")
            
            current_vacancy = None
            for _, row in df.iterrows():
                vac = row["Associated Vacancy"]
                if vac != current_vacancy:
                    current_vacancy = vac
                    f.write(f"\n============================================================\n")
                    f.write(f"VACANCY: {current_vacancy}\n")
                    f.write(f"============================================================\n")
                
                f.write(f"Candidate: {row['Candidate / Headline']}\n")
                f.write(f"Score: {row['Score']}\n")
                if 'Score Breakdown' in row and pd.notna(row['Score Breakdown']):
                    f.write(f"Score Breakdown: {row['Score Breakdown']}\n")
                f.write(f"LinkedIn: {row['LinkedIn URL']}\n")
                f.write(f"Status: {row['Status']}\n")
                f.write(f"Evaluation Summary: {row['Evaluation Summary (LLM)']}\n")
                f.write(f"------------------------------------------------------------\n")
                
        print(f"[Report] Reports successfully updated in 'output/'.")
    except Exception as e:
        print(f"[Error] Could not regenerate reports: {e}")

def update_json_report(candidate_info: dict):
    """
    Adds or updates a candidate in the consolidated JSON database (output/candidates.json).
    Classifies in 'desirable_candidates' if score is >= 85%, else in 'undesirable_candidates'.
    """
    json_path = "output/candidates.json"
    
    # Initialize empty structure
    report = {
        "desirable_candidates": [],
        "undesirable_candidates": []
    }
    
    if os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                if isinstance(loaded, dict):
                    report["desirable_candidates"] = loaded.get("desirable_candidates", [])
                    report["undesirable_candidates"] = loaded.get("undesirable_candidates", [])
        except Exception:
            pass
            
    url = candidate_info.get("linkedin_url")
    
    # Remove previous duplicates of the same candidate from both lists
    report["desirable_candidates"] = [c for c in report["desirable_candidates"] if c.get("linkedin_url") != url]
    report["undesirable_candidates"] = [c for c in report["undesirable_candidates"] if c.get("linkedin_url") != url]
    
    score = candidate_info.get("score", 0)
    
    # Save into the corresponding category list
    if score >= 85:
        report["desirable_candidates"].append(candidate_info)
        print(f"[JSON Database] Candidate '{candidate_info.get('name')}' added to 'desirable_candidates' (Score: {score}%)")
    else:
        report["undesirable_candidates"].append(candidate_info)
        print(f"[JSON Database] Candidate '{candidate_info.get('name')}' added to 'undesirable_candidates' (Score: {score}%)")
        
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    # If it meets the threshold, update the Excel and TXT reports
    if score >= 85:
        excel_record = {
            "Associated Vacancy": candidate_info.get("vacancy", "Unknown"),
            "Candidate / Headline": f"{candidate_info.get('name', 'Unknown')} | {candidate_info.get('headline', 'No headline')}",
            "Score": f"{score}%",
            "Score Breakdown": f"Tech: {candidate_info.get('technical_score', 0)}/40 | Exp: {candidate_info.get('experience_score', 0)}/40 | Aux: {candidate_info.get('auxiliary_score', 0)}/20",
            "Evaluation Summary (LLM)": candidate_info.get("evaluation_summary", ""),
            "LinkedIn URL": url,
            "Status": "Pending"
        }
        update_excel_report(excel_record, "output/desirable_candidates.xlsx")
        regenerate_reports("output/desirable_candidates.xlsx", "output/desirable_candidates.txt")

def process_vacancy(vac_file: str, vac_folder: str, config: dict, processed_history: dict):
    """Processes a single vacancy (query generation, search, scraping, evaluation)."""
    vac_path = os.path.join(vac_folder, vac_file)
    print(f"\n" + "-" * 50)
    print(f"Processing vacancy: {vac_file} from '{vac_folder}'")
    print("-" * 50)
    
    with open(vac_path, "r", encoding="utf-8") as f:
        vacancy_text = f.read().strip()
        
    if not vacancy_text:
        print(f"[Warning] Vacancy file {vac_file} is empty. Skipping.")
        return
        
    # 1. Generate Google X-Ray search query with local LLM
    print("Generating X-Ray search query with Ollama...")
    analysis = generate_search_query(vacancy_text, config)
    role = analysis.get("role", "Unknown")
    query = analysis.get("search_query", "")
    target_country = analysis.get("target_country", "Any")
    
    print(f"Role detected: {role}")
    print(f"Target country for vacancy: {target_country}")
    print(f"Generated query: {query}")
    
    if not query:
        print("[Error] Could not generate a valid search query. Skipping vacancy.")
        return
        
    satisfied = False
    refined_query = query
    
    while not satisfied:
        # Determine current search offset based on previously processed candidates for this vacancy
        start_offset = sum(1 for url, info in processed_history.items() if info.get("vacante") == vac_file)
        candidate_urls = search_candidates(refined_query, config, start_offset=start_offset)
        
        if not candidate_urls:
            print(f"[Warning] No LinkedIn profiles found with the current query.")
        else:
            # Verify that the LinkedIn session is active (assisting visibly if expired)
            if any(url not in processed_history for url in candidate_urls):
                ensure_linkedin_session(config)
                
            # Scrape and evaluate candidates
            for url in candidate_urls:
                if url in processed_history:
                    print(f"[Skipped] Candidate already processed: {url}")
                    continue
                    
                # Scrape profile (includes Phase 1 country check)
                profile = scrape_linkedin_profile(url, target_country, config)
                
                # Register URL in history logs
                processed_history[url] = {
                    "vacante": vac_file,
                    "status": profile["status"],
                    "name": profile["name"],
                    "timestamp": pd.Timestamp.now().isoformat()
                }
                save_processed_urls(processed_history)
                
                # If discarded in Phase 1 due to location mismatch
                if profile["status"] == "location_mismatch":
                    candidate_record = {
                        "vacancy": vac_file,
                        "name": profile["name"] or "Unknown",
                        "headline": profile["headline"] or "No headline",
                        "technical_score": 0,
                        "experience_score": 0,
                        "auxiliary_score": 0,
                        "score": 0,
                        "open_to_work": False,
                        "evaluation_summary": f"Automatically discarded: location mismatch. (Candidate location: '{profile.get('location')}', Job requires: '{target_country}').",
                        "linkedin_url": url,
                        "location": profile.get("location") or "Not specified",
                        "about": profile.get("about") or "",
                        "experience": profile.get("experience") or "",
                        "skills": profile.get("skills") or "",
                        "timestamp": pd.Timestamp.now().isoformat()
                    }
                    update_json_report(candidate_record)
                    continue
                    
                # If scraping error occurred
                if profile["status"] != "success":
                    print(f"[Scraper Error] Could not process {url}: {profile['error_message']}")
                    candidate_record = {
                        "vacancy": vac_file,
                        "name": profile["name"] or "Unknown",
                        "headline": profile["headline"] or "No headline",
                        "technical_score": 0,
                        "experience_score": 0,
                        "auxiliary_score": 0,
                        "score": 0,
                        "open_to_work": False,
                        "evaluation_summary": f"Scraping error: {profile['error_message']}",
                        "linkedin_url": url,
                        "location": profile.get("location") or "Not specified",
                        "about": profile.get("about") or "",
                        "experience": profile.get("experience") or "",
                        "skills": profile.get("skills") or "",
                        "timestamp": pd.Timestamp.now().isoformat()
                    }
                    update_json_report(candidate_record)
                    continue
                    
                # Perform full profile evaluation with Ollama
                print(f"Evaluating candidate profile '{profile['name']}' against job description...")
                evaluation = evaluate_candidate(profile, vacancy_text, config)
                score = evaluation["match_score"]
                open_to_work = evaluation["open_to_work"]
                eval_summary = evaluation["evaluation_summary"]
                
                print(f"--> Match Score: {score}% | OpenToWork: {open_to_work}")
                
                # Save structured JSON candidate details
                candidate_record = {
                    "vacancy": vac_file,
                    "name": profile["name"] or "Unknown",
                    "headline": profile["headline"] or "No headline",
                    "technical_score": int(evaluation.get("technical_score", 0)),
                    "experience_score": int(evaluation.get("experience_score", 0)),
                    "auxiliary_score": int(evaluation.get("auxiliary_score", 0)),
                    "score": int(score),
                    "open_to_work": bool(open_to_work),
                    "evaluation_summary": eval_summary,
                    "linkedin_url": url,
                    "location": profile.get("location") or "Not specified",
                    "about": profile.get("about") or "",
                    "experience": profile.get("experience") or "",
                    "skills": profile.get("skills") or "",
                    "timestamp": pd.Timestamp.now().isoformat()
                }
                update_json_report(candidate_record)
                
        # Show interactive summary of candidates processed for this vacancy
        print(f"\n" + "=" * 60)
        print(f"   CANDIDATE SUMMARY FOR VACANCY: {vac_file}")
        print(f"   (Required Country: {target_country})")
        print(f"=" * 60)
        
        vacancy_candidates = []
        if os.path.exists("output/candidates.json"):
            try:
                with open("output/candidates.json", "r", encoding="utf-8") as f:
                    report = json.load(f)
                    all_cands = report.get("desirable_candidates", []) + report.get("undesirable_candidates", [])
                    vacancy_candidates = [c for c in all_cands if c.get("vacancy") == vac_file]
            except Exception:
                pass
        
        if vacancy_candidates:
            # Sort by score descending
            vacancy_candidates.sort(key=lambda x: x.get("score", 0), reverse=True)
            for c in vacancy_candidates:
                print(f"- {c.get('name')} | Score: {c.get('score')}% | Location: {c.get('location')} | URL: {c.get('linkedin_url')}")
        else:
            print("No candidates processed for this vacancy yet.")
        print("=" * 60)
        
        satisfy_input = input(f"\nAre you satisfied with the results obtained for vacancy '{vac_file}'? (Y/N) [Y]: ").strip().lower()
        if satisfy_input in ("", "y", "yes"):
            satisfied = True
            # Move to history if processed from the active vacancies folder
            if vac_folder == "vacancies":
                dest_path = os.path.join("processed/archived_vacancies", vac_file)
                try:
                    if os.path.exists(dest_path):
                        os.remove(dest_path)
                    shutil.move(vac_path, dest_path)
                    print(f"Vacancy file archived to: {dest_path}")
                except Exception as e:
                    print(f"[Error] Could not archive vacancy file: {e}")
            else:
                print(f"[Info] Keeping vacancy in archived history: {vac_path}")
        else:
            refine_input = input("Would you like Ollama to auto-refine the search query to find more candidates? (Y/N) [Y]: ").strip().lower()
            if refine_input in ("", "y", "yes"):
                print("Requesting query refinement from Ollama...")
                new_refined = generate_refined_search_query(vacancy_text, refined_query, config)
                if new_refined:
                    print(f"\n--> Ollama generated the following refined query:\n{new_refined}")
                    use_refined = input("Would you like to execute the search with this refined query? (Y/N) [Y]: ").strip().lower()
                    if use_refined in ("", "y", "yes"):
                        refined_query = new_refined
                    else:
                        print("[Info] Refined query discarded. Retrying with previous query.")
                else:
                    print("[Warning] Ollama could not generate a refined query. Retrying with previous query.")
            else:
                print(f"[Info] Leaving vacancy '{vac_file}' in '{vac_folder}' for future execution runs.")
                break

def main():
    setup_directories()
    # Initialize Tee to log terminal outputs to file
    tee = Tee("output/referral_bot.log", mode="w")
    sys.stdout = tee
    sys.stderr = tee
    
    config = load_config()
    
    while True:
        print("\n" + "=" * 60)
        print("                 REFERLOOKER - MAIN MENU")
        print("=" * 60)
        print("1. Process open vacancies (folder 'vacancies/')")
        print("2. Resume search for processed vacancies (folder 'processed/archived_vacancies/')")
        print("3. Browse and filter candidates (interactive CLI)")
        print("q. Quit")
        print("=" * 60)
        
        opc = input("Select an option: ").strip()
        
        if opc == "1":
            vacancy_files = [f for f in os.listdir("vacancies") if f.endswith(".txt")]
            if not vacancy_files:
                print("\nNo vacancy descriptions (.txt) found in the 'vacancies/' folder.")
                print("Drop vacancy description files in the folder and try again.")
                continue
                
            print(f"\nStarting processing of {len(vacancy_files)} open vacancy(ies)...")
            for vac_file in vacancy_files:
                processed_history = load_processed_urls()
                process_vacancy(vac_file, "vacancies", config, processed_history)
                
        elif opc == "2":
            history_files = [f for f in os.listdir("processed/archived_vacancies") if f.endswith(".txt")]
            if not history_files:
                print("\nNo archived vacancies found in 'processed/archived_vacancies/'.")
                continue
                
            print("\nSelect the vacancy you wish to resume:")
            for idx, file in enumerate(history_files, 1):
                print(f"{idx}. {file}")
            print("q. [Back to main menu]")
            
            sel = input("\nOption: ").strip()
            if sel.lower() == 'q':
                continue
            elif sel.isdigit():
                sel_idx = int(sel)
                if 1 <= sel_idx <= len(history_files):
                    vac_file = history_files[sel_idx - 1]
                    processed_history = load_processed_urls()
                    process_vacancy(vac_file, "processed/archived_vacancies", config, processed_history)
                else:
                    print("Invalid option.")
            else:
                print("Invalid option.")
                
        elif opc == "3":
            # Start interactive CLI browser
            run_cli()
            
        elif opc.lower() == "q":
            print("\nExiting ReferLooker. See you soon!")
            break
        else:
            print("\nInvalid option. Please try again.")
            
    print("\nProcessing completed.")

if __name__ == "__main__":
    main()
