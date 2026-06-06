# Contributing to LinkedIn Vault

Thank you for your interest in contributing. This document covers everything you need to get
started — from reporting bugs to submitting pull requests.

## Code of Conduct

This project follows the [Contributor Covenant Code of Conduct](https://www.contributor-covenant.org/version/2/1/code_of_conduct/).
Be respectful and constructive in all interactions.

## Reporting Bugs

Open a [GitHub Issue](https://github.com/your-username/linkedin-vault/issues/new?template=bug_report.md)
and fill in the bug report template. Include:

- Your OS and Python version
- The exact command you ran
- The full error output (use a code block)
- What you expected to happen

## Proposing Features

Open a [GitHub Issue](https://github.com/your-username/linkedin-vault/issues/new?template=feature_request.md)
using the feature request template. Describe the use case clearly — "I want to do X because Y" is
more useful than "add feature Z."

Large changes (new commands, new providers, schema changes) benefit from a discussion issue before
a PR is opened. This avoids wasted work if the direction doesn't fit the project.

## Development Setup

Requirements: Python 3.11+, git.

```bash
git clone https://github.com/your-username/linkedin-vault.git
cd linkedin-vault
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
playwright install chromium
cp .env.example .env             # fill in your LLM provider settings
```

## Running Tests

```bash
make test
# or directly:
pytest tests/ -v --cov=linkedin_vault --cov-report=term-missing
```

All tests are async (pytest-asyncio in `auto` mode) and use temporary in-memory SQLite databases.
No live LinkedIn session or LLM API key is needed to run the suite.

The test suite is intentionally free of mocked databases — all `DatabaseManager` tests hit a real
SQLite file in a `tmp_path` fixture. If you add tests that require a database, follow the same
pattern and use the `db` fixture from `tests/conftest.py`.

## Running the Linter

```bash
make lint          # check only (CI equivalent)
make format        # auto-fix formatting and import order
```

The project uses [Ruff](https://docs.astral.sh/ruff/) for both linting and formatting.
Line length is 100. Imports are sorted with isort-compatible rules.

## Commit Message Convention

This project uses [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <short description>

[optional body]
```

Types:

| Type | Use for |
|------|---------|
| `feat` | New user-facing feature |
| `fix` | Bug fix |
| `docs` | Documentation only |
| `test` | Adding or fixing tests |
| `refactor` | Code change that is neither a feature nor a bug fix |
| `chore` | Dependency updates, build scripts, CI changes |

Examples:

```
feat(enricher): add Anthropic Claude provider
fix(parser): handle Feb 29 without crashing when year is not a leap year
docs(readme): add Ollama quickstart instructions
test(dashboard): add pagination edge-case tests
```

## Pull Request Process

1. **Fork** the repository and create a branch from `main`:
   ```bash
   git checkout -b feat/my-feature
   ```

2. **Write tests** for any new behaviour. The CI suite must pass before a PR will be reviewed.

3. **Run lint** (`make lint`) and fix any issues before pushing.

4. **Open a PR** against `main` and fill in the PR template. Link any related issues.

5. **Address review feedback** — maintainers may request changes before merging.

## Project Structure

```
src/linkedin_vault/
├── cli.py          Typer CLI — all user-facing commands live here
├── config.py       pydantic-settings configuration
├── db/             SQLite persistence (models, migrations, async DatabaseManager)
├── scraper/        Playwright browser automation and DOM parsing
├── enricher/       LLM provider abstraction, prompt construction, retry logic
├── dashboard/      FastAPI web server and static frontend
└── tui/            Textual TUI wizard for interactive setup
tests/              pytest suite mirroring the src/ structure
```

## Adding a New LLM Provider

1. Create `src/linkedin_vault/enricher/<provider>.py`.
2. Subclass `BaseLLMProvider` from `linkedin_vault.enricher.base`:

```python
from linkedin_vault.enricher.base import BaseLLMProvider, EnrichmentResult, LLMProviderError

class MyProvider(BaseLLMProvider):
    async def list_models(self) -> list[str]:
        ...  # return available model names

    async def enrich_post(
        self,
        content: str,
        author_name: str,
        post_date: str | None,
        model: str,
        today: str,
    ) -> EnrichmentResult:
        ...  # call your API and return a parsed EnrichmentResult
```

3. Add a new variant to `LLMProvider` in `config.py`.
4. Wire it into the factory in `enricher/factory.py`.
5. Add tests in `tests/test_enricher.py` following the existing httpx mock pattern.
6. Document the provider in `README.md`.

## Questions

Open a GitHub Discussion or file an issue with the `question` label.
