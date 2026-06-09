-- Enable WAL mode for better concurrency
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    linkedin_id TEXT UNIQUE NOT NULL,
    url TEXT NOT NULL,
    author_name TEXT NOT NULL,
    author_profile_url TEXT,
    content TEXT NOT NULL,
    post_date TEXT,
    scraped_at TEXT NOT NULL,

    -- LLM-enriched fields (NULL until enriched)
    summary TEXT,
    tags TEXT,                          -- JSON array: ["AI", "Python", ...]
    importance_score REAL,              -- 0.0 to 10.0
    is_outdated INTEGER,                -- 0=false, 1=true, NULL=not enriched
    enriched_at TEXT,
    enrichment_model TEXT,

    -- Read queue status
    status TEXT NOT NULL DEFAULT 'unread',
    status_updated_at TEXT
);

-- Full-text search virtual table (FTS5)
CREATE VIRTUAL TABLE IF NOT EXISTS posts_fts USING fts5(
    content,
    author_name,
    summary,
    tags,
    content='posts',
    content_rowid='id'
);

-- Triggers to keep FTS in sync
CREATE TRIGGER IF NOT EXISTS posts_ai AFTER INSERT ON posts BEGIN
    INSERT INTO posts_fts(rowid, content, author_name, summary, tags)
    VALUES (new.id, new.content, new.author_name, new.summary, new.tags);
END;

CREATE TRIGGER IF NOT EXISTS posts_ad AFTER DELETE ON posts BEGIN
    INSERT INTO posts_fts(posts_fts, rowid, content, author_name, summary, tags)
    VALUES ('delete', old.id, old.content, old.author_name, old.summary, old.tags);
END;

CREATE TRIGGER IF NOT EXISTS posts_au AFTER UPDATE ON posts BEGIN
    INSERT INTO posts_fts(posts_fts, rowid, content, author_name, summary, tags)
    VALUES ('delete', old.id, old.content, old.author_name, old.summary, old.tags);
    INSERT INTO posts_fts(rowid, content, author_name, summary, tags)
    VALUES (new.id, new.content, new.author_name, new.summary, new.tags);
END;

-- Sync metadata for incremental scraping
CREATE TABLE IF NOT EXISTS sync_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    last_scraped_at TEXT,
    total_posts_scraped INTEGER DEFAULT 0,
    last_sync_duration_seconds REAL,
    last_scrape_was_complete INTEGER DEFAULT 0
);

INSERT OR IGNORE INTO sync_state (id) VALUES (1);

-- Persistent chat history (up to 400 turns retained, pruned on insert)
CREATE TABLE IF NOT EXISTS chat_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);
