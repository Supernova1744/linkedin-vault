"""Pure async unit tests for DatabaseManager.save_chat_turn and get_chat_history.

No TUI involvement — only aiosqlite and a tmp_path DB.
"""

from __future__ import annotations

from pathlib import Path

import aiosqlite
import pytest

from linkedin_vault.db.database import DatabaseManager

# ---------------------------------------------------------------------------
# 1. Round-trip: save and retrieve turns in insertion order
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_save_and_retrieve_turns(tmp_path: Path) -> None:
    """save_chat_turn + get_chat_history returns turns in chronological order."""
    db = DatabaseManager(tmp_path / "vault.db")
    await db.initialize_db()

    await db.save_chat_turn("user", "Hello, what is RAG?")
    await db.save_chat_turn("assistant", "RAG is Retrieval-Augmented Generation.")
    await db.save_chat_turn("user", "Can you elaborate?")

    history = await db.get_chat_history()

    assert len(history) == 3
    assert history[0] == {"role": "user", "content": "Hello, what is RAG?"}
    assert history[1] == {"role": "assistant", "content": "RAG is Retrieval-Augmented Generation."}
    assert history[2] == {"role": "user", "content": "Can you elaborate?"}


# ---------------------------------------------------------------------------
# 2. Pruning: 401st insert evicts the oldest row
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_prune_at_400_rows(tmp_path: Path) -> None:
    """After 401 inserts, get_chat_history returns exactly 400 rows (oldest pruned)."""
    db = DatabaseManager(tmp_path / "vault.db")
    await db.initialize_db()

    for i in range(401):
        role = "user" if i % 2 == 0 else "assistant"
        await db.save_chat_turn(role, f"message {i}")

    history = await db.get_chat_history()

    assert len(history) == 400
    # message 0 (the first-inserted row) should have been pruned
    assert history[0]["content"] == "message 1"
    # The newest entry must still be present
    assert history[-1]["content"] == "message 400"


# ---------------------------------------------------------------------------
# 3. Empty history on a fresh DB
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_empty_history(tmp_path: Path) -> None:
    """Fresh DB with no turns returns an empty list."""
    db = DatabaseManager(tmp_path / "vault.db")
    await db.initialize_db()

    history = await db.get_chat_history()

    assert history == []


# ---------------------------------------------------------------------------
# 4. Role CHECK constraint rejects invalid values
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_role_constraint(tmp_path: Path) -> None:
    """Saving with role='invalid' raises aiosqlite.IntegrityError (CHECK constraint)."""
    db = DatabaseManager(tmp_path / "vault.db")
    await db.initialize_db()

    with pytest.raises(aiosqlite.IntegrityError):
        await db.save_chat_turn("invalid", "some content")


# ---------------------------------------------------------------------------
# 5. initialize_db() is idempotent when chat_history already exists
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_initialize_db_idempotent_with_chat_history(tmp_path: Path) -> None:
    """Calling initialize_db() twice succeeds and leaves existing data intact."""
    db = DatabaseManager(tmp_path / "vault.db")
    await db.initialize_db()

    # Write a turn to confirm the table is live
    await db.save_chat_turn("user", "test message")

    # Second call must not raise (CREATE TABLE IF NOT EXISTS is idempotent)
    await db.initialize_db()

    # Data written before the second init must still be present
    history = await db.get_chat_history()
    assert len(history) == 1
    assert history[0]["content"] == "test message"
