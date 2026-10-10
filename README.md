# Finder — research agents on Hermes

Multi-user web app where AI agents (powered by [Hermes Agent](https://github.com/NousResearch/hermes-agent))
search the internet: digital-medicine research, IT grants with verdicts, or any topic described in a brief.
Interface in Ukrainian, English and German.

## What is inside

| Part | Path | What it does |
|---|---|---|
| API | `backend/app` | FastAPI: accounts, agents, chats (SSE streaming), grants board |
| Hermes bridge | `backend/app/hermes` | one Hermes profile per user, `hermes acp` process per user (JSON-RPC over stdio), provider sign-in via Hermes' own CLI |
| Hermes entry | `backend/hermes_entry/finder_hermes.py` | starts Hermes with the shared-credential fallback disabled, so users never see the server owner's accounts |
| Internet tools | `reach_mcp/` | MCP server `finder-reach`: 17 tools (web search, resilient page fetch, PubMed, Europe PMC, ClinicalTrials.gov, OpenAlex, arXiv, EU Funding & Tenders, Grants.gov, Ukrainian grant sites, YouTube transcripts, GitHub, HN, Reddit, RSS) |
| Skills | `skills/` | Hermes skills copied into every profile: web-reach, medical-research, grant-analyst, source-citation |
| Agent presets | `agents/presets/` | AI in digital medicine · Brief-driven researcher · IT grants analyst |
| UI | `frontend/` | React + Vite + Tailwind 4 + Motion, mint design |

### Sandboxing
Each agent runs in its own Hermes profile with only internet toolsets enabled
(`platform_toolsets.acp`: web, skills, clarify, todo, memory, session_search, vision) and
`terminal`, `file`, `code_execution`, `browser`, `delegation`, `cronjob`, `computer_use` … disabled.
The ACP client advertises no filesystem or terminal capability and refuses every permission request.
Each process gets a sanitized environment and its own `HOME`.

### Charts, documents and images in the chat
The agent still has no disk or shell. Three always-on tools take *content* and the server builds
the result inside a folder that belongs to one chat (`data/artifacts/t<thread>`):

- `create_dashboard` — the agent sends numbers and chart types; the app draws the charts
  (Recharts, validated colour-blind-safe palette, table view for every chart). No agent-written
  HTML or script ever reaches the page.
- `create_document` — markdown → PDF (printed by the shared headless Chrome with JavaScript and
  network disabled), DOCX, Markdown or CSV. The markdown is sanitised first.
- `send_image` — downloads a PNG/JPEG/GIF/WebP from a public URL (type checked by file signature).

Files are served only to the chat's owner (`/api/artifacts/{id}`), with `nosniff` and a sandboxing
CSP. Under a finished answer the chat offers "Show analytics in charts" and "Save report as PDF".

### Getting past blocks
`fetch_page` tries, in order: plain HTTP/2 with browser headers and retries → Chrome TLS
fingerprint impersonation (curl_cffi) → a real headless Chrome (one shared instance per server,
run by the backend at `/internal/render`, reads Shadow DOM too) → Jina Reader → Internet Archive;
DOI links that stay blocked fall back to the OpenAlex record (abstract + open-access copy).
Requests are throttled per host and cached. An outbound proxy can be set with `FINDER_PROXY_URL`.
CAPTCHAs are not solved: such pages are reported as unreachable.

## Run locally (Windows, Hermes already installed)

```bash
cd backend
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.txt
.venv/Scripts/python -m uvicorn app.main:app --port 8100
```

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173, register, then **Accounts** → sign in with ChatGPT/Codex, Nous Portal,
xAI or MiniMax (device code), or add an API key (OpenRouter, Anthropic, OpenAI, Gemini …).

Tests: `cd backend && .venv/Scripts/python -m pytest -q tests`

## Run with Docker

```bash
docker compose up -d --build
```

Open http://localhost:8000. The image is built on `nousresearch/hermes-agent:latest`; all state
(users DB, Hermes profiles, tokens, cache) lives in the `finder-data` volume. Set
`FINDER_SECRET_KEY` and, behind HTTPS, `FINDER_COOKIE_SECURE=true`.

## Deploy to Microsoft Azure

One Linux VM with Docker Compose and Caddy (automatic HTTPS). The script copies the sources to the
VM over SSH and builds the image there, so neither local Docker nor a container registry is
required. See [deploy/azure/README.md](deploy/azure/README.md).

```powershell
.\deploy\azure\deploy.ps1 -ResourceGroup finder-rg -Location denmarkeast -VmSize Standard_B2s -InviteCode "your-code"
```

## Model subscriptions

Signed in per user on the Accounts page: ChatGPT/Codex, Nous Portal, xAI, MiniMax (device code),
Claude Pro/Max (paste the code shown by claude.ai), and — on Linux/Docker only — Google Gemini
through the Antigravity CLI. On Windows the Antigravity session is machine-wide, so it stays
hidden unless `FINDER_ANTIGRAVITY=force` (single-operator installs).

## Configuration (`FINDER_*` environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `FINDER_SECRET_KEY` | generated into the data dir | JWT signing key |
| `FINDER_HERMES_ROOT` | `%LOCALAPPDATA%\hermes` / `/opt/data` | Hermes data root (profiles are created under `profiles/`) |
| `FINDER_HERMES_PYTHON`, `FINDER_HERMES_AGENT_DIR` | asked from `hermes --print-runtime-command` | Hermes interpreter and checkout |
| `FINDER_DATA_DIR` | `./data` | Finder database and cache |
| `FINDER_PROXY_URL` | — | outbound proxy for search tools and Hermes |
| `FINDER_CONTACT_EMAIL` | — | e-mail for NCBI / OpenAlex polite pools |
| `FINDER_ALLOW_REGISTRATION` | `true` | open sign-up |
| `FINDER_INVITE_CODE` | — | when set, registration requires this code |
| `FINDER_AUTH_ATTEMPTS_PER_5MIN` | `20` | login/registration attempts per client address |
| `FINDER_ANTIGRAVITY` | `auto` | Gemini subscription: `auto` (Linux only), `off`, `force` |
| `FINDER_ACP_IDLE_SECONDS` | `900` | stop a user's agent process after this idle time |
| `FINDER_BROWSER` | `auto` | `off` disables the shared headless Chrome (blocked / JavaScript pages) |
| `FINDER_BROWSER_MAX_PAGES` | `3` | pages rendered at once for ALL users; others wait in a queue |
| `FINDER_BROWSER_IDLE_SECONDS` | `120` | close the shared Chrome after this idle time |
