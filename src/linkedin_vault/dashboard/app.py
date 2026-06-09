"""FastAPI application for the LinkedIn Vault web dashboard.

Routes:
  GET  /                     Serve the single-page frontend (index.html)
  GET  /api/posts            Paginated post listing with FTS5 search and filters
  GET  /api/posts/{id}       Single post by database ID
  PATCH /api/posts/{id}/status  Update read/skipped/saved-later status
  DELETE /api/posts/{id}     Permanently remove a post
  GET  /api/stats            Vault-wide statistics
  GET  /api/tags             All unique tags across enriched posts
  POST /api/chat             Send a message; returns an LLM answer with citations
  DELETE /api/chat/{session} Clear a chat session
  GET  /api/settings         Current provider and model configuration

The app is served by uvicorn; see :mod:`linkedin_vault.dashboard.server` for
the launch helpers used by both the CLI and the TUI.
"""

import math
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, TypeAlias

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from linkedin_vault.chat.retriever import retrieve_posts
from linkedin_vault.chat.session import SessionStore
from linkedin_vault.chat.synthesiser import extract_citation_ids, synthesise
from linkedin_vault.config import Settings, load_settings
from linkedin_vault.dashboard.schemas import (
    ChatRequest,
    ChatResponse,
    CitationResponse,
    OkResponse,
    PostResponse,
    PostsResponse,
    SettingsResponse,
    StatsResponse,
    TagsResponse,
    UpdateStatusRequest,
)
from linkedin_vault.db.database import DatabaseManager
from linkedin_vault.enricher.base import LLMProviderError

_STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize the database and session store on startup."""
    db_path = getattr(app.state, "db_path", None)
    if db_path is None:
        settings = load_settings()
        db_path = settings.get_db_path()
        app.state.db_path = db_path
    db = DatabaseManager(db_path)
    await db.initialize_db()
    app.state.session_store = SessionStore()
    app.state.settings = load_settings()
    yield


app = FastAPI(title="LinkedIn Vault", docs_url=None, redoc_url=None, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


# ---------------------------------------------------------------------------
# Dependency injection
# ---------------------------------------------------------------------------


def get_db(request: Request) -> DatabaseManager:
    """Create a DatabaseManager from db_path stored in app.state.
    Falls back to settings-derived path when state has no db_path (production
    use with uvicorn string import).
    """
    db_path = getattr(request.app.state, "db_path", None)
    if db_path is None:
        db_path = load_settings().get_db_path()
    return DatabaseManager(db_path)


DbDep: TypeAlias = Annotated[DatabaseManager, Depends(get_db)]


def get_settings(request: Request) -> Settings:
    s = getattr(request.app.state, "settings", None)
    if s is None:
        s = load_settings()
    return s


SettingsDep: TypeAlias = Annotated[Settings, Depends(get_settings)]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_response(post) -> PostResponse:
    return PostResponse(
        id=post.id,
        linkedin_id=post.linkedin_id,
        url=post.url,
        author_name=post.author_name,
        author_profile_url=post.author_profile_url,
        content=post.content,
        post_date=post.post_date,
        scraped_at=post.scraped_at,
        summary=post.summary,
        tags=post.tags or [],
        importance_score=post.importance_score,
        is_outdated=post.is_outdated,
        enriched_at=post.enriched_at,
        enrichment_model=post.enrichment_model,
        status=post.status,
        status_updated_at=post.status_updated_at,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/")
async def root() -> FileResponse:
    return FileResponse(_STATIC_DIR / "index.html")


@app.get("/api/posts", response_model=PostsResponse)
async def get_posts(
    db: DbDep,
    q: str | None = Query(default=None, description="Full-text search query"),
    tag: str | None = Query(default=None, description="Filter by exact tag value"),
    status: str | None = Query(default=None, description="Filter by status"),
    sort: str = Query(default="importance_desc"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> PostsResponse:
    posts, total = await db.get_posts_filtered(
        query=q,
        tag=tag,
        status_filter=status,
        sort=sort,
        page=page,
        page_size=page_size,
    )
    pages = max(1, math.ceil(total / page_size))
    return PostsResponse(
        posts=[_to_response(p) for p in posts],
        total=total,
        page=page,
        pages=pages,
    )


@app.get("/api/posts/{post_id}", response_model=PostResponse)
async def get_post(post_id: int, db: DbDep) -> PostResponse:
    post = await db.get_post_by_id(post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")
    return _to_response(post)


@app.patch("/api/posts/{post_id}/status", response_model=OkResponse)
async def update_post_status(
    post_id: int,
    body: UpdateStatusRequest,
    db: DbDep,
) -> OkResponse:
    post = await db.get_post_by_id(post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")
    await db.update_post_status(post_id, body.status)
    return OkResponse()


@app.get("/api/stats", response_model=StatsResponse)
async def get_stats(db: DbDep) -> StatsResponse:
    stats = await db.get_stats()
    return StatsResponse(
        total_posts=stats.total_posts,
        enriched_posts=stats.enriched_posts,
        unread_posts=stats.unread_posts,
        total_posts_scraped=stats.total_posts_scraped,
        last_scraped_at=stats.last_scraped_at,
    )


@app.get("/api/tags", response_model=TagsResponse)
async def get_tags(db: DbDep) -> TagsResponse:
    tags = await db.get_all_tags()
    return TagsResponse(tags=tags)


@app.delete("/api/posts/{post_id}", response_model=OkResponse)
async def delete_post(post_id: int, db: DbDep) -> OkResponse:
    post = await db.get_post_by_id(post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")
    await db.delete_post(post_id)
    return OkResponse()


# ---------------------------------------------------------------------------
# Chat routes
# ---------------------------------------------------------------------------


@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(
    body: ChatRequest, db: DbDep, settings: SettingsDep, request: Request
) -> ChatResponse:
    if not body.message or not body.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    top_k = max(1, min(20, settings.chat_top_k))

    session_store: SessionStore = request.app.state.session_store
    session = session_store.get_or_create(body.session_id)

    try:
        posts = await retrieve_posts(db, body.message, top_k)
        answer = await synthesise(body.message, posts, session.messages, settings)
    except LLMProviderError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    # Build citations from posts that were actually cited in the answer
    post_map = {p.id: p for p in posts if p.id is not None}
    cited_ids = extract_citation_ids(answer)
    citations = []
    for pid in sorted(cited_ids):
        p = post_map.get(pid)
        if p is not None:
            citations.append(
                CitationResponse(
                    post_id=pid,
                    url=p.url,
                    author_name=p.author_name,
                    excerpt=(p.content or "")[:300],
                    importance_score=p.importance_score,
                    tags=p.tags or [],
                )
            )

    session_store.add_turn(session, body.message, answer)

    return ChatResponse(
        session_id=session.session_id,
        answer=answer,
        citations=citations,
        retrieved_count=len(posts),
    )


@app.delete("/api/chat/{session_id}", response_model=OkResponse)
async def clear_chat(session_id: str, request: Request) -> OkResponse:
    session_store: SessionStore = request.app.state.session_store
    session_store.delete(session_id)
    return OkResponse()


@app.get("/api/settings", response_model=SettingsResponse)
async def get_settings_route(settings: SettingsDep) -> SettingsResponse:
    return SettingsResponse(
        llm_provider=settings.llm_provider.value,
        llm_model=settings.llm_model,
        chat_provider=settings.get_chat_provider().value,
        chat_model=settings.get_chat_model(),
        chat_top_k=settings.chat_top_k,
    )
