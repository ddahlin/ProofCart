"""Admin-only report endpoints (BR-9)."""
import json
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Response

from app import auth
from app.models import ReportCreate, ReportOut, db, report_out, to_dollars

router = APIRouter(prefix="/api/reports", tags=["reports"])

_ADMIN_RESPONSES = {
    401: {"description": "Not authenticated (no session or session expired)."},
    403: {"description": "Authenticated but not an administrator (BR-9)."},
}


def build_payload(conn: sqlite3.Connection, report_type: str,
                  date_from: str, date_to: str) -> dict:
    """Compute a report's figures from current data (called once, at
    creation)."""
    if report_type == "sales_summary":
        rows = conn.execute(
            "SELECT status, COUNT(*) AS n, SUM(total_cents) AS total, "
            "SUM(discount_cents) AS discount FROM orders "
            "WHERE date(created_at) BETWEEN ? AND ? GROUP BY status",
            (date_from, date_to)).fetchall()
        by_status = {r["status"]: r["n"] for r in rows}
        revenue = sum(r["total"] for r in rows
                      if r["status"] in ("paid", "shipped"))
        discounts = sum(r["discount"] for r in rows
                        if r["status"] in ("paid", "shipped"))
        return {
            "orders_total": sum(by_status.values()),
            "orders_by_status": by_status,
            "gross_revenue": to_dollars(revenue),
            "discounts_given": to_dollars(discounts),
        }
    # inventory
    rows = conn.execute("SELECT * FROM products ORDER BY id").fetchall()
    return {
        "products_total": len(rows),
        "active_products": sum(1 for r in rows if r["is_active"]),
        "total_units_in_stock": sum(r["stock"] for r in rows),
        "out_of_stock_product_ids": [r["id"] for r in rows
                                     if r["stock"] == 0],
    }


@router.get(
    "",
    response_model=list[ReportOut],
    responses=_ADMIN_RESPONSES,
)
def list_reports(session: dict = Depends(auth.require_admin)):
    """List all reports (admin only).

    Positive scenario: an administrator receives every report with title,
    type, date range, author, and creation time.

    Negative scenarios: an anonymous caller receives 401; a signed-in
    customer receives 403.
    """
    with db() as conn:
        rows = conn.execute("SELECT * FROM reports ORDER BY id").fetchall()
    return [report_out(r) for r in rows]


@router.post(
    "",
    response_model=ReportOut,
    status_code=201,
    responses={
        **_ADMIN_RESPONSES,
        422: {"description": "date_from is after date_to, the type is not "
                             "sales_summary/inventory, or the title is "
                             "empty or over 100 chars."},
    },
)
def create_report(body: ReportCreate,
                  session: dict = Depends(auth.require_admin)):
    """Create a report (admin only).

    Positive scenario: an administrator submits a title, a type
    (sales_summary or inventory), and a valid date range; the figures are
    computed from the data at this moment and stored with the report.

    Negative scenarios: a date range whose start is after its end returns
    422; an unknown type returns 422; anonymous callers get 401 and
    customers get 403.
    """
    date_from = body.date_from.isoformat()
    date_to = body.date_to.isoformat()
    with db() as conn:
        payload = build_payload(conn, body.type.value, date_from, date_to)
        cur = conn.execute(
            "INSERT INTO reports (title, type, date_from, date_to, payload, "
            "created_by, created_at) VALUES (?, ?, ?, ?, ?, ?, "
            "datetime('now'))",
            (body.title, body.type.value, date_from, date_to,
             json.dumps(payload), session["user_id"]))
        row = conn.execute("SELECT * FROM reports WHERE id = ?",
                           (cur.lastrowid,)).fetchone()
    return report_out(row)


@router.get(
    "/{report_id}/detail",
    response_model=ReportOut,
    responses={
        **_ADMIN_RESPONSES,
        404: {"description": "No report with this id."},
    },
)
def get_report(report_id: int, session: dict = Depends(auth.require_admin)):
    """Fetch one report with its stored payload (admin only).

    Positive scenario: an administrator opens an existing report and sees
    the figures computed at creation time.

    Negative scenarios: an unknown id returns 404; anonymous callers get
    401 and customers get 403.
    """
    with db() as conn:
        row = conn.execute("SELECT * FROM reports WHERE id = ?",
                           (report_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Report not found")
    return report_out(row)


@router.delete(
    "/{report_id}",
    status_code=204,
    responses={
        **_ADMIN_RESPONSES,
        404: {"description": "No report with this id."},
    },
)
def delete_report(report_id: int,
                  session: dict = Depends(auth.require_admin)):
    """Delete a report (admin only).

    Positive scenario: deleting an existing report returns 204 and it
    disappears from the list immediately.

    Negative scenarios: an unknown id returns 404; anonymous callers get
    401 and customers get 403.
    """
    with db() as conn:
        row = conn.execute("SELECT id FROM reports WHERE id = ?",
                           (report_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Report not found")
        conn.execute("DELETE FROM reports WHERE id = ?", (report_id,))
    return Response(status_code=204)
