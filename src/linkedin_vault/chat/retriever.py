"""Post retrieval for the chat feature.

Uses FTS5 keyword search against the database, falling back to top-K by
importance score when the FTS5 query returns no results (e.g. stop-words-only
query or empty vault).
"""

from linkedin_vault.db.database import DatabaseManager
from linkedin_vault.db.models import Post


async def retrieve_posts(db: DatabaseManager, query: str, top_k: int) -> list[Post]:
    """FTS5 search with importance-score fallback.

    Args:
        db:     Open DatabaseManager instance.
        query:  Raw user message used directly as the FTS5 query.
        top_k:  Maximum number of posts to return (caller is responsible for
                clamping to [1, 20]).

    Returns:
        Up to top_k Post objects, ordered by FTS5 relevance or importance score.
    """
    posts = await db.search_posts(query, limit=top_k)
    if not posts:
        # Fallback: fetch recent posts and re-sort by importance
        posts = await db.get_all_posts(limit=top_k)
        posts.sort(key=lambda p: p.importance_score or 0.0, reverse=True)
        posts = posts[:top_k]
    return posts
