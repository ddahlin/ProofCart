"""Single source of truth for every business-rule number in ShopCheck.

Routes, templates, and tests import from here; the numbers must never be
inlined elsewhere. app/defects.py may override some of these values under its
trigger conditions.
"""
from decimal import Decimal

# BR-1 — order discount
DISCOUNT_THRESHOLD = Decimal("100.00")
DISCOUNT_RATE = Decimal("0.10")

# BR-2 — line items
MIN_LINE_ITEMS = 1
MAX_LINE_ITEMS = 20
MIN_QTY = 1
MAX_QTY = 10

# BR-4 — username
USERNAME_MIN = 3
USERNAME_MAX = 20
USERNAME_PATTERN = r"^[A-Za-z0-9_]+$"

# BR-5 — password
PASSWORD_MIN = 8

# BR-6 — product price bounds (inclusive)
PRICE_MIN = Decimal("0.01")
PRICE_MAX = Decimal("9999.99")

# Product text bounds
NAME_MIN = 1
NAME_MAX = 100
DESCRIPTION_MAX = 500

# Report title bounds
REPORT_TITLE_MIN = 1
REPORT_TITLE_MAX = 100

# Session inactivity TTL (seconds)
SESSION_TTL_SECONDS = 15 * 60

# BR-8 — locked-account message
LOCKED_MESSAGE = "Account locked"
