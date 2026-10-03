"""Reports page: preview any report on screen, then export it to PDF or CSV."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from app import AppError
from app.config import CSV_EXPORT_DIR, PDF_EXPORT_DIR, unique_path
from app.models import ReportData
from . import Page
from .dialogs import show_error, show_info
from reports import csv_exporter, pdf_exporter
from .styles import make_treeview, page_header

REPORTS = [
    ("Vehicle inventory", "vehicle_report", False, False),
    ("Bookings", "booking_report", True, True),
    ("Transactions / revenue", "transaction_report", True, False),
    ("Customers", "customer_report", False, False),
    ("Flood risk assessment", "flood_risk_report", False, False),
    ("Flood zones", "zone_report", False, False),
]


class ReportsPage(Page):
    ICON = "≡"
    TITLE = "Reports"
    SUBTITLE = "Preview and export to PDF or CSV"

    def build(self) -> None:
        page_header(self, f"{self.ICON}  {self.TITLE}", self.SUBTITLE).pack(fill="x")

        bar = ttk.Frame(self, style="Card.TFrame", padding=(16, 12))
        bar.pack(fill="x")
        self.report_var = tk.StringVar(value=REPORTS[0][0])
        box = ttk.Combobox(bar, textvariable=self.report_var, state="readonly",
                           width=26, values=[name for name, *_rest in REPORTS])
        box.pack(side="left")
        box.bind("<<ComboboxSelected>>", lambda _event: self.refresh())
        ttk.Label(bar, text="From", style="CardMuted.TLabel").pack(side="left",
                                                                   padx=(14, 4))
        self.from_var = tk.StringVar(value="")
        ttk.Entry(bar, textvariable=self.from_var, width=11).pack(side="left")
        ttk.Label(bar, text="To", style="CardMuted.TLabel").pack(side="left",
                                                                 padx=(6, 4))
        self.to_var = tk.StringVar(value="")
        ttk.Entry(bar, textvariable=self.to_var, width=11).pack(side="left", padx=(6, 14))
        self.include_archived_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar, text="Include archived",
                        variable=self.include_archived_var,
                        command=self.refresh).pack(side="left", padx=(14, 0))
        ttk.Button(bar, text="Preview", style="Primary.TButton",
                   command=self.refresh).pack(side="left", padx=(14, 0))

        body = ttk.Frame(self, style="Card.TFrame", padding=(16, 12))
        body.pack(fill="both", expand=True, pady=(12, 0))
        self.title_var = tk.StringVar(value="Select a report")
        ttk.Label(body, textvariable=self.title_var, style="H2.TLabel").pack(anchor="w")
        self.summary_var = tk.StringVar(value="")
        ttk.Label(body, textvariable=self.summary_var, style="CardMuted.TLabel",
                  wraplength=900, justify="left").pack(anchor="w", pady=(2, 8))
        self.table_container = ttk.Frame(body, style="Card.TFrame")
        self.table_container.pack(fill="both", expand=True)

        footer = ttk.Frame(self, style="Card.TFrame", padding=(16, 10))
        footer.pack(fill="x")
        self.count_var = tk.StringVar(value="")
        ttk.Label(footer, textvariable=self.count_var, style="CardMuted.TLabel").pack(side="left")

        ttk.Button(footer, text="Export PDF", style="Primary.TButton",
                   command=self.export_pdf).pack(side="right")
        ttk.Button(footer, text="Export CSV", style="Secondary.TButton",
                   command=self.export_csv).pack(side="right", padx=(0, 8))
        self.current: ReportData | None = None
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

    # -------------------------------------------------------------------- data
    def _report_data(self) -> ReportData:
        selected = next((entry for entry in REPORTS if entry[0] == self.report_var.get()),
                        REPORTS[0])
        _name, method, uses_dates, uses_archive = selected
        builder = getattr(self.services.reports, method)
        if uses_dates and uses_archive:
            return builder(self.from_var.get(), self.to_var.get(),
                           self.include_archived_var.get())
        if uses_dates:
            return builder(self.from_var.get(), self.to_var.get())
        if uses_archive:
            return builder(self.include_archived_var.get())
        return builder()

    def refresh(self) -> None:
        try:
            report = self._report_data()
        except AppError as exc:
            show_error(str(exc), self)
            return
        except Exception:
            show_error("The report could not be generated. See the log file.", self)
            return
        self.current = report
        self.title_var.set(f"{report.title} - {report.subtitle}")
        self.summary_var.set("   |   ".join(report.summary))
        self.count_var.set(f"{len(report.rows)} row(s)")
        for child in self.table_container.winfo_children():
            child.destroy()
        columns = [(f"col{index}", str(column), 130, "w")
                   for index, column in enumerate(report.columns)]
        _frame, tree = make_treeview(self.table_container, columns, height=17)
        _frame.pack(fill="both", expand=True)
        for row in report.rows:
            tree.insert("", "end", values=["" if value is None else str(value) for value in row])

    # ----------------------------------------------------------------- exports
    def export_pdf(self) -> None:
        report = self._require_report()
        if report is None:
            return
        target = unique_path(PDF_EXPORT_DIR, slug(report.title), ".pdf")
        try:
            path = pdf_exporter.export_report(report, target)
        except AppError as exc:
            show_error(str(exc), self)
            return
        show_info(f"PDF report saved to:\n{path}", self)

    def export_csv(self) -> None:
        report = self._require_report()
        if report is None:
            return
        target = unique_path(CSV_EXPORT_DIR, slug(report.title), ".csv")
        try:
            path = csv_exporter.export_report(report, target)
        except AppError as exc:
            show_error(str(exc), self)
            return
        show_info(f"CSV report saved to:\n{path}", self)

    def _require_report(self) -> ReportData | None:
        if self.current is None or self.title_var.get().startswith(self.current.title):
            try:
                self.current = self._report_data()
            except AppError as exc:
                show_error(str(exc), self)
                return None
            except Exception:
                show_error("The report could not be generated. See the log file.", self)
                return None
        return self.current


def slug(text: str) -> str:
    return "".join(character if character.isalnum() else "_"
                   for character in text.strip().lower()).strip("_")[:40]
