.PHONY: install dev-install lint format test tui stats clean

install:
	pip install -e .

dev-install:
	pip install -e ".[dev]"
	playwright install chromium

lint:
	ruff check src/ tests/
	ruff format --check src/ tests/

format:
	ruff format src/ tests/
	ruff check --fix src/ tests/

test:
	pytest tests/ -v --cov=linkedin_vault --cov-report=term-missing

test-fast:
	pytest tests/ -x -q

tui:
	linkedin-vault tui

stats:
	linkedin-vault stats

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
