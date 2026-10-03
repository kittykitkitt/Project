"""Shared pytest fixtures.

The test suite redirects all application data into a temporary folder so the
real %LOCALAPPDATA% folder is never touched.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:  # allows "pytest" from any folder
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ["FLOODREADY_DATA_DIR"] = str(Path(tempfile.mkdtemp(prefix="floodready_tests_")))
os.environ.pop("LOCALAPPDATA", None)

import pytest  # noqa: E402

from app.database import DatabaseManager  # noqa: E402
from app.services import (  # noqa: E402
    AlertService,
    AuthService,
    BookingService,
    CustomerService,
    FloodZoneService,
    ReportService,
    TransactionService,
    VehicleService,
)


@pytest.fixture()
def db(tmp_path: Path) -> DatabaseManager:
    manager = DatabaseManager(tmp_path / "test.db")
    manager.initialise()
    manager.seed_if_needed()
    return manager


@pytest.fixture()
def auth(db: DatabaseManager) -> AuthService:
    return AuthService(db)


@pytest.fixture()
def vehicles(db: DatabaseManager) -> VehicleService:
    return VehicleService(db)


@pytest.fixture()
def customers(db: DatabaseManager) -> CustomerService:
    return CustomerService(db)


@pytest.fixture()
def bookings(db: DatabaseManager) -> BookingService:
    return BookingService(db)


@pytest.fixture()
def transactions(db: DatabaseManager) -> TransactionService:
    return TransactionService(db)


@pytest.fixture()
def zones(db: DatabaseManager) -> FloodZoneService:
    return FloodZoneService(db)


@pytest.fixture()
def alerts(db: DatabaseManager) -> AlertService:
    return AlertService(db)


@pytest.fixture()
def reports(db: DatabaseManager) -> ReportService:
    return ReportService(db)


@pytest.fixture()
def vehicle_id(vehicles: VehicleService) -> int:
    return vehicles.create(plate_number="bkg 707", brand="Toyota", model="Hiace",
                           category="Van", seats=14, rate_per_day=3800)


@pytest.fixture()
def customer_id(customers: CustomerService) -> int:
    return customers.create(full_name="Juan Dela Cruz", phone="0917 123 4567",
                            email="juan@example.com")
