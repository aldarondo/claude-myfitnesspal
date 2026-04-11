"""
Run this script once to authenticate with MyFitnessPal.
A browser window will open — log in, then close the window.
The session is saved to playwright-session.json for use by the MCP server.

Usage:
    python login.py
"""

import os
from playwright.sync_api import sync_playwright

SESSION_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "playwright-session.json")
MFP_LOGIN    = "https://www.myfitnesspal.com/account/login"
MFP_BASE     = "https://www.myfitnesspal.com"

def main():
    print("Opening browser — log in to MyFitnessPal, then close the window.")
    print("(The window will close automatically once you're logged in.)\n")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=["--start-maximized"])
        ctx     = browser.new_context(no_viewport=True)
        page    = ctx.new_page()
        page.goto(MFP_LOGIN)

        # Wait until the user has logged in (navigated away from the login page)
        page.wait_for_url(
            lambda url: "/account/login" not in url,
            timeout=120_000,
        )

        ctx.storage_state(path=SESSION_FILE)
        print(f"Session saved to: {SESSION_FILE}")
        print("You can now use the MyFitnessPal tools in Claude.")
        browser.close()

if __name__ == "__main__":
    main()
