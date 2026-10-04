#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vehicle rental and flood-risk desktop application."""
from __future__ import annotations

import csv
import hashlib
import hmac
import logging
import math
import os
import re
import secrets
import shutil
import sqlite3
import subprocess
import sys
import threading
import traceback
import urllib.request
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime
from functools import partial
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Callable, Iterator, Sequence

import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox, ttk

try:
    from tkintermapview import TkinterMapView
except ImportError:  # pragma: no cover
    TkinterMapView = None


APP_NAME = "Flood Ready Vehicle System"
APP_SHORT_NAME = "FloodReadyVehicleSystem"
APP_VERSION = "1.0.0"

BASE_DIR = Path(__file__).resolve().parent

DEFAULT_CENTER = (14.5995, 120.9842)
DEFAULT_ZOOM = 12
OFFLINE_CHECK_URL = "https://www.openstreetmap.org"
OFFLINE_TIMEOUT = 3

CURRENCY = "PHP"
DATE_FORMAT = "%Y-%m-%d"
DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"

VEHICLE_CATEGORIES = [
    "Sedan", "SUV", "Van", "Pickup", "AUV",
    "Motorcycle", "Truck", "Boat",
]
VEHICLE_STATUSES = ["available", "rented", "maintenance"]
BOOKING_STATUSES = ["pending", "confirmed", "ongoing", "completed", "cancelled"]
PAYMENT_METHODS = ["cash", "card", "bank transfer", "mobile wallet"]
PAYMENT_TYPES = ["payment", "deposit", "refund"]
USER_ROLES = ["admin", "manager", "staff"]
RISK_LEVELS = ["low", "moderate", "high", "severe"]
ID_TYPES = ["Drivers License", "Passport", "UMID", "PhilID", "Company ID", "Barangay ID"]
ALERT_SEVERITIES = ["info", "warning", "critical"]
ALERT_STATUSES = ["new", "acknowledged", "resolved"]


def local_app_data_root() -> Path:
    """%LOCALAPPDATA%\\FloodReadyVehicleSystem (portable fallback beside source).

    ``FLOODREADY_DATA_DIR`` is an optional override used for portable or USB
    installations and automated tests.
    """
    override = os.getenv("FLOODREADY_DATA_DIR")
    if override:
        return Path(override)
    local_app_data = os.getenv("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / APP_SHORT_NAME
    return BASE_DIR / "app_data" / APP_SHORT_NAME


DATA_ROOT = local_app_data_root()
DATA_DIR = DATA_ROOT / "data"
IMAGE_DIR = DATA_ROOT / "images"
EXPORT_DIR = DATA_ROOT / "exports"
PDF_EXPORT_DIR = EXPORT_DIR / "pdf"
CSV_EXPORT_DIR = EXPORT_DIR / "csv"
LOG_DIR = DATA_ROOT / "logs"
MAP_CACHE_DIR = DATA_ROOT / "map_cache"
LOG_FILE = LOG_DIR / "application.log"

APP_DATA_FOLDERS = (
    DATA_DIR, IMAGE_DIR, PDF_EXPORT_DIR, CSV_EXPORT_DIR, LOG_DIR, MAP_CACHE_DIR,
)


def database_path() -> Path:
    return DATA_DIR / "rental_system.db"


def ensure_folders() -> list[Path]:
    """Create every writable application folder. Returns the folders created."""
    created: list[Path] = []
    for folder in APP_DATA_FOLDERS:
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError:
            # Fall back to a folder beside the project when the profile is read only.
            fallback = BASE_DIR / "app_data" / folder.name
            fallback.mkdir(parents=True, exist_ok=True)
            folder = fallback
        if folder not in created:
            created.append(folder)
    return created


def setup_logging(level: int = logging.INFO) -> Path:
    """Configure file logging; returns the log file path."""
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:  # pragma: no cover - defensive
        pass
    handler = RotatingFileHandler(
        LOG_FILE, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")
    )
    root = logging.getLogger()
    root.setLevel(level)
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)
    logging.getLogger(__name__).info(
        "%s %s starting | base=%s | data=%s",
        APP_NAME, APP_VERSION, BASE_DIR, DATA_DIR,
    )
    return LOG_FILE


def unique_path(folder: Path, stem: str, suffix: str) -> Path:
    """Build a non colliding export/report path such as bookings_20260212_1530.pdf."""
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    candidate = folder / f"{stem}_{stamp}{suffix}"
    counter = 1
    while candidate.exists():
        candidate = folder / f"{stem}_{stamp}_{counter}{suffix}"
        counter += 1
    return candidate


class AppError(Exception):
    """Base class for every expected, user presentable error."""


class ValidationError(AppError):
    """Raised when input data is missing or badly formatted."""


class AuthenticationError(AppError):
    """Raised when a login attempt fails."""


class NotFoundError(AppError):
    """Raised when a record does not exist."""


class DataConflictError(AppError):
    """Raised for unique/duplicate data problems such as plate numbers."""


class OperationError(AppError):
    """Raised when an action cannot be completed in the current state."""


PBKDF2_ITERATIONS = 260_000
SALT_BYTES = 16
ALGORITHM = "sha256"


def hash_password(password: str) -> tuple[str, str]:
    """Return ``(salt_hex, hash_hex)`` for *password*.

    A new random salt is generated for every call, so the same password never
    produces the same stored value.  Plain text passwords are never stored.
    """
    if not isinstance(password, str) or not password:
        raise AuthenticationError("Password cannot be empty.")
    salt = secrets.token_bytes(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(
        ALGORITHM, password.encode("utf-8"), salt, PBKDF2_ITERATIONS
    )
    return salt.hex(), digest.hex()


def verify_password(password: str, salt_hex: str, hash_hex: str) -> bool:
    """Constant-time verification of *password* against stored values."""
    try:
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except (TypeError, ValueError):
        return False
    if not password or not salt or not expected:
        return False
    digest = hashlib.pbkdf2_hmac(
        ALGORITHM, password.encode("utf-8"), salt, PBKDF2_ITERATIONS
    )
    return hmac.compare_digest(digest, expected)


def password_problems(password: str, confirm: str | None = None) -> list[str]:
    """Small password policy helper used by the user management forms."""
    problems: list[str] = []
    if len(password) < 6:
        problems.append("Password must be at least 6 characters long.")
    if not any(char.isdigit() for char in password):
        problems.append("Password must contain at least one number.")
    if confirm is not None and password != confirm:
        problems.append("Passwords do not match.")
    return problems


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
PHONE_RE = re.compile(r"^[+0-9()\- \t]{7,20}$")
PLATE_RE = re.compile(r"^[A-Za-z0-9\- ]{3,12}$")
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.\-]{3,24}$")


def v_text(value: object, field_name: str, required: bool = True,
           max_length: int = 250) -> str:
    """Trimmed text; raises ValidationError when required and empty."""
    clean = "" if value is None else str(value).strip()
    if not clean:
        if required:
            raise ValidationError(f"{field_name} is required.")
        return ""
    if len(clean) > max_length:
        raise ValidationError(f"{field_name} must be {max_length} characters or fewer.")
    return clean


def v_integer(value: object, field_name: str, minimum: int | None = None,
              maximum: int | None = None) -> int:
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        raise ValidationError(f"{field_name} must be a whole number.") from None
    if minimum is not None and number < minimum:
        raise ValidationError(f"{field_name} must be {minimum} or greater.")
    if maximum is not None and number > maximum:
        raise ValidationError(f"{field_name} must be {maximum} or lower.")
    return number


def v_decimal(value: object, field_name: str, minimum: float = 0.0) -> float:
    try:
        number = float(str(value).strip() or "0")
    except (TypeError, ValueError):
        raise ValidationError(f"{field_name} must be a number.") from None
    if number < minimum:
        raise ValidationError(f"{field_name} cannot be less than {minimum:g}.")
    return round(number, 2)


def v_boolean(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def v_iso_date(value: object, field_name: str) -> date:
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
    raise ValidationError(f"{field_name} must be a valid date (YYYY-MM-DD).")


def v_choice(value: object, options: list[str] | tuple[str, ...],
             field_name: str) -> str:
    clean = str(value or "").strip().lower()
    if clean not in [str(option).lower() for option in options]:
        raise ValidationError(
            f"{field_name} must be one of: {', '.join(options)}.")
    return clean


def v_email(value: object, field_name: str = "Email", required: bool = False) -> str:
    clean = v_text(value, field_name, required=required)
    if clean and not EMAIL_RE.match(clean):
        raise ValidationError(f"{field_name} is not a valid email address.")
    return clean


def v_phone(value: object, field_name: str = "Contact number",
            required: bool = True) -> str:
    clean = v_text(value, field_name, required=required)
    if clean and not PHONE_RE.match(clean):
        raise ValidationError(f"{field_name} must contain 7 to 20 digits.")
    return clean


def v_plate_number(value: object, field_name: str = "Plate number") -> str:
    clean = v_text(value, field_name).upper()
    if not PLATE_RE.match(clean):
        raise ValidationError(
            f"{field_name} must be 3-12 letters, digits or dashes.")
    return clean


def v_username(value: object, field_name: str = "Username") -> str:
    clean = v_text(value, field_name).lower()
    if not USERNAME_RE.match(clean):
        raise ValidationError(
            f"{field_name} must be 3-24 characters "
            "(letters, numbers, dot, dash, underscore).")
    return clean


def v_coordinates(latitude: object, longitude: object) -> tuple[float, float]:
    """Validate GPS coordinates; empty values are allowed (unknown position)."""
    lat_raw = "" if latitude is None else str(latitude).strip()
    lon_raw = "" if longitude is None else str(longitude).strip()
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


def v_date_range(start: object, end: object, start_field: str = "Start date",
                 end_field: str = "End date") -> tuple[date, date]:
    first = v_iso_date(start, start_field)
    last = v_iso_date(end, end_field)
    if last < first:
        raise ValidationError(f"{end_field} cannot be earlier than {start_field}.")
    return first, last


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def today_iso() -> str:
    return date.today().isoformat()


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def has_gps_position(latitude: Any, longitude: Any) -> bool:
    """Return whether a vehicle has a valid, non-sentinel GPS position."""
    if latitude is None or longitude is None:
        return False
    try:
        lat, lon = float(latitude), float(longitude)
    except (TypeError, ValueError):
        return False
    return (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0
            and (lat != 0.0 or lon != 0.0))


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@dataclass
class User:
    id: int
    username: str
    full_name: str
    role: str
    password_salt: str = ""
    password_hash: str = ""
    is_active: bool = True
    created_at: str = ""
    updated_at: str = ""

    @classmethod
    def from_row(cls, row: sqlite3.Row | Any) -> "User":
        return cls(
            id=as_int(row["id"]),
            username=str(row["username"]),
            full_name=str(row["full_name"]),
            role=str(row["role"]),
            password_salt=str(row["password_salt"]),
            password_hash=str(row["password_hash"]),
            is_active=bool(row["is_active"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    def safe_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "username": self.username, "full_name": self.full_name,
            "role": self.role, "is_active": self.is_active,
        }


@dataclass
class ReportData:
    """Everything the PDF/CSV exporters need for one report."""
    title: str
    columns: list[str]
    rows: list[list[Any]]
    summary: list[str] = field(default_factory=list)
    subtitle: str = ""


SCHEMA_SQL = """
-- Flood Ready Vehicle System - SQLite schema
-- Applied automatically on first launch (idempotent: CREATE TABLE IF NOT EXISTS).

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    full_name     TEXT    NOT NULL,
    role          TEXT    NOT NULL DEFAULT 'staff',
    password_salt TEXT    NOT NULL,
    password_hash TEXT    NOT NULL,
    is_active     INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT    NOT NULL,
    updated_at    TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS vehicles (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    plate_number    TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    brand           TEXT    NOT NULL,
    model           TEXT    NOT NULL,
    category        TEXT    NOT NULL DEFAULT 'Sedan',
    year            INTEGER NOT NULL DEFAULT 2020,
    seats           INTEGER NOT NULL DEFAULT 4,
    rate_per_day    REAL    NOT NULL DEFAULT 0,
    status          TEXT    NOT NULL DEFAULT 'available',
    is_archived     INTEGER NOT NULL DEFAULT 0,
    latitude        REAL,
    longitude       REAL,
    image_path      TEXT,
    notes           TEXT,
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS customers (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name      TEXT    NOT NULL,
    phone          TEXT    NOT NULL,
    email          TEXT,
    address        TEXT,
    id_type        TEXT    NOT NULL DEFAULT 'Drivers License',
    id_number      TEXT,
    license_number TEXT,
    is_archived    INTEGER NOT NULL DEFAULT 0,
    notes          TEXT,
    created_at     TEXT    NOT NULL,
    updated_at     TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS flood_zones (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    barangay    TEXT,
    risk_level  TEXT    NOT NULL DEFAULT 'moderate',
    latitude    REAL    NOT NULL,
    longitude   REAL    NOT NULL,
    radius_km   REAL    NOT NULL DEFAULT 1.0,
    is_active   INTEGER NOT NULL DEFAULT 1,
    notes       TEXT,
    created_at  TEXT    NOT NULL,
    updated_at  TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS bookings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    booking_code    TEXT    NOT NULL UNIQUE,
    vehicle_id      INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE RESTRICT,
    customer_id     INTEGER NOT NULL REFERENCES customers(id) ON DELETE RESTRICT,
    start_date      TEXT    NOT NULL,
    end_date        TEXT    NOT NULL,
    pickup_location TEXT,
    destination     TEXT,
    rental_days     INTEGER NOT NULL DEFAULT 1,
    rate_per_day    REAL    NOT NULL DEFAULT 0,
    total_amount    REAL    NOT NULL DEFAULT 0,
    deposit         REAL    NOT NULL DEFAULT 0,
    status          TEXT    NOT NULL DEFAULT 'pending',
    is_archived     INTEGER NOT NULL DEFAULT 0,
    notes           TEXT,
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS transactions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    reference    TEXT    NOT NULL UNIQUE,
    booking_id   INTEGER REFERENCES bookings(id) ON DELETE CASCADE,
    amount       REAL    NOT NULL DEFAULT 0,
    method       TEXT    NOT NULL DEFAULT 'cash',
    entry_type   TEXT    NOT NULL DEFAULT 'payment',
    paid_at      TEXT    NOT NULL,
    recorded_by  INTEGER REFERENCES users(id) ON DELETE SET NULL,
    notes        TEXT,
    created_at   TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS alerts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT    NOT NULL,
    message     TEXT    NOT NULL,
    severity    TEXT    NOT NULL DEFAULT 'info',
    source      TEXT    NOT NULL DEFAULT 'manual',
    vehicle_id  INTEGER REFERENCES vehicles(id) ON DELETE CASCADE,
    zone_id     INTEGER REFERENCES flood_zones(id) ON DELETE SET NULL,
    status      TEXT    NOT NULL DEFAULT 'new',
    created_by  INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at  TEXT    NOT NULL,
    updated_at  TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_vehicles_status   ON vehicles(status, is_archived);
CREATE INDEX IF NOT EXISTS idx_customers_name    ON customers(full_name);
CREATE INDEX IF NOT EXISTS idx_bookings_status   ON bookings(status, is_archived);
CREATE INDEX IF NOT EXISTS idx_bookings_dates    ON bookings(start_date, end_date);
CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(paid_at);
CREATE INDEX IF NOT EXISTS idx_alerts_status     ON alerts(status, created_at);
CREATE INDEX IF NOT EXISTS idx_zones_active      ON flood_zones(is_active);
"""


class DatabaseManager:
    """Thin, reusable wrapper around sqlite3 (one connection per operation)."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else database_path()
        self._initialised = False

    def initialise(self) -> None:
        """Create folders, the database file and tables."""
        ensure_folders()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.touch()
            logging.getLogger(__name__).info(
                "Created new SQLite database at %s", self.path)
        self.apply_schema()
        self._initialised = True

    def apply_schema(self) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA_SQL)

    def seed_if_needed(self) -> bool:
        """Insert the default admin and vehicle catalog exactly once."""
        return seed_database(self)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        try:
            connection = sqlite3.connect(str(self.path), timeout=15)
        except sqlite3.Error as exc:  # pragma: no cover - defensive
            raise AppError("The database file could not be opened.") from exc
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            yield connection
        except sqlite3.Error as exc:
            connection.rollback()
            raise AppError("A database error occurred. See the log file.") from exc
        finally:
            try:
                connection.close()
            except sqlite3.Error:  # pragma: no cover - defensive
                pass

    def fetch_all(self, query: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
        with self.connect() as connection:
            return connection.execute(query, tuple(params)).fetchall()

    def fetch_one(self, query: str, params: Sequence[Any] = ()) -> sqlite3.Row | None:
        with self.connect() as connection:
            return connection.execute(query, tuple(params)).fetchone()

    def scalar(self, query: str, params: Sequence[Any] = ()) -> Any:
        row = self.fetch_one(query, params)
        return None if row is None else row[0]

    def rows_as_dicts(self, query: str,
                      params: Sequence[Any] = ()) -> list[dict[str, Any]]:
        return [dict(row) for row in self.fetch_all(query, params)]

    def execute(self, query: str, params: Sequence[Any] = ()) -> int:
        """Run a single INSERT/UPDATE/DELETE and return the new/changed row id."""
        with self.connect() as connection:
            cursor = connection.execute(query, tuple(params))
            connection.commit()
            return int(cursor.lastrowid or 0)

    def execute_many(self, query: str, rows: Sequence[Sequence[Any]]) -> int:
        rows = list(rows)
        if not rows:
            return 0
        with self.connect() as connection:
            cursor = connection.executemany(query, [tuple(r) for r in rows])
            connection.commit()
            return int(cursor.rowcount or 0)

    def count(self, table: str, where: str = "1=1",
              params: Sequence[Any] = ()) -> int:
        value = self.scalar(f"SELECT COUNT(*) FROM {table} WHERE {where}", params)
        return int(value or 0)

    def setting(self, key: str, default: str = "") -> str:
        row = self.fetch_one("SELECT value FROM settings WHERE key = ?", (key,))
        return str(row["value"]) if row else default

    def set_setting(self, key: str, value: str) -> None:
        now = now_iso()
        self.execute(
            "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value, "
            "updated_at = excluded.updated_at",
            (key, value, now),
        )

    def backup_to(self, destination: str | Path) -> Path:
        """File level backup of the SQLite database."""
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(self.path, destination)
        except OSError as exc:
            raise AppError("The database backup could not be created.") from exc
        logging.getLogger(__name__).info(
            "Database backed up to %s", destination)
        return destination


SEED_VERSION = "1"
DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "admin123"
DEFAULT_ADMIN_NAME = "System Administrator"

VEHICLE_CATALOG = [
    ("NCB 1234", "Toyota", "Vios 1.5 G", "Sedan", 2021, 5, 1800, 14.5995, 120.9842),
    ("ABC 4567", "Toyota", "Innova J", "AUV", 2020, 7, 2200, 14.6096, 120.9910),
    ("XYZ 7788", "Mitsubishi", "Montero Sport", "SUV", 2022, 7, 3000, 14.5500, 121.0300),
    ("PLT 9012", "Ford", "Ranger XLT 4x4", "Pickup", 2021, 5, 2800, 14.6320, 120.9820),
    ("VNL 3344", "Hyundai", "H350 Shuttle", "Van", 2020, 12, 4500, 14.5800, 121.0000),
    ("MTC 5566", "Honda", "Click 125i", "Motorcycle", 2023, 2, 500, 14.6100, 120.9800),
    ("TRK 2211", "Isuzu", "NLR Rescue Truck", "Truck", 2019, 6, 5500, 14.6500, 121.0500),
    ("BTT 8899", "Rainbow", "Rescue Boat + Trailer", "Boat", 2021, 8, 6000, 14.5300, 121.0200),
    ("RDY 4455", "Toyota", "Hiace Commuter", "Van", 2022, 14, 3800, 14.5900, 121.0600),
    ("FLR 6677", "Suzuki", "Ertiga GL", "AUV", 2023, 7, 2000, 14.5700, 120.9600),
]

FLOOD_ZONES = [
    ("Espana Boulevard Corridor", "Sampaloc, Manila", "severe", 14.6058, 120.9900, 1.2,
     "Knee to waist deep water within 30 minutes of heavy rain."),
    ("Sto. Nino Street", "Malabon City", "severe", 14.6580, 120.9400, 2.0,
     "Tidal plus storm water; usually impassable during habagat."),
    ("Kalayaan Avenue", "Diliman, Quezon City", "high", 14.6330, 121.0330, 1.0,
     "Creek overflow near Culiat."),
    ("Zapote River Area", "Las Pinas City", "high", 14.4800, 120.9800, 1.5,
     "River bank overflow during high tide."),
    ("C5 Taguig Flood Plain", "Ususan, Taguig", "moderate", 14.5700, 121.0600, 2.0,
     "Slow drainage; passable by high clearance vehicles."),
    ("Commonwealth Avenue", "Fairview, Quezon City", "low", 14.6600, 121.0500, 1.0,
     "Primary evacuation route - keep clear."),
]

DEFAULT_SETTINGS = {
    "organisation": "Flood Ready Vehicle System",
    "currency": "PHP",
    "map_center_latitude": "14.5995",
    "map_center_longitude": "120.9842",
    "map_zoom": "12",
    "alert_threshold": "high",
}


def seed_database(db: DatabaseManager) -> bool:
    """Insert defaults once. Returns True when seeding happened."""
    if db.setting("seed_version", "") == SEED_VERSION:
        return False

    now = now_iso()
    salt, digest = hash_password(DEFAULT_ADMIN_PASSWORD)
    db.execute(
        "INSERT OR IGNORE INTO users "
        "(username, full_name, role, password_salt, password_hash, is_active, "
        " created_at, updated_at) VALUES (?, ?, ?, ?, ?, 1, ?, ?)",
        (DEFAULT_ADMIN_USERNAME, DEFAULT_ADMIN_NAME, "admin", salt, digest, now, now),
    )
    db.execute_many(
        "INSERT OR IGNORE INTO vehicles "
        "(plate_number, brand, model, category, year, seats, rate_per_day, status, "
        " is_archived, latitude, longitude, image_path, notes, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, 'available', 0, ?, ?, NULL, '', ?, ?)",
        [
            (plate, brand, model, category, year, seats, rate, lat, lon, now, now)
            for plate, brand, model, category, year, seats, rate, lat, lon
            in VEHICLE_CATALOG
        ],
    )
    db.execute_many(
        "INSERT INTO flood_zones "
        "(name, barangay, risk_level, latitude, longitude, radius_km, is_active, "
        " notes, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?)",
        [
            (name, barangay, risk, lat, lon, radius, notes, now, now)
            for name, barangay, risk, lat, lon, radius, notes in FLOOD_ZONES
        ],
    )
    for key, value in DEFAULT_SETTINGS.items():
        db.set_setting(key, value)
    db.set_setting("seed_version", SEED_VERSION)

    logging.getLogger(__name__).info(
        "Seed data inserted (default admin + %d vehicles + %d flood zones)",
        len(VEHICLE_CATALOG), len(FLOOD_ZONES))
    return True


RISK_WEIGHTS = {"low": 10, "moderate": 30, "high": 50, "severe": 70}
ACTIVE_BOOKING_STATUSES = ("pending", "confirmed", "ongoing")
MAX_IMAGE_BYTES = 8 * 1024 * 1024
ALLOWED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres between two GPS positions."""
    radius = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return round(2 * radius * math.asin(math.sqrt(a)), 4)


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
    Risk model: inside a zone the full severity weight applies
    (low 10 / moderate 30 / high 50 / severe 70); the weight decays linearly
    to zero at 5 km from the zone edge, and nearby zones add a small bonus.
    """
    if not has_gps_position(latitude, longitude):
        return {
            "score": 0, "level": "unknown", "nearest_zone": "",
            "distance_km": 0.0, "inside_zone": False, "has_position": False,
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
            latitude, longitude, float(zone["latitude"]), float(zone["longitude"]))
        radius = float(zone.get("radius_km") or 0)
        edge = max(0.0, distance - radius)
        weight = RISK_WEIGHTS.get(str(zone.get("risk_level", "low")).lower(), 10)
        if edge <= 0:
            contribution = float(weight)
            inside = True
            reasons.append(
                f"Inside {zone['name']} ({zone['risk_level']} risk zone).")
        elif edge <= 5:
            contribution = weight * (1 - edge / 5)
            reasons.append(
                f"{edge:.1f} km from {zone['name']} ({zone['risk_level']} risk).")
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


Point = tuple[float, float]

# Coarse water model of the demonstration area.  The Manila Bay coastline runs
# north-east from Pasay to Navotas; Laguna de Bay is the south-east corner.
COAST_BASE_LON = 120.978
COAST_BASE_LAT = 14.500
COAST_SLOPE = 0.15
LAGUNA_LAT = 14.6000
LAGUNA_LON = 121.0900
RIVER_CORRIDOR_KM = 0.25

ROAD_SPEED_RANGE = (18.0, 34.0)   # km/h - Metro Manila traffic
WATER_SPEED_RANGE = (10.0, 14.0)  # km/h - rescue boat on the river

ROUTES: dict[str, dict[str, Any]] = {
    "EDSA": {
        "kind": "road",
        "waypoints": [
            (14.5339, 120.9796), (14.5375, 120.9950), (14.5465, 121.0100),
            (14.5530, 121.0220), (14.5670, 121.0330), (14.5820, 121.0440),
            (14.5860, 121.0570), (14.6060, 121.0510), (14.6196, 121.0414),
            (14.6330, 121.0370), (14.6480, 121.0170), (14.6570, 121.0040),
            (14.6680, 120.9630),
        ],
    },
    "Commonwealth Avenue": {
        "kind": "road",
        "waypoints": [
            (14.6400, 121.0350), (14.6520, 121.0360), (14.6620, 121.0370),
            (14.6720, 121.0330), (14.6800, 121.0270),
        ],
    },
    "Espana - Quezon Avenue": {
        "kind": "road",
        "waypoints": [
            (14.5940, 120.9860), (14.6058, 120.9900), (14.6150, 121.0020),
            (14.6250, 121.0170), (14.6330, 121.0300),
        ],
    },
    "Roxas Boulevard": {
        "kind": "road",
        "waypoints": [
            (14.5330, 120.9820), (14.5450, 120.9780), (14.5600, 120.9750),
            (14.5780, 120.9740), (14.5900, 120.9730),
        ],
    },
    "C5 - Katipunan": {
        "kind": "road",
        "waypoints": [
            (14.5300, 121.0500), (14.5500, 121.0560), (14.5700, 121.0630),
            (14.5900, 121.0650), (14.6100, 121.0660), (14.6250, 121.0630),
            (14.6400, 121.0580),
        ],
    },
    "Aurora Boulevard": {
        "kind": "road",
        "waypoints": [
            (14.6200, 121.0410), (14.6250, 121.0550), (14.6300, 121.0650),
            (14.6350, 121.0750),
        ],
    },
    "Quirino Highway - Novaliches": {
        "kind": "road",
        "waypoints": [
            (14.6500, 121.0250), (14.6600, 121.0150), (14.6700, 121.0050),
            (14.6800, 120.9950), (14.6900, 120.9850),
        ],
    },
    "Pasig River patrol": {
        "kind": "water",
        "waypoints": [
            (14.5750, 121.0900), (14.5850, 121.0600), (14.5930, 121.0300),
            (14.6000, 121.0000), (14.5960, 120.9760),
        ],
    },
}

PASIG_RIVER: list[Point] = ROUTES["Pasig River patrol"]["waypoints"]


def coast_longitude(latitude: float) -> float:
    """Approximate longitude of the Manila Bay coastline at *latitude*."""
    return COAST_BASE_LON - (latitude - COAST_BASE_LAT) * COAST_SLOPE


def route_length_km(waypoints: Sequence[Point]) -> float:
    return sum(haversine_km(a[0], a[1], b[0], b[1])
               for a, b in zip(waypoints, list(waypoints)[1:]))


def position_at(waypoints: Sequence[Point], distance_km: float) -> Point:
    """Point at *distance_km* along the polyline (never leaves the route)."""
    if not waypoints:
        raise AppError("The route has no waypoints.")
    if distance_km <= 0:
        return float(waypoints[0][0]), float(waypoints[0][1])
    remaining = float(distance_km)
    for start, end in zip(waypoints, list(waypoints)[1:]):
        segment = haversine_km(start[0], start[1], end[0], end[1])
        if segment > 0 and remaining <= segment:
            ratio = remaining / segment
            return (start[0] + (end[0] - start[0]) * ratio,
                    start[1] + (end[1] - start[1]) * ratio)
        remaining -= segment
    return float(waypoints[-1][0]), float(waypoints[-1][1])


def _point_to_segment_km(point: Point, start: Point, end: Point) -> float:
    """Distance in km from *point* to the segment start-end (flat earth)."""
    latitude = math.radians(point[0])
    scale = 111.32 * math.cos(latitude)

    def to_xy(target: Point) -> tuple[float, float]:
        return ((target[1] - point[1]) * scale, (target[0] - point[0]) * 111.32)

    ax, ay = to_xy(start)
    bx, by = to_xy(end)
    dx, dy = bx - ax, by - ay
    length_sq = dx * dx + dy * dy
    if length_sq == 0:
        return math.hypot(ax, ay)
    ratio = max(0.0, min(1.0, -(ax * dx + ay * dy) / length_sq))
    return math.hypot(ax + ratio * dx, ay + ratio * dy)


def distance_to_route_km(point: Point, waypoints: Sequence[Point]) -> float:
    if not waypoints:
        return 0.0
    return min(_point_to_segment_km(point, start, end)
               for start, end in zip(waypoints, list(waypoints)[1:] or [waypoints[0]] * 2))


def is_open_water(latitude: float, longitude: float) -> bool:
    """True for Manila Bay and Laguna de Bay (the water cars must never enter)."""
    if 14.40 <= latitude <= 14.78 and longitude < coast_longitude(latitude):
        return True                     # west of the coastline = Manila Bay
    if latitude < LAGUNA_LAT and longitude > LAGUNA_LON:
        return True                     # south-east corner = Laguna de Bay
    return False


def is_on_water(latitude: float, longitude: float) -> bool:
    """True for open water *and* the Pasig River corridor (the boat's route)."""
    return is_open_water(latitude, longitude) or (
        distance_to_route_km((latitude, longitude), PASIG_RIVER) <= RIVER_CORRIDOR_KM)


class TrackingService:
    """Moves the demonstration fleet and stores the positions in SQLite.

    Vehicles drive along real Metro Manila road corridors (EDSA, Commonwealth,
    Espana/Quezon Avenue, Roxas Boulevard, C5/Katipunan, Aurora Boulevard and
    Quirino Highway) while the rescue boat patrols the Pasig River.  The feed
    is deterministic: each vehicle always gets the same route and speed, so
    the demonstration is repeatable.  Runs completely offline.
    """

    def __init__(self, db: DatabaseManager) -> None:
        self.db = db
        self.vehicles = VehicleService(db)
        self._state: dict[int, dict[str, Any]] = {}
        self._lengths: dict[str, float] = {}
        self.elapsed_seconds = 0.0

    @staticmethod
    def route_names() -> list[str]:
        return list(ROUTES)

    def route_length(self, name: str) -> float:
        if name not in self._lengths:
            self._lengths[name] = route_length_km(ROUTES[name]["waypoints"])
        return self._lengths[name]

    @staticmethod
    def _hash(value: str) -> int:
        return int(hashlib.sha256(value.encode("utf-8")).hexdigest(), 16)

    def route_for(self, vehicle: dict[str, Any]) -> str:
        """Deterministic route: boats patrol the river, cars use roads."""
        if str(vehicle.get("category") or "").strip().lower() == "boat":
            return "Pasig River patrol"
        names = [name for name in ROUTES if ROUTES[name]["kind"] == "road"]
        return names[self._hash(str(vehicle.get("plate_number") or "seed")) % len(names)]

    def speed_for(self, vehicle: dict[str, Any]) -> float:
        route = ROUTES[self.route_for(vehicle)]
        low, high = (WATER_SPEED_RANGE if route["kind"] == "water"
                     else ROAD_SPEED_RANGE)
        fraction = (self._hash("speed:" + str(vehicle.get("plate_number") or "x"))
                    % 1000) / 1000.0
        return round(low + fraction * (high - low), 1)

    def _ensure_state(self, vehicle: dict[str, Any]) -> dict[str, Any]:
        vehicle_id = int(vehicle["id"])
        if vehicle_id not in self._state:
            route = self.route_for(vehicle)
            offset = (self._hash("start:" + str(vehicle.get("plate_number") or "x"))
                      % 1000) / 1000.0
            self._state[vehicle_id] = {
                "route": route,
                "distance_km": offset * self.route_length(route),
                "speed_kmh": self.speed_for(vehicle),
                "direction": 1,
            }
        return self._state[vehicle_id]

    def step(self, dt_seconds: float) -> list[dict[str, Any]]:
        """Advance every positioned vehicle by *dt_seconds* of simulated time."""
        self.elapsed_seconds += dt_seconds
        moved: list[dict[str, Any]] = []
        for vehicle in self.vehicles.list_vehicles():
            if not has_gps_position(vehicle.get("latitude"),
                                    vehicle.get("longitude")):
                continue
            state = self._ensure_state(vehicle)
            length = self.route_length(state["route"])
            distance_km = state["speed_kmh"] * dt_seconds / 3600.0
            travelled = state["distance_km"] + state["direction"] * distance_km
            if travelled >= length:
                travelled = max(0.0, 2 * length - travelled)
                state["direction"] = -1
            elif travelled <= 0:
                travelled = min(length, -travelled)
                state["direction"] = 1
            state["distance_km"] = travelled
            latitude, longitude = position_at(
                ROUTES[state["route"]]["waypoints"], travelled)
            self.vehicles.set_gps(int(vehicle["id"]), latitude, longitude)
            moved.append({**vehicle, "latitude": latitude, "longitude": longitude})
        return moved

    def reset_positions(self) -> int:
        """Put every unit back at the start of its route."""
        self._state.clear()
        self.elapsed_seconds = 0.0
        reset_count = 0
        for vehicle in self.vehicles.list_vehicles():
            start = ROUTES[self.route_for(vehicle)]["waypoints"][0]
            self.vehicles.set_gps(int(vehicle["id"]), start[0], start[1])
            reset_count += 1
        return reset_count

    def apply_gps_log(self, path: str | Path) -> tuple[int, int]:
        """Import real positions from a CSV log.

        Expected header: ``plate_number,latitude,longitude[,timestamp]``.
        Unknown plates and invalid coordinates are skipped and reported.
        """
        path = Path(path)
        try:
            handle = path.open("r", newline="", encoding="utf-8-sig")
        except OSError as exc:
            raise ValidationError(
                f"The GPS log could not be read: {path.name}") from exc
        updated = 0
        skipped = 0
        with handle:
            reader = csv.DictReader(handle)
            fields = reader.fieldnames or []
            if not {"plate_number", "latitude", "longitude"} <= set(fields):
                raise ValidationError(
                    "The GPS log must have the columns: "
                    "plate_number, latitude, longitude[, timestamp].")
            for row in reader:
                plate = str(row.get("plate_number") or "").strip().upper()
                try:
                    latitude = float(str(row.get("latitude") or "").strip())
                    longitude = float(str(row.get("longitude") or "").strip())
                    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                        raise ValueError
                except (TypeError, ValueError):
                    skipped += 1
                    continue
                vehicle = self.vehicles.get_by_plate(plate)
                if vehicle is None:
                    skipped += 1
                    continue
                self.vehicles.set_gps(int(vehicle["id"]), latitude, longitude)
                updated += 1
        self._state.clear()          # a real source stops the demonstration feed
        return updated, skipped


class AuthService:
    """Login and user account administration (PBKDF2 passwords)."""

    def __init__(self, db: DatabaseManager) -> None:
        self.db = db

    def login(self, username: object, password: object) -> User:
        clean = str(username or "").strip().lower()
        if not clean or not str(password or ""):
            raise AuthenticationError("Please enter your username and password.")
        row = self.db.fetch_one("SELECT * FROM users WHERE username = ?", (clean,))
        if row is None or not verify_password(
                str(password), row["password_salt"], row["password_hash"]):
            logging.getLogger(__name__).warning(
                "Failed login attempt for username '%s'", clean)
            raise AuthenticationError("Incorrect username or password.")
        if not bool(row["is_active"]):
            raise AuthenticationError(
                "This account is deactivated. Contact an administrator.")
        logging.getLogger(__name__).info("User '%s' logged in", clean)
        return User.from_row(row)

    def list_users(self, include_inactive: bool = True) -> list[dict[str, Any]]:
        query = "SELECT id, username, full_name, role, is_active, created_at FROM users"
        if not include_inactive:
            query += " WHERE is_active = 1"
        query += " ORDER BY username"
        return self.db.rows_as_dicts(query)

    def create_user(self, *, username: object, full_name: object, role: object,
                    password: object, confirm: object | None = None,
                    is_active: bool = True) -> int:
        clean_user = v_username(username)
        name = v_text(full_name, "Full name", max_length=80)
        clean_role = v_choice(role, USER_ROLES, "Role")
        problems = password_problems(
            str(password or ""), None if confirm is None else str(confirm))
        if problems:
            raise ValidationError(" ".join(problems))
        if self.db.fetch_one("SELECT id FROM users WHERE username = ?", (clean_user,)):
            raise DataConflictError(f"Username '{clean_user}' already exists.")
        salt, digest = hash_password(str(password))
        now = now_iso()
        return self.db.execute(
            "INSERT INTO users (username, full_name, role, password_salt, "
            " password_hash, is_active, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (clean_user, name, clean_role, salt, digest,
             int(bool(is_active)), now, now),
        )

    def update_user(self, user_id: int, *, full_name: object | None = None,
                    role: object | None = None,
                    is_active: object | None = None) -> None:
        current = self.db.fetch_one("SELECT * FROM users WHERE id = ?", (user_id,))
        if current is None:
            raise NotFoundError("That user no longer exists.")
        name = (v_text(full_name, "Full name", max_length=80)
                if full_name is not None else current["full_name"])
        clean_role = (v_choice(role, USER_ROLES, "Role")
                      if role is not None else current["role"])
        active = (v_boolean(is_active)
                  if is_active is not None else bool(current["is_active"]))
        if bool(current["is_active"]) and not active:
            admins = self.db.scalar(
                "SELECT COUNT(*) FROM users WHERE role = 'admin' AND is_active = 1")
            if int(admins or 0) <= 1:
                raise OperationError(
                    "The last active administrator cannot be deactivated.")
        self.db.execute(
            "UPDATE users SET full_name = ?, role = ?, is_active = ?, "
            "updated_at = ? WHERE id = ?",
            (name, clean_role, int(active), now_iso(), user_id),
        )

    def reset_password(self, user_id: int, password: object,
                       confirm: object) -> None:
        current = self.db.fetch_one("SELECT * FROM users WHERE id = ?", (user_id,))
        if current is None:
            raise NotFoundError("That user no longer exists.")
        problems = password_problems(
            str(password or ""), str(confirm or ""))
        if problems:
            raise ValidationError(" ".join(problems))
        salt, digest = hash_password(str(password))
        self.db.execute(
            "UPDATE users SET password_salt = ?, password_hash = ?, "
            "updated_at = ? WHERE id = ?",
            (salt, digest, now_iso(), user_id),
        )


class VehicleService:
    """Inventory with plate, rates, status, GPS position and pictures."""

    def __init__(self, db: DatabaseManager) -> None:
        self.db = db

    def list_vehicles(self, search: str = "", status: str = "",
                      category: str = "", include_archived: bool = False
                      ) -> list[dict[str, Any]]:
        where = ["is_archived = ?"]
        params: list[Any] = [int(bool(include_archived))]
        if status:
            where.append("status = ?")
            params.append(status)
        if category:
            where.append("category = ?")
            params.append(category)
        clean = str(search or "").strip().lower()
        if clean:
            where.append("(LOWER(plate_number) LIKE ? OR LOWER(brand) LIKE ? "
                         "OR LOWER(model) LIKE ? OR LOWER(category) LIKE ?)")
            params.extend([f"%{clean}%"] * 4)
        rows = self.db.rows_as_dicts(
            "SELECT * FROM vehicles WHERE " + " AND ".join(where) +
            " ORDER BY plate_number", params)
        zones = ZoneService(self.db).list_zones(active_only=True)
        for row in rows:
            assessment = assess_position(
                row.get("latitude"), row.get("longitude"), zones)
            row["risk_level"] = assessment["level"]
            row["risk_score"] = assessment["score"]
        return rows

    def get(self, vehicle_id: int) -> dict[str, Any]:
        row = self.db.fetch_one(
            "SELECT * FROM vehicles WHERE id = ?", (int(vehicle_id),))
        if row is None:
            raise NotFoundError("That vehicle no longer exists.")
        return dict(row)

    def get_by_plate(self, plate: str) -> dict[str, Any] | None:
        row = self.db.fetch_one(
            "SELECT * FROM vehicles WHERE plate_number = ?",
            (str(plate or "").strip().upper(),))
        return dict(row) if row else None

    def create(self, *, plate_number: object, brand: object, model: object,
               category: object = "Sedan", year: object = 2020, seats: object = 4,
               rate_per_day: object = 0, status: object = "available",
               latitude: object = "", longitude: object = "",
               notes: object = "", image_path: str = "") -> int:
        plate = v_plate_number(plate_number)
        clean_brand = v_text(brand, "Brand", max_length=60)
        clean_model = v_text(model, "Model", max_length=80)
        clean_category = v_choice(category, VEHICLE_CATEGORIES, "Category")
        clean_year = v_integer(year, "Year", minimum=1980, maximum=2100)
        clean_seats = v_integer(seats, "Seats", minimum=1, maximum=80)
        clean_rate = v_decimal(rate_per_day, "Rate per day")
        clean_status = v_choice(status, VEHICLE_STATUSES, "Status")
        lat, lon = v_coordinates(latitude, longitude)
        if self.get_by_plate(plate):
            raise DataConflictError(
                f"A vehicle with plate number {plate} already exists.")
        now = now_iso()
        return self.db.execute(
            "INSERT INTO vehicles (plate_number, brand, model, category, year, "
            " seats, rate_per_day, status, is_archived, latitude, longitude, "
            " image_path, notes, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?)",
            (plate, clean_brand, clean_model, clean_category, clean_year,
             clean_seats, clean_rate, clean_status, lat, lon,
             image_path, str(notes or ""), now, now),
        )

    def update(self, vehicle_id: int, *, plate_number: object, brand: object,
               model: object, category: object, year: object, seats: object,
               rate_per_day: object, status: object, notes: object = "") -> None:
        self.get(vehicle_id)
        plate = v_plate_number(plate_number)
        existing = self.get_by_plate(plate)
        if existing and int(existing["id"]) != int(vehicle_id):
            raise DataConflictError(
                f"A vehicle with plate number {plate} already exists.")
        clean_brand = v_text(brand, "Brand", max_length=60)
        clean_model = v_text(model, "Model", max_length=80)
        clean_category = v_choice(category, VEHICLE_CATEGORIES, "Category")
        clean_year = v_integer(year, "Year", minimum=1980, maximum=2100)
        clean_seats = v_integer(seats, "Seats", minimum=1, maximum=80)
        clean_rate = v_decimal(rate_per_day, "Rate per day")
        clean_status = v_choice(status, VEHICLE_STATUSES, "Status")
        self.db.execute(
            "UPDATE vehicles SET plate_number = ?, brand = ?, model = ?, "
            "category = ?, year = ?, seats = ?, rate_per_day = ?, status = ?, "
            "notes = ?, updated_at = ? WHERE id = ?",
            (plate, clean_brand, clean_model, clean_category, clean_year,
             clean_seats, clean_rate, clean_status, str(notes or ""),
             now_iso(), int(vehicle_id)),
        )

    def set_archived(self, vehicle_id: int, archived: bool) -> None:
        self.get(vehicle_id)
        self.db.execute(
            "UPDATE vehicles SET is_archived = ?, updated_at = ? WHERE id = ?",
            (int(bool(archived)), now_iso(), int(vehicle_id)),
        )

    def delete(self, vehicle_id: int) -> None:
        vehicle = self.get(vehicle_id)
        booking_count = self.db.count(
            "bookings", "vehicle_id = ?", (int(vehicle_id),))
        if booking_count:
            raise DataConflictError(
                f"{vehicle['plate_number']} has {booking_count} booking(s) "
                "and cannot be permanently deleted. Archive it instead.")
        self.db.execute("DELETE FROM vehicles WHERE id = ?", (int(vehicle_id),))
        logging.getLogger(__name__).info(
            "Vehicle '%s' permanently deleted", vehicle["plate_number"])

    def set_status(self, vehicle_id: int, status: object) -> None:
        clean = v_choice(status, VEHICLE_STATUSES, "Status")
        self.get(vehicle_id)
        self.db.execute(
            "UPDATE vehicles SET status = ?, updated_at = ? WHERE id = ?",
            (clean, now_iso(), int(vehicle_id)),
        )

    def set_gps(self, vehicle_id: int, latitude: float, longitude: float) -> None:
        lat, lon = v_coordinates(latitude, longitude)
        self.db.execute(
            "UPDATE vehicles SET latitude = ?, longitude = ?, updated_at = ? "
            "WHERE id = ?",
            (lat, lon, now_iso(), int(vehicle_id)),
        )

    def store_image(self, vehicle_id: int, source: str | Path) -> str:
        """Copy a picture into the app data folder and reference it by name."""
        source = Path(source)
        if source.suffix.lower() not in ALLOWED_IMAGE_SUFFIXES:
            raise ValidationError(
                "Unsupported picture type (use PNG, JPG, GIF, BMP or WEBP).")
        if not source.exists():
            raise ValidationError("The selected picture no longer exists.")
        if source.stat().st_size > MAX_IMAGE_BYTES:
            raise ValidationError("The picture is larger than 8 MB.")
        vehicle = self.get(vehicle_id)
        IMAGE_DIR.mkdir(parents=True, exist_ok=True)
        stem = re.sub(r"[^A-Za-z0-9_-]+", "_", vehicle["plate_number"]).strip("_")
        destination = IMAGE_DIR / f"{stem}{source.suffix.lower()}"
        counter = 1
        while destination.exists():
            destination = IMAGE_DIR / f"{stem}_{counter}{source.suffix.lower()}"
            counter += 1
        shutil.copy2(source, destination)
        self.db.execute(
            "UPDATE vehicles SET image_path = ?, updated_at = ? WHERE id = ?",
            (destination.name, now_iso(), int(vehicle_id)),
        )
        return destination.name


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


class CustomerService:
    """Renter records with contact details and identification."""

    def __init__(self, db: DatabaseManager) -> None:
        self.db = db

    def list_customers(self, search: str = "",
                       include_archived: bool = False) -> list[dict[str, Any]]:
        where = ["c.is_archived = ?"]
        params: list[Any] = [int(bool(include_archived))]
        clean = str(search or "").strip().lower()
        if clean:
            where.append("(LOWER(c.full_name) LIKE ? OR LOWER(c.phone) LIKE ? "
                         "OR LOWER(c.email) LIKE ? OR LOWER(c.id_number) LIKE ?)")
            params.extend([f"%{clean}%"] * 4)
        return self.db.rows_as_dicts(
            "SELECT c.*, (SELECT COUNT(*) FROM bookings b "
            " WHERE b.customer_id = c.id) AS bookings_count "
            "FROM customers c WHERE " + " AND ".join(where) +
            " ORDER BY c.full_name", params)

    def get(self, customer_id: int) -> dict[str, Any]:
        row = self.db.fetch_one(
            "SELECT * FROM customers WHERE id = ?", (int(customer_id),))
        if row is None:
            raise NotFoundError("That customer no longer exists.")
        return dict(row)

    def _validate(self, *, full_name: object, phone: object, email: object = "",
                  address: object = "", id_type: object = "Drivers License",
                  id_number: object = "", license_number: object = "",
                  notes: object = "") -> tuple[Any, ...]:
        return (
            v_text(full_name, "Full name", max_length=90),
            v_phone(phone),
            v_email(email, required=False),
            v_text(address, "Address", required=False, max_length=200),
            v_choice(id_type, ID_TYPES, "ID type"),
            v_text(id_number, "ID number", required=False, max_length=40),
            v_text(license_number, "License number", required=False, max_length=40),
            v_text(notes, "Notes", required=False, max_length=500),
        )

    def create(self, *, full_name: object, phone: object, email: object = "",
               address: object = "", id_type: object = "Drivers License",
               id_number: object = "", license_number: object = "",
               notes: object = "") -> int:
        values = self._validate(full_name=full_name, phone=phone, email=email,
                                address=address, id_type=id_type,
                                id_number=id_number,
                                license_number=license_number, notes=notes)
        now = now_iso()
        return self.db.execute(
            "INSERT INTO customers (full_name, phone, email, address, id_type, "
            " id_number, license_number, is_archived, notes, created_at, "
            " updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)",
            (*values, now, now),
        )

    def update(self, customer_id: int, *, full_name: object, phone: object,
               email: object = "", address: object = "",
               id_type: object = "Drivers License", id_number: object = "",
               license_number: object = "", notes: object = "") -> None:
        self.get(customer_id)
        values = self._validate(full_name=full_name, phone=phone, email=email,
                                address=address, id_type=id_type,
                                id_number=id_number,
                                license_number=license_number, notes=notes)
        self.db.execute(
            "UPDATE customers SET full_name = ?, phone = ?, email = ?, "
            "address = ?, id_type = ?, id_number = ?, license_number = ?, "
            "notes = ?, updated_at = ? WHERE id = ?",
            (*values, now_iso(), int(customer_id)),
        )

    def set_archived(self, customer_id: int, archived: bool) -> None:
        self.get(customer_id)
        self.db.execute(
            "UPDATE customers SET is_archived = ?, updated_at = ? WHERE id = ?",
            (int(bool(archived)), now_iso(), int(customer_id)),
        )


class BookingService:
    """Rental contracts with automatic totals and overlap protection."""

    def __init__(self, db: DatabaseManager) -> None:
        self.db = db

    LIST_QUERY = (
        "SELECT b.*, c.full_name AS customer_name, v.plate_number, "
        " v.brand || ' ' || v.model AS vehicle_label, v.category "
        "FROM bookings b "
        "JOIN customers c ON c.id = b.customer_id "
        "JOIN vehicles v ON v.id = b.vehicle_id ")

    def list_bookings(self, status: str = "", search: str = "",
                      date_from: str = "", date_to: str = "",
                      include_archived: bool = False) -> list[dict[str, Any]]:
        where = ["b.is_archived = ?"]
        params: list[Any] = [int(bool(include_archived))]
        if status:
            where.append("b.status = ?")
            params.append(status)
        clean = str(search or "").strip().lower()
        if clean:
            where.append("(LOWER(b.booking_code) LIKE ? OR LOWER(c.full_name) "
                         "LIKE ? OR LOWER(v.plate_number) LIKE ?)")
            params.extend([f"%{clean}%"] * 3)
        if str(date_from or "").strip():
            where.append("b.end_date >= ?")
            params.append(str(date_from).strip())
        if str(date_to or "").strip():
            where.append("b.start_date <= ?")
            params.append(str(date_to).strip())
        return self.db.rows_as_dicts(
            self.LIST_QUERY + "WHERE " + " AND ".join(where) +
            " ORDER BY b.start_date DESC, b.id DESC", params)

    def get(self, booking_id: int) -> dict[str, Any]:
        row = self.db.fetch_one(
            self.LIST_QUERY + "WHERE b.id = ?", (int(booking_id),))
        if row is None:
            raise NotFoundError("That booking no longer exists.")
        return dict(row)

    def _next_booking_code(self) -> str:
        prefix = f"BK-{date.today().year}-"
        count = int(self.db.scalar("SELECT COUNT(*) FROM bookings") or 0)
        for number in range(count + 1, count + 500):
            code = f"{prefix}{number:04d}"
            if not self.db.fetch_one(
                    "SELECT id FROM bookings WHERE booking_code = ?", (code,)):
                return code
        raise OperationError("A booking code could not be generated.")

    def _overlap_conflict(self, vehicle_id: int, start: date, end: date,
                          exclude_id: int | None = None) -> str | None:
        query = ("SELECT booking_code FROM bookings WHERE vehicle_id = ? "
                 "AND is_archived = 0 AND status IN (?, ?, ?) "
                 "AND start_date <= ? AND end_date >= ?")
        params: list[Any] = [int(vehicle_id), *ACTIVE_BOOKING_STATUSES,
                             end.isoformat(), start.isoformat()]
        if exclude_id is not None:
            query += " AND id != ?"
            params.append(int(exclude_id))
        row = self.db.fetch_one(query, params)
        return str(row["booking_code"]) if row else None

    def create(self, *, vehicle_id: object, customer_id: object,
               start_date: object, end_date: object,
               pickup_location: object = "", destination: object = "",
               deposit: object = 0, notes: object = "") -> int:
        vehicle = self.db.fetch_one(
            "SELECT * FROM vehicles WHERE id = ?", (int(vehicle_id),))
        if vehicle is None:
            raise NotFoundError("Please choose a vehicle for this booking.")
        customer = self.db.fetch_one(
            "SELECT * FROM customers WHERE id = ?", (int(customer_id),))
        if customer is None:
            raise NotFoundError("Please choose a customer for this booking.")
        start, end = v_date_range(start_date, end_date)
        conflict = self._overlap_conflict(int(vehicle_id), start, end)
        if conflict:
            raise DataConflictError(
                f"{vehicle['plate_number']} is already booked for those dates "
                f"(contract {conflict}). Choose other dates or another vehicle.")
        days = (end - start).days + 1
        rate = round(as_float(vehicle["rate_per_day"]), 2)
        total = round(days * rate, 2)
        clean_deposit = v_decimal(deposit, "Deposit")
        now = now_iso()
        return self.db.execute(
            "INSERT INTO bookings (booking_code, vehicle_id, customer_id, "
            " start_date, end_date, pickup_location, destination, rental_days, "
            " rate_per_day, total_amount, deposit, status, is_archived, notes, "
            " created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', 0, ?, ?, ?)",
            (self._next_booking_code(), int(vehicle_id), int(customer_id),
             start.isoformat(), end.isoformat(),
             v_text(pickup_location, "Pickup location", required=False,
                    max_length=120),
             v_text(destination, "Destination", required=False, max_length=120),
             days, rate, total, clean_deposit, str(notes or ""), now, now),
        )

    def update(self, booking_id: int, *, vehicle_id: object, customer_id: object,
               start_date: object, end_date: object, pickup_location: object = "",
               destination: object = "", deposit: object = 0,
               notes: object = "") -> None:
        current = self.get(booking_id)
        if current["status"] not in ("pending", "confirmed"):
            raise OperationError(
                "Only pending or confirmed contracts can be edited. "
                "Cancel this contract and create a new one instead.")
        vehicle = self.db.fetch_one(
            "SELECT * FROM vehicles WHERE id = ?", (int(vehicle_id),))
        if vehicle is None:
            raise NotFoundError("Please choose a vehicle for this booking.")
        if not self.db.fetch_one(
                "SELECT id FROM customers WHERE id = ?", (int(customer_id),)):
            raise NotFoundError("Please choose a customer for this booking.")
        start, end = v_date_range(start_date, end_date)
        conflict = self._overlap_conflict(
            int(vehicle_id), start, end, exclude_id=int(booking_id))
        if conflict:
            raise DataConflictError(
                f"{vehicle['plate_number']} is already booked for those dates "
                f"(contract {conflict}). Choose other dates or another vehicle.")
        days = (end - start).days + 1
        rate = round(as_float(vehicle["rate_per_day"]), 2)
        total = round(days * rate, 2)
        clean_deposit = v_decimal(deposit, "Deposit")
        self.db.execute(
            "UPDATE bookings SET vehicle_id = ?, customer_id = ?, start_date = ?, "
            "end_date = ?, pickup_location = ?, destination = ?, rental_days = ?, "
            "rate_per_day = ?, total_amount = ?, deposit = ?, notes = ?, "
            "updated_at = ? WHERE id = ?",
            (int(vehicle_id), int(customer_id), start.isoformat(),
             end.isoformat(),
             v_text(pickup_location, "Pickup location", required=False,
                    max_length=120),
             v_text(destination, "Destination", required=False, max_length=120),
             days, rate, total, clean_deposit, str(notes or ""),
             now_iso(), int(booking_id)),
        )

    def set_status(self, booking_id: int, status: object) -> None:
        clean = v_choice(status, BOOKING_STATUSES, "Status")
        current = self.get(booking_id)
        allowed = {
            "pending": {"confirmed", "cancelled"},
            "confirmed": {"ongoing", "cancelled"},
            "ongoing": {"completed", "cancelled"},
            "completed": set(),
            "cancelled": set(),
        }
        if clean not in allowed[current["status"]]:
            raise OperationError(
                f"A {current['status']} contract cannot be moved to {clean}.")
        self.db.execute(
            "UPDATE bookings SET status = ?, updated_at = ? WHERE id = ?",
            (clean, now_iso(), int(booking_id)))
        vehicle_status = ("rented" if clean == "ongoing" else "available")
        self.db.execute(
            "UPDATE vehicles SET status = ?, updated_at = ? WHERE id = ?",
            (vehicle_status, now_iso(), int(current["vehicle_id"])))

    def set_archived(self, booking_id: int, archived: bool) -> None:
        self.get(booking_id)
        self.db.execute(
            "UPDATE bookings SET is_archived = ?, updated_at = ? WHERE id = ?",
            (int(bool(archived)), now_iso(), int(booking_id)))

    def due_back_today(self) -> list[dict[str, Any]]:
        return self.db.rows_as_dicts(
            self.LIST_QUERY + "WHERE b.end_date = ? AND b.status IN "
            "('confirmed', 'ongoing') AND b.is_archived = 0 "
            "ORDER BY b.end_date", (today_iso(),))


class TransactionService:
    """Payments, deposits and refunds with reference numbers."""

    def __init__(self, db: DatabaseManager) -> None:
        self.db = db

    LIST_QUERY = (
        "SELECT t.*, b.booking_code, c.full_name AS customer_name, "
        " u.full_name AS recorded_by_name FROM transactions t "
        "LEFT JOIN bookings b ON b.id = t.booking_id "
        "LEFT JOIN customers c ON c.id = b.customer_id "
        "LEFT JOIN users u ON u.id = t.recorded_by ")

    def list_transactions(self, entry_type: str = "", search: str = "",
                          date_from: str = "", date_to: str = ""
                          ) -> list[dict[str, Any]]:
        where = ["1=1"]
        params: list[Any] = []
        if entry_type:
            where.append("t.entry_type = ?")
            params.append(entry_type)
        clean = str(search or "").strip().lower()
        if clean:
            where.append("(LOWER(t.reference) LIKE ? OR LOWER(b.booking_code) "
                         "LIKE ? OR LOWER(c.full_name) LIKE ?)")
            params.extend([f"%{clean}%"] * 3)
        if str(date_from or "").strip():
            where.append("date(t.paid_at) >= ?")
            params.append(str(date_from).strip())
        if str(date_to or "").strip():
            where.append("date(t.paid_at) <= ?")
            params.append(str(date_to).strip())
        return self.db.rows_as_dicts(
            self.LIST_QUERY + "WHERE " + " AND ".join(where) +
            " ORDER BY t.paid_at DESC, t.id DESC", params)

    def _next_reference(self) -> str:
        stamp = datetime.now().strftime("%Y%m%d")
        prefix = f"TXN-{stamp}-"
        count = int(self.db.scalar("SELECT COUNT(*) FROM transactions") or 0)
        for number in range(count + 1, count + 500):
            reference = f"{prefix}{number:04d}"
            if not self.db.fetch_one(
                    "SELECT id FROM transactions WHERE reference = ?",
                    (reference,)):
                return reference
        raise OperationError("A transaction reference could not be generated.")

    def create(self, *, booking_id: object, amount: object, method: object,
               entry_type: object, paid_at: object = "",
               notes: object = "", user_id: int | None = None) -> int:
        booking = self.db.fetch_one(
            "SELECT * FROM bookings WHERE id = ?", (int(booking_id),))
        if booking is None:
            raise NotFoundError("Please choose the booking this money is for.")
        clean_amount = v_decimal(amount, "Amount", minimum=0.01)
        clean_method = v_choice(method, PAYMENT_METHODS, "Method")
        clean_type = v_choice(entry_type, PAYMENT_TYPES, "Entry type")
        raw_paid = str(paid_at or "").strip()
        try:
            moment = datetime.strptime(raw_paid, DATETIME_FORMAT) if raw_paid \
                else datetime.now()
        except ValueError:
            try:
                moment = datetime.strptime(raw_paid, DATE_FORMAT)
            except ValueError:
                raise ValidationError(
                    "Paid at must be a valid date (YYYY-MM-DD HH:MM:SS).") from None
        now = now_iso()
        return self.db.execute(
            "INSERT INTO transactions (reference, booking_id, amount, method, "
            " entry_type, paid_at, recorded_by, notes, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (self._next_reference(), int(booking_id), clean_amount,
             clean_method, clean_type, moment.strftime(DATETIME_FORMAT),
             user_id, str(notes or ""), now),
        )


class ZoneService:
    """Flood prone areas with severity, radius and active monitoring."""

    def __init__(self, db: DatabaseManager) -> None:
        self.db = db

    def list_zones(self, active_only: bool = False,
                   search: str = "") -> list[dict[str, Any]]:
        where = ["1=1"]
        params: list[Any] = []
        if active_only:
            where.append("is_active = 1")
        clean = str(search or "").strip().lower()
        if clean:
            where.append("(LOWER(name) LIKE ? OR LOWER(barangay) LIKE ?)")
            params.extend([f"%{clean}%"] * 2)
        return self.db.rows_as_dicts(
            "SELECT * FROM flood_zones WHERE " + " AND ".join(where) +
            " ORDER BY name", params)

    def get(self, zone_id: int) -> dict[str, Any]:
        row = self.db.fetch_one(
            "SELECT * FROM flood_zones WHERE id = ?", (int(zone_id),))
        if row is None:
            raise NotFoundError("That flood zone no longer exists.")
        return dict(row)

    def _validate(self, *, name: object, barangay: object, risk_level: object,
                  latitude: object, longitude: object, radius_km: object,
                  notes: object) -> tuple[Any, ...]:
        lat, lon = v_coordinates(latitude, longitude)
        if not str(latitude if latitude is not None else "").strip() or \
                not str(longitude if longitude is not None else "").strip():
            raise ValidationError(
                "Both latitude and longitude are required for a flood zone.")
        return (
            v_text(name, "Zone name", max_length=90),
            v_text(barangay, "Barangay", required=False, max_length=90),
            v_choice(risk_level, RISK_LEVELS, "Risk level"),
            lat, lon,
            v_decimal(radius_km, "Radius (km)", minimum=0.1),
            v_text(notes, "Notes", required=False, max_length=400),
        )

    def create(self, *, name: object, barangay: object, risk_level: object,
               latitude: object, longitude: object, radius_km: object = 1.0,
               notes: object = "", is_active: bool = True) -> int:
        values = self._validate(name=name, barangay=barangay,
                                risk_level=risk_level, latitude=latitude,
                                longitude=longitude, radius_km=radius_km,
                                notes=notes)
        now = now_iso()
        return self.db.execute(
            "INSERT INTO flood_zones (name, barangay, risk_level, latitude, "
            " longitude, radius_km, is_active, notes, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (*values, int(bool(is_active)), now, now),
        )

    def update(self, zone_id: int, *, name: object, barangay: object,
               risk_level: object, latitude: object, longitude: object,
               radius_km: object, notes: object = "") -> None:
        self.get(zone_id)
        values = self._validate(name=name, barangay=barangay,
                                risk_level=risk_level, latitude=latitude,
                                longitude=longitude, radius_km=radius_km,
                                notes=notes)
        self.db.execute(
            "UPDATE flood_zones SET name = ?, barangay = ?, risk_level = ?, "
            "latitude = ?, longitude = ?, radius_km = ?, notes = ?, "
            "updated_at = ? WHERE id = ?",
            (*values, now_iso(), int(zone_id)),
        )

    def set_active(self, zone_id: int, active: bool) -> None:
        self.get(zone_id)
        self.db.execute(
            "UPDATE flood_zones SET is_active = ?, updated_at = ? WHERE id = ?",
            (int(bool(active)), now_iso(), int(zone_id)),
        )


class AlertService:
    """Manual notices plus the automatic fleet flood-risk scan."""

    def __init__(self, db: DatabaseManager) -> None:
        self.db = db

    LIST_QUERY = (
        "SELECT a.*, v.plate_number, z.name AS zone_name, "
        " u.full_name AS created_by_name FROM alerts a "
        "LEFT JOIN vehicles v ON v.id = a.vehicle_id "
        "LEFT JOIN flood_zones z ON z.id = a.zone_id "
        "LEFT JOIN users u ON u.id = a.created_by ")

    def list_alerts(self, status: str = "", search: str = "",
                    limit: int = 0) -> list[dict[str, Any]]:
        where = ["1=1"]
        params: list[Any] = []
        if status:
            where.append("a.status = ?")
            params.append(status)
        clean = str(search or "").strip().lower()
        if clean:
            where.append("(LOWER(a.title) LIKE ? OR LOWER(a.message) LIKE ? "
                         "OR LOWER(v.plate_number) LIKE ?)")
            params.extend([f"%{clean}%"] * 3)
        query = (self.LIST_QUERY + "WHERE " + " AND ".join(where) +
                 " ORDER BY a.created_at DESC, a.id DESC")
        if limit:
            query += f" LIMIT {int(limit)}"
        return self.db.rows_as_dicts(query, params)

    def create(self, *, title: object, message: object, severity: object,
               source: str = "manual", vehicle_id: int | None = None,
               zone_id: int | None = None, user_id: int | None = None,
               status: str = "new") -> int:
        clean_title = v_text(title, "Title", max_length=120)
        clean_message = v_text(message, "Message", max_length=800)
        clean_severity = v_choice(severity, ALERT_SEVERITIES, "Severity")
        clean_status = v_choice(status, ALERT_STATUSES, "Status")
        now = now_iso()
        return self.db.execute(
            "INSERT INTO alerts (title, message, severity, source, vehicle_id, "
            " zone_id, status, created_by, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (clean_title, clean_message, clean_severity, source,
             vehicle_id, zone_id, clean_status, user_id, now, now),
        )

    def set_status(self, alert_id: int, status: object) -> None:
        clean = v_choice(status, ALERT_STATUSES, "Status")
        if not self.db.fetch_one(
                "SELECT id FROM alerts WHERE id = ?", (int(alert_id),)):
            raise NotFoundError("That alert no longer exists.")
        self.db.execute(
            "UPDATE alerts SET status = ?, updated_at = ? WHERE id = ?",
            (clean, now_iso(), int(alert_id)))

    def delete(self, alert_id: int) -> None:
        self.db.execute("DELETE FROM alerts WHERE id = ?", (int(alert_id),))

    def generate_flood_alerts(self, user_id: int | None,
                              threshold: str = "high") -> int:
        """Automatic fleet scan: raise alerts at/above the threshold."""
        clean_threshold = v_choice(threshold, RISK_LEVELS, "Threshold")
        order = {level: index for index, level in enumerate(RISK_LEVELS)}
        minimum = order[clean_threshold]
        created = 0
        for vehicle in VehicleService(self.db).list_vehicles():
            level = str(vehicle.get("risk_level") or "unknown")
            if level == "unknown" or order.get(level, 0) < minimum:
                continue
            existing = self.db.fetch_one(
                "SELECT id FROM alerts WHERE vehicle_id = ? "
                "AND source = 'flood_scan' AND status IN ('new', 'acknowledged')",
                (int(vehicle["id"]),))
            if existing:
                continue
            zones = ZoneService(self.db).list_zones(active_only=True)
            assessment = assess_position(
                vehicle.get("latitude"), vehicle.get("longitude"), zones)
            severity = "critical" if level == "severe" else "warning"
            self.create(
                title=f"Flood risk {level}: {vehicle['plate_number']}",
                message=("Automatic fleet scan: " +
                         "; ".join(assessment["reasons"]) +
                         f" Risk score {assessment['score']}/100 ({level}). "
                         f"Nearest zone: {assessment['nearest_zone'] or 'n/a'}."),
                severity=severity, source="flood_scan",
                vehicle_id=int(vehicle["id"]), user_id=user_id)
            created += 1
        return created


class ReportService:
    """Builds ReportData for the six standard reports."""

    def __init__(self, db: DatabaseManager) -> None:
        self.db = db

    REPORT_TYPES = [
        ("vehicles", "Vehicle inventory"),
        ("bookings", "Booking contracts"),
        ("transactions", "Transactions"),
        ("customers", "Customer directory"),
        ("flood_risk", "Fleet flood risk"),
        ("flood_zones", "Flood zones"),
    ]

    def build(self, report_type: str) -> ReportData:
        builder = getattr(self, f"_report_{report_type}", None)
        if builder is None:
            raise NotFoundError(f"Unknown report type: {report_type}")
        return builder()

    def _report_vehicles(self) -> ReportData:
        vehicles = VehicleService(self.db).list_vehicles(include_archived=True)
        rows = [[v["plate_number"], v["brand"], v["model"], v["category"],
                 v["year"], v["seats"], v["rate_per_day"], v["status"],
                 v["risk_level"], "Yes" if v["is_archived"] else "No"]
                for v in vehicles]
        available = sum(1 for v in vehicles if v["status"] == "available")
        rates = [as_float(v["rate_per_day"]) for v in vehicles if v["rate_per_day"]]
        return ReportData(
            title="Vehicle Inventory Report",
            subtitle="Complete fleet list including archived units",
            columns=["Plate", "Brand", "Model", "Category", "Year", "Seats",
                     "Rate/day", "Status", "Flood risk", "Archived"],
            rows=rows,
            summary=[f"Total vehicles: {len(vehicles)}",
                     f"Currently available: {available}",
                     f"Average daily rate: "
                     f"{round(sum(rates) / len(rates), 2) if rates else 0:.2f}"],
        )

    def _report_bookings(self) -> ReportData:
        bookings = BookingService(self.db).list_bookings(include_archived=True)
        rows = [[b["booking_code"], b["customer_name"], b["vehicle_label"],
                 b["start_date"], b["end_date"], b["rental_days"],
                 b["rate_per_day"], b["total_amount"], b["deposit"],
                 b["status"]] for b in bookings]
        active = sum(1 for b in bookings if b["status"] in ACTIVE_BOOKING_STATUSES)
        return ReportData(
            title="Booking Contracts Report",
            subtitle="All rental contracts including archived ones",
            columns=["Code", "Customer", "Vehicle", "Start", "End", "Days",
                     "Rate/day", "Total", "Deposit", "Status"],
            rows=rows,
            summary=[f"Total contracts: {len(bookings)}",
                     f"Active contracts: {active}",
                     f"Contract value: "
                     f"{sum(as_float(b['total_amount']) for b in bookings):.2f}"],
        )

    def _report_transactions(self) -> ReportData:
        transactions = TransactionService(self.db).list_transactions()
        rows = [[t["reference"], t["booking_code"] or "-",
                 t["customer_name"] or "-", t["entry_type"], t["method"],
                 t["amount"], t["paid_at"], t["recorded_by_name"] or "system"]
                for t in transactions]

        def total(entry: str) -> float:
            return sum(as_float(t["amount"]) for t in transactions
                       if t["entry_type"] == entry)

        return ReportData(
            title="Transactions Report",
            subtitle="Payments, deposits and refunds",
            columns=["Reference", "Booking", "Customer", "Type", "Method",
                     "Amount", "Paid at", "Recorded by"],
            rows=rows,
            summary=[f"Payments: {total('payment'):.2f}",
                     f"Deposits held: {total('deposit'):.2f}",
                     f"Refunds: {total('refund'):.2f}",
                     f"Net collections: "
                     f"{total('payment') + total('deposit') - total('refund'):.2f}"],
        )

    def _report_customers(self) -> ReportData:
        customers = CustomerService(self.db).list_customers(include_archived=True)
        rows = [[c["full_name"], c["phone"], c["email"] or "-", c["id_type"],
                 c["id_number"] or "-", c["license_number"] or "-",
                 c["bookings_count"], "Yes" if c["is_archived"] else "No"]
                for c in customers]
        return ReportData(
            title="Customer Directory Report",
            subtitle="Renter records including archived ones",
            columns=["Name", "Phone", "Email", "ID type", "ID number",
                     "License", "Bookings", "Archived"],
            rows=rows,
            summary=[f"Total customers: {len(customers)}",
                     f"Total bookings: "
                     f"{sum(as_int(c['bookings_count']) for c in customers)}"],
        )

    def _report_flood_risk(self) -> ReportData:
        vehicles = VehicleService(self.db).list_vehicles()
        zones = ZoneService(self.db).list_zones(active_only=True)
        rows = []
        for v in vehicles:
            assessment = assess_position(
                v.get("latitude"), v.get("longitude"), zones)
            rows.append([v["plate_number"], v["vehicle"] if "vehicle" in v
                         else f"{v['brand']} {v['model']}", v["category"],
                         v["status"], v["latitude"] or 0, v["longitude"] or 0,
                         assessment["level"], assessment["score"],
                         assessment["nearest_zone"] or "-",
                         assessment["distance_km"]])
        counts = {level: sum(1 for r in rows if r[6] == level)
                  for level in [*RISK_LEVELS, "unknown"]}
        return ReportData(
            title="Fleet Flood Risk Report",
            subtitle="Live risk assessment of the positioned fleet",
            columns=["Plate", "Vehicle", "Category", "Status", "Latitude",
                     "Longitude", "Risk", "Score", "Nearest zone", "Distance km"],
            rows=rows,
            summary=[f"Vehicles assessed: {len(rows)}"] +
                    [f"{level.title()} risk: {count}"
                     for level, count in counts.items()],
        )

    def _report_flood_zones(self) -> ReportData:
        zones = ZoneService(self.db).list_zones()
        rows = [[z["name"], z["barangay"] or "-", z["risk_level"],
                 z["latitude"], z["longitude"], z["radius_km"],
                 "Yes" if z["is_active"] else "No", z["notes"] or "-"]
                for z in zones]
        return ReportData(
            title="Flood Zones Report",
            subtitle="Monitored flood prone areas",
            columns=["Name", "Barangay", "Risk", "Latitude", "Longitude",
                     "Radius km", "Active", "Notes"],
            rows=rows,
            summary=[f"Total zones: {len(zones)}",
                     f"Active zones: {sum(1 for z in zones if z['is_active'])}"],
        )


class SettingsService:
    """Organisation, currency, map defaults, alert threshold and backup."""

    DEFAULTS = DEFAULT_SETTINGS

    def __init__(self, db: DatabaseManager) -> None:
        self.db = db

    def all(self) -> dict[str, str]:
        values = dict(self.DEFAULTS)
        for row in self.db.fetch_all("SELECT key, value FROM settings"):
            values[str(row["key"])] = str(row["value"])
        return values

    def update(self, values: dict[str, Any]) -> None:
        organisation = v_text(values.get("organisation"), "Organisation name",
                              max_length=90)
        currency = v_text(values.get("currency"), "Currency", max_length=8)
        lat = v_decimal(values.get("map_center_latitude"),
                        "Map centre latitude", minimum=-90)
        if lat > 90:
            raise ValidationError("Map centre latitude must be between -90 and 90.")
        lon = v_decimal(values.get("map_center_longitude"),
                        "Map centre longitude", minimum=-180)
        if lon > 180:
            raise ValidationError(
                "Map centre longitude must be between -180 and 180.")
        zoom = v_integer(values.get("map_zoom"), "Map zoom",
                         minimum=3, maximum=19)
        threshold = v_choice(values.get("alert_threshold"), RISK_LEVELS,
                             "Alert threshold")
        for key, value in {
            "organisation": organisation, "currency": currency,
            "map_center_latitude": str(lat), "map_center_longitude": str(lon),
            "map_zoom": str(zoom), "alert_threshold": threshold,
        }.items():
            self.db.set_setting(key, value)

    def backup(self, destination: str | Path) -> Path:
        return self.db.backup_to(destination)


class DashboardService:
    """Summary cards, charts and lists for the dashboard."""

    def __init__(self, db: DatabaseManager) -> None:
        self.db = db

    def summary(self) -> dict[str, Any]:
        month = datetime.now().strftime("%Y-%m")
        return {
            "vehicles_total": self.db.count("vehicles", "is_archived = 0"),
            "available": self.db.count(
                "vehicles", "is_archived = 0 AND status = 'available'"),
            "rented": self.db.count(
                "vehicles", "is_archived = 0 AND status = 'rented'"),
            "maintenance": self.db.count(
                "vehicles", "is_archived = 0 AND status = 'maintenance'"),
            "customers": self.db.count("customers", "is_archived = 0"),
            "active_bookings": self.db.count(
                "bookings",
                "is_archived = 0 AND status IN ('pending', 'confirmed', 'ongoing')"),
            "revenue_month": as_float(self.db.scalar(
                "SELECT COALESCE(SUM(CASE WHEN entry_type = 'refund' "
                "THEN -amount ELSE amount END), 0) FROM transactions "
                "WHERE substr(paid_at, 1, 7) = ?", (month,))),
            "open_alerts": self.db.count(
                "alerts", "status IN ('new', 'acknowledged')"),
        }

    def collections_by_month(self, months: int = 6) -> list[tuple[str, float]]:
        """Net collections (payments + deposits - refunds) per month."""
        today = date.today()
        wanted: list[str] = []
        for offset in range(months - 1, -1, -1):
            year, month = today.year, today.month - offset
            while month <= 0:
                month += 12
                year -= 1
            wanted.append(f"{year:04d}-{month:02d}")
        rows = self.db.fetch_all(
            "SELECT paid_at, amount, entry_type FROM transactions "
            "WHERE substr(paid_at, 1, 7) >= ?", (wanted[0],))
        totals = {month: 0.0 for month in wanted}
        for row in rows:
            key = str(row["paid_at"])[:7]
            if key not in totals:
                continue
            amount = as_float(row["amount"])
            totals[key] += -amount if row["entry_type"] == "refund" else amount
        return [(month, round(totals[month], 2)) for month in wanted]

    def risk_distribution(self) -> dict[str, int]:
        vehicles = VehicleService(self.db).list_vehicles()
        counts = {level: 0 for level in [*RISK_LEVELS, "unknown"]}
        for vehicle in vehicles:
            level = str(vehicle.get("risk_level") or "unknown")
            counts[level] = counts.get(level, 0) + 1
        return counts

    def latest_alerts(self, limit: int = 6) -> list[dict[str, Any]]:
        return AlertService(self.db).list_alerts(limit=limit)

    def due_back_today(self) -> list[dict[str, Any]]:
        return BookingService(self.db).due_back_today()


class Services:
    """One container handed to every page (mirrors app.services usage)."""

    def __init__(self, db: DatabaseManager) -> None:
        self.db = db
        self.auth = AuthService(db)
        self.vehicles = VehicleService(db)
        self.customers = CustomerService(db)
        self.bookings = BookingService(db)
        self.transactions = TransactionService(db)
        self.zones = ZoneService(db)
        self.alerts = AlertService(db)
        self.reports = ReportService(db)
        self.settings = SettingsService(db)
        self.dashboard = DashboardService(db)
        self.tracking = TrackingService(db)


def export_csv_report(report: ReportData, destination: str | Path) -> Path:
    """Write *report* as UTF-8 CSV (with BOM so Excel opens it cleanly)."""
    destination = Path(destination)
    if not report.rows:
        raise AppError(f"{report.title}: there is no data to export.")
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle)
            writer.writerow([column for column in report.columns])
            for row in report.rows:
                writer.writerow(["" if value is None else value for value in row])
            if report.summary:
                writer.writerow([])
                writer.writerow([])
                for line in report.summary:
                    writer.writerow([line])
    except OSError as exc:
        raise AppError(
            "The CSV file could not be created. See the log file.") from exc
    logging.getLogger(__name__).info(
        "CSV report written to %s (%d rows)", destination, len(report.rows))
    return destination


def _pdf_cell(value: Any) -> Any:
    text = "" if value is None else str(value)
    try:
        # ReportLab default fonts are limited to Latin-1.
        text.encode("latin-1")
    except UnicodeEncodeError:
        text = text.encode("latin-1", "replace").decode("latin-1")
    return text


def export_pdf_report(report: ReportData, destination: str | Path) -> Path:
    """Write *report* as a PDF file and return the path that was created."""
    destination = Path(destination)
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
        )
    except ImportError as exc:  # pragma: no cover - packaging problem
        raise AppError(
            "The PDF library (reportlab) is not installed. "
            "Run:  pip install reportlab") from exc

    if not report.rows:
        raise AppError(f"{report.title}: there is no data to export.")

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ReportTitle", parent=styles["Title"], fontSize=16, spaceAfter=2 * mm)
    subtitle_style = ParagraphStyle(
        "ReportSubtitle", parent=styles["Normal"], fontSize=9,
        textColor=colors.grey)
    heading_style = ParagraphStyle(
        "ColumnHead", parent=styles["Normal"], fontSize=8, leading=10,
        textColor=colors.white, fontName="Helvetica-Bold")
    body_style = ParagraphStyle(
        "Cell", parent=styles["Normal"], fontSize=8, leading=10)

    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        document = SimpleDocTemplate(
            str(destination),
            pagesize=landscape(A4) if len(report.columns) > 6 else A4,
            title=report.title, author=APP_NAME,
        )
        story: list[Any] = [
            Paragraph(report.title, title_style),
            Paragraph(
                f"{APP_NAME} v{APP_VERSION} | {report.subtitle} | "
                f"generated {now_iso()}", subtitle_style),
            Spacer(1, 4 * mm),
        ]
        header = [Paragraph(_pdf_cell(column).upper(), heading_style)
                  for column in report.columns]
        body = [[Paragraph(_pdf_cell(value), body_style) for value in row]
                for row in report.rows]
        table = Table([header, *body], repeatRows=1, hAlign="LEFT")
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#14304d")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#c9d3de")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1),
             [colors.white, colors.HexColor("#f4f7fa")]),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(table)
        story.append(Spacer(1, 5 * mm))
        for line in report.summary:
            story.append(Paragraph(f" {_pdf_cell(line)} ", body_style))
        document.build(story)
    except AppError:
        raise
    except Exception as exc:
        logging.getLogger(__name__).exception(
            "PDF export failed for %s", report.title)
        raise AppError(
            "The PDF report could not be created. See the log file.") from exc
    logging.getLogger(__name__).info(
        "PDF report written to %s (%d rows)", destination, len(report.rows))
    return destination


PALETTE: dict[str, str] = {
    "bg": "#f7f8f6",
    "card": "#ffffff",
    "sidebar": "#18372e",
    "sidebar_soft": "#214a3d",
    "sidebar_hover": "#295343",
    "sidebar_active": "#176b50",
    "accent": "#176b50",
    "accent_active": "#12583f",
    "text": "#172521",
    "muted": "#687771",
    "border": "#d9e0da",
    "danger": "#bb4b46",
    "warning": "#a77a10",
    "ok": "#16805d",
    "stripe": "#f7f8f6",
    "head": "#eef2ee",
    "chart": "#7aab98",
}

# Keys double as Treeview row tags: a status or risk value can be turned into
RISK_COLORS: dict[str, str] = {
    "low": "#15803d", "moderate": "#8a6d00", "high": "#d97706",
    "severe": "#b3261e", "unknown": "#64748b",
    "available": "#15803d", "rented": "#2563eb", "maintenance": "#b06a00",
    "pending": "#64748b", "confirmed": "#2563eb", "ongoing": "#15803d",
    "completed": "#64748b", "cancelled": "#b3261e",
    "new": "#b3261e", "acknowledged": "#b06a00", "resolved": "#15803d",
    "info": "#334155", "warning": "#b06a00", "critical": "#b3261e",
    "payment": "#15803d", "deposit": "#2563eb", "refund": "#b3261e",
    "active": "#15803d", "inactive": "#64748b",
    "archived": "#64748b", "muted": "#64748b", "stripe": "#f6f9fc",
}

DOT = "\u25cf"
BASE_FONT = "Segoe UI"

TILE_SERVERS: list[tuple[str, str, int]] = [
    ("OpenStreetMap", "https://a.tile.openstreetmap.org/{z}/{x}/{y}.png", 19),
    ("Carto light", "https://a.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png", 19),
    ("Carto dark", "https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png", 19),
    ("OpenTopoMap", "https://a.tile.opentopomap.org/{z}/{x}/{y}.png", 17),
]


def apply_theme(root: tk.Tk | tk.Toplevel) -> ttk.Style:
    """Install the application theme and return the ttk.Style instance."""
    root.configure(background=PALETTE["bg"])
    for name, size in (("TkDefaultFont", 10), ("TkTextFont", 10),
                       ("TkMenuFont", 10), ("TkHeadingFont", 9)):
        try:
            tkfont.nametofont(name).configure(family=BASE_FONT, size=size)
        except tk.TclError:  # pragma: no cover - non-standard font set
            pass

    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:  # pragma: no cover - fall back to platform theme
        pass

    style.configure(".", background=PALETTE["bg"], foreground=PALETTE["text"],
                    font=(BASE_FONT, 10), bordercolor=PALETTE["border"],
                    lightcolor=PALETTE["card"], darkcolor=PALETTE["border"])
    style.configure("TFrame", background=PALETTE["bg"])
    style.configure("Card.TFrame", background=PALETTE["card"], relief="flat")
    style.configure("Page.TFrame", background=PALETTE["bg"])
    style.configure("Sidebar.TFrame", background=PALETTE["sidebar"])
    style.configure("SidebarSoft.TFrame", background=PALETTE["sidebar_soft"])
    style.configure("TLabelframe", background=PALETTE["card"],
                    bordercolor=PALETTE["border"], relief="solid", borderwidth=1)
    style.configure("TLabelframe.Label", background=PALETTE["card"],
                    foreground=PALETTE["muted"], font=(BASE_FONT, 9, "bold"),
                    padding=(6, 0))
    style.configure("TLabel", background=PALETTE["bg"],
                    foreground=PALETTE["text"])
    style.configure("Card.TLabel", background=PALETTE["card"],
                    foreground=PALETTE["text"])
    style.configure("H1.TLabel", background=PALETTE["card"],
                    foreground=PALETTE["sidebar"], font=(BASE_FONT, 15, "bold"))
    style.configure("H2.TLabel", background=PALETTE["card"],
                    foreground=PALETTE["sidebar"], font=(BASE_FONT, 11, "bold"))
    style.configure("Muted.TLabel", background=PALETTE["bg"],
                    foreground=PALETTE["muted"])
    style.configure("CardMuted.TLabel", background=PALETTE["card"],
                    foreground=PALETTE["muted"])
    style.configure("Field.TLabel", background=PALETTE["card"],
                    foreground=PALETTE["muted"], font=(BASE_FONT, 9, "bold"))
    style.configure("Value.TLabel", background=PALETTE["card"],
                    foreground=PALETTE["text"], font=(BASE_FONT, 10, "bold"))
    style.configure("Danger.TLabel", background=PALETTE["card"],
                    foreground=PALETTE["danger"])
    style.configure("Sidebar.TLabel", background=PALETTE["sidebar"],
                    foreground="#c9d8e8")
    style.configure("SidebarTitle.TLabel", background=PALETTE["sidebar"],
                    foreground="#ffffff", font=(BASE_FONT, 14, "bold"))
    style.configure("SidebarSection.TLabel", background=PALETTE["sidebar"],
                    foreground="#7f9cb8", font=(BASE_FONT, 8, "bold"))
    style.configure("SidebarUser.TLabel", background=PALETTE["sidebar_soft"],
                    foreground="#dbe6f2", font=(BASE_FONT, 10, "bold"))
    style.configure("SidebarUserRole.TLabel", background=PALETTE["sidebar_soft"],
                    foreground="#8fb0cf", font=(BASE_FONT, 9))
    style.configure("Status.TLabel", background=PALETTE["card"],
                    foreground=PALETTE["muted"])
    style.configure("TButton", padding=(12, 6), font=(BASE_FONT, 10))
    style.configure("Primary.TButton", background=PALETTE["accent"],
                    foreground="#ffffff", padding=(16, 7),
                    font=(BASE_FONT, 10, "bold"), borderwidth=0)
    style.map("Primary.TButton",
              background=[("active", PALETTE["accent_active"]),
                          ("disabled", "#a8c4ea")])
    style.configure("Secondary.TButton", background=PALETTE["card"],
                    foreground=PALETTE["text"], padding=(14, 6),
                    bordercolor=PALETTE["border"])
    style.map("Secondary.TButton", background=[("active", PALETTE["head"])])
    style.configure("Danger.TButton", background=PALETTE["danger"],
                    foreground="#ffffff", padding=(14, 6), borderwidth=0)
    style.map("Danger.TButton", background=[("active", "#8f1e18"),
                                            ("disabled", "#d8a09c")])
    style.configure("Sidebar.TButton", background=PALETTE["sidebar"],
                    foreground="#c9d8e8", anchor="w", padding=(12, 7),
                    font=(BASE_FONT, 10), borderwidth=0)
    style.map("Sidebar.TButton",
              background=[("active", PALETTE["sidebar_hover"])])
    style.configure("SidebarActive.TButton", background=PALETTE["sidebar_active"],
                    foreground="#ffffff", anchor="w", padding=(12, 7),
                    font=(BASE_FONT, 10, "bold"), borderwidth=0)
    style.map("SidebarActive.TButton",
              background=[("active", PALETTE["accent_active"])])
    style.configure("SidebarSignOut.TButton", background=PALETTE["sidebar_soft"],
                    foreground="#c9d8e8", anchor="w", padding=(12, 7),
                    borderwidth=0)
    style.map("SidebarSignOut.TButton", background=[("active", "#24476b")])
    style.configure("TEntry", padding=6, fieldbackground=PALETTE["card"],
                    bordercolor=PALETTE["border"])
    style.map("TEntry", bordercolor=[("focus", PALETTE["accent"])])
    style.configure("TCombobox", padding=5, fieldbackground=PALETTE["card"],
                    arrowsize=14)
    style.configure("TCheckbutton", background=PALETTE["card"],
                    foreground=PALETTE["text"])
    style.map("TCheckbutton", background=[("active", PALETTE["card"])])
    style.configure("Treeview", background=PALETTE["card"],
                    fieldbackground=PALETTE["card"], foreground=PALETTE["text"],
                    rowheight=26, bordercolor=PALETTE["border"],
                    font=(BASE_FONT, 10))
    style.configure("Treeview.Heading", background=PALETTE["head"],
                    foreground=PALETTE["sidebar"],
                    font=(BASE_FONT, 9, "bold"), padding=(8, 6), relief="flat")
    style.map("Treeview",
              background=[("selected", PALETTE["accent"])],
              foreground=[("selected", "#ffffff")])
    style.map("Treeview.Heading", background=[("active", PALETTE["head"])])
    style.configure("Vertical.TScrollbar", background=PALETTE["border"],
                    troughcolor=PALETTE["card"], bordercolor=PALETTE["card"],
                    arrowcolor=PALETTE["muted"])
    return style


def make_treeview(parent: tk.Widget, columns: list[tuple[str, str, int, str]],
                  height: int = 16) -> tuple[ttk.Frame, ttk.Treeview]:
    """Card frame + styled Treeview + scrollbar. Columns: (key, heading, w, anchor)."""
    frame = ttk.Frame(parent, style="Card.TFrame")
    tree = ttk.Treeview(frame, columns=[c[0] for c in columns], show="headings",
                        height=height, selectmode="browse")
    for key, heading, width, anchor in columns:
        tree.heading(key, text=heading)
        tree.column(key, width=width, anchor=anchor, stretch=True)
    scrollbar = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=scrollbar.set)
    tree.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")
    for tag, color in RISK_COLORS.items():
        tree.tag_configure(tag, foreground=color)
    tree.tag_configure("stripe", background=PALETTE["stripe"])
    return frame, tree


def page_header(parent: tk.Widget, title: str, subtitle: str = "") -> ttk.Frame:
    """Card header used at the top of every page (returned unpacked)."""
    frame = ttk.Frame(parent, style="Card.TFrame", padding=(16, 14))
    ttk.Label(frame, text=title, style="H1.TLabel").pack(anchor="w")
    if subtitle:
        ttk.Label(frame, text=subtitle, style="CardMuted.TLabel").pack(
            anchor="w", pady=(2, 0))
    return frame


class Page(ttk.Frame):
    """Base class for a sidebar page (built on first display, then refreshed)."""

    TITLE = "Page"
    SUBTITLE = ""
    ICON = DOT

    def __init__(self, parent: tk.Widget, app: "MainWindow") -> None:
        super().__init__(parent, padding=(0,), style="Page.TFrame")
        self.app = app
        self.db = app.db
        self.user = app.user
        self.services = app.services
        self._built = False

    def build(self) -> None:
        """Create the widgets of the page. Called once."""

    def refresh(self) -> None:
        """Reload data into the widgets. Called on every visit."""

    def on_show(self) -> None:
        if not self._built:
            self.build()
            self._built = True
        self.refresh()

    @property
    def is_built(self) -> bool:
        return self._built


class TablePage(Page):
    """Search bar + filter + date range + Treeview table + standard buttons."""

    COLUMNS: list[tuple[str, str, int, str]] = []
    FILTERS: list[tuple[str, str]] = []
    DEFAULT_FILTER = ""
    SHOW_ADD = True
    SHOW_EDIT = True
    SHOW_VIEW = True
    SHOW_ARCHIVE = False
    SHOW_DELETE = False
    SHOW_DATE_RANGE = False
    EXTRA_ACTIONS: list[tuple[str, str]] = []
    GLOBAL_ACTIONS: list[tuple[str, str]] = []
    TREE_HEIGHT = 16

    def __init__(self, parent: tk.Widget, app: "MainWindow") -> None:
        super().__init__(parent, app)
        self.rows: list[dict[str, Any]] = []
        self.tree: ttk.Treeview | None = None
        self._rows_by_iid: dict[str, dict[str, Any]] = {}
        self.search_var = tk.StringVar()
        self.filter_var = tk.StringVar(value=self.DEFAULT_FILTER)
        self.include_archived_var = tk.BooleanVar(value=False)
        self.date_from_var = tk.StringVar(value="")
        self.date_to_var = tk.StringVar(value="")
        self.count_var = tk.StringVar(value="")
        self.action_buttons: dict[str, ttk.Button] = {}

    def build(self) -> None:
        page_header(self, f"{self.ICON}  {self.TITLE}", self.SUBTITLE).pack(
            fill="x")
        self._build_toolbar().pack(fill="x")
        self._build_table().pack(fill="both", expand=True, pady=(12, 0))
        self._build_actions().pack(fill="x")

    def _build_toolbar(self) -> ttk.Frame:
        bar = ttk.Frame(self, style="Card.TFrame", padding=(16, 12))
        entry = ttk.Entry(bar, textvariable=self.search_var, width=26)
        entry.pack(side="left")
        entry.bind("<KeyRelease>", lambda _event: self.refresh())
        entry.bind("<Return>", lambda _event: self.refresh())
        ttk.Button(bar, text="Search", style="Secondary.TButton",
                   command=self.refresh).pack(side="left", padx=(6, 0))
        ttk.Button(bar, text="Reset", style="Secondary.TButton",
                   command=self.reset_filters).pack(side="left", padx=(6, 0))
        if self.FILTERS:
            box = ttk.Combobox(
                bar, textvariable=self.filter_var, width=16, state="readonly",
                values=[label for label, _value in self.FILTERS])
            box.pack(side="left", padx=(14, 0))
            box.bind("<<ComboboxSelected>>", lambda _event: self.refresh())
        if self.SHOW_ARCHIVE:
            ttk.Checkbutton(bar, text="Show archived",
                            variable=self.include_archived_var,
                            command=self.refresh).pack(side="left", padx=(14, 0))
        if self.SHOW_DATE_RANGE:
            ttk.Label(bar, text="From", style="CardMuted.TLabel").pack(
                side="left", padx=(14, 4))
            date_from = ttk.Entry(bar, textvariable=self.date_from_var,
                                  width=11)
            date_from.pack(side="left")
            date_from.bind("<Return>", lambda _event: self.refresh())
            ttk.Label(bar, text="To", style="CardMuted.TLabel").pack(
                side="left", padx=(6, 4))
            date_to = ttk.Entry(bar, textvariable=self.date_to_var, width=11)
            date_to.pack(side="left")
            date_to.bind("<Return>", lambda _event: self.refresh())
        ttk.Label(bar, textvariable=self.count_var,
                  style="CardMuted.TLabel").pack(side="right")
        return bar

    def _build_table(self) -> ttk.Frame:
        frame, tree = make_treeview(self, self.COLUMNS, height=self.TREE_HEIGHT)
        self.tree = tree
        tree.bind("<<TreeviewSelect>>", lambda _event: self._update_buttons())
        tree.bind("<Double-1>", lambda _event: self.on_view())
        return frame

    def _build_actions(self) -> ttk.Frame:
        bar = ttk.Frame(self, style="Card.TFrame", padding=(16, 10))
        actions: list[tuple[str, str, str]] = []
        if self.SHOW_ADD:
            actions.append(("add", "Add", "Primary.TButton"))
        if self.SHOW_EDIT:
            actions.append(("edit", "Edit", "Secondary.TButton"))
        if self.SHOW_VIEW:
            actions.append(("view", "View", "Secondary.TButton"))
        if self.SHOW_ARCHIVE:
            actions.append(("archive", "Archive", "Secondary.TButton"))
        if self.SHOW_DELETE:
            actions.append(("delete", "Delete", "Danger.TButton"))
        for text, method in self.EXTRA_ACTIONS:
            actions.append((method, text, "Secondary.TButton"))
        for key, text, style_name in actions:
            button = ttk.Button(bar, text=text, style=style_name,
                                command=partial(self._run, key))
            button.pack(side="left", padx=(0, 8))
            self.action_buttons[key] = button
        for text, method in self.GLOBAL_ACTIONS:
            ttk.Button(bar, text=text, style="Primary.TButton",
                       command=partial(self._run_method, method)).pack(
                side="right", padx=(6, 0))
        self._update_buttons()
        return bar

    def load_rows(self) -> list[dict[str, Any]]:
        """Return the rows to display (already filtered)."""
        return []

    def row_values(self, row: dict[str, Any]) -> list[Any]:
        return [row.get(column[0], "") for column in self.COLUMNS]

    def row_tags(self, row: dict[str, Any]) -> list[str]:
        status = str(row.get("status") or row.get("risk_level") or "").lower()
        return [status] if status else []

    def refresh(self) -> None:
        selected = self.tree.selection() if self.tree is not None else ()
        selected_iid = selected[0] if selected else None
        self.rows = self.load_rows()
        if self.tree is not None:
            self.tree.delete(*self.tree.get_children())
            self._rows_by_iid.clear()
            for index, row in enumerate(self.rows):
                iid = f"row-{row['id']}" if "id" in row else f"row-{index}"
                self._rows_by_iid[iid] = row
                self.tree.insert(
                    "", "end", iid=iid, values=self.row_values(row),
                    tags=[*self.row_tags(row),
                          "stripe" if index % 2 else ""])
            if selected_iid in self._rows_by_iid:
                self.tree.selection_set(selected_iid)
                self.tree.focus(selected_iid)
        total = len(self.rows)
        archived = sum(1 for row in self.rows if row.get("is_archived"))
        self.count_var.set(
            f"{total} records" + (f" ({archived} archived)" if archived else ""))
        self._update_buttons()

    def reset_filters(self) -> None:
        self.search_var.set("")
        self.filter_var.set(self.DEFAULT_FILTER)
        self.include_archived_var.set(False)
        self.date_from_var.set("")
        self.date_to_var.set("")
        self.refresh()

    def filter_value(self) -> str:
        for label, value in self.FILTERS:
            if label == self.filter_var.get():
                return value
        return ""

    def date_range(self) -> tuple[str, str]:
        return self.date_from_var.get().strip(), self.date_to_var.get().strip()

    def selected_row(self) -> dict[str, Any] | None:
        if self.tree is None:
            return None
        selection = self.tree.selection()
        if not selection:
            return None
        return self._rows_by_iid.get(selection[0])

    def _update_buttons(self) -> None:
        has_selection = self.selected_row() is not None
        for key, button in self.action_buttons.items():
            if key == "add":
                continue
            button.configure(state="normal" if has_selection else "disabled")
        archive = self.action_buttons.get("archive")
        row = self.selected_row()
        if archive is not None and row is not None:
            archive.configure(
                text="Restore" if row.get("is_archived") else "Archive")

    def _run(self, key: str) -> None:
        handler = getattr(self, f"on_{key}", None)
        if handler is None:
            return
        if key != "add" and self.selected_row() is None:
            return
        handler()

    def _run_method(self, method: str) -> None:
        handler = getattr(self, f"on_{method}", None)
        if handler is not None:
            handler()

    def on_add(self) -> None:
        return

    def on_edit(self) -> None:
        return

    def on_view(self) -> None:
        return

    def on_archive(self) -> None:
        return

    def on_delete(self) -> None:
        return


def show_error(message: str, parent: tk.Widget | None = None) -> None:
    messagebox.showerror(APP_NAME, message, parent=parent)


def show_info(message: str, parent: tk.Widget | None = None) -> None:
    messagebox.showinfo(APP_NAME, message, parent=parent)


def confirm(message: str, parent: tk.Widget | None = None) -> bool:
    return messagebox.askyesno(APP_NAME, message, parent=parent)


class FormDialog(tk.Toplevel):
    """Grid form built from field definitions.

    Fields: {"name", "label", "kind": entry|combo|text, "value", "options",
             "required" (default True), "hint"}.
    ``options`` may be plain strings or (label, value) pairs.
    ``on_save(values)`` is called with a dict; raising AppError keeps the
    dialog open and shows the message. Successful saves close the dialog and
    refresh their parent page.
    """

    def __init__(self, parent: tk.Widget, title: str,
                 fields: list[dict[str, Any]],
                 on_save: Callable[[dict[str, Any]], Any],
                 columns: int = 2, ok_text: str = "Save") -> None:
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.fields = fields
        self._on_save = on_save
        self._parent_page = parent if isinstance(parent, Page) else None
        self._widgets: dict[str, Any] = {}
        self._combo_maps: dict[str, list[tuple[str, Any]]] = {}
        self._focus_widget: tk.Widget | None = None

        body = ttk.Frame(self, style="Card.TFrame", padding=(22, 18))
        body.pack(fill="both", expand=True)
        ttk.Label(body, text=title, style="H2.TLabel").grid(
            row=0, column=0, columnspan=columns, sticky="w", pady=(0, 12))

        row = 1
        for index, field in enumerate(fields):
            column = index % columns
            if column == 0 and index:
                row += 1
            self._add_field(body, field, row, column)

        self.error_var = tk.StringVar()
        ttk.Label(body, textvariable=self.error_var, style="Danger.TLabel",
                  wraplength=420, justify="left").grid(
            row=row + 1, column=0, columnspan=columns, sticky="w", pady=(10, 4))

        buttons = ttk.Frame(body, style="Card.TFrame")
        buttons.grid(row=row + 2, column=0, columnspan=columns,
                     sticky="e", pady=(6, 0))
        ttk.Button(buttons, text="Cancel", style="Secondary.TButton",
                   command=self.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(buttons, text=ok_text, style="Primary.TButton",
                   command=self._save).pack(side="right")
        self.bind("<Escape>", lambda _event: self.destroy())
        self.transient(parent.winfo_toplevel())
        self.grab_set()
        self._centre(parent)
        if self._focus_widget is not None:
            self._focus_widget.focus_set()

    def _add_field(self, parent: tk.Widget, field: dict[str, Any],
                   row: int, column: int) -> None:
        name = str(field["name"])
        kind = str(field.get("kind", "entry"))
        box = ttk.Frame(parent, style="Card.TFrame")
        box.grid(row=row, column=column, sticky="ew", padx=(0, 16), pady=(0, 10))
        parent.columnconfigure(column, weight=1)
        label = field.get("label", name)
        ttk.Label(box, text=label, style="Field.TLabel").pack(anchor="w")
        value = field.get("value", "")
        if kind == "combo":
            options = field.get("options") or []
            pairs: list[tuple[str, Any]] = []
            for option in options:
                if isinstance(option, tuple):
                    pairs.append((str(option[0]), option[1]))
                else:
                    pairs.append((str(option), str(option)))
            self._combo_maps[name] = pairs
            labels = [pair[0] for pair in pairs]
            variable = tk.StringVar()
            current = ""
            for display, actual in pairs:
                if str(actual) == str(value):
                    current = display
            if not current and labels:
                current = labels[0]
            variable.set(current)
            widget = ttk.Combobox(box, textvariable=variable, values=labels,
                                  state="readonly")
            self._widgets[name] = ("combo", variable)
        elif kind == "text":
            widget = tk.Text(box, height=4, width=30, font=(BASE_FONT, 10),
                             relief="solid", borderwidth=1)
            widget.insert("1.0", str(value or ""))
            self._widgets[name] = ("text", widget)
        else:
            variable = tk.StringVar(value=str(value or ""))
            widget = ttk.Entry(box, textvariable=variable, width=30)
            if kind == "password":
                widget.configure(show="\u2022")
            self._widgets[name] = ("entry", variable)
        widget.pack(fill="x", pady=(4, 0))
        if kind != "text":
            widget.bind("<Return>", self._save_from_keyboard)
            if self._focus_widget is None:
                self._focus_widget = widget
        hint = field.get("hint", "")
        if hint:
            ttk.Label(box, text=hint, style="CardMuted.TLabel").pack(anchor="w")

    def _save_from_keyboard(self, _event: tk.Event) -> str:
        self._save()
        return "break"

    def _collect(self) -> dict[str, Any]:
        values: dict[str, Any] = {}
        for field in self.fields:
            name = str(field["name"])
            kind, widget = self._widgets[name]
            if kind == "text":
                value = widget.get("1.0", "end").strip()
            elif kind == "combo":
                display = widget.get()
                actual = None
                for label, value_pair in self._combo_maps[name]:
                    if label == display:
                        actual = value_pair
                        break
                if field.get("required", True) and (
                        actual is None or actual == ""):
                    raise ValidationError(
                        f"{field.get('label', name)} is required.")
                values[name] = actual
                continue
            else:
                value = widget.get().strip()
            if field.get("required", True) and not value:
                raise ValidationError(
                    f"{field.get('label', name)} is required.")
            values[name] = value
        return values

    def _save(self) -> None:
        try:
            values = self._collect()
            self._on_save(values)
        except AppError as exc:
            self.error_var.set(str(exc))
            return
        except Exception:  # pragma: no cover - defensive
            logging.getLogger(__name__).exception("Dialog save failed")
            self.error_var.set("The action could not be completed. "
                               "See the log file.")
            return
        self.grab_release()
        self.destroy()
        if self._parent_page is not None:
            self._parent_page.refresh()

    def _centre(self, parent: tk.Widget) -> None:
        self.update_idletasks()
        width = max(460, self.winfo_reqwidth())
        height = max(320, self.winfo_reqheight())
        host = parent.winfo_toplevel()
        x = host.winfo_x() + (host.winfo_width() - width) // 2
        y = host.winfo_y() + (host.winfo_height() - height) // 2
        self.geometry(f"{width}x{height}+{max(0, x)}+{max(0, y)}")


class DetailDialog(tk.Toplevel):
    """Read-only detail view: rows of (label, value) plus optional notes."""

    def __init__(self, parent: tk.Widget, title: str,
                 rows: list[tuple[str, Any]], notes: str = "") -> None:
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        body = ttk.Frame(self, style="Card.TFrame", padding=(24, 20))
        body.pack(fill="both", expand=True)
        ttk.Label(body, text=title, style="H2.TLabel").pack(anchor="w",
                                                            pady=(0, 12))
        grid = ttk.Frame(body, style="Card.TFrame")
        grid.pack(fill="x")
        for index, (label, value) in enumerate(rows):
            ttk.Label(grid, text=str(label), style="Field.TLabel").grid(
                row=index, column=0, sticky="nw", pady=(0, 6))
            ttk.Label(grid, text="" if value is None else str(value),
                      style="Value.TLabel", wraplength=420,
                      justify="left").grid(row=index, column=1, sticky="w",
                                           padx=(18, 0), pady=(0, 6))
        if notes:
            ttk.Label(body, text="Notes", style="Field.TLabel").pack(
                anchor="w", pady=(12, 2))
            ttk.Label(body, text=notes or "-", style="Card.TLabel",
                      wraplength=440, justify="left").pack(anchor="w")
        ttk.Button(body, text="Close", style="Primary.TButton",
                   command=self.destroy).pack(anchor="e", pady=(14, 0))
        self.transient(parent.winfo_toplevel())
        self.grab_set()
        self._centre(parent)

    def _centre(self, parent: tk.Widget) -> None:
        self.update_idletasks()
        width = max(480, self.winfo_reqwidth())
        height = max(300, self.winfo_reqheight())
        host = parent.winfo_toplevel()
        x = host.winfo_x() + (host.winfo_width() - width) // 2
        y = host.winfo_y() + (host.winfo_height() - height) // 2
        self.geometry(f"{width}x{height}+{max(0, x)}+{max(0, y)}")


class LoginWindow(tk.Toplevel):
    def __init__(self, parent: tk.Tk, auth_service: AuthService) -> None:
        super().__init__(parent)
        self.auth = auth_service
        self.user: User | None = None
        self.title(f"{APP_NAME} - Sign in")
        self.resizable(False, False)
        self.configure(background=PALETTE["bg"])
        # ttk styles are shared by the whole interpreter, so the login
        # window only needs its background colour set above.

        card = ttk.Frame(self, style="Card.TFrame", padding=(28, 24))
        card.pack(fill="both", expand=True, padx=20, pady=20)

        brand = ttk.Frame(card, style="Card.TFrame")
        brand.pack(anchor="w", fill="x")
        logo = self._logo(brand)
        if logo is not None:
            logo.pack(side="left", padx=(0, 14))
        titles = ttk.Frame(card, style="Card.TFrame")
        titles.pack(anchor="w", pady=(0 if logo is None else 6, 0))
        ttk.Label(titles, text="Flood Ready", style="H1.TLabel").pack(anchor="w")
        ttk.Label(titles, text="Vehicle System", style="H2.TLabel").pack(anchor="w")
        ttk.Label(card, text="Rental operations with flood-risk monitoring",
                  style="CardMuted.TLabel").pack(anchor="w", pady=(10, 0))
        ttk.Separator(card).pack(fill="x", pady=(16, 18))

        self.username_var = tk.StringVar()
        self.password_var = tk.StringVar()
        self.error_var = tk.StringVar()

        ttk.Label(card, text="Username", style="Field.TLabel").pack(anchor="w")
        username = ttk.Entry(card, textvariable=self.username_var, width=32)
        username.pack(fill="x", pady=(4, 14))
        ttk.Label(card, text="Password", style="Field.TLabel").pack(anchor="w")
        password = ttk.Entry(card, textvariable=self.password_var, width=32,
                             show="\u2022")
        password.pack(fill="x", pady=(4, 8))
        ttk.Label(card, textvariable=self.error_var, style="Danger.TLabel",
                  wraplength=340, justify="left").pack(anchor="w", pady=(0, 12))
        ttk.Button(card, text="Sign in", style="Primary.TButton",
                   command=self._login).pack(fill="x", ipady=2)
        ttk.Label(card, text="Default login: admin / admin123",
                  style="CardMuted.TLabel").pack(anchor="w", pady=(18, 0))
        ttk.Label(card, text="Works offline - only map tiles need internet",
                  style="CardMuted.TLabel").pack(anchor="w", pady=(4, 0))
        ttk.Label(card, text=f"Version {APP_VERSION}",
                  style="CardMuted.TLabel").pack(anchor="w", pady=(14, 0))

        username.focus_set()
        self.bind("<Return>", lambda _event: self._login())
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self._centre()

    @staticmethod
    def _logo(parent: tk.Widget) -> tk.Label | None:
        """Small drawn badge (no image files needed)."""
        try:
            badge = tk.Canvas(parent, width=56, height=56,
                              background=PALETTE["card"], highlightthickness=0)
            badge.create_oval(2, 2, 54, 54, fill=PALETTE["sidebar"],
                              outline=PALETTE["accent"], width=2)
            badge.create_text(28, 26, text="FR", fill="#ffffff",
                              font=(BASE_FONT, 13, "bold"))
            badge.create_text(28, 39, text="VS", fill="#93b4d8",
                              font=(BASE_FONT, 9, "bold"))
            return badge
        except tk.TclError:  # pragma: no cover - cosmetic only
            return None

    def _centre(self) -> None:
        """Centre the window, sized from its content (safe on high DPI)."""
        self.update_idletasks()
        width = max(440, self.winfo_reqwidth())
        height = max(500, self.winfo_reqheight())
        x = max(0, (self.winfo_screenwidth() - width) // 2)
        y = max(0, (self.winfo_screenheight() - height) // 3)
        self.geometry(f"{width}x{height}+{x}+{y}")

    def _login(self) -> None:
        try:
            self.user = self.auth.login(self.username_var.get(),
                                        self.password_var.get())
        except AppError as exc:
            self.error_var.set(str(exc))
            self.password_var.set("")
            return
        except Exception:  # pragma: no cover - defensive
            logging.getLogger(__name__).exception("Unexpected login failure")
            self.error_var.set("Sign in failed. Check the application log.")
            return
        self.destroy()

    def _cancel(self) -> None:
        self.user = None
        self.destroy()


MONTH_NAMES = {"01": "Jan", "02": "Feb", "03": "Mar", "04": "Apr", "05": "May",
               "06": "Jun", "07": "Jul", "08": "Aug", "09": "Sep", "10": "Oct",
               "11": "Nov", "12": "Dec"}


def open_in_file_manager(path: Path | str,
                         parent: tk.Widget | None = None) -> None:
    """Open a file or folder in the system file manager."""
    target = Path(path).expanduser()
    try:
        if not target.exists():
            raise FileNotFoundError(target)
        target_text = str(target)
        if sys.platform.startswith("win"):
            os.startfile(target_text)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", target_text],
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        else:
            subprocess.Popen(["xdg-open", target_text],
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
    except OSError as exc:
        logging.getLogger(__name__).warning(
            "Could not open path in the file manager: %s: %s", target, exc)
        show_error(f"Could not open this location:\n{target}\n\n{exc}",
                   parent)


class DashboardPage(Page):
    """Icon summary cards, charts, bookings due back, latest alerts."""
    TITLE = "Dashboard"
    SUBTITLE = "Operations overview and flood readiness"
    ICON = "\u25c9"

    def build(self) -> None:
        page_header(self, f"{self.ICON}  {self.TITLE}",
                    self.SUBTITLE).pack(fill="x")
        quick = ttk.Frame(self, style="Card.TFrame", padding=(16, 12))
        quick.pack(fill="x", pady=(12, 0))
        for label, key in (("Add vehicle", "vehicles"),
                           ("New booking", "bookings"),
                           ("New alert", "alerts"),
                           ("Flood zones", "zones")):
            ttk.Button(quick, text=label, style="Secondary.TButton",
                       command=partial(self.app.show_page, key)).pack(
                side="left", padx=(0, 8))
        ttk.Button(quick, text="Run flood risk scan",
                   style="Primary.TButton",
                   command=self._scan).pack(side="left", padx=(0, 8))

        cards = ttk.Frame(self, style="Page.TFrame")
        cards.pack(fill="x", pady=(12, 0))
        self.card_values: dict[str, tk.StringVar] = {}
        self.card_subs: dict[str, tk.StringVar] = {}
        for key, title in (("fleet", "Fleet available"),
                           ("bookings", "Active bookings"),
                           ("revenue", "Collections this month"),
                           ("alerts", "Open alerts")):
            card = ttk.Frame(cards, style="Card.TFrame", padding=(16, 14))
            card.pack(side="left", fill="both", expand=True, padx=(0, 10))
            ttk.Label(card, text=title, style="CardMuted.TLabel").pack(anchor="w")
            value_var = tk.StringVar(value="-")
            sub_var = tk.StringVar(value="")
            ttk.Label(card, textvariable=value_var,
                      style="H1.TLabel").pack(anchor="w", pady=(4, 0))
            ttk.Label(card, textvariable=sub_var,
                      style="CardMuted.TLabel").pack(anchor="w")
            self.card_values[key] = value_var
            self.card_subs[key] = sub_var

        charts = ttk.Frame(self, style="Page.TFrame")
        charts.pack(fill="both", expand=True, pady=(12, 0))
        left_card = ttk.Frame(charts, style="Card.TFrame", padding=(16, 12))
        left_card.pack(side="left", fill="both", expand=True, padx=(0, 12))
        ttk.Label(left_card, text="Net collections - last 6 months",
                  style="H2.TLabel").pack(anchor="w")
        self.collections_canvas = tk.Canvas(
            left_card, height=190, background=PALETTE["card"],
            highlightthickness=0)
        self.collections_canvas.pack(fill="both", expand=True, pady=(8, 0))
        self.collections_canvas.bind(
            "<Configure>", lambda _event: self._redraw_charts())
        right_card = ttk.Frame(charts, style="Card.TFrame", padding=(16, 12))
        right_card.pack(side="left", fill="both", expand=True)
        ttk.Label(right_card, text="Fleet flood risk",
                  style="H2.TLabel").pack(anchor="w")
        self.risk_canvas = tk.Canvas(right_card, height=190,
                                     background=PALETTE["card"],
                                     highlightthickness=0)
        self.risk_canvas.pack(fill="both", expand=True, pady=(8, 0))
        self.risk_canvas.bind(
            "<Configure>", lambda _event: self._redraw_charts())

        bottom = ttk.Frame(self, style="Page.TFrame")
        bottom.pack(fill="both", expand=True, pady=(12, 0))
        due_card = ttk.Frame(bottom, style="Card.TFrame", padding=(16, 12))
        due_card.pack(side="left", fill="both", expand=True, padx=(0, 12))
        ttk.Label(due_card, text="Bookings due back today",
                  style="H2.TLabel").pack(anchor="w")
        frame, self.due_tree = make_treeview(due_card, [
            ("code", "Code", 90, "w"), ("customer", "Customer", 150, "w"),
            ("vehicle", "Vehicle", 130, "w"), ("end", "Due", 90, "center")],
            height=7)
        frame.pack(fill="both", expand=True, pady=(8, 0))
        alerts_card = ttk.Frame(bottom, style="Card.TFrame", padding=(16, 12))
        alerts_card.pack(side="left", fill="both", expand=True)
        ttk.Label(alerts_card, text="Latest alerts",
                  style="H2.TLabel").pack(anchor="w")
        frame, self.alerts_tree = make_treeview(alerts_card, [
            ("created_at", "Created", 140, "w"), ("title", "Title", 230, "w"),
            ("severity", "Severity", 80, "w"), ("status", "Status", 95, "w")],
            height=7)
        frame.pack(fill="both", expand=True, pady=(8, 0))

        self.collections_data: list[tuple[str, float]] = []
        self.risk_counts: dict[str, int] = {}

    def refresh(self) -> None:
        summary = self.services.dashboard.summary()
        self.card_values["fleet"].set(
            f"{summary['available']} / {summary['vehicles_total']}")
        self.card_subs["fleet"].set(
            f"{summary['rented']} rented | {summary['maintenance']} maintenance")
        self.card_values["bookings"].set(str(summary["active_bookings"]))
        self.card_subs["bookings"].set(
            f"{summary['customers']} active customers")
        currency = self.db.setting("currency", CURRENCY)
        self.card_values["revenue"].set(
            f"{currency} {summary['revenue_month']:,.2f}")
        self.card_subs["revenue"].set("payments + deposits - refunds")
        self.card_values["alerts"].set(str(summary["open_alerts"]))
        self.card_subs["alerts"].set("new or acknowledged")

        self.collections_data = self.services.dashboard.collections_by_month(6)
        self.risk_counts = self.services.dashboard.risk_distribution()

        self.due_tree.delete(*self.due_tree.get_children())
        for booking in self.services.dashboard.due_back_today():
            self.due_tree.insert("", "end", values=[
                booking["booking_code"], booking["customer_name"],
                booking["vehicle_label"], booking["end_date"]])
        self.alerts_tree.delete(*self.alerts_tree.get_children())
        for index, alert in enumerate(self.services.dashboard.latest_alerts(7)):
            self.alerts_tree.insert("", "end", values=[
                alert["created_at"], alert["title"], alert["severity"],
                alert["status"]],
                tags=[str(alert["severity"]), "stripe" if index % 2 else ""])
        self._redraw_charts()

    def _redraw_charts(self) -> None:
        self._draw_collections(self.collections_canvas, self.collections_data)
        self._draw_risk(self.risk_canvas, self.risk_counts)

    @staticmethod
    def _draw_collections(canvas: tk.Canvas,
                          data: list[tuple[str, float]]) -> None:
        canvas.delete("all")
        width = canvas.winfo_width()
        height = canvas.winfo_height()
        if width < 40 or height < 40 or not data:
            return
        top, bottom = 26.0, height - 30
        chart_height = max(10.0, bottom - top)
        maximum = max((value for _label, value in data), default=0) or 1.0
        count = len(data)
        gap = 16.0
        bar_width = max(14.0, (width - gap * (count + 1)) / count)
        for index, (label, value) in enumerate(data):
            x = gap + index * (bar_width + gap)
            bar_height = max(2.0, value / maximum * chart_height)
            canvas.create_rectangle(
                x, bottom - bar_height, x + bar_width, bottom,
                fill=PALETTE["chart"], outline=PALETTE["accent"])
            canvas.create_text(x + bar_width / 2, bottom - bar_height - 10,
                               text=f"{value:,.0f}",
                               font=(BASE_FONT, 8), fill=PALETTE["muted"])
            month = label[5:7]
            canvas.create_text(
                x + bar_width / 2, bottom + 13,
                text=f"{MONTH_NAMES.get(month, month)} {label[2:4]}",
                font=(BASE_FONT, 8), fill=PALETTE["muted"])

    @staticmethod
    def _draw_risk(canvas: tk.Canvas, counts: dict[str, int]) -> None:
        canvas.delete("all")
        width = canvas.winfo_width()
        height = canvas.winfo_height()
        if width < 40 or height < 40:
            return
        order = ["severe", "high", "moderate", "low", "unknown"]
        maximum = max((counts.get(level, 0) for level in order), default=0) or 1
        row_height = min(30, (height - 16) // len(order))
        for index, level in enumerate(order):
            y = 8 + index * row_height
            color = RISK_COLORS.get(level, "#64748b")
            canvas.create_text(
                4, y + row_height / 2 - 4, anchor="w", text=level.title(),
                font=(BASE_FONT, 9), fill=PALETTE["text"])
            count = counts.get(level, 0)
            bar_width = max(2.0, count / maximum * (width - 170))
            canvas.create_rectangle(
                92, y, 92 + bar_width, y + row_height - 12, fill=color,
                outline="")
            canvas.create_text(
                100 + bar_width, y + row_height / 2 - 4, anchor="w",
                text=str(count), font=(BASE_FONT, 9, "bold"),
                fill=PALETTE["text"])

    def _scan(self) -> None:
        threshold = self.db.setting("alert_threshold", "high")
        try:
            created = self.services.alerts.generate_flood_alerts(
                self.user.id, threshold)
        except AppError as exc:
            show_error(f"The flood risk scan failed: {exc}", self)
            return
        self.refresh()
        show_info(
            f"Flood risk scan finished.\n\n{created} new alert(s) were raised "
            f"using the '{threshold}' threshold.\n\nChange the threshold on "
            "the Settings page if you need earlier warnings.", self)


class VehiclesPage(TablePage):
    """Inventory with plate, rates, status, GPS position and pictures."""
    TITLE = "Vehicles"
    SUBTITLE = "Inventory, GPS positions and flood risk"
    ICON = "\u25a4"
    COLUMNS = [
        ("plate_number", "Plate", 100, "w"),
        ("vehicle", "Vehicle", 210, "w"),
        ("category", "Category", 95, "w"),
        ("year", "Year", 60, "center"),
        ("seats", "Seats", 55, "center"),
        ("rate", "Rate/day", 90, "e"),
        ("status", "Status", 100, "w"),
        ("risk", "Flood risk", 105, "w"),
        ("gps", "GPS position", 150, "w"),
    ]
    FILTERS = [("All statuses", "")] + [(s.title(), s)
                                        for s in VEHICLE_STATUSES]
    SHOW_ARCHIVE = True
    SHOW_DELETE = True
    EXTRA_ACTIONS = [("Set GPS location", "gps"),
                     ("Set picture", "picture")]
    GLOBAL_ACTIONS = [("Import GPS log", "import_gps")]
    TREE_HEIGHT = 16

    def load_rows(self) -> list[dict[str, Any]]:
        return self.services.vehicles.list_vehicles(
            search=self.search_var.get(), status=self.filter_value(),
            include_archived=self.include_archived_var.get())

    def row_values(self, row: dict[str, Any]) -> list[Any]:
        gps = "-"
        if has_gps_position(row.get("latitude"), row.get("longitude")):
            gps = (f"{as_float(row['latitude']):.5f}, "
                   f"{as_float(row['longitude']):.5f}")
        return [
            row.get("plate_number", ""),
            f"{row.get('brand', '')} {row.get('model', '')}",
            row.get("category", ""), row.get("year", ""), row.get("seats", ""),
            f"{as_float(row.get('rate_per_day')):,.2f}",
            row.get("status", ""),
            f"{row.get('risk_level', 'unknown')} ({row.get('risk_score', 0)})",
            gps,
        ]

    def row_tags(self, row: dict[str, Any]) -> list[str]:
        return [str(row.get("status") or ""),
                str(row.get("risk_level") or "unknown")]

    @staticmethod
    def _fields(vehicle: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        vehicle = vehicle or {}
        return [
            {"name": "plate_number", "label": "Plate number", "kind": "entry",
             "value": vehicle.get("plate_number", ""),
             "hint": "e.g. NCB 1234"},
            {"name": "brand", "label": "Brand", "kind": "entry",
             "value": vehicle.get("brand", "")},
            {"name": "model", "label": "Model", "kind": "entry",
             "value": vehicle.get("model", "")},
            {"name": "category", "label": "Category", "kind": "combo",
             "options": VEHICLE_CATEGORIES,
             "value": vehicle.get("category", "Sedan")},
            {"name": "year", "label": "Year", "kind": "entry",
             "value": vehicle.get("year", 2023)},
            {"name": "seats", "label": "Seats", "kind": "entry",
             "value": vehicle.get("seats", 4)},
            {"name": "rate_per_day", "label": "Rate per day", "kind": "entry",
             "value": vehicle.get("rate_per_day", 0)},
            {"name": "status", "label": "Status", "kind": "combo",
             "options": VEHICLE_STATUSES,
             "value": vehicle.get("status", "available")},
            {"name": "notes", "label": "Notes", "kind": "text",
             "required": False, "value": vehicle.get("notes", "")},
        ]

    def on_add(self) -> None:
        FormDialog(self, "Add vehicle", self._fields(),
                   on_save=self._create)

    def _create(self, values: dict[str, Any]) -> None:
        vehicle_id = self.services.vehicles.create(**values)
        show_info(f"{values['plate_number']} was added "
                  f"(record #{vehicle_id}).", self)

    def on_edit(self) -> None:
        row = self.selected_row()
        if row is None:
            return
        current = self.services.vehicles.get(int(row["id"]))
        FormDialog(self, f"Edit {current['plate_number']}",
                   self._fields(current),
                   on_save=lambda values: self.services.vehicles.update(
                       int(row["id"]), **values))

    def on_view(self) -> None:
        row = self.selected_row()
        if row is None:
            return
        vehicle = self.services.vehicles.get(int(row["id"]))
        zones = self.services.zones.list_zones(active_only=True)
        assessment = assess_position(vehicle.get("latitude"),
                                     vehicle.get("longitude"), zones)
        DetailDialog(
            self, f"Vehicle - {vehicle['plate_number']}",
            [("Plate number", vehicle["plate_number"]),
             ("Brand / model", f"{vehicle['brand']} {vehicle['model']}"),
             ("Category", vehicle["category"]),
             ("Year", vehicle["year"]), ("Seats", vehicle["seats"]),
             ("Rate per day", f"{as_float(vehicle['rate_per_day']):,.2f}"),
             ("Status", vehicle["status"]),
             ("GPS position",
              f"{as_float(vehicle['latitude']):.5f}, "
              f"{as_float(vehicle['longitude']):.5f}"
              if has_gps_position(vehicle.get("latitude"),
                                  vehicle.get("longitude"))
              else "No position recorded"),
             ("Flood risk",
              f"{assessment['level'].title()} "
              f"({assessment['score']}/100)"),
             ("Nearest zone", assessment["nearest_zone"] or "-"),
             ("Archived", "Yes" if vehicle["is_archived"] else "No"),
             ("Registered", vehicle["created_at"])],
            notes="; ".join(assessment["reasons"]))

    def on_archive(self) -> None:
        row = self.selected_row()
        if row is None:
            return
        archived = bool(row.get("is_archived"))
        label = "restore" if archived else "archive"
        if not confirm(f"Do you want to {label} "
                       f"{row['plate_number']}?", self):
            return
        try:
            self.services.vehicles.set_archived(int(row["id"]), not archived)
        except AppError as exc:
            show_error(str(exc), self)
            return
        self.app.refresh_all()

    def on_delete(self) -> None:
        row = self.selected_row()
        if row is None:
            return
        plate = str(row["plate_number"])
        if not confirm(
                f"Permanently delete {plate}?\n\n"
                "This cannot be undone. Related alerts will also be deleted. "
                "Vehicles with booking history cannot be deleted; archive "
                "those instead.", self):
            return
        try:
            self.services.vehicles.delete(int(row["id"]))
        except AppError as exc:
            show_error(str(exc), self)
            return
        self.app.refresh_all()

    def on_gps(self) -> None:
        row = self.selected_row()
        if row is None:
            return
        current = self.services.vehicles.get(int(row["id"]))
        FormDialog(
            self, f"Set GPS location - {current['plate_number']}",
            [{"name": "latitude", "label": "Latitude", "kind": "entry",
              "value": (current.get("latitude")
                        if current.get("latitude") is not None else "")},
             {"name": "longitude", "label": "Longitude", "kind": "entry",
              "value": (current.get("longitude")
                        if current.get("longitude") is not None else "")}],
            ok_text="Save position",
            on_save=lambda values: self.services.vehicles.set_gps(
                int(row["id"]), values["latitude"] or 0,
                values["longitude"] or 0))

    def on_picture(self) -> None:
        row = self.selected_row()
        if row is None:
            return
        source = filedialog.askopenfilename(
            parent=self, title="Choose a vehicle picture",
            filetypes=[("Pictures", "*.png *.jpg *.jpeg *.gif *.bmp *.webp"),
                       ("All files", "*.*")])
        if not source:
            return
        try:
            stored = self.services.vehicles.store_image(int(row["id"]), source)
        except AppError as exc:
            show_error(str(exc), self)
            return
        show_info(f"The picture was saved as {stored}.", self)

    def on_import_gps(self) -> None:
        path = filedialog.askopenfilename(
            parent=self, title="Import GPS log (CSV)",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if not path:
            return
        try:
            updated, skipped = self.services.tracking.apply_gps_log(path)
        except AppError as exc:
            show_error(str(exc), self)
            return
        show_info(f"GPS log imported.\n\nUpdated: {updated} vehicle(s)\n"
                  f"Skipped: {skipped} row(s)", self)
        self.app.refresh_all()


class CustomersPage(TablePage):
    """Renter records and identification (mirrors ui/customers_page.py)."""
    TITLE = "Customers"
    SUBTITLE = "Renter records and identification"
    ICON = "\u2630"
    COLUMNS = [
        ("full_name", "Customer name", 210, "w"),
        ("phone", "Contact number", 130, "w"),
        ("email", "Email", 180, "w"),
        ("id_type", "ID type", 130, "w"),
        ("id_number", "ID number", 120, "w"),
        ("license_number", "License number", 120, "w"),
        ("bookings_count", "Bookings", 75, "center"),
    ]
    SHOW_ARCHIVE = True
    TREE_HEIGHT = 17

    def load_rows(self) -> list[dict[str, Any]]:
        return self.services.customers.list_customers(
            search=self.search_var.get(),
            include_archived=self.include_archived_var.get())

    def row_tags(self, row: dict[str, Any]) -> list[str]:
        return ["archived"] if row.get("is_archived") else []

    @staticmethod
    def _fields(customer: dict[str, Any] | None = None
                ) -> list[dict[str, Any]]:
        customer = customer or {}
        return [
            {"name": "full_name", "label": "Full name", "kind": "entry",
             "value": customer.get("full_name", "")},
            {"name": "phone", "label": "Contact number", "kind": "entry",
             "value": customer.get("phone", ""),
             "hint": "e.g. 0917 123 4567"},
            {"name": "email", "label": "Email", "kind": "entry",
             "required": False, "value": customer.get("email", "")},
            {"name": "address", "label": "Address", "kind": "entry",
             "required": False, "value": customer.get("address", "")},
            {"name": "id_type", "label": "ID type", "kind": "combo",
             "options": ID_TYPES,
             "value": customer.get("id_type", "Drivers License")},
            {"name": "id_number", "label": "ID number", "kind": "entry",
             "required": False, "value": customer.get("id_number", "")},
            {"name": "license_number", "label": "License number",
             "kind": "entry", "required": False,
             "value": customer.get("license_number", "")},
            {"name": "notes", "label": "Notes", "kind": "text",
             "required": False, "value": customer.get("notes", "")},
        ]

    def on_add(self) -> None:
        FormDialog(self, "Add customer", self._fields(), on_save=self._create)

    def _create(self, values: dict[str, Any]) -> None:
        customer_id = self.services.customers.create(**values)
        show_info(f"{values['full_name']} was added "
                  f"(record #{customer_id}).", self)

    def on_edit(self) -> None:
        row = self.selected_row()
        if row is None:
            return
        current = self.services.customers.get(int(row["id"]))
        FormDialog(self, f"Edit {current['full_name']}",
                   self._fields(current),
                   on_save=lambda values: self.services.customers.update(
                       int(row["id"]), **values))

    def on_view(self) -> None:
        row = self.selected_row()
        if row is None:
            return
        customer = self.services.customers.get(int(row["id"]))
        DetailDialog(
            self, f"Customer - {customer['full_name']}",
            [("Full name", customer["full_name"]),
             ("Contact number", customer["phone"]),
             ("Email", customer["email"] or "-"),
             ("Address", customer["address"] or "-"),
             ("ID type", customer["id_type"]),
             ("ID number", customer["id_number"] or "-"),
             ("License number", customer["license_number"] or "-"),
             ("Total bookings", row.get("bookings_count", 0)),
             ("Archived", "Yes" if customer["is_archived"] else "No"),
             ("Registered", customer["created_at"])],
            notes=customer["notes"])

    def on_archive(self) -> None:
        row = self.selected_row()
        if row is None:
            return
        archived = bool(row["is_archived"])
        label = "restore" if archived else "archive"
        if not confirm(f"Do you want to {label} {row['full_name']}?", self):
            return
        try:
            self.services.customers.set_archived(int(row["id"]), not archived)
        except AppError as exc:
            show_error(str(exc), self)
            return
        self.app.refresh_all()


class BookingsPage(TablePage):
    """Rental contracts with automatic totals and overlap protection."""
    TITLE = "Bookings"
    SUBTITLE = ("Rental contracts with automatic day/rate totals and "
                "overlap protection")
    ICON = "\u25a6"
    COLUMNS = [
        ("booking_code", "Code", 100, "w"),
        ("customer_name", "Customer", 170, "w"),
        ("plate_number", "Vehicle", 90, "w"),
        ("start_date", "Start", 90, "center"),
        ("end_date", "End", 90, "center"),
        ("rental_days", "Days", 50, "center"),
        ("total", "Total", 100, "e"),
        ("status", "Status", 100, "w"),
    ]
    FILTERS = [("All statuses", "")] + [(s.title(), s)
                                        for s in BOOKING_STATUSES]
    SHOW_DATE_RANGE = True
    SHOW_ARCHIVE = True
    EXTRA_ACTIONS = [("Confirm", "confirm"), ("Start rental", "start"),
                     ("Complete", "complete"), ("Cancel", "cancel")]
    TREE_HEIGHT = 16

    def load_rows(self) -> list[dict[str, Any]]:
        start, end = self.date_range()
        return self.services.bookings.list_bookings(
            status=self.filter_value(), search=self.search_var.get(),
            date_from=start, date_to=end,
            include_archived=self.include_archived_var.get())

    def row_values(self, row: dict[str, Any]) -> list[Any]:
        return [
            row.get("booking_code", ""), row.get("customer_name", ""),
            row.get("plate_number", ""), row.get("start_date", ""),
            row.get("end_date", ""), row.get("rental_days", ""),
            f"{as_float(row.get('total_amount')):,.2f}",
            row.get("status", ""),
        ]

    def row_tags(self, row: dict[str, Any]) -> list[str]:
        return [str(row.get("status") or "")]

    def _fields(self, current: dict[str, Any] | None = None
                ) -> list[dict[str, Any]]:
        current = current or {}
        vehicles = [v for v in self.services.vehicles.list_vehicles()
                    if not v["is_archived"]]
        customers = [c for c in self.services.customers.list_customers()
                     if not c["is_archived"]]
        return [
            {"name": "vehicle_id", "label": "Vehicle", "kind": "combo",
             "options": [(f"{v['plate_number']} - {v['brand']} "
                          f"{v['model']} ({v['status']})", int(v["id"]))
                         for v in vehicles],
             "value": current.get("vehicle_id")},
            {"name": "customer_id", "label": "Customer", "kind": "combo",
             "options": [(c["full_name"], int(c["id"])) for c in customers],
             "value": current.get("customer_id")},
            {"name": "start_date", "label": "Start date", "kind": "entry",
             "value": current.get("start_date", today_iso()),
             "hint": "YYYY-MM-DD"},
            {"name": "end_date", "label": "End date", "kind": "entry",
             "value": current.get("end_date", today_iso()),
             "hint": "YYYY-MM-DD"},
            {"name": "pickup_location", "label": "Pickup location",
             "kind": "entry", "required": False,
             "value": current.get("pickup_location", "")},
            {"name": "destination", "label": "Destination", "kind": "entry",
             "required": False, "value": current.get("destination", "")},
            {"name": "deposit", "label": "Deposit", "kind": "entry",
             "value": current.get("deposit", 0)},
            {"name": "notes", "label": "Notes", "kind": "text",
             "required": False, "value": current.get("notes", "")},
        ]

    def on_add(self) -> None:
        FormDialog(self, "New booking", self._fields(),
                   ok_text="Create contract", on_save=self._create)

    def _create(self, values: dict[str, Any]) -> None:
        booking_id = self.services.bookings.create(**values)
        booking = self.services.bookings.get(booking_id)
        show_info(
            f"Contract {booking['booking_code']} was created for "
            f"{booking['customer_name']}.\n\n"
            f"{booking['rental_days']} day(s) at "
            f"{as_float(booking['rate_per_day']):,.2f} per day = "
            f"{as_float(booking['total_amount']):,.2f}.", self)

    def on_edit(self) -> None:
        row = self.selected_row()
        if row is None:
            return
        current = self.services.bookings.get(int(row["id"]))
        if current["status"] not in ("pending", "confirmed"):
            show_error("Only pending or confirmed contracts can be edited. "
                       "Cancel this contract and create a new one instead.",
                       self)
            return
        FormDialog(self, f"Edit {current['booking_code']}",
                   self._fields(current),
                   on_save=lambda values: self.services.bookings.update(
                       int(row["id"]), **values))

    def on_view(self) -> None:
        row = self.selected_row()
        if row is None:
            return
        booking = self.services.bookings.get(int(row["id"]))
        DetailDialog(
            self, f"Booking - {booking['booking_code']}",
            [("Code", booking["booking_code"]),
             ("Customer", booking["customer_name"]),
             ("Vehicle", f"{booking['vehicle_label']} "
                         f"({booking['plate_number']})"),
             ("Start date", booking["start_date"]),
             ("End date", booking["end_date"]),
             ("Rental days", booking["rental_days"]),
             ("Rate per day", f"{as_float(booking['rate_per_day']):,.2f}"),
             ("Total amount", f"{as_float(booking['total_amount']):,.2f}"),
             ("Deposit", f"{as_float(booking['deposit']):,.2f}"),
             ("Status", booking["status"]),
             ("Pickup location", booking["pickup_location"] or "-"),
             ("Destination", booking["destination"] or "-"),
             ("Created", booking["created_at"])],
            notes=booking["notes"])

    def on_archive(self) -> None:
        row = self.selected_row()
        if row is None:
            return
        archived = bool(row.get("is_archived"))
        label = "restore" if archived else "archive"
        if not confirm(f"Do you want to {label} "
                       f"{row['booking_code']}?", self):
            return
        try:
            self.services.bookings.set_archived(int(row["id"]), not archived)
        except AppError as exc:
            show_error(str(exc), self)
            return
        self.app.refresh_all()

    def on_confirm(self) -> None:
        self._set_status("confirmed")

    def on_start(self) -> None:
        self._set_status("ongoing")

    def on_complete(self) -> None:
        self._set_status("completed")

    def on_cancel(self) -> None:
        self._set_status("cancelled")

    def _set_status(self, status: str) -> None:
        row = self.selected_row()
        if row is None:
            return
        try:
            self.services.bookings.set_status(int(row["id"]), status)
        except AppError as exc:
            show_error(str(exc), self)
            return
        self.app.refresh_all()


class TransactionsPage(TablePage):
    """Payments, deposits and refunds with reference numbers and totals."""
    TITLE = "Transactions"
    SUBTITLE = "Payments, deposits and refunds with running totals"
    ICON = "\u20b1"
    COLUMNS = [
        ("reference", "Reference", 130, "w"),
        ("booking_code", "Booking", 100, "w"),
        ("customer_name", "Customer", 160, "w"),
        ("entry_type", "Type", 80, "w"),
        ("method", "Method", 100, "w"),
        ("amount", "Amount", 100, "e"),
        ("paid_at", "Paid at", 150, "w"),
        ("recorded_by_name", "Recorded by", 130, "w"),
    ]
    FILTERS = [("All types", "")] + [(t.title(), t) for t in PAYMENT_TYPES]
    SHOW_DATE_RANGE = True
    SHOW_ADD = False
    SHOW_EDIT = False
    GLOBAL_ACTIONS = [("Record payment", "record")]
    TREE_HEIGHT = 16

    def load_rows(self) -> list[dict[str, Any]]:
        start, end = self.date_range()
        return self.services.transactions.list_transactions(
            entry_type=self.filter_value(), search=self.search_var.get(),
            date_from=start, date_to=end)

    def row_values(self, row: dict[str, Any]) -> list[Any]:
        return [
            row.get("reference", ""), row.get("booking_code") or "-",
            row.get("customer_name") or "-", row.get("entry_type", ""),
            row.get("method", ""), f"{as_float(row.get('amount')):,.2f}",
            row.get("paid_at", ""), row.get("recorded_by_name") or "system",
        ]

    def row_tags(self, row: dict[str, Any]) -> list[str]:
        return [str(row.get("entry_type") or "")]

    def refresh(self) -> None:
        super().refresh()
        paid = sum(as_float(r["amount"]) for r in self.rows
                   if r.get("entry_type") == "payment")
        held = sum(as_float(r["amount"]) for r in self.rows
                   if r.get("entry_type") == "deposit")
        refunded = sum(as_float(r["amount"]) for r in self.rows
                       if r.get("entry_type") == "refund")
        currency = self.db.setting("currency", CURRENCY)
        self.count_var.set(
            f"{len(self.rows)} records | payments {paid:,.2f} | deposits "
            f"{held:,.2f} | refunds {refunded:,.2f} {currency}")

    def _fields(self) -> list[dict[str, Any]]:
        bookings = self.services.bookings.list_bookings()
        return [
            {"name": "booking_id", "label": "Booking", "kind": "combo",
             "options": [(f"{b['booking_code']} - {b['customer_name']} - "
                          f"{b['plate_number']}", int(b["id"]))
                         for b in bookings]},
            {"name": "entry_type", "label": "Entry type", "kind": "combo",
             "options": PAYMENT_TYPES, "value": "payment"},
            {"name": "amount", "label": "Amount", "kind": "entry"},
            {"name": "method", "label": "Method", "kind": "combo",
             "options": PAYMENT_METHODS, "value": "cash"},
            {"name": "paid_at", "label": "Paid at", "kind": "entry",
             "required": False, "value": datetime.now().strftime(DATETIME_FORMAT),
             "hint": "YYYY-MM-DD HH:MM:SS (blank = now)"},
            {"name": "notes", "label": "Notes", "kind": "text",
             "required": False},
        ]

    def on_record(self) -> None:
        FormDialog(self, "Record payment", self._fields(),
                   ok_text="Record", on_save=self._record)

    def _record(self, values: dict[str, Any]) -> None:
        self.services.transactions.create(**values, user_id=self.user.id)
        show_info("The transaction was recorded.", self)

    def on_view(self) -> None:
        row = self.selected_row()
        if row is None:
            return
        DetailDialog(
            self, f"Transaction - {row['reference']}",
            [("Reference", row["reference"]),
             ("Booking", row["booking_code"] or "-"),
             ("Customer", row["customer_name"] or "-"),
             ("Entry type", row["entry_type"]),
             ("Method", row["method"]),
             ("Amount", f"{as_float(row['amount']):,.2f}"),
             ("Paid at", row["paid_at"]),
             ("Recorded by", row["recorded_by_name"] or "system")],
            notes=row.get("notes") or "")


def circle_points(latitude: float, longitude: float, radius_km: float,
                  points: int = 24) -> list[Point]:
    """Approximate a geographic circle (used for the flood-zone overlays)."""
    result: list[Point] = []
    for index in range(points):
        angle = 2 * math.pi * index / points
        d_lat = (radius_km * math.cos(angle)) / 111.32
        d_lon = (radius_km * math.sin(angle)) / (
            111.32 * math.cos(math.radians(latitude)) or 1.0)
        result.append((latitude + d_lat, longitude + d_lon))
    return result


class GpsMapPage(Page):
    """Live feed: vehicles drive along real roads while the boat patrols
    the Pasig River. Smooth marker movement, trails, follow-selected, CSV
    import, 1x-16x speed, fit fleet, four map styles and risk filters."""
    TITLE = "GPS Map"
    SUBTITLE = "Live fleet positions on real Metro Manila roads"
    ICON = "\u2316"
    SPEEDS = [("1x", 1.0), ("4x", 4.0), ("8x", 8.0), ("16x", 16.0)]
    TICK_MS = 150

    def build(self) -> None:
        page_header(self, f"{self.ICON}  {self.TITLE}",
                    self.SUBTITLE).pack(fill="x")
        toolbar = ttk.Frame(self, style="Card.TFrame", padding=(16, 12))
        toolbar.pack(fill="x", pady=(12, 0))
        self.track_button = ttk.Button(
            toolbar, text="Start tracking", style="Primary.TButton",
            command=self._toggle_tracking)
        self.track_button.pack(side="left")
        ttk.Label(toolbar, text="Feed speed",
                  style="CardMuted.TLabel").pack(side="left", padx=(16, 4))
        self.speed_var = tk.StringVar(value="1x")
        speed_box = ttk.Combobox(
            toolbar, textvariable=self.speed_var,
            values=[label for label, _value in self.SPEEDS], width=5,
            state="readonly")
        speed_box.pack(side="left")
        ttk.Button(toolbar, text="Reset positions",
                   style="Secondary.TButton",
                   command=self._reset_positions).pack(side="left",
                                                       padx=(10, 0))
        ttk.Button(toolbar, text="Fit fleet", style="Secondary.TButton",
                   command=self._fit_fleet).pack(side="left", padx=(10, 0))
        ttk.Button(toolbar, text="Center selected",
                   style="Secondary.TButton",
                   command=self._center_selected).pack(
                       side="left", padx=(10, 0))
        self.follow_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(toolbar, text="Follow", variable=self.follow_var,
                        command=self._center_selected).pack(
                            side="left", padx=(8, 0))
        ttk.Label(toolbar, text="Map style",
                  style="CardMuted.TLabel").pack(side="left", padx=(16, 4))
        self.style_var = tk.StringVar(value=TILE_SERVERS[0][0])
        self._active_tile_style = self.style_var.get()
        style_box = ttk.Combobox(
            toolbar, textvariable=self.style_var,
            values=[name for name, _url, _zoom in TILE_SERVERS], width=14,
            state="readonly")
        style_box.pack(side="left")
        style_box.bind("<<ComboboxSelected>>",
                       lambda _event: self._apply_tile_server())
        ttk.Button(toolbar, text="Import GPS log",
                   style="Secondary.TButton",
                   command=self._import_log).pack(side="right")

        body = ttk.Frame(self, style="Page.TFrame")
        body.pack(fill="both", expand=True, pady=(12, 0))

        map_card = ttk.Frame(body, style="Card.TFrame", padding=(8, 8))
        map_card.pack(side="left", fill="both", expand=True, padx=(0, 12))
        if TkinterMapView is not None:
            self.map = TkinterMapView(map_card, corner_radius=0)
            self.map.pack(fill="both", expand=True)
            settings = self.services.settings.all()
            try:
                self.map.set_position(
                    float(settings["map_center_latitude"]),
                    float(settings["map_center_longitude"]))
                self.map.set_zoom(int(float(settings["map_zoom"])))
            except (TypeError, ValueError):
                self.map.set_position(*DEFAULT_CENTER)
                self.map.set_zoom(DEFAULT_ZOOM)
            self._apply_tile_server()
        else:
            self.map = None
            placeholder = ttk.Frame(map_card, style="Card.TFrame")
            placeholder.pack(fill="both", expand=True)
            ttk.Label(placeholder, text="Map unavailable",
                      style="H2.TLabel").pack(pady=(70, 6))
            ttk.Label(placeholder,
                      text="Install the map component to see live tiles:\n\n"
                           "pip install tkintermapview\n\n"
                           "The coordinate table, risk summary, search and\n"
                           "filters below keep working without it.",
                      style="CardMuted.TLabel",
                      justify="center").pack()

        panel = ttk.Frame(body, style="Card.TFrame", padding=(14, 12))
        panel.pack(side="right", fill="y")
        panel.configure(width=350)
        panel.pack_propagate(False)
        ttk.Label(panel, text="Fleet positions",
                  style="H2.TLabel").pack(anchor="w")
        search_row = ttk.Frame(panel, style="Card.TFrame")
        search_row.pack(fill="x", pady=(8, 0))
        self.search_var = tk.StringVar()
        search_entry = ttk.Entry(search_row, textvariable=self.search_var)
        search_entry.pack(side="left", fill="x", expand=True)
        search_entry.bind("<KeyRelease>",
                          lambda _event: self._refresh_table())
        self.risk_filter_var = tk.StringVar(value="All risk levels")
        risk_box = ttk.Combobox(
            search_row, textvariable=self.risk_filter_var, width=12,
            state="readonly",
            values=["All risk levels", "Low", "Moderate", "High", "Severe",
                    "Unknown"])
        risk_box.pack(side="left", padx=(6, 0))
        risk_box.bind("<<ComboboxSelected>>",
                      lambda _event: self._refresh_table())

        summary = ttk.Frame(panel, style="Card.TFrame")
        summary.pack(fill="x", pady=(10, 0))
        self.risk_vars: dict[str, tk.StringVar] = {}
        for level in ("severe", "high", "moderate", "low", "unknown"):
            row = ttk.Frame(summary, style="Card.TFrame")
            row.pack(fill="x", pady=1)
            ttk.Label(row, text=DOT, foreground=RISK_COLORS[level],
                      background=PALETTE["card"]).pack(side="left")
            ttk.Label(row, text=level.title(),
                      style="Card.TLabel").pack(side="left", padx=(6, 0))
            var = tk.StringVar(value="0")
            self.risk_vars[level] = var
            ttk.Label(row, textvariable=var,
                      style="Value.TLabel").pack(side="right")

        table_frame, self.table = make_treeview(panel, [
            ("plate", "Plate", 90, "w"), ("position", "Position", 125, "w"),
            ("risk", "Risk", 80, "w")], height=10)
        table_frame.pack(fill="x", pady=(10, 0))
        self.table.bind("<<TreeviewSelect>>",
                        lambda _event: self._select_vehicle())

        ttk.Label(panel, text="Selected vehicle",
                  style="Field.TLabel").pack(anchor="w", pady=(12, 0))
        self.assessment_var = tk.StringVar(
            value="Select a vehicle in the table to see its live flood risk "
                  "assessment.")
        ttk.Label(panel, textvariable=self.assessment_var,
                  style="Card.TLabel", wraplength=310,
                  justify="left").pack(anchor="w", pady=(4, 0))

        self.markers: dict[str, Any] = {}
        self.marker_risks: dict[str, str] = {}
        self.vehicle_rows: list[dict[str, Any]] = []
        self.table_rows: list[dict[str, Any]] = []
        self.selected_plate: str | None = None
        self.trail: list[Point] = []
        self.trail_path = None
        self._tracking = False
        self._tick_count = 0
        self._zone_signature: tuple[Any, ...] | None = None
        self._draw_zones()
        self._tick_after_id: str | None = self.after(
            self.TICK_MS, self._tick)

    def refresh(self) -> None:
        self.vehicle_rows = self.services.vehicles.list_vehicles()
        self._draw_zones()
        self._update_markers()
        self._update_summary()
        self._refresh_table()
        self._update_assessment()

    def _refresh_table(self) -> None:
        search = self.search_var.get().strip().lower()
        filter_label = self.risk_filter_var.get()
        level_filter = (filter_label.lower() if
                        filter_label != "All risk levels" else "")
        self.table_rows = []
        for row in self.vehicle_rows:
            if search and search not in str(row["plate_number"]).lower():
                continue
            if level_filter and str(row.get("risk_level") or "unknown") \
                    != level_filter:
                continue
            self.table_rows.append(row)
        self.table.delete(*self.table.get_children())
        for index, row in enumerate(self.table_rows):
            position = "-"
            if has_gps_position(row.get("latitude"),
                                row.get("longitude")):
                position = (f"{as_float(row['latitude']):.5f}, "
                            f"{as_float(row['longitude']):.5f}")
            self.table.insert("", "end", values=[
                row["plate_number"], position,
                str(row.get("risk_level") or "unknown")],
                tags=[str(row.get("risk_level") or "unknown"),
                      "stripe" if index % 2 else ""])

    def _update_summary(self) -> None:
        counts: dict[str, int] = {}
        for row in self.vehicle_rows:
            level = str(row.get("risk_level") or "unknown")
            counts[level] = counts.get(level, 0) + 1
        for level, var in self.risk_vars.items():
            var.set(str(counts.get(level, 0)))

    def _update_assessment(self) -> None:
        row = None
        if self.selected_plate:
            row = next((r for r in self.vehicle_rows
                        if str(r.get("plate_number")) == self.selected_plate),
                       None)
        if row is None:
            self.assessment_var.set(
                "Select a vehicle in the table to see its live flood risk "
                "assessment.")
            return
        zones = self.services.zones.list_zones(active_only=True)
        result = assess_position(row.get("latitude"), row.get("longitude"),
                                 zones)
        lines = [f"{row['plate_number']} - {row['brand']} {row['model']}",
                 f"Risk: {result['level'].title()} ({result['score']}/100)"]
        if result["has_position"]:
            lines.append(f"Nearest zone: {result['nearest_zone']} "
                         f"({result['distance_km']:.1f} km)")
        lines.extend(f"- {reason}" for reason in result["reasons"])
        self.assessment_var.set("\n".join(lines))

    def _make_marker(self, latitude: float, longitude: float, text: str,
                     color: str) -> Any:
        try:
            return self.map.set_marker(
                latitude, longitude, text=text,
                marker_color_circle=color, text_color=color)
        except Exception:
            try:
                return self.map.set_marker(latitude, longitude, text=text)
            except Exception:  # pragma: no cover - map not ready
                return None

    def _update_markers(self) -> None:
        if self.map is None:
            return
        seen: set[str] = set()
        for row in self.vehicle_rows:
            if not has_gps_position(row.get("latitude"),
                                    row.get("longitude")):
                continue
            plate = str(row["plate_number"])
            seen.add(plate)
            color = RISK_COLORS.get(str(row.get("risk_level") or "unknown"),
                                    "#64748b")
            risk = str(row.get("risk_level") or "unknown")
            marker = self.markers.get(plate)
            if marker is not None and self.marker_risks.get(plate) != risk:
                try:
                    marker.delete()
                except Exception:  # pragma: no cover - map widget teardown
                    logging.getLogger(__name__).debug(
                        "Could not refresh GPS marker for %s", plate,
                        exc_info=True)
                self.markers.pop(plate, None)
                self.marker_risks.pop(plate, None)
                marker = None
            if marker is None:
                marker = self._make_marker(as_float(row["latitude"]),
                                           as_float(row["longitude"]),
                                           plate, color)
                if marker is not None:
                    self.markers[plate] = marker
                    self.marker_risks[plate] = risk
            else:
                try:
                    marker.set_position(as_float(row["latitude"]),
                                        as_float(row["longitude"]))
                except Exception:  # pragma: no cover - map widget teardown
                    logging.getLogger(__name__).debug(
                        "Could not update GPS marker for %s", plate,
                        exc_info=True)
        for plate in list(self.markers):
            if plate not in seen:
                try:
                    self.markers[plate].delete()
                except Exception:  # pragma: no cover - map widget teardown
                    logging.getLogger(__name__).debug(
                        "Could not remove GPS marker for %s", plate,
                        exc_info=True)
                del self.markers[plate]
                self.marker_risks.pop(plate, None)

    def _draw_zones(self) -> None:
        if self.map is None:
            return
        zones = self.services.zones.list_zones(active_only=True)
        signature = tuple(sorted(
            (z["id"], z["risk_level"], round(as_float(z["latitude"]), 5),
             round(as_float(z["longitude"]), 5),
             round(as_float(z["radius_km"]), 2)) for z in zones))
        if signature == self._zone_signature:
            return
        self._zone_signature = signature
        try:
            self.map.delete_all_polygon()
        except Exception:  # pragma: no cover
            pass
        for zone in zones:
            color = RISK_COLORS.get(str(zone["risk_level"]), "#d97706")
            points = circle_points(as_float(zone["latitude"]),
                                   as_float(zone["longitude"]),
                                   as_float(zone["radius_km"]))
            try:
                self.map.set_polygon(points, fill_color=None,
                                     outline_color=color, border_width=2,
                                     name=str(zone["name"]))
            except Exception:
                try:
                    self.map.set_polygon(points, outline_color=color,
                                         border_width=2)
                except Exception:  # pragma: no cover
                    pass

    def _apply_tile_server(self) -> None:
        if self.map is None:
            return
        for name, url, max_zoom in TILE_SERVERS:
            if name == self.style_var.get():
                try:
                    self.map.set_tile_server(url, max_zoom=max_zoom)
                    self._active_tile_style = name
                except Exception as exc:  # pragma: no cover - widget/provider
                    logging.getLogger(__name__).exception(
                        "Could not switch GPS map style to %s", name)
                    self.style_var.set(self._active_tile_style)
                    show_error(
                        f"Could not switch the map to {name}.\n\n{exc}", self)
                return

    def _fit_fleet(self) -> None:
        if self.map is None:
            return
        positioned = [r for r in self.vehicle_rows if has_gps_position(
            r.get("latitude"), r.get("longitude"))]
        latitudes = [as_float(r["latitude"]) for r in positioned]
        longitudes = [as_float(r["longitude"]) for r in positioned]
        for zone in self.services.zones.list_zones(active_only=True):
            latitudes.append(as_float(zone["latitude"]))
            longitudes.append(as_float(zone["longitude"]))
        if not latitudes or not longitudes:
            show_info("There are no GPS positions or active flood zones to fit.",
                      self)
            return
        try:
            self.map.fit_bounding_box((max(latitudes), min(longitudes)),
                                      (min(latitudes), max(longitudes)))
        except Exception as exc:  # pragma: no cover - widget state
            logging.getLogger(__name__).exception(
                "Could not fit the GPS map to the fleet")
            show_error(f"Could not fit the map to the fleet.\n\n{exc}", self)

    def _center_selected(self) -> None:
        if self.map is None:
            return
        row = next((item for item in self.vehicle_rows
                    if str(item.get("plate_number")) == self.selected_plate),
                   None)
        if row is None or not has_gps_position(
                row.get("latitude"), row.get("longitude")):
            show_info("Select a vehicle with a recorded GPS position first.",
                      self)
            return
        try:
            self.map.set_position(as_float(row["latitude"]),
                                  as_float(row["longitude"]))
        except Exception as exc:  # pragma: no cover - widget state
            logging.getLogger(__name__).exception(
                "Could not center GPS map on %s", row["plate_number"])
            show_error(
                f"Could not center the map on {row['plate_number']}.\n\n{exc}",
                self)

    def stop(self) -> None:
        self._tracking = False
        if self._tick_after_id is None:
            return
        try:
            self.after_cancel(self._tick_after_id)
        except tk.TclError:  # pragma: no cover - window is already closing
            logging.getLogger(__name__).debug(
                "Could not cancel GPS update timer during shutdown",
                exc_info=True)
        self._tick_after_id = None

    def _tick(self) -> None:
        self._tick_after_id = None
        if not self.winfo_exists():
            return
        if self._tracking:
            multiplier = dict(self.SPEEDS).get(self.speed_var.get(), 1.0)
            moved = self.services.tracking.step(
                self.TICK_MS / 1000.0 * multiplier)
            self.vehicle_rows = moved
            self._update_markers()
            self._record_trail()
            if self.follow_var.get() and self.map is not None:
                row = next((item for item in moved
                            if str(item.get("plate_number")) ==
                            self.selected_plate), None)
                if row is not None:
                    self.map.set_position(as_float(row["latitude"]),
                                          as_float(row["longitude"]))
            self._tick_count += 1
            if self._tick_count % 10 == 0:
                self.vehicle_rows = self.services.vehicles.list_vehicles()
                self._update_markers()
                self._update_summary()
                self._refresh_table()
                self._update_assessment()
        self._tick_after_id = self.after(self.TICK_MS, self._tick)

    def _record_trail(self) -> None:
        if not self.selected_plate or self.map is None:
            return
        row = next((r for r in self.vehicle_rows
                    if str(r.get("plate_number")) == self.selected_plate), None)
        if row is None or not has_gps_position(
                row.get("latitude"), row.get("longitude")):
            return
        self.trail.append((as_float(row["latitude"]),
                           as_float(row["longitude"])))
        if len(self.trail) > 80:
            self.trail = self.trail[-80:]
        if len(self.trail) >= 2:
            try:
                if self.trail_path is None:
                    self.trail_path = self.map.set_path(
                        list(self.trail), color=PALETTE["accent"], width=2)
                else:
                    self.trail_path.set_position_list(list(self.trail))
            except Exception:  # pragma: no cover
                self.trail_path = None

    def _toggle_tracking(self) -> None:
        self._tracking = not self._tracking
        self.track_button.configure(
            text="Stop tracking" if self._tracking else "Start tracking")

    def _reset_positions(self) -> None:
        try:
            count = self.services.tracking.reset_positions()
        except AppError as exc:
            show_error(str(exc), self)
            return
        self.trail.clear()
        if self.trail_path is not None:
            try:
                self.trail_path.delete()
            except Exception:  # pragma: no cover
                pass
            self.trail_path = None
        self.refresh()
        show_info(f"{count} vehicle(s) were placed back at the start of "
                  "their routes.", self)

    def _import_log(self) -> None:
        path = filedialog.askopenfilename(
            parent=self, title="Import GPS log (CSV)",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if not path:
            return
        try:
            updated, skipped = self.services.tracking.apply_gps_log(path)
        except AppError as exc:
            show_error(str(exc), self)
            return
        self._tracking = False
        self.track_button.configure(text="Start tracking")
        self.follow_var.set(False)
        show_info(f"GPS log imported.\n\nUpdated: {updated} vehicle(s)\n"
                  f"Skipped: {skipped} row(s)\n\n"
                  "Demo tracking was paused so these positions are not "
                  "overwritten.", self)
        self.refresh()
        self._fit_fleet()

    def _select_vehicle(self) -> None:
        selection = self.table.selection()
        if not selection:
            return
        index = self.table.index(selection[0])
        if 0 <= index < len(self.table_rows):
            self.selected_plate = str(self.table_rows[index]["plate_number"])
        self._center_selected()
        self.trail.clear()
        if self.trail_path is not None:
            try:
                self.trail_path.delete()
            except Exception:  # pragma: no cover
                pass
            self.trail_path = None
        self._update_assessment()


class FloodZonesPage(TablePage):
    """Flood prone areas with severity, radius and active monitoring."""
    TITLE = "Flood Zones"
    SUBTITLE = "Flood prone areas with severity, radius and monitoring"
    ICON = "\u25c8"
    COLUMNS = [
        ("name", "Zone name", 230, "w"),
        ("barangay", "Barangay", 180, "w"),
        ("risk_level", "Risk", 90, "w"),
        ("latitude", "Latitude", 90, "e"),
        ("longitude", "Longitude", 90, "e"),
        ("radius", "Radius km", 80, "e"),
        ("active", "Monitoring", 90, "center"),
    ]
    FILTERS = [("All zones", ""), ("Active only", "active"),
               ("Inactive only", "inactive")]
    EXTRA_ACTIONS = [("Toggle monitoring", "toggle")]
    TREE_HEIGHT = 16

    def load_rows(self) -> list[dict[str, Any]]:
        search = self.search_var.get()
        value = self.filter_value()
        if value == "active":
            return self.services.zones.list_zones(active_only=True,
                                                  search=search)
        rows = self.services.zones.list_zones(search=search)
        if value == "inactive":
            return [z for z in rows if not z["is_active"]]
        return rows

    def row_values(self, row: dict[str, Any]) -> list[Any]:
        return [
            row["name"], row.get("barangay") or "-", row["risk_level"],
            f"{as_float(row['latitude']):.5f}",
            f"{as_float(row['longitude']):.5f}",
            f"{as_float(row['radius_km']):.2f}",
            "Active" if row["is_active"] else "Paused",
        ]

    def row_tags(self, row: dict[str, Any]) -> list[str]:
        tags = [str(row["risk_level"])]
        if not row["is_active"]:
            tags.append("muted")
        return tags

    @staticmethod
    def _fields(zone: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        zone = zone or {}
        return [
            {"name": "name", "label": "Zone name", "kind": "entry",
             "value": zone.get("name", "")},
            {"name": "barangay", "label": "Barangay", "kind": "entry",
             "required": False, "value": zone.get("barangay", "")},
            {"name": "risk_level", "label": "Risk level", "kind": "combo",
             "options": RISK_LEVELS, "value": zone.get("risk_level",
                                                       "moderate")},
            {"name": "latitude", "label": "Latitude", "kind": "entry",
             "value": zone.get("latitude", ""), "hint": "e.g. 14.5995"},
            {"name": "longitude", "label": "Longitude", "kind": "entry",
             "value": zone.get("longitude", ""), "hint": "e.g. 120.9842"},
            {"name": "radius_km", "label": "Radius (km)", "kind": "entry",
             "value": zone.get("radius_km", 1.0)},
            {"name": "notes", "label": "Notes", "kind": "text",
             "required": False, "value": zone.get("notes", "")},
        ]

    def on_add(self) -> None:
        FormDialog(self, "Add flood zone", self._fields(), on_save=self._create)

    def _create(self, values: dict[str, Any]) -> None:
        zone_id = self.services.zones.create(**values)
        show_info(f"{values['name']} was added (zone #{zone_id}).", self)

    def on_edit(self) -> None:
        row = self.selected_row()
        if row is None:
            return
        current = self.services.zones.get(int(row["id"]))
        FormDialog(self, f"Edit {current['name']}", self._fields(current),
                   on_save=lambda values: self.services.zones.update(
                       int(row["id"]), **values))

    def on_view(self) -> None:
        row = self.selected_row()
        if row is None:
            return
        zone = self.services.zones.get(int(row["id"]))
        DetailDialog(
            self, f"Flood zone - {zone['name']}",
            [("Name", zone["name"]),
             ("Barangay", zone["barangay"] or "-"),
             ("Risk level", zone["risk_level"]),
             ("Latitude", f"{as_float(zone['latitude']):.5f}"),
             ("Longitude", f"{as_float(zone['longitude']):.5f}"),
             ("Radius", f"{as_float(zone['radius_km']):.2f} km"),
             ("Monitoring", "Active" if zone["is_active"] else "Paused"),
             ("Registered", zone["created_at"])],
            notes=zone["notes"])

    def on_toggle(self) -> None:
        row = self.selected_row()
        if row is None:
            return
        active = bool(row["is_active"])
        label = "resume monitoring for" if not active else "pause monitoring for"
        if not confirm(f"Do you want to {label} {row['name']}?", self):
            return
        try:
            self.services.zones.set_active(int(row["id"]), not active)
        except AppError as exc:
            show_error(str(exc), self)
            return
        self.app.refresh_all()


class AlertsPage(TablePage):
    """Alerts page: manual notices plus the automatic flood-risk warnings."""
    TITLE = "Alerts"
    SUBTITLE = "Flood warnings and manual notices"
    ICON = "\u2691"
    COLUMNS = [
        ("created_at", "Created", 140, "w"),
        ("title", "Title", 250, "w"),
        ("severity", "Severity", 90, "w"),
        ("plate_number", "Vehicle", 100, "w"),
        ("zone_name", "Flood zone", 170, "w"),
        ("source", "Source", 80, "center"),
        ("status", "Status", 110, "w"),
    ]
    FILTERS = [("All statuses", ""), ("New", "new"),
               ("Acknowledged", "acknowledged"), ("Resolved", "resolved")]
    DEFAULT_FILTER = "All statuses"
    SHOW_ADD = False
    SHOW_DELETE = True
    EXTRA_ACTIONS = [("Acknowledge", "acknowledge"),
                     ("Mark resolved", "resolve")]
    GLOBAL_ACTIONS = [("Run flood risk scan", "scan"),
                       ("New alert", "new_alert")]
    TREE_HEIGHT = 16

    def load_rows(self) -> list[dict[str, Any]]:
        return self.services.alerts.list_alerts(
            status=self.filter_value(), search=self.search_var.get())

    def row_tags(self, row: dict[str, Any]) -> list[str]:
        return [str(row["severity"]), str(row["status"])]

    def on_view(self) -> None:
        row = self.selected_row()
        if row is None:
            return
        DetailDialog(
            self, f"Alert - {row['title']}",
            [("Created", row["created_at"]),
             ("Title", row["title"]),
             ("Severity", row["severity"]),
             ("Vehicle", row["plate_number"] or "-"),
             ("Flood zone", row["zone_name"] or "-"),
             ("Source", row["source"]),
             ("Status", row["status"]),
             ("Raised by", row["created_by_name"] or "system")],
            notes=row["message"])

    def on_new_alert(self) -> None:
        vehicles = self.services.vehicles.list_vehicles()
        FormDialog(
            self, "New alert",
            [{"name": "title", "label": "Title", "kind": "entry"},
             {"name": "severity", "label": "Severity", "kind": "combo",
              "options": ALERT_SEVERITIES, "value": "warning"},
             {"name": "vehicle_id", "label": "Vehicle (optional)",
              "kind": "combo",
              "options": [("(none)", None)] + [
                  (f"{v['plate_number']} - {v['brand']} {v['model']}",
                   int(v["id"])) for v in vehicles],
              "value": None, "required": False},
             {"name": "message", "label": "Message", "kind": "text",
              "required": True}],
            columns=2, ok_text="Raise alert",
            on_save=lambda values: self.services.alerts.create(
                title=values["title"], message=values["message"],
                severity=values["severity"], source="manual",
                vehicle_id=values["vehicle_id"], user_id=self.user.id))

    def on_acknowledge(self) -> None:
        self._set_status("acknowledged")

    def on_resolve(self) -> None:
        self._set_status("resolved")

    def _set_status(self, status: str) -> None:
        row = self.selected_row()
        if row is None:
            return
        self.services.alerts.set_status(int(row["id"]), status)
        self.app.refresh_all()

    def on_delete(self) -> None:
        row = self.selected_row()
        if row is None:
            return
        if not confirm(f"Delete the alert '{row['title']}'?", self):
            return
        try:
            self.services.alerts.delete(int(row["id"]))
        except AppError as exc:
            show_error(str(exc), self)
            return
        self.app.refresh_all()

    def on_scan(self) -> None:
        threshold = self.db.setting("alert_threshold", "high")
        try:
            created = self.services.alerts.generate_flood_alerts(
                self.user.id, threshold)
        except AppError as exc:
            show_error(f"The flood risk scan failed: {exc}", self)
            return
        self.app.refresh_all()
        show_info(
            f"Flood risk scan finished.\n\n{created} new alert(s) were raised "
            f"using the '{threshold}' threshold.\n\nChange the threshold on "
            "th"
            "the Settings page if you need earlier warnings.", self)


class ReportsPage(Page):
    """Preview and export to PDF (ReportLab) and CSV (built-in csv)."""
    TITLE = "Reports"
    SUBTITLE = "Preview and export to PDF (ReportLab) or CSV"
    ICON = "\u2263"

    def build(self) -> None:
        page_header(self, f"{self.ICON}  {self.TITLE}",
                    self.SUBTITLE).pack(fill="x")
        body = ttk.Frame(self, style="Page.TFrame")
        body.pack(fill="both", expand=True, pady=(12, 0))

        picker = ttk.Frame(body, style="Card.TFrame", padding=(14, 12))
        picker.pack(side="left", fill="y", padx=(0, 12))
        ttk.Label(picker, text="Report", style="H2.TLabel").pack(
            anchor="w", pady=(0, 8))
        for key, label in ReportService.REPORT_TYPES:
            ttk.Button(picker, text=label, style="Secondary.TButton",
                       command=partial(self._select, key)).pack(
                fill="x", pady=(0, 6))

        preview = ttk.Frame(body, style="Card.TFrame", padding=(14, 12))
        preview.pack(side="left", fill="both", expand=True)
        self.report_title_var = tk.StringVar(value="Choose a report")
        self.report_summary_var = tk.StringVar(value="")
        ttk.Label(preview, textvariable=self.report_title_var,
                  style="H1.TLabel").pack(anchor="w")
        ttk.Label(preview, textvariable=self.report_summary_var,
                  style="CardMuted.TLabel", wraplength=640,
                  justify="left").pack(anchor="w", pady=(2, 8))
        self.preview_holder = ttk.Frame(preview, style="Card.TFrame")
        self.preview_holder.pack(fill="both", expand=True)
        actions = ttk.Frame(preview, style="Card.TFrame")
        actions.pack(fill="x", pady=(10, 0))
        ttk.Button(actions, text="Export PDF", style="Primary.TButton",
                   command=self._export_pdf).pack(side="right")
        ttk.Button(actions, text="Export CSV", style="Secondary.TButton",
                   command=self._export_csv).pack(side="right", padx=(0, 8))
        self.current_report: ReportData | None = None
        self.current_key = ""

    def refresh(self) -> None:
        if self.current_key:
            self._select(self.current_key)

    def _select(self, key: str) -> None:
        try:
            report = self.services.reports.build(key)
        except AppError as exc:
            show_error(str(exc), self)
            return
        self.current_report = report
        self.current_key = key
        self.report_title_var.set(report.title)
        self.report_summary_var.set(
            f"{report.subtitle}  |  " + "  |  ".join(report.summary))
        for child in self.preview_holder.winfo_children():
            child.destroy()
        columns = [(f"c{index}", str(name), 120, "w")
                   for index, name in enumerate(report.columns)]
        frame, tree = make_treeview(self.preview_holder, columns, height=18)
        frame.pack(fill="both", expand=True)
        for index, row in enumerate(report.rows):
            tree.insert("", "end",
                        values=["" if v is None else str(v) for v in row],
                        tags=["stripe" if index % 2 else ""])

    def _export_pdf(self) -> None:
        if self.current_report is None:
            show_info("Choose a report first.", self)
            return
        try:
            destination = unique_path(PDF_EXPORT_DIR, self.current_key, ".pdf")
            export_pdf_report(self.current_report, destination)
        except AppError as exc:
            show_error(str(exc), self)
            return
        show_info(f"PDF report saved to:\n{destination}", self)
        open_in_file_manager(destination.parent, self)

    def _export_csv(self) -> None:
        if self.current_report is None:
            show_info("Choose a report first.", self)
            return
        try:
            destination = unique_path(CSV_EXPORT_DIR, self.current_key, ".csv")
            export_csv_report(self.current_report, destination)
        except AppError as exc:
            show_error(str(exc), self)
            return
        show_info(f"CSV report saved to:\n{destination}", self)
        open_in_file_manager(destination.parent, self)


class UsersPage(TablePage):
    """Administrator-only account management with password resets."""
    TITLE = "Users"
    SUBTITLE = "Administrator-only account management"
    ICON = "\u25c6"
    COLUMNS = [
        ("username", "Username", 140, "w"),
        ("full_name", "Full name", 230, "w"),
        ("role", "Role", 90, "w"),
        ("active", "Status", 100, "w"),
        ("created_at", "Created", 160, "w"),
    ]
    EXTRA_ACTIONS = [("Reset password", "password"),
                     ("Activate/Deactivate", "toggle")]
    TREE_HEIGHT = 16

    def load_rows(self) -> list[dict[str, Any]]:
        rows = []
        for user in self.services.auth.list_users():
            user["active"] = "Active" if user["is_active"] else "Disabled"
            rows.append(user)
        return rows

    def row_tags(self, row: dict[str, Any]) -> list[str]:
        return ["muted"] if not row.get("is_active") else []

    @staticmethod
    def _add_fields() -> list[dict[str, Any]]:
        return [
            {"name": "username", "label": "Username", "kind": "entry",
             "hint": "3-24 characters"},
            {"name": "full_name", "label": "Full name", "kind": "entry"},
            {"name": "role", "label": "Role", "kind": "combo",
             "options": USER_ROLES, "value": "staff"},
            {"name": "password", "label": "Password", "kind": "password",
             "hint": "min 6 characters with a number"},
            {"name": "confirm", "label": "Confirm password",
             "kind": "password"},
        ]

    @staticmethod
    def _edit_fields(current: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            {"name": "full_name", "label": "Full name", "kind": "entry",
             "value": current["full_name"]},
            {"name": "role", "label": "Role", "kind": "combo",
             "options": USER_ROLES, "value": current["role"]},
        ]

    @staticmethod
    def _password_fields() -> list[dict[str, Any]]:
        return [
            {"name": "password", "label": "New password", "kind": "password"},
            {"name": "confirm", "label": "Confirm new password",
             "kind": "password"},
        ]

    def on_add(self) -> None:
        FormDialog(self, "Add user", self._add_fields(),
                   ok_text="Create account", on_save=self._create)

    def _create(self, values: dict[str, Any]) -> None:
        self.services.auth.create_user(**values)
        show_info(f"Account '{values['username']}' was created.", self)

    def on_edit(self) -> None:
        row = self.selected_row()
        if row is None:
            return
        current = self.services.auth.list_users()
        record = next((u for u in current if int(u["id"]) == int(row["id"])),
                      None)
        if record is None:
            show_error("That user no longer exists.", self)
            return
        FormDialog(self, f"Edit {record['username']}",
                   self._edit_fields(record),
                   on_save=lambda values: self.services.auth.update_user(
                       int(row["id"]), **values))

    def on_view(self) -> None:
        row = self.selected_row()
        if row is None:
            return
        DetailDialog(
            self, f"User - {row['username']}",
            [("Username", row["username"]),
             ("Full name", row["full_name"]),
             ("Role", row["role"]),
             ("Status", row["active"]),
             ("Created", row["created_at"])])

    def on_password(self) -> None:
        row = self.selected_row()
        if row is None:
            return
        FormDialog(
            self, f"Reset password - {row['username']}",
            self._password_fields(), columns=1, ok_text="Reset password",
            on_save=lambda values: self._reset_password(
                int(row["id"]), str(row["username"]), values))

    def _reset_password(self, user_id: int, username: str,
                        values: dict[str, Any]) -> None:
        self.services.auth.reset_password(
            user_id, values["password"], values["confirm"])
        show_info(f"The password for '{username}' was reset.", self)

    def on_toggle(self) -> None:
        row = self.selected_row()
        if row is None:
            return
        if int(row["id"]) == int(self.user.id):
            show_error("You cannot deactivate your own account while "
                       "signed in.", self)
            return
        active = bool(row["is_active"])
        verb = "re-enable" if not active else "deactivate"
        if not confirm(f"Do you want to {verb} the account "
                       f"'{row['username']}'?", self):
            return
        try:
            self.services.auth.update_user(int(row["id"]),
                                           is_active=not active)
        except AppError as exc:
            show_error(str(exc), self)
            return
        self.app.refresh_all()


class SettingsPage(Page):
    """Organisation, currency, map centre/zoom, alert threshold, backup."""
    TITLE = "Settings"
    SUBTITLE = ("Organisation, currency, map defaults, alert threshold, "
                "data locations and backup")
    ICON = "\u2699"

    FIELDS = [
        ("organisation", "Organisation name", "entry", None),
        ("currency", "Currency", "entry", None),
        ("map_center_latitude", "Map centre latitude", "entry", None),
        ("map_center_longitude", "Map centre longitude", "entry", None),
        ("map_zoom", "Map zoom (3-19)", "entry", None),
        ("alert_threshold", "Flood alert threshold", "combo", RISK_LEVELS),
    ]

    def build(self) -> None:
        page_header(self, f"{self.ICON}  {self.TITLE}",
                    self.SUBTITLE).pack(fill="x")
        body = ttk.Frame(self, style="Page.TFrame")
        body.pack(fill="both", expand=True, pady=(12, 0))

        left = ttk.Frame(body, style="Card.TFrame", padding=(18, 14))
        left.pack(side="left", fill="both", expand=True, padx=(0, 12))
        ttk.Label(left, text="Organisation and defaults",
                  style="H2.TLabel").pack(anchor="w", pady=(0, 10))
        self.vars: dict[str, tk.StringVar] = {}
        for name, label, kind, options in self.FIELDS:
            row = ttk.Frame(left, style="Card.TFrame")
            row.pack(fill="x", pady=(0, 8))
            ttk.Label(row, text=label, style="Field.TLabel").pack(anchor="w")
            variable = tk.StringVar()
            self.vars[name] = variable
            if kind == "combo":
                box = ttk.Combobox(row, textvariable=variable,
                                   values=list(options or []), width=28,
                                   state="readonly")
                box.pack(anchor="w")
            else:
                ttk.Entry(row, textvariable=variable,
                          width=30).pack(anchor="w")
        ttk.Button(left, text="Save settings", style="Primary.TButton",
                   command=self._save).pack(anchor="w", pady=(14, 0))
        self.save_message_var = tk.StringVar()
        ttk.Label(left, textvariable=self.save_message_var,
                  style="CardMuted.TLabel").pack(anchor="w", pady=(6, 0))

        right = ttk.Frame(body, style="Card.TFrame", padding=(18, 14))
        right.pack(side="left", fill="both", expand=True)
        ttk.Label(right, text="Data locations",
                  style="H2.TLabel").pack(anchor="w", pady=(0, 10))
        for label, path in (("Database", database_path()),
                            ("Vehicle pictures", IMAGE_DIR),
                            ("PDF exports", PDF_EXPORT_DIR),
                            ("CSV exports", CSV_EXPORT_DIR),
                            ("Log file", LOG_FILE)):
            ttk.Label(right, text=label, style="Field.TLabel").pack(anchor="w")
            ttk.Label(right, text=str(path), style="CardMuted.TLabel",
                      wraplength=330, justify="left").pack(anchor="w",
                                                           pady=(0, 8))
        ttk.Button(right, text="Open data folder",
                   style="Secondary.TButton",
                   command=lambda: open_in_file_manager(
                       DATA_ROOT, self)).pack(anchor="w", pady=(4, 12))
        ttk.Separator(right).pack(fill="x", pady=(4, 10))
        ttk.Label(right, text="Backup", style="H2.TLabel").pack(anchor="w",
                                                                pady=(0, 6))
        ttk.Label(right,
                  text="Copy the whole SQLite database to a safe location "
                       "before making big changes.",
                  style="CardMuted.TLabel", wraplength=330,
                  justify="left").pack(anchor="w")
        ttk.Button(right, text="Backup database now",
                   style="Primary.TButton",
                   command=self._backup).pack(anchor="w", pady=(10, 0))

    def refresh(self) -> None:
        settings = self.services.settings.all()
        for name, _label, _kind, _options in self.FIELDS:
            self.vars[name].set(settings.get(name, ""))

    def _save(self) -> None:
        try:
            self.services.settings.update(
                {name: variable.get() for name, variable in self.vars.items()})
        except AppError as exc:
            show_error(str(exc), self)
            return
        self.save_message_var.set("Settings saved.")
        self.app.refresh_all()

    def _backup(self) -> None:
        destination = filedialog.asksaveasfilename(
            parent=self, title="Backup database",
            defaultextension=".db",
            initialfile=("rental_system_backup_"
                         f"{datetime.now():%Y%m%d_%H%M%S}.db"),
            filetypes=[("SQLite database", "*.db"), ("All files", "*.*")])
        if not destination:
            return
        try:
            saved = self.services.settings.backup(destination)
        except AppError as exc:
            show_error(str(exc), self)
            return
        show_info(f"The database was backed up to:\n{saved}", self)


NAV_PAGES = [
    ("dashboard", "Dashboard", "\u25c9", DashboardPage),
    ("vehicles", "Vehicles", "\u25a4", VehiclesPage),
    ("customers", "Customers", "\u2630", CustomersPage),
    ("bookings", "Bookings", "\u25a6", BookingsPage),
    ("transactions", "Transactions", "\u20b1", TransactionsPage),
    ("gps", "GPS Map", "\u2316", GpsMapPage),
    ("zones", "Flood Zones", "\u25c8", FloodZonesPage),
    ("alerts", "Alerts", "\u2691", AlertsPage),
    ("reports", "Reports", "\u2263", ReportsPage),
    ("users", "Users", "\u25c6", UsersPage),
    ("settings", "Settings", "\u2699", SettingsPage),
]


def _exc_location(exc: Exception) -> str:
    """Deepest frame of an exception - pinpoints where it happened."""
    frame = exc.__traceback__
    while frame is not None and frame.tb_next is not None:
        frame = frame.tb_next
    if frame is None:
        return "unknown location"
    return f"{frame.tb_frame.f_code.co_filename}, line {frame.tb_lineno}"


class _ErrorPage(ttk.Frame):
    """Placeholder shown when a page cannot be built.

    The rest of the application keeps working - one broken page never
    stops the whole interface.
    """

    def __init__(self, parent: tk.Widget, key: str, exc: Exception) -> None:
        super().__init__(parent, style="Page.TFrame", padding=(24, 20))
        title = {entry[0]: entry[1] for entry in NAV_PAGES}.get(key, key)
        ttk.Label(self, text=f"The {title} page could not be opened",
                  style="H1.TLabel").pack(anchor="w")
        ttk.Label(self, text=f"{type(exc).__name__}: {exc}",
                  style="Danger.TLabel", wraplength=760,
                  justify="left").pack(anchor="w", pady=(10, 0))
        ttk.Label(self, text=f"Where: {_exc_location(exc)}",
                  style="Muted.TLabel").pack(anchor="w", pady=(6, 0))
        ttk.Label(self, text=(
            "The rest of the application keeps working. The full technical "
            f"details were written to {LOG_FILE}"),
            style="Muted.TLabel", wraplength=760,
            justify="left").pack(anchor="w", pady=(10, 0))

    def on_show(self) -> None:
        return

    def refresh(self) -> None:
        return


class _FallbackLoginWindow(tk.Toplevel):
    """Emergency sign-in window built only from classic tk widgets.

    Used when the themed login window cannot be constructed on a
    particular computer, so signing in is always possible.
    """

    def __init__(self, parent: tk.Tk, auth_service: AuthService,
                 reason: Exception | None = None) -> None:
        super().__init__(parent)
        self.auth = auth_service
        self.user: User | None = None
        self.title(f"{APP_NAME} - Sign in")
        self.configure(background="#eef2f7")
        self.resizable(False, False)

        card = tk.Frame(self, bg="#ffffff", padx=36, pady=28)
        card.pack(fill="both", expand=True, padx=24, pady=24)
        tk.Label(card, text="Flood Ready Vehicle System", bg="#ffffff",
                 fg="#12293f", font=("Segoe UI", 15, "bold")).pack(anchor="w")
        tk.Label(card, text="Rental operations with flood-risk monitoring",
                 bg="#ffffff", fg="#64748b",
                 font=("Segoe UI", 10)).pack(anchor="w", pady=(4, 4))
        if reason is not None:
            tk.Label(card, text=(
                "Using the simple sign-in window because the standard one "
                f"could not be opened:\n{type(reason).__name__}: {reason}"),
                bg="#ffffff", fg="#b06a00", font=("Segoe UI", 9),
                wraplength=330, justify="left").pack(anchor="w", pady=(8, 10))
        else:
            tk.Frame(card, bg="#ffffff", height=10).pack()

        self.username_var = tk.StringVar()
        self.password_var = tk.StringVar()
        self.error_var = tk.StringVar()
        tk.Label(card, textvariable=self.error_var, bg="#ffffff",
                 fg="#b3261e", font=("Segoe UI", 10), wraplength=330,
                 justify="left").pack(anchor="w", pady=(0, 6))
        tk.Label(card, text="Username", bg="#ffffff",
                 fg="#64748b").pack(anchor="w")
        tk.Entry(card, textvariable=self.username_var, width=34,
                 font=("Segoe UI", 11)).pack(fill="x", pady=(4, 12))
        tk.Label(card, text="Password", bg="#ffffff",
                 fg="#64748b").pack(anchor="w")
        tk.Entry(card, textvariable=self.password_var, width=34,
                 show="\u2022", font=("Segoe UI", 11)).pack(fill="x",
                                                            pady=(4, 12))
        tk.Button(card, text="Sign in", bg="#2563eb", fg="#ffffff",
                  activebackground="#1d4ed8", activeforeground="#ffffff",
                  font=("Segoe UI", 10, "bold"), relief="flat",
                  command=self._login).pack(fill="x", ipady=4)
        tk.Label(card, text="Default login: admin / admin123",
                 bg="#ffffff", fg="#64748b").pack(anchor="w", pady=(14, 0))

        self.bind("<Return>", lambda _event: self._login())
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self._centre()

    def _login(self) -> None:
        try:
            self.user = self.auth.login(self.username_var.get(),
                                        self.password_var.get())
        except AppError as exc:
            self.error_var.set(str(exc))
            self.password_var.set("")
            return
        except Exception:
            logging.getLogger(__name__).exception("Unexpected login failure")
            self.error_var.set("Sign in failed. Check the application log.")
            return
        self.destroy()

    def _cancel(self) -> None:
        self.user = None
        self.destroy()

    def _centre(self) -> None:
        self.update_idletasks()
        width = max(440, self.winfo_reqwidth())
        height = max(500, self.winfo_reqheight())
        x = max(0, (self.winfo_screenwidth() - width) // 2)
        y = max(0, (self.winfo_screenheight() - height) // 3)
        self.geometry(f"{width}x{height}+{x}+{y}")


class MainWindow(ttk.Frame):
    """Sidebar shell with the status bar and the menu bar."""

    def __init__(self, parent: tk.Tk, database: DatabaseManager,
                 user: User) -> None:
        super().__init__(parent, style="Page.TFrame")
        self.db = database
        self.user = user
        self.services = Services(database)
        self.sign_out = False
        self.pages: dict[str, Page] = {}
        self.current_key = ""
        self.nav_buttons: dict[str, ttk.Button] = {}
        self._online_flag: bool | None = None
        self._closing = threading.Event()

        parent.title(f"{APP_NAME} - {user.full_name}")
        parent.geometry("1180x760")
        parent.minsize(1000, 660)
        self._centre_window(parent)
        parent.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_menu(parent)
        self._build_status_bar()
        self._build_sidebar()
        self.container = ttk.Frame(self, style="Page.TFrame")
        self.container.pack(side="left", fill="both", expand=True)
        self.show_page("dashboard")
        self._start_connectivity_check()
        self.pack(fill="both", expand=True)

    def destroy(self) -> None:
        self._closing.set()
        gps_page = self.pages.get("gps")
        if isinstance(gps_page, GpsMapPage):
            gps_page.stop()
        super().destroy()

    def _build_menu(self, parent: tk.Tk) -> None:
        menubar = tk.Menu(parent)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Backup database...",
                              command=self._backup_database)
        file_menu.add_separator()
        file_menu.add_command(label="Sign out", command=self._sign_out)
        file_menu.add_command(label="Exit", command=self._on_close)
        menubar.add_cascade(label="File", menu=file_menu)
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(
            label=f"About {APP_NAME}",
            command=lambda: messagebox.showinfo(
                APP_NAME,
                f"{APP_NAME} v{APP_VERSION}\n\nRental operations with "
                "flood-risk monitoring for Metro Manila.\n\nGUI: Tkinter | "
                "Data: SQLite | Map: OpenStreetMap\n\nDefault login: "
                "admin / admin123", parent=self))
        menubar.add_cascade(label="Help", menu=help_menu)
        parent.config(menu=menubar)

    def _build_sidebar(self) -> None:
        sidebar = ttk.Frame(self, style="Sidebar.TFrame", padding=(0, 12))
        sidebar.pack(side="left", fill="y")
        brand = ttk.Frame(sidebar, style="Sidebar.TFrame", padding=(14, 0))
        brand.pack(fill="x")
        ttk.Label(brand, text="Flood Ready\nVehicle System",
                  style="SidebarTitle.TLabel", justify="left").pack(anchor="w")
        ttk.Label(brand, text=f"Version {APP_VERSION}",
                  style="SidebarSection.TLabel").pack(anchor="w", pady=(6, 0))

        nav = ttk.Frame(sidebar, style="Sidebar.TFrame")
        nav.pack(fill="x", pady=(18, 0))
        for key, label, icon, _page_class in NAV_PAGES:
            if key == "users" and not self.user.is_admin:
                continue
            button = ttk.Button(nav, text=f"  {icon}  {label}",
                                style="Sidebar.TButton",
                                command=partial(self.show_page, key))
            button.pack(fill="x", pady=1)
            self.nav_buttons[key] = button

        user_card = ttk.Frame(sidebar, style="SidebarSoft.TFrame",
                              padding=(14, 10))
        user_card.pack(side="bottom", fill="x")
        ttk.Label(user_card, text=self.user.full_name,
                  style="SidebarUser.TLabel").pack(anchor="w")
        ttk.Label(user_card, text=self.user.role.title(),
                  style="SidebarUserRole.TLabel").pack(anchor="w")
        ttk.Button(user_card, text="Sign out",
                   style="SidebarSignOut.TButton",
                   command=self._sign_out).pack(fill="x", pady=(8, 0))

    def _build_status_bar(self) -> None:
        bar = ttk.Frame(self, style="Card.TFrame", padding=(14, 6))
        bar.pack(side="bottom", fill="x")
        self.status_dot = tk.Canvas(bar, width=12, height=12,
                                    background=PALETTE["card"],
                                    highlightthickness=0)
        self.status_dot.pack(side="left")
        self.status_label = ttk.Label(
            bar, text="Checking internet connection...",
            style="Status.TLabel")
        self.status_label.pack(side="left", padx=(8, 0))
        self.org_var = tk.StringVar(
            value=self.db.setting("organisation", APP_NAME))
        ttk.Label(bar, textvariable=self.org_var,
                  style="Status.TLabel").pack(side="left", padx=(18, 0))
        ttk.Label(bar, text=f"Data: {DATA_ROOT}",
                  style="Status.TLabel").pack(side="right")
        ttk.Label(bar, text=f"{self.user.full_name} ({self.user.role})",
                  style="Status.TLabel").pack(side="right", padx=(0, 18))

    def show_page(self, key: str) -> None:
        if self.current_key and self.current_key in self.pages:
            self.pages[self.current_key].pack_forget()
        self.current_key = key
        page = self.pages.get(key)
        if page is None:
            page_class = {entry[0]: entry[3] for entry in NAV_PAGES}[key]
            try:
                page = page_class(self.container, self)
                self.pages[key] = page
                page.on_show()
            except Exception as exc:
                # One broken page never stops the application: show a clear
                logging.getLogger(__name__).exception(
                    "The '%s' page could not be built", key)
                self.pages.pop(key, None)
                page = _ErrorPage(self.container, key, exc)
        else:
            try:
                page.on_show()
            except Exception as exc:
                logging.getLogger(__name__).exception(
                    "The '%s' page could not be refreshed", key)
                self.pages.pop(key, None)
                page = _ErrorPage(self.container, key, exc)
        page.pack(fill="both", expand=True)
        for button_key, button in self.nav_buttons.items():
            button.configure(
                style="SidebarActive.TButton"
                if button_key == key else "Sidebar.TButton")

    def refresh_all(self) -> None:
        page = self.pages.get(self.current_key)
        if page is not None:
            page.refresh()
        self.org_var.set(self.db.setting("organisation", APP_NAME))

    def _start_connectivity_check(self) -> None:
        worker = threading.Thread(target=self._connectivity_worker, daemon=True)
        worker.start()
        self._poll_connectivity()

    def _connectivity_worker(self) -> None:
        while not self._closing.is_set():
            try:
                with urllib.request.urlopen(
                        OFFLINE_CHECK_URL, timeout=OFFLINE_TIMEOUT) as response:
                    self._online_flag = response.getcode() < 400
            except OSError:
                self._online_flag = False
            self._closing.wait(30)

    def _poll_connectivity(self) -> None:
        if not self.winfo_exists():
            return
        self._set_connectivity(self._online_flag)
        self.after(5000, self._poll_connectivity)

    def _set_connectivity(self, online: bool | None) -> None:
        if online is None:
            color = PALETTE["muted"]
            text = "Checking internet connection..."
        elif online:
            color = PALETTE["ok"]
            text = "Internet connection available"
        else:
            color = "#d97706"
            text = ("Offline - map tiles may not load; saved data and "
                    "other features remain available")
        self.status_dot.delete("all")
        self.status_dot.create_oval(2, 2, 10, 10, fill=color, outline="")
        self.status_label.configure(text=text)

    def _backup_database(self) -> None:
        destination = filedialog.asksaveasfilename(
            parent=self, title="Backup database", defaultextension=".db",
            initialfile=(f"rental_system_backup_"
                         f"{datetime.now():%Y%m%d_%H%M%S}.db"),
            filetypes=[("SQLite database", "*.db"), ("All files", "*.*")])
        if not destination:
            return
        try:
            saved = self.services.settings.backup(destination)
        except AppError as exc:
            show_error(str(exc), self)
            return
        show_info(f"The database was backed up to:\n{saved}", self)

    def _sign_out(self) -> None:
        if not confirm("Sign out and return to the sign-in window?", self):
            return
        self.sign_out = True
        self._closing.set()
        self.winfo_toplevel().quit()

    def _on_close(self) -> None:
        self.sign_out = False
        self._closing.set()
        self.winfo_toplevel().quit()

    @staticmethod
    def _centre_window(window: tk.Tk) -> None:
        window.update_idletasks()
        width, height = 1180, 760
        x = max(0, (window.winfo_screenwidth() - width) // 2)
        y = max(0, (window.winfo_screenheight() - height) // 3)
        window.geometry(f"{width}x{height}+{x}+{y}")


def _fatal(message: str, log_path: str = "") -> None:
    """Show a friendly fatal error (never a raw traceback)."""
    logging.getLogger(__name__).critical(message)
    try:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            APP_NAME,
            f"{message}\n\nApplication data folder: {DATA_DIR}"
            + (f"\nLog file: {log_path}" if log_path else ""))
        root.destroy()
    except Exception:  # pragma: no cover - no display available
        print(message, file=sys.stderr)


def _excepthook(exc_type: Any, exc_value: Any, exc_traceback: Any) -> None:
    logging.getLogger(__name__).exception(
        "Unhandled exception",
        exc_info=(exc_type, exc_value, exc_traceback))
    try:
        messagebox.showerror(
            APP_NAME,
            "An unexpected problem occurred and the action was cancelled.\n"
            "Technical details were written to the log file.\n\n"
            f"({exc_value})")
    except Exception:  # pragma: no cover
        pass


def _report_interface_failure(exc: Exception, log_path: str) -> None:
    """Precise interface failure report: dialog, startup_error.txt, console."""
    details = "".join(traceback.format_exception(type(exc), exc,
                                                 exc.__traceback__))
    report_file = DATA_ROOT / "startup_error.txt"
    try:
        report_file.parent.mkdir(parents=True, exist_ok=True)
        report_file.write_text(
            f"{APP_NAME} {APP_VERSION} - the interface could not be started\n"
            f"Python {sys.version.split()[0]} on {sys.platform}\n\n"
            f"{details}\n", encoding="utf-8")
    except OSError:
        report_file = None
    print(details, file=sys.stderr)
    lines = [line for line in details.strip().splitlines() if line.strip()]
    tail = "\n".join(lines[-8:])
    _fatal(
        "The application interface could not be started.\n\n"
        f"Reason: {type(exc).__name__}: {exc}\n\n"
        f"{tail}\n\n"
        "The complete report was saved to:\n"
        f"{report_file if report_file else log_path}\n\n"
        "Tip: run   python main.py --smoke-test   to "
        "pinpoint problems.", log_path)


def prepare_database() -> DatabaseManager:
    """Create folders, the database file, tables and the one-time seed data."""
    manager = DatabaseManager()
    manager.initialise()
    if manager.seed_if_needed():
        logging.getLogger(__name__).info(
            "First launch preparation finished (defaults inserted once)")
    return manager


def run_smoke_test(log_path: str) -> int:
    """Build every window and page offscreen and exercise the services.

    Prints a [ok]/[FAIL] line per check so problems can be pinpointed
    without opening the GUI.
    """
    print(f"{APP_NAME} {APP_VERSION} - smoke test")
    print("-" * 58)
    failures: list[str] = []

    try:
        database = prepare_database()
        print("  [ok] folders, SQLite database, schema and seed data")
    except Exception as exc:
        print(f"  [FAIL] database preparation: {type(exc).__name__}: {exc}")
        print(f"\nTechnical details were written to: {log_path}")
        return 1

    auth = AuthService(database)
    test_username = "smoketest_temp"
    database.execute("DELETE FROM users WHERE username = ?", (test_username,))
    auth.create_user(username=test_username, full_name="Smoke Test",
                     role="admin", password="smoketest1",
                     confirm="smoketest1")

    root = tk.Tk()
    root.withdraw()
    apply_theme(root)
    try:
        try:
            login_window = LoginWindow(root, auth)
            root.update_idletasks()
            login_window.destroy()
            print("  [ok] login window")
        except Exception as exc:
            failures.append(f"login window: {type(exc).__name__}: {exc}")
            print(f"  [FAIL] login window: {type(exc).__name__}: {exc}")

        user = None
        try:
            user = auth.login(test_username, "smoketest1")
            print("  [ok] authentication (PBKDF2 sign-in)")
        except Exception as exc:
            failures.append(f"sign-in: {type(exc).__name__}: {exc}")
            print(f"  [FAIL] sign-in: {type(exc).__name__}: {exc}")

        if user is not None:
            window = None
            try:
                window = MainWindow(root, database, user)
            except Exception as exc:
                failures.append(f"main window: {type(exc).__name__}: {exc}")
                print(f"  [FAIL] main window: {type(exc).__name__}: {exc}")
            if window is not None:
                for key, label, _icon, _page in NAV_PAGES:
                    if key == "users" and not user.is_admin:
                        continue
                    try:
                        window.show_page(key)
                        root.update_idletasks()
                        print(f"  [ok] {label.lower()} page")
                    except Exception as exc:
                        failures.append(
                            f"{label.lower()} page: {type(exc).__name__}: {exc}")
                        print(f"  [FAIL] {label.lower()} page: "
                              f"{type(exc).__name__}: {exc}")

                services = window.services
                checks = (
                    ("dashboard statistics",
                     lambda: (services.dashboard.summary(),
                              services.dashboard.collections_by_month(),
                              services.dashboard.risk_distribution())),
                    ("report builders (all six)",
                     lambda: [services.reports.build(key)
                              for key, _label in
                              services.reports.REPORT_TYPES]),
                    ("flood risk scan",
                     lambda: services.alerts.generate_flood_alerts(
                         user.id, "high")),
                    ("demonstration GPS feed",
                     lambda: services.tracking.step(1.0)),
                )
                for label, check in checks:
                    try:
                        check()
                        print(f"  [ok] {label}")
                    except Exception as exc:
                        failures.append(
                            f"{label}: {type(exc).__name__}: {exc}")
                        print(f"  [FAIL] {label}: {type(exc).__name__}: {exc}")
                window.destroy()
    finally:
        database.execute("DELETE FROM users WHERE username = ?",
                         (test_username,))
        root.destroy()

    print("-" * 58)
    if failures:
        print(f"{len(failures)} problem(s) found.")
        for failure in failures:
            print(f"  - {failure}")
        print(f"\nTechnical details were written to: {log_path}")
        return 1
    print("Everything works. Start the application with:")
    print("  python main.py")
    return 0


def main() -> int:
    log_path = setup_logging()
    sys.excepthook = _excepthook
    logging.getLogger(__name__).info("%s %s starting", APP_NAME, APP_VERSION)

    if "--smoke-test" in sys.argv[1:]:
        return run_smoke_test(str(log_path))

    try:
        database = prepare_database()
    except AppError as exc:
        _fatal(str(exc), str(log_path))
        return 1
    except Exception as exc:
        logging.getLogger(__name__).exception("Startup failed")
        _fatal("The application could not prepare its local database.\n\n"
               f"Reason: {type(exc).__name__}: {exc}", str(log_path))
        return 1

    try:
        root = tk.Tk()
    except Exception as exc:  # Python installed without tcl/tk
        _fatal("Python's Tkinter module is not available on this computer.\n\n"
               "Reinstall Python 3.11 or newer and make sure the "
               "'tcl/tk and IDLE' option is ticked in the installer.",
               str(log_path))
        logging.getLogger(__name__).debug("tkinter import error: %s", exc)
        return 1

    apply_theme(root)
    root.withdraw()
    try:
        while True:
            auth = AuthService(database)
            try:
                login = LoginWindow(root, auth)
            except Exception as exc:
                # The themed login window failed on this computer - fall
                # back to a plain tk window so signing in still works.
                logging.getLogger(__name__).exception(
                    "The themed login window failed - using the fallback")
                login = _FallbackLoginWindow(root, auth, exc)
            root.wait_window(login)
            if login.user is None:
                root.destroy()
                return 0
            window = MainWindow(root, database, login.user)
            root.deiconify()
            root.mainloop()
            window.destroy()
            if not window.sign_out:
                root.destroy()
                return 0
            root.withdraw()
    except Exception as exc:
        logging.getLogger(__name__).exception("Interface failure")
        _report_interface_failure(exc, str(log_path))
        return 1
    finally:
        logging.getLogger(__name__).info("Application closed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
