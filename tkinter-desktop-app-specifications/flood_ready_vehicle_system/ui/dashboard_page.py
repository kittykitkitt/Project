"""Dashboard: fleet, rental and flood-risk overview with an inline chart."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from app.config import RISK_LEVELS
from . import Page
from .dialogs import show_error
from .styles import PALETTE, RISK_COLORS, make_treeview, money, page_header

CARDS: list[tuple[str, str, str, str]] = [
    ("available", "\U0001f699", "Available", "#15803d"),
    ("rented", "\U0001f697", "Rented", "#2563eb"),
    ("maintenance", "\U0001f527", "Maintenance", "#b06a00"),
    ("bookings_active", "\U0001f4c6", "Active bookings", "#12293f"),
    ("revenue_month", "\U0001f4b0", "Revenue (month)", "#15803d"),
    ("open_alerts", "\u26a0", "Open alerts", "#b3261e"),
]
CHART_HEIGHT = 168


class DashboardPage(Page):
    TITLE = "Dashboard"
    SUBTITLE = "Fleet, rentals and flood risk at a glance"
    ICON = "\u2302"

    def build(self) -> None:
        page_header(self, f"{self.ICON}  {self.TITLE}", self.SUBTITLE).pack(fill="x")

        # ---- summary cards
        cards = ttk.Frame(self, style="Card.TFrame", padding=(16, 14))
        cards.pack(fill="x")
        self.card_vars: dict[str, tk.StringVar] = {}
        for index, (key, icon, label, colour) in enumerate(CARDS):
            cards.columnconfigure(index, weight=1, uniform="cards")
            card = ttk.Frame(cards, style="Card.TFrame")
            card.grid(row=0, column=index, sticky="nsew",
                      padx=(0 if index == 0 else 8, 0))
            head = ttk.Frame(card, style="Card.TFrame")
            head.pack(anchor="w", fill="x")
            ttk.Label(head, text=icon, style="Card.TLabel",
                      font=("Segoe UI", 14)).pack(side="left")
            ttk.Label(head, text=label.upper(), style="CardMuted.TLabel",
                      font=("Segoe UI", 8, "bold")).pack(side="left", padx=(7, 0),
                                                         pady=(6, 0))
            var = tk.StringVar(value="-")
            self.card_vars[key] = var
            ttk.Label(card, textvariable=var, style="Card.TLabel",
                      font=("Segoe UI", 19, "bold"),
                      foreground=colour).pack(anchor="w", pady=(4, 0))

        # ---- main body: returns table | revenue chart + risk chips
        body = ttk.Frame(self, style="Card.TFrame", padding=(16, 12))
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=3, uniform="dash")
        body.columnconfigure(1, weight=2, uniform="dash")
        body.rowconfigure(1, weight=1)

        returns_panel = ttk.Labelframe(body, text="  Due back (7 days)  ",
                                       padding=(10, 8))
        returns_panel.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=(0, 12))
        returns_frame, self.returns_tree = make_treeview(
            returns_panel,
            [("code", "Booking", 105, "w"), ("vehicle", "Vehicle", 110, "w"),
             ("customer", "Customer", 165, "w"), ("end_date", "Due back", 95, "w"),
             ("total", "Contract", 100, "e"), ("status", "Status", 90, "w")],
            height=11)
        returns_frame.pack(fill="both", expand=True)

        chart_panel = ttk.Labelframe(body, text="  Net collections (6 months)  ",
                                     padding=(10, 8))
        chart_panel.grid(row=0, column=1, sticky="ew")
        self.chart = tk.Canvas(chart_panel, height=CHART_HEIGHT,
                               background=PALETTE["card"], highlightthickness=0)
        self.chart.pack(fill="both", expand=True)
        self.chart.bind("<Configure>", lambda _event: self._draw_chart())

        risk_panel = ttk.Labelframe(body, text="  Fleet risk  ", padding=(10, 8))
        risk_panel.grid(row=1, column=1, sticky="nsew", pady=(12, 0))
        self.risk_vars: dict[str, tk.StringVar] = {}
        chip_row = ttk.Frame(risk_panel, style="Card.TFrame")
        chip_row.pack(anchor="w")
        for level in (*RISK_LEVELS, "unknown"):
            chip = ttk.Frame(chip_row, style="Card.TFrame")
            chip.pack(side="left", padx=(0, 12))
            var = tk.StringVar(value="0")
            self.risk_vars[level] = var
            tk.Label(chip, text="\u25cf", background=PALETTE["card"],
                     foreground=RISK_COLORS.get(level, PALETTE["muted"]),
                     font=("Segoe UI", 15, "bold")).pack(side="left")
            ttk.Label(chip, textvariable=var, style="Value.TLabel",
                      font=("Segoe UI", 15, "bold")).pack(side="left", padx=(4, 4))
            ttk.Label(chip, text=level.title(),
                      style="CardMuted.TLabel").pack(side="left")


        # ---- alerts + quick actions
        alerts_panel = ttk.Labelframe(self, text="  Latest alerts  ",
                                      padding=(10, 8))
        alerts_panel.pack(fill="both", expand=True, pady=(12, 0))
        alerts_frame, self.alerts_tree = make_treeview(
            alerts_panel,
            [("created", "Created", 95, "w"), ("title", "Alert", 250, "w"),
             ("vehicle", "Vehicle", 90, "w"), ("status", "Status", 100, "w")],
            height=6)
        alerts_frame.pack(fill="both", expand=True)

        footer = ttk.Frame(self, style="Card.TFrame", padding=(16, 10))
        footer.pack(fill="x")
        ttk.Button(footer, text="New booking", style="Primary.TButton",
                   command=lambda: self.app.show_page("bookings")).pack(side="left")
        ttk.Button(footer, text="Run flood risk scan", style="Secondary.TButton",
                   command=self.run_scan).pack(side="left", padx=(8, 0))
        ttk.Button(footer, text="Open GPS map", style="Secondary.TButton",
                   command=lambda: self.app.show_page("gps")).pack(side="left", padx=(8, 0))
        ttk.Button(footer, text="Reports", style="Secondary.TButton",
                   command=lambda: self.app.show_page("reports")).pack(side="left")
        self.summary_var = tk.StringVar(value="")
        ttk.Label(footer, textvariable=self.summary_var,
                  style="CardMuted.TLabel").pack(side="right")

    # -------------------------------------------------------------------- data
    def refresh(self) -> None:
        try:
            summary = self.services.dashboard.summary()
            distribution = self.services.dashboard.risk_distribution()
            self.revenue_months = self.services.dashboard.revenue_by_month(6)
        except Exception:
            show_error("The dashboard summary could not be loaded.", self)
            return

        self.card_vars["available"].set(str(summary["vehicles"]["available"]))
        self.card_vars["rented"].set(str(summary["vehicles"]["rented"]))
        self.card_vars["maintenance"].set(str(summary["vehicles"]["maintenance"]))
        self.card_vars["bookings_active"].set(str(summary["bookings_active"]))
        self.card_vars["revenue_month"].set(money(summary["revenue_month"]))
        self.card_vars["open_alerts"].set(str(summary["open_alerts"]))
        for level, var in self.risk_vars.items():
            var.set(str(distribution.get(level, 0)))

        self.returns_tree.delete(*self.returns_tree.get_children())
        for index, row in enumerate(self.services.dashboard.bookings.upcoming_returns(7, 12)):
            self.returns_tree.insert(
                "", "end", tags=[str(row["status"]), "stripe" if index % 2 else ""],
                values=[row["booking_code"], row["plate_number"], row["customer_name"],
                        row["end_date"], money(row["total_amount"]), row["status"]])

        self.alerts_tree.delete(*self.alerts_tree.get_children())
        for index, row in enumerate(self.services.alerts.list_alerts(limit=12)):
            self.alerts_tree.insert(
                "", "end",
                tags=[str(row["severity"]), "stripe" if index % 2 else ""],
                values=[str(row["created_at"])[:16], row["title"],
                        row["plate_number"] or "-", row["status"]])

        self.summary_var.set(
            f"{summary['vehicles']['total']} vehicles  \u2022  "
            f"{summary['customers']} customers  \u2022  "
            f"{summary['high_risk_vehicles']} at high risk")
        self._draw_chart()

    # ------------------------------------------------------------------- chart
    def _draw_chart(self) -> None:
        """Dependency free bar chart of the last months' net collections."""
        canvas = self.chart
        canvas.delete("all")
        width = max(int(canvas.winfo_width() or 0), 240)
        data = getattr(self, "revenue_months", [])
        top_gap, base_gap = 22, 26
        chart_height = CHART_HEIGHT - top_gap - base_gap

        if not data or all(float(row["net"]) == 0 for row in data):
            canvas.create_text(width // 2, CHART_HEIGHT // 2,
                               text="No payments recorded yet",
                               font=("Segoe UI", 10), fill=PALETTE["muted"])
            return

        highest = max(float(row["net"]) for row in data) or 1.0
        slot = max(28, (width - 16) // len(data))
        bar_width = max(10, slot - 12)
        for index, row in enumerate(data):
            value = float(row["net"])
            bar_height = int(chart_height * (value / highest))
            x0 = 8 + index * slot
            y0 = top_gap + chart_height - bar_height
            canvas.create_rectangle(x0, y0, x0 + bar_width, top_gap + chart_height,
                                    fill=PALETTE["chart"], outline="")
            canvas.create_text(x0 + bar_width // 2, y0 - 9,
                               text=f"{value:,.0f}",
                               font=("Segoe UI", 8, "bold"),
                               fill=PALETTE["sidebar"])
            canvas.create_text(x0 + bar_width // 2, CHART_HEIGHT - base_gap + 11,
                               text=str(row["month"])[5:], font=("Segoe UI", 8),
                               fill=PALETTE["muted"])

    # ----------------------------------------------------------------- actions
    def run_scan(self) -> None:
        try:
            created = self.services.alerts.generate_flood_alerts(self.user.id)
        except Exception as exc:
            show_error(f"The flood risk scan failed: {exc}", self)
            return
        self.app.refresh_all()
        self.app.status_var.set(f"Flood risk scan complete - {created} new alert(s)")
