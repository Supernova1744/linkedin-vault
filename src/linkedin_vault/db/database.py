import json
from datetime import UTC, datetime
from pathlib import Path

import aiosqlite

from linkedin_vault.db.models import Post, SyncState, VaultStats


def _now_utc() -> str:
    return datetime.now(UTC).isoformat()


def _row_to_post(row: aiosqlite.Row) -> Post:
    d = dict(row)
    raw_tags = d.get("tags")
    tags: list[str] | None = json.loads(raw_tags) if raw_tags else None
    raw_outdated = d.get("is_outdated")
    is_outdated: bool | None = bool(raw_outdated) if raw_outdated is not None else None
    return Post(
        id=d["id"],
        linkedin_id=d["linkedin_id"],
        url=d["url"],
        author_name=d["author_name"],
        author_profile_url=d.get("author_profile_url"),
        content=d["content"],
        post_date=d.get("post_date"),
        scraped_at=d["scraped_at"],
        summary=d.get("summary"),
        tags=tags,
        importance_score=d.get("importance_score"),
        is_outdated=is_outdated,
        enriched_at=d.get("enriched_at"),
        enrichment_model=d.get("enrichment_model"),
        status=d.get("status", "unread"),
        status_updated_at=d.get("status_updated_at"),
    )


class DatabaseManager:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._migrations_sql = Path(__file__).parent / "migrations.sql"

    async def initialize_db(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        migration_sql = self._migrations_sql.read_text(encoding="utf-8")
        async with aiosqlite.connect(self._db_path) as conn:
            await conn.executescript(migration_sql)
            await conn.commit()

    async def upsert_post(self, post: Post) -> int:
        tags_json = json.dumps(post.tags) if post.tags is not None else None
        is_outdated_int = int(post.is_outdated) if post.is_outdated is not None else None
        async with aiosqlite.connect(self._db_path) as conn:
            cursor = await conn.execute(
                """
                INSERT INTO posts (
                    linkedin_id, url, author_name, author_profile_url, content,
                    post_date, scraped_at, summary, tags, importance_score,
                    is_outdated, enriched_at, enrichment_model, status, status_updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(linkedin_id) DO UPDATE SET
                    url = excluded.url,
                    author_name = excluded.author_name,
                    author_profile_url = excluded.author_profile_url,
                    content = excluded.content,
                    post_date = excluded.post_date,
                    scraped_at = excluded.scraped_at,
                    summary = COALESCE(excluded.summary, summary),
                    tags = COALESCE(excluded.tags, tags),
                    importance_score = COALESCE(excluded.importance_score, importance_score),
                    is_outdated = COALESCE(excluded.is_outdated, is_outdated),
                    enriched_at = COALESCE(excluded.enriched_at, enriched_at),
                    enrichment_model = COALESCE(excluded.enrichment_model, enrichment_model)
                """,
                (
                    post.linkedin_id,
                    post.url,
                    post.author_name,
                    post.author_profile_url,
                    post.content,
                    post.post_date,
                    post.scraped_at,
                    post.summary,
                    tags_json,
                    post.importance_score,
                    is_outdated_int,
                    post.enriched_at,
                    post.enrichment_model,
                    post.status,
                    post.status_updated_at,
                ),
            )
            await conn.commit()
            return cursor.lastrowid or 0

    async def get_all_posts(
        self,
        status_filter: str | None = None,
        min_importance: float | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Post]:
        clauses: list[str] = []
        params: list[object] = []
        if status_filter is not None:
            clauses.append("status = ?")
            params.append(status_filter)
        if min_importance is not None:
            clauses.append("importance_score >= ?")
            params.append(min_importance)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        if limit is not None:
            limit_clause = f"LIMIT {limit} OFFSET {offset}"
        else:
            limit_clause = f"LIMIT -1 OFFSET {offset}"
        sql = f"SELECT * FROM posts {where} ORDER BY scraped_at DESC {limit_clause}"
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute(sql, params)
            rows = await cursor.fetchall()
        return [_row_to_post(row) for row in rows]

    async def get_post_by_id(self, post_id: int) -> Post | None:
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute("SELECT * FROM posts WHERE id = ?", (post_id,))
            row = await cursor.fetchone()
        return _row_to_post(row) if row else None

    async def get_post_by_linkedin_id(self, linkedin_id: str) -> Post | None:
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute("SELECT * FROM posts WHERE linkedin_id = ?", (linkedin_id,))
            row = await cursor.fetchone()
        return _row_to_post(row) if row else None

    async def update_post_status(self, post_id: int, status: str) -> None:
        async with aiosqlite.connect(self._db_path) as conn:
            await conn.execute(
                "UPDATE posts SET status = ?, status_updated_at = ? WHERE id = ?",
                (status, _now_utc(), post_id),
            )
            await conn.commit()

    async def update_post_enrichment(
        self,
        post_id: int,
        summary: str,
        tags: list[str],
        importance_score: float,
        is_outdated: bool,
        enrichment_model: str,
    ) -> None:
        async with aiosqlite.connect(self._db_path) as conn:
            await conn.execute(
                """
                UPDATE posts SET
                    summary = ?,
                    tags = ?,
                    importance_score = ?,
                    is_outdated = ?,
                    enriched_at = ?,
                    enrichment_model = ?
                WHERE id = ?
                """,
                (
                    summary,
                    json.dumps(tags),
                    importance_score,
                    int(is_outdated),
                    _now_utc(),
                    enrichment_model,
                    post_id,
                ),
            )
            await conn.commit()

    async def get_posts_for_enrichment(
        self,
        re_enrich: bool = False,
        limit: int | None = None,
    ) -> list[Post]:
        """Return posts that need LLM enrichment.

        Args:
            re_enrich: If ``True``, return all posts (re-enrich everything).
                       If ``False`` (default), return only posts with
                       ``enriched_at IS NULL``.
            limit:     Maximum number of rows to return.  ``None`` = all.
        """
        where = "" if re_enrich else "WHERE enriched_at IS NULL"
        limit_clause = f"LIMIT {limit}" if limit is not None else "LIMIT -1"
        sql = f"SELECT * FROM posts {where} ORDER BY scraped_at ASC {limit_clause}"
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute(sql)
            rows = await cursor.fetchall()
        return [_row_to_post(row) for row in rows]

    async def search_posts(self, query: str, limit: int = 50) -> list[Post]:
        # Wrap in double-quotes to safely handle special FTS5 chars (C++, foo:bar, etc.)
        safe_query = f'"{query}"'
        sql = """
            SELECT p.*
            FROM posts p
            JOIN posts_fts fts ON p.id = fts.rowid
            WHERE posts_fts MATCH ?
            ORDER BY rank
            LIMIT ?
        """
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute(sql, (safe_query, limit))
            rows = await cursor.fetchall()
        return [_row_to_post(row) for row in rows]

    async def get_sync_state(self) -> SyncState:
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute("SELECT * FROM sync_state WHERE id = 1")
            row = await cursor.fetchone()
        if row is None:
            return SyncState(
                last_scraped_at=None, total_posts_scraped=0, last_sync_duration_seconds=None
            )
        d = dict(row)
        return SyncState(
            last_scraped_at=d.get("last_scraped_at"),
            total_posts_scraped=d.get("total_posts_scraped", 0),
            last_sync_duration_seconds=d.get("last_sync_duration_seconds"),
        )

    async def update_sync_state(
        self,
        last_scraped_at: str,
        total_posts_scraped: int,
        last_sync_duration_seconds: float,
    ) -> None:
        async with aiosqlite.connect(self._db_path) as conn:
            await conn.execute(
                """
                UPDATE sync_state SET
                    last_scraped_at = ?,
                    total_posts_scraped = ?,
                    last_sync_duration_seconds = ?
                WHERE id = 1
                """,
                (last_scraped_at, total_posts_scraped, last_sync_duration_seconds),
            )
            await conn.commit()

    async def get_stats(self) -> VaultStats:
        sql = """
            SELECT
                COUNT(*) AS total_posts,
                SUM(CASE WHEN enriched_at IS NOT NULL THEN 1 ELSE 0 END) AS enriched_posts,
                SUM(CASE WHEN status = 'unread' THEN 1 ELSE 0 END) AS unread_posts
            FROM posts
        """
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute(sql)
            row = await cursor.fetchone()
            sync_cursor = await conn.execute(
                "SELECT total_posts_scraped, last_scraped_at FROM sync_state WHERE id = 1"
            )
            sync_row = await sync_cursor.fetchone()

        counts = dict(row) if row else {}
        sync = dict(sync_row) if sync_row else {}
        return VaultStats(
            total_posts=counts.get("total_posts", 0) or 0,
            enriched_posts=counts.get("enriched_posts", 0) or 0,
            unread_posts=counts.get("unread_posts", 0) or 0,
            total_posts_scraped=sync.get("total_posts_scraped", 0) or 0,
            last_scraped_at=sync.get("last_scraped_at"),
        )

    async def delete_post(self, post_id: int) -> None:
        async with aiosqlite.connect(self._db_path) as conn:
            await conn.execute("DELETE FROM posts WHERE id = ?", (post_id,))
            await conn.commit()

    async def get_posts_filtered(
        self,
        query: str | None = None,
        tag: str | None = None,
        status_filter: str | None = None,
        sort: str = "date_desc",
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Post], int]:
        """Return (posts, total_count) with optional FTS5 search, tag/status filtering,
        custom sort, and pagination.

        Null importance scores are always sorted last regardless of direction.
        """
        sort_map = {
            "importance_desc": "(p.importance_score IS NULL), p.importance_score DESC",
            "importance_asc": "(p.importance_score IS NULL), p.importance_score ASC",
            "date_desc": "p.scraped_at DESC",
            "date_asc": "p.scraped_at ASC",
        }
        order_by = sort_map.get(sort, "p.scraped_at DESC")
        offset = (page - 1) * page_size

        clauses: list[str] = []
        params: list[object] = []
        if status_filter:
            clauses.append("p.status = ?")
            params.append(status_filter)
        if tag:
            clauses.append(
                "EXISTS (SELECT 1 FROM json_each(p.tags) e WHERE e.value = ?)"
            )
            params.append(tag)

        use_fts = bool(query and query.strip())
        if use_fts:
            assert query is not None  # narrowing for mypy
            safe_q = f'"{query}"'
            extra_where = (" AND " + " AND ".join(clauses)) if clauses else ""
            count_sql = (
                "SELECT COUNT(*) AS cnt FROM posts p "
                "JOIN posts_fts fts ON p.id = fts.rowid "
                f"WHERE posts_fts MATCH ?{extra_where}"
            )
            data_sql = (
                "SELECT p.* FROM posts p "
                "JOIN posts_fts fts ON p.id = fts.rowid "
                f"WHERE posts_fts MATCH ?{extra_where} "
                f"ORDER BY {order_by} LIMIT ? OFFSET ?"
            )
            count_params: list[object] = [safe_q, *params]
            data_params: list[object] = [safe_q, *params, page_size, offset]
        else:
            where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
            count_sql = f"SELECT COUNT(*) AS cnt FROM posts p {where}"
            data_sql = (
                f"SELECT p.* FROM posts p {where} "
                f"ORDER BY {order_by} LIMIT ? OFFSET ?"
            )
            count_params = [*params]
            data_params = [*params, page_size, offset]

        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cnt_cursor = await conn.execute(count_sql, count_params)
            cnt_row = await cnt_cursor.fetchone()
            total: int = dict(cnt_row)["cnt"] if cnt_row else 0

            data_cursor = await conn.execute(data_sql, data_params)
            rows = await data_cursor.fetchall()

        return [_row_to_post(row) for row in rows], total

    async def get_all_tags(self) -> list[str]:
        """Return all unique tags across all enriched posts, sorted alphabetically."""
        sql = """
            SELECT DISTINCT e.value
            FROM posts p, json_each(p.tags) e
            WHERE p.tags IS NOT NULL
            ORDER BY e.value
        """
        async with aiosqlite.connect(self._db_path) as conn:
            cursor = await conn.execute(sql)
            rows = await cursor.fetchall()
        return [row[0] for row in rows]
