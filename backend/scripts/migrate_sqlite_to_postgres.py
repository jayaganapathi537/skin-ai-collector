"""Copy the app's SQLite records into the DATABASE_URL PostgreSQL database."""

import argparse
import sqlite3
import sys
from pathlib import Path

from dotenv import load_dotenv

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

# Load the local settings first, then let `vercel env pull .env.local` override them.
load_dotenv(BACKEND_ROOT / ".env")
load_dotenv(REPO_ROOT / ".env.local", override=True)

from app.config import settings  # noqa: E402
from app.db import connect, initialize, is_postgres, transaction  # noqa: E402


TABLES = {
    "photos": [
        "photo_id", "participant_id", "drive_file_id", "mime_type", "file_size", "image_width",
        "image_height", "created_at", "consent_version", "consent_timestamp", "consent_id",
        "consent_confirmed", "adult_confirmed", "review_status", "rejection_reason", "annotation_json",
        "idempotency_key", "upload_state",
    ],
    "annotation_history": ["id", "photo_id", "saved_at", "annotation_json", "review_status"],
    "app_settings": ["setting_key", "setting_value"],
}


def copy_table(source: sqlite3.Connection, table: str, columns: list[str]) -> int:
    source_rows = source.execute(f"SELECT {', '.join(columns)} FROM {table}").fetchall()
    if not source_rows:
        return 0
    names = ", ".join(columns)
    marks = ", ".join("?" for _ in columns)
    if table == "app_settings":
        conflict = "ON CONFLICT(setting_key) DO UPDATE SET setting_value=excluded.setting_value"
    elif table == "photos":
        conflict = "ON CONFLICT(photo_id) DO NOTHING"
    else:
        conflict = "ON CONFLICT(id) DO NOTHING"
    with transaction() as target:
        for row in source_rows:
            target.execute(f"INSERT INTO {table} ({names}) VALUES ({marks}) {conflict}", tuple(row))
    return len(source_rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sqlite_path", type=Path, help="Path to the current local SQLite database")
    args = parser.parse_args()

    if not is_postgres():
        raise SystemExit("DATABASE_URL must be set to the Neon PostgreSQL connection string before migration.")
    if not args.sqlite_path.is_file():
        raise SystemExit(f"SQLite database not found: {args.sqlite_path}")

    source_uri = args.sqlite_path.resolve().as_uri() + "?mode=ro"
    source = sqlite3.connect(source_uri, uri=True)
    source.row_factory = sqlite3.Row
    try:
        initialize()
        counts = {table: copy_table(source, table, columns) for table, columns in TABLES.items()}
    finally:
        source.close()

    with transaction() as target:
        target.execute(
            "SELECT setval(pg_get_serial_sequence('annotation_history','id'), "
            "COALESCE(MAX(id), 1), MAX(id) IS NOT NULL) FROM annotation_history"
        )
    summary = ", ".join(f"{table}: {count}" for table, count in counts.items())
    print(f"Copied records into PostgreSQL ({summary}).")
    print("The Google Drive OAuth token is not copied; reconnect Drive from the deployed researcher dashboard.")


if __name__ == "__main__":
    main()
