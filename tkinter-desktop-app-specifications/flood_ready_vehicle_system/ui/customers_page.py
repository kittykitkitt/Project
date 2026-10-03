"""Customers page."""
from __future__ import annotations

from typing import Any

from . import TablePage
from .dialogs import DetailDialog, FormDialog, confirm, show_error, show_info

ID_TYPES = ["Drivers License", "Passport", "UMID", "PhilID", "Company ID", "Barangay ID"]


class CustomersPage(TablePage):
    TITLE = "Customers"
    SUBTITLE = "Renter records and identification"
    COLUMNS = [
        ("full_name", "Customer name", 210, "w"),
        ("phone", "Contact number", 130, "w"),
        ("email", "Email", 180, "w"),
        ("id_type", "ID type", 130, "w"),
        ("id_number", "ID number", 120, "w"),
        ("license_number", "License number", 120, "w"),
        ("bookings_count", "Bookings", 75, "center"),
    ]
    SHOW_ARCHIVE = True
    TREE_HEIGHT = 17

    def load_rows(self) -> list[dict[str, Any]]:
        return self.services.customers.list_customers(
            search=self.search_var.get(),
            include_archived=self.include_archived_var.get())

    def row_tags(self, row: dict[str, Any]) -> list[str]:
        return ["archived"] if row.get("is_archived") else []

    def _fields(self, customer: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        customer = customer or {}
        return [
            {"name": "full_name", "label": "Full name", "kind": "entry",
             "value": customer.get("full_name", "")},
            {"name": "phone", "label": "Contact number", "kind": "entry",
             "value": customer.get("phone", ""), "hint": "e.g. 0917 123 4567"},
            {"name": "email", "label": "Email", "kind": "entry", "required": False,
             "value": customer.get("email", "")},
            {"name": "address", "label": "Address", "kind": "entry", "required": False,
             "value": customer.get("address", "")},
            {"name": "id_type", "label": "ID type", "kind": "combo", "options": ID_TYPES,
             "value": customer.get("id_type", "Drivers License")},
            {"name": "id_number", "label": "ID number", "kind": "entry", "required": False,
             "value": customer.get("id_number", "")},
            {"name": "license_number", "label": "License number", "kind": "entry",
             "required": False, "value": customer.get("license_number", "")},
            {"name": "notes", "label": "Notes", "kind": "text", "required": False,
             "value": customer.get("notes", "")},
        ]

    def on_add(self) -> None:
        FormDialog(self, "Add customer", self._fields(), on_save=self._create)

    def _create(self, values: dict[str, Any]) -> None:
        customer_id = self.services.customers.create(**values)
        show_info(f"{values['full_name']} was added (record #{customer_id}).", self)
        self.app.refresh_all()

    def on_edit(self) -> None:
        row = self.selected_row()
        if row is None:
            return
        current = self.services.customers.get(int(row["id"]))
        FormDialog(self, f"Edit {current['full_name']}", self._fields(current),
                   on_save=lambda values: self.services.customers.update(
                       int(row["id"]), **values))
        self.app.refresh_all()

    def on_view(self) -> None:
        row = self.selected_row()
        if row is None:
            return
        customer = self.services.customers.get(int(row["id"]))
        DetailDialog(
            self, f"Customer - {customer['full_name']}",
            [("Full name", customer["full_name"]),
             ("Contact number", customer["phone"]),
             ("Email", customer["email"] or "-"),
             ("Address", customer["address"] or "-"),
             ("ID type", customer["id_type"]),
             ("ID number", customer["id_number"] or "-"),
             ("License number", customer["license_number"] or "-"),
             ("Total bookings", row.get("bookings_count", 0)),
             ("Archived", "Yes" if customer["is_archived"] else "No"),
             ("Registered", customer["created_at"])],
            notes=customer["notes"])

    def on_archive(self) -> None:
        row = self.selected_row()
        if row is None:
            return
        archived = bool(row["is_archived"])
        label = "restore" if archived else "archive"
        if not confirm(f"Do you want to {label} {row['full_name']}?", self):
            return
        try:
            self.services.customers.set_archived(int(row["id"]), not archived)
        except Exception as exc:
            show_error(str(exc), self)
            return
        self.app.refresh_all()
