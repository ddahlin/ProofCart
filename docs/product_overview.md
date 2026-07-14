# ShopCheck — Product Overview

## What ShopCheck is

ShopCheck is a small internal e-commerce ordering portal. Administrators
maintain a product catalog, manage customer accounts, and review reports,
while customers browse the catalog, fill a cart, and place orders. The whole
system is one web application backed by one embedded database; there are no
external integrations. Payments are simulated: an order is considered paid
when it is moved into the "paid" state, and no money or card data ever passes
through the system.

## User roles and permissions

ShopCheck has exactly two roles. **Administrators** can create, view, update,
lock, and delete user accounts; create, edit, deactivate, and delete
products; view and manage every order in the system; and create, view, and
delete reports. **Customers** can browse the active product catalog, place
orders, view their own orders, and cancel their own orders while those orders
are still pending or paid. Customers cannot see other customers' orders,
cannot manage users or products, and cannot access reports. Accounts are
created by administrators; there is no self-registration.

## Catalog and pricing concepts

Every product has a name, a description, a price in USD, a stock count, and
an active flag. Prices range from $0.01 to $9,999.99. Inactive products are
hidden from the customer-facing catalog but remain visible to administrators.
When an order is placed, the current price of each product is captured on the
order line item as a snapshot, so later price changes never affect existing
orders. Orders whose subtotal reaches $100.00 receive an automatic 10%
discount; the subtotal, discount, and final total are all stored on the
order.

## Order lifecycle

An order starts in the **pending** state when a customer places it. An
administrator records payment by moving it to **paid**, which is the moment
stock is deducted for each line item; if there is not enough stock, the
payment attempt is rejected and the order stays pending. A paid order can be
moved to **shipped**, which is a terminal state. An order can be **cancelled**
from pending or paid — cancelling a paid order puts the deducted stock back.
Shipped and cancelled orders cannot change state again. Customers may cancel
their own orders; every other state change is performed by administrators.

## Reports

Reports are an administrator-only feature. A report has a title, a type —
"sales_summary" or "inventory" — and a date range. Its figures are computed
at the moment the report is created and stored with it, so a report is a
snapshot, not a live view. A sales summary counts orders by status within the
date range and totals the revenue and discounts of paid and shipped orders.
An inventory report captures product counts, total units in stock, and which
products are out of stock.

## Seeded test accounts

Test environments ship with five accounts. `admin` is the administrator
account (password `Admin123`). The customer test accounts, all with password
`Secret123`, are: `standard_user`, a customer with existing order history;
`problem_user`, a second customer test account with its own order history;
`locked_out_user`, an account that is permanently locked and cannot sign in;
and `new_customer`, a customer with no orders at all.

## Environments and how to run

ShopCheck runs as a single Python web service. Install the Python
dependencies and start the server with `uvicorn app.main:app`; the
application listens on port 8000 and serves both the browser UI and the JSON
API from the same process. On first start it creates and seeds its embedded
SQLite database automatically. A container image can be built from the
included Dockerfile and run with port 8000 published; the database inside a
container is ephemeral, which is intentional.

## Resetting data

`POST /api/reset` restores the database to its standard seed state: the five
accounts above, twelve products with fixed ids and prices (including
boundary items at $0.01 and $9,999.99, one out-of-stock product, and one
inactive product), eight orders spread across the seeded customers covering
every order state, and one saved sales-summary report. The endpoint requires
no authentication, responds with `{"status": "reset"}`, and always produces
exactly the same data, which makes it the supported way to get a repeatable
starting point for testing.
