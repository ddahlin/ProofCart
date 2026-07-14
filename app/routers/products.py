"""Product-catalog endpoints."""
from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app import auth, defects
from app.models import (NON_TERMINAL_STATUSES, ProductIn, ProductOut, db,
                        product_out, to_cents)

router = APIRouter(prefix="/api/products", tags=["products"])

_ADMIN_RESPONSES = {
    401: {"description": "Not authenticated (no session or session expired)."},
    403: {"description": "Authenticated but not an administrator."},
}


@router.get(
    "",
    response_model=list[ProductOut],
)
def list_products(request: Request, include_inactive: bool = False):
    """List the product catalog.

    Positive scenario: any caller receives the list of active products with
    name, description, price, and stock. An administrator may pass
    `?include_inactive=true` to also see inactive products.

    Negative scenario: for non-administrators the `include_inactive` flag is
    ignored and only active products are returned.
    """
    session = auth.get_session(request)
    show_all = include_inactive and session is not None \
        and session["role"] == "admin"
    with db() as conn:
        if show_all:
            rows = conn.execute(
                "SELECT * FROM products ORDER BY id").fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM products WHERE is_active = 1 "
                "ORDER BY id").fetchall()
    return [product_out(r) for r in rows]


@router.post(
    "",
    response_model=ProductOut,
    status_code=201,
    responses={
        **_ADMIN_RESPONSES,
        422: {"description": "Price outside $0.01-$9,999.99 (BR-6), name "
                             "empty or over 100 chars, description over 500 "
                             "chars, or negative stock."},
    },
)
def create_product(body: ProductIn,
                   session: dict = Depends(auth.require_admin)):
    """Create a product (admin only).

    Positive scenario: a valid name, description, price, and stock returns
    201 and the product appears in the catalog per its active flag.

    Negative scenarios: a price outside the allowed bounds or a name/
    description outside its length bounds returns 422; anonymous callers get
    401 and customers get 403.
    """
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO products (name, description, price_cents, stock, "
            "is_active) VALUES (?, ?, ?, ?, ?)",
            (body.name, body.description, to_cents(body.price), body.stock,
             1 if body.is_active else 0))
        row = conn.execute("SELECT * FROM products WHERE id = ?",
                           (cur.lastrowid,)).fetchone()
    return product_out(row)


@router.get(
    "/{product_id}",
    response_model=ProductOut,
    responses={
        404: {"description": "No product with this id, or the product is "
                             "inactive and the caller is not an "
                             "administrator."},
        422: {"description": "The id is not an integer."},
    },
)
def get_product(product_id: int, request: Request):
    """Fetch one product by id.

    Positive scenario: an existing active product is returned to any caller;
    an inactive product is returned to an administrator.

    Negative scenarios: an unknown id returns 404; an inactive product
    requested by a non-administrator also returns 404.
    """
    session = auth.get_session(request)
    is_admin = session is not None and session["role"] == "admin"
    with db() as conn:
        row = conn.execute("SELECT * FROM products WHERE id = ?",
                           (product_id,)).fetchone()
    if row is None or (not row["is_active"] and not is_admin):
        raise HTTPException(status_code=404, detail="Product not found")
    return product_out(row)


@router.put(
    "/{product_id}",
    response_model=ProductOut,
    responses={
        **_ADMIN_RESPONSES,
        404: {"description": "No product with this id."},
        422: {"description": "Price, name, description, or stock outside "
                             "the allowed bounds."},
    },
)
def update_product(product_id: int, body: ProductIn,
                   session: dict = Depends(auth.require_admin)):
    """Update a product (admin only).

    Positive scenario: an administrator edits price, stock, or the active
    flag and the change is visible on the next catalog read; prices already
    captured on existing orders are unaffected.

    Negative scenarios: an unknown id returns 404; out-of-bounds values
    return 422; anonymous callers get 401 and customers get 403.
    """
    with db() as conn:
        row = conn.execute("SELECT id FROM products WHERE id = ?",
                           (product_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Product not found")
        conn.execute(
            "UPDATE products SET name = ?, description = ?, price_cents = ?, "
            "stock = ?, is_active = ? WHERE id = ?",
            (body.name, body.description, to_cents(body.price), body.stock,
             1 if body.is_active else 0, product_id))
        row = conn.execute("SELECT * FROM products WHERE id = ?",
                           (product_id,)).fetchone()
    return product_out(row)


@router.delete(
    "/{product_id}",
    status_code=204,
    responses={
        **_ADMIN_RESPONSES,
        404: {"description": "No product with this id."},
        409: {"description": "The product is referenced by pending or paid "
                             "orders."},
    },
)
def delete_product(product_id: int,
                   session: dict = Depends(auth.require_admin)):
    """Delete a product (admin only).

    Positive scenario: deleting a product not referenced by any pending or
    paid order returns 204 and removes it permanently.

    Negative scenarios: a product referenced by an open order returns 409
    and is kept; an unknown id returns 404; anonymous callers get 401 and
    customers get 403.
    """
    with db() as conn:
        row = conn.execute("SELECT id FROM products WHERE id = ?",
                           (product_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Product not found")
        open_refs = conn.execute(
            f"SELECT COUNT(*) AS n FROM order_items oi "
            f"JOIN orders o ON o.id = oi.order_id "
            f"WHERE oi.product_id = ? AND o.status "
            f"IN ({','.join('?' * len(NON_TERMINAL_STATUSES))})",
            (product_id, *NON_TERMINAL_STATUSES)).fetchone()["n"]
        if open_refs:
            raise HTTPException(
                status_code=409,
                detail="Product is referenced by open (pending or paid) "
                       "orders")
        if not defects.suppress_product_delete():
            conn.execute("DELETE FROM products WHERE id = ?", (product_id,))
    return Response(status_code=204)
