# LinkedIn Vault

<div align="center">

[![CI](https://github.com/Supernova1744/linkedin-vault/actions/workflows/ci.yml/badge.svg)](https://github.com/Supernova1744/linkedin-vault/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/github/license/Supernova1744/linkedin-vault)](LICENSE)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![GitHub Stars](https://img.shields.io/github/stars/Supernova1744/linkedin-vault?style=social)](https://github.com/Supernova1744/linkedin-vault/stargazers)
[![Issues](https://img.shields.io/github/issues/Supernova1744/linkedin-vault)](https://github.com/Supernova1744/linkedin-vault/issues)

**Turn your LinkedIn saved posts into a searchable, prioritized knowledge base.**

</div>

LinkedIn Vault scrapes your saved posts via browser automation, enriches each one with an LLM
(summary, topic tags, importance score, freshness check), and stores everything locally in SQLite.
A web dashboard lets you search, filter, and work through your read queue — no cloud sync, no
accounts, no third-party services required.

---

## Features

- **Browser-based scraping** — Playwright drives a real Chromium session; no undocumented API usage
- **LLM enrichment** — summarizes each post, assigns topic tags, scores importance (0–10), and flags outdated content
- **Local-first storage** — all data stays in a single SQLite file on your machine; nothing is sent anywhere
- **Full-text search** — FTS5 index across post content, summaries, and author names
- **Web dashboard** — filter by tag, status, or importance; mark posts read/skipped/saved-for-later
- **Two LLM backends** — [z.ai](https://api.z.ai) (cloud, fast) or [Ollama](https://ollama.ai) (fully local, zero network calls)
- **Interactive TUI** — Textual keyboard-driven interface for first-time setup and daily use
- **CLI interface** — scriptable commands for scraping, enrichment, and stats

---

## Quick Start

### Prerequisites

- Python 3.11 or newer
- A LinkedIn account with saved posts
- Either a [z.ai](https://api.z.ai) API key **or** [Ollama](https://ollama.ai) running locally

### Installation

```bash
git clone https://github.com/Supernova1744/linkedin-vault.git
cd linkedin-vault
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
playwright install chromium
```

### Configuration

**Option A — interactive TUI wizard (recommended)**

```bash
linkedin-vault tui
```

The wizard walks you through selecting an LLM provider, entering your API key, and choosing a
model.  Settings are saved to `~/.linkedin-vault/.env` so they persist across sessions.

**Option B — manual `.env`**

```bash
cp .env.example .env
# Edit .env and fill in the required values
```

---

## Usage

### TUI

```bash
linkedin-vault tui
```

Launches the keyboard-driven Textual interface.  From the home screen you can scrape, enrich,
chat, open the dashboard, and configure settings — all without leaving the terminal.

### CLI Commands

```
linkedin-vault scrape                # Open a browser, log in to LinkedIn, and scrape saved posts
linkedin-vault scrape --headless     # Run without a visible browser window (requires an active session)

linkedin-vault enrich                # Enrich all unenriched posts with LLM analysis
linkedin-vault enrich --limit 10     # Enrich at most 10 posts
linkedin-vault enrich --re-enrich    # Re-run enrichment on already-enriched posts

linkedin-vault models                # List available models for the configured LLM provider

linkedin-vault dashboard             # Start the web dashboard at http://127.0.0.1:8765

linkedin-vault stats                 # Print database statistics to the terminal
```

### Web Dashboard

Navigate to `http://127.0.0.1:8765` after running `linkedin-vault dashboard` (or pressing `d`
in the TUI).

The dashboard provides:

- **Search bar** — full-text search across post content, summaries, and author names
- **Tag filter** — narrow posts by topic (AI, Python, Career, etc.)
- **Status filter** — show only unread, read, skipped, or saved-for-later posts
- **Importance sort** — float high-scoring posts to the top of your reading queue
- **Read queue actions** — mark posts as read, skip, or save for later in one click
- **Chat** — ask questions about your saved posts; answers include citations
- **Stats panel** — total posts, enriched count, and last scrape time

---

## LLM Providers

### z.ai (default)

Sign up at [api.z.ai](https://api.z.ai) and set `ZAI_API_KEY` in your `.env`.
Post content is sent to z.ai's servers for analysis.

Recommended model: `glm-4-flash` (fast and cost-effective).

### Ollama (fully local)

Install [Ollama](https://ollama.ai), pull a model, and start the server:

```bash
ollama pull llama3.2
ollama serve          # runs on http://localhost:11434 by default
```

Then set `LLM_PROVIDER=ollama` in `.env` (or configure via the TUI). Post content never leaves
your machine.

---

## Architecture

```
src/linkedin_vault/
├── cli.py                  Typer CLI entry point (all user-facing commands)
├── config.py               pydantic-settings configuration with .env support
├── db/
│   ├── models.py           Post, SyncState, VaultStats dataclasses
│   ├── database.py         Async SQLite via aiosqlite (upsert, FTS5 search, pagination)
│   └── migrations.sql      Schema DDL with FTS5 virtual table and triggers
├── scraper/
│   ├── browser.py          Playwright session management and scroll loop
│   ├── parser.py           DOM extraction and date parsing (pure functions)
│   └── runner.py           Orchestrates scrape → parse → upsert pipeline
├── enricher/
│   ├── base.py             BaseLLMProvider ABC, EnrichmentResult, retry constants
│   ├── zai.py              z.ai provider (OpenAI-compatible REST)
│   ├── ollama.py           Ollama provider (/api/chat)
│   ├── factory.py          Provider selection based on settings
│   ├── prompt.py           Prompt builder and JSON response parser
│   └── runner.py           Batch enrichment with progress callbacks
├── dashboard/
│   ├── app.py              FastAPI application with lifespan and route definitions
│   ├── schemas.py          Pydantic request/response models
│   ├── server.py           Uvicorn launch wrapper (stoppable from TUI)
│   └── static/             index.html, CSS, and frontend JS
├── chat/
│   ├── retriever.py        FTS5-based post retrieval for chat context
│   ├── synthesiser.py      LLM answer synthesis with citation extraction
│   └── session.py          In-memory chat session store
└── tui/
    ├── app.py              Textual application entry point
    ├── vault_screen.py     Base screen with top/bottom chrome bars
    └── screens/
        ├── welcome.py      Home screen with live stats and action menu
        ├── scrape_screen.py  Scrape progress log
        ├── enrich_screen.py  Enrichment progress log
        ├── chat_screen.py    Interactive chat interface
        ├── login_screen.py   LinkedIn login via Playwright
        └── config_wizard.py  LLM provider and model configuration wizard
```

---

## Development

```bash
make dev-install    # pip install -e ".[dev]" + playwright install chromium
make test           # pytest with coverage
make lint           # ruff check + ruff format --check
make format         # ruff format + ruff check --fix
```

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on reporting bugs, proposing features,
and submitting pull requests.

---

## License

[MIT](LICENSE) — LinkedIn Vault Contributors, 2026
