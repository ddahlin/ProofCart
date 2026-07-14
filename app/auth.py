"""Cookie-based server-side sessions and role checks.

The cookie carries only a signed opaque token; all session state (user id,
role, last-activity timestamp) lives server-side. Sessions expire after
rules.SESSION_TTL_SECONDS of inactivity.
"""
import hashlib
import os
import secrets
import time
from typing import Optional

from fastapi import Depends, HTTPException, Request, Response
from itsdangerous import BadSignature, URLSafeSerializer

from app import rules

SECRET_KEY = os.environ.get("SHOPCHECK_SECRET", "shopcheck-dev-secret-key")
COOKIE_NAME = "shopcheck_session"
_PASSWORD_SALT = "shopcheck.v1"

_serializer = URLSafeSerializer(SECRET_KEY, salt="shopcheck.session")

# token -> {"user_id", "username", "role", "last_activity"}
_sessions: dict[str, dict] = {}


def hash_password(password: str) -> str:
    return hashlib.sha256(f"{_PASSWORD_SALT}:{password}".encode()).hexdigest()


def verify_password(password: str, password_hash: str) -> bool:
    return secrets.compare_digest(hash_password(password), password_hash)


def create_session(user_id: int, username: str, role: str,
                   response: Response) -> None:
    token = secrets.token_urlsafe(32)
    _sessions[token] = {"user_id": user_id, "username": username,
                        "role": role, "last_activity": time.time()}
    response.set_cookie(COOKIE_NAME, _serializer.dumps(token), httponly=True,
                        samesite="lax")


def _token_from_request(request: Request) -> Optional[str]:
    cookie = request.cookies.get(COOKIE_NAME)
    if not cookie:
        return None
    try:
        return _serializer.loads(cookie)
    except BadSignature:
        return None


def get_session(request: Request) -> Optional[dict]:
    """Return the live session for this request, refreshing its activity
    timestamp, or None if absent/expired."""
    token = _token_from_request(request)
    if token is None:
        return None
    session = _sessions.get(token)
    if session is None:
        return None
    if time.time() - session["last_activity"] > rules.SESSION_TTL_SECONDS:
        del _sessions[token]
        return None
    session["last_activity"] = time.time()
    return session


def destroy_session(request: Request, response: Response) -> bool:
    token = _token_from_request(request)
    existed = token is not None and _sessions.pop(token, None) is not None
    response.delete_cookie(COOKIE_NAME)
    return existed


def clear_all_sessions() -> None:
    _sessions.clear()


def require_user(request: Request) -> dict:
    session = get_session(request)
    if session is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return session


def require_admin(session: dict = Depends(require_user)) -> dict:
    if session["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return session
