"""Transactions page: payments, deposits and refunds."""
from __future__ import annotations

from typing import Any

from app.config import PAYMENT_TYPES
from . import TablePage
from .dialogs import DetailDialog, confirm, show_error
from .styles import money


class TransactionsPage(TablePage):
    TITLE = "Transactions"
    SUBTITLE = "Payments, deposits and refunds"
    COLUMNS = [
        ("reference", "Reference", 100, "w"),
        ("paid_at", "Paid at", 140, "w"),
        ("booking_code", "Booking", 110, "w"),
        ("plate_number", "Vehicle", 100, "w"),
        ("customer_name", "Customer", 170, "w"),
        ("entry_type", "Type", 90, "w"),
        ("method", "Method", 120, "w"),
        ("amount", "Amount", 100, "e"),
        ("recorded_by_name", "Recorded by", 110, "w"),
    ]
    FILTERS = [("All types", "")] + [(kind.title(), kind) for kind in PAYMENT_TYPES]
    DEFAULT_FILTER = "All types"
    SHOW_DATE_RANGE = True
    SHOW_DELETE = True
    TREE_HEIGHT = 17

    def load_rows(self) -> list[dict[str, Any]]:
        start, end = self.date_range()
        rows = self.services.transactions.list_transactions(
            search=self.search_var.get(), start=start, end=end)
        entry_type = self.filter_value()
        return [row for row in rows if not entry_type or row["entry_type"] == entry_type]

    def row_values(self, row: dict[str, Any]) -> list[Any]:
        return [row["reference"], row["paid_at"], row["booking_code"] or "-",
                row["plate_number"] or "-", row["customer_name"] or "-",
                row["entry_type"], row["method"], money(row["amount"]),
                row["recorded_by_name"] or "-"]

    def row_tags(self, row: dict[str, Any]) -> list[str]:
        return [str(row["entry_type"])]

    def refresh(self) -> None:
        super().refresh()
        start, end = self.date_range()
        totals = self.services.transactions.totals(start=start, end=end)
        self.count_var.set(
            f"{totals['entries']} entries | net {money(totals['net'])} | "
            f"refunds {money(totals['refunds'])}")

    def on_view(self) -> None:
        row = self.selected_row()
        if row is None:
            return
        DetailDialog(
            self, f"Transaction {row['reference']}",
            [("Reference", row["reference"]),
             ("Paid at", row["paid_at"]),
             ("Booking", row["booking_code"] or "-"),
             ("Vehicle", row["plate_number"] or "-"),
             ("Customer", row["customer_name"] or "-"),
             ("Entry type", row["entry_type"]),
             ("Method", row["method"]),
             ("Amount", money(row["amount"])),
             ("Recorded by", row["recorded_by_name"] or "-"),
             ("Notes", row["notes"] or "-")])

    def on_delete(self) -> None:
        row = self.selected_row()
        if row is None:
            return
        if not confirm(f"Delete transaction {row['reference']}? This cannot be undone.", self):
            return
        try:
            self.services.transactions.delete(int(row["id"]))
        except Exception as exc:
            show_error(str(exc), self)
            return
        self.app.refresh_all()
