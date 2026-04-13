# claude-myfitnesspal — Roadmap

## Current Milestone
Stable daily-use MCP connector — reliable session handling, all core read tools working

### 🔨 In Progress
[Empty]

### 🟢 Ready (Next Up)
- Verify session auto-refresh or add a re-login prompt when session expires
- Document how to re-authenticate (run `login.py`) in a visible place

### 📋 Backlog
- Add tool: log food entry (currently read-only for diary)
- Add tool: get weekly nutrition trends
- Improve error messages when session is expired vs. network error
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
