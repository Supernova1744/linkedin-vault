# LinkedIn Vault

Turn your LinkedIn saved posts into a searchable, LLM-enriched knowledge base.

## What it does

1. **Scrapes** your LinkedIn saved posts via Playwright browser automation
2. **Enriches** each post with an LLM (summary, topic tags, importance score, freshness check)
3. **Stores** everything locally in SQLite — your data never leaves your machine unless you use a cloud LLM
4. **Surfaces** posts through a web dashboard with search, filtering, and a read queue
5. **Configures** via a wizard-style TUI built with Textual

## Quick Start

```bash
# Install
pip install -e ".[dev]"
playwright install chromium

# Configure your LLM provider
linkedin-vault tui  # opens the wizard

# Or copy and edit the example env
cp .env.example .env

# View stats
linkedin-vault stats
```

## Requirements

- Python 3.11+
- Chromium (installed via `playwright install chromium`)
- A LinkedIn account with saved posts
- Either a [z.ai](https://api.z.ai) API key or [Ollama](https://ollama.ai) running locally

## LLM Providers

| Provider | Setup | Privacy |
|----------|-------|---------|
| z.ai (default) | Set `ZAI_API_KEY` in `.env` | Post content sent to z.ai |
| Ollama | Run `ollama serve` locally | Fully local, zero network calls |

## Development

```bash
# Install with dev deps
make dev-install

# Run tests
make test

# Lint
make lint

# Format
make format
```

## Project Structure

```
src/linkedin_vault/
├── cli.py              CLI entry point (Typer)
├── config.py           Settings via pydantic-settings
├── db/
│   ├── models.py       Post, SyncState, VaultStats dataclasses
│   ├── database.py     Async SQLite via aiosqlite
│   └── migrations.sql  Schema DDL with FTS5
├── tui/
│   ├── app.py          Textual application
│   └── screens/
│       ├── welcome.py          Home screen with stats
│       └── config_wizard.py    Provider & model configuration
└── utils/
    └── logging.py      Structured logging via Rich
```

## Roadmap

- **Phase 1** (current): Foundation — db, config, TUI wizard, CLI scaffold
- **Phase 2**: Playwright scraper — login, scroll, extract all saved posts
- **Phase 3**: LLM enrichment pipeline — z.ai + Ollama, batch processing
- **Phase 4**: Web dashboard — FastAPI/HTMX, search, filters, read queue

## License

MIT
