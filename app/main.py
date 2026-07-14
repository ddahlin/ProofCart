"""ShopCheck — FastAPI application: JSON API + server-rendered UI."""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app import auth, defects, seed
from app.models import StatusOut, db, init_db, order_out, product_out
from app.routers import auth as auth_router
from app.routers import orders as orders_router
from app.routers import products as products_router
from app.routers import reports as reports_router
from app.routers import users as users_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    seed.ensure_seeded()
    yield


app = FastAPI(
    title="ShopCheck",
    version="1.0.0",
    description="Internal e-commerce ordering portal: catalog, orders, "
                "user management, and reports.",
    lifespan=lifespan,
)

app.include_router(auth_router.router)
app.include_router(users_router.router)
app.include_router(products_router.router)
app.include_router(orders_router.router)
app.include_router(reports_router.router)

templates = Jinja2Templates(
    directory=os.path.join(os.path.dirname(__file__), "templates"))


@app.post(
    "/api/reset",
    response_model=StatusOut,
    tags=["test-support"],
)
def reset():
    """Restore the canonical seed data (test facility).

    Positive scenario: any caller, authenticated or not, receives 200 with
    {"status": "reset"} and the database is returned to its standard seed
    state (users, products, orders, reports with fixed ids).

    Negative scenarios: none — this endpoint is intentionally unrestricted
    and is only deployed to test environments.
    """
    seed.reset()
    return StatusOut(status="reset")


# ---------------------------------------------------------------------------
# Server-rendered UI
# ---------------------------------------------------------------------------

def _render(request: Request, template: str, session: dict, **context):
    return templates.TemplateResponse(request, template, {
        "session": session,
        "omit_logout_handler": defects.omit_logout_handler(
            session["username"] if session else None),
        **context,
    })


def _require_page_session(request: Request):
    """UI pages redirect anonymous browsers to /login (API returns 401)."""
    session = auth.get_session(request)
    if session is None:
        return None, RedirectResponse("/login", status_code=303)
    return session, None


@app.get("/", include_in_schema=False)
def home(request: Request):
    if auth.get_session(request) is None:
        return RedirectResponse("/login", status_code=303)
    return RedirectResponse("/catalog", status_code=303)


@app.get("/login", response_class=HTMLResponse, include_in_schema=False)
def login_page(request: Request):
    if auth.get_session(request) is not None:
        return RedirectResponse("/catalog", status_code=303)
    return templates.TemplateResponse(request, "login.html",
                                      {"session": None,
                                       "omit_logout_handler": False})


@app.get("/catalog", response_class=HTMLResponse, include_in_schema=False)
def catalog_page(request: Request):
    session, redirect = _require_page_session(request)
    if redirect:
        return redirect
    with db() as conn:
        rows = conn.execute("SELECT * FROM products WHERE is_active = 1 "
                            "ORDER BY id").fetchall()
        products = [product_out(r) for r in rows]
    return _render(request, "catalog.html", session, products=products)


@app.get("/cart", response_class=HTMLResponse, include_in_schema=False)
def cart_page(request: Request):
    session, redirect = _require_page_session(request)
    if redirect:
        return redirect
    return _render(request, "cart.html", session)


@app.get("/orders", response_class=HTMLResponse, include_in_schema=False)
def orders_page(request: Request):
    session, redirect = _require_page_session(request)
    if redirect:
        return redirect
    with db() as conn:
        if session["role"] == "admin":
            rows = conn.execute("SELECT * FROM orders ORDER BY id").fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM orders WHERE user_id = ? ORDER BY id",
                (session["user_id"],)).fetchall()
        orders = [order_out(conn, r) for r in rows]
    return _render(request, "orders.html", session, orders=orders)


@app.get("/admin", response_class=HTMLResponse, include_in_schema=False)
def admin_page(request: Request):
    session, redirect = _require_page_session(request)
    if redirect:
        return redirect
    if session["role"] != "admin":
        return RedirectResponse("/catalog", status_code=303)
    return _render(request, "admin.html", session)
