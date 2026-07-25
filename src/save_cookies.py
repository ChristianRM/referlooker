import os
import sys
import json
from playwright.sync_api import sync_playwright

def main():
    cookies_path = "cookies.json"
    print("Launching browser to log into LinkedIn...")
    
    with sync_playwright() as p:
        # Launch the browser in headful mode (headless=False) to allow user interaction
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        
        print("Navigating to the LinkedIn login page...")
        page.goto("https://www.linkedin.com/login")
        
        print("\n" + "=" * 60)
        print("INSTRUCTIONS:")
        print("1. Log in to LinkedIn in the browser window that just opened.")
        print("2. Resolve any security checks (MFA, CAPTCHA) if required.")
        print("3. Once you reach the LinkedIn home feed page,")
        print("   return to this terminal and press ENTER.")
        print("=" * 60 + "\n")
        
        input("Press ENTER when you have successfully logged in...")
        
        # Save the complete storage state (cookies + local storage)
        context.storage_state(path=cookies_path)
            
        print(f"\n[Success] Session successfully saved to: {os.path.abspath(cookies_path)}")
        browser.close()

if __name__ == "__main__":
    main()
