from __future__ import annotations

import json
import os
import secrets
import tempfile
from io import BytesIO
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseUpload

from ..config import settings

SCOPES = ["https://www.googleapis.com/auth/drive.file"]
FOLDER_NAME = "Skin_AI_Collected_Photos"
APP_MARKER_KEY = "skinAiCollector"
APP_MARKER_VALUE = "v1"


class DriveNotReady(RuntimeError):
    pass


def oauth_client_config() -> dict[str, Any]:
    if not settings.google_client_id or not settings.google_client_secret:
        raise DriveNotReady("Google OAuth client is not configured.")
    return {"web": {"client_id": settings.google_client_id, "client_secret": settings.google_client_secret,
                     "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                     "token_uri": "https://oauth2.googleapis.com/token",
                     "redirect_uris": [settings.google_redirect_uri]}}


def create_flow(state: str | None = None) -> Flow:
    flow = Flow.from_client_config(oauth_client_config(), scopes=SCOPES, state=state)
    flow.redirect_uri = settings.google_redirect_uri
    return flow


def save_credentials(credentials: Credentials) -> None:
    database_url = getattr(settings, "database_url", "")
    if database_url.startswith(("postgres://", "postgresql://")):
        from ..db import transaction
        from .token_crypto import encrypt_token

        encrypted = encrypt_token(credentials.to_json(), settings.secret_key)
        with transaction() as db:
            db.execute(
                "INSERT INTO app_settings(setting_key,setting_value) VALUES(?,?) "
                "ON CONFLICT(setting_key) DO UPDATE SET setting_value=excluded.setting_value",
                ("google_oauth_token", encrypted),
            )
        return

    path = settings.token_file
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = credentials.to_json()
    fd, temp_name = tempfile.mkstemp(prefix="oauth-", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
        os.chmod(path, 0o600)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def has_credentials() -> bool:
    if getattr(settings, "database_url", "").startswith(("postgres://", "postgresql://")):
        from ..db import connect
        with connect() as db:
            row = db.execute("SELECT setting_value FROM app_settings WHERE setting_key='google_oauth_token'").fetchone()
        return bool(row)
    return settings.token_file.is_file()


def credentials() -> Credentials:
    if getattr(settings, "database_url", "").startswith(("postgres://", "postgresql://")):
        from ..db import connect
        from .token_crypto import decrypt_token

        with connect() as db:
            row = db.execute("SELECT setting_value FROM app_settings WHERE setting_key='google_oauth_token'").fetchone()
        if not row:
            raise DriveNotReady("Google Drive is not connected. Sign in from the researcher dashboard.")
        payload = decrypt_token(row["setting_value"], settings.secret_key)
        creds = Credentials.from_authorized_user_info(json.loads(payload), SCOPES)
    else:
        if not settings.token_file.is_file():
            raise DriveNotReady("Google Drive is not connected. Sign in from the researcher dashboard.")
        creds = Credentials.from_authorized_user_file(str(settings.token_file), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(GoogleRequest())
        save_credentials(creds)
    if not creds.valid:
        raise DriveNotReady("Google Drive authorization expired. Reconnect Google Drive from the researcher dashboard.")
    return creds


def client():
    return build("drive", "v3", credentials=credentials(), cache_discovery=False)


def find_or_create_folder() -> str:
    service = client()
    # drive.file can see files created by this OAuth application; it cannot discover arbitrary existing Drive folders.
    if settings.drive_folder_id:
        metadata = service.files().get(fileId=settings.drive_folder_id, fields="id,mimeType,trashed").execute()
        if metadata.get("mimeType") != "application/vnd.google-apps.folder" or metadata.get("trashed"):
            raise DriveNotReady("Configured Drive folder is missing or is not a folder.")
        return metadata["id"]
    from ..db import connect, transaction
    with connect() as db:
        configured = db.execute("SELECT setting_value FROM app_settings WHERE setting_key='drive_folder_id'").fetchone()
    if configured:
        return configured["setting_value"]
    query = (f"mimeType='application/vnd.google-apps.folder' and trashed=false and "
             f"appProperties has {{ key='{APP_MARKER_KEY}' and value='{APP_MARKER_VALUE}' }}")
    found = service.files().list(q=query, spaces="drive", pageSize=10, fields="files(id,name,mimeType)").execute().get("files", [])
    if found:
        folder_id = found[0]["id"]
        with transaction() as db:
            db.execute("INSERT INTO app_settings(setting_key,setting_value) VALUES('drive_folder_id',?) "
                       "ON CONFLICT(setting_key) DO UPDATE SET setting_value=excluded.setting_value", (folder_id,))
        return folder_id
    folder = service.files().create(body={"name": FOLDER_NAME, "mimeType": "application/vnd.google-apps.folder",
                                         "appProperties": {APP_MARKER_KEY: APP_MARKER_VALUE}}, fields="id").execute()
    with transaction() as db:
        db.execute("INSERT INTO app_settings(setting_key,setting_value) VALUES('drive_folder_id',?) "
                   "ON CONFLICT(setting_key) DO UPDATE SET setting_value=excluded.setting_value", (folder["id"],))
    return folder["id"]


def verify_folder() -> dict[str, Any]:
    service = client()
    folder_id = find_or_create_folder()
    probe_name = f".skin-ai-collector-verify-{secrets.token_hex(8)}.txt"
    probe = service.files().create(body={"name": probe_name, "mimeType": "text/plain", "parents": [folder_id],
                                         "appProperties": {APP_MARKER_KEY: APP_MARKER_VALUE}},
                                   media_body=MediaIoBaseUpload(BytesIO(b"private folder verification"), mimetype="text/plain"),
                                   fields="id,name").execute()
    try:
        result = service.files().list(q=f"'{folder_id}' in parents and name='{probe_name}' and trashed=false", spaces="drive", pageSize=10,
                                      fields="files(id,name,mimeType)").execute()
        visible = any(item.get("id") == probe["id"] for item in result.get("files", []))
        if not visible:
            raise DriveNotReady("The Drive folder was created, but the app could not list its own file.")
    finally:
        service.files().delete(fileId=probe["id"]).execute()
    return {"connected": True, "folder_id": folder_id, "folder_name": FOLDER_NAME,
            "can_upload": True, "can_list": True, "verification_file_removed": True}


def find_by_idempotency(key: str) -> dict[str, Any] | None:
    query = (f"'{find_or_create_folder()}' in parents and trashed=false and "
             f"appProperties has {{ key='submissionKey' and value='{key}' }}")
    files = client().files().list(q=query, spaces="drive", pageSize=1,
                                  fields="files(id,name,mimeType,size)").execute().get("files", [])
    return files[0] if files else None


def upload_photo(photo_id: str, key: str, data: bytes, mime_type: str) -> dict[str, Any]:
    existing = find_by_idempotency(key)
    if existing:
        return existing
    folder_id = find_or_create_folder()
    media = MediaIoBaseUpload(BytesIO(data), mimetype=mime_type, resumable=True)
    body = {"name": f"{photo_id}.{ {'image/jpeg':'jpg','image/png':'png','image/webp':'webp'}[mime_type] }",
            "mimeType": mime_type, "parents": [folder_id],
            "appProperties": {"submissionKey": key, "photoId": photo_id}}
    return client().files().create(body=body, media_body=media, fields="id,name,mimeType,size").execute()


def download_photo(file_id: str) -> bytes:
    from googleapiclient.http import MediaIoBaseDownload
    stream = BytesIO()
    downloader = MediaIoBaseDownload(stream, client().files().get_media(fileId=file_id))
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return stream.getvalue()


def delete_photo(file_id: str) -> None:
    try:
        client().files().delete(fileId=file_id).execute()
    except HttpError as exc:
        if getattr(exc, "resp", None) is None or exc.resp.status != 404:
            raise
