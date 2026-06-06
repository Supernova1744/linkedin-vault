from pathlib import Path

import pytest
import pytest_asyncio

from linkedin_vault.config import LLMProvider, Settings
from linkedin_vault.db.database import DatabaseManager
from linkedin_vault.db.models import Post


@pytest.fixture
def tmp_db_path(tmp_path: Path) -> Path:
    return tmp_path / "test_vault.db"


@pytest_asyncio.fixture
async def db(tmp_db_path: Path) -> DatabaseManager:
    manager = DatabaseManager(tmp_db_path)
    await manager.initialize_db()
    return manager


@pytest.fixture
def sample_post() -> Post:
    return Post(
        linkedin_id="urn:li:activity:1234567890",
        url="https://www.linkedin.com/feed/update/urn:li:activity:1234567890",
        author_name="Jane Doe",
        author_profile_url="https://www.linkedin.com/in/janedoe",
        content="Excited to share that Python 3.12 brings major performance improvements!",
        post_date="2024-01-15T10:30:00Z",
        scraped_at="2024-06-01T12:00:00Z",
    )


@pytest.fixture
def enriched_post(sample_post: Post) -> Post:
    return Post(
        linkedin_id=sample_post.linkedin_id,
        url=sample_post.url,
        author_name=sample_post.author_name,
        author_profile_url=sample_post.author_profile_url,
        content=sample_post.content,
        post_date=sample_post.post_date,
        scraped_at=sample_post.scraped_at,
        summary="Python 3.12 performance improvements announcement.",
        tags=["Python", "Performance", "Open Source"],
        importance_score=8.5,
        is_outdated=False,
        enriched_at="2024-06-01T13:00:00Z",
        enrichment_model="glm-4-flash",
    )


@pytest.fixture
def test_settings(tmp_path: Path) -> Settings:
    db_path = tmp_path / "test.db"
    return Settings(
        data_dir=tmp_path,
        db_path=db_path,
        llm_provider=LLMProvider.ZAI,
        llm_model="glm-4-flash",
        zai_api_key="test_key_abc123",
        log_level="DEBUG",
    )
