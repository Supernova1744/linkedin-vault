"""Pydantic request and response schemas for the LinkedIn Vault dashboard API.

Each class corresponds to either an incoming request body or an outgoing JSON
response.  FastAPI validates requests against these schemas automatically and
uses them to generate the OpenAPI spec.
"""

from typing import Literal

from pydantic import BaseModel, Field


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


class CitationResponse(BaseModel):
    post_id: int
    url: str
    author_name: str
    excerpt: str
    importance_score: float | None
    tags: list[str]


class ChatRequest(BaseModel):
    session_id: str | None = None
    message: str = Field(max_length=4000)


class ChatResponse(BaseModel):
    session_id: str
    answer: str
    citations: list[CitationResponse]
    retrieved_count: int


class SettingsResponse(BaseModel):
    llm_provider: str
    llm_model: str
    chat_provider: str
    chat_model: str
    chat_top_k: int
