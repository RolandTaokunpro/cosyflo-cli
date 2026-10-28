"""Money handling — the single Decimal-owned pence conversion (SR5).

The Cosyflo controller stores payment_rent.amount/monthly_rental in PENCE
(`amount * 100` in PaymentRentController::createPayment). All conversion between
pounds (CLI surface, API contract for create_payment) and pence (storage) goes
through this module. No float arithmetic for money anywhere else.
"""
import re
from decimal import Decimal, InvalidOperation

from .errors import ValidationError

CENT = Decimal("0.01")
MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def parse_amount(value):
    """Parse a pounds string into a 2-dp Decimal. Raises ValidationError on
    non-numeric, negative, or >2-dp input (spec scenarios)."""
    try:
        dec = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValidationError("amount must be a number")
    if not dec.is_finite():
        raise ValidationError("amount must be a number")
    if dec < 0:
        raise ValidationError("amount must be >= 0")
    if -int(dec.as_tuple().exponent) > 2:
        raise ValidationError("amount max 2 decimals")
    return dec.quantize(CENT)


def pounds_to_pence(value):
    """Pounds (string/Decimal) -> integer pence. The one place ×100 happens."""
    return int(parse_amount(value) * 100)


def pence_to_pounds(pence):
    """Integer pence -> 2-dp Decimal pounds. The one inverse."""
    return (Decimal(int(pence)) / 100).quantize(CENT)


def format_pounds(dec):
    return f"£{dec}"


def validate_month(value):
    """Validate a YYYY-MM month string (typed error, pre-network)."""
    if not value or not MONTH_RE.match(str(value)):
        raise ValidationError(f"invalid month '{value}': expected YYYY-MM")
    return str(value)