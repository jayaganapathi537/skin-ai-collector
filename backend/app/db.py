import sqlite3
from contextlib import contextmanager

from .config import settings

SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS photos (
 photo_id TEXT PRIMARY KEY, participant_id TEXT NOT NULL, drive_file_id TEXT,
 mime_type TEXT NOT NULL, file_size INTEGER NOT NULL, image_width INTEGER NOT NULL,
 image_height INTEGER NOT NULL, created_at TEXT NOT NULL, consent_version TEXT NOT NULL,
 consent_timestamp TEXT NOT NULL, consent_id TEXT NOT NULL, consent_confirmed INTEGER NOT NULL,
 adult_confirmed INTEGER NOT NULL, review_status TEXT NOT NULL DEFAULT 'pending'
   CHECK(review_status IN ('pending','approved','rejected')),
 rejection_reason TEXT NOT NULL DEFAULT '', annotation_json TEXT NOT NULL,
 idempotency_key TEXT NOT NULL UNIQUE, upload_state TEXT NOT NULL DEFAULT 'pending'
   CHECK(upload_state IN ('pending','uploaded','failed'))
);
CREATE TABLE IF NOT EXISTS annotation_history (
 id INTEGER PRIMARY KEY AUTOINCREMENT, photo_id TEXT NOT NULL, saved_at TEXT NOT NULL,
 annotation_json TEXT NOT NULL, review_status TEXT NOT NULL,
 FOREIGN KEY(photo_id) REFERENCES photos(photo_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS app_settings (setting_key TEXT PRIMARY KEY, setting_value TEXT NOT NULL);
"""

POSTGRES_SCHEMA = """
CREATE TABLE IF NOT EXISTS photos (
 photo_id TEXT PRIMARY KEY, participant_id TEXT NOT NULL, drive_file_id TEXT,
 mime_type TEXT NOT NULL, file_size BIGINT NOT NULL, image_width INTEGER NOT NULL,
 image_height INTEGER NOT NULL, created_at TEXT NOT NULL, consent_version TEXT NOT NULL,
 consent_timestamp TEXT NOT NULL, consent_id TEXT NOT NULL, consent_confirmed INTEGER NOT NULL,
 adult_confirmed INTEGER NOT NULL, review_status TEXT NOT NULL DEFAULT 'pending'
   CHECK(review_status IN ('pending','approved','rejected')),
 rejection_reason TEXT NOT NULL DEFAULT '', annotation_json TEXT NOT NULL,
 idempotency_key TEXT NOT NULL UNIQUE, upload_state TEXT NOT NULL DEFAULT 'pending'
   CHECK(upload_state IN ('pending','uploaded','failed'))
);
CREATE TABLE IF NOT EXISTS annotation_history (
 id BIGSERIAL PRIMARY KEY, photo_id TEXT NOT NULL, saved_at TEXT NOT NULL,
 annotation_json TEXT NOT NULL, review_status TEXT NOT NULL,
 FOREIGN KEY(photo_id) REFERENCES photos(photo_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS app_settings (setting_key TEXT PRIMARY KEY, setting_value TEXT NOT NULL);
"""


def is_postgres() -> bool:
    return settings.database_url.startswith(("postgres://", "postgresql://"))


if is_postgres():
    import psycopg
    from psycopg.rows import dict_row

    INTEGRITY_ERRORS = (psycopg.IntegrityError,)
else:
    psycopg = None
    dict_row = None
    INTEGRITY_ERRORS = (sqlite3.IntegrityError,)


class Connection:
    """Small common connection surface for the existing SQLite and Postgres queries."""

    def __init__(self, raw, postgres: bool):
        self.raw = raw
        self.postgres = postgres

    def execute(self, statement: str, parameters=()):
        if self.postgres:
            statement = statement.replace("?", "%s")
        return self.raw.execute(statement, parameters)

    def __enter__(self):
        self.raw.__enter__()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return self.raw.__exit__(exc_type, exc_value, traceback)
        finally:
            if not self.postgres:
                self.raw.close()

    def commit(self):
        self.raw.commit()

    def rollback(self):
        self.raw.rollback()

    def close(self):
        self.raw.close()


def connect() -> Connection:
    if is_postgres():
        database_url = settings.database_url
        if database_url.startswith("postgres://"):
            database_url = "postgresql://" + database_url[len("postgres://"):]
        raw = psycopg.connect(database_url, row_factory=dict_row, connect_timeout=10)
        return Connection(raw, postgres=True)

    path = settings.db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = sqlite3.connect(path, timeout=15)
    raw.row_factory = sqlite3.Row
    raw.execute("PRAGMA foreign_keys=ON")
    raw.execute("PRAGMA journal_mode=WAL")
    return Connection(raw, postgres=False)


def initialize() -> None:
    with connect() as db:
        schema = POSTGRES_SCHEMA if is_postgres() else SQLITE_SCHEMA
        for statement in schema.split(";"):
            if statement.strip():
                db.execute(statement)


@contextmanager
def transaction():
    db = connect()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
