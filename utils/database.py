"""SQLite database manager — schema creation & connection pooling."""
from __future__ import annotations

import logging
import sqlite3
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

_SCHEMA_VERSION = 1

_SCHEMA_SQL = """
-- Groups table (group-centric model)
CREATE TABLE IF NOT EXISTS groups (
    chat_id        TEXT PRIMARY KEY,
    chat_title     TEXT,
    added_by       INTEGER NOT NULL,
    language       TEXT DEFAULT 'en',
    created_at     TEXT,
    updated_at     TEXT
);

CREATE TABLE IF NOT EXISTS group_admins (
    chat_id        TEXT NOT NULL,
    user_id        INTEGER NOT NULL,
    role           TEXT DEFAULT 'admin',
    PRIMARY KEY (chat_id, user_id)
);

-- Anti-spam config
CREATE TABLE IF NOT EXISTS spam_config (
    chat_id            TEXT PRIMARY KEY,
    enabled            INTEGER DEFAULT 0,
    keyword_blacklist  TEXT DEFAULT '[]',
    link_filter        INTEGER DEFAULT 0,
    link_whitelist     TEXT DEFAULT '[]',
    newbie_restrict    INTEGER DEFAULT 0,
    newbie_minutes     INTEGER DEFAULT 10,
    repeat_detect      INTEGER DEFAULT 0,
    repeat_window_sec  INTEGER DEFAULT 60,
    repeat_threshold   INTEGER DEFAULT 3,
    punishment         TEXT DEFAULT 'delete_warn',
    whitelist_users    TEXT DEFAULT '[]',
    updated_at         TEXT
);

-- Q&A rules
CREATE TABLE IF NOT EXISTS qa_rules (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id         TEXT NOT NULL,
    trigger_text    TEXT NOT NULL,
    response_text   TEXT NOT NULL,
    match_mode      TEXT DEFAULT 'fuzzy',
    reply_mode      TEXT DEFAULT 'reply',
    cooldown_sec    INTEGER DEFAULT 30,
    enabled         INTEGER DEFAULT 1,
    created_at      TEXT,
    updated_at      TEXT
);

-- Community chat config
CREATE TABLE IF NOT EXISTS chat_config (
    chat_id            TEXT PRIMARY KEY,
    welcome_enabled    INTEGER DEFAULT 0,
    welcome_message    TEXT DEFAULT '',
    at_bot_reply       TEXT DEFAULT '',
    updated_at         TEXT
);

-- Scheduled messages
CREATE TABLE IF NOT EXISTS scheduled_messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id         TEXT NOT NULL,
    content         TEXT NOT NULL,
    cron_expr       TEXT NOT NULL,
    enabled         INTEGER DEFAULT 1,
    last_sent_at    TEXT,
    created_at      TEXT
);

-- Events / giveaways
CREATE TABLE IF NOT EXISTS events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id         TEXT NOT NULL,
    title           TEXT NOT NULL,
    description     TEXT DEFAULT '',
    prize           TEXT DEFAULT '',
    winner_count    INTEGER DEFAULT 1,
    status          TEXT DEFAULT 'active',
    end_time        TEXT,
    message_id      INTEGER,
    created_by      INTEGER NOT NULL,
    created_at      TEXT,
    drawn_at        TEXT
);

CREATE TABLE IF NOT EXISTS event_participants (
    event_id        INTEGER NOT NULL,
    user_id         INTEGER NOT NULL,
    username        TEXT,
    display_name    TEXT,
    joined_at       TEXT,
    PRIMARY KEY (event_id, user_id)
);

-- Moderation log
CREATE TABLE IF NOT EXISTS moderation_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id         TEXT NOT NULL,
    user_id         INTEGER,
    action          TEXT NOT NULL,
    reason          TEXT,
    message_text    TEXT,
    created_at      TEXT
);

-- Legacy monitor configs (migrated from JSON)
CREATE TABLE IF NOT EXISTS monitor_config (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id        INTEGER NOT NULL,
    monitor_type    TEXT NOT NULL,
    source_config   TEXT NOT NULL,
    destination     TEXT NOT NULL,
    keywords        TEXT DEFAULT '[]',
    active          INTEGER DEFAULT 1,
    created_at      TEXT,
    updated_at      TEXT
);

-- Knowledge base files
CREATE TABLE IF NOT EXISTS knowledge_files (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id         TEXT NOT NULL,
    file_name       TEXT NOT NULL,
    file_type       TEXT NOT NULL,
    file_size       INTEGER DEFAULT 0,
    file_path       TEXT NOT NULL,
    chunk_count     INTEGER DEFAULT 0,
    total_chars     INTEGER DEFAULT 0,
    uploaded_by     INTEGER NOT NULL,
    status          TEXT DEFAULT 'active',
    created_at      TEXT,
    updated_at      TEXT
);

-- Knowledge chunks
CREATE TABLE IF NOT EXISTS knowledge_chunks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id         INTEGER NOT NULL,
    chat_id         TEXT NOT NULL,
    chunk_index     INTEGER NOT NULL,
    content         TEXT NOT NULL,
    keywords        TEXT DEFAULT '',
    char_count      INTEGER DEFAULT 0,
    FOREIGN KEY (file_id) REFERENCES knowledge_files(id)
);

-- AI config per group
CREATE TABLE IF NOT EXISTS ai_config (
    chat_id             TEXT PRIMARY KEY,
    enabled             INTEGER DEFAULT 0,
    system_prompt       TEXT DEFAULT 'You are a friendly community assistant. Answer user questions based on the knowledge base.',
    trigger_mode        TEXT DEFAULT 'all',
    trigger_keywords    TEXT DEFAULT '[]',
    temperature         REAL DEFAULT 0.7,
    max_tokens          INTEGER DEFAULT 1024,
    proactive_enabled   INTEGER DEFAULT 1,
    proactive_threshold REAL DEFAULT 0.3,
    idle_reply_enabled  INTEGER DEFAULT 0,
    idle_reply_minutes  INTEGER DEFAULT 5,
    daily_share_enabled INTEGER DEFAULT 0,
    daily_share_cron    TEXT DEFAULT '09:00',
    updated_at          TEXT
);

-- AI usage log
CREATE TABLE IF NOT EXISTS ai_usage_log (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id           TEXT NOT NULL,
    user_id           INTEGER,
    question          TEXT,
    answer            TEXT,
    prompt_tokens     INTEGER DEFAULT 0,
    completion_tokens INTEGER DEFAULT 0,
    total_tokens      INTEGER DEFAULT 0,
    latency_ms        INTEGER DEFAULT 0,
    created_at        TEXT
);

-- Schema version tracking
CREATE TABLE IF NOT EXISTS schema_meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


class Database:
    """Thin wrapper around SQLite for the bot's data layer."""

    def __init__(self, db_path: str = "data/bot.db") -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn: sqlite3.Connection | None = None
        self._ensure_schema()

    # -- connection helpers --------------------------------------------------

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    def _ensure_schema(self) -> None:
        with self._lock:
            conn = self._get_conn()
            conn.executescript(_SCHEMA_SQL)
            conn.execute(
                "INSERT OR IGNORE INTO schema_meta (key, value) VALUES (?, ?)",
                ("version", str(_SCHEMA_VERSION)),
            )
            conn.commit()
            logger.info("Database schema ensured at %s (v%s)", self._db_path, _SCHEMA_VERSION)

    def close(self) -> None:
        with self._lock:
            if self._conn:
                self._conn.close()
                self._conn = None

    # -- generic helpers -----------------------------------------------------

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            return self._get_conn().execute(sql, params)

    def executemany(self, sql: str, params_list: list[tuple]) -> sqlite3.Cursor:
        with self._lock:
            return self._get_conn().executemany(sql, params_list)

    def commit(self) -> None:
        with self._lock:
            self._get_conn().commit()

    def fetchone(self, sql: str, params: tuple = ()) -> dict | None:
        with self._lock:
            row = self._get_conn().execute(sql, params).fetchone()
            return dict(row) if row else None

    def fetchall(self, sql: str, params: tuple = ()) -> list[dict]:
        with self._lock:
            rows = self._get_conn().execute(sql, params).fetchall()
            return [dict(r) for r in rows]
