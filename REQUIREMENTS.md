# LinkedIn Vault — Product Requirements & Implementation Blueprint

**Version:** 1.0
**Date:** 2026-06-06
**Status:** Approved for Development
**Prepared by:** Expert Business Analyst
**Intended Audience:** Architect Agent, QA Agent, Security Agent, Open-Source Contributors

---

## Table of Contents

1. [Business Requirements Document (BRD)](#part-1-business-requirements-document-brd)
2. [Functional Requirements Document (FRD)](#part-2-functional-requirements-document-frd)
3. [Phased Implementation Plan](#part-3-phased-implementation-plan)
4. [Recommended Tech Stack](#part-4-recommended-tech-stack)

---

# Part 1: Business Requirements Document (BRD)

---

## 1.1 Executive Summary

LinkedIn Vault is an open-source command-line tool written in Python that solves a universal productivity problem: users curate valuable content by saving LinkedIn posts, but the platform's native saved posts feature provides no way to organize, prioritize, search, or review that content. The result is an ever-growing graveyard of saved-but-never-read material.

LinkedIn Vault automates the extraction of a user's saved posts, enriches each post with LLM-generated intelligence (summary, topic tags, importance score, and freshness assessment), persists everything to a local SQLite database, and exposes the enriched data through both a web dashboard and a terminal user interface (TUI). The tool is built for individual knowledge workers who also happen to be technically proficient — developers, data scientists, and ML practitioners who are comfortable running CLI tools.

---

## 1.2 Business Context & Problem Statement

### The Root Problem

LinkedIn's "saved posts" feature functions as a bookmarking system but with no downstream value delivery mechanism. There is no summarization, no categorization, no prioritization, and no indication of whether saved content is still relevant. Users accumulate hundreds of posts they intended to read, then never do because:

1. **Volume overwhelm**: The list becomes too long to scan without context.
2. **No signal**: Every saved post looks equally important, so none appear urgent.
3. **No freshness signal**: A 3-year-old post about "the future of GPT-2" looks identical to a post saved yesterday.
4. **No search**: LinkedIn's saved posts page provides no full-text search or filtering.

### The Opportunity

The raw material (saved posts) already exists and has been pre-filtered by the user's own curiosity. The gap is purely in processing and presentation. LLM APIs have made summarization, classification, and relevance scoring accessible and cheap. SQLite provides zero-infrastructure persistence. Playwright enables reliable browser automation. These three components, combined with a clean interface, close the gap entirely.

### Why Open Source

The creator is building this for personal use and for the developer community. Making it open source serves two goals: (1) it multiplies the tool's robustness via community contributions, and (2) it establishes credibility as a portfolio project demonstrating clean, production-quality Python engineering.

---

## 1.3 Business Objectives & Success Metrics

| # | Objective | Success Metric | Priority |
|---|-----------|---------------|----------|
| O1 | Enable reliable scraping of all LinkedIn saved posts | 100% of visible saved posts extracted per run; zero silent failures | Must Have |
| O2 | Enrich posts with LLM metadata without manual effort | All scraped posts reach `enrichment_status = completed` within one pipeline run | Must Have |
| O3 | Surface high-value content via importance scoring | User can filter to top-10 posts by importance score in < 5 seconds | Must Have |
| O4 | Prevent waste of time on stale content | `is_outdated = true` posts are visually distinct in the dashboard | Must Have |
| O5 | Support both cloud (z.ai) and local (Ollama) LLM providers | User can switch provider and model with a single config change | Must Have |
| O6 | Attract open-source contributors | Project follows PEP 8, has >80% test coverage, and ships with CONTRIBUTING.md | Should Have |
| O7 | Work without a persistent internet connection for enrichment | Ollama provider path requires zero external network calls | Should Have |

---

## 1.4 Stakeholders & Personas

### Primary Persona — The Overwhelmed Power User

> **Name:** Alex (they/them)
> **Role:** Senior Software Engineer / ML Practitioner
> **Technical Level:** High — comfortable with CLI tools, Python, local LLM tooling
> **Pain:** Has 400+ LinkedIn saved posts. Scans the feed heavily but never revisits saves.
> **Goal:** Spend 20 minutes per week reviewing only the highest-value, non-stale posts.
> **Constraint:** Does not want data in the cloud unless they choose to use a cloud LLM.

### Secondary Persona — The Open-Source Contributor

> **Name:** Sam (he/him)
> **Role:** Junior–Mid-level Python Developer
> **Technical Level:** Medium — knows Python, has used SQLAlchemy and FastAPI, unfamiliar with Playwright or Textual.
> **Goal:** Contribute a feature (e.g., a new LLM provider, an additional dashboard filter) within a weekend.
> **Constraint:** Needs clear architecture, documented interfaces, and passing tests to have confidence their change doesn't break anything.

### Tertiary Stakeholder — The Creator / Maintainer

- Reviews and merges PRs.
- Sets the technical direction.
- The primary user of the tool in production.

---

## 1.5 High-Level Requirements

| ID | Requirement | Category | Priority |
|----|-------------|----------|----------|
| HLR-01 | The system shall automate login to LinkedIn and navigate to the saved posts page | Scraping | Must Have |
| HLR-02 | The system shall extract all saved posts including URL, content, post date, and author | Scraping | Must Have |
| HLR-03 | The system shall deduplicate posts on re-runs (no duplicate rows in DB) | Scraping | Must Have |
| HLR-04 | The system shall enrich each post with a summary, tags, importance score, and is_outdated flag via a configured LLM | Enrichment | Must Have |
| HLR-05 | The system shall support z.ai (Zhipu AI GLM) and Ollama as LLM providers | Enrichment | Must Have |
| HLR-06 | The system shall display available models for the configured provider before enrichment begins | Enrichment | Must Have |
| HLR-07 | The system shall persist all post data (raw + enriched) to a local SQLite database | Storage | Must Have |
| HLR-08 | The system shall expose a web dashboard for browsing, filtering, and searching posts | Dashboard | Must Have |
| HLR-09 | The system shall provide a TUI for running scrape jobs, configuring providers, and viewing status | TUI | Must Have |
| HLR-10 | The system shall be structured for open-source contribution with clean module boundaries | Open Source | Must Have |
| HLR-11 | The system shall not store LinkedIn credentials at rest | Security | Must Have |
| HLR-12 | The system shall store API keys only via environment variables or an encrypted/gitignored config file | Security | Must Have |

---

## 1.6 Constraints

### Technical Constraints

- **Language:** Python 3.11+ (primary language for all backend logic, TUI, and pipeline)
- **Storage:** SQLite only — no external databases, no Docker dependency
- **Scraping:** Playwright for browser automation; no `requests`-based scraping of LinkedIn (too easily blocked)
- **LLM Providers:** z.ai (GLM model family) and Ollama (local) only at v1.0
- **Platform:** Linux, macOS, Windows (WSL2). Pure Python dependencies preferred.
- **Distribution:** PyPI package (`pip install linkedin-vault` or `uv tool install linkedin-vault`)

### Organizational Constraints

- No paid infrastructure. All execution is local.
- No build server at launch (GitHub Actions for CI only, no deployment pipeline).
- Single maintainer at launch.

---

## 1.7 Legal & Ethical Risk Register

> **This section is mandatory reading for the Security Agent.**

This section documents known legal, ethical, and operational risks. These are not implementation details — they are constraints that shape multiple architectural decisions.

| ID | Risk | Severity | Mitigation Required |
|----|------|----------|---------------------|
| LR-01 | **LinkedIn Terms of Service Violation** — Section 8.2 of LinkedIn's User Agreement prohibits automated scraping without explicit permission. Users who run this tool risk account suspension or a cease-and-desist. | **High** | Tool must display a prominent ToS disclaimer on first run and in the README. The scraper must use human-like interaction patterns (randomized scroll delays, no parallel sessions). This is user's risk to accept; the tool must not obscure it. |
| LR-02 | **LinkedIn Anti-Bot Detection** — LinkedIn actively detects and blocks automated browsers via fingerprinting, rate-limiting, and CAPTCHA. | **High** | Playwright browser must run in non-headless mode by default (user can override to headless). Scroll speeds must be randomized within human-plausible ranges. Session cookies must be reused across runs to avoid repeated login triggers. |
| LR-03 | **Credential Exposure** — Storing a LinkedIn password at rest is unacceptable; a breach of the config file would compromise the user's LinkedIn account. | **Critical** | The system MUST NEVER persist the LinkedIn password. Authentication is session-cookie-based after the initial browser login. Cookies are stored in `~/.linkedin-vault/session.json` with `600` file permissions. |
| LR-04 | **LLM API Key Exposure** — z.ai API keys stored in plaintext config files or committed to git would allow unauthorized API usage. | **High** | API keys are read from environment variables (`ZAI_API_KEY`) or a gitignored config file. The project `.gitignore` must explicitly exclude `config.yaml` and `.env`. A secret-scanning CI check must be added. |
| LR-05 | **PII Handling** — The scraped data includes author names, author LinkedIn profile URLs, and post content, which may contain personal information. | **Medium** | Data is stored locally only, never transmitted except to the configured LLM provider for enrichment. README must document what data is sent to external APIs (post content + metadata for z.ai; nothing external for Ollama). |
| LR-06 | **Rate Limiting by z.ai** — Enriching hundreds of posts in a tight loop may hit z.ai's rate limits. | **Medium** | Enrichment pipeline must implement exponential backoff with jitter and a configurable `batch_size`. |

---

## 1.8 Assumptions

> All assumptions must be confirmed or corrected by the maintainer before implementation begins.

- **A-01:** The user's LinkedIn saved posts page URL structure is `https://www.linkedin.com/my-items/saved-posts/`. This URL is assumed stable; if LinkedIn changes it, the scraper selector configuration must be updated.
- **A-02:** z.ai's API is OpenAI-compatible (chat completions at `/api/paas/v4/chat/completions`, Bearer token auth). This is based on confirmed documentation as of 2026-06-06.
- **A-03:** The official z.ai Python SDK (`zai-org/z-ai-sdk-python`) is used as the client library. If it does not expose a synchronous model-listing endpoint, the HTTP API is called directly.
- **A-04:** Ollama is running locally on `http://localhost:11434` and uses the standard `/api/tags` endpoint to list locally installed models.
- **A-05:** The initial tag taxonomy is hardcoded at launch. Community expansion of the taxonomy is a v1.1 concern.
- **A-06:** The web dashboard is served locally only (no auth layer needed at v1.0). Exposing it over a network is out of scope.
- **A-07:** Posts that LinkedIn marks as "unavailable" (deleted by author after saving) are stored with `content = "[Post unavailable]"` and excluded from LLM enrichment.
- **A-08:** "Post date" refers to the date the original post was published on LinkedIn, not the date the user saved it.

---

## 1.9 Out of Scope (v1.0)

- Scraping other content types (articles, videos, newsletters)
- Exporting posts to Notion, Obsidian, or other PKM tools
- Multi-user support or authentication on the dashboard
- Scheduling automated scrape runs (cron integration)
- Support for LLM providers other than z.ai and Ollama
- Mobile interface
- Browser extension

---

# Part 2: Functional Requirements Document (FRD)

---

## 2.1 System Overview

LinkedIn Vault is a locally-hosted Python application comprising five loosely coupled subsystems:

```
┌─────────────────────────────────────────────────────────────────┐
│                        User Interface Layer                      │
│         ┌──────────────────┐     ┌──────────────────────┐      │
│         │  TUI (Textual)   │     │  Web Dashboard        │      │
│         │  Port: N/A (CLI) │     │  FastAPI + React      │      │
│         └────────┬─────────┘     └──────────┬────────────┘      │
└──────────────────┼───────────────────────────┼───────────────────┘
                   │ invokes                   │ HTTP/REST
┌──────────────────▼───────────────────────────▼───────────────────┐
│                      Application Core (Python)                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐   │
│  │   Scraper    │  │  Enrichment  │  │    FastAPI REST API   │   │
│  │  (Playwright)│  │   Pipeline   │  │    (posts CRUD +      │   │
│  └──────┬───────┘  └──────┬───────┘  │     config + stats)  │   │
│         │                 │          └───────────────────────┘   │
│  ┌──────▼─────────────────▼──────────────────────────────────┐   │
│  │                  Repository Layer (SQLAlchemy)              │   │
│  └──────────────────────────┬─────────────────────────────────┘   │
│                             │                                      │
│  ┌──────────────────────────▼─────────────────────────────────┐   │
│  │              SQLite Database (data.db)                       │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │              LLM Provider Abstraction Layer                   │   │
│  │   ┌────────────────────┐   ┌────────────────────────────┐   │   │
│  │   │  z.ai Provider     │   │  Ollama Provider           │   │   │
│  │   │  (GLM models)      │   │  (local models)            │   │   │
│  │   └────────────────────┘   └────────────────────────────┘   │   │
│  └──────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────┘
```

**Architectural Principles:**

1. **Module independence**: Each subsystem (scraper, enrichment, storage, API, TUI) is a Python package with a documented public interface. No subsystem imports another's internals.
2. **Repository pattern**: All database operations go through a repository layer. No raw SQL outside repository classes.
3. **Provider pattern**: LLM providers implement a common abstract interface. Adding a new provider requires only implementing that interface.
4. **Config-driven**: All tuneable parameters (LLM provider, model, scroll speed, batch size) are controlled via config, not hardcoded.
5. **Fail loudly, recover gracefully**: Scraping and enrichment failures are logged with full context, stored in the database (via `enrichment_error` field), and do not halt the pipeline.

---

## 2.2 Feature Area 1: Authentication & Session Management

### FR-AUTH-01: Browser-Based LinkedIn Login

The system shall launch a Playwright-controlled browser window (non-headless by default) and navigate to `https://www.linkedin.com/login`. The user completes login manually. This is intentional — it avoids storing credentials and handles MFA/CAPTCHA naturally.

### FR-AUTH-02: Session Cookie Persistence

Upon successful login detection (URL contains `/feed` or `/my-items`), the system shall:
1. Extract all browser cookies from the LinkedIn domain.
2. Serialize cookies as JSON.
3. Write cookies to `~/.linkedin-vault/session.json` with file permissions `600` (owner read/write only).

### FR-AUTH-03: Session Reuse

On subsequent runs, if `~/.linkedin-vault/session.json` exists:
1. Load cookies and inject them into a new browser context.
2. Navigate to the saved posts URL directly.
3. If LinkedIn redirects to login (session expired), fall back to FR-AUTH-01 and refresh the cookie file.

### FR-AUTH-04: Session Validation

After loading a session, the system navigates to `https://www.linkedin.com/my-items/saved-posts/` and checks for the presence of the saved posts container element. If not found within 10 seconds, treat session as expired.

---

## 2.3 Feature Area 2: Web Scraping Engine

### FR-SCRAPE-01: Navigate to Saved Posts

After authentication, navigate to `https://www.linkedin.com/my-items/saved-posts/`. Wait for the posts container to fully render (wait for network idle or first post element).

### FR-SCRAPE-02: Infinite Scroll Extraction

The saved posts page uses infinite scroll. The system shall:
1. Extract all currently visible posts.
2. Scroll down by a configurable increment (`scroll_increment_px`, default: 800).
3. Wait for a configurable pause (`scroll_pause_ms`, default: 1200–2000ms randomized).
4. Detect page end via: (a) scroll position unchanged after two consecutive scrolls, or (b) a "no more posts" indicator element.
5. Repeat until end of page or `max_posts` limit is reached (null = unlimited).

### FR-SCRAPE-03: Per-Post Data Extraction

For each post element, the system shall extract:

| Field | Source | Required | Notes |
|-------|--------|----------|-------|
| `post_url` | `<a>` element with LinkedIn post permalink | **Yes** | Must validate as a URL; posts without a URL are discarded with a warning |
| `content` | Post text container element | **Yes** | Full text; "see more" must be expanded before extraction |
| `post_date` | Date/time metadata element | **Yes** | Parse relative dates ("2 weeks ago") to absolute datetime using today's date |
| `author_name` | Author name element | **Yes** | Plain text, no markup |
| `author_profile_url` | Author name's `<a>` href | No | LinkedIn profile URL; null if not extractable |

### FR-SCRAPE-04: Unavailable Post Handling

If a post element indicates the post has been deleted or is unavailable:
- Store the record with `content = "[Post unavailable]"` and `enrichment_status = "skipped"`.
- Log a warning with the post URL if available, or position index if not.

### FR-SCRAPE-05: Deduplication

Before inserting a scraped post, check whether `post_url` already exists in the database. If it does:
- Skip insertion.
- Increment a `skipped_duplicates` counter for the run summary.
- Do NOT re-trigger enrichment on the existing record unless explicitly requested via `--re-enrich` flag.

### FR-SCRAPE-06: Run Summary

Upon completion, the system shall output a structured run summary containing:
- Total posts found on page
- New posts inserted
- Duplicates skipped
- Unavailable posts encountered
- Errors (with details)
- Elapsed time

---

## 2.4 Feature Area 3: LLM Enrichment Pipeline

### FR-ENRICH-01: Provider Abstraction Interface

All LLM providers shall implement the following abstract interface:

```python
class LLMProvider(ABC):
    @abstractmethod
    async def list_models(self) -> list[str]: ...

    @abstractmethod
    async def enrich_post(self, post: Post, config: EnrichmentConfig) -> EnrichmentResult: ...
```

This interface is the contract against which both providers and tests operate.

### FR-ENRICH-02: Enrichment Result Schema

The `EnrichmentResult` dataclass (not ORM model) returned by every provider:

```python
@dataclass
class EnrichmentResult:
    summary: str              # 2-4 sentence plain text summary
    tags: list[str]           # 1–5 strings from the tag taxonomy
    importance_score: float   # float in [0.0, 10.0], one decimal place
    is_outdated: bool         # boolean
    raw_response: str         # full LLM response string, for debugging
```

**Testability contract for QA:** The enrichment pipeline validates that each field conforms to its schema constraint before writing to the database. An `EnrichmentValidationError` is raised if:
- `summary` is empty or longer than 2000 characters
- `tags` is an empty list or has more than 5 elements
- `importance_score` is not a float in `[0.0, 10.0]`
- `is_outdated` is not a boolean

QA tests must assert schema conformance, NOT assert specific values. LLM outputs are non-deterministic; tests that assert `importance_score == 7.5` are forbidden.

### FR-ENRICH-03: Structured Output / JSON Mode

The enrichment prompt must request JSON output. The LLM is instructed to return exactly:

```json
{
  "summary": "...",
  "tags": ["...", "..."],
  "importance_score": 7.5,
  "is_outdated": false
}
```

The pipeline shall parse and validate this JSON. If parsing fails (malformed JSON or missing fields), retry up to `max_retries` times with an adjusted prompt. If all retries are exhausted, set `enrichment_status = "failed"` and store the raw response in `enrichment_error`.

### FR-ENRICH-04: z.ai Provider

- **Base URL:** `https://api.z.ai/api/paas/v4/`
- **Auth:** Bearer token from `ZAI_API_KEY` environment variable
- **Model listing:** `GET /models` endpoint; returns list of available model IDs
- **Chat endpoint:** `POST /chat/completions` (OpenAI-compatible)
- **JSON mode:** Set `response_format: {"type": "json_object"}` in the request
- **Default model:** `glm-4.5-flash` (fast, free-tier model; configurable)

### FR-ENRICH-05: Ollama Provider

- **Base URL:** `http://localhost:11434` (configurable)
- **Model listing:** `GET /api/tags` — returns locally installed models; the provider extracts `model.name` from the response array
- **Chat endpoint:** `POST /api/chat` with `stream: false`
- **JSON mode:** Set `format: "json"` in the Ollama request body
- **Default model:** Must be explicitly configured by user (no default; Ollama has no universal model)
- **Pre-flight check:** If Ollama is not reachable at the configured base URL, raise an `OllamaNotAvailableError` with a message guiding the user to start Ollama.

### FR-ENRICH-06: Enrichment Pipeline Execution

1. Query all posts where `enrichment_status = "pending"`.
2. Process in batches of `batch_size` (default: 10).
3. For each post, call `provider.enrich_post()`.
4. On success: update post fields + set `enrichment_status = "completed"`, `enrichment_attempted_at = now()`.
5. On `EnrichmentValidationError`: retry up to `max_retries`. If exhausted, set `enrichment_status = "failed"`, store error.
6. On network/API error: exponential backoff with jitter, up to `max_retries`. Log full error context.
7. On rate-limit (HTTP 429): honour `Retry-After` header if present; otherwise use exponential backoff starting at 5 seconds.
8. Output a live progress indicator (handled by TUI or stdout progress bar).

### FR-ENRICH-07: Model Selection UI

Before enrichment begins (via TUI or CLI command), the system shall:
1. Call `provider.list_models()`.
2. Present the returned list to the user.
3. Allow the user to select a model (or accept the default from config).
4. Store the selected model name in `enrichment_model` on each enriched post record.

---

## 2.5 Feature Area 4: Data Storage

### FR-DB-01: Database Location

The SQLite database is stored at `~/.linkedin-vault/data.db` by default. This path is configurable via `database.path` in the config file.

### FR-DB-02: Schema Migrations

Alembic is used for all schema changes. No schema modification shall be applied by hand. Migration files are version-controlled in `alembic/versions/`. The application runs `alembic upgrade head` automatically on startup.

### FR-DB-03: Post Table Schema

See **Section 2.8 Data Models** for the canonical schema.

### FR-DB-04: Repository Interface

All database operations are encapsulated in a `PostRepository` class:

```python
class PostRepository:
    def insert_post(self, post: PostCreate) -> Post: ...
    def get_post_by_url(self, url: str) -> Post | None: ...
    def get_posts_pending_enrichment(self, limit: int | None = None) -> list[Post]: ...
    def update_enrichment(self, post_id: int, result: EnrichmentResult) -> Post: ...
    def get_all_posts(self, filters: PostFilter) -> list[Post]: ...
    def get_post_by_id(self, post_id: int) -> Post | None: ...
    def get_stats(self) -> DatabaseStats: ...
```

---

## 2.6 Feature Area 5: Web Dashboard

### FR-DASH-01: Technology

The dashboard is a single-page application (React + TypeScript + Tailwind CSS + shadcn/ui components). It is served by a FastAPI backend that exposes a REST API. The frontend is built to `dist/` and served as static files by FastAPI. The dashboard is accessible at `http://localhost:8000` when the server is running.

### FR-DASH-02: Posts List View

The main view displays a paginated table/card list of all posts. Each row/card displays:
- Author name and truncated author profile link
- Post date
- Summary (truncated to 3 lines with "expand" option)
- Tags (as colour-coded badges)
- Importance score (displayed as a numeric badge and a visual bar; colour-coded: ≥7.0 = green, 4.0–6.9 = amber, <4.0 = red)
- Is outdated indicator (a distinct "Outdated" badge if `is_outdated = true`)
- Enrichment status (for posts still `pending` or `failed`, show status badge)
- Link to original LinkedIn post (opens in new tab)

### FR-DASH-03: Filtering

The dashboard shall support simultaneous application of the following filters:
- **By tag:** Multi-select dropdown (shows all tags present in the database with post counts)
- **By importance score:** Range slider (min/max, 0–10)
- **Outdated:** Toggle (show all / hide outdated / show outdated only)
- **Enrichment status:** Dropdown (all / completed / pending / failed / skipped)
- **Date range:** Date-picker for `post_date` from/to

### FR-DASH-04: Search

Full-text search over `content` and `summary` fields. Implemented via SQLite FTS5 virtual table. Results are ranked by relevance. Search is debounced (300ms) in the frontend.

### FR-DASH-05: Post Detail View

Clicking a post opens a side panel (slide-over) or modal displaying:
- Full post content
- Full summary
- All tags
- Importance score with the LLM's implicit reasoning (displayed if available)
- Post date, author, link to original post

### FR-DASH-06: Statistics Panel

A summary panel (collapsible header bar) shows:
- Total posts in database
- Posts enriched / pending / failed
- Most common tags (top 5)
- Average importance score
- Percentage flagged as outdated

### FR-DASH-07: Dashboard Server Lifecycle

The dashboard server is started and stopped via the TUI or the CLI command `linkedin-vault serve`. It must not auto-start on import; it is started on demand.

---

## 2.7 Feature Area 6: Terminal User Interface (TUI)

Built with **Textual**. The TUI provides a full-screen interactive terminal application.

### FR-TUI-01: Main Menu

Top-level navigation with the following options:
- **Scrape** — Run the LinkedIn scraping job
- **Enrich** — Run the LLM enrichment pipeline
- **Serve Dashboard** — Start/stop the web dashboard server
- **Settings** — View and edit configuration
- **Logs** — View recent run logs
- **Quit**

### FR-TUI-02: Scrape Screen

- Shows current config (URL, max posts, headless mode).
- Displays a live progress indicator during scraping (posts found, scrolls completed).
- Shows the run summary upon completion.

### FR-TUI-03: Enrich Screen

- Displays current provider and model from config.
- Shows a model selection list populated from `provider.list_models()`.
- Displays a live progress bar (posts enriched / total pending).
- Shows errors inline (post URL + error message) for failed enrichments.

### FR-TUI-04: Settings Screen

- Displays all configurable options in a form.
- Changes are written to `~/.linkedin-vault/config.yaml`.
- Settings include: provider (zai / ollama), model name, API key (write-only field — displayed as `****`), Ollama base URL, batch size, max retries, scroll speed, headless mode, database path.

### FR-TUI-05: Keyboard Navigation

All screens are fully keyboard-navigable (no mouse required). Standard Textual keybindings apply: Tab/Shift-Tab for focus, Enter to activate, `q` or Escape to go back.

---

## 2.8 Data Models

### 2.8.1 Post Table (`posts`)

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | INTEGER | No | AUTOINCREMENT | Primary key |
| `post_url` | TEXT | No | — | LinkedIn post permalink. UNIQUE index. |
| `content` | TEXT | No | — | Raw post text content. `[Post unavailable]` for deleted posts. |
| `post_date` | DATETIME | Yes | NULL | Original publication date of the post. Nullable if not extractable. |
| `author_name` | TEXT | No | — | Display name of the post author. |
| `author_profile_url` | TEXT | Yes | NULL | LinkedIn profile URL of author. |
| `scraped_at` | DATETIME | No | `CURRENT_TIMESTAMP` | Timestamp when this record was created. |
| `summary` | TEXT | Yes | NULL | LLM-generated 2–4 sentence summary. |
| `tags` | TEXT | Yes | NULL | JSON array of tag strings. e.g. `["AI", "Python"]` |
| `importance_score` | REAL | Yes | NULL | Float in [0.0, 10.0]. LLM-assessed reading value. |
| `is_outdated` | INTEGER | Yes | NULL | SQLite boolean (0/1). LLM-assessed freshness. |
| `enrichment_status` | TEXT | No | `'pending'` | Enum: `pending` \| `processing` \| `completed` \| `failed` \| `skipped` |
| `enrichment_provider` | TEXT | Yes | NULL | Provider used: `zai` or `ollama`. |
| `enrichment_model` | TEXT | Yes | NULL | Model name used for enrichment. |
| `enrichment_error` | TEXT | Yes | NULL | Error message or raw response on failure. |
| `enrichment_attempted_at` | DATETIME | Yes | NULL | Timestamp of last enrichment attempt. |
| `created_at` | DATETIME | No | `CURRENT_TIMESTAMP` | Row creation timestamp. |
| `updated_at` | DATETIME | No | `CURRENT_TIMESTAMP` | Row last-modified timestamp (updated via SQLAlchemy event). |

**Indexes:**
- `UNIQUE INDEX idx_post_url ON posts(post_url)`
- `INDEX idx_enrichment_status ON posts(enrichment_status)`
- `INDEX idx_importance_score ON posts(importance_score)`
- `INDEX idx_post_date ON posts(post_date)`
- `FTS5 VIRTUAL TABLE posts_fts` — indexed on `content, summary` for full-text search

### 2.8.2 Config Schema (`~/.linkedin-vault/config.yaml`)

```yaml
database:
  path: ~/.linkedin-vault/data.db

scraping:
  headless: false            # true to run browser without a visible window
  scroll_pause_ms_min: 1200  # lower bound of randomized scroll pause
  scroll_pause_ms_max: 2000  # upper bound of randomized scroll pause
  scroll_increment_px: 800
  max_posts: null            # integer or null (no limit)

enrichment:
  provider: zai              # zai | ollama
  model: glm-4.5-flash       # model ID string; required for ollama
  batch_size: 10
  max_retries: 3

providers:
  zai:
    api_key: ${ZAI_API_KEY}  # read from environment variable
    base_url: https://api.z.ai/api/paas/v4
  ollama:
    base_url: http://localhost:11434

dashboard:
  host: 127.0.0.1
  port: 8000
```

### 2.8.3 Session Storage (`~/.linkedin-vault/session.json`)

Raw JSON array of Playwright cookie objects. Written with `chmod 600`. Never committed to version control. `.gitignore` must exclude this path pattern.

---

## 2.9 Business Rules

### BR-01: Importance Score Calculation

The LLM is not given an explicit formula; it is given a prompt that guides scoring along four dimensions. These dimensions provide interpretability, not a strict formula, because LLM judgment holistically integrates them:

| Dimension | Weight | Description |
|-----------|--------|-------------|
| Information Depth | 0–3 | Surface observation vs. substantive insight with evidence |
| Actionability | 0–3 | Can the reader apply or act on this directly? |
| Novelty | 0–2 | Is this obvious/common knowledge, or a unique perspective? |
| Relevance | 0–2 | Does this contribute to professional or technical growth? |

The LLM is instructed to return a single float score in `[0.0, 10.0]` that holistically reflects these dimensions. It does not return dimension sub-scores.

**Score interpretation guide (for dashboard display):**
- 8.0–10.0: Must read
- 6.0–7.9: Worth reading when time allows
- 4.0–5.9: Low priority, skim only
- 0.0–3.9: Skip or archive

### BR-02: Is Outdated Assessment

The LLM receives: `{summary}`, `{post_date}`, `{today_date}`. It is instructed to return `true` if it assesses the content as likely stale or superseded by current developments.

**Heuristics provided to the LLM in the prompt:**
- Technology versions mentioned that are now significantly superseded
- Events or deadlines described as upcoming that have already passed
- Statistics, market data, or news that is >18 months old in a fast-moving domain
- Job listings, event registrations, or time-limited offers
- **Evergreen content (design principles, mental models, career advice, algorithms) should generally return `false` even if old**

### BR-03: Tag Taxonomy

The default taxonomy is defined in `linkedin_vault/enrichment/taxonomy.py` as a module-level constant list. It is the source of truth loaded at runtime.

**Initial taxonomy (v1.0):**
`AI`, `LLM`, `NLP`, `Computer Vision`, `Machine Learning`, `Data Science`, `Python`, `Software Engineering`, `Web Development`, `DevOps`, `Security`, `Cloud`, `Databases`, `System Design`, `Open Source`, `Tools & Productivity`, `Career`, `Leadership`, `Research`, `Mathematics`

**LLM tag instruction:** Select 1 to 5 tags from the provided taxonomy. If no tag fits, you may add one new tag that is a concise noun phrase (max 3 words, Title Case). Do not create tags that duplicate existing ones.

### BR-04: Date Parsing for Relative Dates

LinkedIn displays post dates as relative strings ("3 days ago", "2 weeks ago", "4 months ago"). The scraper must convert these to absolute `datetime` objects using `today's date` as the reference point. If the date string is not parseable, `post_date` is stored as `NULL` and a warning is logged.

### BR-05: Deduplication Key

`post_url` is the sole deduplication key. The same post may appear multiple times during scroll (LinkedIn sometimes repeats posts). The `INSERT OR IGNORE` strategy on `post_url` handles this.

---

## 2.10 System Behaviors & State Machine

### Scraping Job State

```
[idle] → (run scrape) → [authenticating] → [navigating] → [scrolling] → [extracting] → [persisting] → [complete]
                                    ↓
                             [session_expired] → [authenticating]
                                    ↓
                             [error] → [complete with errors]
```

### Post Enrichment Status State Machine

```
[pending] → (pipeline picks up) → [processing] → (success) → [completed]
                                         ↓
                                    (LLM error, retries exhausted) → [failed]

[pending] → (post unavailable, no content to enrich) → [skipped]

[failed] → (--re-enrich flag) → [pending] → (pipeline) → [processing] → ...
```

---

## 2.11 Integration Specifications

### z.ai Enrichment Request

**Endpoint:** `POST https://api.z.ai/api/paas/v4/chat/completions`

**Headers:**
```
Authorization: Bearer {ZAI_API_KEY}
Content-Type: application/json
```

**Request body:**
```json
{
  "model": "glm-4.5-flash",
  "response_format": {"type": "json_object"},
  "messages": [
    {
      "role": "system",
      "content": "You are a content analyst. Analyze LinkedIn posts and return structured JSON..."
    },
    {
      "role": "user",
      "content": "Post date: {post_date}\nToday's date: {today_date}\n\nPost content:\n{content}\n\nReturn JSON with fields: summary, tags, importance_score, is_outdated."
    }
  ]
}
```

### Ollama Model Listing Request

**Endpoint:** `GET http://localhost:11434/api/tags`

**Expected response structure:**
```json
{
  "models": [
    {"name": "llama3:8b", "modified_at": "...", "size": 4700000000},
    ...
  ]
}
```

The provider extracts `model["name"]` for each item in `models`.

### Ollama Enrichment Request

**Endpoint:** `POST http://localhost:11434/api/chat`

```json
{
  "model": "llama3:8b",
  "format": "json",
  "stream": false,
  "messages": [...]
}
```

---

## 2.12 Non-Functional Requirements

| ID | Requirement | Target |
|----|-------------|--------|
| NFR-01 | Scraping performance | Full scroll of 500 saved posts completes in < 10 minutes with default settings |
| NFR-02 | Enrichment throughput | Batch of 50 posts enriched in < 5 minutes with z.ai glm-4.5-flash |
| NFR-03 | Dashboard load time | Posts list page loads in < 2 seconds for up to 1000 posts |
| NFR-04 | Test coverage | ≥ 80% line coverage across `scraper`, `enrichment`, `repository`, and `api` packages |
| NFR-05 | Code quality | `ruff check` passes with zero violations; `mypy` passes in strict mode on core packages |
| NFR-06 | Python compatibility | Python 3.11, 3.12, 3.13 |
| NFR-07 | Installation | `pip install linkedin-vault` or `uv tool install linkedin-vault` completes without errors on Linux, macOS, Windows (WSL2) |
| NFR-08 | Documentation | Every public function and class has a docstring. README covers install, usage, and contributing. |

---

# Part 3: Phased Implementation Plan

---

## Phase 1: Foundation

**Goal:** Establish the project scaffold, tooling, configuration management, database schema, and TUI skeleton such that all subsequent phases have a stable base to build on. At the end of Phase 1, a contributor can clone the repo, run `uv sync`, and interact with an empty but fully functional TUI and database.

**Duration estimate:** 1 week

### Phase 1 Deliverables

- `pyproject.toml` with all production and development dependencies declared
- Project package structure: `linkedin_vault/{scraper, enrichment, repository, api, tui, config}/`
- SQLAlchemy models and Alembic migration for the `posts` table
- `PostRepository` class with all methods stubbed (raise `NotImplementedError`) and fully typed
- Config loader using Pydantic Settings (reads `~/.linkedin-vault/config.yaml` + env vars)
- Logging infrastructure (structured JSON log output to `~/.linkedin-vault/logs/`)
- Textual TUI skeleton: main menu, settings screen (read-only), placeholder screens for scrape/enrich/serve
- `linkedin-vault` CLI entry point registered in `pyproject.toml`
- GitHub Actions CI: `ruff`, `mypy`, `pytest` on push/PR (Python 3.11, 3.12, 3.13)
- `.gitignore`, `LICENSE` (MIT), `CONTRIBUTING.md` stub

### Phase 1 User Stories

---

**Story P1-01: Project Scaffold**

> As a contributor, I want a standard Python project layout with dependency management so that I can start contributing without manual environment setup.

**Acceptance Criteria:**

*Scenario 1 (Happy path — fresh install)*
```
Given a machine with Python 3.11+ and uv installed
When I run `uv sync` in the project root
Then all dependencies install without errors
And `linkedin-vault --help` outputs the CLI help text
```

*Scenario 2 (CI gate)*
```
Given a pull request is opened against main
When GitHub Actions runs
Then ruff lint, mypy type checks, and pytest all pass
And the pipeline completes in under 5 minutes
```

---

**Story P1-02: Database Schema & Repository**

> As a developer, I want a SQLite database with a versioned schema so that I can store posts reliably and roll back schema changes during development.

**Acceptance Criteria:**

*Scenario 1 (Happy path — first run)*
```
Given no database file exists at the configured path
When the application initializes
Then Alembic runs `upgrade head` automatically
And the `posts` table is created with all columns defined in the FRD
And an index exists on `post_url`, `enrichment_status`, `importance_score`, and `post_date`
```

*Scenario 2 (Deduplication)*
```
Given a post with URL "https://linkedin.com/posts/test-123" already exists in the database
When `PostRepository.insert_post()` is called with a post having the same URL
Then no new row is inserted
And the existing row is unchanged
And the method returns the existing post object
```

*Scenario 3 (Schema migration)*
```
Given a database at migration version N
When a new migration file is added and the app starts
Then `alembic upgrade head` applies the migration without data loss
```

---

**Story P1-03: Configuration Management**

> As a user, I want to configure LinkedIn Vault via a YAML file so that I can set my LLM provider, model, and scraping preferences once and have them persist across runs.

**Acceptance Criteria:**

*Scenario 1 (Happy path — config file)*
```
Given a valid `~/.linkedin-vault/config.yaml` exists
When the application starts
Then config values are loaded correctly
And provider, model, batch_size, and database path reflect the file values
```

*Scenario 2 (Environment variable override)*
```
Given `ZAI_API_KEY=test-key-123` is set in the environment
And config.yaml does not define an API key
When the application loads config
Then `config.providers.zai.api_key` equals "test-key-123"
```

*Scenario 3 (Missing required config)*
```
Given `enrichment.provider = "ollama"` is set
And `enrichment.model` is not set
When the enrichment pipeline attempts to start
Then an error is raised: "Ollama requires an explicit model to be configured. Run `linkedin-vault settings` to set one."
```

*Scenario 4 (Default config on first run)*
```
Given no config file exists
When the application starts for the first time
Then a default config file is written to `~/.linkedin-vault/config.yaml`
And the user is notified of the file location
```

---

**Story P1-04: TUI Main Menu**

> As a user, I want a terminal-based main menu so that I can navigate between the scrape, enrich, serve, settings, and logs functions without memorizing CLI flags.

**Acceptance Criteria:**

*Scenario 1 (Happy path — launch)*
```
Given the application is installed
When I run `linkedin-vault tui`
Then a full-screen Textual application opens
And I can see menu options: Scrape, Enrich, Serve Dashboard, Settings, Logs, Quit
```

*Scenario 2 (Keyboard navigation)*
```
Given the TUI is open on the main menu
When I press the down arrow key twice
Then focus moves to the third menu item
When I press Enter
Then the corresponding screen opens
When I press Escape
Then I return to the main menu
```

*Scenario 3 (Settings read display)*
```
Given a config file exists with provider = "zai" and model = "glm-4.5-flash"
When I navigate to the Settings screen
Then I see "Provider: zai" and "Model: glm-4.5-flash" displayed
And the API key field shows "****" (masked)
```

---

**Phase 1 Dependencies:** None. This phase has no dependencies on other phases.

---

## Phase 2: Scraper

**Goal:** Implement the full LinkedIn authentication and saved-posts scraping pipeline. At the end of Phase 2, a user can run `linkedin-vault scrape`, log into LinkedIn via a browser window, and have all their saved posts extracted and stored in the database (without enrichment).

**Duration estimate:** 1.5–2 weeks

### Phase 2 Deliverables

- `linkedin_vault/scraper/` package: `browser.py` (Playwright lifecycle), `auth.py` (login + session management), `extractor.py` (post extraction logic), `models.py` (scraped post dataclass)
- Session cookie persistence to `~/.linkedin-vault/session.json` (chmod 600)
- Relative-date parser utility (`linkedin_vault/utils/date_parser.py`)
- Full `PostRepository` methods implemented (insert, deduplicate)
- `linkedin-vault scrape` CLI command
- Scrape screen in TUI (live progress + run summary)
- Integration test using Playwright's `--save-storage` / mock HTML fixture (no real LinkedIn credentials in CI)
- Prominent ToS disclaimer printed on first-ever scrape run

### Phase 2 User Stories

---

**Story P2-01: LinkedIn Authentication**

> As a user, I want to log into LinkedIn via a browser window so that the tool can access my saved posts without storing my password.

**Acceptance Criteria:**

*Scenario 1 (Happy path — fresh login)*
```
Given no session file exists at `~/.linkedin-vault/session.json`
When I run `linkedin-vault scrape`
Then the tool displays the ToS disclaimer and waits for acknowledgement
And a Chromium browser window opens at the LinkedIn login page
And I can type my credentials and complete MFA normally
When the browser URL contains "/feed" or "/my-items"
Then the tool detects successful login
And saves cookies to `~/.linkedin-vault/session.json` with permissions 600
And proceeds to navigate to the saved posts page
```

*Scenario 2 (Session reuse)*
```
Given a valid session file exists
When I run `linkedin-vault scrape`
Then no browser login page is shown
And the tool navigates directly to the saved posts page
```

*Scenario 3 (Session expiry)*
```
Given an expired session file exists
When the tool attempts to navigate to saved posts
And LinkedIn redirects to the login page
Then the tool detects the redirect
And opens a browser window for re-authentication
And overwrites the old session file with fresh cookies upon success
```

---

**Story P2-02: Saved Posts Extraction**

> As a user, I want the tool to automatically scroll through my LinkedIn saved posts and extract all of them so that I have a complete local copy of my curated content.

**Acceptance Criteria:**

*Scenario 1 (Happy path — full scroll)*
```
Given I am authenticated and on the saved posts page
When the scraper runs with max_posts = null
Then the tool scrolls to the bottom of the page with randomized pauses between 1200ms and 2000ms
And each post's URL, content, post_date, and author_name are extracted
And all extracted posts are inserted into the database
And the run summary reports total posts found, new posts inserted, and duplicates skipped
```

*Scenario 2 (Deduplication on re-run)*
```
Given 50 posts already exist in the database from a previous scrape
When I run `linkedin-vault scrape` again
And the saved posts page contains the same 50 posts plus 5 new ones
Then 5 new rows are inserted
And 50 rows are skipped (duplicate)
And the run summary shows "New: 5, Skipped: 50"
```

*Scenario 3 (Unavailable post)*
```
Given a saved post has been deleted by its author
When the scraper encounters the unavailable post element
Then it stores a record with content = "[Post unavailable]" and enrichment_status = "skipped"
And it logs a warning with the post's position index
And it continues to the next post without stopping
```

*Scenario 4 (max_posts limit)*
```
Given max_posts = 100 is configured
When the scraper starts scrolling
Then it stops after extracting 100 posts even if more posts exist below
And the run summary notes that the limit was reached
```

---

**Story P2-03: ToS Disclaimer**

> As a user, I want to be informed of LinkedIn's Terms of Service risk before my first scrape so that I can make an informed decision about using the tool.

**Acceptance Criteria:**

*Scenario 1 (First run)*
```
Given the tool has never been run on this machine (no `~/.linkedin-vault/` directory)
When I run any scrape command
Then the tool displays a disclaimer stating that browser automation may violate LinkedIn's Terms of Service
And it requires explicit acknowledgement (type "yes" or press a TUI button) before proceeding
And after acknowledgement, a flag file is written so the disclaimer is not shown again
```

*Scenario 2 (Subsequent runs)*
```
Given the disclaimer has been previously acknowledged
When I run `linkedin-vault scrape`
Then the disclaimer is NOT shown
And scraping begins immediately
```

---

**Phase 2 Dependencies:** Phase 1 (database schema, config management, repository, TUI skeleton).

---

## Phase 3: LLM Enrichment

**Goal:** Implement the LLM enrichment pipeline with both z.ai and Ollama providers, model selection UX, and all business rules for summary, tags, importance score, and is_outdated. At the end of Phase 3, a user with either a z.ai API key or a local Ollama installation can enrich all pending posts with a single command.

**Duration estimate:** 1.5–2 weeks

### Phase 3 Deliverables

- `linkedin_vault/enrichment/` package: `interface.py` (abstract base), `zai_provider.py`, `ollama_provider.py`, `pipeline.py`, `prompts.py`, `taxonomy.py`, `validator.py`
- `EnrichmentResult` dataclass and `EnrichmentValidationError`
- z.ai provider with model listing, JSON-mode chat, retry/backoff
- Ollama provider with model listing, pre-flight connectivity check, JSON-mode chat, retry/backoff
- Enrichment pipeline with batch processing, live progress, and error recording
- `linkedin-vault enrich` CLI command with `--provider`, `--model`, `--re-enrich` flags
- Enrich screen in TUI (model selection list, live progress bar, inline error display)
- Unit tests for `EnrichmentValidator`, `date_parser`, prompt construction
- Integration test stubs (mock HTTP for providers)

### Phase 3 User Stories

---

**Story P3-01: z.ai Enrichment**

> As a user with a z.ai API key, I want to enrich my scraped posts using a GLM model so that each post gets a summary, tags, importance score, and freshness assessment automatically.

**Acceptance Criteria:**

*Scenario 1 (Happy path — enrichment succeeds)*
```
Given 10 posts with enrichment_status = "pending" exist in the database
And ZAI_API_KEY is set in the environment
And provider = "zai" and model = "glm-4.5-flash" are configured
When I run `linkedin-vault enrich`
Then the pipeline calls the z.ai chat completions endpoint for each post
And each response is parsed for the JSON fields: summary, tags, importance_score, is_outdated
And each post is updated in the database with the enrichment fields
And enrichment_status is set to "completed" for all successfully enriched posts
And enrichment_model is set to "glm-4.5-flash" for each post
```

*Scenario 2 (Rate limit handling)*
```
Given a z.ai API call returns HTTP 429 with a Retry-After header of 5 seconds
When the pipeline receives this response
Then it pauses for at least 5 seconds before retrying
And the retry succeeds
And the post is marked as "completed"
```

*Scenario 3 (Invalid API key)*
```
Given ZAI_API_KEY is set to an invalid value
When the pipeline attempts to enrich the first post
Then it receives HTTP 401 from z.ai
And it immediately aborts the enrichment run (does not retry on 401)
And it outputs a clear error: "Invalid z.ai API key. Set ZAI_API_KEY environment variable."
And no posts are marked as "failed" (they remain "pending" for future retry)
```

*Scenario 4 (Malformed LLM response)*
```
Given the LLM returns a response that is not valid JSON
When the pipeline attempts to parse the response
Then it retries the request up to max_retries times
If all retries produce unparseable responses
Then the post is marked enrichment_status = "failed"
And the raw response is stored in enrichment_error
And the pipeline continues to the next post
```

---

**Story P3-02: Ollama Enrichment**

> As a user who prefers local processing, I want to enrich my posts using a locally running Ollama model so that no post content is sent to an external server.

**Acceptance Criteria:**

*Scenario 1 (Happy path — Ollama running with model available)*
```
Given Ollama is running at localhost:11434
And the model "llama3:8b" is installed locally
And provider = "ollama" and model = "llama3:8b" are configured
When I run `linkedin-vault enrich`
Then the pipeline calls POST http://localhost:11434/api/chat for each post
And each post is enriched and marked as "completed"
And enrichment_provider = "ollama" and enrichment_model = "llama3:8b" are stored
```

*Scenario 2 (Ollama not running)*
```
Given no service is listening on localhost:11434
When I run `linkedin-vault enrich` with provider = "ollama"
Then the pipeline immediately raises OllamaNotAvailableError
And outputs: "Ollama is not running. Start it with `ollama serve` and try again."
And no posts are modified
```

---

**Story P3-03: Model Selection**

> As a user, I want to see a list of available models for my configured provider before enrichment starts so that I can choose the most appropriate model.

**Acceptance Criteria:**

*Scenario 1 (z.ai model list)*
```
Given provider = "zai" is configured
And ZAI_API_KEY is valid
When I start the enrich workflow (TUI or CLI with --select-model flag)
Then the tool fetches the model list from z.ai's /models endpoint
And displays the list of available model IDs
And I can select one before enrichment begins
```

*Scenario 2 (Ollama model list)*
```
Given provider = "ollama" and Ollama is running with 3 models installed
When I start the enrich workflow
Then the tool fetches GET /api/tags from Ollama
And displays the 3 model names
And I can select one
```

*Scenario 3 (Default model acceptance)*
```
Given a model is configured in config.yaml
When I start enrichment without the --select-model flag
Then enrichment proceeds with the configured model immediately
And model selection UI is skipped
```

---

**Story P3-04: Enrichment Validation**

> As a developer, I want all LLM enrichment outputs to be schema-validated before being written to the database so that data quality is guaranteed regardless of which model produced the output.

**Acceptance Criteria:**

*Scenario 1 (Valid output)*
```
Given an EnrichmentResult with summary = "Valid text", tags = ["AI"], importance_score = 7.5, is_outdated = False
When EnrichmentValidator.validate() is called
Then no exception is raised
And the result passes through unchanged
```

*Scenario 2 (Score out of range)*
```
Given an EnrichmentResult with importance_score = 11.0
When EnrichmentValidator.validate() is called
Then EnrichmentValidationError is raised with message indicating score must be in [0.0, 10.0]
```

*Scenario 3 (Too many tags)*
```
Given an EnrichmentResult with 7 tags in the tags list
When EnrichmentValidator.validate() is called
Then EnrichmentValidationError is raised with message indicating max 5 tags are allowed
```

---

**Phase 3 Dependencies:** Phase 1 (config, database, repository), Phase 2 (posts exist in DB to enrich).

---

## Phase 4: Dashboard

**Goal:** Build and integrate the web dashboard. At the end of Phase 4, a user can run `linkedin-vault serve`, open `http://localhost:8000`, and browse, filter, search, and read all their enriched posts in a polished web UI.

**Duration estimate:** 2–2.5 weeks

### Phase 4 Deliverables

- `linkedin_vault/api/` package: `main.py` (FastAPI app), `routers/posts.py`, `routers/stats.py`, `schemas.py` (Pydantic response models)
- SQLite FTS5 virtual table migration for full-text search
- React + TypeScript + Tailwind CSS + shadcn/ui frontend in `frontend/`
- `frontend/src/` components: `PostList`, `PostCard`, `PostDetail`, `FilterPanel`, `SearchBar`, `StatsBar`, `TagBadge`, `ImportanceBadge`
- Built frontend served as static files from `linkedin_vault/api/static/`
- `linkedin-vault serve` CLI command (starts FastAPI server, opens browser)
- Serve screen in TUI (start/stop server, show URL)
- API endpoint documentation (auto-generated via FastAPI + OpenAPI)
- Playwright e2e tests covering: post list renders, filter by tag works, search returns results

### Phase 4 REST API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/posts` | List posts with optional filters (query params: `tags`, `min_score`, `max_score`, `is_outdated`, `status`, `date_from`, `date_to`, `search`, `page`, `page_size`) |
| GET | `/api/posts/{id}` | Get a single post by ID |
| GET | `/api/tags` | List all distinct tags with post counts |
| GET | `/api/stats` | Get database summary statistics |
| POST | `/api/posts/{id}/re-enrich` | Re-queue a post for enrichment (sets status to "pending") |

### Phase 4 User Stories

---

**Story P4-01: Posts List with Filters**

> As a user, I want to browse my enriched posts in a web dashboard with filtering by tag, importance score, and freshness so that I can focus on the highest-value, most relevant content.

**Acceptance Criteria:**

*Scenario 1 (Initial load)*
```
Given the dashboard server is running and posts exist in the database
When I navigate to http://localhost:8000
Then the posts list renders within 2 seconds
And each post card displays: author name, post date, summary (truncated), tags, importance score badge, outdated indicator (if applicable)
```

*Scenario 2 (Filter by tag)*
```
Given posts with tags ["AI", "Python", "Career"] exist in the database
When I select "AI" in the tag filter
Then only posts tagged with "AI" are displayed
And the post count updates to reflect the filtered result
```

*Scenario 3 (Filter by importance score)*
```
Given I set the importance score range slider to min=7.0 and max=10.0
Then only posts with importance_score >= 7.0 are displayed
And posts below 7.0 are hidden
```

*Scenario 4 (Outdated toggle)*
```
Given I toggle "Hide outdated posts"
Then posts where is_outdated = true are removed from the list
When I toggle back to "Show all"
Then all posts are visible again
```

---

**Story P4-02: Full-Text Search**

> As a user, I want to search across post content and summaries so that I can find posts on a specific topic without scrolling through the entire list.

**Acceptance Criteria:**

*Scenario 1 (Happy path)*
```
Given posts containing the word "transformer" in either content or summary
When I type "transformer" in the search box
Then after 300ms debounce
Then only posts matching "transformer" are displayed
And matched terms are highlighted in the result
```

*Scenario 2 (No results)*
```
Given no posts contain the search term "zxqwerty"
When I type "zxqwerty" in the search box
Then a "No posts found matching your search" message is displayed
And the filter panel remains visible
```

*Scenario 3 (Search combined with filters)*
```
Given I have filtered to tag = "AI" and search = "fine-tuning"
Then only posts tagged "AI" AND containing "fine-tuning" are shown
```

---

**Story P4-03: Post Detail View**

> As a user, I want to click a post and see its full content and enrichment details in a detail panel so that I can read without leaving the dashboard.

**Acceptance Criteria:**

*Scenario 1 (Happy path)*
```
Given the posts list is displayed
When I click on a post card
Then a slide-over panel opens on the right
And it displays: full content (not truncated), full summary, all tags, importance score, is_outdated status, post date, author name, and a link to the original LinkedIn post
```

*Scenario 2 (Link to original)*
```
Given a post detail panel is open
When I click "View on LinkedIn"
Then the original LinkedIn post URL opens in a new browser tab
```

---

**Story P4-04: Statistics Panel**

> As a user, I want a high-level summary of my vault at the top of the dashboard so that I can understand my collection at a glance.

**Acceptance Criteria:**

*Scenario 1 (Stats display)*
```
Given the dashboard is loaded and 200 posts exist (150 enriched, 40 pending, 10 failed)
When the stats bar renders
Then I see: "200 posts | 150 enriched | 40 pending | 10 failed | 35% outdated | Avg score: 6.2"
And the top 5 tags are shown as clickable badges that apply a filter when clicked
```

---

**Phase 4 Dependencies:** Phase 1 (config, DB), Phase 2 (posts in DB), Phase 3 (enriched posts). Dashboard is read-only; it does not require enrichment to be complete, but enrichment data improves its utility.

---

## Phase 5: Polish & Open-Source Readiness

**Goal:** Elevate the codebase to production-quality, contributor-ready open-source standard. At the end of Phase 5, the project can be published on PyPI and announced to the community.

**Duration estimate:** 1–1.5 weeks

### Phase 5 Deliverables

- Test coverage ≥ 80% across all core packages (`pytest-cov` report in CI)
- `mypy` strict mode passing on all packages
- `ruff` format + lint with zero violations
- `pytest-asyncio` suite for all async functions
- Playwright e2e test suite against mock LinkedIn HTML fixtures (no real credentials in CI)
- `README.md`: project overview, demo GIF/screenshot, installation, quickstart, configuration reference, LLM provider setup guides, FAQ (ToS risk, Ollama setup, z.ai setup)
- `CONTRIBUTING.md`: development environment setup, code standards, how to add a new LLM provider, PR checklist
- `CHANGELOG.md`
- GitHub issue templates (bug report, feature request)
- GitHub PR template
- `.github/workflows/ci.yml`: lint + type check + test on push/PR, matrix Python 3.11/3.12/3.13
- `.github/workflows/publish.yml`: build + publish to PyPI on git tag
- `gitleaks` or `detect-secrets` GitHub Action step for secret scanning
- `SECURITY.md`: responsible disclosure policy

### Phase 5 User Stories

---

**Story P5-01: Test Coverage Gate**

> As a maintainer, I want a CI gate that enforces ≥80% test coverage so that contributors cannot merge code that leaves critical logic untested.

**Acceptance Criteria:**

*Scenario 1 (Coverage passes)*
```
Given a PR is opened with coverage at 82%
When the CI pipeline runs
Then the coverage check passes
And the PR can be merged
```

*Scenario 2 (Coverage fails)*
```
Given a PR adds a new module with no tests, dropping coverage to 71%
When the CI pipeline runs
Then the coverage check fails with: "Coverage 71% is below the required 80% threshold."
And the PR cannot be merged until coverage is restored
```

---

**Story P5-02: New Provider Contribution Path**

> As an open-source contributor, I want a documented, testable interface for adding a new LLM provider so that I can contribute a new provider (e.g., OpenAI, Anthropic) in a weekend without needing to understand the full codebase.

**Acceptance Criteria:**

*Scenario 1 (Interface compliance)*
```
Given a new class `OpenAIProvider` that implements `LLMProvider`
When the test suite runs `test_provider_contract(OpenAIProvider)`
Then all interface contract tests pass (list_models returns list[str], enrich_post returns EnrichmentResult)
Without needing to make real API calls (provider tests use httpx mock)
```

*Scenario 2 (Contributing docs)*
```
Given I read CONTRIBUTING.md
Then the "Adding a New LLM Provider" section walks me through:
1. Creating the provider class in linkedin_vault/enrichment/
2. Registering it in the provider registry
3. Adding config schema fields
4. Running the contract test
And I can complete all steps without asking the maintainer a question
```

---

**Story P5-03: PyPI Publication**

> As a user, I want to install LinkedIn Vault with a single pip command so that there is no need to clone the repository or manage a virtual environment manually.

**Acceptance Criteria:**

*Scenario 1 (Install from PyPI)*
```
Given Python 3.11+ is installed
When I run `pip install linkedin-vault`
Then the package installs successfully
And `linkedin-vault --help` is available in PATH
And `linkedin-vault tui` launches the Textual TUI
```

*Scenario 2 (Version tag triggers publish)*
```
Given I push a git tag `v1.0.0` to GitHub
When the publish GitHub Action runs
Then it builds the wheel and sdist
And publishes to PyPI using a stored API token
And the package is available at `pypi.org/project/linkedin-vault`
```

---

**Phase 5 Dependencies:** All previous phases (polishing what has been built).

---

# Part 4: Recommended Tech Stack

---

## 4.1 Technology Decisions Table

| Component | Technology | Version | Justification |
|-----------|------------|---------|---------------|
| Language | Python | 3.11+ | Specified by the creator. Dominant language for AI/ML tooling; largest potential contributor base. 3.11+ required for performance improvements and `tomllib` stdlib inclusion. |
| Package Manager | uv | latest | Dramatically faster than pip; first-class `pyproject.toml` support; emerging standard for Python AI projects. `uv tool install` for zero-setup distribution. |
| Browser Automation | Playwright (Python) | 1.44+ | Specified. More reliable than Selenium for modern SPAs; supports async; built-in stealth-resistance vs. basic detection. |
| ORM | SQLAlchemy | 2.x | Industry-standard Python ORM. 2.x async-first API. Repository pattern is well-supported. Core (not ORM) can be used for raw SQL when needed. |
| Migrations | Alembic | 1.x | The standard Alembic + SQLAlchemy pairing. Auto-generates migration scripts from model changes. Zero-infrastructure. |
| TUI | Textual | 0.x (latest) | **Chosen over curses, rich alone, or click-based CLIs.** Textual provides a full reactive widget system (CSS-styled, composable) that is dramatically more capable than raw curses or rich. It is the current-generation Python TUI standard. It produces interfaces that are contributor-readable without TUI expertise. |
| API Framework | FastAPI | 0.11x | Async, auto-generates OpenAPI docs, Pydantic integration is seamless with the existing data models. Minimal boilerplate. Standard choice for Python REST APIs. |
| Frontend | React 18 + TypeScript | 18.x / 5.x | **Decision: React over Streamlit/Gradio.** The "clean, elegant" requirement rules out Streamlit (functional but visually limited). React with shadcn/ui produces a polished component-level UI. The Node.js build requirement adds friction for Python-only contributors, but the API-first architecture (FastAPI REST API) means backend contributors never need to touch the frontend. The frontend is an isolated `frontend/` directory with its own README. |
| UI Component Library | shadcn/ui | latest | Accessible, unstyled Radix primitives styled with Tailwind. Components are copied into the project (not a dependency), which means contributors can modify them directly. Produces visually polished results with minimal custom CSS. |
| CSS | Tailwind CSS | 3.x | Utility-first, no naming convention decisions for contributors. Works seamlessly with shadcn/ui. |
| Frontend Bundler | Vite | 5.x | Fastest dev server for React projects. `vite build` produces the `dist/` folder served by FastAPI. |
| HTTP Client | httpx | 0.27+ | Async-first HTTP client for Python. Used for z.ai and Ollama API calls. Consistent interface with both sync and async support; `httpx.AsyncClient` drops cleanly into async enrichment pipeline. |
| z.ai SDK | zai-org/z-ai-sdk-python OR direct httpx | latest | The official SDK is used if it exposes async model listing; otherwise direct httpx calls against the OpenAI-compatible endpoint. The provider implementation must abstract this detail. |
| Config | Pydantic Settings | 2.x | Reads from YAML + environment variables with type validation. Pydantic v2 performance is a significant improvement. Eliminates hand-written config parsing. |
| Logging | structlog | 23.x+ | Structured JSON log output. Each log entry carries context (run_id, post_url, provider). Makes logs machine-parseable for future analytics. |
| Testing | pytest + pytest-asyncio + pytest-cov | latest | Standard Python test stack. `pytest-asyncio` for async enrichment pipeline tests. `pytest-cov` for coverage gating in CI. |
| Mock HTTP | pytest-httpx | latest | Mock `httpx` calls in unit tests. Required for provider unit tests (no real API calls in CI). |
| Browser Test | Playwright test runner | 1.44+ | Playwright's own Python test integration for e2e dashboard tests. Uses fixture-based HTML for LinkedIn scraper tests (no real credentials). |
| Linter / Formatter | ruff | 0.4+ | Replaces both flake8 and isort. Fastest Python linter; single tool. Includes formatter (`ruff format`) that replaces black. One dependency, one config section in `pyproject.toml`. |
| Type Checker | mypy | 1.x | Strict mode enforced on core packages. Ensures the `LLMProvider` interface contract is statically verifiable. |
| CI | GitHub Actions | N/A | Standard for open-source Python. Matrix testing across Python 3.11/3.12/3.13. Free for public repos. |
| Secret Scanning | gitleaks | 8.x | Runs in CI on every push. Catches accidentally committed API keys before they are public. Zero-config for common patterns (API keys, tokens). |

---

## 4.2 Project Directory Structure

```
linkedin-vault/
├── pyproject.toml               # All deps, build config, tool config (ruff, mypy, pytest)
├── README.md
├── CONTRIBUTING.md
├── CHANGELOG.md
├── SECURITY.md
├── LICENSE                      # MIT
├── .gitignore                   # Includes: .env, config.yaml, session.json, *.db, dist/, node_modules/
├── alembic/
│   ├── alembic.ini
│   └── versions/
│       └── 0001_initial_schema.py
├── linkedin_vault/              # Main Python package
│   ├── __init__.py
│   ├── cli.py                   # CLI entry point (click or typer)
│   ├── config/
│   │   ├── __init__.py
│   │   ├── schema.py            # Pydantic Settings model
│   │   └── loader.py            # Load from ~/.linkedin-vault/config.yaml
│   ├── repository/
│   │   ├── __init__.py
│   │   ├── database.py          # SQLAlchemy engine + session factory
│   │   ├── models.py            # SQLAlchemy ORM models
│   │   └── post_repository.py   # PostRepository class
│   ├── scraper/
│   │   ├── __init__.py
│   │   ├── browser.py           # Playwright browser lifecycle
│   │   ├── auth.py              # Login + session cookie management
│   │   ├── extractor.py         # Post element extraction
│   │   └── models.py            # ScrapedPost dataclass (pre-DB)
│   ├── enrichment/
│   │   ├── __init__.py
│   │   ├── interface.py         # LLMProvider ABC
│   │   ├── zai_provider.py      # z.ai / Zhipu AI implementation
│   │   ├── ollama_provider.py   # Ollama implementation
│   │   ├── pipeline.py          # Batch enrichment orchestration
│   │   ├── prompts.py           # Prompt templates
│   │   ├── taxonomy.py          # Tag taxonomy constant
│   │   ├── validator.py         # EnrichmentResult schema validation
│   │   └── models.py            # EnrichmentResult dataclass
│   ├── api/
│   │   ├── __init__.py
│   │   ├── main.py              # FastAPI app factory
│   │   ├── schemas.py           # Pydantic response/request models
│   │   ├── routers/
│   │   │   ├── posts.py
│   │   │   └── stats.py
│   │   └── static/              # Built React frontend (gitignored, built at package time)
│   ├── tui/
│   │   ├── __init__.py
│   │   ├── app.py               # Textual App class
│   │   └── screens/
│   │       ├── main_menu.py
│   │       ├── scrape.py
│   │       ├── enrich.py
│   │       ├── serve.py
│   │       ├── settings.py
│   │       └── logs.py
│   └── utils/
│       ├── __init__.py
│       └── date_parser.py       # Relative → absolute date parser
├── frontend/                    # React app (built output goes to linkedin_vault/api/static/)
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── api/                 # API client functions
│       └── components/
│           ├── PostList.tsx
│           ├── PostCard.tsx
│           ├── PostDetail.tsx
│           ├── FilterPanel.tsx
│           ├── SearchBar.tsx
│           ├── StatsBar.tsx
│           └── ui/              # shadcn/ui components
└── tests/
    ├── unit/
    │   ├── test_validator.py
    │   ├── test_date_parser.py
    │   ├── test_repository.py
    │   └── test_prompts.py
    ├── integration/
    │   ├── test_zai_provider.py  # Uses pytest-httpx mock
    │   ├── test_ollama_provider.py
    │   └── test_api.py           # FastAPI TestClient
    └── e2e/
        ├── test_scraper_fixture.py  # Playwright against mock HTML
        └── test_dashboard.py        # Playwright against running server
```

---

## 4.3 Key Architectural Decisions & Trade-offs

| Decision | Chosen | Rejected | Reason |
|----------|--------|----------|--------|
| Frontend framework | React + TypeScript | Streamlit, Gradio, NiceGUI | "Clean, elegant" requirement demands component-level control. Streamlit/Gradio impose visual constraints and are harder to theme. React + shadcn/ui produces genuinely polished UIs. Python-only contributors work exclusively on the backend via the REST API boundary. |
| LLM HTTP client | httpx (async) | requests (sync) | The enrichment pipeline is I/O-bound and batched. Async HTTP via httpx enables concurrent batch enrichment without threading. `requests` is sync-only and would require thread pools for batching. |
| Config format | YAML | TOML, .env only | YAML is the most human-readable for nested config (provider sub-configs). TOML is equally valid but less common in Python AI tooling. Environment variables are supported as overrides for CI/CD and secrets — both are supported via Pydantic Settings. |
| CLI framework | Typer | Click, argparse | Typer wraps Click with Python type annotations for automatic argument parsing and help generation. Produces a clean CLI with minimal code. The TUI (`linkedin-vault tui`) remains the primary UX; CLI flags serve power users and automation. |
| Session storage | File (`~/.linkedin-vault/session.json`) | DB column, keyring | Keeping session cookies out of the database reduces attack surface (DB is queryable; file has `600` permissions). OS keyring is platform-specific and complicates cross-platform testing. File approach is simple, transparent, and auditable. |

---

## 4.4 Recommended Next Steps

1. **Maintainer confirms tech stack** — Especially: confirm z.ai API key is available and working before Phase 3 begins; confirm Ollama is installed locally for provider testing.
2. **Security Agent review** — Section 1.7 (Legal & Ethical Risk Register) and FR-AUTH-03 (session cookie permissions) require security agent sign-off before Phase 2 implementation begins.
3. **Architect Agent** — Design the SQLAlchemy models and Alembic migration to exactly match the Post Table schema in Section 2.8.1. FTS5 virtual table must be added in Phase 4's migration.
4. **QA Agent** — Note the testability contract in FR-ENRICH-02: enrichment tests validate schema conformance (range, type, non-empty), never exact LLM output values. Build the provider contract test (`test_provider_contract`) in Phase 3 so it can be reused by contributors adding new providers.
5. **Phase 1 begins** — Project scaffold, pyproject.toml, directory structure, and CI/CD pipeline. No phase may begin until Phase 1 is complete (all phases depend on the foundation).

---

## 4.5 Open Questions for Maintainer

| # | Question | Blocks |
|---|----------|--------|
| OQ-01 | Should the dashboard frontend be pre-built and committed to the repo (so `pip install` works without Node.js), or should users build it from source? | Phase 4 packaging |
| OQ-02 | Is the z.ai "coding endpoint" (`/api/coding/paas/v4`) required for any enrichment use case, or is it only relevant for code generation tasks outside LinkedIn Vault's scope? | Phase 3 z.ai provider |
| OQ-03 | Should the `--re-enrich` flag re-enrich ALL posts, or only failed posts? Or should there be separate flags for each? | Phase 3 pipeline |
| OQ-04 | What is the desired behaviour when the saved posts page structure changes (LinkedIn DOM update)? Should the scraper fail loudly or extract partial data? | Phase 2 error handling |
| OQ-05 | Is there a preference for how the tag taxonomy is extended by contributors — via a PR to `taxonomy.py`, or via a user-editable config file? | Phase 3 taxonomy design |

---

*Sources consulted during analysis:*
- [Z.AI Developer Documentation](https://docs.z.ai/api-reference/introduction)
- [Z.AI Models — Mastra Docs](https://mastra.ai/models/providers/zai)
- [Z.AI (Zhipu AI) — liteLLM Docs](https://docs.litellm.ai/docs/providers/zai)
- [Z.AI Python SDK — GitHub](https://github.com/zai-org/z-ai-sdk-python)