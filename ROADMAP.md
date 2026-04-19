# claude-myfitnesspal — Roadmap

## Current Milestone
Stable daily-use MCP connector — reliable session handling, all core read tools working

### 🔨 In Progress
[Empty]

### 🟢 Ready (Next Up)

### 📋 Backlog
- [x] `[Code]` 2026-04-19 — Add tool: get_weekly_trends — 7-day calorie + macro averages, per-day vs goal, best/worst day; API call + page-scrape fallback
- Add tool: search exercises / log exercise
- Investigate MFP selector stability — scraping can break on UI changes

### 🔴 Blocked
[Empty]

## ✅ Completed
- Playwright login flow with Cloudflare bypass
- MCP tools: read diary, read measurements, nutrition summary, search foods
- Write tool: log body measurements
- Session persistence via `playwright-session.json`
- pytest test suite with browser interaction mocking
- `session_status()` MCP tool — check session validity before running other tools (2026-04-14)
- Session expiry handling: clear RuntimeError messages in all tools with "Run login.py" instructions (2026-04-14)
- Re-auth documentation in README (Step 3 + note in Usage section) (2026-04-14)
- Fallback path tests for `get_weekly_summary` individual day fetches (2026-04-14)
- Add tool: log food entry — POST to `/api/nutrition` with Playwright page-nav fallback, 8 unit tests (2026-04-19)
