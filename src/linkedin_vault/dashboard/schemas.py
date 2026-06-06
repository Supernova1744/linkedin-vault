from typing import Literal

from pydantic import BaseModel


class PostResponse(BaseModel):
    id: int
    linkedin_id: str
    url: str
    author_name: str
    author_profile_url: str | None
    content: str
    post_date: str | None
    scraped_at: str
    summary: str | None
    tags: list[str]
    importance_score: float | None
    is_outdated: bool | None
    enriched_at: str | None
    enrichment_model: str | None
    status: str
    status_updated_at: str | None


class PostsResponse(BaseModel):
    posts: list[PostResponse]
    total: int
    page: int
    pages: int


class StatsResponse(BaseModel):
    total_posts: int
    enriched_posts: int
    unread_posts: int
    total_posts_scraped: int
    last_scraped_at: str | None


class TagsResponse(BaseModel):
    tags: list[str]


class UpdateStatusRequest(BaseModel):
    status: Literal["read", "unread", "skipped", "saved_later"]


class OkResponse(BaseModel):
    ok: bool = True
