"""Business logic for the application.

Nothing in this module imports Tkinter: the same functions are used by the GUI
and by the pytest suite.  Each service receives the shared
:class:`~app.database.DatabaseManager` instance.
"""
from __future__ import annotations

import logging
import math
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Sequence

from app import (
    AuthenticationError,
    DataConflictError,
    NotFoundError,
    OperationError,
    ValidationError,
)
from app.config import IMAGE_DIR, RISK_LEVELS, VEHICLE_STATUSES
from app.models import ReportData, Vehicle, now_iso, today_iso
from app.security import hash_password, password_problems, verify_password
from app import validators as v

if TYPE_CHECKING:  # pragma: no cover
    from .database import DatabaseManager

log = logging.getLogger(__name__)

ACTIVE_BOOKING_STATUSES = ("pending", "confirmed", "ongoing")
RISK_WEIGHTS = {"low": 10, "moderate": 30, "high": 50, "severe": 70}
RISK_ORDER = ["low", "moderate", "high", "severe"]
MAX_IMAGE_BYTES = 8 * 1024 * 1024
ALLOWED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}


# --------------------------------------------------------------------- helpers
def _like(value: object) -> str:
    return f"%{str(value or '').strip().lower()}%"


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def resolve_image_path(stored: object) -> Path | None:
    """Resolve a stored image reference to a real file (or None when missing)."""
    if not stored:
        return None
    raw = Path(str(stored))
    if raw.is_absolute():
        if raw.exists():
            return raw
        raw = Path(raw.name)
    candidate = IMAGE_DIR / raw
    return candidate if candidate.exists() else None


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres between two GPS positions."""
    radius = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return round(2 * radius * math.asin(math.sqrt(a)), 4)


# ------------------------------------------------------------------ flood risk
def risk_level_for_score(score: float) -> str:
    if score >= 60:
        return "severe"
    if score >= 40:
        return "high"
    if score >= 20:
        return "moderate"
    return "low"


def assess_position(latitude: float, longitude: float,
                    zones: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Score a GPS position against the active flood zones.

    Works completely offline - it only needs the zone rows from SQLite.
    """
    if not latitude or not longitude:
        return {
            "score": 0,
            "level": "unknown",
            "nearest_zone": "",
            "distance_km": 0.0,
            "inside_zone": False,
            "has_position": False,
            "reasons": ["No GPS coordinates recorded for this vehicle."],
        }

    dominant = 0.0
    nearest_name = ""
    nearest_distance = 0.0
    inside = False
    nearby = 0
    reasons: list[str] = []
    for zone in zones:
        distance = haversine_km(
            latitude, longitude, float(zone["latitude"]), float(zone["longitude"])
        )
        radius = float(zone.get("radius_km") or 0)
        edge = max(0.0, distance - radius)
        weight = RISK_WEIGHTS.get(str(zone.get("risk_level", "low")).lower(), 10)
        if edge <= 0:
            contribution = float(weight)
            inside = True
            reasons.append(f"Inside {zone['name']} ({zone['risk_level']} risk zone).")
        elif edge <= 5:
            contribution = weight * (1 - edge / 5)
            reasons.append(
                f"{edge:.1f} km from {zone['name']} ({zone['risk_level']} risk)."
            )
        else:
            contribution = 0.0
        if edge <= 5:
            nearby += 1
        if contribution > dominant:
            dominant = contribution
        if not nearest_distance or distance < nearest_distance:
            nearest_distance = distance
            nearest_name = str(zone["name"])

    score = int(round(_clamp(dominant + min(10, nearby * 2), 0, 100)))
    return {
        "score": score,
        "level": risk_level_for_score(score),
        "nearest_zone": nearest_name,
        "distance_km": nearest_distance,
        "inside_zone": inside,
        "has_position": True,
        "reasons": reasons or ["No active flood zone within 5 km."],
    }


def positions_meeting_threshold(zones: Sequence[dict[str, Any]], threshold: str = "high",
                                ) -> dict[str, int]:
    return {level: RISK_WEIGHTS[level] for level in RISK_LEVELS}


# ------------------------------------------------------------------ auth/users
class AuthService:
    def __init__(self, db: "DatabaseManager") -> None:
        self.db = db

    def login(self, username: object, password: object) -> Any:
        clean = str(username or "").strip().lower()
        if not clean or not str(password or ""):
            raise AuthenticationError("Please enter your username and password.")
        row = self.db.fetch_one("SELECT * FROM users WHERE username = ?", (clean,))
        if row is None or not verify_password(
            str(password), row["password_salt"], row["password_hash"]
        ):
            log.warning("Failed login attempt for username '%s'", clean)
            raise AuthenticationError("Incorrect username or password.")
        if not bool(row["is_active"]):
            raise AuthenticationError("This account is deactivated. Contact an administrator.")
        from app.models import User

        log.info("User '%s' logged in", clean)
        return User.from_row(row)

    def list_users(self, include_inactive: bool = True) -> list[dict[str, Any]]:
        query = (
            "SELECT id, username, full_name, role, is_active, created_at FROM users"
        )
        if not include_inactive:
            query += " WHERE is_active = 1"
        query += " ORDER BY username"
        return self.db.rows_as_dicts(query)

    def create_user(self, *, username: object, full_name: object, role: object,
                    password: object, confirm: object | None = None,
                    is_active: bool = True) -> int:
        clean_user = v.username(username)
        name = v.text(full_name, "Full name", max_length=80)
        clean_role = v.choice(role, ("admin", "manager", "staff"), "Role")
        problems = password_problems(str(password or ""), None if confirm is None else str(confirm))
        if problems:
            raise ValidationError(" ".join(problems))
        if self.db.fetch_one("SELECT id FROM users WHERE username = ?", (clean_user,)):
            raise DataConflictError(f"Username '{clean_user}' already exists.")
        salt, digest = hash_password(str(password))
        now = now_iso()
        return self.db.execute(
            "INSERT INTO users (username, full_name, role, password_salt, password_hash, "
            "is_active, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (clean_user, name, clean_role, salt, digest, int(bool(is_active)), now, now),
        )

    def update_user(self, user_id: int, *, full_name: object | None = None,
                    role: object | None = None, is_active: bool | None = None) -> None:
        current = self.db.fetch_one("SELECT * FROM users WHERE id = ?", (user_id,))
        if current is None:
            raise NotFoundError("That user no longer exists.")
        name = v.text(full_name, "Full name", max_length=80) if full_name is not None else current["full_name"]
        clean_role = (
            v.choice(role, ("admin", "manager", "staff"), "Role")
            if role is not None
            else current["role"]
        )
        active = int(bool(is_active)) if is_active is not None else int(bool(current["is_active"]))
        if current["role"] == "admin" and not active:
            admins = self.db.count("users", "role = 'admin' AND is_active = 1 AND id <> ?", (user_id,))
            if admins == 0:
                raise OperationError("At least one active administrator is required.")
        self.db.execute(
            "UPDATE users SET full_name = ?, role = ?, is_active = ?, updated_at = ? WHERE id = ?",
            (name, clean_role, active, now_iso(), user_id),
        )

    def reset_password(self, user_id: int, new_password: object, confirm: object) -> None:
        problems = password_problems(str(new_password or ""), str(confirm or ""))
        if problems:
            raise ValidationError(" ".join(problems))
        salt, digest = hash_password(str(new_password))
        self.db.execute(
            "UPDATE users SET password_salt = ?, password_hash = ?, updated_at = ? WHERE id = ?",
            (salt, digest, now_iso(), user_id),
        )

    def change_password(self, user_id: int, current_password: object,
                        new_password: object, confirm: object) -> None:
        row = self.db.fetch_one("SELECT * FROM users WHERE id = ?", (user_id,))
        if row is None:
            raise NotFoundError("That user no longer exists.")
        if not verify_password(str(current_password or ""), row["password_salt"], row["password_hash"]):
            raise AuthenticationError("Your current password is not correct.")
        self.reset_password(user_id, new_password, confirm)


# -------------------------------------------------------------------- vehicles
class VehicleService:
    def __init__(self, db: "DatabaseManager") -> None:
        self.db = db

    def _select(self, search: object = "", status: object = "",
                include_archived: bool = False,
                extra_where: str = "") -> tuple[str, list[Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        term = str(search or "").strip()
        if term:
            like = _like(term)
            clauses.append(
                "(LOWER(v.plate_number) LIKE ? OR LOWER(v.brand) LIKE ? OR "
                "LOWER(v.model) LIKE ? OR LOWER(v.category) LIKE ? OR LOWER(v.status) LIKE ?)"
            )
            params += [like] * 5
        if status:
            clauses.append("v.status = ?")
            params.append(str(status).lower())
        if not include_archived:
            clauses.append("v.is_archived = 0")
        if extra_where:
            clauses.append(extra_where)
        where = " AND ".join(clauses) if clauses else "1 = 1"
        return where, params

    def list_vehicles(self, search: object = "", status: object = "",
                      include_archived: bool = False) -> list[dict[str, Any]]:
        where, params = self._select(search, status, include_archived)
        query = (
            "SELECT v.*, (SELECT b.booking_code FROM bookings b WHERE b.vehicle_id = v.id "
            "  AND b.status IN ('pending','confirmed','ongoing') "
            "  ORDER BY b.start_date DESC LIMIT 1) AS active_booking "
            f"FROM vehicles v WHERE {where} ORDER BY v.is_archived, v.plate_number"
        )
        return self.db.rows_as_dicts(query, params)

    def get(self, vehicle_id: int) -> Vehicle:
        row = self.db.fetch_one("SELECT * FROM vehicles WHERE id = ?", (vehicle_id,))
        if row is None:
            raise NotFoundError("That vehicle record no longer exists.")
        return Vehicle.from_row(row)

    def active_bookings_for(self, vehicle_id: int) -> list[dict[str, Any]]:
        placeholders = ",".join("?" for _ in ACTIVE_BOOKING_STATUSES)
        return self.db.rows_as_dicts(
            f"SELECT * FROM bookings WHERE vehicle_id = ? AND status IN ({placeholders}) "
            "ORDER BY start_date",
            [vehicle_id, *ACTIVE_BOOKING_STATUSES],
        )

    def create(self, *, plate_number: object, brand: object, model: object,
               category: object = "Sedan", year: object = 2020, seats: object = 4,
               rate_per_day: object = 0, status: object = "available",
               latitude: object = "", longitude: object = "", notes: object = "",
               image_path: object = "") -> int:
        plate = v.plate_number(plate_number)
        clean_brand = v.text(brand, "Brand", max_length=60)
        clean_model = v.text(model, "Model", max_length=80)
        clean_category = v.text(category, "Category", max_length=40)
        clean_year = v.integer(year, "Year", minimum=1980, maximum=2100)
        clean_seats = v.integer(seats, "Seats", minimum=1, maximum=80)
        rate = v.decimal(rate_per_day, "Rate per day")
        clean_status = v.choice(status, VEHICLE_STATUSES + ["archived"], "Status")
        lat, lon = v.coordinates(latitude, longitude)
        if self.db.fetch_one("SELECT id FROM vehicles WHERE plate_number = ?", (plate,)):
            raise DataConflictError(f"Plate number {plate} is already registered.")
        now = now_iso()
        vehicle_id = self.db.execute(
            "INSERT INTO vehicles (plate_number, brand, model, category, year, seats, "
            "rate_per_day, status, is_archived, latitude, longitude, image_path, notes, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (plate, clean_brand, clean_model, clean_category, clean_year, clean_seats, rate,
             "available" if clean_status == "archived" else clean_status,
             1 if clean_status == "archived" else 0, lat, lon,
             str(image_path or "") or None, v.text(notes, "Notes", required=False, max_length=500),
             now, now),
        )
        log.info("Vehicle %s created (id=%s)", plate, vehicle_id)
        return vehicle_id

    def update(self, vehicle_id: int, **fields: Any) -> None:
        vehicle = self.get(vehicle_id)
        plate = v.plate_number(fields.get("plate_number", vehicle.plate_number))
        duplicate = self.db.fetch_one(
            "SELECT id FROM vehicles WHERE plate_number = ? AND id <> ?", (plate, vehicle_id)
        )
        if duplicate:
            raise DataConflictError(f"Plate number {plate} is already registered.")
        lat, lon = v.coordinates(
            fields.get("latitude", vehicle.latitude), fields.get("longitude", vehicle.longitude)
        )
        status = v.choice(fields.get("status", vehicle.status), VEHICLE_STATUSES, "Status")
        self.db.execute(
            "UPDATE vehicles SET plate_number = ?, brand = ?, model = ?, category = ?, year = ?, "
            "seats = ?, rate_per_day = ?, status = ?, latitude = ?, longitude = ?, image_path = ?, "
            "notes = ?, updated_at = ? WHERE id = ?",
            (plate, v.text(fields.get("brand", vehicle.brand), "Brand", max_length=60),
             v.text(fields.get("model", vehicle.model), "Model", max_length=80),
             v.text(fields.get("category", vehicle.category), "Category", max_length=40),
             v.integer(fields.get("year", vehicle.year), "Year", minimum=1980, maximum=2100),
             v.integer(fields.get("seats", vehicle.seats), "Seats", minimum=1, maximum=80),
             v.decimal(fields.get("rate_per_day", vehicle.rate_per_day), "Rate per day"),
             status, lat, lon, str(fields.get("image_path", vehicle.image_path) or "") or None,
             v.text(fields.get("notes", vehicle.notes), "Notes", required=False, max_length=500),
             now_iso(), vehicle_id),
        )
        log.info("Vehicle %s updated", plate)

    def set_status(self, vehicle_id: int, status: object) -> None:
        clean = v.choice(status, VEHICLE_STATUSES, "Status")
        self.get(vehicle_id)
        self.db.execute(
            "UPDATE vehicles SET status = ?, updated_at = ? WHERE id = ?",
            (clean, now_iso(), vehicle_id),
        )

    def set_archived(self, vehicle_id: int, archived: bool) -> None:
        self.get(vehicle_id)
        active = self.active_bookings_for(vehicle_id)
        if archived and active:
            raise OperationError("Archive is blocked: this vehicle has active bookings.")
        if archived:
            status = "maintenance"
        elif any(booking["status"] == "ongoing" for booking in active):
            status = "rented"          # still out on rent
        else:
            status = "available"
        self.db.execute(
            "UPDATE vehicles SET is_archived = ?, status = ?, updated_at = ? WHERE id = ?",
            (int(bool(archived)), status, now_iso(), vehicle_id),
        )
        log.info("Vehicle %s archive=%s", vehicle_id, archived)

    def update_location(self, vehicle_id: int, latitude: object, longitude: object) -> None:
        self.get(vehicle_id)
        lat, lon = v.coordinates(latitude, longitude)
        self.db.execute(
            "UPDATE vehicles SET latitude = ?, longitude = ?, updated_at = ? WHERE id = ?",
            (lat, lon, now_iso(), vehicle_id),
        )

    def store_image(self, vehicle_id: int, source: object) -> str:
        """Copy a chosen picture into the local images folder; returns its name."""
        raw = Path(str(source or "")).expanduser()
        if not raw.exists() or not raw.is_file():
            raise ValidationError("The selected image file could not be read.")
        if raw.suffix.lower() not in ALLOWED_IMAGE_SUFFIXES:
            raise ValidationError("Only PNG, JPG, JPEG, GIF, BMP or WEBP images are allowed.")
        if raw.stat().st_size > MAX_IMAGE_BYTES:
            raise ValidationError("The image is larger than 8 MB.")
        try:
            from PIL import Image  # noqa: WPS433 - optional at runtime

            with Image.open(raw) as picture:
                picture.verify()
        except Exception:  # pragma: no cover - depends on Pillow/file
            raise ValidationError("That file is not a valid image.") from None
        IMAGE_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        target = IMAGE_DIR / f"vehicle_{vehicle_id}_{stamp}{raw.suffix.lower()}"
        try:
            shutil.copy2(raw, target)
        except OSError as exc:
            log.exception("Could not copy the vehicle image")
            raise OperationError("The image could not be saved to the application folder.") from exc
        self.db.execute(
            "UPDATE vehicles SET image_path = ?, updated_at = ? WHERE id = ?",
            (target.name, now_iso(), vehicle_id),
        )
        return target.name

    def stats(self) -> dict[str, int]:
        return {
            "total": self.db.count("vehicles", "is_archived = 0"),
            "available": self.db.count("vehicles", "status = 'available' AND is_archived = 0"),
            "rented": self.db.count("vehicles", "status = 'rented' AND is_archived = 0"),
            "maintenance": self.db.count("vehicles", "status = 'maintenance' AND is_archived = 0"),
            "archived": self.db.count("vehicles", "is_archived = 1"),
        }


# ------------------------------------------------------------------- customers
class CustomerService:
    def __init__(self, db: "DatabaseManager") -> None:
        self.db = db

    def list_customers(self, search: object = "", include_archived: bool = False) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        term = str(search or "").strip()
        if term:
            like = _like(term)
            clauses.append(
                "(LOWER(c.full_name) LIKE ? OR LOWER(c.phone) LIKE ? OR LOWER(c.email) LIKE ? "
                "OR LOWER(c.license_number) LIKE ?)"
            )
            params += [like] * 4
        if not include_archived:
            clauses.append("c.is_archived = 0")
        where = " AND ".join(clauses) if clauses else "1 = 1"
        return self.db.rows_as_dicts(
            "SELECT c.*, (SELECT COUNT(*) FROM bookings b WHERE b.customer_id = c.id) AS bookings_count "
            f"FROM customers c WHERE {where} ORDER BY c.full_name",
            params,
        )

    def get(self, customer_id: int) -> dict[str, Any]:
        row = self.db.fetch_one("SELECT * FROM customers WHERE id = ?", (customer_id,))
        if row is None:
            raise NotFoundError("That customer record no longer exists.")
        return dict(row)

    def create(self, *, full_name: object, phone: object, email: object = "",
               address: object = "", id_type: object = "Drivers License",
               id_number: object = "", license_number: object = "",
               notes: object = "") -> int:
        name = v.text(full_name, "Customer name", max_length=90)
        clean_phone = v.phone(phone)
        clean_email = v.email(email, "Email", required=False)
        clean_license = v.text(license_number, "License number", required=False, max_length=40)
        if clean_license and not clean_license.replace("-", "").isalnum():
            raise ValidationError("License number must be letters and numbers only.")
        now = now_iso()
        return self.db.execute(
            "INSERT INTO customers (full_name, phone, email, address, id_type, id_number, "
            "license_number, is_archived, notes, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)",
            (name, clean_phone, clean_email, v.text(address, "Address", required=False, max_length=200),
             v.text(id_type, "ID type", max_length=40), v.text(id_number, "ID number", required=False, max_length=40),
             clean_license, v.text(notes, "Notes", required=False, max_length=500), now, now),
        )

    def update(self, customer_id: int, **fields: Any) -> None:
        current = self.get(customer_id)
        license_raw = v.text(fields.get("license_number", current["license_number"] or ""),
                             "License number", required=False, max_length=40)
        if license_raw and not license_raw.replace("-", "").isalnum():
            raise ValidationError("License number must be letters and numbers only.")
        self.db.execute(
            "UPDATE customers SET full_name = ?, phone = ?, email = ?, address = ?, id_type = ?, "
            "id_number = ?, license_number = ?, notes = ?, updated_at = ? WHERE id = ?",
            (v.text(fields.get("full_name", current["full_name"]), "Customer name", max_length=90),
             v.phone(fields.get("phone", current["phone"])),
             v.email(fields.get("email", current["email"] or ""), "Email", required=False),
             v.text(fields.get("address", current["address"] or ""), "Address", required=False, max_length=200),
             v.text(fields.get("id_type", current["id_type"]), "ID type", max_length=40),
             v.text(fields.get("id_number", current["id_number"] or ""), "ID number", required=False, max_length=40),
             license_raw,
             v.text(fields.get("notes", current["notes"] or ""), "Notes", required=False, max_length=500),
             now_iso(), customer_id),
        )

    def set_archived(self, customer_id: int, archived: bool) -> None:
        self.get(customer_id)
        if archived:
            placeholders = ",".join("?" for _ in ACTIVE_BOOKING_STATUSES)
            active = self.db.count(
                "bookings",
                f"customer_id = ? AND status IN ({placeholders})",
                [customer_id, *ACTIVE_BOOKING_STATUSES],
            )
            if active:
                raise OperationError("Archive is blocked: this customer has active bookings.")
        self.db.execute(
            "UPDATE customers SET is_archived = ?, updated_at = ? WHERE id = ?",
            (int(bool(archived)), now_iso(), customer_id),
        )


# -------------------------------------------------------------------- bookings
class BookingService:
    def __init__(self, db: "DatabaseManager") -> None:
        self.db = db
        self.vehicles = VehicleService(db)
        self.customers = CustomerService(db)

    def next_code(self) -> str:
        year = date.today().year
        count = self.db.count("bookings") + 1
        code = f"BK-{year}-{count:04d}"
        while self.db.fetch_one("SELECT id FROM bookings WHERE booking_code = ?", (code,)):
            count += 1
            code = f"BK-{year}-{count:04d}"
        return code

    def list_bookings(self, search: object = "", status: object = "",
                      include_archived: bool = False) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        term = str(search or "").strip()
        if term:
            like = _like(term)
            clauses.append(
                "(LOWER(b.booking_code) LIKE ? OR LOWER(v.plate_number) LIKE ? OR "
                "LOWER(c.full_name) LIKE ? OR LOWER(b.destination) LIKE ?)"
            )
            params += [like] * 4
        if status:
            clauses.append("b.status = ?")
            params.append(str(status).lower())
        if not include_archived:
            clauses.append("b.is_archived = 0")
        where = " AND ".join(clauses) if clauses else "1 = 1"
        return self.db.rows_as_dicts(
            "SELECT b.*, v.plate_number, v.brand, v.model, c.full_name AS customer_name, "
            "c.phone AS customer_phone, "
            "COALESCE((SELECT SUM(CASE WHEN t.entry_type = 'refund' THEN -t.amount ELSE t.amount END) "
            "  FROM transactions t WHERE t.booking_id = b.id), 0) AS paid_amount "
            "FROM bookings b JOIN vehicles v ON v.id = b.vehicle_id "
            "JOIN customers c ON c.id = b.customer_id "
            f"WHERE {where} ORDER BY b.start_date DESC, b.id DESC",
            params,
        )

    def get(self, booking_id: int) -> dict[str, Any]:
        rows = self.list_bookings(include_archived=True)
        for row in rows:
            if int(row["id"]) == int(booking_id):
                return row
        raise NotFoundError("That booking no longer exists.")

    def quote(self, vehicle_id: int, start: object, end: object) -> dict[str, Any]:
        first, last = v.date_range(start, end, "Start date", "End date")
        days = max(1, (last - first).days + 1)
        vehicle = self.vehicles.get(vehicle_id)
        total = round(days * vehicle.rate_per_day, 2)
        return {
            "rental_days": days,
            "rate_per_day": vehicle.rate_per_day,
            "total_amount": total,
            "start_date": first.isoformat(),
            "end_date": last.isoformat(),
            "vehicle": f"{vehicle.plate_number} {vehicle.brand} {vehicle.model}",
        }

    def _check_overlap(self, vehicle_id: int, start: str, end: str, exclude: int | None) -> None:
        placeholders = ",".join("?" for _ in ACTIVE_BOOKING_STATUSES)
        params: list[Any] = [vehicle_id, *ACTIVE_BOOKING_STATUSES, end, start]
        query = (
            f"SELECT booking_code FROM bookings WHERE vehicle_id = ? AND status IN ({placeholders}) "
            "AND start_date <= ? AND end_date >= ?"
        )
        if exclude:
            query += " AND id <> ?"
            params.append(exclude)
        clash = self.db.fetch_one(query, params)
        if clash:
            raise DataConflictError(
                f"Those dates clash with booking {clash['booking_code']} for this vehicle."
            )

    def create(self, *, vehicle_id: int, customer_id: int, start_date: object,
               end_date: object, pickup_location: object = "", destination: object = "",
               deposit: object = 0, status: object = "pending", notes: object = "",
               user_id: int | None = None) -> int:
        vehicle = self.vehicles.get(vehicle_id)
        self.customers.get(customer_id)
        if vehicle.is_archived:
            raise OperationError("Archived vehicles cannot be booked.")
        if vehicle.status == "maintenance":
            raise OperationError("This vehicle is under maintenance and cannot be booked.")
        first, last = v.date_range(start_date, end_date, "Start date", "End date")
        days = max(1, (last - first).days + 1)
        total = round(days * float(vehicle.rate_per_day), 2)
        clean_status = v.choice(status, list(ACTIVE_BOOKING_STATUSES) + ["completed", "cancelled"], "Status")
        self._check_overlap(vehicle.id, first.isoformat(), last.isoformat(), None)
        code = self.next_code()
        now = now_iso()
        booking_id = self.db.execute(
            "INSERT INTO bookings (booking_code, vehicle_id, customer_id, start_date, end_date, "
            "pickup_location, destination, rental_days, rate_per_day, total_amount, deposit, status, "
            "is_archived, notes, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)",
            (code, vehicle_id, customer_id, first.isoformat(), last.isoformat(),
             v.text(pickup_location, "Pickup location", required=False, max_length=150),
             v.text(destination, "Destination", required=False, max_length=150),
             days, float(vehicle.rate_per_day), total, v.decimal(deposit, "Deposit"),
             clean_status, v.text(notes, "Notes", required=False, max_length=500), now, now),
        )
        if clean_status == "ongoing":
            self.vehicles.set_status(vehicle_id, "rented")
        log.info("Booking %s created by user %s", code, user_id)
        return booking_id

    def update(self, booking_id: int, **fields: Any) -> None:
        row = self.db.fetch_one("SELECT * FROM bookings WHERE id = ?", (booking_id,))
        if row is None:
            raise NotFoundError("That booking no longer exists.")
        previous = str(row["status"])
        first, last = v.date_range(
            fields.get("start_date", row["start_date"]),
            fields.get("end_date", row["end_date"]),
            "Start date", "End date",
        )
        days = max(1, (last - first).days + 1)
        vehicle_id = int(fields.get("vehicle_id", row["vehicle_id"]))
        customer_id = int(fields.get("customer_id", row["customer_id"]))
        rate = v.decimal(fields.get("rate_per_day", row["rate_per_day"]), "Rate per day")
        status = v.choice(fields.get("status", row["status"]),
                          list(ACTIVE_BOOKING_STATUSES) + ["completed", "cancelled"], "Status")
        self._check_overlap(vehicle_id, first.isoformat(), last.isoformat(), booking_id)
        self.db.execute(
            "UPDATE bookings SET vehicle_id = ?, customer_id = ?, start_date = ?, end_date = ?, "
            "pickup_location = ?, destination = ?, rental_days = ?, rate_per_day = ?, "
            "total_amount = ?, deposit = ?, status = ?, notes = ?, updated_at = ? WHERE id = ?",
            (vehicle_id, customer_id, first.isoformat(), last.isoformat(),
             v.text(fields.get("pickup_location", row["pickup_location"] or ""),
                    "Pickup location", required=False, max_length=150),
             v.text(fields.get("destination", row["destination"] or ""),
                    "Destination", required=False, max_length=150),
             days, rate, round(days * rate, 2),
             v.decimal(fields.get("deposit", row["deposit"]), "Deposit"), status,
             v.text(fields.get("notes", row["notes"] or ""), "Notes", required=False, max_length=500),
             now_iso(), booking_id),
        )
        if status == "ongoing":
            self.vehicles.set_status(vehicle_id, "rented")
        elif previous == "ongoing":
            still_rented = self.db.count(
                "bookings", "vehicle_id = ? AND id <> ? AND status = 'ongoing'",
                (vehicle_id, booking_id))
            if still_rented == 0:
                self.vehicles.set_status(vehicle_id, "available")

    def set_status(self, booking_id: int, status: object, user_id: int | None = None) -> None:
        row = self.db.fetch_one("SELECT * FROM bookings WHERE id = ?", (booking_id,))
        if row is None:
            raise NotFoundError("That booking no longer exists.")
        clean = v.choice(status, list(ACTIVE_BOOKING_STATUSES) + ["completed", "cancelled"], "Status")
        previous = str(row["status"])
        if previous == clean:
            return
        if previous == "completed":
            raise OperationError("A completed booking cannot be reopened.")
        self.db.execute(
            "UPDATE bookings SET status = ?, updated_at = ? WHERE id = ?",
            (clean, now_iso(), booking_id),
        )
        if clean == "ongoing":
            self.vehicles.set_status(int(row["vehicle_id"]), "rented")
        elif clean in ("completed", "cancelled"):
            others = self.db.count(
                "bookings",
                "vehicle_id = ? AND id <> ? AND status = 'ongoing'",
                (row["vehicle_id"], booking_id),
            )
            if others == 0 and previous == "ongoing":
                self.vehicles.set_status(int(row["vehicle_id"]), "available")
        log.info("Booking %s status %s -> %s (user %s)", row["booking_code"], previous, clean, user_id)

    def set_archived(self, booking_id: int, archived: bool) -> None:
        row = self.db.fetch_one("SELECT id FROM bookings WHERE id = ?", (booking_id,))
        if row is None:
            raise NotFoundError("That booking no longer exists.")
        self.db.execute(
            "UPDATE bookings SET is_archived = ?, updated_at = ? WHERE id = ?",
            (int(bool(archived)), now_iso(), booking_id),
        )

    def upcoming_returns(self, days_ahead: int = 7, limit: int = 10) -> list[dict[str, Any]]:
        horizon = (date.today() + timedelta(days=days_ahead)).isoformat()
        return self.db.rows_as_dicts(
            "SELECT b.booking_code, b.end_date, b.status, b.total_amount, v.plate_number, "
            "c.full_name AS customer_name, b.vehicle_id, b.customer_id, b.id "
            "FROM bookings b JOIN vehicles v ON v.id = b.vehicle_id "
            "JOIN customers c ON c.id = b.customer_id "
            "WHERE b.status IN ('pending','confirmed','ongoing') AND b.end_date <= ? "
            "ORDER BY b.end_date LIMIT ?",
            (horizon, limit),
        )


# ---------------------------------------------------------------- transactions
class TransactionService:
    def __init__(self, db: "DatabaseManager") -> None:
        self.db = db

    def next_reference(self) -> str:
        count = self.db.count("transactions") + 1
        reference = f"TXN-{count:05d}"
        while self.db.fetch_one("SELECT id FROM transactions WHERE reference = ?", (reference,)):
            count += 1
            reference = f"TXN-{count:05d}"
        return reference

    def list_transactions(self, search: object = "", start: object = "",
                          end: object = "") -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        term = str(search or "").strip()
        if term:
            like = _like(term)
            clauses.append(
                "(LOWER(t.reference) LIKE ? OR LOWER(t.method) LIKE ? OR "
                "LOWER(v.plate_number) LIKE ? OR LOWER(c.full_name) LIKE ? OR LOWER(b.booking_code) LIKE ?)"
            )
            params += [like] * 5
        if start:
            clauses.append("date(t.paid_at) >= ?")
            params.append(v.iso_date(start, "From date").isoformat())
        if end:
            clauses.append("date(t.paid_at) <= ?")
            params.append(v.iso_date(end, "To date").isoformat())
        where = " AND ".join(clauses) if clauses else "1 = 1"
        return self.db.rows_as_dicts(
            "SELECT t.*, b.booking_code, v.plate_number, c.full_name AS customer_name, "
            "u.username AS recorded_by_name FROM transactions t "
            "LEFT JOIN bookings b ON b.id = t.booking_id "
            "LEFT JOIN vehicles v ON v.id = b.vehicle_id "
            "LEFT JOIN customers c ON c.id = b.customer_id "
            "LEFT JOIN users u ON u.id = t.recorded_by "
            f"WHERE {where} ORDER BY t.paid_at DESC, t.id DESC",
            params,
        )

    def record_payment(self, *, booking_id: int, amount: object, method: object = "cash",
                       entry_type: object = "payment", notes: object = "",
                       user_id: int | None = None,
                       paid_at: object | None = None) -> int:
        row = self.db.fetch_one("SELECT * FROM bookings WHERE id = ?", (booking_id,))
        if row is None:
            raise NotFoundError("That booking no longer exists.")
        value = v.decimal(amount, "Amount")
        if value <= 0:
            raise ValidationError("Amount must be greater than zero.")
        clean_method = v.choice(method, ("cash", "card", "bank transfer", "mobile wallet"), "Method")
        clean_type = v.choice(entry_type, ("payment", "deposit", "refund"), "Entry type")
        clean_paid_at = (
            v.iso_datetime(paid_at, "Payment date").strftime("%Y-%m-%d %H:%M:%S")
            if paid_at else now_iso()
        )
        transaction_id = self.db.execute(
            "INSERT INTO transactions (reference, booking_id, amount, method, entry_type, paid_at, "
            "recorded_by, notes, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (self.next_reference(), booking_id, value, clean_method, clean_type, clean_paid_at,
             user_id, v.text(notes, "Notes", required=False, max_length=300), now_iso()),
        )
        if str(row["status"]) == "pending" and clean_type in ("payment", "deposit"):
            self.db.execute(
                "UPDATE bookings SET status = 'confirmed', updated_at = ? WHERE id = ?",
                (now_iso(), booking_id),
            )
        log.info("Transaction %s recorded for booking %s", clean_type, row["booking_code"])
        return transaction_id

    def delete(self, transaction_id: int) -> None:
        row = self.db.fetch_one("SELECT id FROM transactions WHERE id = ?", (transaction_id,))
        if row is None:
            raise NotFoundError("That transaction no longer exists.")
        self.db.execute("DELETE FROM transactions WHERE id = ?", (transaction_id,))

    def paid_for_booking(self, booking_id: int) -> float:
        value = self.db.scalar(
            "SELECT COALESCE(SUM(CASE WHEN entry_type = 'refund' THEN -amount ELSE amount END), 0) "
            "FROM transactions WHERE booking_id = ?",
            (booking_id,),
        )
        return round(float(value or 0), 2)

    def totals(self, start: object = "", end: object = "") -> dict[str, Any]:
        clauses: list[str] = []
        params: list[Any] = []
        if start:
            clauses.append("date(paid_at) >= ?")
            params.append(v.iso_date(start, "From date").isoformat())
        if end:
            clauses.append("date(paid_at) <= ?")
            params.append(v.iso_date(end, "To date").isoformat())
        where = " AND ".join(clauses) if clauses else "1 = 1"
        row = self.db.fetch_one(
            f"SELECT COUNT(*) AS entries, "
            "COALESCE(SUM(CASE WHEN entry_type = 'refund' THEN -amount ELSE amount END), 0) AS net, "
            "COALESCE(SUM(CASE WHEN entry_type = 'refund' THEN amount ELSE 0 END), 0) AS refunds "
            f"FROM transactions WHERE {where}",
            params,
        )
        return {
            "entries": int(row["entries"] if row else 0),
            "net": round(float(row["net"] if row else 0), 2),
            "refunds": round(float(row["refunds"] if row else 0), 2),
        }


# ------------------------------------------------------------------ flood zones
class FloodZoneService:
    def __init__(self, db: "DatabaseManager") -> None:
        self.db = db

    def list_zones(self, active_only: bool = True) -> list[dict[str, Any]]:
        where = "is_active = 1" if active_only else "1 = 1"
        return self.db.rows_as_dicts(
            f"SELECT * FROM flood_zones WHERE {where} ORDER BY "
            "CASE risk_level WHEN 'severe' THEN 0 WHEN 'high' THEN 1 WHEN 'moderate' THEN 2 ELSE 3 END, name"
        )

    def get(self, zone_id: int) -> dict[str, Any]:
        row = self.db.fetch_one("SELECT * FROM flood_zones WHERE id = ?", (zone_id,))
        if row is None:
            raise NotFoundError("That flood zone no longer exists.")
        return dict(row)

    def create(self, *, name: object, barangay: object = "", risk_level: object = "moderate",
               latitude: object, longitude: object, radius_km: object = 1.0,
               notes: object = "") -> int:
        lat, lon = v.coordinates(latitude, longitude)
        now = now_iso()
        return self.db.execute(
            "INSERT INTO flood_zones (name, barangay, risk_level, latitude, longitude, radius_km, "
            "is_active, notes, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?)",
            (v.text(name, "Zone name", max_length=90),
             v.text(barangay, "Barangay / city", required=False, max_length=90),
             v.choice(risk_level, RISK_LEVELS, "Risk level"), lat, lon,
             v.decimal(radius_km, "Radius (km)"), v.text(notes, "Notes", required=False, max_length=400),
             now, now),
        )

    def update(self, zone_id: int, **fields: Any) -> None:
        current = self.get(zone_id)
        lat, lon = v.coordinates(fields.get("latitude", current["latitude"]),
                                 fields.get("longitude", current["longitude"]))
        self.db.execute(
            "UPDATE flood_zones SET name = ?, barangay = ?, risk_level = ?, latitude = ?, "
            "longitude = ?, radius_km = ?, notes = ?, updated_at = ? WHERE id = ?",
            (v.text(fields.get("name", current["name"]), "Zone name", max_length=90),
             v.text(fields.get("barangay", current["barangay"] or ""), "Barangay / city",
                    required=False, max_length=90),
             v.choice(fields.get("risk_level", current["risk_level"]), RISK_LEVELS, "Risk level"),
             lat, lon, v.decimal(fields.get("radius_km", current["radius_km"]), "Radius (km)"),
             v.text(fields.get("notes", current["notes"] or ""), "Notes", required=False, max_length=400),
             now_iso(), zone_id),
        )

    def set_active(self, zone_id: int, active: bool) -> None:
        self.get(zone_id)
        self.db.execute(
            "UPDATE flood_zones SET is_active = ?, updated_at = ? WHERE id = ?",
            (int(bool(active)), now_iso(), zone_id),
        )

    def delete(self, zone_id: int) -> None:
        self.get(zone_id)
        self.db.execute("DELETE FROM flood_zones WHERE id = ?", (zone_id,))


# ---------------------------------------------------------------------- alerts
class AlertService:
    def __init__(self, db: "DatabaseManager") -> None:
        self.db = db
        self.zones = FloodZoneService(db)

    def list_alerts(self, status: object = "", search: object = "",
                    limit: int = 200) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if status:
            clauses.append("a.status = ?")
            params.append(str(status).lower())
        term = str(search or "").strip()
        if term:
            like = _like(term)
            clauses.append("(LOWER(a.title) LIKE ? OR LOWER(a.message) LIKE ? OR LOWER(v.plate_number) LIKE ?)")
            params += [like] * 3
        where = " AND ".join(clauses) if clauses else "1 = 1"
        return self.db.rows_as_dicts(
            "SELECT a.*, v.plate_number, z.name AS zone_name, u.username AS created_by_name "
            "FROM alerts a LEFT JOIN vehicles v ON v.id = a.vehicle_id "
            "LEFT JOIN flood_zones z ON z.id = a.zone_id "
            "LEFT JOIN users u ON u.id = a.created_by "
            f"WHERE {where} ORDER BY a.created_at DESC, a.id DESC LIMIT ?",
            [*params, limit],
        )

    def create(self, *, title: object, message: object, severity: object = "info",
               source: object = "manual", vehicle_id: int | None = None,
               zone_id: int | None = None, user_id: int | None = None) -> int:
        now = now_iso()
        return self.db.execute(
            "INSERT INTO alerts (title, message, severity, source, vehicle_id, zone_id, status, "
            "created_by, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, 'new', ?, ?, ?)",
            (v.text(title, "Title", max_length=120), v.text(message, "Message", max_length=600),
             v.choice(severity, ("info", "warning", "critical"), "Severity"),
             v.text(source, "Source", max_length=20), vehicle_id, zone_id, user_id, now, now),
        )

    def generate_flood_alerts(self, user_id: int | None = None,
                              threshold: object = "high") -> int:
        """Scan the fleet and raise alerts for vehicles at/above *threshold* risk."""
        clean_threshold = v.choice(threshold, RISK_LEVELS, "Threshold")
        minimum = RISK_WEIGHTS[clean_threshold]
        zones = self.zones.list_zones(active_only=True)
        created = 0
        today_prefix = today_iso()
        for vehicle in VehicleService(self.db).list_vehicles():
            assessment = assess_position(
                float(vehicle["latitude"] or 0), float(vehicle["longitude"] or 0), zones
            )
            if not assessment["has_position"]:
                continue
            level_weight = RISK_WEIGHTS.get(assessment["level"], 0)
            if level_weight < minimum:
                continue
            title = f"Flood risk {assessment['level'].upper()} - {vehicle['plate_number']}"
            duplicate = self.db.fetch_one(
                "SELECT id FROM alerts WHERE vehicle_id = ? AND title = ? "
                "AND status IN ('new','acknowledged') AND created_at LIKE ?",
                (vehicle["id"], title, f"{today_prefix}%"),
            )
            if duplicate:
                continue
            message = (
                f"{vehicle['plate_number']} ({vehicle['brand']} {vehicle['model']}) scored "
                f"{assessment['score']}/100. Nearest zone: {assessment['nearest_zone']} "
                f"({assessment['distance_km']:.2f} km). {assessment['reasons'][0]}"
            )
            self.create(title=title, message=message,
                        severity="critical" if assessment["level"] == "severe" else "warning",
                        source="system", vehicle_id=int(vehicle["id"]), user_id=user_id)
            created += 1
        log.info("Flood alert scan created %d alert(s)", created)
        return created

    def set_status(self, alert_id: int, status: object) -> None:
        clean = v.choice(status, ("new", "acknowledged", "resolved"), "Status")
        row = self.db.fetch_one("SELECT id FROM alerts WHERE id = ?", (alert_id,))
        if row is None:
            raise NotFoundError("That alert no longer exists.")
        self.db.execute(
            "UPDATE alerts SET status = ?, updated_at = ? WHERE id = ?",
            (clean, now_iso(), alert_id),
        )

    def delete(self, alert_id: int) -> None:
        row = self.db.fetch_one("SELECT id FROM alerts WHERE id = ?", (alert_id,))
        if row is None:
            raise NotFoundError("That alert no longer exists.")
        self.db.execute("DELETE FROM alerts WHERE id = ?", (alert_id,))

    def open_count(self) -> int:
        return self.db.count("alerts", "status <> 'resolved'")


# ------------------------------------------------------------------- dashboard
class DashboardService:
    def __init__(self, db: "DatabaseManager") -> None:
        self.db = db
        self.vehicles = VehicleService(db)
        self.bookings = BookingService(db)
        self.alerts = AlertService(db)
        self.zones = FloodZoneService(db)
        self.transactions = TransactionService(db)

    def risk_distribution(self) -> dict[str, int]:
        """Vehicle count per flood-risk level (works completely offline)."""
        zones = self.zones.list_zones(active_only=True)
        counts = {level: 0 for level in RISK_ORDER}
        counts["unknown"] = 0
        for vehicle in self.vehicles.list_vehicles():
            assessment = assess_position(
                float(vehicle["latitude"] or 0), float(vehicle["longitude"] or 0), zones
            )
            level = assessment["level"] if assessment["has_position"] else "unknown"
            counts[level] = counts.get(level, 0) + 1
        return counts

    def summary(self) -> dict[str, Any]:
        month_start = date.today().replace(day=1).isoformat()
        revenue_month = self.transactions.totals(start=month_start)
        zones = self.zones.list_zones(active_only=True)
        distribution = self.risk_distribution()
        high_risk = sum(count for level, count in distribution.items()
                        if RISK_WEIGHTS.get(level, 0) >= RISK_WEIGHTS["high"])
        placeholders = ",".join("?" for _ in ACTIVE_BOOKING_STATUSES)
        return {
            "vehicles": self.vehicles.stats(),
            "customers": self.db.count("customers", "is_archived = 0"),
            "bookings_active": self.db.count(
                "bookings", f"status IN ({placeholders})", list(ACTIVE_BOOKING_STATUSES)
            ),
            "bookings_total": self.db.count("bookings"),
            "revenue_month": revenue_month["net"],
            "revenue_entries": revenue_month["entries"],
            "open_alerts": self.alerts.open_count(),
            "high_risk_vehicles": high_risk,
            "flood_zones": len(zones),
        }

    def revenue_by_month(self, months: int = 6) -> list[dict[str, Any]]:
        first = (date.today().replace(day=1) - timedelta(days=30 * (months - 1)))
        start = first.replace(day=1).isoformat()
        return self.db.rows_as_dicts(
            "SELECT strftime('%Y-%m', paid_at) AS month, "
            "COALESCE(SUM(CASE WHEN entry_type = 'refund' THEN -amount ELSE amount END), 0) AS net, "
            "COUNT(*) AS entries FROM transactions WHERE date(paid_at) >= ? "
            "GROUP BY month ORDER BY month",
            (start,),
        )


# --------------------------------------------------------------------- reports
class ReportService:
    def __init__(self, db: "DatabaseManager") -> None:
        self.db = db
        self.vehicles = VehicleService(db)
        self.bookings = BookingService(db)
        self.customers = CustomerService(db)
        self.transactions = TransactionService(db)
        self.zones = FloodZoneService(db)

    @staticmethod
    def _money(value: Any) -> str:
        return f"{float(value or 0):,.2f}"

    def vehicle_report(self, include_archived: bool = False) -> ReportData:
        rows = self.vehicles.list_vehicles(include_archived=include_archived)
        return ReportData(
            title="Vehicle Inventory Report",
            subtitle="All fleet units with status and daily rate"
            if include_archived else "Active fleet units with status and daily rate",
            columns=["Plate", "Brand / Model", "Category", "Year", "Seats", "Rate/day",
                     "Status", "Booking", "Latitude", "Longitude"],
            rows=[[r["plate_number"], f"{r['brand']} {r['model']}", r["category"], r["year"],
                   r["seats"], self._money(r["rate_per_day"]), r["status"],
                   r["active_booking"] or "-", f"{float(r['latitude'] or 0):.5f}",
                   f"{float(r['longitude'] or 0):.5f}"] for r in rows],
            summary=[f"Vehicles listed: {len(rows)}"],
        )

    def booking_report(self, start: object = "", end: object = "",
                       include_archived: bool = False) -> ReportData:
        rows = self.bookings.list_bookings(include_archived=include_archived)
        if start or end:
            first = v.iso_date(start, "From date").isoformat() if start else "0000-00-00"
            last = v.iso_date(end, "To date").isoformat() if end else "9999-12-31"
            rows = [r for r in rows if first <= str(r["start_date"]) <= last]
        total = sum(float(r["total_amount"]) for r in rows)
        paid = sum(float(r["paid_amount"]) for r in rows)
        return ReportData(
            title="Booking Report",
            subtitle=f"Rentals from {start or 'beginning'} to {end or 'today'}",
            columns=["Code", "Vehicle", "Customer", "Start", "End", "Days", "Total",
                     "Paid", "Balance", "Status"],
            rows=[[r["booking_code"], r["plate_number"], r["customer_name"], r["start_date"],
                   r["end_date"], r["rental_days"], self._money(r["total_amount"]),
                   self._money(r["paid_amount"]),
                   self._money(float(r["total_amount"]) - float(r["paid_amount"])), r["status"]]
                  for r in rows],
            summary=[f"Bookings: {len(rows)}", f"Contract value: {self._money(total)}",
                     f"Collected: {self._money(paid)}",
                     f"Outstanding: {self._money(total - paid)}"],
        )

    def transaction_report(self, start: object = "", end: object = "") -> ReportData:
        rows = self.transactions.list_transactions(start=start, end=end)
        totals = self.transactions.totals(start=start, end=end)
        return ReportData(
            title="Transaction Report",
            subtitle=f"Payments from {start or 'beginning'} to {end or 'today'}",
            columns=["Reference", "Paid at", "Booking", "Vehicle", "Customer", "Type",
                     "Method", "Amount", "Recorded by"],
            rows=[[r["reference"], r["paid_at"], r["booking_code"] or "-", r["plate_number"] or "-",
                   r["customer_name"] or "-", r["entry_type"], r["method"],
                   self._money(r["amount"]), r["recorded_by_name"] or "-"] for r in rows],
            summary=[f"Entries: {totals['entries']}", f"Net collected: {self._money(totals['net'])}",
                     f"Refunds: {self._money(totals['refunds'])}"],
        )

    def customer_report(self) -> ReportData:
        rows = self.customers.list_customers(include_archived=True)
        return ReportData(
            title="Customer Report",
            subtitle="Registered renters with contact details",
            columns=["Name", "Contact", "Email", "ID type", "ID number", "License", "Bookings", "Archived"],
            rows=[[r["full_name"], r["phone"], r["email"] or "-", r["id_type"],
                   r["id_number"] or "-", r["license_number"] or "-", r["bookings_count"],
                   "Yes" if r["is_archived"] else "No"] for r in rows],
            summary=[f"Customers listed: {len(rows)}"],
        )

    def flood_risk_report(self) -> ReportData:
        zones = self.zones.list_zones(active_only=True)
        vehicles = self.vehicles.list_vehicles()
        rows = []
        counts = {level: 0 for level in RISK_ORDER}
        for vehicle in vehicles:
            assessment = assess_position(
                float(vehicle["latitude"] or 0), float(vehicle["longitude"] or 0), zones
            )
            level = assessment["level"]
            if level in counts:
                counts[level] += 1
            rows.append([vehicle["plate_number"], f"{vehicle['brand']} {vehicle['model']}",
                         vehicle["status"], f"{float(vehicle['latitude'] or 0):.5f}",
                         f"{float(vehicle['longitude'] or 0):.5f}",
                         assessment["nearest_zone"] or "-",
                         f"{assessment['distance_km']:.2f}" if assessment["has_position"] else "-",
                         assessment["score"], level])
        return ReportData(
            title="Flood Risk Assessment Report",
            subtitle="Vehicle positions scored against active flood zones",
            columns=["Plate", "Vehicle", "Status", "Latitude", "Longitude", "Nearest zone",
                     "Distance (km)", "Score", "Risk level"],
            rows=rows,
            summary=[f"Vehicles assessed: {len(vehicles)}",
                     f"Severe: {counts['severe']} | High: {counts['high']} | "
                     f"Moderate: {counts['moderate']} | Low: {counts['low']}",
                     f"Active flood zones: {len(zones)}"],
        )

    def zone_report(self) -> ReportData:
        zones = self.zones.list_zones(active_only=False)
        return ReportData(
            title="Flood Zone Report",
            subtitle="Monitored flood prone areas",
            columns=["Zone", "Barangay / City", "Risk", "Latitude", "Longitude", "Radius (km)", "Active"],
            rows=[[z["name"], z["barangay"] or "-", z["risk_level"], z["latitude"], z["longitude"],
                   z["radius_km"], "Yes" if z["is_active"] else "No"] for z in zones],
            summary=[f"Zones listed: {len(zones)}"],
        )
