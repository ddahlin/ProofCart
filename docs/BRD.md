# ShopCheck — Business Requirements Document (BRD)

**Document owner:** Product Management
**Status:** Approved
**Version:** 1.0

---

## 1. Program Overview

ShopCheck is an internal e-commerce ordering portal used by our retail
operations group. It gives our operations administrators a single place to
maintain the product catalog, manage customer accounts, and review sales and
inventory reports, while giving customers a simple storefront where they can
browse products, build a cart, place orders, and track or cancel those orders.

The portal replaces a spreadsheet-driven ordering process. It is intentionally
small: one web application, one database, no external integrations in this
release. Payments are recorded inside the system by moving an order into a
"paid" state; money never moves through ShopCheck itself.

## 2. In Scope

- Sign-in / sign-out and session management for administrators and customers.
- Administrator-managed user accounts (create, view, update, delete, lock).
- Product catalog management (admin) and catalog browsing (customer).
- Shopping cart and order placement with automatic pricing and discounts.
- Order lifecycle management: pending, paid, shipped, cancelled.
- Inventory (stock) tracking tied to the order lifecycle.
- Administrator reports: sales summary and inventory reports.

## 3. Out of Scope

The following are explicitly **out of scope** for this release:

- **Real payment-gateway integration.** Payment is simulated by transitioning
  an order from "pending" to "paid"; no card data is collected or processed.
- **User self-registration.** All accounts are created by an administrator.
- **Email notifications** of any kind (order confirmations, shipping updates,
  password resets).
- **Shipping-carrier integration.** Marking an order "shipped" is a manual,
  administrative action; no carrier APIs or tracking numbers are involved.
- Multi-currency support; all prices are in USD.
- Product reviews, ratings, or promotions/coupon codes.

## 4. Functional Requirements

### 4.1 Authentication & Sessions

**FR-1 — Sign in.** A user must be able to sign in with a username and
password.
- AC1: With a valid username and matching password, the user is signed in and
  a session is established.
- AC2: With an unknown username or a wrong password, sign-in is refused and
  the user is told the credentials are invalid.
- AC3: A request missing the username or the password is rejected as invalid
  input.

**FR-2 — Sign out.** A signed-in user must be able to sign out from any page.
- AC1: After signing out, the session is ended and protected pages are no
  longer accessible.
- AC2: A sign-out attempt without an active session is refused as
  unauthenticated.

**FR-3 — Locked accounts.** An account can be locked by an administrator, and
a locked account must not be able to sign in.
- AC1: A sign-in attempt on a locked account is refused with the message
  "Account locked", even when the password is correct.
- AC2: Locking a user does not delete any of the user's data or orders.

**FR-4 — Access control for anonymous visitors.** Only signed-in users may use
the application's protected pages and services.
- AC1: An anonymous browser visiting the catalog, cart, orders, or admin pages
  is redirected to the sign-in page.
- AC2: An anonymous call to a protected service endpoint is refused as
  unauthenticated.

**FR-5 — Role-based permissions.** Every user has exactly one role, either
**admin** or **customer**, and permissions follow the role.
- AC1: Administrators can manage users, products, all orders, and reports.
- AC2: Customers can browse the active catalog and create, view, and cancel
  only their own orders.
- AC3: A signed-in user who attempts an action outside their role is refused
  with a "forbidden" response.

### 4.2 User Management

**FR-6 — List users.** An administrator must be able to view the list of all
user accounts.
- AC1: The list shows every account with its username, role, and locked state.
- AC2: Customers cannot access the user list.

**FR-7 — Create user.** An administrator must be able to create a new user
account with a username, password, and role.
- AC1: A valid request creates the account, and the new user can sign in
  immediately.
- AC2: A username that is already taken is refused as a conflict.
- AC3: A username or password that violates the business rules (BR-4, BR-5)
  is rejected as invalid input.

**FR-8 — View and update user.** An administrator must be able to view a
single account and update its password, role, or locked state.
- AC1: Updates take effect immediately; locking takes effect at the user's
  next sign-in attempt.
- AC2: A request for a user id that does not exist is answered "not found".
- AC3: An invalid new password is rejected as invalid input (BR-5).

**FR-9 — Delete user.** An administrator must be able to delete a user
account that has no open business with the company.
- AC1: Deleting a user with no orders, or whose orders are all shipped or
  cancelled, removes the account.
- AC2: Deleting a user who still has pending or paid orders is refused as a
  conflict, and the account remains.

**FR-10 — Own profile.** Any signed-in user must be able to view their own
profile.
- AC1: The profile shows the user's id, username, and role.
- AC2: An anonymous request for the profile is refused as unauthenticated.

### 4.3 Product Catalog

**FR-11 — Browse catalog.** Visitors of the catalog must see the list of
active products.
- AC1: Each product shows name, description, price, and stock availability.
- AC2: Inactive (retired) products do not appear in the catalog list.

**FR-12 — Admin catalog view.** An administrator must be able to see inactive
products as well.
- AC1: The administrator can request the product list including inactive
  products and sees an "active" indicator per product.
- AC2: For non-administrators the inclusion request is ignored and only active
  products are returned.

**FR-13 — Product detail.** A product's details must be viewable by id.
- AC1: An active product's detail is visible to any viewer.
- AC2: An inactive product's detail is visible only to administrators; for
  anyone else the product is reported "not found".
- AC3: An id that does not exist is answered "not found".

**FR-14 — Create product.** An administrator must be able to add a product
with name, description, price, stock, and active flag.
- AC1: A valid product is created and immediately visible per its active flag.
- AC2: A price outside the allowed bounds (BR-6) is rejected as invalid input.
- AC3: A name that is empty or longer than 100 characters is rejected as
  invalid input.

**FR-15 — Update product.** An administrator must be able to edit any product
field, including deactivating it.
- AC1: Changes are visible on the next catalog read.
- AC2: Price and name bounds are enforced exactly as on creation.
- AC3: Editing a product does not change prices already captured on existing
  orders.

**FR-16 — Delete product.** An administrator must be able to delete a product
that is not part of any open order.
- AC1: Deleting a product not referenced by any pending or paid order removes
  it permanently.
- AC2: Deleting a product referenced by a pending or paid order is refused as
  a conflict.

### 4.4 Ordering & Order Lifecycle

**FR-17 — Place order.** A signed-in customer must be able to place an order
for one or more products.
- AC1: An order contains between 1 and 20 line items; each line item names a
  product and a quantity between 1 and 10 (BR-2).
- AC2: The price of each line item is captured at the moment the order is
  placed; later catalog price changes do not affect it.
- AC3: An order that references a product id that does not exist is answered
  "not found".
- AC4: An order that asks for more units than are currently in stock is
  refused as a conflict (BR-3).

**FR-18 — Order pricing.** The system must compute order amounts
automatically.
- AC1: The subtotal is the sum of quantity × captured unit price across all
  line items.
- AC2: The discount is applied per BR-1 and shown as its own amount.
- AC3: The total equals subtotal minus discount. All amounts are in USD with
  two decimal places.

**FR-19 — View orders.** Users must be able to review orders.
- AC1: A customer sees a list of only their own orders.
- AC2: An administrator sees all orders from all customers.

**FR-20 — View order detail.** An order's full detail must be viewable by its
owner and by administrators.
- AC1: The detail shows status, line items with captured prices, subtotal,
  discount, and total.
- AC2: A customer requesting another customer's order is refused with a
  "forbidden" response.
- AC3: An order id that does not exist is answered "not found".

**FR-21 — Order status lifecycle.** An order moves through a fixed lifecycle:
**pending → paid → shipped**, with cancellation possible per BR-7.
- AC1: Allowed moves are exactly: pending→paid, pending→cancelled,
  paid→shipped, paid→cancelled. Any other move (including repeating the
  current status) is refused as a conflict.
- AC2: Only administrators may move orders between statuses, with one
  exception: a customer may cancel their own order per BR-7.
- AC3: A move to a status name that does not exist is rejected as invalid
  input.

**FR-22 — Payment and stock.** Recording payment reserves inventory.
- AC1: When an order moves pending→paid, stock for each line item is reduced
  by the ordered quantity.
- AC2: If any line item's quantity exceeds the stock on hand at payment time,
  the payment is refused as a conflict, no stock is changed, and the order
  stays pending (BR-3).

**FR-23 — Cancellation and stock.** Cancelling a paid order returns its
inventory.
- AC1: When a paid order is cancelled, the stock of every line item is
  restored by the ordered quantity (BR-3, BR-7).
- AC2: Cancelling a pending order changes no stock.

### 4.5 Reports

**FR-24 — Create report.** An administrator must be able to create a report
of type "sales_summary" or "inventory" over a date range.
- AC1: The report's figures are computed from the data at the moment of
  creation and stored with the report.
- AC2: A date range whose start is after its end is rejected as invalid input.
- AC3: Customers cannot create reports (BR-9).

**FR-25 — View reports.** An administrator must be able to list all reports
and open any single report.
- AC1: The list shows title, type, date range, author, and creation time.
- AC2: Customers cannot list or open reports (BR-9).
- AC3: A report id that does not exist is answered "not found".

**FR-26 — Delete report.** An administrator must be able to delete a report.
- AC1: A deleted report disappears from the list immediately.
- AC2: Customers cannot delete reports (BR-9).

## 5. Business Rules

- **BR-1 (order discount):** Orders with subtotal **≥ $100.00** receive a
  **10% discount** on the subtotal. Orders below $100.00 receive no discount.
- **BR-2 (line-item quantity):** The maximum quantity per line item is **10**.
- **BR-3 (stock protection):** Stock can never go negative. Creating or paying
  an order with insufficient stock is refused as a conflict and no stock is
  changed. Stock is reduced when an order moves from pending to paid, and
  restored when a paid order is cancelled.
- **BR-4 (username):** Usernames are 3–20 characters and may contain only
  letters, digits, and underscores.
- **BR-5 (password):** Passwords are at least 8 characters and contain at
  least one letter and one digit.
- **BR-6 (price bounds):** A product price is between **$0.01 and $9,999.99**
  inclusive.
- **BR-7 (cancellation window):** An order may be cancelled only while it is
  pending or paid. Cancelling a paid order restores stock.
- **BR-8 (locked accounts):** A locked account cannot sign in; the attempt is
  refused with the message "Account locked".
- **BR-9 (reports access):** Reports are for administrators only.
- **BR-10 (loyalty):** Loyal customers receive a loyalty discount on their
  orders.

## 6. Non-Functional Requirements

- **NFR-1 (browsers):** The application must work correctly on Chrome,
  Firefox, and Edge (current versions).
- **NFR-2 (performance):** The product catalog page must load in under
  3 seconds on a standard office connection.
- **NFR-3 (sessions):** User sessions must expire after 30 minutes of
  inactivity, after which the user must sign in again.
- **NFR-4 (usability):** All user-facing error messages must state the problem
  in plain language.
- **NFR-5 (data integrity):** Monetary amounts are stored and displayed with
  exactly two decimal places.

## 7. Assumptions & Constraints

- The system is deployed as a single web application with a single embedded
  database; no clustering or horizontal scaling in this release.
- All prices and totals are in USD.
- Accounts are provisioned by administrators; the seeded environment ships
  with a small set of test accounts (an administrator plus test customers,
  including `standard_user`, `problem_user`, `locked_out_user`, and
  `new_customer`).
- Non-production environments provide a data-reset facility that restores the
  standard seed data for repeatable testing.
- The business operates in a single time zone; report date ranges are
  interpreted in that time zone.
