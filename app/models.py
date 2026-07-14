"""Database layer (SQLite) and API schemas for ShopCheck.

Money is stored as integer cents; the JSON API exposes dollars with two
decimal places.
"""
import os
import sqlite3
from contextlib import contextmanager
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, model_validator

from app import rules

DB_PATH = os.environ.get("SHOPCHECK_DB", os.path.join("data", "shopcheck.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin', 'customer')),
    is_locked INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    price_cents INTEGER NOT NULL,
    stock INTEGER NOT NULL CHECK (stock >= 0),
    is_active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    status TEXT NOT NULL CHECK (status IN ('pending', 'paid', 'shipped', 'cancelled')),
    subtotal_cents INTEGER NOT NULL,
    discount_cents INTEGER NOT NULL,
    total_cents INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS order_items (
    id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    -- no FK on product_id: line items are snapshots and outlive the product
    product_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price_cents INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('sales_summary', 'inventory')),
    date_from TEXT NOT NULL,
    date_to TEXT NOT NULL,
    payload TEXT NOT NULL,
    created_by INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL
);
"""

NON_TERMINAL_STATUSES = ("pending", "paid")


def connect() -> sqlite3.Connection:
    directory = os.path.dirname(DB_PATH)
    if directory:
        os.makedirs(directory, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def db():
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with db() as conn:
        conn.executescript(SCHEMA)


# ---------------------------------------------------------------------------
# Money helpers
# ---------------------------------------------------------------------------

def to_cents(amount: Decimal) -> int:
    return int((amount * 100).to_integral_value(rounding=ROUND_HALF_UP))


def to_dollars(cents: int) -> float:
    return round(cents / 100, 2)


def discount_cents_for(subtotal_cents: int, threshold: Decimal) -> int:
    """BR-1: 10% off when subtotal >= threshold, else zero."""
    if Decimal(subtotal_cents) >= threshold * 100:
        raw = Decimal(subtotal_cents) * rules.DISCOUNT_RATE
        return int(raw.to_integral_value(rounding=ROUND_HALF_UP))
    return 0


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Role(str, Enum):
    admin = "admin"
    customer = "customer"


class OrderStatus(str, Enum):
    pending = "pending"
    paid = "paid"
    shipped = "shipped"
    cancelled = "cancelled"


class ReportType(str, Enum):
    sales_summary = "sales_summary"
    inventory = "inventory"


LEGAL_TRANSITIONS = {
    (OrderStatus.pending, OrderStatus.paid),
    (OrderStatus.pending, OrderStatus.cancelled),
    (OrderStatus.paid, OrderStatus.shipped),
    (OrderStatus.paid, OrderStatus.cancelled),
}


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    username: str
    password: str


def _validate_password(password: str) -> str:
    if len(password) < rules.PASSWORD_MIN:
        raise ValueError(
            f"password must be at least {rules.PASSWORD_MIN} characters")
    if not any(c.isalpha() for c in password):
        raise ValueError("password must contain at least one letter")
    if not any(c.isdigit() for c in password):
        raise ValueError("password must contain at least one digit")
    return password


class UserCreate(BaseModel):
    username: str = Field(min_length=rules.USERNAME_MIN,
                          max_length=rules.USERNAME_MAX,
                          pattern=rules.USERNAME_PATTERN)
    password: str
    role: Role = Role.customer

    @model_validator(mode="after")
    def check_password(self):
        _validate_password(self.password)
        return self


class UserUpdate(BaseModel):
    password: Optional[str] = None
    role: Optional[Role] = None
    is_locked: Optional[bool] = None

    @model_validator(mode="after")
    def check_password(self):
        if self.password is not None:
            _validate_password(self.password)
        return self


class ProductIn(BaseModel):
    name: str = Field(min_length=rules.NAME_MIN, max_length=rules.NAME_MAX)
    description: str = Field(default="", max_length=rules.DESCRIPTION_MAX)
    price: Decimal = Field(ge=rules.PRICE_MIN, le=rules.PRICE_MAX,
                           decimal_places=2)
    stock: int = Field(ge=0)
    is_active: bool = True


class OrderItemIn(BaseModel):
    product_id: int
    quantity: int = Field(ge=rules.MIN_QTY, le=rules.MAX_QTY)


class OrderCreate(BaseModel):
    items: list[OrderItemIn] = Field(min_length=rules.MIN_LINE_ITEMS,
                                     max_length=rules.MAX_LINE_ITEMS)


class StatusChange(BaseModel):
    status: OrderStatus


class ReportCreate(BaseModel):
    title: str = Field(min_length=rules.REPORT_TITLE_MIN,
                       max_length=rules.REPORT_TITLE_MAX)
    type: ReportType
    date_from: date
    date_to: date

    @model_validator(mode="after")
    def check_range(self):
        if self.date_from > self.date_to:
            raise ValueError("date_from must be on or before date_to")
        return self


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class UserOut(BaseModel):
    id: int
    username: str
    role: Role
    is_locked: bool
    created_at: str


class ProductOut(BaseModel):
    id: int
    name: str
    description: str
    price: float
    stock: int
    is_active: bool


class OrderItemOut(BaseModel):
    product_id: int
    quantity: int
    unit_price: float


class OrderOut(BaseModel):
    id: int
    user_id: int
    status: OrderStatus
    items: list[OrderItemOut]
    subtotal: float
    discount: float
    total: float
    created_at: str
    updated_at: str


class ReportOut(BaseModel):
    id: int
    title: str
    type: ReportType
    date_from: str
    date_to: str
    payload: dict
    created_by: int
    created_at: str


class LoginOut(BaseModel):
    id: int
    username: str
    role: Role


class StatusOut(BaseModel):
    status: str


# ---------------------------------------------------------------------------
# Row -> schema helpers
# ---------------------------------------------------------------------------

def user_out(row: sqlite3.Row) -> UserOut:
    return UserOut(id=row["id"], username=row["username"], role=row["role"],
                   is_locked=bool(row["is_locked"]),
                   created_at=row["created_at"])


def product_out(row: sqlite3.Row) -> ProductOut:
    return ProductOut(id=row["id"], name=row["name"],
                      description=row["description"],
                      price=to_dollars(row["price_cents"]),
                      stock=row["stock"], is_active=bool(row["is_active"]))


def order_out(conn: sqlite3.Connection, row: sqlite3.Row) -> OrderOut:
    items = conn.execute(
        "SELECT product_id, quantity, unit_price_cents FROM order_items "
        "WHERE order_id = ? ORDER BY id", (row["id"],)).fetchall()
    return OrderOut(
        id=row["id"], user_id=row["user_id"], status=row["status"],
        items=[OrderItemOut(product_id=i["product_id"],
                            quantity=i["quantity"],
                            unit_price=to_dollars(i["unit_price_cents"]))
               for i in items],
        subtotal=to_dollars(row["subtotal_cents"]),
        discount=to_dollars(row["discount_cents"]),
        total=to_dollars(row["total_cents"]),
        created_at=row["created_at"], updated_at=row["updated_at"])


def report_out(row: sqlite3.Row) -> ReportOut:
    import json
    return ReportOut(id=row["id"], title=row["title"], type=row["type"],
                     date_from=row["date_from"], date_to=row["date_to"],
                     payload=json.loads(row["payload"]),
                     created_by=row["created_by"],
                     created_at=row["created_at"])
