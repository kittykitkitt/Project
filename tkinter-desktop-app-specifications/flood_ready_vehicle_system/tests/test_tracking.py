"""Tests for the demonstration GPS feed (routes, movement and real-feed import)."""
from __future__ import annotations

import pytest

from app import AppError, ValidationError
from app.tracking import (
    ROUTES,
    TrackingService,
    distance_to_route_km,
    is_on_water,
    is_open_water,
    position_at,
    route_length_km,
)


@pytest.fixture()
def tracking(db):
    return TrackingService(db)


def test_every_road_route_stays_on_land():
    for name, route in ROUTES.items():
        for latitude, longitude in route["waypoints"]:
            if route["kind"] != "road":
                continue
            assert not is_open_water(latitude, longitude), (
                f"{name} waypoint ({latitude}, {longitude}) is in the water")


def test_boat_patrols_the_pasig_river():
    for latitude, longitude in ROUTES["Pasig River patrol"]["waypoints"]:
        assert is_on_water(latitude, longitude), "the boat left the river"


def test_water_model_detects_manila_bay_and_laguna():
    assert is_open_water(14.55, 120.95) is True      # Manila Bay
    assert is_open_water(14.45, 121.20) is True      # Laguna de Bay
    assert is_open_water(14.60, 121.00) is False     # Manila (land)
    assert is_open_water(14.68, 120.99) is False     # Caloocan (land)


def test_position_at_never_leaves_the_route():
    waypoints = ROUTES["EDSA"]["waypoints"]
    total = route_length_km(waypoints)
    assert position_at(waypoints, 0) == waypoints[0]
    assert position_at(waypoints, -5) == waypoints[0]
    assert position_at(waypoints, total * 2) == waypoints[-1]
    # every interpolated point sits on the polyline
    for fraction in [i / 40 for i in range(41)]:
        point = position_at(waypoints, total * fraction)
        assert distance_to_route_km(point, waypoints) < 0.05


def test_start_places_the_whole_fleet_on_a_route(tracking):
    count = tracking.start()
    assert count == 10
    status = tracking.status()
    assert len(status) == 10
    for vehicle_id, details in status.items():
        assert details["route"] in ROUTES
        assert 0.0 <= details["progress"] <= 1.0
        assert details["speed_kmh"] > 0
        if details["route"] != "Pasig River patrol":
            assert not is_open_water(details["latitude"], details["longitude"]), (
                "a vehicle was placed in the water")


def test_vehicles_only_move_along_their_route(tracking):
    tracking.start()
    for _ in range(40):
        tracking.step(600)          # ten minutes at a time
    for details in tracking.status().values():
        waypoints = ROUTES[details["route"]]["waypoints"]
        assert distance_to_route_km((details["latitude"], details["longitude"]),
                                    waypoints) < 0.05
        if details["route"] != "Pasig River patrol":
            assert not is_open_water(details["latitude"], details["longitude"]), (
                "a vehicle drove into the water")


def test_positions_are_persisted(tracking, db):
    tracking.start()
    tracking.step(300)
    rows = db.rows_as_dicts("SELECT id, latitude, longitude FROM vehicles")
    status = tracking.status()
    assert len(rows) == 10
    for row in rows:
        details = status[int(row["id"])]
        assert abs(row["latitude"] - details["latitude"]) < 0.000001
        assert abs(row["longitude"] - details["longitude"]) < 0.000001


def test_ping_pong_keeps_the_distance_inside_the_route(tracking):
    tracking.start()
    tracking.step(3600 * 40)        # far more than a full run
    total = max(tracking.route_length(state["route"])
                for state in tracking._state.values())
    for state in tracking._state.values():
        assert 0.0 <= state["distance"] <= tracking.route_length(state["route"])
    assert total > 0


def test_elapsed_simulated_time_is_tracked(tracking):
    tracking.start()
    tracking.step(90)
    tracking.step(30)
    assert tracking.elapsed_seconds == 120


def test_step_without_start_raises(tracking):
    with pytest.raises(AppError):
        tracking.step(60)


def test_reset_puts_vehicles_at_the_route_start(tracking):
    tracking.start()
    tracking.step(1800)
    tracking.reset()
    for details in tracking.status().values():
        assert details["progress"] == 0.0


def test_route_assignment_is_stable_and_sensible(tracking, vehicles):
    boats = 0
    for vehicle in vehicles.list_vehicles():
        name, route = tracking.route_for(vehicle)
        assert name in ROUTES
        if route["kind"] == "water":
            boats += 1
            assert vehicle["category"] == "Boat"
        else:
            assert vehicle["category"] != "Boat"
    assert boats == 1, "only the rescue boat should be on the water"


def test_gps_log_import_updates_positions(tracking, tmp_path):
    tracking.start()
    log = tmp_path / "gps.csv"
    log.write_text("plate_number,latitude,longitude,timestamp\n"
                   "NCB 1234,14.600000,120.990000,2026-09-23 08:00:00\n"
                   "ABC 4567,14.650000,121.020000,2026-09-23 08:00:05\n",
                   encoding="utf-8")
    assert tracking.apply_gps_log(log) == 2
    row = tracking.db.fetch_one(
        "SELECT latitude, longitude FROM vehicles WHERE plate_number = ?", ("NCB 1234",))
    assert (row["latitude"], row["longitude"]) == (14.6, 120.99)
    assert tracking.is_running is False


def test_gps_log_import_reports_problems(tracking, tmp_path):
    log = tmp_path / "gps.csv"
    log.write_text("plate_number,latitude,longitude\n"
                   "UNKNOWN 1,14.60,120.99\n"
                   "NCB 1234,999,120.99\n", encoding="utf-8")
    with pytest.raises(ValidationError):
        tracking.apply_gps_log(log)


def test_gps_log_import_requires_an_existing_file(tracking, tmp_path):
    with pytest.raises(ValidationError):
        tracking.apply_gps_log(tmp_path / "missing.csv")
