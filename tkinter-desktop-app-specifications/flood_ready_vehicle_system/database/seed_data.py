"""First-launch seed data.

Runs exactly once, guarded by the ``seed_version`` row in the ``settings``
table, so re-opening the application never duplicates the default
administrator or the vehicle catalog.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.models import now_iso
from app.security import hash_password

if TYPE_CHECKING:  # pragma: no cover
    from app.database import DatabaseManager

log = logging.getLogger(__name__)

SEED_VERSION = "1"
DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "admin123"
DEFAULT_ADMIN_NAME = "System Administrator"

VEHICLE_CATALOG = [
    # plate, brand, model, category, year, seats, rate/day, lat, lon
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
    # name, barangay, risk, lat, lon, radius_km, notes
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

SETTINGS = {
    "organisation": "Flood Ready Vehicle System",
    "currency": "PHP",
    "map_center_latitude": "14.5995",
    "map_center_longitude": "120.9842",
    "map_zoom": "12",
    "alert_threshold": "high",
}


def seed_database(db: "DatabaseManager") -> bool:
    """Insert defaults once. Returns True when seeding happened."""
    if db.setting("seed_version", "") == SEED_VERSION:
        return False

    now = now_iso()
    salt, digest = hash_password(DEFAULT_ADMIN_PASSWORD)
    db.execute(
        "INSERT OR IGNORE INTO users "
        "(username, full_name, role, password_salt, password_hash, is_active, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, 1, ?, ?)",
        (DEFAULT_ADMIN_USERNAME, DEFAULT_ADMIN_NAME, "admin", salt, digest, now, now),
    )

    db.execute_many(
        "INSERT OR IGNORE INTO vehicles "
        "(plate_number, brand, model, category, year, seats, rate_per_day, status, "
        " is_archived, latitude, longitude, image_path, notes, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, 'available', 0, ?, ?, NULL, '', ?, ?)",
        [
            (plate, brand, model, category, year, seats, rate, lat, lon, now, now)
            for plate, brand, model, category, year, seats, rate, lat, lon in VEHICLE_CATALOG
        ],
    )

    db.execute_many(
        "INSERT INTO flood_zones "
        "(name, barangay, risk_level, latitude, longitude, radius_km, is_active, notes, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?)",
        [
            (name, barangay, risk, lat, lon, radius, notes, now, now)
            for name, barangay, risk, lat, lon, radius, notes in FLOOD_ZONES
        ],
    )

    for key, value in SETTINGS.items():
        db.set_setting(key, value)
    db.set_setting("seed_version", SEED_VERSION)

    log.info("Seed data inserted (default admin + %d vehicles + %d flood zones)",
             len(VEHICLE_CATALOG), len(FLOOD_ZONES))
    return True
