import os
import sys
import json
import shutil
import time
import pandas as pd

# Add current directory to path just in case
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from query_generator import generate_search_query, generate_refined_search_query, chat_refine_search_query
from search_engine import search_candidates
from linkedin_scraper import scrape_linkedin_profile, ensure_linkedin_session
from evaluator import evaluate_candidate
from cli import run_cli
from database import (
    upsert_candidate,
    init_db,
    get_vacancies,
    get_vacancy_by_id,
    get_candidates,
    update_vacancy,
    get_processed_urls_from_db,
    is_url_processed_in_db
)

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
    """Creates the necessary directories and initializes SQLite database."""
    os.makedirs("output", exist_ok=True)
    init_db()

def update_json_report(candidate_info: dict):
    """
    Saves candidate in SQLite database (output/referlooker.db).
    SQLite is the single source of truth.
    """
    try:
        upsert_candidate(candidate_info)
    except Exception as e:
        print(f"[Database Error] Could not upsert candidate into SQLite: {e}")

def process_vacancy(
    vacancy_input,
    config,
    processed_history=None,
    min_target=5,
    interactive=True,
    progress_callback=None,
    cancel_check=None,
    custom_query=None,
    pause_check=None,
    get_active_query=None,
    on_candidate_evaluated=None,
    on_candidate_discarded=None
):
    """
    Main workflow for a specific vacancy.
    Scrapes and evaluates profiles until reaching min_target newly evaluated candidates.
    Supports progress callbacks, real-time match/discard notifications, in-flight pause, and query refinement.
    """
    def report_progress(msg: str, current_evals: int, is_done: bool = False):
        if progress_callback:
            try:
                progress_callback(msg, current_evals, min_target, is_done)
            except Exception:
                pass

    def wait_if_paused():
        if not pause_check:
            return
        while pause_check():
            if cancel_check and cancel_check():
                return
            time.sleep(0.4)

    def check_query_update(current_q):
        if get_active_query:
            new_q = get_active_query()
            if new_q and new_q.strip() and new_q.strip() != current_q:
                print(f"\n[Query Updated In-Flight] Switching to new query: {new_q.strip()}")
                return new_q.strip(), True
        return current_q, False

    if cancel_check and cancel_check():
        report_progress("Sourcing cancelled by user.", 0, is_done=True)
        return {"success": False, "cancelled": True, "evaluated": 0}

    # Support dictionary (from SQLite vacancies table) or filepath (legacy)
    if isinstance(vacancy_input, dict):
        vac_id = vacancy_input.get("id")
        vac_title = vacancy_input.get("title", "Untitled Vacancy")
        vacancy_text = vacancy_input.get("description", "").strip()
        target_country_configured = vacancy_input.get("target_country", "Any")
    else:
        # Fallback for file path
        vac_file = vacancy_input
        vac_title = os.path.basename(vac_file).replace(".txt", "")
        vac_id = None
        target_country_configured = "Any"
        if os.path.exists(vac_file):
            with open(vac_file, "r", encoding="utf-8") as f:
                vacancy_text = f.read().strip()
        else:
            vacancy_text = ""

    print(f"\n" + "-" * 50)
    print(f"Processing vacancy: {vac_title} (Target: {min_target} evaluated candidates)")
    print("-" * 50)
    report_progress(f"Starting analysis for position '{vac_title}'...", 0)
    
    if not vacancy_text:
        print(f"[Warning] Vacancy description for '{vac_title}' is empty. Skipping.")
        report_progress(f"Empty description. Sourcing finished.", 0, is_done=True)
        return {"success": False, "error": "Empty vacancy description", "evaluated": 0}
        
    # 1. Generate or use custom Google X-Ray search query
    if custom_query and custom_query.strip():
        print("[Copilot] Using recruiter-refined custom X-Ray search query.")
        report_progress("Using refined custom query from AI Copilot...", 0)
        query = custom_query.strip()
        target_country = target_country_configured or "Any"
    else:
        print("Generating X-Ray search query with Ollama...")
        report_progress("Generating AI-optimized search query with Ollama...", 0)
        analysis = generate_search_query(vacancy_text, config)
        role = analysis.get("role", "Unknown")
        query = analysis.get("search_query", "")
        
        # Use target country from database if specified, else from LLM analysis
        if target_country_configured and target_country_configured not in ("Any", "Remote", ""):
            target_country = target_country_configured
        else:
            target_country = analysis.get("target_country", "Any")
        
        print(f"Role detected: {role}")
        print(f"Target country for vacancy: {target_country}")
        
    print(f"Active search query: {query}")
    
    if not query:
        print("[Error] Could not generate a valid search query. Skipping vacancy.")
        report_progress("Error generating search query with AI.", 0, is_done=True)
        return {"success": False, "error": "Could not generate search query", "evaluated": 0}
        
    if processed_history is None:
        processed_history = get_processed_urls_from_db()
    elif isinstance(processed_history, dict):
        processed_history = set(processed_history.keys())
    elif not isinstance(processed_history, set):
        processed_history = set(processed_history)

    satisfied = False
    refined_query = query
    evaluations_count = 0
    current_run_urls = set()
    
    # Always start search from offset 0 (page 1) and filter duplicates via processed_history set
    current_offset = 0
    
    while not satisfied:
        wait_if_paused()
        if cancel_check and cancel_check():
            print("[Cancelled] Sourcing aborted by user.")
            report_progress("Sourcing cancelled by user.", evaluations_count, is_done=True)
            return {"success": False, "cancelled": True, "evaluated": evaluations_count}

        # Check for in-flight query modification
        refined_query, query_changed = check_query_update(refined_query)
        if query_changed:
            current_offset = 0
            report_progress(f"Search query updated. Searching with new parameters...", evaluations_count)

        print(f"\n[Search] Executing query search starting at offset {current_offset}...")
        report_progress(f"Searching candidate profiles (offset {current_offset})...", evaluations_count)
        candidate_urls = search_candidates(refined_query, config, start_offset=current_offset)
        
        wait_if_paused()
        if cancel_check and cancel_check():
            print("[Cancelled] Sourcing aborted by user.")
            report_progress("Sourcing cancelled by user.", evaluations_count, is_done=True)
            return {"success": False, "cancelled": True, "evaluated": evaluations_count}

        if not candidate_urls:
            print(f"[Warning] No candidates returned by the search engine.")
            # If target not reached, auto-refine
            if evaluations_count < min_target:
                print(f"[Info] Target not reached ({evaluations_count}/{min_target}). Auto-refining search query...")
                report_progress("Auto-refining search query with AI to expand results...", evaluations_count)
                new_refined = generate_refined_search_query(vacancy_text, refined_query, config)
                if new_refined and new_refined != refined_query:
                    print(f"\n--> Auto-refined search query: {new_refined}")
                    refined_query = new_refined
                    current_offset = 0
                    continue
                else:
                    print("[Warning] Could not auto-refine query further. Ending search run.")
                    break
            else:
                break
        else:
            current_offset += len(candidate_urls)
            
        # Verify that the LinkedIn session is active (assisting visibly if expired)
        if any(url not in processed_history for url in candidate_urls):
            report_progress("Verifying LinkedIn session...", evaluations_count)
            ensure_linkedin_session(config, interactive=interactive)
            
        # Scrape and evaluate candidates
        for url in candidate_urls:
            wait_if_paused()
            if cancel_check and cancel_check():
                print("[Cancelled] Sourcing aborted by user.")
                report_progress("Sourcing cancelled by user.", evaluations_count, is_done=True)
                return {"success": False, "cancelled": True, "evaluated": evaluations_count}

            # Check if query changed mid-batch
            refined_query, query_changed = check_query_update(refined_query)
            if query_changed:
                current_offset = 0
                break

            if url in processed_history or is_url_processed_in_db(url):
                print(f"[Skipped] Candidate already processed: {url}")
                continue
                
            report_progress(f"Scraping LinkedIn profile ({evaluations_count}/{min_target})...", evaluations_count)
            # Scrape profile (includes Phase 1 country check)
            profile = scrape_linkedin_profile(url, target_country, config)
            
            # Register in in-memory sets
            processed_history.add(url)
            current_run_urls.add(url)
            
            # If discarded in Phase 1 due to location mismatch
            if profile["status"] == "location_mismatch":
                cand_loc = profile.get("location") or "Not specified"
                candidate_record = {
                    "vacancy_id": vac_id,
                    "vacancy": vac_title,
                    "name": profile["name"] or "Unknown",
                    "headline": profile["headline"] or "No headline",
                    "technical_score": 0,
                    "experience_score": 0,
                    "auxiliary_score": 0,
                    "score": 0,
                    "open_to_work": False,
                    "status": "location_mismatch",
                    "evaluation_summary": f"Automatically discarded: location mismatch. (Candidate location: '{cand_loc}', Job requires: '{target_country}').",
                    "linkedin_url": url,
                    "location": cand_loc,
                    "about": profile.get("about") or "",
                    "experience": profile.get("experience") or "",
                    "skills": profile.get("skills") or "",
                    "timestamp": pd.Timestamp.now().isoformat()
                }
                update_json_report(candidate_record)
                if on_candidate_discarded:
                    try:
                        on_candidate_discarded({
                            "name": profile["name"] or "LinkedIn Member",
                            "headline": profile["headline"] or "Profile evaluated",
                            "location": cand_loc,
                            "linkedin_url": url,
                            "type": "location_mismatch",
                            "reason": f"Location mismatch: Candidate based in '{cand_loc}', required '{target_country}'."
                        })
                    except Exception as e:
                        print(f"[Warning] Error in on_candidate_discarded callback: {e}")
                continue
                
            # If scraping error occurred
            if profile["status"] != "success":
                print(f"[Scraper Error] Could not process {url}: {profile['error_message']}")
                candidate_record = {
                    "vacancy_id": vac_id,
                    "vacancy": vac_title,
                    "name": profile["name"] or "Unknown",
                    "headline": profile["headline"] or "No headline",
                    "technical_score": 0,
                    "experience_score": 0,
                    "auxiliary_score": 0,
                    "score": 0,
                    "open_to_work": False,
                    "status": "discarded",
                    "evaluation_summary": f"Scraping error: {profile['error_message']}",
                    "linkedin_url": url,
                    "location": profile.get("location") or "Not specified",
                    "about": profile.get("about") or "",
                    "experience": profile.get("experience") or "",
                    "skills": profile.get("skills") or "",
                    "timestamp": pd.Timestamp.now().isoformat()
                }
                update_json_report(candidate_record)
                if on_candidate_discarded:
                    try:
                        on_candidate_discarded({
                            "name": profile["name"] or "LinkedIn Member",
                            "headline": profile["headline"] or "Profile evaluated",
                            "location": profile.get("location") or "Not specified",
                            "linkedin_url": url,
                            "type": "error",
                            "reason": f"Scraping issue: {profile.get('error_message') or 'Inaccessible profile'}"
                        })
                    except Exception as e:
                        print(f"[Warning] Error in on_candidate_discarded callback: {e}")
                continue
                
            # Perform full profile evaluation with Ollama
            c_name = profile['name'] or 'Candidate'
            report_progress(f"Evaluating profile of '{c_name}' with AI...", evaluations_count)
            print(f"Evaluating candidate profile '{c_name}' against job description...")
            evaluation = evaluate_candidate(profile, vacancy_text, config)
            score = evaluation["match_score"]
            open_to_work = evaluation["open_to_work"]
            eval_summary = evaluation["evaluation_summary"]
            
            print(f"--> Match Score: {score}% | OpenToWork: {open_to_work}")
            
            # Save candidate details
            default_status = "new" if int(score) >= 60 else "discarded"
            candidate_record = {
                "vacancy_id": vac_id,
                "vacancy": vac_title,
                "name": profile["name"] or "Unknown",
                "headline": profile["headline"] or "No headline",
                "technical_score": int(evaluation.get("technical_score", 0)),
                "experience_score": int(evaluation.get("experience_score", 0)),
                "auxiliary_score": int(evaluation.get("auxiliary_score", 0)),
                "score": int(score),
                "open_to_work": bool(open_to_work),
                "status": default_status,
                "evaluation_summary": eval_summary,
                "linkedin_url": url,
                "location": profile.get("location") or "Not specified",
                "about": profile.get("about") or "",
                "experience": profile.get("experience") or "",
                "skills": profile.get("skills") or "",
                "timestamp": pd.Timestamp.now().isoformat()
            }
            update_json_report(candidate_record)
            
            if profile["status"] == "success":
                evaluations_count += 1
                if on_candidate_evaluated:
                    try:
                        on_candidate_evaluated(candidate_record)
                    except Exception as e:
                        print(f"[Warning] Error in on_candidate_evaluated callback: {e}")
                report_progress(f"Evaluated: {c_name} (Score: {score}%) [{evaluations_count}/{min_target}]", evaluations_count)
                
            # Check target reached mid-page
            if evaluations_count >= min_target:
                print(f"[Info] Target reached: Evaluated {evaluations_count}/{min_target} candidates.")
                break
                
        # If the target has not been reached yet, continue the search loop
        if evaluations_count < min_target:
            print(f"\n[Info] Evaluated {evaluations_count}/{min_target} candidates. Fetching next page of search results...")
            continue
            
        # Non-interactive mode (for Web Dashboard background task)
        if not interactive:
            report_progress(f"Sourcing completed successfully. Evaluated {evaluations_count} candidates.", evaluations_count, is_done=True)
            return {
                "success": True,
                "evaluated": evaluations_count,
                "target": min_target,
                "candidates_processed": len(current_run_urls)
            }

        # Show interactive summary of candidates processed for this vacancy in CLI
        print(f"\n" + "=" * 60)
        print(f"   CANDIDATE SUMMARY FOR VACANCY: {vac_title}")
        print(f"=" * 60)
        
        try:
            from database import get_candidates
            vacancy_candidates = get_candidates(vacancy_id=vac_id, vacancy=vac_title)
        except Exception:
            vacancy_candidates = []
                
        if vacancy_candidates:
            # Sort by score descending
            vacancy_candidates.sort(key=lambda x: x.get("score", 0), reverse=True)
            print(f"{'Candidate Name':<35} | Match Score")
            print("-" * 60)
            for c in vacancy_candidates:
                name = c.get("name", "Unknown")
                score = f"{c.get('score', 0)}%"
                is_new = " [NEW]" if c.get("linkedin_url") in current_run_urls else ""
                print(f"- {name + is_new:<33} | {score}")
        else:
            print("No candidates processed for this vacancy yet.")
        print("=" * 60)
        
        satisfy_input = input(f"\nAre you satisfied with the results obtained for vacancy '{vac_title}'? (Y/N) [Y]: ").strip().lower()
        if satisfy_input in ("", "y", "yes"):
            satisfied = True
            if vac_id:
                update_vacancy(vac_id, status="archived")
                print(f"[Database] Vacancy '{vac_title}' status updated to 'archived'.")
            else:
                print(f"[Info] Vacancy processing marked completed.")
        else:
            print("\n" + "=" * 65)
            print("       💬 RECRUITER AI SOURCING COPILOT (CHAT REFINEMENT)")
            print("=" * 65)
            print(f"Current query:\n{refined_query}\n")
            print("Chat with the Copilot to tune seniority, skills, location, or boolean terms.")
            print("Type your instruction (e.g. 'Focus on Senior profiles with strong AWS and Terraform experience')")
            print("or press [Enter] to run the search with the current query, or 'q' to stop.\n")
            
            chat_history = []
            while True:
                user_prompt = input("Recruiter > ").strip()
                if not user_prompt:
                    # User accepted current query and wants to run search
                    evaluations_count = 0
                    current_offset = 0
                    break
                if user_prompt.lower() in ("q", "quit", "exit"):
                    print(f"[Info] Leaving vacancy '{vac_title}' active in database.")
                    satisfied = True
                    break
                
                chat_history.append({"role": "user", "content": user_prompt})
                print("\n[AI Copilot is analyzing and refining query...]")
                copilot_res = chat_refine_search_query(
                    history=chat_history,
                    vacancy_text=vacancy_text,
                    current_query=refined_query,
                    target_country=target_country,
                    config=config
                )
                reply = copilot_res.get("reply", "")
                new_q = copilot_res.get("search_query", "")
                chat_history.append({"role": "assistant", "content": reply})
                
                print(f"\n🤖 AI Copilot: {reply}")
                if new_q and new_q != refined_query:
                    refined_query = new_q
                    print(f"\n🔍 Updated query:\n{refined_query}\n")
                for tip in copilot_res.get("tips", []):
                    print(f"💡 Tip: {tip}")
                print("\nType another instruction to keep refining, or press [Enter] to launch the search:")

def main():
    setup_directories()
    
    # Check if started with --dashboard or --web flag
    if len(sys.argv) > 1 and sys.argv[1].lower() in ("--dashboard", "--web", "-w", "-d"):
        from dashboard import start_dashboard
        start_dashboard(open_browser=True)
        return

    # Initialize Tee to log terminal outputs to file
    tee = Tee("output/referral_bot.log", mode="w")
    sys.stdout = tee
    sys.stderr = tee
    
    config = load_config()
    
    while True:
        print("\n" + "=" * 60)
        print("                 REFERLOOKER - MAIN MENU")
        print("=" * 60)
        print("1. Process active vacancies (SQLite Database)")
        print("2. Resume search for archived vacancies (SQLite Database)")
        print("3. Browse and filter candidates (interactive CLI)")
        print("4. Launch Web Dashboard & Kanban ATS (http://localhost:5000)")
        print("q. Quit")
        print("=" * 60)
        
        opc = input("Select an option: ").strip()
        
        if opc == "1":
            active_vacancies = get_vacancies(status="active")
            if not active_vacancies:
                print("\nNo active vacancies found in the SQLite database.")
                print("You can create new vacancies from the Web Dashboard (http://localhost:5000).")
                continue
                
            print("\nSelect the vacancy you wish to process:")
            print("1. [Process all active vacancies]")
            for idx, v in enumerate(active_vacancies, 2):
                star_tag = "⭐ " if v.get("is_starred") else ""
                country_info = f" (Target: {v.get('target_country')})" if v.get('target_country') and v.get('target_country') != 'Any' else ""
                print(f"{idx}. {star_tag}{v['title']}{country_info} [ID #{v['id']}]")
            print("q. [Back to main menu]")
            
            sel = input("\nOption: ").strip()
            if sel.lower() == 'q':
                continue
            elif sel == "1":
                selected_vacancies = active_vacancies
            elif sel.isdigit():
                sel_idx = int(sel)
                if 2 <= sel_idx <= len(active_vacancies) + 1:
                    selected_vacancies = [active_vacancies[sel_idx - 2]]
                else:
                    print("Invalid option.")
                    continue
            else:
                print("Invalid option.")
                continue
                
            try:
                target_input = input("\nEnter minimum candidates to evaluate for each vacancy in this run [5]: ").strip()
                min_target = int(target_input) if target_input else 5
            except ValueError:
                print("[Info] Invalid input. Defaulting to 5.")
                min_target = 5
                
            print(f"\nStarting processing of {len(selected_vacancies)} active vacancy(ies)...")
            for vac in selected_vacancies:
                processed_history = get_processed_urls_from_db()
                process_vacancy(vac, config, processed_history, min_target)
                
        elif opc == "2":
            archived_vacancies = get_vacancies(status="archived")
            if not archived_vacancies:
                print("\nNo archived vacancies found in SQLite database.")
                continue
                
            print("\nSelect the archived vacancy you wish to resume:")
            for idx, v in enumerate(archived_vacancies, 1):
                star_tag = "⭐ " if v.get("is_starred") else ""
                print(f"{idx}. {star_tag}{v['title']} [ID #{v['id']}]")
            print("q. [Back to main menu]")
            
            sel = input("\nOption: ").strip()
            if sel.lower() == 'q':
                continue
            elif sel.isdigit():
                sel_idx = int(sel)
                if 1 <= sel_idx <= len(archived_vacancies):
                    vac = archived_vacancies[sel_idx - 1]
                    
                    try:
                        target_input = input("\nEnter minimum candidates to evaluate in this run [5]: ").strip()
                        min_target = int(target_input) if target_input else 5
                    except ValueError:
                        print("[Info] Invalid input. Defaulting to 5.")
                        min_target = 5
                        
                    processed_history = get_processed_urls_from_db()
                    process_vacancy(vac, config, processed_history, min_target)
                else:
                    print("Invalid option.")
            else:
                print("Invalid option.")
                
        elif opc == "3":
            # Start interactive CLI browser
            run_cli()

        elif opc == "4":
            # Launch Web Dashboard
            from dashboard import start_dashboard
            start_dashboard(open_browser=True)
            
        elif opc.lower() == "q":
            print("\nExiting ReferLooker. See you soon!")
            break
        else:
            print("\nInvalid option. Please try again.")
            
    print("\nProcessing completed.")

if __name__ == "__main__":
    main()

