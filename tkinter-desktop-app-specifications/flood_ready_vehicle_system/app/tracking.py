"""Demonstration GPS feed for the fleet.

Vehicles move along real Metro Manila road corridors (EDSA, Commonwealth,
Espana/Quezon Avenue, Roxas Boulevard, C5/Katipunan, Aurora Boulevard and the
MacArthur Highway) so the movement looks believable and never drives into
Manila Bay or Laguna de Bay.  The rescue boat is the only unit on the water: it
patrols the Pasig River, which is its job.

The feed is deterministic (a vehicle always gets the same route and speed) and
runs completely offline.  To use real positions instead, import a GPS log with
:func:`TrackingService.apply_gps_log` - the demonstration feed stops as soon as
a real source is used.
"""
from __future__ import annotations

import csv
import hashlib
import logging
import math
from pathlib import Path
from typing import TYPE_CHECKING, Any, Sequence

from app import AppError, ValidationError
from app.models import now_iso
from app.services import VehicleService, haversine_km

if TYPE_CHECKING:  # pragma: no cover
    from app.database import DatabaseManager

log = logging.getLogger(__name__)

Point = tuple[float, float]

# Coarse water model of the demonstration area.  The Manila Bay coastline runs
# north-east from Pasay to Navotas, so it is modelled as a latitude dependent
# longitude; Laguna de Bay is the south-east corner of the map.
COAST_BASE_LON = 120.978
COAST_BASE_LAT = 14.500
COAST_SLOPE = 0.15          # degrees of longitude per degree of latitude
LAGUNA_LAT = 14.6000
LAGUNA_LON = 121.0900
RIVER_CORRIDOR_KM = 0.25


def coast_longitude(latitude: float) -> float:
    """Approximate longitude of the Manila Bay coastline at *latitude*."""
    return COAST_BASE_LON - (latitude - COAST_BASE_LAT) * COAST_SLOPE

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


# ------------------------------------------------------------------ geometry
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
    """True for Manila Bay and Laguna de Bay (the water cars must never enter).

    The model is intentionally coarse but conservative: it is only used to prove
    that the demonstration routes stay on land.
    """
    if 14.40 <= latitude <= 14.78 and longitude < coast_longitude(latitude):
        return True                     # west of the coastline = Manila Bay
    if latitude < LAGUNA_LAT and longitude > LAGUNA_LON:
        return True                     # south-east corner = Laguna de Bay
    return False


def is_on_water(latitude: float, longitude: float) -> bool:
    """True for open water *and* the Pasig River corridor (the boat's route)."""
    return is_open_water(latitude, longitude) or (
        distance_to_route_km((latitude, longitude), PASIG_RIVER) <= RIVER_CORRIDOR_KM)


# -------------------------------------------------------------------- service
class TrackingService:
    """Moves the demonstration fleet and stores the positions in SQLite."""

    def __init__(self, db: "DatabaseManager") -> None:
        self.db = db
        self.vehicles = VehicleService(db)
        self._state: dict[int, dict[str, Any]] = {}
        self._lengths: dict[str, float] = {}
        self.elapsed_seconds = 0.0

    # ------------------------------------------------------------------ routes
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

    def route_for(self, vehicle: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        """Deterministic route assignment: boats patrol the river, cars use roads."""
        if str(vehicle.get("category") or "").strip().lower() == "boat":
            return "Pasig River patrol", ROUTES["Pasig River patrol"]
        roads = [name for name, route in ROUTES.items() if route["kind"] == "road"]
        name = roads[self._hash(str(vehicle.get("plate_number") or "")) % len(roads)]
        return name, ROUTES[name]

    def speed_for(self, vehicle: dict[str, Any], route: dict[str, Any]) -> float:
        low, high = (WATER_SPEED_RANGE if route["kind"] == "water"
                     else ROAD_SPEED_RANGE)
        ratio = (self._hash(f"speed:{vehicle.get('plate_number')}") % 100) / 99.0
        return round(low + (high - low) * ratio, 1)

    # -------------------------------------------------------------------- feed
    @property
    def is_running(self) -> bool:
        return bool(self._state)

    def start(self) -> int:
        """Assign routes and place every active vehicle on its route."""
        self._state = {}
        self.elapsed_seconds = 0.0
        for vehicle in self.vehicles.list_vehicles():
            name, route = self.route_for(vehicle)
            total = self.route_length(name)
            offset = (self._hash(f"offset:{vehicle['plate_number']}") % 100) / 99.0 * total
            self._state[int(vehicle["id"])] = {
                "route": name,
                "distance": round(offset, 4),
                "direction": 1,
                "speed_kmh": self.speed_for(vehicle, route),
            }
        if not self._state:
            raise AppError("There are no active vehicles to track.")
        self._persist()
        log.info("Demonstration GPS feed started for %d vehicle(s)", len(self._state))
        return len(self._state)

    def stop(self) -> None:
        self._state = {}
        self.elapsed_seconds = 0.0

    def reset(self) -> int:
        """Place every vehicle at the start of its route."""
        if not self._state:
            self.start()
        for state in self._state.values():
            state["distance"] = 0.0
            state["direction"] = 1
        self.elapsed_seconds = 0.0
        return self._persist()

    def step(self, seconds: float) -> int:
        """Advance the feed by *seconds* of simulated time and store positions."""
        if not self._state:
            raise AppError("The demonstration GPS feed is not running.")
        for state in self._state.values():
            total = self.route_length(state["route"])
            distance = state["distance"] + state["direction"] * (
                state["speed_kmh"] * float(seconds) / 3600.0)
            if distance > total:            # ping-pong: turn around at the end
                distance = max(0.0, 2 * total - distance)
                state["direction"] = -1
            elif distance < 0:
                distance = min(total, -distance)
                state["direction"] = 1
            state["distance"] = distance
        self.elapsed_seconds += float(seconds)
        return self._persist()

    def status(self) -> dict[int, dict[str, Any]]:
        """Per-vehicle route, speed and progress for the detail panel."""
        details: dict[int, dict[str, Any]] = {}
        for vehicle_id, state in self._state.items():
            waypoints = ROUTES[state["route"]]["waypoints"]
            total = self.route_length(state["route"])
            latitude, longitude = position_at(waypoints, state["distance"])
            previous = position_at(waypoints, max(0.0, state["distance"] - 0.05))
            details[vehicle_id] = {
                "route": state["route"],
                "speed_kmh": state["speed_kmh"],
                "direction": "outbound" if state["direction"] > 0 else "returning",
                "heading": "north" if latitude >= previous[0] else "south",
                "progress": round(state["distance"] / total, 2) if total else 0.0,
                "latitude": latitude,
                "longitude": longitude,
            }
        return details

    def _persist(self) -> int:
        rows = []
        for vehicle_id, state in self._state.items():
            latitude, longitude = position_at(ROUTES[state["route"]]["waypoints"],
                                              state["distance"])
            rows.append((round(latitude, 6), round(longitude, 6), now_iso(), vehicle_id))
        if rows:
            self.db.execute_many(
                "UPDATE vehicles SET latitude = ?, longitude = ?, updated_at = ? "
                "WHERE id = ?", rows)
        return len(rows)

    # ---------------------------------------------------------------- real feed
    def apply_gps_log(self, path: str | Path) -> int:
        """Import real positions from a CSV GPS log.

        Expected header: ``plate_number,latitude,longitude[,timestamp]``.
        The demonstration feed is stopped first.
        """
        source = Path(path)
        if not source.exists() or not source.is_file():
            raise ValidationError("The selected GPS log file could not be read.")
        self.stop()
        updated = 0
        problems: list[str] = []
        try:
            with source.open(newline="", encoding="utf-8-sig") as handle:
                for row in csv.DictReader(handle):
                    plate = str(row.get("plate_number") or row.get("plate") or "").strip()
                    try:
                        latitude, longitude = _coordinates(row.get("latitude"),
                                                           row.get("longitude"))
                        vehicle = self.db.fetch_one(
                            "SELECT id FROM vehicles WHERE plate_number = ?",
                            (plate.upper(),))
                        if vehicle is None:
                            problems.append(f"{plate or '?'}: unknown plate number")
                            continue
                    except ValidationError as exc:
                        problems.append(f"{plate or '?'}: {exc}")
                        continue
                    self.db.execute(
                        "UPDATE vehicles SET latitude = ?, longitude = ?, updated_at = ? "
                        "WHERE id = ?", (latitude, longitude, now_iso(),
                                         int(vehicle["id"])))
                    updated += 1
        except (OSError, csv.Error) as exc:
            log.exception("GPS log import failed")
            raise AppError("The GPS log could not be read. See the log file.") from exc

        if not updated:
            raise ValidationError(
                "No vehicle position could be imported.\n"
                + "\n".join(problems[:5]))
        if problems:
            log.warning("GPS log import skipped %d row(s): %s", len(problems),
                        "; ".join(problems[:5]))
        log.info("Imported %d vehicle position(s) from a GPS log", updated)
        return updated


def _coordinates(latitude: object, longitude: object) -> tuple[float, float]:
    from app import validators

    return validators.coordinates(latitude, longitude)
