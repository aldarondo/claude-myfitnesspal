# MyFitnessPal MCP Connector

A custom MCP (Model Context Protocol) server that connects Claude to your MyFitnessPal account. Ask Claude about your food diary, nutrition trends, body measurements, and more — or have it log measurements and update your goals.

Uses **Playwright** under the hood to make requests through a real browser, bypassing MFP's bot detection. You authenticate once via a visible browser window; the session is saved locally and reused automatically.

## Tools

| Tool | Type | Description |
|------|------|-------------|
| `login` | Auth | Open a browser to log in and save your session (run once) |
| `get_diary` | Read | Food diary for a specific date — meals, entries, macros, goals |
| `get_measurements` | Read | Body measurements over a date range (weight, waist, etc.) |
| `search_foods` | Read | Search the MFP food database |
| `get_weekly_summary` | Read | 7-day nutrition data |
| `log_measurement` | Write | Log a body measurement (weight, neck, waist, etc.) |

> **Note:** Logging food diary entries (adding what you ate) is not supported — MFP's API does not expose that write endpoint to third parties.

## Setup

### 1. Install dependencies

```bash
pip install mcp playwright
python -m playwright install chromium
```

### 2. Register the MCP server

Add the following to `%APPDATA%\Claude\claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "myfitnesspal": {
      "command": "C:\\Users\\<YourName>\\AppData\\Local\\Programs\\Python\\Python312\\python.exe",
      "args": [
        "C:\\Users\\<YourName>\\Documents\\Github\\claude-myfitnesspal\\mfp_server.py"
      ]
    }
  }
}
```

### 3. Authenticate (one-time)

Run the login script directly from a terminal — this must be run outside of Claude so the browser window can appear:

```bash
python login.py
```

A Chromium window will open. Log in to MyFitnessPal normally. Once you're redirected to your dashboard the session is saved to `playwright-session.json` and the window closes automatically.

You won't need to do this again unless your MFP session expires (typically weeks to months). Just re-run `login.py` if tools start returning auth errors.

## Usage

Once authenticated, just talk to Claude naturally:

- *"What did I eat yesterday?"*
- *"Show me my weight trend over the last 30 days"*
- *"Give me a nutrition summary for last week"*
- *"Search for the nutrition info on Greek yogurt"*
- *"Log my weight as 183.5 lbs today"*

## Why Playwright?

MFP uses Cloudflare bot detection that blocks standard Python HTTP requests (even with valid cookies). Playwright runs a real Chromium browser, which passes the bot checks. The session is saved after login so subsequent calls are headless and fast.

## Files

| File | Purpose |
|------|---------|
| `mfp_server.py` | MCP server — the main entry point |
| `login.py` | Run once from a terminal to authenticate |
| `playwright-session.json` | Saved browser session (**gitignored** — never commit this) |
