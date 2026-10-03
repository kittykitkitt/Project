"""Bookings page: rental contracts, status changes and payment recording."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.config import BOOKING_STATUSES, PAYMENT_METHODS, PAYMENT_TYPES
from app.services import ACTIVE_BOOKING_STATUSES
from . import TablePage
from .dialogs import DetailDialog, FormDialog, confirm, show_error, show_info, show_warning
from .styles import money


class BookingsPage(TablePage):
    TITLE = "Bookings"
    SUBTITLE = "Contracts, status flow and payments"
    COLUMNS = [
        ("booking_code", "Code", 115, "w"),
        ("vehicle", "Vehicle", 150, "w"),
        ("customer", "Customer", 170, "w"),
        ("start_date", "Start", 90, "w"),
        ("end_date", "End", 90, "w"),
        ("rental_days", "Days", 50, "center"),
        ("total", "Total", 100, "e"),
        ("paid", "Paid", 100, "e"),
        ("balance", "Balance", 90, "e"),
        ("status", "Status", 95, "w"),
    ]
    FILTERS = [("All statuses", "")] + [(status.title(), status) for status in BOOKING_STATUSES]
    DEFAULT_FILTER = "All statuses"
    SHOW_ARCHIVE = True
    EXTRA_ACTIONS = [("Record payment", "payment"), ("Start rental", "start"),
                     ("Complete", "complete"), ("Cancel", "cancel")]
    TREE_HEIGHT = 15

    # -------------------------------------------------------------------- data
    def load_rows(self) -> list[dict[str, Any]]:
        return self.services.bookings.list_bookings(
            search=self.search_var.get(), status=self.filter_value(),
            include_archived=self.include_archived_var.get())

    def row_values(self, row: dict[str, Any]) -> list[Any]:
        balance = float(row["total_amount"]) - float(row["paid_amount"])
        return [row["booking_code"], f"{row['plate_number']} {row['brand']} {row['model']}",
                row["customer_name"], row["start_date"], row["end_date"], row["rental_days"],
                money(row["total_amount"]), money(row["paid_amount"]), money(balance),
                row["status"]]

    def _vehicle_options(self, include_id: int | None = None) -> list[tuple[str, int]]:
        options: list[tuple[str, int]] = []
        for vehicle in self.services.vehicles.list_vehicles(status="available"):
            options.append((f"{vehicle['plate_number']} - {vehicle['brand']} {vehicle['model']} "
                            f"({money(vehicle['rate_per_day'])}/day)", int(vehicle["id"])))
        if include_id is not None:
            current = self.services.vehicles.get(include_id)
            options.append((f"{current.plate_number} - {current.brand} {current.model} "
                            f"({money(current.rate_per_day)}/day)", current.id))
        return options

    def _customer_options(self, include_id: int | None = None) -> list[tuple[str, int]]:
        options = [(f"{customer['full_name']} - {customer['phone']}", int(customer["id"]))
                   for customer in self.services.customers.list_customers()]
        if include_id is not None:      # keep an archived renter selectable on edit
            current = self.services.customers.get(include_id)
            options.append((f"{current['full_name']} - {current['phone']}",
                            int(current["id"])))
        return options

    def _fields(self, booking: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        booking = booking or {}
        default_start = booking.get("start_date") or date.today().isoformat()
        default_end = booking.get("end_date") or (date.today() + timedelta(days=3)).isoformat()
        vehicle_id = int(booking["vehicle_id"]) if booking.get("vehicle_id") else None
        customer_id = (int(booking["customer_id"])
                       if booking.get("customer_id") else None)
        return [
            {"name": "vehicle_id", "label": "Vehicle", "kind": "combo",
             "options": self._vehicle_options(vehicle_id), "value": vehicle_id},
            {"name": "customer_id", "label": "Customer", "kind": "combo",
             "options": self._customer_options(customer_id), "value": customer_id},
            {"name": "start_date", "label": "Start date", "kind": "entry",
             "value": default_start, "hint": "YYYY-MM-DD"},
            {"name": "end_date", "label": "End date", "kind": "entry",
             "value": default_end, "hint": "YYYY-MM-DD"},
            {"name": "pickup_location", "label": "Pickup location", "kind": "entry",
             "required": False, "value": booking.get("pickup_location", "")},
            {"name": "destination", "label": "Destination", "kind": "entry",
             "required": False, "value": booking.get("destination", "")},
            {"name": "deposit", "label": "Deposit", "kind": "number",
             "value": booking.get("deposit", 0)},
            {"name": "status", "label": "Status", "kind": "combo",
             "options": list(ACTIVE_BOOKING_STATUSES) + ["completed", "cancelled"],
             "value": booking.get("status", "pending")},
            {"name": "notes", "label": "Notes", "kind": "text", "required": False,
             "value": booking.get("notes", "")},
        ]

    # ----------------------------------------------------------------- actions
    def on_add(self) -> None:
        if not self._customer_options():
            show_warning("Add a customer first - every booking needs a renter.", self)
            return
        if not self._vehicle_options():
            show_warning("There is no available vehicle to book. Free a vehicle up or "
                         "add one on the Vehicles page first.", self)
            return
        dialog = FormDialog(self, "New booking", self._fields(), on_save=self._create)
        if dialog.values is None:
            return

    def _create(self, values: dict[str, Any]) -> None:
        booking_id = self.services.bookings.create(
            vehicle_id=int(values["vehicle_id"] or 0),
            customer_id=int(values["customer_id"] or 0),
            start_date=values["start_date"], end_date=values["end_date"],
            pickup_location=values["pickup_location"], destination=values["destination"],
            deposit=values["deposit"], status=values["status"], notes=values["notes"],
            user_id=self.user.id)
        booking = self.services.bookings.list_bookings()[0]
        for row in self.services.bookings.list_bookings():
            if int(row["id"]) == booking_id:
                booking = row
                break
        self.app.refresh_all()
        show_info(
            f"Booking {booking['booking_code']} saved.\n\n"
            f"{booking['rental_days']} day(s) at {money(booking['rate_per_day'])} per day\n"
            f"Contract total: {money(booking['total_amount'])}", self)

    def on_edit(self) -> None:
        row = self.selected_row()
        if row is None:
            return
        current = self.services.bookings.get(int(row["id"]))
        FormDialog(self, f"Edit {row['booking_code']}", self._fields(current),
                   on_save=lambda values: self.services.bookings.update(
                       int(row["id"]), **values))
        self.app.refresh_all()

    def on_view(self) -> None:
        row = self.selected_row()
        if row is None:
            return
        booking = self.services.bookings.get(int(row["id"]))
        balance = float(booking["total_amount"]) - float(booking["paid_amount"])
        DetailDialog(
            self, f"Booking {booking['booking_code']}",
            [("Booking code", booking["booking_code"]),
             ("Vehicle", f"{booking['plate_number']} {booking['brand']} {booking['model']}"),
             ("Customer", booking["customer_name"]),
             ("Contact", booking["customer_phone"] or "-"),
             ("Start date", booking["start_date"]), ("End date", booking["end_date"]),
             ("Rental days", booking["rental_days"]),
             ("Rate per day", money(booking["rate_per_day"])),
             ("Contract total", money(booking["total_amount"])),
             ("Deposit", money(booking["deposit"])),
             ("Amount paid", money(booking["paid_amount"])),
             ("Balance", money(balance)),
             ("Pickup location", booking["pickup_location"] or "-"),
             ("Destination", booking["destination"] or "-"),
             ("Status", booking["status"]),
             ("Archived", "Yes" if booking["is_archived"] else "No"),
             ("Created", booking["created_at"])],
            notes=booking["notes"])

    def on_archive(self) -> None:
        row = self.selected_row()
        if row is None:
            return
        archived = bool(row["is_archived"])
        label = "restore" if archived else "archive"
        if not confirm(f"Do you want to {label} booking {row['booking_code']}?", self):
            return
        self.services.bookings.set_archived(int(row["id"]), not archived)
        self.app.refresh_all()

    def on_payment(self) -> None:
        row = self.selected_row()
        if row is None:
            return
        balance = round(float(row["total_amount"]) - float(row["paid_amount"]), 2)
        dialog = FormDialog(
            self, f"Record payment - {row['booking_code']}",
            [{"name": "amount", "label": "Amount", "kind": "number",
              "value": max(0.0, balance), "hint": f"Outstanding balance: {money(balance)}"},
             {"name": "method", "label": "Method", "kind": "combo",
              "options": PAYMENT_METHODS, "value": "cash"},
             {"name": "entry_type", "label": "Entry type", "kind": "combo",
              "options": PAYMENT_TYPES, "value": "payment"},
             {"name": "notes", "label": "Notes", "kind": "text", "required": False}],
            columns=2, ok_text="Save payment",
            on_save=lambda values: self.services.transactions.record_payment(
                booking_id=int(row["id"]), amount=values["amount"],
                method=values["method"], entry_type=values["entry_type"],
                notes=values["notes"], user_id=self.user.id))
        if dialog.values is None:
            return
        self.app.refresh_all()

    def _change_status(self, status: str, question: str) -> None:
        row = self.selected_row()
        if row is None:
            return
        if not confirm(question.format(code=row["booking_code"]), self):
            return
        try:
            self.services.bookings.set_status(int(row["id"]), status, self.user.id)
        except Exception as exc:
            show_error(str(exc), self)
            return
        self.app.refresh_all()

    def on_start(self) -> None:
        self._change_status("ongoing", "Mark {code} as ongoing (hand over the vehicle)?")

    def on_complete(self) -> None:
        self._change_status("completed", "Complete {code} and return the vehicle to the fleet?")

    def on_cancel(self) -> None:
        self._change_status("cancelled", "Cancel {code}? The vehicle will be released.")
