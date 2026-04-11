"""
MyFitnessPal MCP Server
Exposes MyFitnessPal data as MCP tools for Claude Cowork.

Uses a persistent Playwright browser session stored locally.
Run login.py once to authenticate; all subsequent calls reuse the saved session.

Session file: playwright-session.json (gitignored)
"""

import datetime
import json
import os
from typing import Any

from mcp.server.fastmcp import FastMCP
from playwright.sync_api import sync_playwright, Browser, BrowserContext

mcp = FastMCP("MyFitnessPal")

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_SESSION_FILE = os.path.join(_SCRIPT_DIR, "playwright-session.json")
_MFP_BASE = "https://www.myfitnesspal.com"
_AUTH_URL = f"{_MFP_BASE}/user/auth_token?refresh=true"

# Global browser instance (created once at startup)
_browser: Browser | None = None
_playwright = None

def _init_browser():
    """Initialize the global browser instance."""
    global _browser, _playwright
    if _browser is None:
        _playwright = sync_playwright().__enter__()
        _browser = _playwright.chromium.launch(headless=True)


def _get_context() -> BrowserContext:
    """Return a Playwright browser context, restoring saved session if present."""
    _init_browser()
    if os.path.exists(_SESSION_FILE):
        return _browser.new_context(storage_state=_SESSION_FILE)
    return _browser.new_context()


def _get_bearer_token(ctx: BrowserContext) -> str:
    """Fetch a short-lived Bearer token from MFP using the stored session."""
    resp = ctx.request.get(_AUTH_URL)
    if not resp.ok:
        ctx.close()
        raise RuntimeError(
            f"MFP auth failed (HTTP {resp.status}). "
            "Run login.py to re-authenticate."
        )
    ct = resp.headers.get("content-type", "")
    if "application/json" not in ct:
        ctx.close()
        raise RuntimeError(
            "MFP returned non-JSON — session has expired. "
            "Run login.py to re-authenticate."
        )
    return resp.json()["access_token"]


def _parse_date(date_str: str) -> datetime.date:
    return datetime.date.fromisoformat(date_str) if date_str else datetime.date.today()


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def get_diary(date: str = "") -> str:
    """
    Get the food diary for a specific date.

    Args:
        date: Date in YYYY-MM-DD format. Defaults to today.

    Returns:
        JSON with meals, food entries, nutritional totals, and daily goals.
    """
    d = _parse_date(date)
    ctx = _get_context()
    try:
        token = _get_bearer_token(ctx)

        # Try API first
        resp = ctx.request.get(
            f"{_MFP_BASE}/api/nutrition",
            params={"from": str(d), "to": str(d)},
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        )
        if resp.ok and "application/json" in resp.headers.get("content-type", ""):
            result = resp.text()
            ctx.close()
            return result

        # Fallback: scrape the page
        page = ctx.new_page()
        page.goto(f"{_MFP_BASE}/food/diary/{d}", wait_until="domcontentloaded")
        next_data = page.evaluate(
            "() => { const el = document.getElementById('__NEXT_DATA__'); return el ? JSON.parse(el.textContent) : null; }"
        )
        page.close()
        ctx.close()

        if next_data:
            try:
                props = next_data["props"]["pageProps"]
                return json.dumps(props, default=str)
            except (KeyError, TypeError):
                return json.dumps(next_data, default=str)

        return json.dumps({"error": "Could not retrieve diary. Run login.py to re-authenticate."})
    except Exception as e:
        ctx.close()
        return json.dumps({"error": str(e)})


@mcp.tool()
def get_measurements(
    measurement: str = "Weight",
    lower_bound: str = "",
    upper_bound: str = "",
) -> str:
    """
    Get body measurements over a date range.

    Args:
        measurement: e.g. "Weight", "Neck", "Waist", "Hips". Default: "Weight".
        lower_bound: Start date YYYY-MM-DD. Leave blank for all-time.
        upper_bound: End date YYYY-MM-DD. Leave blank for today.

    Returns:
        JSON dict mapping date strings to measurement values.
    """
    ctx = _get_context()
    try:
        token = _get_bearer_token(ctx)

        params = {"name": measurement}
        if lower_bound:
            params["from"] = lower_bound
        if upper_bound:
            params["to"] = upper_bound

        resp = ctx.request.get(
            f"{_MFP_BASE}/measurements",
            params=params,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        )

        if resp.ok and "application/json" in resp.headers.get("content-type", ""):
            result = resp.text()
            ctx.close()
            return result

        # Fallback: scrape
        page = ctx.new_page()
        page.goto(f"{_MFP_BASE}/measurements/check-in", wait_until="domcontentloaded")
        next_data = page.evaluate(
            "() => { const el = document.getElementById('__NEXT_DATA__'); return el ? JSON.parse(el.textContent) : null; }"
        )
        page.close()
        ctx.close()
        return json.dumps(next_data or {"error": "Could not retrieve measurements."}, default=str)
    except Exception as e:
        ctx.close()
        return json.dumps({"error": str(e)})


@mcp.tool()
def search_foods(query: str) -> str:
    """
    Search the MyFitnessPal food database.

    Args:
        query: Food name or brand (e.g. "chicken breast", "Chobani yogurt").

    Returns:
        JSON list of matching food items with name, brand, and nutritional info.
    """
    ctx = _get_context()
    try:
        token = _get_bearer_token(ctx)
        resp = ctx.request.get(
            "https://api.myfitnesspal.com/public/nutrition",
            params={"q": query, "page": "1", "per_page": "20"},
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "mfp-client-id": "mfp-main-js",
            },
        )
        ctx.close()
        if resp.ok:
            return resp.text()
        return json.dumps({"error": f"Search failed: HTTP {resp.status}"})
    except Exception as e:
        ctx.close()
        return json.dumps({"error": str(e)})


@mcp.tool()
def get_weekly_summary(start_date: str) -> str:
    """
    Get a 7-day nutrition summary starting from a given date.

    Args:
        start_date: Start date in YYYY-MM-DD format.

    Returns:
        JSON with daily diary data for each of the 7 days.
    """
    start = _parse_date(start_date)
    end = start + datetime.timedelta(days=6)

    ctx = _get_context()
    try:
        token = _get_bearer_token(ctx)

        resp = ctx.request.get(
            f"{_MFP_BASE}/api/nutrition",
            params={"from": str(start), "to": str(end)},
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        )

        if resp.ok and "application/json" in resp.headers.get("content-type", ""):
            result = resp.text()
            ctx.close()
            return result

        # Fallback: fetch each day individually
        days = []
        for i in range(7):
            d = start + datetime.timedelta(days=i)
            page = ctx.new_page()
            page.goto(f"{_MFP_BASE}/food/diary/{d}", wait_until="domcontentloaded")
            nd = page.evaluate(
                "() => { const el = document.getElementById('__NEXT_DATA__'); return el ? JSON.parse(el.textContent) : null; }"
            )
            page.close()
            days.append({"date": str(d), "data": nd})

        ctx.close()
        return json.dumps({"days": days}, default=str)
    except Exception as e:
        ctx.close()
        return json.dumps({"error": str(e)})


@mcp.tool()
def log_measurement(
    value: float,
    measurement: str = "Weight",
    date: str = "",
) -> str:
    """
    Log a body measurement to MyFitnessPal.

    Args:
        value: Measurement value (e.g. 185.5 for weight in lbs).
        measurement: e.g. "Weight", "Neck", "Waist", "Hips". Default: "Weight".
        date: Date YYYY-MM-DD. Defaults to today.

    Returns:
        Confirmation message.
    """
    d = _parse_date(date)
    ctx = _get_context()
    try:
        token = _get_bearer_token(ctx)
        resp = ctx.request.post(
            f"{_MFP_BASE}/api/measurements",
            data=json.dumps({"measurement": {"date": str(d), "value": value, "unit": measurement}}),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        ctx.close()
        if resp.ok:
            return json.dumps({"status": "ok", "measurement": measurement, "value": value, "date": str(d)})
        return json.dumps({"status": "error", "http_status": resp.status, "detail": resp.text()[:300]})
    except Exception as e:
        ctx.close()
        return json.dumps({"status": "error", "detail": str(e)})


if __name__ == "__main__":
    mcp.run()
