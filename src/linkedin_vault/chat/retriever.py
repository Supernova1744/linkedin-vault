"""Post retrieval for the chat feature.

Uses FTS5 keyword search against the database, falling back to top-K by
importance score when the FTS5 query returns no results.

The key design choice: we do NOT pass the raw user question as an FTS5 phrase.
`database.search_posts` phrase-quotes its input (correct for the UI search bar),
but a natural-language question like "What posts do you have about Python?" would
never phrase-match any post.  Instead we extract meaningful keywords first, then
run an unquoted FTS5 term search (implicit AND across all terms).
"""

from __future__ import annotations

import re

from linkedin_vault.db.database import DatabaseManager
from linkedin_vault.db.models import Post

# Common English stop words + question/filler words to strip before FTS5.
# Keep this list broad — false-negatives (keeping a weak word) are less harmful
# than false-positives (dropping a meaningful short term like "ai" or "ml").
_STOP_WORDS: frozenset[str] = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "or",
        "but",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "with",
        "by",
        "from",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "shall",
        "can",
        "not",
        "no",
        "yes",
        "i",
        "you",
        "he",
        "she",
        "it",
        "we",
        "they",
        "me",
        "him",
        "her",
        "us",
        "them",
        "my",
        "your",
        "his",
        "its",
        "our",
        "their",
        "what",
        "which",
        "who",
        "whom",
        "whose",
        "when",
        "where",
        "why",
        "how",
        "there",
        "here",
        "this",
        "that",
        "these",
        "those",
        "any",
        "all",
        "some",
        "about",
        "posts",
        "post",
        "saved",
        "show",
        "tell",
        "find",
        "get",
        "give",
        "know",
        "see",
        "look",
        "make",
        "take",
        "use",
        "need",
        "want",
        "just",
        "also",
        "so",
        "as",
        "if",
        "then",
        "than",
        "more",
        "most",
        # Filler adverbs/qualifiers that add noise to FTS5 queries
        "specially",
        "especially",
        "particularly",
        "specifically",
        "really",
        "very",
        "quite",
        "pretty",
        "rather",
        "actually",
        "basically",
    }
)


def _extract_keywords(question: str) -> str:
    """Strip stop/question words and return remaining tokens joined by spaces.

    Minimum token length is 2 (not 3) so short but meaningful terms like
    'ai', 'ml', 'hr', 'vc' survive filtering.
    """
    tokens = re.findall(r"\b\w+\b", question.lower())
    keywords = [t for t in tokens if t not in _STOP_WORDS and len(t) >= 2]
    unique = list(dict.fromkeys(keywords))
    return " ".join(unique)


async def retrieve_posts(db: DatabaseManager, query: str, top_k: int) -> list[Post]:
    """FTS5 keyword search with OR fallback and importance-score last resort.

    Search strategy (in order):
    1. AND query: all keywords must match (high precision, low recall).
    2. OR query: any keyword may match (lower precision, higher recall).
       Only attempted when AND returns nothing and there are 2+ keywords.
    3. Importance-score fallback: top-K enriched posts regardless of content.

    Args:
        db:     Open DatabaseManager instance.
        query:  Raw user message — keywords are extracted automatically.
        top_k:  Maximum number of posts to return (caller clamps to [1, 20]).

    Returns:
        Up to top_k Post objects, ordered by FTS5 relevance or importance score.
    """
    keywords = _extract_keywords(query)
    posts: list[Post] = []

    if keywords:
        # Step 1: AND search — implicit AND when tokens are space-separated in FTS5
        posts = await db.search_posts_keywords(keywords, limit=top_k)

    keyword_tokens = keywords.split()
    if not posts and len(keyword_tokens) > 1:
        # Step 2: OR search — return posts matching ANY keyword, ranked by relevance
        or_query = " OR ".join(keyword_tokens)
        posts = await db.search_posts_keywords(or_query, limit=top_k)

    if not posts:
        # Step 3: No FTS5 match at all — fall back to top-K by importance score
        all_posts = await db.get_all_posts(limit=top_k * 5)
        all_posts.sort(
            key=lambda p: p.importance_score if p.importance_score is not None else -1.0,
            reverse=True,
        )
        posts = all_posts[:top_k]

    return posts
