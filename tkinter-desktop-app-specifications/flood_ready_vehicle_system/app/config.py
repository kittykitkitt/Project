"""Application configuration, path handling and logging setup.

Every path used by the application is derived at runtime so the project folder
can be moved to another computer, or packaged with PyInstaller, without any
code change.  No absolute, user specific path is ever hard-coded.
"""
from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

APP_NAME = "Flood Ready Vehicle System"
APP_SHORT_NAME = "FloodReadyVehicleSystem"
APP_VERSION = "1.0.0"

# Source project root: flood_ready_vehicle_system/
BASE_DIR = Path(__file__).resolve().parent.parent

# Map defaults (Manila, Philippines - the demo service area).
DEFAULT_CENTER = (14.5995, 120.9842)
DEFAULT_ZOOM = 12
OFFLINE_CHECK_URL = "https://www.openstreetmap.org"
OFFLINE_TIMEOUT = 3

CURRENCY = "PHP"
DATE_FORMAT = "%Y-%m-%d"
DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"

VEHICLE_CATEGORIES = [
    "Sedan",
    "SUV",
    "Van",
    "Pickup",
    "AUV",
    "Motorcycle",
    "Truck",
    "Boat",
]

VEHICLE_STATUSES = ["available", "rented", "maintenance"]
BOOKING_STATUSES = ["pending", "confirmed", "ongoing", "completed", "cancelled"]
PAYMENT_METHODS = ["cash", "card", "bank transfer", "mobile wallet"]
PAYMENT_TYPES = ["payment", "deposit", "refund"]
USER_ROLES = ["admin", "manager", "staff"]
RISK_LEVELS = ["low", "moderate", "high", "severe"]
ROLES_ALLOWED_TO_MANAGE_USERS = ("admin",)


def is_frozen() -> bool:
    """True when running from a PyInstaller executable."""
    return bool(getattr(sys, "frozen", False))


def resource_dir() -> Path:
    """Read-only resources (assets / schema) bundled with the application."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return BASE_DIR


def asset_path(*parts: str) -> Path:
    """Path to a bundled asset, e.g. asset_path('icons', 'app_icon.png')."""
    return resource_dir().joinpath("assets", *parts)


def schema_path() -> Path:
    if is_frozen():
        return resource_dir() / "database" / "schema.sql"
    return BASE_DIR / "database" / "schema.sql"


def local_app_data_root() -> Path:
    """%LOCALAPPDATA%\\FloodReadyVehicleSystem (portable fallback beside source).

    ``FLOODREADY_DATA_DIR`` is an optional override used by the test suite and
    for portable/USB installations; the classroom build never needs it.
    """
    override = os.getenv("FLOODREADY_DATA_DIR")
    if override:
        return Path(override)
    local_app_data = os.getenv("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / APP_SHORT_NAME
    return BASE_DIR / "app_data" / APP_SHORT_NAME


DATA_DIR = local_app_data_root() / "data"
IMAGE_DIR = local_app_data_root() / "images"
EXPORT_DIR = local_app_data_root() / "exports"
PDF_EXPORT_DIR = EXPORT_DIR / "pdf"
CSV_EXPORT_DIR = EXPORT_DIR / "csv"
LOG_DIR = local_app_data_root() / "logs"
MAP_CACHE_DIR = local_app_data_root() / "map_cache"
LOG_FILE = LOG_DIR / "application.log"

APP_DATA_FOLDERS = (
    DATA_DIR,
    IMAGE_DIR,
    PDF_EXPORT_DIR,
    CSV_EXPORT_DIR,
    LOG_DIR,
    MAP_CACHE_DIR,
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
        logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
        )
    )
    root = logging.getLogger()
    root.setLevel(level)
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)
    logging.getLogger(__name__).info(
        "%s %s starting | base=%s | data=%s", APP_NAME, APP_VERSION, BASE_DIR, DATA_DIR
    )
    return LOG_FILE


def unique_path(folder: Path, stem: str, suffix: str) -> Path:
    """Build a non colliding export/report path such as bookings_20260212_1530.pdf."""
    from datetime import datetime

    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    candidate = folder / f"{stem}_{stamp}{suffix}"
    counter = 1
    while candidate.exists():
        candidate = folder / f"{stem}_{stamp}_{counter}{suffix}"
        counter += 1
    return candidate
