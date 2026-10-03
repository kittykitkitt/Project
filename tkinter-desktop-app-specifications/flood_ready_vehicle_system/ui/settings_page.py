"""Settings page: application preferences, data locations and maintenance."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from app.config import (
    APP_VERSION,
    CSV_EXPORT_DIR,
    DATA_DIR,
    IMAGE_DIR,
    LOG_DIR,
    MAP_CACHE_DIR,
    PDF_EXPORT_DIR,
    RISK_LEVELS,
)
from . import Page
from .dialogs import show_info
from .styles import page_header

SETTINGS_FIELDS = [
    ("organisation", "Organisation name"),
    ("currency", "Currency code"),
    ("map_center_latitude", "Map centre latitude"),
    ("map_center_longitude", "Map centre longitude"),
    ("map_zoom", "Map zoom level"),
]

DATA_LOCATIONS = [
    ("Database", DATA_DIR / "rental_system.db"),
    ("Vehicle images", IMAGE_DIR),
    ("PDF exports", PDF_EXPORT_DIR),
    ("CSV exports", CSV_EXPORT_DIR),
    ("Log files", LOG_DIR / "application.log"),
    ("Map tile cache", MAP_CACHE_DIR),
]


class SettingsPage(Page):
    ICON = "⚙"
    TITLE = "Settings"
    SUBTITLE = "Preferences, data locations and backup"

    def build(self) -> None:
        page_header(self, f"{self.ICON}  {self.TITLE}", self.SUBTITLE).pack(fill="x")

        body = ttk.Frame(self, style="Card.TFrame", padding=(16, 14))
        body.pack(fill="x")
        body.columnconfigure(1, weight=1)

        self.vars: dict[str, tk.StringVar] = {}
        for index, (key, label) in enumerate(SETTINGS_FIELDS):
            ttk.Label(body, text=label, style="Field.TLabel").grid(
                row=index, column=0, sticky="w", padx=(0, 14), pady=4)
            var = tk.StringVar()
            ttk.Entry(body, textvariable=var, width=30).grid(
                row=index, column=1, sticky="w")
            self.vars[key] = var

        threshold_row = len(SETTINGS_FIELDS)
        ttk.Label(body, text="Flood alert threshold", style="Field.TLabel").grid(
            row=threshold_row, column=0, sticky="w", padx=(0, 14), pady=4)
        self.threshold_var = tk.StringVar()
        ttk.Combobox(body, textvariable=self.threshold_var, values=RISK_LEVELS,
                     state="readonly", width=14).grid(
            row=threshold_row, column=1, sticky="w")


        actions = ttk.Frame(body, style="Card.TFrame")
        actions.grid(row=threshold_row + 2, column=0, columnspan=2, sticky="w",
                     pady=(14, 0))
        ttk.Button(actions, text="Save settings", style="Primary.TButton",
                   command=self.save).pack(side="left")
        ttk.Button(actions, text="Reload", style="Secondary.TButton",
                   command=self.refresh).pack(side="left", padx=(8, 0))

        info = ttk.Frame(self, style="Card.TFrame", padding=(16, 14))
        info.pack(fill="both", expand=True, pady=(12, 0))
        ttk.Label(info, text="Data locations", style="H2.TLabel").pack(anchor="w")
        for label, path in DATA_LOCATIONS:
            row = ttk.Frame(info, style="Card.TFrame")
            row.pack(fill="x", pady=2)
            ttk.Label(row, text=label, style="Field.TLabel").pack(side="left")
            ttk.Label(row, text=str(path), style="CardMuted.TLabel").pack(
                side="left", padx=(12, 0))
        ttk.Label(info,
                  text=f"Version {APP_VERSION}  \u00b7  data lives in the local "
                       "application data folder, never in the program folder.",
                  style="CardMuted.TLabel").pack(anchor="w", pady=(12, 0))
        maintenance = ttk.Frame(info, style="Card.TFrame")
        maintenance.pack(fill="x", pady=(10, 0))
        ttk.Button(maintenance, text="Open data folder", style="Secondary.TButton",
                   command=self.app.open_data_folder).pack(side="left")
        ttk.Button(maintenance, text="Backup database", style="Secondary.TButton",
                   command=self.app.backup_database).pack(side="left", padx=(8, 0))

    def refresh(self) -> None:
        for key, var in self.vars.items():
            var.set(self.db.setting(key, ""))
        self.threshold_var.set(self.db.setting("alert_threshold", "high"))

    def save(self) -> None:
        for key, var in self.vars.items():
            value = var.get().strip()
            if value:
                self.db.set_setting(key, value)
        self.db.set_setting("alert_threshold", self.threshold_var.get() or "high")
        self.app.status_var.set("Settings saved")
        show_info("Settings were saved. Restart the application for map changes to "
                  "take full effect.", self)
