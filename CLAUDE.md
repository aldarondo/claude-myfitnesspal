# claude-myfitnesspal

## What This Project Is
MCP connector that bridges Claude to a MyFitnessPal account. Uses Playwright to handle Cloudflare bot detection during login; once authenticated, exposes MCP tools for reading food diaries, body measurements, nutrition summaries, and searching the food database. Supports writing body measurements. Session is saved locally and reused.

## Tech Stack
- Python 3.x
- Playwright (browser automation — handles Cloudflare, session persistence)
- MCP SDK (Model Context Protocol)
- pytest, requirements-dev.txt for dev dependencies
- `playwright-session.json` — persisted session (gitignored)

## Key Decisions
- Playwright chosen specifically to bypass Cloudflare bot detection on MFP login
- Session file is gitignored; re-run `login.py` to regenerate if session expires
- No official MFP API — all data access is via browser automation scraping
- Writing is limited to body measurements (safest write operation)

## Session Startup Checklist
1. Read ROADMAP.md to find the current active task
2. Check MEMORY.md if it exists — it contains auto-saved learnings from prior sessions
3. Verify `playwright-session.json` exists; if missing run `python login.py` to authenticate
4. Run `pip install -r requirements-dev.txt` if dependencies are stale
5. Run `pytest` to verify tests pass before making changes
6. Do not make architectural changes without confirming with Charles first

## Key Files
- `mfp_server.py` — MCP server entry point, tool definitions
- `login.py` — Playwright login flow, saves session JSON
- `tests/` — pytest test suite with browser interaction mocks
- `playwright-session.json` — persisted auth session (gitignored)

---
@~/Documents/GitHub/CLAUDE.md

## Git Rules
- Never create pull requests. Push directly to main.
- solo/auto-push OK
