"""Flood-risk calculation and alert tests (no internet, no map needed)."""
from __future__ import annotations

import pytest

from app import ValidationError
from app.services import assess_position, haversine_km


def zone(name="Test Zone", risk="severe", latitude=14.6000, longitude=120.9800,
         radius=1.0):
    return {"name": name, "risk_level": risk, "latitude": latitude,
            "longitude": longitude, "radius_km": radius}


def test_haversine_known_distance():
    # One degree of latitude is about 111 km.
    assert haversine_km(14.0, 121.0, 15.0, 121.0) == pytest.approx(111.19, abs=1.0)
    assert haversine_km(14.0, 121.0, 14.0, 121.0) == 0


def test_position_without_coordinates_is_unknown():
    result = assess_position(0, 0, [zone()])
    assert result["has_position"] is False
    assert result["level"] == "unknown"
    assert result["score"] == 0


def test_inside_severe_zone_scores_high():
    result = assess_position(14.6000, 120.9800, [zone(risk="severe", radius=1.0)])
    assert result["inside_zone"] is True
    assert result["score"] >= 60
    assert result["level"] == "severe"


def test_edge_of_zone_is_scored_by_distance():
    centre = zone(radius=1.0, risk="high")
    near = assess_position(14.6000, 120.9810, [centre])   # ~0.1 km - inside the zone
    far = assess_position(14.6000, 121.0300, [centre])    # ~5.4 km - outside
    assert near["score"] > far["score"]
    assert far["level"] == "low"


def test_multiple_zones_increase_the_score():
    single = assess_position(14.6000, 120.9800, [zone(risk="moderate", radius=0.5)])
    several = assess_position(14.6000, 120.9800, [
        zone(name="A", risk="moderate", radius=0.5),
        zone(name="B", risk="high", latitude=14.6000, longitude=120.9820, radius=0.5),
        zone(name="C", risk="low", latitude=14.6000, longitude=120.9840, radius=0.5),
    ])
    assert several["score"] >= single["score"]
    assert several["nearest_zone"] in {"A", "B", "C"}


def test_zone_crud_and_validation(zones):
    zone_id = zones.create(name="Test Creek", barangay="Malabon",
                           risk_level="high", latitude=14.65, longitude=120.94,
                           radius_km=1.5)
    assert zones.get(zone_id)["name"] == "Test Creek"
    zones.update(zone_id, risk_level="severe", radius_km=2.0)
    assert zones.get(zone_id)["risk_level"] == "severe"
    zones.set_active(zone_id, False)
    assert zone_id not in [row["id"] for row in zones.list_zones(active_only=True)]
    assert zone_id in [row["id"] for row in zones.list_zones(active_only=False)]
    with pytest.raises(ValidationError):
        zones.create(name="Bad Zone", latitude="not-a-number", longitude=121)


def test_fleet_risk_alerts_are_generated(vehicles, alerts):
    created = alerts.generate_flood_alerts(threshold="high")
    assert created >= 1
    rows = alerts.list_alerts(status="new")
    assert any("FLOOD RISK" in row["title"].upper() for row in rows)
    # running the scan again on the same day must not duplicate alerts
    assert alerts.generate_flood_alerts(threshold="high") == 0


def test_alert_lifecycle(alerts):
    alert_id = alerts.create(title="Manual notice", message="Typhoon signal 2",
                             severity="warning", source="manual")
    alerts.set_status(alert_id, "acknowledged")
    assert alerts.list_alerts(status="acknowledged")[0]["id"] == alert_id
    alerts.set_status(alert_id, "resolved")
    assert alerts.open_count() == 0


def test_dashboard_summary_counts(db, alerts):
    from app.services import DashboardService

    summary = DashboardService(db).summary()
    assert summary["vehicles"]["total"] == 10
    assert summary["flood_zones"] >= 1
    assert summary["customers"] == 0
    assert summary["high_risk_vehicles"] >= 1
    assert summary["revenue_month"] == 0
