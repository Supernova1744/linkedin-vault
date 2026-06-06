from dataclasses import dataclass, field

POST_STATUS_UNREAD = "unread"
POST_STATUS_READ = "read"
POST_STATUS_SKIPPED = "skipped"
POST_STATUS_SAVED_LATER = "saved_later"

VALID_POST_STATUSES = frozenset(
    {POST_STATUS_UNREAD, POST_STATUS_READ, POST_STATUS_SKIPPED, POST_STATUS_SAVED_LATER}
)


@dataclass
class Post:
    linkedin_id: str
    url: str
    author_name: str
    content: str
    scraped_at: str
    author_profile_url: str | None = None
    post_date: str | None = None
    summary: str | None = None
    tags: list[str] | None = None
    importance_score: float | None = None
    is_outdated: bool | None = None
    enriched_at: str | None = None
    enrichment_model: str | None = None
    status: str = field(default=POST_STATUS_UNREAD)
    status_updated_at: str | None = None
    id: int | None = None

    def __post_init__(self) -> None:
        if self.status not in VALID_POST_STATUSES:
            raise ValueError(
                f"Invalid status '{self.status}'. Must be one of {VALID_POST_STATUSES}"
            )
        if self.importance_score is not None and not (0.0 <= self.importance_score <= 10.0):
            raise ValueError(
                f"importance_score must be between 0.0 and 10.0, got {self.importance_score}"
            )


@dataclass
class SyncState:
    last_scraped_at: str | None
    total_posts_scraped: int
    last_sync_duration_seconds: float | None


@dataclass
class VaultStats:
    total_posts: int
    enriched_posts: int
    unread_posts: int
    total_posts_scraped: int
    last_scraped_at: str | None
