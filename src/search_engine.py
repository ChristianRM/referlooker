import os
import re
import time
import requests
import urllib.parse
from playwright.sync_api import sync_playwright

RESERVED_SLUGS = {
    "dir", "jobs", "company", "school", "pulse", "posts", "share",
    "learning", "feed", "groups", "events", "newsletters", "help",
    "mynetwork", "messaging", "notifications"
}

def clean_linkedin_url(url: str) -> str:
    """
    Cleans and validates that the URL corresponds to an individual LinkedIn profile.
    Unpacks Google redirect links (/url?q=..., /url?url=...), removes tracking and query params,
    and normalizes to https://www.linkedin.com/in/{username}.
    """
    if not url:
        return ""
        
    try:
        raw_url = str(url).strip()
        
        # Unquote up to twice to handle nested URL encoding in redirects
        for _ in range(2):
            decoded = urllib.parse.unquote(raw_url)
            if decoded == raw_url:
                break
            raw_url = decoded
            
        # Check if wrapped in a Google redirect
        if "google." in raw_url and "/url" in raw_url:
            parsed_g = urllib.parse.urlparse(raw_url)
            qs = urllib.parse.parse_qs(parsed_g.query)
            target = qs.get("q", [None])[0] or qs.get("url", [None])[0]
            if target:
                raw_url = urllib.parse.unquote(target)
                
        # Regex search for linkedin.com/in/{slug}
        # Matches subdomains (mx.linkedin.com, www.linkedin.com, linkedin.com, etc.)
        match = re.search(r'(?:https?://)?(?:[a-zA-Z0-9_\-]+\.)?linkedin\.com/in/([a-zA-Z0-9_\-%]+)', raw_url, re.IGNORECASE)
        if match:
            slug = match.group(1).strip("/").strip()
            # Clean any trailing parameters or path fragments that might have attached
            if "?" in slug:
                slug = slug.split("?")[0]
            if "&" in slug:
                slug = slug.split("&")[0]
            if "#" in slug:
                slug = slug.split("#")[0]
            if "/" in slug:
                slug = slug.split("/")[0]
                
            slug_lower = slug.lower()
            if slug and slug_lower not in RESERVED_SLUGS and len(slug) >= 2:
                return f"https://www.linkedin.com/in/{slug}"
    except Exception:
        pass
    return ""

def search_candidates_via_playwright(query: str, max_results: int, config: dict, start_offset: int = 0) -> list:
    """
    Search directly on Google using Playwright without requiring external API keys.
    Serves as a fallback mechanism if Google CSE fails with 403 errors or quota limits.
    """
    urls = []
    # Force headful mode with stealth flags for Google search
    page_idx = (start_offset // max(1, max_results)) + 1
    print(f"[Fallback] Launching direct Google search with Playwright in headful mode (Page {page_idx})...")
    
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(
                headless=False,
                args=["--disable-blink-features=AutomationControlled"]
            )
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 720}
            )
            page = context.new_page()
            
            # Format search query for Google
            encoded_query = urllib.parse.quote(query)
            google_url = f"https://www.google.com/search?q={encoded_query}&start={start_offset}"
            
            page.goto(google_url, wait_until="domcontentloaded", timeout=30000)
            
            # Detect if Google threw a CAPTCHA (redirected to google.com/sorry)
            if "google.com/sorry" in page.url:
                print("\n" + "!" * 50)
                print("[Action Required] Google is requesting human verification (CAPTCHA).")
                print("Tip: To run 100% automated searches without CAPTCHA, activate Google Custom Search API in Google Cloud or configure SERPAPI_KEY in your .env.")
                print("If a browser window is visible, please complete the CAPTCHA now (waiting 15 seconds)...")
                print("!" * 50 + "\n")
                
                # Wait up to 15 seconds for user to solve CAPTCHA if headful
                try:
                    for _ in range(15):
                        page.wait_for_timeout(1000)
                        if "google.com/sorry" not in page.url:
                            print("[Success] CAPTCHA resolved. Waiting for search results to load...")
                            page.wait_for_timeout(2000)
                            break
                except Exception:
                    pass
            
            # Polling loop: Wait up to 10 seconds for search results to render and extract links
            extracted = []
            for attempt in range(10):
                try:
                    # If still stuck on sorry page, continue waiting
                    if "google.com/sorry" in page.url:
                        page.wait_for_timeout(1000)
                        continue
                        
                    # Extract from anchor elements
                    elements_data = page.eval_on_selector_all(
                        "a", 
                        "els => els.map(e => ({ href: e.href, attrHref: e.getAttribute('href'), dataHref: e.getAttribute('data-href'), ping: e.getAttribute('ping') }))"
                    )
                    
                    for item in elements_data:
                        for candidate_link in [item.get("href"), item.get("attrHref"), item.get("dataHref"), item.get("ping")]:
                            if candidate_link:
                                cleaned = clean_linkedin_url(candidate_link)
                                if cleaned and cleaned not in extracted:
                                    extracted.append(cleaned)
                                    if len(extracted) >= max_results:
                                        break
                        if len(extracted) >= max_results:
                            break
                            
                    # Fallback: scan page HTML for LinkedIn profile links if none found yet
                    if not extracted:
                        html_content = page.content()
                        # Unescape backslashes if any exist in JSON embedded in HTML
                        clean_html = html_content.replace("\\/", "/")
                        matches = re.findall(r'(?:https?://)?(?:[a-zA-Z0-9_\-]+\.)?linkedin\.com/in/([a-zA-Z0-9_\-%]+)', clean_html, re.IGNORECASE)
                        for slug in matches:
                            cleaned = clean_linkedin_url(f"https://www.linkedin.com/in/{slug}")
                            if cleaned and cleaned not in extracted:
                                extracted.append(cleaned)
                                if len(extracted) >= max_results:
                                    break
                                    
                    if extracted:
                        print(f"[Success] Extracted {len(extracted)} candidate LinkedIn profile(s) from search results.")
                        break
                        
                except Exception as e:
                    # Handle brief moments where page context is navigating
                    pass
                    
                page.wait_for_timeout(1000)
                
            urls = extracted[:max_results]
            # Brief pause before closing browser so user sees successful extraction
            page.wait_for_timeout(1000)
            browser.close()
        except Exception as e:
            print(f"[Fallback Error] Direct Google search failed: {e}")
            
    return urls


def load_dotenv(dotenv_path=".env"):
    """
    Simple parser for .env file if it exists and loads variables to os.environ.
    Avoids third-party dependencies like python-dotenv.
    """
    if os.path.exists(dotenv_path):
        try:
            with open(dotenv_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        key, val = line.split("=", 1)
                        # Remove quotes if they exist in the value
                        val = val.strip().strip("'").strip('"')
                        os.environ[key.strip()] = val
        except Exception as e:
            print(f"[Warning] Could not read .env file: {e}")

# Load environment variables on module import
load_dotenv()

def extract_concise_keywords(query: str, target_country: str = "Any") -> str:
    """Extracts concise, high-relevance natural search keywords from complex boolean X-Ray query."""
    # 1. Strip OpenToWork & boilerplate terms
    q = re.sub(r'\("?open to work"?.*?\)', '', query, flags=re.IGNORECASE)
    q = re.sub(r'site:linkedin\.com/in/?', '', q, flags=re.IGNORECASE)
    
    # 2. Extract parenthesized groups
    groups = re.findall(r'\(([^)]+)\)', q)
    terms = []
    
    for g in groups:
        items = re.findall(r'"([^"]+)"', g) or [i.strip() for i in g.split("OR")]
        clean_items = [i.strip() for i in items if i.strip() and i.strip().lower() not in {"open to work", "opentowork", "#opentowork", "seeking", "looking for", "disponible", "open to opportunities"}]
        if clean_items:
            # Pick ONLY the first item from this group to avoid competing role titles
            terms.append(clean_items[0])
            
    if not terms:
        quoted = re.findall(r'"([^"]+)"', q)
        terms = quoted[:2] if quoted else q.split()[:3]
        
    # Build clean keyword string
    clean_terms = []
    for t in terms:
        t_clean = re.sub(r'["\']', '', t).strip()
        if t_clean and t_clean.lower() not in ("mexico", "méxico", "spain", "españa", "colombia", "argentina", "latam", "remote"):
            clean_terms.append(t_clean)
            
    result = " ".join(clean_terms[:3])
    
    if target_country and target_country not in ("Any", "Remote", "") and target_country.lower() not in result.lower():
        result += f" {target_country}"
        
    return result.strip()

def search_candidates_via_linkedin_direct(query: str, max_results: int = 5, start_offset: int = 0) -> list:
    """
    Directly queries LinkedIn search using saved authenticated cookies.
    Highly reliable, fast, zero API keys required, and never blocked by Google CAPTCHA.
    """
    cookies_path = "cookies.json"
    if not os.path.exists(cookies_path):
        return []
        
    extracted = []
    page_num = (start_offset // max(1, max_results)) + 1
    clean_kw = extract_concise_keywords(query)
    if not clean_kw:
        clean_kw = query.replace('site:linkedin.com/in/', '').replace('site:linkedin.com/in', '').strip()
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                storage_state=cookies_path,
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            encoded = urllib.parse.quote(clean_kw)
            url = f"https://www.linkedin.com/search/results/people/?keywords={encoded}&origin=GLOBAL_SEARCH_HEADER"
            if page_num > 1:
                url += f"&page={page_num}"
                
            print(f"[Direct LinkedIn] Sourcing candidates via LinkedIn People Search ({clean_kw}): {url}")
            page.goto(url, wait_until="domcontentloaded", timeout=25000)
            page.wait_for_timeout(2500)
            
            links = page.eval_on_selector_all("a", "els => els.map(e => e.href)")
            for l in links:
                cleaned = clean_linkedin_url(l)
                if cleaned and cleaned not in extracted:
                    extracted.append(cleaned)
                    if len(extracted) >= max_results:
                        break
                        
            browser.close()
            print(f"[Direct LinkedIn] Found {len(extracted)} candidate profiles.")
    except Exception as e:
        print(f"[Direct LinkedIn Error] {e}")
        
    return extracted

def search_candidates(query: str, config: dict, start_offset: int = 0) -> list:
    """
    Executes search query on Google via Google Custom Search, SerpAPI, or Direct LinkedIn Search.
    Returns a list of unique LinkedIn profile URLs.
    """
    engine_config = config.get("search_engine", {})
    engine = engine_config.get("engine", "auto")
    max_results = config.get("search_limits", {}).get("max_results_per_vacancy", 5)
    
    urls = []
    
    page_idx = (start_offset // max(1, max_results)) + 1
    print(f"Starting search using engine '{engine}' with query: {query} (Page {page_idx})")
    
    # 1. Check if direct LinkedIn search with session cookies is available (preferred & most reliable)
    if os.path.exists("cookies.json") and engine in ("auto", "linkedin_direct", "google_cse", "google_playwright"):
        direct_urls = search_candidates_via_linkedin_direct(query, max_results=max_results, start_offset=start_offset)
        if direct_urls:
            return list(dict.fromkeys(direct_urls))
            
    if engine in ("google_playwright", "direct"):
        return list(dict.fromkeys(search_candidates_via_playwright(query, max_results, config, start_offset)))
        
    if engine in ("google_cse", "auto"):
        # Prioritize environment variables (from .env file)
        api_key = os.getenv("GOOGLE_API_KEY") or engine_config.get("google_api_key", "")
        cx = os.getenv("GOOGLE_CX") or engine_config.get("google_cx", "")
        
        if not api_key or not cx or api_key in ("YOUR_GOOGLE_API_KEY", "Ver archivo .env", "") or cx in ("YOUR_GOOGLE_CSE_ID", "Ver archivo .env", ""):
            print("[Warning] Google Custom Search API Key or CX ID not configured. Set them in your '.env' file.")
            if os.path.exists("cookies.json"):
                direct_urls = search_candidates_via_linkedin_direct(query, max_results=max_results, start_offset=start_offset)
                if direct_urls:
                    return list(dict.fromkeys(direct_urls))
            print("[Warning] Activating Playwright fallback search...")
            return list(dict.fromkeys(search_candidates_via_playwright(query, max_results, config, start_offset)))
            
        params = {
            "key": api_key,
            "cx": cx,
            "q": query,
            "num": max_results
        }
        if start_offset > 0:
            params["start"] = start_offset + 1
            
        # Try primary Custom Search API endpoint (v1) and fallback to siterestrict if configured
        endpoints = [
            "https://www.googleapis.com/customsearch/v1",
            "https://www.googleapis.com/customsearch/v1/siterestrict"
        ]
        
        cse_success = False
        for url in endpoints:
            try:
                response = requests.get(url, params=params, timeout=15)
                if response.status_code == 200:
                    data = response.json()
                    items = data.get("items", [])
                    for item in items:
                        link = item.get("link", "")
                        cleaned = clean_linkedin_url(link)
                        if cleaned and cleaned not in urls:
                            urls.append(cleaned)
                    cse_success = True
                    break
                else:
                    try:
                        error_json = response.json()
                        error_msg = error_json.get("error", {}).get("message", "No detailed message")
                    except Exception:
                        error_msg = response.text
                    print(f"[Notice] Google CSE endpoint '{url}' returned code {response.status_code}: {error_msg}")
            except Exception as e:
                print(f"[Error] Search with Google CSE endpoint '{url}' failed: {e}")
                
        if not cse_success and not urls:
            if os.path.exists("cookies.json"):
                direct_urls = search_candidates_via_linkedin_direct(query, max_results=max_results, start_offset=start_offset)
                if direct_urls:
                    return list(dict.fromkeys(direct_urls))
            print("[Warning] Google CSE was unsuccessful. Activating direct Playwright fallback search...")
            return list(dict.fromkeys(search_candidates_via_playwright(query, max_results, config, start_offset)))
            
    elif engine == "serpapi":
        # Prioritize environment variables (from .env file)
        api_key = os.getenv("SERPAPI_KEY") or engine_config.get("serpapi_key", "")
        
        if not api_key or api_key in ("YOUR_SERPAPI_KEY", "Ver archivo .env", ""):
            print("[Warning] SerpAPI Key not configured. Set it in your '.env' file.")
            if os.path.exists("cookies.json"):
                direct_urls = search_candidates_via_linkedin_direct(query, max_results=max_results, start_offset=start_offset)
                if direct_urls:
                    return list(dict.fromkeys(direct_urls))
            return []
            
        url = "https://serpapi.com/search"
        params = {
            "engine": "google",
            "q": query,
            "api_key": api_key,
            "num": max_results
        }
        if start_offset > 0:
            params["start"] = start_offset
            
        try:
            response = requests.get(url, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()
            results = data.get("organic_results", [])
            for result in results:
                link = result.get("link", "")
                cleaned = clean_linkedin_url(link)
                if cleaned:
                    urls.append(cleaned)
        except Exception as e:
            print(f"[Error] Search with SerpAPI failed: {e}")
            if os.path.exists("cookies.json"):
                direct_urls = search_candidates_via_linkedin_direct(query, max_results=max_results, start_offset=start_offset)
                if direct_urls:
                    return list(dict.fromkeys(direct_urls))
            
    else:
        print(f"[Error] Unrecognized search engine: {engine}")
        if os.path.exists("cookies.json"):
            direct_urls = search_candidates_via_linkedin_direct(query, max_results=max_results, start_offset=start_offset)
            if direct_urls:
                return list(dict.fromkeys(direct_urls))
        
    # Deduplicate while preserving original order
    unique_urls = list(dict.fromkeys(urls))
    print(f"Found {len(unique_urls)} unique LinkedIn profiles.")
    return unique_urls
