"""Authentication endpoints: login and logout."""
from fastapi import APIRouter, HTTPException, Request, Response

from app import auth, rules
from app.models import LoginOut, LoginRequest, StatusOut, db

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post(
    "/login",
    response_model=LoginOut,
    responses={
        401: {"description": "Unknown username or wrong password."},
        403: {"description": "The account is locked ('Account locked')."},
        422: {"description": "Malformed body: username or password missing."},
    },
)
def login(body: LoginRequest, request: Request, response: Response):
    """Sign in with username and password.

    Positive scenario: a valid username/password pair returns 200, sets the
    session cookie, and returns the user's id, username, and role.

    Negative scenarios: an unknown username or a wrong password returns 401;
    a locked account returns 403 with detail "Account locked" even when the
    password is correct; a body missing username or password returns 422.
    """
    with db() as conn:
        user = conn.execute("SELECT * FROM users WHERE username = ?",
                            (body.username,)).fetchone()
    if user is None or not auth.verify_password(body.password,
                                                user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if user["is_locked"]:
        raise HTTPException(status_code=403, detail=rules.LOCKED_MESSAGE)
    auth.create_session(user["id"], user["username"], user["role"], response)
    return LoginOut(id=user["id"], username=user["username"],
                    role=user["role"])


@router.post(
    "/logout",
    response_model=StatusOut,
    responses={
        401: {"description": "No active session to log out."},
    },
)
def logout(request: Request, response: Response):
    """End the current session.

    Positive scenario: with a valid session cookie, returns 200 and clears
    the session; subsequent authenticated calls return 401.

    Negative scenario: without an active session, returns 401.
    """
    if auth.get_session(request) is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    auth.destroy_session(request, response)
    return StatusOut(status="logged out")
