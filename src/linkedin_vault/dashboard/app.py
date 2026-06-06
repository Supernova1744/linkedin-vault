import math
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, TypeAlias

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from linkedin_vault.config import load_settings
from linkedin_vault.dashboard.schemas import (
    OkResponse,
    PostResponse,
    PostsResponse,
    StatsResponse,
    TagsResponse,
    UpdateStatusRequest,
)
from linkedin_vault.db.database import DatabaseManager

_STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize the database on startup so the first request never waits."""
    db_path = getattr(app.state, "db_path", None)
    if db_path is None:
        settings = load_settings()
        db_path = settings.get_db_path()
        app.state.db_path = db_path
    db = DatabaseManager(db_path)
    await db.initialize_db()
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
