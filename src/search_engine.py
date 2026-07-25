import os
import time
import requests
import urllib.parse
from playwright.sync_api import sync_playwright

def search_candidates_via_playwright(query: str, max_results: int, config: dict, start_offset: int = 0) -> list:
    """
    Search directly on Google using Playwright without requiring external API keys.
    Serves as a fallback mechanism if Google CSE fails with 403 errors or quota limits.
    """
    urls = []
    # Force headless=False for Google search to avoid bot detection and allow solving CAPTCHAs
    print(f"[Fallback] Launching direct Google search with Playwright in headful mode (headless=False) at offset {start_offset}...")
    
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=False)
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
                print("[Action Required] Google is requesting a human verification (CAPTCHA).")
                print("Please resolve it in the browser window that just opened.")
                print("The script will wait for you to complete it before continuing automatically...")
                print("!" * 50 + "\n")
                
                # Wait up to 2 minutes for the URL to no longer be the CAPTCHA page
                try:
                    for _ in range(120):
                        page.wait_for_timeout(1000)  # Allow Playwright to process events and update page URL
                        if "google.com/sorry" not in page.url:
                            print("[Success] CAPTCHA resolved. Continuing with extraction...")
                            break
                except Exception:
                    pass
            
            # Wait for Google search results container (#search) to render
            try:
                page.wait_for_selector("#search", timeout=5000)
            except Exception:
                # Fallback if it does not render but links might still be present
                page.wait_for_timeout(2000)
            
            # Extract all anchor tags (a) hrefs that correspond to LinkedIn profiles
            hrefs = page.eval_on_selector_all("a", "elements => elements.map(el => el.href)")
            
            for href in hrefs:
                cleaned = clean_linkedin_url(href)
                if cleaned:
                    urls.append(cleaned)
                    if len(urls) >= max_results:
                        break
                        
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

def clean_linkedin_url(url: str) -> str:
    """
    Cleans and validates that the URL corresponds to an individual LinkedIn profile.
    Removes additional query parameters (?miniProfile=..., etc.).
    """
    try:
        # Decode URL in case it is URL-encoded
        decoded_url = urllib.parse.unquote(url)
        parsed = urllib.parse.urlparse(decoded_url)
        
        # Check if it is a LinkedIn profile link
        if "linkedin.com/in/" in parsed.netloc + parsed.path:
            # Reconstruct clean URL using only path (e.g. /in/candidate-name/)
            path = parsed.path
            # Remove trailing slashes
            path = path.rstrip("/")
            clean_url = f"https://www.linkedin.com{path}"
            return clean_url
    except Exception:
        pass
    return ""

def search_candidates(query: str, config: dict, start_offset: int = 0) -> list:
    """
    Executes search query on Google via Google Custom Search or SerpAPI.
    Returns a list of unique LinkedIn profile URLs.
    """
    engine_config = config.get("search_engine", {})
    engine = engine_config.get("engine", "google_cse")
    max_results = config.get("search_limits", {}).get("max_results_per_vacancy", 5)
    
    urls = []
    
    print(f"Starting search using engine '{engine}' with query: {query} (offset: {start_offset})")
    
    if engine in ("google_playwright", "direct"):
        return list(dict.fromkeys(search_candidates_via_playwright(query, max_results, config, start_offset)))
        
    if engine == "google_cse":
        # Prioritize environment variables (from .env file)
        api_key = os.getenv("GOOGLE_API_KEY") or engine_config.get("google_api_key", "")
        cx = os.getenv("GOOGLE_CX") or engine_config.get("google_cx", "")
        
        if not api_key or not cx or api_key in ("YOUR_GOOGLE_API_KEY", "Ver archivo .env", "") or cx in ("YOUR_GOOGLE_CSE_ID", "Ver archivo .env", ""):
            print("[Warning] Google Custom Search API Key or CX ID not configured. Set them in your '.env' file.")
            print("[Warning] Activating Playwright fallback search...")
            return list(dict.fromkeys(search_candidates_via_playwright(query, max_results, config, start_offset)))
            
        url = "https://www.googleapis.com/customsearch/v1"
        params = {
            "key": api_key,
            "cx": cx,
            "q": query,
            "num": max_results
        }
        if start_offset > 0:
            params["start"] = start_offset + 1
            
        try:
            response = requests.get(url, params=params, timeout=15)
            if response.status_code != 200:
                try:
                    error_json = response.json()
                    error_msg = error_json.get("error", {}).get("message", "No detailed message")
                    print(f"[Error] Google CSE returned code {response.status_code}: {error_msg}")
                except Exception:
                    print(f"[Error] Google CSE returned code {response.status_code}: {response.text}")
                
                # Automatic fallback on 400 or 403 errors
                if response.status_code in (400, 403):
                    print("[Warning] Google CSE error detected. Activating direct Playwright fallback search...")
                    return list(dict.fromkeys(search_candidates_via_playwright(query, max_results, config, start_offset)))
                return []
                
            response.raise_for_status()
            data = response.json()
            items = data.get("items", [])
            for item in items:
                link = item.get("link", "")
                cleaned = clean_linkedin_url(link)
                if cleaned:
                    urls.append(cleaned)
        except Exception as e:
            print(f"[Error] Search with Google CSE failed: {e}")
            
    elif engine == "serpapi":
        # Prioritize environment variables (from .env file)
        api_key = os.getenv("SERPAPI_KEY") or engine_config.get("serpapi_key", "")
        
        if not api_key or api_key in ("YOUR_SERPAPI_KEY", "Ver archivo .env", ""):
            print("[Warning] SerpAPI Key not configured. Set it in your '.env' file.")
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
            
    else:
        print(f"[Error] Unrecognized search engine: {engine}")
        
    # Deduplicate while preserving original order
    unique_urls = list(dict.fromkeys(urls))
    print(f"Found {len(unique_urls)} unique LinkedIn profiles.")
    return unique_urls
