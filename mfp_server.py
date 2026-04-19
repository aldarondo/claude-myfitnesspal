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


@mcp.tool()
def session_status() -> str:
    """
    Check whether the current MyFitnessPal session is valid.

    Returns:
        JSON with "status": "valid" or "expired", plus re-auth instructions if needed.
    """
    ctx = _get_context()
    try:
        _get_bearer_token(ctx)
        ctx.close()
        return json.dumps({"status": "valid", "message": "Session is active."})
    except RuntimeError as e:
        ctx.close()
        return json.dumps({
            "status": "expired",
            "message": str(e),
            "instructions": "Run `python login.py` from a terminal to re-authenticate.",
        })
    except Exception as e:
        ctx.close()
        return json.dumps({
            "status": "unknown",
            "message": f"Could not verify session: {e}",
            "instructions": "Run `python login.py` from a terminal to re-authenticate.",
        })


@mcp.tool()
def log_food_entry(
    food_name: str,
    meal: str = "Lunch",
    quantity: float = 1.0,
    unit: str = "",
    date: str = "",
) -> str:
    """
    Log a food entry to the MyFitnessPal diary.

    First searches for the food, then logs the top result.

    Args:
        food_name: Food name to search for and log (e.g. "chicken breast", "Chobani yogurt").
        meal: Meal name — Breakfast, Lunch, Dinner, or Snacks. Default: Lunch.
        quantity: Quantity to log. Default: 1.0.
        unit: Unit description (e.g. "oz", "serving", "cup"). Defaults to first available unit.
        date: Date in YYYY-MM-DD format. Defaults to today.

    Returns:
        Confirmation message with food logged, calories, and macros.
    """
    d = _parse_date(date)

    # Step 1: search for the food
    search_result_raw = search_foods(food_name)
    try:
        search_result = json.loads(search_result_raw)
    except (json.JSONDecodeError, ValueError) as exc:
        return json.dumps({"status": "error", "detail": f"Could not parse search results: {exc}"})

    if "error" in search_result:
        return json.dumps({"status": "error", "detail": search_result["error"]})

    # Normalise: API returns {"items": [...]} or a top-level list
    items = search_result if isinstance(search_result, list) else search_result.get("items", [])
    if not items:
        return json.dumps({"status": "error", "detail": f"No foods found for '{food_name}'"})

    top = items[0]

    # Pull food_id — field name varies by API version
    food_id = (
        top.get("id")
        or top.get("food_id")
        or (top.get("food") or {}).get("id")
    )
    if not food_id:
        return json.dumps({"status": "error", "detail": "Search result missing food ID", "item": top})

    # Resolve unit
    if not unit:
        # Try to find a default serving unit from the search result
        servings = (
            top.get("servings")
            or (top.get("food") or {}).get("servings")
            or []
        )
        if isinstance(servings, list) and servings:
            unit = servings[0].get("unit", "serving")
        elif isinstance(servings, dict):
            # some versions: {"serving": {"unit": "..."}}
            inner = servings.get("serving") or {}
            unit = inner.get("unit", "serving") if isinstance(inner, dict) else "serving"
        else:
            unit = "serving"

    food_display_name = (
        top.get("description")
        or top.get("name")
        or (top.get("food") or {}).get("description")
        or food_name
    )

    # Pull calories for the confirmation message (best-effort)
    calories = None
    try:
        entry_nutrition = (
            top.get("nutritional_contents")
            or (top.get("food") or {}).get("nutritional_contents")
            or {}
        )
        calories = entry_nutrition.get("energy", {}).get("value") if isinstance(entry_nutrition.get("energy"), dict) else entry_nutrition.get("calories")
    except Exception:
        pass

    # Step 2: POST the diary entry
    ctx = _get_context()
    try:
        token = _get_bearer_token(ctx)

        payload = json.dumps({
            "food_entries": [{
                "food_id": str(food_id),
                "meal_entry_name": meal,
                "quantity": quantity,
                "unit_name": unit,
                "date": str(d),
            }]
        })

        resp = ctx.request.post(
            f"{_MFP_BASE}/api/nutrition",
            data=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

        if resp.ok:
            ctx.close()
            result = {
                "status": "ok",
                "food": food_display_name,
                "meal": meal,
                "quantity": quantity,
                "unit": unit,
                "date": str(d),
            }
            if calories is not None:
                result["calories"] = calories
            return json.dumps(result)

        # Fallback: Playwright page navigation to fill the diary form
        page = ctx.new_page()
        page.goto(f"{_MFP_BASE}/food/diary/{d}", wait_until="domcontentloaded")

        # Try the legacy diary add endpoint via fetch() inside the page
        js_result = page.evaluate(
            """
            async ([foodId, mealName, qty, unitName, dateStr]) => {
                try {
                    const r = await fetch('/food/diary/add', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/x-www-form-urlencoded'},
                        body: new URLSearchParams({
                            food_id: foodId,
                            meal_entry_name: mealName,
                            quantity: qty,
                            unit_name: unitName,
                            date: dateStr,
                        }).toString(),
                        credentials: 'include',
                    });
                    return {ok: r.ok, status: r.status, body: await r.text()};
                } catch(e) {
                    return {ok: false, status: 0, body: e.toString()};
                }
            }
            """,
            [str(food_id), meal, quantity, unit, str(d)],
        )
        page.close()
        ctx.close()

        if js_result and js_result.get("ok"):
            result = {
                "status": "ok",
                "food": food_display_name,
                "meal": meal,
                "quantity": quantity,
                "unit": unit,
                "date": str(d),
                "method": "page_fallback",
            }
            if calories is not None:
                result["calories"] = calories
            return json.dumps(result)

        return json.dumps({
            "status": "error",
            "detail": "Both API and page-navigation logging attempts failed",
            "api_status": resp.status,
            "fallback_status": (js_result or {}).get("status"),
            "fallback_body": str((js_result or {}).get("body", ""))[:300],
        })

    except Exception as e:
        ctx.close()
        return json.dumps({"status": "error", "detail": str(e)})


def _parse_day_totals(day_data: dict) -> dict | None:
    """Extract calorie and macro totals from a single day's diary API response."""
    if not isinstance(day_data, dict):
        return None
    # API format: {"goals": {...}, "totals": {"calories": N, "protein": N, ...}}
    totals = day_data.get("totals") or {}
    goals = day_data.get("goals") or {}
    if not totals:
        # pageProps format
        try:
            props = day_data.get("pageProps") or day_data
            totals = props.get("diary", {}).get("totals", {})
            goals = props.get("diary", {}).get("goals", {})
        except Exception:
            return None
    if not totals:
        return None
    return {
        "calories": totals.get("calories") or totals.get("energy"),
        "protein": totals.get("protein"),
        "carbs": totals.get("carbohydrates") or totals.get("carbs"),
        "fat": totals.get("fat"),
        "goal_calories": goals.get("calories") or goals.get("energy"),
    }


@mcp.tool()
def get_weekly_trends(start_date: str = "") -> str:
    """
    Get a 7-day nutrition trends summary: average calories, macros, best/worst days,
    and comparison to daily calorie goal.

    Args:
        start_date: Start date YYYY-MM-DD. Defaults to 7 days ago (last full week).

    Returns:
        Human-readable summary with per-day breakdown and weekly averages.
    """
    if start_date:
        start = _parse_date(start_date)
    else:
        start = datetime.date.today() - datetime.timedelta(days=7)

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
            raw = resp.json()
            ctx.close()
        else:
            # Fallback: fetch each day
            days_raw = []
            for i in range(7):
                d = start + datetime.timedelta(days=i)
                page = ctx.new_page()
                page.goto(f"{_MFP_BASE}/food/diary/{d}", wait_until="domcontentloaded")
                nd = page.evaluate(
                    "() => { const el = document.getElementById('__NEXT_DATA__'); return el ? JSON.parse(el.textContent) : null; }"
                )
                page.close()
                days_raw.append({"date": str(d), "data": nd or {}})
            ctx.close()
            raw = {"days": days_raw}

    except Exception as e:
        ctx.close()
        return json.dumps({"error": str(e)})

    # Parse per-day totals
    day_entries = raw if isinstance(raw, list) else raw.get("items") or raw.get("days") or []
    parsed_days = []

    if isinstance(day_entries, list):
        for entry in day_entries:
            date_val = entry.get("date") or ""
            data = entry.get("data") or entry
            totals = _parse_day_totals(data)
            if totals:
                totals["date"] = str(date_val)[:10]
                parsed_days.append(totals)
    else:
        # Single dict response (rare)
        t = _parse_day_totals(raw)
        if t:
            t["date"] = str(start)
            parsed_days.append(t)

    if not parsed_days:
        return json.dumps({
            "status": "no_data",
            "message": "No nutrition data found for this week. Make sure the session is valid.",
        })

    # Compute aggregates
    def avg(values):
        vals = [v for v in values if v is not None]
        return round(sum(vals) / len(vals), 1) if vals else None

    calories_list = [d["calories"] for d in parsed_days if d.get("calories") is not None]
    protein_list  = [d["protein"]  for d in parsed_days if d.get("protein") is not None]
    carbs_list    = [d["carbs"]    for d in parsed_days if d.get("carbs") is not None]
    fat_list      = [d["fat"]      for d in parsed_days if d.get("fat") is not None]
    goal_cal      = next((d["goal_calories"] for d in parsed_days if d.get("goal_calories")), None)

    best_day  = max(parsed_days, key=lambda d: d.get("calories") or 0) if calories_list else None
    worst_day = min(parsed_days, key=lambda d: d.get("calories") or float("inf")) if calories_list else None

    lines = [f"Weekly nutrition trends ({start} → {end})", ""]
    lines.append("Per-day calories:")
    for d in parsed_days:
        cal = d.get("calories")
        line = f"  {d['date']}: {cal} kcal" if cal is not None else f"  {d['date']}: no data"
        if goal_cal and cal is not None:
            diff = cal - goal_cal
            sign = "+" if diff >= 0 else ""
            line += f" ({sign}{diff} vs goal)"
        lines.append(line)

    lines.append("")
    lines.append("Averages:")
    if avg(calories_list) is not None:
        lines.append(f"  Calories: {avg(calories_list)} kcal/day")
        if goal_cal:
            lines.append(f"  Calorie goal: {goal_cal} kcal/day")
    if avg(protein_list) is not None:
        lines.append(f"  Protein:  {avg(protein_list)} g/day")
    if avg(carbs_list) is not None:
        lines.append(f"  Carbs:    {avg(carbs_list)} g/day")
    if avg(fat_list) is not None:
        lines.append(f"  Fat:      {avg(fat_list)} g/day")

    if best_day and worst_day and best_day["date"] != worst_day["date"]:
        lines.append("")
        lines.append(f"Best day:  {best_day['date']} ({best_day.get('calories')} kcal)")
        lines.append(f"Worst day: {worst_day['date']} ({worst_day.get('calories')} kcal)")

    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run()
