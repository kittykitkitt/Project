"""Flood zones page: monitored flood prone areas used by the risk calculation."""
from __future__ import annotations

from typing import Any

from app.config import RISK_LEVELS
from . import TablePage
from .dialogs import DetailDialog, FormDialog, confirm, show_error


class FloodZonesPage(TablePage):
    TITLE = "Flood Zones"
    SUBTITLE = "Monitored flood-prone areas"
    COLUMNS = [
        ("name", "Zone", 230, "w"),
        ("barangay", "Barangay / City", 180, "w"),
        ("risk_level", "Risk", 90, "w"),
        ("latitude", "Latitude", 90, "e"),
        ("longitude", "Longitude", 90, "e"),
        ("radius_km", "Radius (km)", 85, "center"),
        ("vehicles_nearby", "Vehicles in zone", 120, "center"),
        ("active", "Active", 70, "center"),
    ]
    SHOW_ARCHIVE = True
    SHOW_DELETE = True
    TREE_HEIGHT = 17

    def load_rows(self) -> list[dict[str, Any]]:
        from app.services import assess_position

        zones = self.services.zones.list_zones(active_only=False)
        vehicles = self.services.vehicles.list_vehicles()
        for zone in zones:
            zone["is_archived"] = not bool(zone["is_active"])
            zone["active"] = "Yes" if zone["is_active"] else "No"
            count = 0
            for vehicle in vehicles:
                assessment = assess_position(
                    float(vehicle["latitude"] or 0), float(vehicle["longitude"] or 0), [zone])
                if assessment["inside_zone"]:
                    count += 1
            zone["vehicles_nearby"] = count
        return zones

    def row_tags(self, row: dict[str, Any]) -> list[str]:
        return [str(row["risk_level"])]

    def _fields(self, zone: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        zone = zone or {}
        return [
            {"name": "name", "label": "Zone name", "kind": "entry",
             "value": zone.get("name", "")},
            {"name": "barangay", "label": "Barangay / City", "kind": "entry",
             "required": False, "value": zone.get("barangay", "")},
            {"name": "risk_level", "label": "Risk level", "kind": "combo",
             "options": RISK_LEVELS, "value": zone.get("risk_level", "moderate")},
            {"name": "latitude", "label": "Latitude", "kind": "number",
             "value": zone.get("latitude", "")},
            {"name": "longitude", "label": "Longitude", "kind": "number",
             "value": zone.get("longitude", "")},
            {"name": "radius_km", "label": "Radius (km)", "kind": "number",
             "value": zone.get("radius_km", 1)},
            {"name": "notes", "label": "Notes", "kind": "text", "required": False,
             "value": zone.get("notes", "")},
        ]

    def on_add(self) -> None:
        FormDialog(self, "Add flood zone", self._fields(), on_save=self._create)

    def _create(self, values: dict[str, Any]) -> None:
        self.services.zones.create(**values)
        self.app.refresh_all()

    def on_edit(self) -> None:
        row = self.selected_row()
        if row is None:
            return
        FormDialog(self, f"Edit {row['name']}", self._fields(row),
                   on_save=lambda values: self.services.zones.update(
                       int(row["id"]), **values))
        self.app.refresh_all()

    def on_view(self) -> None:
        row = self.selected_row()
        if row is None:
            return
        DetailDialog(
            self, f"Flood zone - {row['name']}",
            [("Zone name", row["name"]),
             ("Barangay / City", row["barangay"] or "-"),
             ("Risk level", row["risk_level"]),
             ("Latitude", row["latitude"]),
             ("Longitude", row["longitude"]),
             ("Radius (km)", row["radius_km"]),
             ("Vehicles inside", row["vehicles_nearby"]),
             ("Active", "Yes" if row["is_active"] else "No"),
             ("Last updated", row["updated_at"])],
            notes=row["notes"])

    def on_archive(self) -> None:
        """Archive toggle is reused here to enable/disable monitoring."""
        row = self.selected_row()
        if row is None:
            return
        active = bool(row["is_active"])
        label = "deactivate" if active else "reactivate"
        if not confirm(f"Do you want to {label} monitoring for {row['name']}?", self):
            return
        self.services.zones.set_active(int(row["id"]), not active)
        self.app.refresh_all()

    def on_delete(self) -> None:
        row = self.selected_row()
        if row is None:
            return
        if not confirm(f"Delete flood zone {row['name']}? This cannot be undone.", self):
            return
        try:
            self.services.zones.delete(int(row["id"]))
        except Exception as exc:
            show_error(str(exc), self)
            return
        self.app.refresh_all()
