import os
import json
import csv
import time

# ANSI color codes for styled console output
RESET = "\033[0m"
BOLD = "\033[1m"
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
MAGENTA = "\033[35m"
WHITE = "\033[37m"

def clear_screen():
    """Clears the console based on the operating system."""
    os.system('cls' if os.name == 'nt' else 'clear')

def print_header(title):
    """Prints a styled header to the console."""
    width = 70
    print("\n" + "=" * width)
    print(f"{BOLD}{CYAN}{title.center(width)}{RESET}")
    print("=" * width)

def load_candidates(json_path="output/candidates.json"):
    """Loads candidates from candidates.json and groups them by vacancy."""
    if not os.path.exists(json_path):
        return {}

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"{RED}[Error] Could not read {json_path}: {e}{RESET}")
        return {}

    desirable_candidates = data.get("desirable_candidates", [])
    undesirable_candidates = data.get("undesirable_candidates", [])

    # Group by vacancy
    vacancies = {}
    
    def add_to_group(cand_list, group_name):
        for cand in cand_list:
            vac_name = cand.get("vacancy", "Unassigned Vacancy")
            if vac_name not in vacancies:
                vacancies[vac_name] = {"desirable": [], "undesirable": []}
            # Ensure score is an integer
            try:
                cand["score"] = int(cand.get("score", 0))
            except Exception:
                cand["score"] = 0
            vacancies[vac_name][group_name].append(cand)

    add_to_group(desirable_candidates, "desirable")
    add_to_group(undesirable_candidates, "undesirable")

    return vacancies

def print_candidates_table(candidates):
    """Draws an ASCII table of the candidates and returns a mapped list of candidates."""
    if not candidates:
        print(f"{YELLOW}No candidates found matching the active filters.{RESET}")
        return []

    # Table headers
    col_idx = " # "
    col_name = "Name"
    col_score = "Score"
    col_otw = "OpenToWork"
    col_loc = "Location"

    print(f"+-----+---------------------------+-------+------------+---------------------------------+")
    print(f"|{BOLD}{WHITE}{col_idx:^3}{RESET}|{BOLD}{WHITE}{col_name:^27}{RESET}|{BOLD}{WHITE}{col_score:^7}{RESET}|{BOLD}{WHITE}{col_otw:^12}{RESET}|{BOLD}{WHITE}{col_loc:^33}{RESET}|")
    print(f"+-----+---------------------------+-------+------------+---------------------------------+")

    mapped = []
    for i, c in enumerate(candidates, 1):
        mapped.append(c)
        name = c.get("name", "Unknown")[:25]
        score = c.get("score", 0)
        open_to_work = "Yes" if c.get("open_to_work") else "No"
        location = c.get("location", "Not specified")[:31]

        # Score and availability status colors
        score_color = GREEN if score >= 85 else (YELLOW if score >= 60 else RED)
        otw_color = GREEN if c.get("open_to_work") else RESET
        
        # Format cells with fixed widths
        name_str = f"{name:<25}"
        score_str = f"{score:>4}%"
        otw_str = f"{open_to_work:^10}"
        loc_str = f"{location:<31}"

        print(f"| {i:^3} | {name_str} | {score_color}{score_str}{RESET} | {otw_color}{otw_str}{RESET} | {loc_str} |")

    print(f"+-----+---------------------------+-------+------------+---------------------------------+")
    return mapped

def view_candidate_detail(candidate):
    """Displays detailed information for a selected candidate."""
    clear_screen()
    print_header(f"Detailed File: {candidate.get('name')}")
    
    score = candidate.get("score", 0)
    score_color = GREEN if score >= 85 else (YELLOW if score >= 60 else RED)
    open_to_work = f"{GREEN}Yes (Active Search){RESET}" if candidate.get("open_to_work") else "No / Not detected"

    print(f"{BOLD}Associated Vacancy:{RESET} {candidate.get('vacancy')}")
    print(f"{BOLD}LinkedIn URL:{RESET}       {candidate.get('linkedin_url')}")
    print(f"{BOLD}Location:{RESET}           {candidate.get('location')}")
    print(f"{BOLD}Match Score:{RESET}        {score_color}{score}%{RESET}")
    print(f"{BOLD}Open to Work:{RESET}       {open_to_work}")
    print(f"{BOLD}Headline:{RESET}           {candidate.get('headline')}")
    print(f"{BOLD}Registration Date:{RESET}  {candidate.get('timestamp', 'N/A')}")
    print("-" * 70)
    
    print(f"{BOLD}{CYAN}[Ollama Evaluation Summary]{RESET}")
    print(candidate.get("evaluation_summary", "No evaluation summary available."))
    print("-" * 70)

    # Display profile sections
    print(f"{BOLD}{CYAN}[About / Summary]{RESET}")
    about = candidate.get("about", "").strip()
    print(about if about else "Section empty or not available.")
    print("-" * 70)

    print(f"{BOLD}{CYAN}[Professional Experience (Summary)]{RESET}")
    exp = candidate.get("experience", "").strip()
    if exp:
        # Display the first 15 lines to avoid flooding the console
        lines = exp.split('\n')
        if len(lines) > 15:
            print('\n'.join(lines[:15]))
            print(f"{YELLOW}... [Profile contains {len(lines)} lines of experience. Visit full LinkedIn profile for more details] ...{RESET}")
        else:
            print(exp)
    else:
        print("Section empty or not available.")
    print("-" * 70)

    print(f"{BOLD}{CYAN}[Skills]{RESET}")
    skills_text = candidate.get("skills", "").strip()
    if skills_text:
        lines = skills_text.split('\n')
        skills = [l.strip() for l in lines if l.strip() and not l.strip().startswith("Skills") and not l.strip().startswith("All") and not l.strip().startswith("Tools") and not l.strip().startswith("Industry")]
        if skills:
            print(", ".join(skills[:30]))
            if len(skills) > 30:
                print(f"{YELLOW}... and {len(skills) - 30} more skills.{RESET}")
        else:
            print(skills_text[:300])
    else:
        print("Section empty or not available.")
    
    print("=" * 70)
    input(f"\nPress {BOLD}[Enter]{RESET} to return to the candidate list...")

def export_vacancy_to_csv(vac_name, candidates):
    """Exports the filtered candidates of a specific vacancy to a CSV file."""
    # Sanitize the file name
    safe_name = "".join(c for c in vac_name if c.isalnum() or c in (' ', '_', '-')).rstrip()
    safe_name = safe_name.replace(" ", "_")
    filename = f"output/{safe_name}_export.csv"

    fieldnames = ["Name", "Score", "Open to Work", "LinkedIn URL", "Location", "Headline", "Evaluation Summary"]
    
    try:
        with open(filename, "w", newline="", encoding="utf-8") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for c in candidates:
                writer.writerow({
                    "Name": c.get("name", ""),
                    "Score": f"{c.get('score', 0)}%",
                    "Open to Work": "Yes" if c.get("open_to_work") else "No",
                    "LinkedIn URL": c.get("linkedin_url", ""),
                    "Location": c.get("location", ""),
                    "Headline": c.get("headline", ""),
                    "Evaluation Summary": c.get("evaluation_summary", "")
                })
        print(f"\n{GREEN}[Success] Report exported to: {os.path.abspath(filename)}{RESET}")
        input(f"Press {BOLD}[Enter]{RESET} to continue...")
    except Exception as e:
        print(f"\n{RED}[Error] Could not export to CSV: {e}{RESET}")
        input(f"Press {BOLD}[Enter]{RESET} to continue...")

def filter_candidates_menu(all_candidates):
    """Secondary menu to apply filters to a list of candidates."""
    filtered = all_candidates.copy()
    
    while True:
        clear_screen()
        print_header(f"Candidate Filters (Active Results: {len(filtered)})")
        
        print("1. Filter by Minimum Score")
        print("2. Filter by 'Open to Work' status")
        print("3. Filter by Location / Country (Text search)")
        print("4. Search Keyword in Profile (Name, Headline, Skills)")
        print("5. Reset all filters")
        print("6. View result candidates")
        print("q. Exit to vacancy menu")
        
        opc = input(f"\nSelect an option: ").strip()
        
        if opc == "1":
            try:
                min_score = int(input("Enter minimum score (0-100): ").strip())
                filtered = [c for c in filtered if c.get("score", 0) >= min_score]
            except ValueError:
                print(f"{RED}Invalid value.{RESET}")
                input("Press Enter...")
        elif opc == "2":
            otw_input = input("Show only Open to Work candidates? (Y/N): ").strip().lower()
            if otw_input in ("y", "yes"):
                filtered = [c for c in filtered if c.get("open_to_work")]
            elif otw_input in ("n", "no"):
                filtered = [c for c in filtered if not c.get("open_to_work")]
        elif opc == "3":
            loc_query = input("Enter country, state, or city keyword: ").strip().lower()
            if loc_query:
                filtered = [c for c in filtered if loc_query in c.get("location", "").lower()]
        elif opc == "4":
            keyword = input("Enter search term: ").strip().lower()
            if keyword:
                filtered = [c for c in filtered if (
                    keyword in c.get("name", "").lower() or
                    keyword in c.get("headline", "").lower() or
                    keyword in c.get("skills", "").lower() or
                    keyword in c.get("experience", "").lower() or
                    keyword in c.get("about", "").lower()
                )]
        elif opc == "5":
            filtered = all_candidates.copy()
            print(f"{GREEN}Filters reset.{RESET}")
            input("Press Enter...")
        elif opc == "6":
            # Display the resulting table directly
            clear_screen()
            print_header(f"Filtered Candidates ({len(filtered)})")
            mapped = print_candidates_table(filtered)
            if mapped:
                idx = input(f"\nEnter candidate number to view details or {BOLD}[Enter]{RESET} to return: ").strip()
                if idx.isdigit() and 1 <= int(idx) <= len(mapped):
                    view_candidate_detail(mapped[int(idx) - 1])
            else:
                input("\nPress Enter to return...")
        elif opc.lower() == "q":
            break
            
    return filtered

def manage_vacancy_candidates(vac_name, data):
    """Menu to manage/visualize the candidates of a specific vacancy."""
    desirable = data.get("desirable", [])
    undesirable = data.get("undesirable", [])
    all_cands = desirable + undesirable
    
    # Sort by score descending by default
    all_cands.sort(key=lambda x: x.get("score", 0), reverse=True)
    
    current_list = all_cands.copy()

    while True:
        clear_screen()
        print_header(f"Vacancy: {vac_name}")
        print(f"Candidates summary:")
        print(f"- Desirable (Score >= 85): {GREEN}{len(desirable)}{RESET}")
        print(f"- Undesirable (Score < 85): {RED}{len(undesirable)}{RESET}")
        print(f"- Currently viewing: {BOLD}{len(current_list)}{RESET} candidates\n")

        print("1. View All candidates")
        print("2. View only Desirable candidates")
        print("3. View only Undesirable candidates")
        print("4. Apply Advanced Filters and Search")
        print("5. Export this list to CSV")
        print("q. Go back to previous menu")
        
        opc = input(f"\nSelect an option: ").strip()

        if opc == "1":
            current_list = all_cands.copy()
            clear_screen()
            print_header(f"All Candidates ({len(current_list)})")
            mapped = print_candidates_table(current_list)
            if mapped:
                idx = input(f"\nEnter candidate number to view details or {BOLD}[Enter]{RESET} to return: ").strip()
                if idx.isdigit() and 1 <= int(idx) <= len(mapped):
                    view_candidate_detail(mapped[int(idx) - 1])
        elif opc == "2":
            current_list = desirable.copy()
            clear_screen()
            print_header(f"Desirable Candidates ({len(current_list)})")
            mapped = print_candidates_table(current_list)
            if mapped:
                idx = input(f"\nEnter candidate number to view details or {BOLD}[Enter]{RESET} to return: ").strip()
                if idx.isdigit() and 1 <= int(idx) <= len(mapped):
                    view_candidate_detail(mapped[int(idx) - 1])
        elif opc == "3":
            current_list = undesirable.copy()
            clear_screen()
            print_header(f"Undesirable Candidates ({len(current_list)})")
            mapped = print_candidates_table(current_list)
            if mapped:
                idx = input(f"\nEnter candidate number to view details or {BOLD}[Enter]{RESET} to return: ").strip()
                if idx.isdigit() and 1 <= int(idx) <= len(mapped):
                    view_candidate_detail(mapped[int(idx) - 1])
        elif opc == "4":
            current_list = filter_candidates_menu(all_cands)
        elif opc == "5":
            export_vacancy_to_csv(vac_name, current_list)
        elif opc.lower() == "q":
            break

def run_cli():
    """Starts the main loop of the candidate browser CLI."""
    while True:
        clear_screen()
        print_header("ReferLooker - Candidate Browser and Filter")
        
        vacancies = load_candidates()
        
        if not vacancies:
            print(f"\n{YELLOW}No candidate records found in 'output/candidates.json'.{RESET}")
            print("Make sure to process vacancies first to populate the database.")
            input(f"\nPress {BOLD}[Enter]{RESET} to return...")
            break

        print("Select a vacancy to explore its candidates:\n")
        
        mapped_vacs = []
        for i, (vac_name, data) in enumerate(vacancies.items(), 1):
            mapped_vacs.append((vac_name, data))
            num_des = len(data["desirable"])
            num_ndes = len(data["undesirable"])
            print(f"{BOLD}{i:>2}.{RESET} {vac_name:<60} [{GREEN}{num_des} Desirable{RESET} | {RED}{num_ndes} Undesirable{RESET}]")

        print(f"\n{BOLD} q.{RESET} Back to main menu")

        selection = input(f"\nSelect an option: ").strip()

        if selection.lower() == 'q':
            break

        if selection.isdigit():
            idx = int(selection)
            if 1 <= idx <= len(mapped_vacs):
                vac_name, data = mapped_vacs[idx - 1]
                manage_vacancy_candidates(vac_name, data)
            else:
                print(f"{RED}Invalid option. Retry.{RESET}")
                time.sleep(1)
        else:
            print(f"{RED}Invalid option. Retry.{RESET}")
            time.sleep(1)

if __name__ == "__main__":
    run_cli()
