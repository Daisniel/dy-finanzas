from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP


def format_date(value: object, empty: str = "—") -> str:
    """Return dates as dd/mm/yyyy while keeping ISO in the database."""
    if value is None:
        return empty
    text = str(value).strip()
    if not text:
        return empty
    for pattern in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y"):
        try:
            return datetime.strptime(text[:19], pattern).strftime("%d/%m/%Y")
        except ValueError:
            continue
    try:
        return date.fromisoformat(text[:10]).strftime("%d/%m/%Y")
    except ValueError:
        return text


def round_area(value: float) -> int:
    """Commercial rounding for final square meters: .5 always rounds up."""
    return int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
