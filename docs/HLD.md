# ShopCheck — High-Level Design (HLD)

**Document owner:** Engineering / Solution Architecture
**Status:** Approved
**Version:** 1.0

---

## 1. System Context

ShopCheck is a self-contained web application serving two user populations —
administrators and customers — over a browser. There are no upstream or
downstream system integrations: no payment gateway, no shipping carriers, no
email service. All state lives in a single embedded relational database.

```
Browser (admin / customer)
        │  HTTPS (HTML pages + JSON API)
        ▼
FastAPI application (single Uvicorn process)
  ├── Jinja2 server-rendered UI
  ├── JSON REST API (/api/*)
  └── Session store (server-side)
        │
        ▼
SQLite database (data/shopcheck.db)
```

## 2. Component Overview

| Component | Responsibility |
|---|---|
| **FastAPI application** | Single Python 3.11 process hosting both the HTML UI and the JSON API. |
| **Jinja2 UI** | Server-rendered pages: sign-in, catalog, cart, orders, admin dashboard (users / products / reports). Minimal vanilla JavaScript calls the JSON API for actions (add to cart, place order, sign out, admin CRUD). No frontend build step. |
| **REST API (`/api/*`)** | All business operations. The UI is a thin client of this API; automated tests target it directly. |
| **Auth & session layer** | Cookie-based server-side sessions and role enforcement (see §5). |
| **Business-rule module** | All numeric business constants (discount threshold and rate, quantity and price bounds, credential rules, session TTL) are defined in one module and referenced everywhere else. |
| **SQLite database** | Single file `data/shopcheck.db`. Recreated deterministically by the reset endpoint. |

## 3. Data Model Summary

| Table | Key fields | Notes |
|---|---|---|
| **users** | id (PK), username (unique), password_hash, role (`admin`\|`customer`), is_locked, created_at | Usernames 3–20 chars, letters/digits/underscore. |
| **products** | id (PK), name (1–100), description (0–500), price (2 dp, $0.01–$9,999.99), stock (≥ 0), is_active | Inactive products are hidden from the public catalog but remain readable by admins. |
| **orders** | id (PK), user_id (FK), status (`pending`\|`paid`\|`shipped`\|`cancelled`), subtotal, discount, total, created_at, updated_at | Totals are computed server-side and persisted. |
| **order_items** | order_id (FK), product_id (FK), quantity (1–10), unit_price | 1–20 items per order; unit_price is a snapshot taken at order creation. |
| **reports** | id (PK), title (1–100), type (`sales_summary`\|`inventory`), date_from ≤ date_to, payload (JSON), created_by (FK), created_at | Payload is computed once, at creation. |

## 4. API Design Summary

All endpoints are under `/api`. Full request/response schemas are in the
exported OpenAPI document (`openapi.json`).

| Resource | Operations | Access |
|---|---|---|
| `/api/auth/login`, `/api/auth/logout` | POST | Public / any session |
| `/api/users` | GET, POST | Admin |
| `/api/users/me` | GET | Any authenticated user |
| `/api/users/{id}` | GET, PUT, DELETE | Admin; DELETE conflicts if the user has pending or paid orders |
| `/api/products` | GET (public, active only; admins may pass `?include_inactive=true`), POST (admin) | Mixed |
| `/api/products/{id}` | GET (inactive → visible to admin only), PUT (admin), DELETE (admin; conflicts if referenced by pending/paid orders) | Mixed |
| `/api/orders` | GET (customer: own; admin: all), POST (authenticated) | Mixed |
| `/api/orders/{id}` | GET (owner or admin) | Mixed |
| `/api/orders/{id}/status` | PATCH — drives the state machine below | Admin; customers may cancel their own orders only |
| `/api/reports` | GET, POST | Admin only |
| `/api/reports/{id}/detail` | GET — one report with its stored payload | Admin only |
| `/api/reports/{id}` | DELETE | Admin only |
| `/api/reset` | POST | Test facility: drops and recreates seed data; unauthenticated by design, never deployed to production |

### Order state machine

```
pending  → paid        (decrements stock; insufficient stock → 409, order stays pending)
pending  → cancelled
paid     → shipped
paid     → cancelled   (restores stock)
shipped  → (terminal)
cancelled→ (terminal)
```

Any other transition — including a "transition" to the current status —
returns `409` with `{"detail": "Illegal transition <from> -> <to>"}`.

## 5. Authentication & Session Design

- **Mechanism:** cookie-based **server-side sessions**. On successful login the
  server creates a session record and sets a signed, HTTP-only session cookie
  containing only the opaque session id. No JWTs; no credentials or roles are
  stored client-side.
- **TTL:** server-side sessions with a **15-minute inactivity TTL**. Each
  authenticated request refreshes the session's last-activity timestamp; a
  request arriving after the TTL has elapsed finds the session expired and is
  treated as unauthenticated.
- **Password storage:** salted hashes only; plaintext passwords are never
  persisted or logged.
- **Roles:** `admin` and `customer`, checked per route. Unauthenticated
  requests receive `401`; authenticated requests lacking the required role or
  ownership receive `403`. A locked account is refused at login with `403`
  and the message "Account locked".
- **UI behavior:** protected pages (catalog, cart, orders, admin dashboard)
  redirect anonymous browsers to `/login`.

## 6. Error-Handling Conventions

| Code | Meaning | Examples |
|---|---|---|
| `401` | Not authenticated (no session, or session expired) | API call without a valid session cookie |
| `403` | Authenticated but not allowed | Customer calling an admin endpoint; customer reading another customer's order; locked account at login |
| `404` | Resource does not exist (or is hidden from the caller) | Unknown id; inactive product requested by a non-admin |
| `409` | Business conflict — the request is well-formed but the current state forbids it | Illegal status transition; insufficient stock; duplicate username; deleting a user/product still referenced by open orders |
| `422` | Validation failure — the request itself is malformed or out of bounds | Quantity 11; price $10,000.00; username with spaces; `date_from > date_to`. FastAPI's standard validation-error body shape is used. |

Business conflicts (`409`) carry a human-readable `detail` string. Validation
failures (`422`) use the framework's standard error structure listing each
offending field.

## 7. Deployment Notes

- Single **Uvicorn** process (`uvicorn app.main:app`), listening on port 8000;
  suitable for a container or a small VM. No horizontal scaling — the SQLite
  file and the in-process session store assume one instance.
- The database file is created on startup if missing; `POST /api/reset`
  restores the canonical seed data at any time, which is the supported way to
  reach a known-good state in test environments.
- Configuration is via environment variables; no config files are required for
  a default run.
