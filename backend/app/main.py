import json
import logging
import secrets
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from uuid import uuid4
from contextlib import asynccontextmanager

from dotenv import load_dotenv
load_dotenv()

from argon2 import PasswordHasher
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response
from PIL import Image, ImageOps, UnidentifiedImageError
from googleapiclient.errors import HttpError
from starlette.middleware.sessions import SessionMiddleware

from .config import settings
from .db import INTEGRITY_ERRORS, connect, initialize, transaction
from .security import check_login_rate, check_submission_rate, require_researcher, require_same_origin, verify_password
from .services import google_drive_service as drive
from .services.google_drive_service import DriveNotReady
from .domain import CSV_COLUMNS, empty_annotation, make_csv

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("skin_ai_collector")
MAX_PIXELS = 40_000_000
DEFAULT_RETENTION_POLICY = "Photos are retained until a researcher deletes them or the study retention period ends."


def collection_is_ready() -> bool:
    """Fail closed when consent details or production storage have not been verified."""
    if not settings.collection_enabled:
        return False

    contact = settings.consent_contact.strip()
    contact_lower = contact.lower()
    if (not contact or "update this contact" in contact_lower or "your email" in contact_lower
            or contact_lower.endswith(("@example.com", "@example.test", "@example.org"))):
        return False
    retention = settings.retention_policy.strip()
    if (not retention or retention == DEFAULT_RETENTION_POLICY
            or any(marker in retention.lower() for marker in ("todo", "tbd", "replace this", "update this"))):
        return False
    if settings.minimum_age < 18 or not settings.consent_version.strip():
        return False

    # Development tests use mocked storage. Production requires durable metadata,
    # OAuth credentials, a valid token, and an admin-verified private Drive folder.
    if settings.app_env != "production":
        return True
    if (not settings.database_url.startswith(("postgres://", "postgresql://"))
            or not settings.google_client_id or not settings.google_client_secret
            or not settings.allowed_origin.startswith("https://")):
        return False
    try:
        with connect() as db:
            db.execute("SELECT 1").fetchone()
            saved_folder = db.execute(
                "SELECT setting_value FROM app_settings WHERE setting_key='drive_folder_id'"
            ).fetchone()
            verified_folder = db.execute(
                "SELECT setting_value FROM app_settings WHERE setting_key='drive_verified_folder_id'"
            ).fetchone()
        folder_id = settings.drive_folder_id or (saved_folder["setting_value"] if saved_folder else "")
        if not folder_id or not verified_folder or verified_folder["setting_value"] != folder_id:
            return False
        drive.credentials()
    except Exception as exc:
        logger.info("Collection readiness check failed (%s)", type(exc).__name__)
        return False
    return True

@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.app_env == "production":
        if len(settings.secret_key) < 32 or not settings.researcher_password_hash:
            raise RuntimeError("Production requires APP_SECRET_KEY and RESEARCHER_PASSWORD_HASH.")
        if not settings.google_redirect_uri.startswith("https://"):
            raise RuntimeError("Production OAuth redirect URI must use HTTPS.")
    initialize()
    yield


app = FastAPI(title="Skin AI Data Collector API", docs_url=None if settings.app_env == "production" else "/api/docs",
              redoc_url=None, openapi_url=None if settings.app_env == "production" else "/api/openapi.json", lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key or "development-only-change-me",
                   session_cookie="skinai_session", same_site="lax", https_only=settings.app_env == "production",
                   max_age=60 * 60 * 8)


@app.middleware("http")
async def security_headers_and_body_limit(request: Request, call_next):
    content_length = request.headers.get("content-length")
    if request.url.path == "/api/submissions" and content_length:
        try:
            if int(content_length) > settings.max_upload_bytes + 256_000:
                return JSONResponse({"detail": "This image exceeds the upload limit."}, status_code=413)
        except ValueError:
            return JSONResponse({"detail": "Invalid content length."}, status_code=400)
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Permissions-Policy", "camera=(self), microphone=()")
    if request.url.path.startswith("/api/admin/") or request.url.path == "/api/submissions":
        response.headers.setdefault("Cache-Control", "private, no-store, max-age=0")
    if settings.app_env == "production":
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        response.headers.setdefault("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob: data:; media-src 'self' blob:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
    return response


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/public-config")
def public_config():
    configured = collection_is_ready()
    return {"consentVersion": settings.consent_version, "minimumAge": settings.minimum_age,
            "contact": settings.consent_contact, "retention": settings.retention_policy,
            "maxUploadBytes": settings.max_upload_bytes, "ready": configured}


@app.post("/api/admin/login")
async def login(request: Request):
    require_same_origin(request)
    check_login_rate(request)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid sign-in request.")
    username, password = body.get("username", ""), body.get("password", "")
    if not isinstance(username, str) or not isinstance(password, str) or len(password) > 1024:
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    if username != settings.researcher_username or not verify_password(password):
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    request.session.clear()
    request.session["researcher"] = settings.researcher_username
    request.session["csrf"] = secrets.token_urlsafe(32)
    return {"authenticated": True}


@app.post("/api/admin/logout")
def logout(request: Request, _: str = Depends(require_researcher)):
    require_same_origin(request)
    request.session.clear()
    return {"authenticated": False}


@app.get("/api/admin/me")
def me(request: Request):
    return {"authenticated": bool(request.session.get("researcher")), "csrf": request.session.get("csrf")}


@app.get("/api/admin/status")
def admin_status(_: str = Depends(require_researcher)):
    try:
        ready = False
        if drive.has_credentials():
            try:
                drive.credentials()
                ready = True
            except Exception:
                ready = False
        with connect() as db:
            saved_folder = db.execute("SELECT setting_value FROM app_settings WHERE setting_key='drive_folder_id'").fetchone()
        return {"drive_connected": ready, "folder_configured": bool(settings.drive_folder_id or saved_folder),
                "oauth_configured": bool(settings.google_client_id and settings.google_client_secret),
                "drive_folder_name": drive.FOLDER_NAME}
    except Exception:
        return {"drive_connected": False, "folder_configured": False, "oauth_configured": False}


@app.post("/api/admin/google-drive/authorize")
def authorize_google(request: Request, _: str = Depends(require_researcher)):
    require_same_origin(request)
    flow = drive.create_flow()
    state = secrets.token_urlsafe(32)
    request.session["oauth_state"] = state
    url, _ = flow.authorization_url(state=state, access_type="offline", prompt="consent select_account")
    return JSONResponse({"authorization_url": url}, headers={"Cache-Control": "no-store"})


@app.get("/api/admin/google-drive/callback")
def google_callback(request: Request, state: str = "", code: str = "", error: str = ""):
    expected = request.session.pop("oauth_state", None)
    if not expected or not secrets.compare_digest(expected, state):
        raise HTTPException(status_code=400, detail="Google authorization state did not match. Start the connection again.")
    if error or not code:
        raise HTTPException(status_code=400, detail="Google authorization was cancelled or denied.")
    try:
        flow = drive.create_flow(state=state)
        flow.fetch_token(code=code)
        creds = flow.credentials
        if not creds.refresh_token:
            raise DriveNotReady("Google did not return offline access. Reconnect and approve access.")
        drive.save_credentials(creds)
        folder_id = drive.find_or_create_folder()
        with transaction() as db:
            db.execute("DELETE FROM app_settings WHERE setting_key='drive_verified_folder_id'")
        request.session["drive_connected"] = True
        request.session["drive_folder_id"] = folder_id
    except Exception as exc:
        logger.warning("Google Drive connection failed (%s)", type(exc).__name__)
        raise HTTPException(status_code=502, detail="Could not finish Google Drive setup. Check OAuth settings and try again.")
    return HTMLResponse("<h1>Google Drive connected</h1><p>Return to the researcher dashboard.</p>",
                        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})


@app.post("/api/admin/google-drive/verify")
def verify_drive(request: Request, _: str = Depends(require_researcher)):
    require_same_origin(request)
    try:
        result = drive.verify_folder()
        with transaction() as db:
            db.execute("INSERT INTO app_settings(setting_key,setting_value) VALUES('drive_verified_folder_id',?) "
                       "ON CONFLICT(setting_key) DO UPDATE SET setting_value=excluded.setting_value",
                       (result["folder_id"],))
        # The folder ID is an administrative setting, but not exposed to the public site.
        return {key: value for key, value in result.items() if key != "folder_id"}
    except Exception as exc:
        with transaction() as db:
            db.execute("DELETE FROM app_settings WHERE setting_key='drive_verified_folder_id'")
        logger.warning("Drive verification failed (%s)", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Google Drive is unavailable or authorization needs attention.")


@app.post("/api/admin/storage/reconcile")
def reconcile_uploads(request: Request, _: str = Depends(require_researcher)):
    require_same_origin(request)
    with connect() as db:
        candidates = db.execute("SELECT photo_id,idempotency_key FROM photos WHERE upload_state IN ('pending','failed')").fetchall()
    recovered = 0
    for row in candidates:
        try:
            remote = drive.find_by_idempotency(row["idempotency_key"])
        except Exception as exc:
            logger.warning("Drive reconciliation failed (%s)", type(exc).__name__)
            raise HTTPException(status_code=503, detail="Google Drive is unavailable; upload recovery could not finish.")
        if remote:
            with transaction() as db:
                db.execute("UPDATE photos SET drive_file_id=?,file_size=?,upload_state='uploaded' WHERE photo_id=?",
                           (remote["id"], int(remote.get("size", 0)), row["photo_id"]))
            recovered += 1
    return {"recovered": recovered, "checked": len(candidates)}


def sanitize_image(data: bytes, supplied_type: str) -> tuple[bytes, str, int, int]:
    try:
        image = Image.open(BytesIO(data))
        actual = image.format
        expected = {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}.get(supplied_type)
        if not expected or actual != expected:
            raise ValueError("Choose a valid JPG, PNG, or WebP image.")
        if image.width * image.height > MAX_PIXELS:
            raise ValueError("This image has too many pixels.")
        image.verify()
        image = Image.open(BytesIO(data))
        image = ImageOps.exif_transpose(image)
        width, height = image.size
        if width < 320 or height < 320:
            raise ValueError("Choose an image at least 320 × 320 pixels.")
        # Re-encoding drops EXIF/GPS and other embedded metadata before the photo reaches Drive.
        if supplied_type == "image/jpeg":
            image = image.convert("RGB")
            output_type, fmt, options = "image/jpeg", "JPEG", {"quality": 92, "optimize": True}
        elif supplied_type == "image/png":
            image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
            output_type, fmt, options = "image/png", "PNG", {"optimize": True}
        else:
            image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
            output_type, fmt, options = "image/webp", "WEBP", {"quality": 90, "method": 4}
        stream = BytesIO()
        image.save(stream, format=fmt, **options)
        result = stream.getvalue()
        if len(result) > settings.max_upload_bytes:
            raise ValueError("The processed photo exceeds the upload limit. Choose a smaller image.")
        return result, output_type, width, height
    except ValueError:
        raise
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError("The selected file could not be read as a valid image.") from exc


@app.post("/api/submissions")
async def submit_photo(request: Request, image: UploadFile = File(...), consent_confirmed: bool = Form(...),
                       adult_confirmed: bool = Form(...), consent_version: str = Form(...),
                       consent_id: str = Form(...),
                       idempotency_key: str = Header(..., alias="Idempotency-Key")):
    require_same_origin(request)
    if not collection_is_ready():
        raise HTTPException(status_code=503, detail="Photo collection is not enabled yet. Please try again later.")
    if not consent_confirmed or not adult_confirmed or consent_version != settings.consent_version:
        raise HTTPException(status_code=400, detail="Current consent and adult confirmation are required.")
    if len(consent_id) > 80 or not all(c.isalnum() or c in "-_" for c in consent_id):
        raise HTTPException(status_code=400, detail="Invalid consent reference.")
    if len(idempotency_key) > 80 or not all(c.isalnum() or c in "-_" for c in idempotency_key):
        raise HTTPException(status_code=400, detail="Invalid submission reference.")
    check_submission_rate(request)
    if image.content_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise HTTPException(status_code=415, detail="Choose a JPG, PNG, or WebP image.")
    data = await image.read(settings.max_upload_bytes + 1)
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="This image exceeds the upload limit. Choose a smaller file.")
    try:
        safe_data, mime_type, width, height = sanitize_image(data, image.content_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    photo_id, participant_id = uuid4().hex, uuid4().hex
    now = datetime.now(timezone.utc).isoformat()
    try:
        # Recover a previous ambiguous attempt first: Drive's private appProperties key prevents duplicate uploads.
        with connect() as db:
            prior = db.execute("SELECT photo_id,upload_state,created_at FROM photos WHERE idempotency_key=?", (idempotency_key,)).fetchone()
        if prior and prior["upload_state"] in {"failed", "pending"}:
            try:
                recovered = drive.find_by_idempotency(idempotency_key)
            except Exception:
                recovered = None
            if recovered:
                with transaction() as db:
                    db.execute("UPDATE photos SET drive_file_id=?,file_size=?,upload_state='uploaded' WHERE photo_id=?",
                               (recovered["id"], int(recovered.get("size", 0)), prior["photo_id"]))
                return {"photo_id": prior["photo_id"], "status": "received"}
            prior_age = (datetime.now(timezone.utc) - datetime.fromisoformat(prior["created_at"])).total_seconds()
            if prior["upload_state"] == "pending" and prior_age < 600:
                raise HTTPException(status_code=409, detail="This submission is still being processed. Please wait before retrying.")
            with transaction() as db:
                db.execute("DELETE FROM photos WHERE photo_id=?", (prior["photo_id"],))
        with transaction() as db:
            existing = db.execute("SELECT photo_id,upload_state FROM photos WHERE idempotency_key=?", (idempotency_key,)).fetchone()
            if existing:
                if existing["upload_state"] == "uploaded":
                    return {"photo_id": existing["photo_id"], "status": "received"}
                raise HTTPException(status_code=409, detail="This submission is already being processed. Please wait before retrying.")
            db.execute("INSERT INTO photos(photo_id,participant_id,mime_type,file_size,image_width,image_height,created_at,consent_version,consent_timestamp,consent_id,consent_confirmed,adult_confirmed,annotation_json,idempotency_key) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                       (photo_id, participant_id, mime_type, len(safe_data), width, height, now, consent_version, now, consent_id, 1, 1,
                        json.dumps(empty_annotation(), separators=(",", ":")), idempotency_key))
    except HTTPException:
        raise
    except INTEGRITY_ERRORS:
        with connect() as db:
            existing = db.execute("SELECT photo_id,upload_state FROM photos WHERE idempotency_key=?", (idempotency_key,)).fetchone()
        if existing and existing["upload_state"] == "uploaded":
            return {"photo_id": existing["photo_id"], "status": "received"}
        raise HTTPException(status_code=409, detail="This submission is already being processed. Please wait before retrying.")
    try:
        uploaded = drive.upload_photo(photo_id, idempotency_key, safe_data, mime_type)
        with transaction() as db:
            db.execute("UPDATE photos SET drive_file_id=?,file_size=?,upload_state='uploaded' WHERE photo_id=?",
                       (uploaded["id"], int(uploaded.get("size", len(safe_data))), photo_id))
        return {"photo_id": photo_id, "status": "received"}
    except Exception as exc:
        # Keep a recoverable metadata row; the next identical request reconciles via Drive appProperties.
        with transaction() as db:
            db.execute("UPDATE photos SET upload_state='failed' WHERE photo_id=?", (photo_id,))
        logger.warning("Photo upload failed for %s (%s)", photo_id, type(exc).__name__)
        if isinstance(exc, DriveNotReady):
            raise HTTPException(status_code=503, detail="Photo storage is not connected. Please try again later.")
        if isinstance(exc, HttpError) and getattr(exc, "resp", None) is not None:
            if exc.resp.status == 403:
                raise HTTPException(status_code=507, detail="Google Drive storage quota or permissions prevented this upload.")
            if exc.resp.status == 429:
                raise HTTPException(status_code=503, detail="Google Drive is temporarily rate limiting uploads. Retry shortly.")
        raise HTTPException(status_code=503, detail="Photo storage is temporarily unavailable. Retry the same submission shortly.")


def photo_record(row) -> dict:
    annotation = json.loads(row["annotation_json"])
    annotation.update({"person_id": row["participant_id"], "photo_id": row["photo_id"]})
    return {"photoId": row["photo_id"], "participantId": row["participant_id"],
            "mimeType": row["mime_type"], "fileSize": row["file_size"],
            "imageWidth": row["image_width"], "imageHeight": row["image_height"],
            "createdAt": row["created_at"], "reviewStatus": row["review_status"],
            "rejectionReason": row["rejection_reason"], "annotation": annotation,
            "qualityNotes": ["File format, size, dimensions, and image data validated; embedded metadata removed."],
            "qualityStatus": "basic_checks_passed"}


@app.get("/api/admin/photos")
def list_photos(status: str = "all", query: str = "", _: str = Depends(require_researcher)):
    if status not in {"all", "pending", "approved", "rejected"}:
        raise HTTPException(status_code=400, detail="Unknown review status.")
    with connect() as db:
        where = "upload_state='uploaded'"
        params: list[str] = []
        if status != "all":
            where += " AND review_status=?"
            params.append(status)
        if query:
            where += " AND photo_id LIKE ?"
            params.append(f"%{query[:80]}%")
        rows = db.execute(f"SELECT * FROM photos WHERE {where} ORDER BY created_at DESC", params).fetchall()
        return [photo_record(row) for row in rows]


@app.get("/api/admin/photos/{photo_id}/image")
def get_image(photo_id: str, _: str = Depends(require_researcher)):
    with connect() as db:
        row = db.execute("SELECT drive_file_id,mime_type FROM photos WHERE photo_id=? AND upload_state='uploaded'", (photo_id,)).fetchone()
    if not row or not row["drive_file_id"]:
        raise HTTPException(status_code=404, detail="Photo not found.")
    try:
        data = drive.download_photo(row["drive_file_id"])
    except Exception as exc:
        logger.warning("Drive image retrieval failed (%s)", type(exc).__name__)
        if isinstance(exc, HttpError) and getattr(exc, "resp", None) is not None and exc.resp.status == 403:
            raise HTTPException(status_code=507, detail="Google Drive storage or authorization needs attention.")
        raise HTTPException(status_code=503, detail="Photo storage is temporarily unavailable.")
    return Response(data, media_type=row["mime_type"], headers={"Cache-Control": "private, no-store, max-age=0",
                    "Pragma": "no-cache", "X-Content-Type-Options": "nosniff", "Content-Disposition": "inline"})


@app.patch("/api/admin/photos/{photo_id}")
async def update_photo(photo_id: str, request: Request, _: str = Depends(require_researcher)):
    require_same_origin(request)
    try:
        body = await request.json()
        status, reason = body["reviewStatus"], str(body.get("rejectionReason", ""))[:1000]
        annotation = body["annotation"]
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid review data.")
    if status not in {"pending", "approved", "rejected"} or not isinstance(annotation, dict):
        raise HTTPException(status_code=400, detail="Invalid review data.")
    allowed = set(CSV_COLUMNS)
    clean = {key: str(annotation.get(key, ""))[:500] for key in allowed}
    with transaction() as db:
        row = db.execute("SELECT participant_id FROM photos WHERE photo_id=? AND upload_state='uploaded'", (photo_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Photo not found.")
        clean["person_id"], clean["photo_id"] = row["participant_id"], photo_id
        saved_at = datetime.now(timezone.utc).isoformat()
        db.execute("UPDATE photos SET review_status=?,rejection_reason=?,annotation_json=? WHERE photo_id=?",
                   (status, reason if status == "rejected" else "", json.dumps(clean, ensure_ascii=False), photo_id))
        db.execute("INSERT INTO annotation_history(photo_id,saved_at,annotation_json,review_status) VALUES(?,?,?,?)",
                   (photo_id, saved_at, json.dumps(clean, ensure_ascii=False), status))
    return {"saved": True}


@app.delete("/api/admin/photos/{photo_id}")
def delete_photo(photo_id: str, request: Request, _: str = Depends(require_researcher)):
    require_same_origin(request)
    with connect() as db:
        row = db.execute("SELECT drive_file_id FROM photos WHERE photo_id=?", (photo_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Photo not found.")
    if row["drive_file_id"]:
        try:
            drive.delete_photo(row["drive_file_id"])
        except Exception as exc:
            logger.warning("Drive deletion failed (%s)", type(exc).__name__)
            if isinstance(exc, HttpError) and getattr(exc, "resp", None) is not None and exc.resp.status == 403:
                raise HTTPException(status_code=507, detail="Google Drive authorization or quota needs attention. The metadata was retained.")
            raise HTTPException(status_code=503, detail="Could not delete the Drive photo. Metadata was retained.")
    with transaction() as db:
        db.execute("DELETE FROM photos WHERE photo_id=?", (photo_id,))
    return {"deleted": True}


@app.get("/api/admin/export/labels1.csv")
def export_csv(_: str = Depends(require_researcher)):
    with connect() as db:
        rows = db.execute("SELECT participant_id,photo_id,annotation_json FROM photos WHERE upload_state='uploaded' AND review_status='approved' ORDER BY created_at").fetchall()
    data = make_csv([{**json.loads(row["annotation_json"]), "person_id": row["participant_id"], "photo_id": row["photo_id"]} for row in rows])
    return Response(data.encode("utf-8"), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="labels1.csv"', "Cache-Control": "private, no-store"})


frontend = Path(__file__).resolve().parents[2] / "dist"
if frontend.is_dir():
    app.mount("/", __import__("fastapi.staticfiles", fromlist=["StaticFiles"]).StaticFiles(directory=frontend, html=True), name="frontend")
