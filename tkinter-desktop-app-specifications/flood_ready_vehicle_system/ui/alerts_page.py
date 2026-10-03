"""Alerts page: manual notices plus the automatic flood-risk warnings."""
from __future__ import annotations

from typing import Any

from . import TablePage
from .dialogs import DetailDialog, FormDialog, confirm, show_error, show_info


class AlertsPage(TablePage):
    TITLE = "Alerts"
    SUBTITLE = "Flood warnings and manual notices"
    COLUMNS = [
        ("created_at", "Created", 140, "w"),
        ("title", "Title", 250, "w"),
        ("severity", "Severity", 90, "w"),
        ("plate_number", "Vehicle", 100, "w"),
        ("zone_name", "Flood zone", 170, "w"),
        ("source", "Source", 80, "center"),
        ("status", "Status", 110, "w"),
    ]
    FILTERS = [("All statuses", ""), ("New", "new"), ("Acknowledged", "acknowledged"),
               ("Resolved", "resolved")]
    DEFAULT_FILTER = "All statuses"
    SHOW_DELETE = True
    EXTRA_ACTIONS = [("Acknowledge", "acknowledge"), ("Mark resolved", "resolve")]
    GLOBAL_ACTIONS = [("Run flood risk scan", "scan"), ("New alert", "new_alert")]
    TREE_HEIGHT = 16

    def load_rows(self) -> list[dict[str, Any]]:
        return self.services.alerts.list_alerts(status=self.filter_value(),
                                                search=self.search_var.get())

    def row_tags(self, row: dict[str, Any]) -> list[str]:
        return [str(row["severity"]), str(row["status"])]

    # ----------------------------------------------------------------- actions
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
              "options": ["info", "warning", "critical"], "value": "warning"},
             {"name": "vehicle_id", "label": "Vehicle (optional)", "kind": "combo",
              "options": [("(none)", None)] + [
                  (f"{v['plate_number']} - {v['brand']} {v['model']}", int(v["id"]))
                  for v in vehicles],
              "value": None, "required": False},
             {"name": "message", "label": "Message", "kind": "text", "required": True}],
            columns=2, ok_text="Raise alert",
            on_save=lambda values: self.services.alerts.create(
                title=values["title"], message=values["message"],
                severity=values["severity"], source="manual",
                vehicle_id=values["vehicle_id"], user_id=self.user.id))
        self.app.refresh_all()

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
        except Exception as exc:
            show_error(str(exc), self)
            return
        self.app.refresh_all()

    def on_scan(self) -> None:
        threshold = self.db.setting("alert_threshold", "high")
        try:
            created = self.services.alerts.generate_flood_alerts(self.user.id, threshold)
        except Exception as exc:
            show_error(f"The flood risk scan failed: {exc}", self)
            return
        self.app.refresh_all()
        show_info(
            f"Flood risk scan finished.\n\n{created} new alert(s) were raised using the "
            f"'{threshold}' threshold.\n\nChange the threshold on the Settings page if you "
            "need earlier warnings.", self)
