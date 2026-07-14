"""Deliberate-defect switchboard (APP_SPEC §8).

Every planted defect is decided here and nowhere else, so that normal
behavior is provably clean. Triggers:
  - D1, D3: the `problem_user` session
  - D2, D4: the DEFECT_MODE=1 environment variable

Do not "fix" anything in this file — the defects are the product.
"""
import os
from decimal import Decimal

from app import rules

PROBLEM_USERNAME = "problem_user"

# D1 — calculation defect target
D1_PRODUCT_ID = 7
D1_WRONG_UNIT_PRICE = Decimal("19.99")  # true seeded price is $29.99

# D4 — boundary defect threshold
D4_WRONG_THRESHOLD = Decimal("99.00")


def defect_mode() -> bool:
    """True when the DEFECT_MODE=1 environment variable is set."""
    return os.environ.get("DEFECT_MODE") == "1"


def is_problem_user(username: str | None) -> bool:
    return username == PROBLEM_USERNAME


def unit_price_for_totals(username: str | None, product_id: int,
                          true_price: Decimal) -> Decimal:
    """D1: for problem_user, order-total math for product id 7 uses $19.99
    instead of the true price. The stored unit_price snapshot and stock
    handling stay correct — only subtotal/discount/total are affected."""
    if is_problem_user(username) and product_id == D1_PRODUCT_ID:
        return D1_WRONG_UNIT_PRICE
    return true_price


def suppress_product_delete() -> bool:
    """D2: under DEFECT_MODE=1, DELETE /api/products/{id} returns 204 but
    silently does not delete."""
    return defect_mode()


def omit_logout_handler(username: str | None) -> bool:
    """D3: for problem_user, the UI logout button is rendered without its JS
    handler, so clicking it never sends the request. API logout still works."""
    return is_problem_user(username)


def discount_threshold() -> Decimal:
    """D4: under DEFECT_MODE=1 the BR-1 discount kicks in at >= $99.00
    instead of >= $100.00."""
    if defect_mode():
        return D4_WRONG_THRESHOLD
    return rules.DISCOUNT_THRESHOLD
