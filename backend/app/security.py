import hmac
import secrets
import threading
import time
from hashlib import sha256

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import HTTPException, Request

from .config import settings

hasher = PasswordHasher()
_rate_limit_salt = secrets.token_bytes(32)
_rate_limit_lock = threading.Lock()
_rate_limit_state: dict[tuple[str, str], tuple[int, int]] = {}


def require_researcher(request: Request) -> str:
    user = request.session.get("researcher")
    if not user or not hmac.compare_digest(str(user), settings.researcher_username):
        raise HTTPException(status_code=401, detail="Researcher sign-in required.")
    return str(user)


def verify_password(password: str) -> bool:
    if not settings.researcher_password_hash:
        return False
    try:
        return hasher.verify(settings.researcher_password_hash, password)
    except (VerifyMismatchError, Exception):
        return False


def require_same_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if not origin or origin.rstrip("/") != settings.allowed_origin.rstrip("/"):
        raise HTTPException(status_code=403, detail="Request origin is not allowed.")


def _consume_rate_limit(request: Request, purpose: str, limit: int, window_seconds: int) -> None:
    ip = request.client.host if request.client else "unknown"
    key = hmac.new(_rate_limit_salt, ip.encode(), sha256).hexdigest()
    now = int(time.time())
    state_key = (purpose, key)
    with _rate_limit_lock:
        for old_key, (_, started) in list(_rate_limit_state.items()):
            if now - started >= window_seconds:
                _rate_limit_state.pop(old_key, None)
        count, started = _rate_limit_state.get(state_key, (0, now))
        if count >= limit and now - started < window_seconds:
            detail = "Submission limit reached. Please try again later." if purpose == "submission" else "Too many sign-in attempts. Try again later."
            raise HTTPException(status_code=429, detail=detail)
        if now - started >= window_seconds:
            count, started = 0, now
        if len(_rate_limit_state) >= 4096 and state_key not in _rate_limit_state:
            _rate_limit_state.clear()
        _rate_limit_state[state_key] = (count + 1, started)


def check_login_rate(request: Request) -> None:
    _consume_rate_limit(request, "login", 10, 900)


def check_submission_rate(request: Request) -> None:
    _consume_rate_limit(request, "submission", 12, 3600)
