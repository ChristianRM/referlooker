import os
import json
import time
from playwright.sync_api import sync_playwright

def get_section_text(page, section_id: str) -> str:
    """
    Looks up a section of the LinkedIn page based on semantic anchor ID.
    If it fails, attempts common heading text selectors (English & Spanish)
    to maintain compatibility across different profile layout languages.
    """
    # 1. Try by ID suffix case-insensitively (specific card container selector on modern LinkedIn)
    try:
        locator = page.locator(f"[id$='{section_id}' i]")
        if locator.count() > 0:
            return locator.first.inner_text().strip()
    except Exception:
        pass

    # 2. Try by ID as a direct child of a section (classic layout card selector)
    xpath = f"//section[./div[@id='{section_id}'] or ./span[@id='{section_id}'] or ./a[@id='{section_id}'] or ./*[@id='{section_id}']]"
    try:
        locator = page.locator(xpath)
        if locator.count() > 0:
            return locator.first.inner_text().strip()
    except Exception:
        pass
        
    # 3. Try by ID anywhere, but select the innermost section to avoid parent wrapper bloat
    xpath_inner = f"//section[.//div[@id='{section_id}'] or .//span[@id='{section_id}'] or .//a[@id='{section_id}']][not(.//section[.//div[@id='{section_id}'] or .//span[@id='{section_id}'] or .//a[@id='{section_id}']])]"
    try:
        locator = page.locator(xpath_inner)
        if locator.count() > 0:
            return locator.first.inner_text().strip()
    except Exception:
        pass

    # 3. Fallback by heading text (h2) - selecting the innermost section
    headings = []
    if section_id == "about":
        headings = ["About", "Acerca de", "Extracto"]
    elif section_id == "experience":
        headings = ["Experience", "Experiencia"]
    elif section_id == "skills":
        headings = ["Skills", "Habilidades", "Aptitudes"]
        
    for heading in headings:
        xpath_h = f"//section[.//h2[contains(., '{heading}')] or .//h3[contains(., '{heading}')]][not(.//section[.//h2[contains(., '{heading}')] or .//h3[contains(., '{heading}')])]"
        try:
            locator = page.locator(xpath_h)
            if locator.count() > 0:
                return locator.first.inner_text().strip()
        except Exception:
            pass
            
    return ""

def expand_collapsed_sections(page):
    """
    Locates and clicks all "see more", "ver más", or "show more" buttons
    to expand collapsed descriptions and sections in the profile.
    """
    try:
        # Common selectors for "see more" buttons
        selectors = [
            "button:has-text('see more')",
            "button:has-text('ver más')",
            "button:has-text('ver mas')",
            "button:has-text('show more')",
            "button.inline-show-more-text",
            "span:has-text('...see more')",
            "span:has-text('...ver más')"
        ]
        
        for selector in selectors:
            try:
                buttons = page.locator(selector)
                count = buttons.count()
                for i in range(count):
                    btn = buttons.nth(i)
                    if btn.is_visible():
                        btn.click(timeout=1000, force=True)
                        page.wait_for_timeout(300)
            except Exception:
                pass
    except Exception:
        pass

def scrape_linkedin_profile(profile_url: str, target_country: str, config: dict) -> dict:
    """
    Scrapes a LinkedIn profile using a persistent Chrome user context.
    Executes in a two-phase workflow:
    Phase 1: Extracts location and asks Ollama if it is compatible with the required country.
    Phase 2: If compatible, performs a full scraping of sections and raw profile text.
    """
    profile_data = {
        "url": profile_url,
        "name": "",
        "headline": "",
        "location": "",
        "about": "",
        "experience": "",
        "skills": "",
        "raw_text": "",
        "status": "error",
        "error_message": ""
    }
    
    user_data_dir = os.path.abspath("linkedin_profile_context")
    
    with sync_playwright() as p:
        try:
            # Launch Chromium with persistent context in headful or headless mode
            context = p.chromium.launch_persistent_context(
                user_data_dir,
                headless=config.get("scraping", {}).get("headless", True),
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 720}
            )
            page = context.pages[0] if context.pages else context.new_page()
            
            # Navigate to profile URL with a 30s timeout
            page.goto(profile_url, wait_until="domcontentloaded", timeout=30000)
            
            # Wait for h1 (profile name) to render in DOM
            try:
                page.wait_for_selector("h1", timeout=10000)
            except Exception:
                pass
                
            # Allow 2 seconds for header elements to populate
            page.wait_for_timeout(2000)
            
            current_url = page.url
            # Check if LinkedIn redirected us to a login page or verification checkpoint
            if "linkedin.com/login" in current_url or "checkpoint" in current_url or "authwall" in current_url:
                error_msg = "Session closed or expired in persistent profile."
                print(f"[Error] {error_msg}")
                profile_data["error_message"] = error_msg
                profile_data["status"] = "session_expired"
                context.close()
                return profile_data
                
            # --- PHASE 1: HEADER EXTRACTION & QUICK COUNTRY FILTERING ---
            # Extract Name (usually first h1 element)
            try:
                name_locator = page.locator("h1").first
                if name_locator.count() > 0:
                    profile_data["name"] = name_locator.inner_text().strip()
            except Exception:
                pass
                
            # Fallback: Extract name from page title if h1 extraction failed
            if not profile_data["name"] or profile_data["name"].lower() in ("", "join linkedin", "iniciar sesión", "sign in", "welcome to linkedin"):
                title = page.title()
                if " | LinkedIn" in title:
                    raw_name = title.split(" | LinkedIn")[0]
                    if " - " in raw_name:
                        raw_name = raw_name.split(" - ")[0]
                    profile_data["name"] = raw_name.strip()
                    
            # Extract Headline
            try:
                headline_locator = page.locator(".text-body-medium").first
                if headline_locator.count() > 0:
                    profile_data["headline"] = headline_locator.inner_text().strip()
            except Exception:
                pass
                
            # Extract header text (first 2500 characters, sufficient to get location and names)
            header_text = ""
            try:
                body_locator = page.locator("body")
                if body_locator.count() > 0:
                    header_text = body_locator.inner_text()[:2500].strip()
            except Exception:
                pass

            # Use Ollama to check geographic compatibility
            from evaluator import evaluate_location_with_llm
            res = evaluate_location_with_llm(header_text, target_country, config)
            profile_data["location"] = res.get("extracted_location", "Not detected")
            is_compatible = res.get("compatible", False)
            
            if not is_compatible:
                print(f"[Geographic Deselect] Candidate '{profile_data['name']}' skipped by Ollama due to location mismatch (Detected: '{profile_data['location']}', Required: '{target_country}').")
                profile_data["status"] = "location_mismatch"
                profile_data["error_message"] = f"Location incompatible with Ollama: {profile_data['location']}"
                context.close()
                return profile_data
                
            # --- PHASE 2: FULL PROFILE SCRAPING ---
            # Progressively scroll down to trigger lazy loading of profile sections
            print("Loading full profile sections (scrolling)...")
            try:
                for i in range(1, 5):
                    page.evaluate(f"window.scrollTo(0, {i * 800})")
                    page.wait_for_timeout(1200)
            except Exception as e:
                print(f"[Debug] Scroll error: {e}")
            
            # Click all "see more" buttons to expand descriptions
            expand_collapsed_sections(page)
            
            # Extract sections by their ID anchor tags
            profile_data["about"] = get_section_text(page, "about")
            profile_data["experience"] = get_section_text(page, "experience")
            profile_data["skills"] = get_section_text(page, "skills")
            
            # Reconstruct profile base URL without trailing query arguments
            base_profile_url = profile_url
            if "/in/" in profile_url:
                try:
                    parts = profile_url.split("/in/")
                    username = parts[1].split("/")[0].split("?")[0]
                    base_profile_url = f"https://www.linkedin.com/in/{username}"
                except Exception:
                    pass
            
            # Self-Healing: If experience section is empty, navigate directly to details page
            if not profile_data["experience"] or len(profile_data["experience"].strip()) < 15:
                print(f"[Self-Healing] Empty experience on main page. Navigating to experience details subpage...")
                try:
                    exp_url = base_profile_url.rstrip("/") + "/details/experience/"
                    page.goto(exp_url, wait_until="domcontentloaded", timeout=20000)
                    page.wait_for_timeout(2000)
                    # PageDown key scroll loop to load content
                    for _ in range(3):
                        page.keyboard.press("PageDown")
                        page.wait_for_timeout(600)
                    # Retrieve text from main container or body
                    main_text = page.locator("main").inner_text() or page.locator("body").inner_text()
                    if len(main_text.strip()) > 100:
                        profile_data["experience"] = main_text.strip()
                        print("[Self-Healing] Experience successfully recovered from details subpage.")
                except Exception as e:
                    print(f"[Self-Healing] Error trying to recover experience: {e}")
                    
            # Self-Healing: If skills section is empty, navigate directly to skills details page
            if not profile_data["skills"] or len(profile_data["skills"].strip()) < 15:
                print(f"[Self-Healing] Empty skills on main page. Navigating to skills details subpage...")
                try:
                    skills_url = base_profile_url.rstrip("/") + "/details/skills/"
                    page.goto(skills_url, wait_until="domcontentloaded", timeout=20000)
                    page.wait_for_timeout(2000)
                    for _ in range(3):
                        page.keyboard.press("PageDown")
                        page.wait_for_timeout(600)
                    main_text = page.locator("main").inner_text() or page.locator("body").inner_text()
                    if len(main_text.strip()) > 100:
                        profile_data["skills"] = main_text.strip()
                        print("[Self-Healing] Skills successfully recovered from details subpage.")
                except Exception as e:
                    print(f"[Self-Healing] Error trying to recover skills: {e}")
            
            # Navigate back to primary profile page if we ended up on details pages
            try:
                if page.url != profile_url:
                    page.goto(profile_url, wait_until="domcontentloaded", timeout=20000)
                profile_data["raw_text"] = page.locator("body").inner_text()
            except Exception:
                pass
                
            # Verify if we extracted valid candidate details or fell into a signup/login wall
            name_lower = profile_data["name"].lower()
            is_login_wall = (
                name_lower in ("", "join linkedin", "iniciar sesión", "sign in", "welcome to linkedin") or
                "join linkedin" in name_lower or
                "iniciar sesión" in name_lower
            )
            
            # Successful parse if candidate has a valid name and raw text is present
            if profile_data["name"] and not is_login_wall and len(profile_data["raw_text"]) > 200:
                profile_data["status"] = "success"
                print(f"Profile of '{profile_data['name']}' successfully scraped.")
            else:
                body_text = profile_data["raw_text"].lower()
                if (is_login_wall or "join linkedin" in body_text or "iniciar sesión" in body_text) and len(body_text) < 1500:
                    profile_data["status"] = "session_expired"
                    profile_data["error_message"] = "LinkedIn requested login. Persistent browser session has expired or is invalid."
                else:
                    profile_data["status"] = "empty"
                    profile_data["error_message"] = "No data found in public/private profile."
                    
            context.close()
            
        except Exception as e:
            error_msg = f"Exception during scraping: {e}"
            print(f"[Error] {error_msg}")
            profile_data["error_message"] = error_msg
            profile_data["status"] = "error"
            
    return profile_data

def ensure_linkedin_session(config: dict):
    """
    Verifies automatically whether a valid LinkedIn session exists in the persistent profile.
    If it does not exist or has expired, opens a headful Chrome window for manual log in
    and saves the credentials context directly.
    """
    user_data_dir = os.path.abspath("linkedin_profile_context")
    session_valid = False
    
    if os.path.exists(user_data_dir):
        print("Checking if LinkedIn session is still active...")
        with sync_playwright() as p:
            try:
                # Run headless to verify silently in background
                context = p.chromium.launch_persistent_context(
                    user_data_dir,
                    headless=True,
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                )
                page = context.pages[0] if context.pages else context.new_page()
                
                # Navigate to the feed page which requires authentication
                page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=25000)
                page.wait_for_timeout(3000)
                
                body_text = page.locator("body").inner_text().lower()
                if "linkedin.com/feed" in page.url and "join linkedin" not in body_text and "iniciar sesión" not in body_text:
                    session_valid = True
                    print("[Session] Your LinkedIn session is ACTIVE and valid.")
                else:
                    print("[Session] LinkedIn session EXPIRED or invalid.")
                context.close()
            except Exception as e:
                print(f"[Session] Error checking session: {e}")
                
    if not session_valid:
        print("\n" + "=" * 70)
        print("[LINKEDIN SESSION REQUIRED]")
        print("No active LinkedIn session found.")
        print("A headful Chrome window will open to allow manual login.")
        print("=" * 70 + "\n")
        
        with sync_playwright() as p:
            try:
                context = p.chromium.launch_persistent_context(
                    user_data_dir,
                    headless=False,
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                    viewport={"width": 1280, "height": 720}
                )
                page = context.pages[0] if context.pages else context.new_page()
                
                print("Navigating to LinkedIn login page...")
                page.goto("https://www.linkedin.com/login")
                
                print("\n" + "=" * 70)
                print("INSTRUCTIONS:")
                print("1. Log in to your LinkedIn account in the Chrome window.")
                print("2. Resolve any checkpoints (MFA or CAPTCHA) if prompted.")
                print("3. Once the main feed page loads, return here.")
                print("4. Press ENTER in this terminal to continue.")
                print("=" * 70 + "\n")
                
                input("Press ENTER when you are ready...")
                
                print(f"\n[Success] LinkedIn session started and saved persistently to {user_data_dir}")
                context.close()
            except Exception as e:
                print(f"[Error] Assisted authentication failed: {e}")
