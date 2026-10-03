"""Vehicle inventory tests."""
from __future__ import annotations

import pytest

from app import DataConflictError, NotFoundError, OperationError, ValidationError
from database.seed_data import VEHICLE_CATALOG


def test_vehicle_catalog_is_seeded_once(vehicles):
    rows = vehicles.list_vehicles()
    assert len(rows) == len(VEHICLE_CATALOG)
    assert {row["plate_number"] for row in rows} == {
        entry[0] for entry in VEHICLE_CATALOG
    }
    assert vehicles.db.seed_if_needed() is False
    assert len(vehicles.list_vehicles()) == len(VEHICLE_CATALOG)


def test_create_and_fetch_vehicle(vehicles):
    vehicle_id = vehicles.create(plate_number="tst 101", brand="Toyota",
                                model="Avanza", category="AUV", year=2024,
                                seats=7, rate_per_day=2000)
    vehicle = vehicles.get(vehicle_id)
    assert vehicle.plate_number == "TST 101"
    assert vehicle.status == "available"
    assert vehicle.is_archived is False


def test_duplicate_plate_is_rejected(vehicles):
    vehicles.create(plate_number="dup 101", brand="Toyota", model="Vios",
                    rate_per_day=1500)
    with pytest.raises(DataConflictError):
        vehicles.create(plate_number="DUP 101", brand="Honda", model="City",
                        rate_per_day=1400)


def test_invalid_data_is_rejected(vehicles):
    with pytest.raises(ValidationError):  # plate too short
        vehicles.create(plate_number="A", brand="Toyota", model="Vios")
    with pytest.raises(ValidationError):  # missing brand
        vehicles.create(plate_number="ok 202", brand="  ", model="Vios")
    with pytest.raises(ValidationError):  # bad year
        vehicles.create(plate_number="ok 202", brand="Toyota", model="Vios", year="nope")
    with pytest.raises(ValidationError):  # bad coordinates
        vehicles.create(plate_number="ok 202", brand="Toyota", model="Vios",
                        latitude="14.6", longitude="")


def test_update_vehicle_details(vehicles):
    vehicle_id = vehicles.create(plate_number="upd 303", brand="Toyota", model="Vios",
                                rate_per_day=1500, seats=5)
    vehicles.update(vehicle_id, rate_per_day=1750, seats=6, latitude=14.6, longitude=121.0)
    vehicle = vehicles.get(vehicle_id)
    assert vehicle.rate_per_day == 1750
    assert vehicle.seats == 6
    assert (vehicle.latitude, vehicle.longitude) == (14.6, 121.0)


def test_update_location_validates_coordinates(vehicles):
    vehicle_id = vehicles.create(plate_number="loc 404", brand="Toyota", model="Vios")
    with pytest.raises(ValidationError):
        vehicles.update_location(vehicle_id, 999, 121)
    vehicles.update_location(vehicle_id, "14.5995", "120.9842")
    vehicle = vehicles.get(vehicle_id)
    assert vehicle.latitude == pytest.approx(14.5995)


def test_archive_and_restore(vehicles, bookings, customer_id):
    vehicle_id = vehicles.create(plate_number="arc 505", brand="Toyota", model="Innova")
    vehicles.set_archived(vehicle_id, True)
    assert vehicles.get(vehicle_id).is_archived is True
    assert all(row["id"] != vehicle_id for row in vehicles.list_vehicles())
    assert any(row["id"] == vehicle_id
               for row in vehicles.list_vehicles(include_archived=True))
    vehicles.set_archived(vehicle_id, False)
    assert vehicles.get(vehicle_id).is_archived is False

    bookings.create(vehicle_id=vehicle_id, customer_id=customer_id,
                    start_date="2026-07-01", end_date="2026-07-02")
    with pytest.raises(OperationError):
        vehicles.set_archived(vehicle_id, True)


def test_missing_vehicle_raises(vehicles):
    with pytest.raises(NotFoundError):
        vehicles.get(99999)


def test_search_and_status_filters(vehicles):
    vehicles.create(plate_number="fnd 606", brand="Isuzu", model="NLR")
    assert len(vehicles.list_vehicles(search="isuzu")) >= 1
    assert len(vehicles.list_vehicles(search="nothing-matches")) == 0
    assert all(row["status"] == "rented"
               for row in vehicles.list_vehicles(status="rented"))
