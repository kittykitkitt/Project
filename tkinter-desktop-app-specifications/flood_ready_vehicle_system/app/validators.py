"""Reusable validation helpers used by the services (and indirectly by the UI)."""
from __future__ import annotations

import re
from datetime import date, datetime

from app import ValidationError

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
PHONE_RE = re.compile(r"^[+0-9()\-\s]{7,20}$")
PLATE_RE = re.compile(r"^[A-Za-z0-9\- ]{3,12}$")
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.\-]{3,24}$")


def text(value: object, field: str, required: bool = True, max_length: int = 250) -> str:
    """Trimmed text; raises ValidationError when required and empty."""
    clean = "" if value is None else str(value).strip()
    if not clean:
        if required:
            raise ValidationError(f"{field} is required.")
        return ""
    if len(clean) > max_length:
        raise ValidationError(f"{field} must be {max_length} characters or fewer.")
    return clean


def integer(value: object, field: str, minimum: int | None = None,
            maximum: int | None = None) -> int:
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        raise ValidationError(f"{field} must be a whole number.") from None
    if minimum is not None and number < minimum:
        raise ValidationError(f"{field} must be {minimum} or greater.")
    if maximum is not None and number > maximum:
        raise ValidationError(f"{field} must be {maximum} or lower.")
    return number


def decimal(value: object, field: str, minimum: float = 0.0) -> float:
    try:
        number = float(str(value).strip() or "0")
    except (TypeError, ValueError):
        raise ValidationError(f"{field} must be a number.") from None
    if number < minimum:
        raise ValidationError(f"{field} cannot be less than {minimum:g}.")
    return round(number, 2)


def boolean(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def iso_date(value: object, field: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raw = str(value or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    raise ValidationError(f"{field} must be a valid date (YYYY-MM-DD).")


def iso_datetime(value: object, field: str) -> datetime:
    if isinstance(value, datetime):
        return value
    raw = str(value or "").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    raise ValidationError(f"{field} must be a valid date and time.")


def choice(value: object, options: list[str] | tuple[str, ...], field: str) -> str:
    clean = str(value or "").strip().lower()
    if clean not in [str(option).lower() for option in options]:
        raise ValidationError(f"{field} must be one of: {', '.join(options)}.")
    return clean


def email(value: object, field: str = "Email", required: bool = False) -> str:
    clean = text(value, field, required=required)
    if clean and not EMAIL_RE.match(clean):
        raise ValidationError(f"{field} is not a valid email address.")
    return clean


def phone(value: object, field: str = "Contact number", required: bool = True) -> str:
    clean = text(value, field, required=required)
    if clean and not PHONE_RE.match(clean):
        raise ValidationError(f"{field} must contain 7 to 20 digits.")
    return clean


def plate_number(value: object, field: str = "Plate number") -> str:
    clean = text(value, field).upper()
    if not PLATE_RE.match(clean):
        raise ValidationError(f"{field} must be 3-12 letters, digits or dashes.")
    return clean


def username(value: object, field: str = "Username") -> str:
    clean = text(value, field).lower()
    if not USERNAME_RE.match(clean):
        raise ValidationError(
            f"{field} must be 3-24 characters (letters, numbers, dot, dash, underscore)."
        )
    return clean


def coordinates(latitude: object, longitude: object) -> tuple[float, float]:
    """Validate GPS coordinates; empty values are allowed (unknown position)."""
    lat_raw = str(latitude or "").strip()
    lon_raw = str(longitude or "").strip()
    if not lat_raw and not lon_raw:
        return (0.0, 0.0)
    if not lat_raw or not lon_raw:
        raise ValidationError("Both latitude and longitude must be provided.")
    try:
        lat = float(lat_raw)
        lon = float(lon_raw)
    except (TypeError, ValueError):
        raise ValidationError("Latitude and longitude must be numbers.") from None
    if not -90.0 <= lat <= 90.0:
        raise ValidationError("Latitude must be between -90 and 90.")
    if not -180.0 <= lon <= 180.0:
        raise ValidationError("Longitude must be between -180 and 180.")
    return round(lat, 6), round(lon, 6)


def date_range(start: object, end: object,
               start_field: str = "Start date",
               end_field: str = "End date") -> tuple[date, date]:
    first = iso_date(start, start_field)
    last = iso_date(end, end_field)
    if last < first:
        raise ValidationError(f"{end_field} cannot be earlier than {start_field}.")
    return first, last
