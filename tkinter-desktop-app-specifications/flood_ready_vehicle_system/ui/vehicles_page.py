"""Vehicles page: inventory, rates, GPS position, pictures and archiving."""
from __future__ import annotations

from typing import Any

from app.config import VEHICLE_CATEGORIES, VEHICLE_STATUSES
from app.services import assess_position
from . import TablePage
from .dialogs import DetailDialog, FormDialog, confirm, show_error, show_info
from .styles import money


class VehiclesPage(TablePage):
    TITLE = "Vehicles"
    SUBTITLE = "Inventory, rates, GPS position and pictures"
    COLUMNS = [
        ("plate_number", "Plate", 105, "w"),
        ("vehicle", "Brand / Model", 195, "w"),
        ("category", "Category", 95, "w"),
        ("rate", "Rate/day", 95, "e"),
        ("status", "Status", 100, "w"),
        ("active_booking", "Current booking", 110, "w"),
        ("risk", "Flood risk", 90, "w"),
        ("score", "Score", 55, "center"),
        ("nearest_zone", "Nearest flood zone", 185, "w"),
    ]
    FILTERS = [("All statuses", ""), ("Available", "available"), ("Rented", "rented"),
               ("Maintenance", "maintenance")]
    DEFAULT_FILTER = "All statuses"
    SHOW_ARCHIVE = True
    EXTRA_ACTIONS = [("Set GPS location", "location"), ("Attach picture", "picture"),
                     ("Change status", "status")]
    TREE_HEIGHT = 15

    # -------------------------------------------------------------------- data
    def load_rows(self) -> list[dict[str, Any]]:
        zones = self.services.zones.list_zones(active_only=True)
        rows = self.services.vehicles.list_vehicles(
            search=self.search_var.get(), status=self.filter_value(),
            include_archived=self.include_archived_var.get())
        for row in rows:
            assessment = assess_position(
                float(row["latitude"] or 0), float(row["longitude"] or 0), zones)
            row["risk"] = assessment["level"]
            row["risk_level"] = assessment["level"]
            row["score"] = assessment["score"] if assessment["has_position"] else "-"
            row["nearest_zone"] = assessment["nearest_zone"]
        return rows

    def row_values(self, row: dict[str, Any]) -> list[Any]:
        return [row["plate_number"], f"{row['brand']} {row['model']}", row["category"],
                money(row["rate_per_day"]), row["status"],
                row["active_booking"] or "-", row["risk"], row["score"],
                row["nearest_zone"] or "-"]

    def row_tags(self, row: dict[str, Any]) -> list[str]:
        tags = [str(row["status"])]
        if row.get("risk_level"):
            tags.append(str(row["risk_level"]))
        if row.get("is_archived"):
            tags.append("archived")
        return tags

    # ------------------------------------------------------------------ dialogs
    def _fields(self, vehicle: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        vehicle = vehicle or {}
        return [
            {"name": "plate_number", "label": "Plate number", "kind": "entry",
             "value": vehicle.get("plate_number", "")},
            {"name": "category", "label": "Category", "kind": "combo",
             "options": VEHICLE_CATEGORIES, "value": vehicle.get("category", "Sedan")},
            {"name": "brand", "label": "Brand", "kind": "entry",
             "value": vehicle.get("brand", "")},
            {"name": "model", "label": "Model", "kind": "entry",
             "value": vehicle.get("model", "")},
            {"name": "year", "label": "Year", "kind": "number",
             "value": vehicle.get("year", 2024)},
            {"name": "seats", "label": "Seats", "kind": "number",
             "value": vehicle.get("seats", 4)},
            {"name": "rate_per_day", "label": "Rate per day", "kind": "number",
             "value": vehicle.get("rate_per_day", 1500)},
            {"name": "status", "label": "Status", "kind": "combo",
             "options": VEHICLE_STATUSES, "value": vehicle.get("status", "available")},
            {"name": "latitude", "label": "Latitude", "kind": "number",
             "value": vehicle.get("latitude") or "", "required": False,
             "hint": "Decimal degrees, e.g. 14.5995 (leave blank when unknown)"},
            {"name": "longitude", "label": "Longitude", "kind": "number",
             "value": vehicle.get("longitude") or "", "required": False},
            {"name": "notes", "label": "Notes", "kind": "text", "required": False,
             "value": vehicle.get("notes", "")},
        ]

    # ----------------------------------------------------------------- actions
    def on_add(self) -> None:
        dialog = FormDialog(self, "Add vehicle", self._fields(), on_save=self._create)
        if dialog.values is None:
            return
        self.app.refresh_all()
        show_info(f"Vehicle {dialog.values['plate_number'].upper()} was added.", self)

    def _create(self, values: dict[str, Any]) -> None:
        self.services.vehicles.create(**values)

    def on_edit(self) -> None:
        row = self.selected_row()
        if row is None:
            return
        dialog = FormDialog(self, f"Edit {row['plate_number']}", self._fields(row),
                            on_save=lambda values: self.services.vehicles.update(
                                int(row["id"]), **values))
        if dialog.values is None:
            return
        self.app.refresh_all()

    def on_view(self) -> None:
        row = self.selected_row()
        if row is None:
            return
        vehicle = self.services.vehicles.get(int(row["id"]))
        DetailDialog(
            self, f"Vehicle {vehicle.plate_number}",
            [("Plate number", vehicle.plate_number),
             ("Brand / Model", f"{vehicle.brand} {vehicle.model}"),
             ("Category", vehicle.category),
             ("Year", vehicle.year),
             ("Seats", vehicle.seats),
             ("Rate per day", money(vehicle.rate_per_day)),
             ("Status", vehicle.status),
             ("Current booking", row["active_booking"] or "-"),
             ("Latitude", vehicle.latitude or "-"),
             ("Longitude", vehicle.longitude or "-"),
             ("Nearest flood zone", row["nearest_zone"] or "-"),
             ("Flood risk", f"{row['risk']} ({row['score']}/100)"),
             ("Archived", "Yes" if vehicle.is_archived else "No")],
            notes=vehicle.notes, image_path=vehicle.image_path)

    def on_archive(self) -> None:
        row = self.selected_row()
        if row is None:
            return
        archived = bool(row["is_archived"])
        label = "restore" if archived else "archive"
        if not confirm(f"Do you want to {label} vehicle {row['plate_number']}?", self):
            return
        try:
            self.services.vehicles.set_archived(int(row["id"]), not archived)
        except Exception as exc:
            show_error(str(exc), self)
            return
        self.app.refresh_all()

    def on_status(self) -> None:
        row = self.selected_row()
        if row is None:
            return
        dialog = FormDialog(
            self, f"Change status - {row['plate_number']}",
            [{"name": "status", "label": "New status", "kind": "combo",
              "options": VEHICLE_STATUSES, "value": row["status"]}],
            columns=1, ok_text="Apply",
            on_save=lambda values: self.services.vehicles.set_status(
                int(row["id"]), values["status"]))
        if dialog.values is None:
            return
        self.app.refresh_all()

    def on_location(self) -> None:
        row = self.selected_row()
        if row is None:
            return
        dialog = FormDialog(
            self, f"Set GPS location - {row['plate_number']}",
            [{"name": "latitude", "label": "Latitude", "kind": "number",
              "value": row["latitude"] or ""},
             {"name": "longitude", "label": "Longitude", "kind": "number",
              "value": row["longitude"] or ""}],
            columns=2, ok_text="Save position",
            on_save=lambda values: self.services.vehicles.update_location(
                int(row["id"]), values["latitude"], values["longitude"]))
        if dialog.values is None:
            return
        self.app.refresh_all()

    def on_picture(self) -> None:
        from tkinter import filedialog

        row = self.selected_row()
        if row is None:
            return
        source = filedialog.askopenfilename(
            parent=self, title="Choose a vehicle picture",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.gif *.bmp *.webp"),
                       ("All files", "*.*")])
        if not source:
            return
        try:
            stored = self.services.vehicles.store_image(int(row["id"]), source)
        except Exception as exc:
            show_error(str(exc), self)
            return
        show_info(f"Picture saved as {stored} in the application images folder.", self)
        self.app.refresh_all()
