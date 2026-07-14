"""Order endpoints: creation, listing, detail, and the status state machine."""
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException

from app import auth, defects
from app.models import (LEGAL_TRANSITIONS, OrderCreate, OrderOut, OrderStatus,
                        StatusChange, db, discount_cents_for, order_out,
                        to_cents)

router = APIRouter(prefix="/api/orders", tags=["orders"])

_NOW = "datetime('now')"


@router.get(
    "",
    response_model=list[OrderOut],
    responses={
        401: {"description": "Not authenticated (no session or session "
                             "expired)."},
    },
)
def list_orders(session: dict = Depends(auth.require_user)):
    """List orders visible to the caller.

    Positive scenarios: a customer receives only their own orders; an
    administrator receives every order from every customer.

    Negative scenario: an anonymous caller receives 401.
    """
    with db() as conn:
        if session["role"] == "admin":
            rows = conn.execute("SELECT * FROM orders ORDER BY id").fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM orders WHERE user_id = ? ORDER BY id",
                (session["user_id"],)).fetchall()
        return [order_out(conn, r) for r in rows]


@router.post(
    "",
    response_model=OrderOut,
    status_code=201,
    responses={
        401: {"description": "Not authenticated."},
        404: {"description": "A line item references an unknown product."},
        409: {"description": "A line item asks for more units than are in "
                             "stock (BR-3)."},
        422: {"description": "Quantity outside 1-10 (BR-2), more than 20 "
                             "line items, or fewer than 1."},
    },
)
def create_order(body: OrderCreate, session: dict = Depends(auth.require_user)):
    """Place a new order.

    Positive scenario: a signed-in user submits 1-20 line items, each with
    quantity 1-10 of an in-stock product; the order is created as `pending`
    with unit prices captured at this moment, and subtotal, discount (BR-1),
    and total computed automatically.

    Negative scenarios: an unknown product id returns 404; requesting more
    units than the current stock returns 409 and creates nothing; a quantity
    outside 1-10 or an item count outside 1-20 returns 422.
    """
    username = session["username"]
    with db() as conn:
        products = {}
        requested: dict[int, int] = {}
        for item in body.items:
            row = conn.execute("SELECT * FROM products WHERE id = ?",
                               (item.product_id,)).fetchone()
            if row is None or (not row["is_active"]
                               and session["role"] != "admin"):
                raise HTTPException(
                    status_code=404,
                    detail=f"Product {item.product_id} not found")
            products[item.product_id] = row
            requested[item.product_id] = \
                requested.get(item.product_id, 0) + item.quantity

        for pid, qty in requested.items():
            if qty > products[pid]["stock"]:
                raise HTTPException(
                    status_code=409,
                    detail=f"Insufficient stock for product {pid}")

        subtotal_cents = 0
        for item in body.items:
            true_price = Decimal(products[item.product_id]["price_cents"]) \
                / 100
            effective = defects.unit_price_for_totals(
                username, item.product_id, true_price)
            subtotal_cents += to_cents(effective) * item.quantity

        discount_cents = discount_cents_for(subtotal_cents,
                                            defects.discount_threshold())
        cur = conn.execute(
            f"INSERT INTO orders (user_id, status, subtotal_cents, "
            f"discount_cents, total_cents, created_at, updated_at) "
            f"VALUES (?, 'pending', ?, ?, ?, {_NOW}, {_NOW})",
            (session["user_id"], subtotal_cents, discount_cents,
             subtotal_cents - discount_cents))
        order_id = cur.lastrowid
        for item in body.items:
            conn.execute(
                "INSERT INTO order_items (order_id, product_id, quantity, "
                "unit_price_cents) VALUES (?, ?, ?, ?)",
                (order_id, item.product_id, item.quantity,
                 products[item.product_id]["price_cents"]))
        row = conn.execute("SELECT * FROM orders WHERE id = ?",
                           (order_id,)).fetchone()
        return order_out(conn, row)


@router.get(
    "/{order_id}",
    response_model=OrderOut,
    responses={
        401: {"description": "Not authenticated."},
        403: {"description": "A customer requested an order they do not "
                             "own."},
        404: {"description": "No order with this id."},
    },
)
def get_order(order_id: int, session: dict = Depends(auth.require_user)):
    """Fetch one order with its line items and amounts.

    Positive scenario: the order's owner (or any administrator) receives
    status, line items with captured unit prices, subtotal, discount, and
    total.

    Negative scenarios: a customer requesting another customer's order
    receives 403; an unknown id returns 404; anonymous callers get 401.
    """
    with db() as conn:
        row = conn.execute("SELECT * FROM orders WHERE id = ?",
                           (order_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Order not found")
        if session["role"] != "admin" and row["user_id"] != session["user_id"]:
            raise HTTPException(status_code=403,
                                detail="Not the owner of this order")
        return order_out(conn, row)


@router.patch(
    "/{order_id}/status",
    response_model=OrderOut,
    responses={
        401: {"description": "Not authenticated."},
        403: {"description": "Customers may only cancel their own orders; "
                             "every other transition is admin-only."},
        404: {"description": "No order with this id."},
        409: {"description": "Illegal transition for the current status, or "
                             "insufficient stock when paying (BR-3)."},
        422: {"description": "Unknown status value."},
    },
)
def change_status(order_id: int, body: StatusChange,
                  session: dict = Depends(auth.require_user)):
    """Move an order through its lifecycle.

    Legal transitions: pending->paid (decrements stock), pending->cancelled,
    paid->shipped, paid->cancelled (restores stock).

    Positive scenario: an administrator pays a pending order; stock is
    reduced by each line item's quantity and the order becomes `paid`.
    A customer cancels their own pending or paid order.

    Negative scenarios: any other from/to pair (including repeating the
    current status) returns 409 with detail "Illegal transition <from> ->
    <to>"; paying with insufficient stock returns 409, changes no stock, and
    leaves the order pending; a customer attempting any transition other
    than cancelling their own order receives 403; an unknown status value
    returns 422; an unknown order id returns 404.
    """
    target = body.status
    with db() as conn:
        row = conn.execute("SELECT * FROM orders WHERE id = ?",
                           (order_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Order not found")

        if session["role"] != "admin":
            owns = row["user_id"] == session["user_id"]
            if not owns or target != OrderStatus.cancelled:
                raise HTTPException(
                    status_code=403,
                    detail="Customers may only cancel their own orders")

        current = OrderStatus(row["status"])
        if (current, target) not in LEGAL_TRANSITIONS:
            raise HTTPException(
                status_code=409,
                detail=f"Illegal transition {current.value} -> {target.value}")

        items = conn.execute(
            "SELECT product_id, quantity FROM order_items WHERE order_id = ?",
            (order_id,)).fetchall()

        needed: dict[int, int] = {}
        for item in items:
            needed[item["product_id"]] = \
                needed.get(item["product_id"], 0) + item["quantity"]

        if current == OrderStatus.pending and target == OrderStatus.paid:
            for pid, qty in needed.items():
                stock = conn.execute(
                    "SELECT stock FROM products WHERE id = ?",
                    (pid,)).fetchone()
                if stock is None or stock["stock"] < qty:
                    raise HTTPException(
                        status_code=409,
                        detail=f"Insufficient stock for product {pid}")
            for pid, qty in needed.items():
                conn.execute(
                    "UPDATE products SET stock = stock - ? WHERE id = ?",
                    (qty, pid))
        elif current == OrderStatus.paid and target == OrderStatus.cancelled:
            for pid, qty in needed.items():
                conn.execute(
                    "UPDATE products SET stock = stock + ? WHERE id = ?",
                    (qty, pid))

        conn.execute(
            f"UPDATE orders SET status = ?, updated_at = {_NOW} "
            f"WHERE id = ?", (target.value, order_id))
        row = conn.execute("SELECT * FROM orders WHERE id = ?",
                           (order_id,)).fetchone()
        return order_out(conn, row)
