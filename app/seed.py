"""Deterministic seed data and the /api/reset logic (APP_SPEC §12).

reset() drops and recreates every table with fixed ids, prices, stock, and
order states. Seeded rows always use the clean business rules — defects only
apply to live requests, never to seed data.
"""
import json

from app import rules
from app.models import SCHEMA, db, discount_cents_for
from app.auth import hash_password

_USER_CREATED_AT = "2026-01-01T09:00:00"

# (id, username, password, role, is_locked)
USERS = [
    (1, "admin", "Admin123", "admin", 0),
    (2, "standard_user", "Secret123", "customer", 0),
    (3, "problem_user", "Secret123", "customer", 0),
    (4, "locked_out_user", "Secret123", "customer", 1),
    (5, "new_customer", "Secret123", "customer", 0),
]

# (id, name, description, price_cents, stock, is_active)
PRODUCTS = [
    (1, "Penny Sticker", "A tiny vinyl sticker.", 1, 100, 1),
    (2, "Flagship Workstation", "Top-of-the-line desktop workstation.",
     999999, 3, 1),
    (3, "Wireless Mouse", "Ergonomic 2.4 GHz wireless mouse.", 2499, 50, 1),
    (4, "Mechanical Keyboard", "Tenkeyless mechanical keyboard.", 8999, 25, 1),
    (5, "USB-C Hub", "7-in-1 USB-C hub.", 4999, 0, 1),
    (6, "Monitor Stand", "Height-adjustable monitor stand.", 3499, 1, 1),
    (7, "Desk Lamp", "LED desk lamp with dimmer.", 2999, 40, 1),
    (8, "Laptop Sleeve", "Padded 14-inch laptop sleeve.", 1000, 60, 1),
    (9, "Gaming Headset", "Over-ear headset with microphone.", 9999, 30, 1),
    (10, "HD Webcam", "1080p webcam with privacy shutter.", 5999, 15, 1),
    (11, "Retro Gamepad", "USB gamepad, discontinued line.", 1999, 5, 0),
    (12, "Pocket Notebook", "A6 dot-grid notebook.", 499, 200, 1),
]

# (id, user_id, status, created_at, [(product_id, quantity), ...])
ORDERS = [
    (1, 2, "pending", "2026-01-05T10:00:00", [(3, 2)]),
    (2, 2, "paid", "2026-01-06T11:00:00", [(8, 10)]),
    (3, 2, "shipped", "2026-01-08T12:00:00", [(3, 1), (12, 1)]),
    (4, 2, "cancelled", "2026-01-10T13:00:00", [(6, 1)]),
    (5, 3, "pending", "2026-01-12T14:00:00", [(7, 1)]),
    (6, 3, "paid", "2026-01-14T15:00:00", [(9, 1)]),
    (7, 3, "shipped", "2026-01-16T16:00:00", [(4, 1)]),
    (8, 2, "paid", "2026-01-18T17:00:00", [(1, 10), (12, 2)]),
]

_REPORT_CREATED_AT = "2026-02-01T09:00:00"


def reset() -> None:
    with db() as conn:
        conn.executescript(
            "DROP TABLE IF EXISTS order_items;"
            "DROP TABLE IF EXISTS orders;"
            "DROP TABLE IF EXISTS reports;"
            "DROP TABLE IF EXISTS products;"
            "DROP TABLE IF EXISTS users;")
        conn.executescript(SCHEMA)

        for uid, username, password, role, locked in USERS:
            conn.execute(
                "INSERT INTO users (id, username, password_hash, role, "
                "is_locked, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (uid, username, hash_password(password), role, locked,
                 _USER_CREATED_AT))

        for pid, name, desc, price_cents, stock, active in PRODUCTS:
            conn.execute(
                "INSERT INTO products (id, name, description, price_cents, "
                "stock, is_active) VALUES (?, ?, ?, ?, ?, ?)",
                (pid, name, desc, price_cents, stock, active))

        prices = {pid: price for pid, _, _, price, _, _ in PRODUCTS}
        for oid, uid, status, created_at, items in ORDERS:
            subtotal = sum(prices[pid] * qty for pid, qty in items)
            discount = discount_cents_for(subtotal, rules.DISCOUNT_THRESHOLD)
            conn.execute(
                "INSERT INTO orders (id, user_id, status, subtotal_cents, "
                "discount_cents, total_cents, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (oid, uid, status, subtotal, discount, subtotal - discount,
                 created_at, created_at))
            for pid, qty in items:
                conn.execute(
                    "INSERT INTO order_items (order_id, product_id, "
                    "quantity, unit_price_cents) VALUES (?, ?, ?, ?)",
                    (oid, pid, qty, prices[pid]))

        from app.routers.reports import build_payload
        payload = build_payload(conn, "sales_summary", "2026-01-01",
                                "2026-01-31")
        conn.execute(
            "INSERT INTO reports (id, title, type, date_from, date_to, "
            "payload, created_by, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (1, "January Sales Summary", "sales_summary", "2026-01-01",
             "2026-01-31", json.dumps(payload), 1, _REPORT_CREATED_AT))


def ensure_seeded() -> None:
    """Seed on first startup so a fresh checkout/container is usable."""
    with db() as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name='users'").fetchone()
        if row is None:
            seeded = False
        else:
            seeded = conn.execute(
                "SELECT COUNT(*) AS n FROM users").fetchone()["n"] > 0
    if not seeded:
        reset()
