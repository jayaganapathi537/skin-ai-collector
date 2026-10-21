import os
from dataclasses import dataclass
from pathlib import Path


def _google_redirect_uri() -> str:
    configured = os.getenv("GOOGLE_OAUTH_REDIRECT_URI", "").strip()
    if configured:
        return configured
    production_host = os.getenv("VERCEL_PROJECT_PRODUCTION_URL", "").strip()
    if production_host:
        return f"https://{production_host}/api/admin/google-drive/callback"
    return "http://localhost:8000/api/admin/google-drive/callback"


def _allowed_origin() -> str:
    configured = os.getenv("ALLOWED_ORIGIN", "").strip()
    if configured:
        return configured
    production_host = os.getenv("VERCEL_PROJECT_PRODUCTION_URL", "").strip()
    return f"https://{production_host}" if production_host else "http://localhost:5173"


@dataclass(frozen=True)
class Settings:
    app_env: str = os.getenv("APP_ENV", "development")
    secret_key: str = os.getenv("APP_SECRET_KEY", "")
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./data/skin_ai_collector.db")
    researcher_username: str = os.getenv("RESEARCHER_USERNAME", "researcher")
    researcher_password_hash: str = os.getenv("RESEARCHER_PASSWORD_HASH", "")
    google_client_id: str = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "")
    google_client_secret: str = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "")
    google_redirect_uri: str = _google_redirect_uri()
    drive_folder_id: str = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "")
    token_file: Path = Path(os.getenv("GOOGLE_TOKEN_FILE", "./data/google_oauth_token.json"))
    max_upload_bytes: int = int(os.getenv("MAX_UPLOAD_BYTES", str(5 * 1024 * 1024)))
    allowed_origin: str = _allowed_origin()
    consent_version: str = os.getenv("CONSENT_VERSION", "2026-10")
    minimum_age: int = int(os.getenv("MINIMUM_AGE", "18"))
    collection_enabled: bool = os.getenv("COLLECTION_ENABLED", "false").lower() == "true"
    consent_contact: str = os.getenv("CONSENT_CONTACT", "Update this contact before collecting submissions")
    retention_policy: str = os.getenv("RETENTION_POLICY", "Photos are retained until a researcher deletes them or the study retention period ends.")

    @property
    def db_path(self) -> Path:
        if self.database_url.startswith(("postgres://", "postgresql://")):
            raise ValueError("DATABASE_URL points to PostgreSQL, not a local SQLite file.")
        prefix = "sqlite:///"
        if not self.database_url.startswith(prefix):
            raise ValueError("DATABASE_URL must be a local SQLite or PostgreSQL connection URL.")
        path = Path(self.database_url[len(prefix):])
        return path if path.is_absolute() else Path.cwd() / path


settings = Settings()
