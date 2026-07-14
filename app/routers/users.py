"""User-management endpoints (admin) plus the own-profile endpoint."""
from fastapi import APIRouter, Depends, HTTPException, Response

from app import auth
from app.models import (NON_TERMINAL_STATUSES, UserCreate, UserOut,
                        UserUpdate, db, user_out)

router = APIRouter(prefix="/api/users", tags=["users"])

_AUTH_RESPONSES = {
    401: {"description": "Not authenticated (no session or session expired)."},
    403: {"description": "Authenticated but not an administrator."},
}


@router.get(
    "",
    response_model=list[UserOut],
    responses=_AUTH_RESPONSES,
)
def list_users(session: dict = Depends(auth.require_admin)):
    """List all user accounts (admin only).

    Positive scenario: an administrator receives every account with username,
    role, and locked state.

    Negative scenarios: an anonymous caller receives 401; a signed-in
    customer receives 403.
    """
    with db() as conn:
        rows = conn.execute("SELECT * FROM users ORDER BY id").fetchall()
    return [user_out(r) for r in rows]


@router.post(
    "",
    response_model=UserOut,
    status_code=201,
    responses={
        **_AUTH_RESPONSES,
        409: {"description": "The username is already taken."},
        422: {"description": "Username violates BR-4 (3-20 chars, letters/"
                             "digits/underscore) or password violates BR-5 "
                             "(min 8 chars, a letter and a digit)."},
    },
)
def create_user(body: UserCreate, session: dict = Depends(auth.require_admin)):
    """Create a user account (admin only).

    Positive scenario: a valid username, password, and role returns 201 and
    the new user can sign in immediately.

    Negative scenarios: a duplicate username returns 409; a username or
    password violating the business rules returns 422; anonymous callers get
    401 and customers get 403.
    """
    with db() as conn:
        exists = conn.execute("SELECT id FROM users WHERE username = ?",
                              (body.username,)).fetchone()
        if exists:
            raise HTTPException(status_code=409,
                                detail="Username already exists")
        cur = conn.execute(
            "INSERT INTO users (username, password_hash, role, is_locked, "
            "created_at) VALUES (?, ?, ?, 0, datetime('now'))",
            (body.username, auth.hash_password(body.password),
             body.role.value))
        row = conn.execute("SELECT * FROM users WHERE id = ?",
                           (cur.lastrowid,)).fetchone()
    return user_out(row)


@router.get(
    "/me",
    response_model=UserOut,
    responses={401: {"description": "Not authenticated."}},
)
def get_me(session: dict = Depends(auth.require_user)):
    """Return the signed-in user's own profile.

    Positive scenario: any authenticated user (admin or customer) receives
    their own id, username, and role.

    Negative scenario: an anonymous caller receives 401.
    """
    with db() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?",
                           (session["user_id"],)).fetchone()
    if row is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user_out(row)


@router.get(
    "/{user_id}",
    response_model=UserOut,
    responses={
        **_AUTH_RESPONSES,
        404: {"description": "No user with this id."},
        422: {"description": "The id is not an integer."},
    },
)
def get_user(user_id: int, session: dict = Depends(auth.require_admin)):
    """Fetch a single user account by id (admin only).

    Positive scenario: an administrator requests an existing id and receives
    the account.

    Negative scenarios: an unknown id returns 404; a non-integer id returns
    422; anonymous callers get 401 and customers get 403.
    """
    with db() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?",
                           (user_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user_out(row)


@router.put(
    "/{user_id}",
    response_model=UserOut,
    responses={
        **_AUTH_RESPONSES,
        404: {"description": "No user with this id."},
        422: {"description": "New password violates BR-5, or the id/role "
                             "value is malformed."},
    },
)
def update_user(user_id: int, body: UserUpdate,
                session: dict = Depends(auth.require_admin)):
    """Update a user's password, role, or locked state (admin only).

    Positive scenario: an administrator locks an account or resets a
    password and the change takes effect immediately.

    Negative scenarios: an unknown id returns 404; an invalid new password
    returns 422; anonymous callers get 401 and customers get 403.
    """
    with db() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?",
                           (user_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="User not found")
        if body.password is not None:
            conn.execute("UPDATE users SET password_hash = ? WHERE id = ?",
                         (auth.hash_password(body.password), user_id))
        if body.role is not None:
            conn.execute("UPDATE users SET role = ? WHERE id = ?",
                         (body.role.value, user_id))
        if body.is_locked is not None:
            conn.execute("UPDATE users SET is_locked = ? WHERE id = ?",
                         (1 if body.is_locked else 0, user_id))
        row = conn.execute("SELECT * FROM users WHERE id = ?",
                           (user_id,)).fetchone()
    return user_out(row)


@router.delete(
    "/{user_id}",
    status_code=204,
    responses={
        **_AUTH_RESPONSES,
        404: {"description": "No user with this id."},
        409: {"description": "The user still has pending or paid orders."},
    },
)
def delete_user(user_id: int, session: dict = Depends(auth.require_admin)):
    """Delete a user account (admin only).

    Positive scenario: deleting a user whose orders are all shipped or
    cancelled (or who has none) returns 204 and removes the account.

    Negative scenarios: a user with pending or paid orders returns 409 and
    is kept; an unknown id returns 404; anonymous callers get 401 and
    customers get 403.
    """
    with db() as conn:
        row = conn.execute("SELECT id FROM users WHERE id = ?",
                           (user_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="User not found")
        open_orders = conn.execute(
            f"SELECT COUNT(*) AS n FROM orders WHERE user_id = ? AND status "
            f"IN ({','.join('?' * len(NON_TERMINAL_STATUSES))})",
            (user_id, *NON_TERMINAL_STATUSES)).fetchone()["n"]
        if open_orders:
            raise HTTPException(
                status_code=409,
                detail="User has open (pending or paid) orders")
        conn.execute("DELETE FROM order_items WHERE order_id IN "
                     "(SELECT id FROM orders WHERE user_id = ?)", (user_id,))
        conn.execute("DELETE FROM orders WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM reports WHERE created_by = ?", (user_id,))
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    return Response(status_code=204)
