"""Main application window: grouped sidebar navigation, status bar and menus."""
from __future__ import annotations

import logging
import os
import threading
import time
import tkinter as tk
from functools import partial
from tkinter import filedialog, messagebox, ttk
from typing import TYPE_CHECKING, Any

from app import AppError
from app.config import (
    APP_NAME,
    APP_VERSION,
    CSV_EXPORT_DIR,
    DATA_DIR,
    PDF_EXPORT_DIR,
    asset_path,
    local_app_data_root,
)
from app.database import DatabaseManager
from app.services import (
    AlertService,
    AuthService,
    BookingService,
    CustomerService,
    DashboardService,
    FloodZoneService,
    ReportService,
    TransactionService,
    VehicleService,
)
from app.tracking import TrackingService
from . import Page
from .login_window import LoginWindow
from .styles import PALETTE, apply_theme

if TYPE_CHECKING:  # pragma: no cover
    from app.models import User

log = logging.getLogger(__name__)


def page_classes() -> list[tuple[str, str, str, Any]]:
    """Navigation registry: (key, title, icon, page class)."""
    from .alerts_page import AlertsPage
    from .bookings_page import BookingsPage
    from .customers_page import CustomersPage
    from .dashboard_page import DashboardPage
    from .flood_zones_page import FloodZonesPage
    from .gps_map_page import GpsMapPage
    from .reports_page import ReportsPage
    from .settings_page import SettingsPage
    from .transactions_page import TransactionsPage
    from .users_page import UsersPage
    from .vehicles_page import VehiclesPage

    return [
        ("dashboard", "Dashboard", "\u2302", DashboardPage),
        ("bookings", "Bookings", "\u25a6", BookingsPage),
        ("customers", "Customers", "\u263a", CustomersPage),
        ("vehicles", "Vehicles", "\u25a4", VehiclesPage),
        ("transactions", "Transactions", "\u20b1", TransactionsPage),
        ("gps", "GPS Map", "\u25c9", GpsMapPage),
        ("flood_zones", "Flood Zones", "\u26c8", FloodZonesPage),
        ("alerts", "Alerts", "\u26a0", AlertsPage),
        ("reports", "Reports", "\u2261", ReportsPage),
        ("users", "Users", "\u25b8", UsersPage),
        ("settings", "Settings", "\u2699", SettingsPage),
    ]


# Sidebar grouping: (section title, navigation keys)
NAV_SECTIONS: list[tuple[str, tuple[str, ...]]] = [
    ("Operations", ("dashboard", "bookings", "customers", "vehicles", "transactions")),
    ("Monitoring", ("gps", "flood_zones", "alerts")),
    ("Administration", ("reports", "users", "settings")),
]


class Services:
    """One instance of every service, all sharing the same DatabaseManager."""

    def __init__(self, db: DatabaseManager) -> None:
        self.db = db
        self.auth = AuthService(db)
        self.vehicles = VehicleService(db)
        self.customers = CustomerService(db)
        self.bookings = BookingService(db)
        self.transactions = TransactionService(db)
        self.zones = FloodZoneService(db)
        self.alerts = AlertService(db)
        self.dashboard = DashboardService(db)
        self.reports = ReportService(db)
        self.tracking = TrackingService(db)


class MainWindow:
    """Builds and controls the main window; pages are created lazily."""

    def __init__(self, root: tk.Tk, db: DatabaseManager, user: "User") -> None:
        self.root = root
        self.db = db
        self.user = user
        self.services = Services(db)
        self.registry = page_classes()
        for _key, _title, icon, page_class in self.registry:
            page_class.ICON = icon          # one icon per page, header + sidebar
        self.pages: dict[str, Page] = {}
        self.nav_buttons: dict[str, ttk.Button] = {}
        self.sidebar: ttk.Frame | None = None
        self.current = ""
        self.online_var = tk.StringVar(value="Checking internet...")
        self.status_var = tk.StringVar(value="Ready")
        self._last_net_check = 0.0

        apply_theme(root)
        root.title(f"{APP_NAME} {APP_VERSION}")
        root.geometry("1280x780")
        root.minsize(1080, 680)
        root.report_callback_exception = self._report_exception
        self._set_icon(root)

        self.body = tk.Frame(root, background=PALETTE["bg"])
        self.body.pack(fill="both", expand=True)
        self.body.columnconfigure(1, weight=1)
        self.body.rowconfigure(0, weight=1)

        self.content = tk.Frame(self.body, background=PALETTE["bg"])
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.columnconfigure(0, weight=1)
        self.content.rowconfigure(0, weight=1)

        self._build_sidebar()
        self._build_statusbar()
        self._build_menu()
        self.check_internet_async(force=True)
        self.show_page("dashboard")

    # ------------------------------------------------------------- composition
    def _set_icon(self, root: tk.Tk) -> None:
        try:
            icon_path = asset_path("icons", "app_icon.png")
            if icon_path.exists():
                root.iconphoto(True, tk.PhotoImage(file=str(icon_path)))
        except tk.TclError:  # pragma: no cover - the icon is cosmetic
            log.info("Application icon could not be loaded")

    def _build_sidebar(self) -> None:
        if self.sidebar is not None:
            self.sidebar.destroy()
            self.nav_buttons = {}
        sidebar = ttk.Frame(self.body, style="Sidebar.TFrame", padding=(14, 18, 14, 14))
        sidebar.grid(row=0, column=0, sticky="nsw")
        self.sidebar = sidebar

        # ---- brand
        brand = ttk.Frame(sidebar, style="Sidebar.TFrame")
        brand.pack(fill="x", pady=(0, 16))
        ttk.Label(brand, text="\u26c8", style="SidebarTitle.TLabel",
                  font=("Segoe UI", 20, "bold")).pack(side="left")
        titles = ttk.Frame(brand, style="Sidebar.TFrame")
        titles.pack(side="left", padx=(10, 0))
        ttk.Label(titles, text="Flood Ready", style="SidebarTitle.TLabel").pack(anchor="w")
        ttk.Label(titles, text="Vehicle System", style="Sidebar.TLabel").pack(anchor="w")

        # ---- signed in card
        user_card = ttk.Frame(sidebar, style="SidebarSoft.TFrame", padding=(12, 10))
        user_card.pack(fill="x", pady=(0, 14))
        ttk.Label(user_card, text=self.user.full_name,
                  style="SidebarUser.TLabel", wraplength=170).pack(anchor="w")
        self.user_label = ttk.Label(user_card, text=self.user.role.upper(),
                                    style="SidebarUserRole.TLabel")
        self.user_label.pack(anchor="w")

        # ---- navigation sections
        known = {item[0] for item in self.registry}
        for section, keys in NAV_SECTIONS:
            ttk.Label(sidebar, text=section.upper(),
                      style="SidebarSection.TLabel").pack(anchor="w", padx=4, pady=(8, 4))
            for key in keys:
                if key not in known:
                    continue
                if key == "users" and not self.user.is_admin:
                    continue
                entry = next(item for item in self.registry if item[0] == key)
                button = ttk.Button(
                    sidebar, text=f"{entry[2]}   {entry[1]}", style="Sidebar.TButton",
                    command=partial(self.show_page, key))
                button.pack(fill="x", pady=1)
                self.nav_buttons[key] = button

        spacer = ttk.Frame(sidebar, style="Sidebar.TFrame")
        spacer.pack(fill="both", expand=True)
        ttk.Button(sidebar, text="\u23fb   Sign out", style="SidebarSignOut.TButton",
                   command=self.logout).pack(fill="x", pady=(8, 0))

    def _build_statusbar(self) -> None:
        bar = ttk.Frame(self.root, style="Card.TFrame", padding=(14, 6))
        bar.pack(fill="x", side="bottom")
        ttk.Label(bar, textvariable=self.status_var, style="Status.TLabel").pack(side="left")
        ttk.Label(bar, text=f"Database: {DATA_DIR}", style="Status.TLabel").pack(
            side="right", padx=(18, 0))
        self.online_dot = tk.Label(bar, text="\u25cf", background=PALETTE["card"],
                                   foreground=PALETTE["muted"], font=("Segoe UI", 11, "bold"))
        self.online_dot.pack(side="right")
        ttk.Label(bar, textvariable=self.online_var, style="Status.TLabel").pack(
            side="right", padx=(6, 4))

    def _build_menu(self) -> None:
        menu = tk.Menu(self.root)
        file_menu = tk.Menu(menu, tearoff=0)
        file_menu.add_command(label="Backup database...", command=self.backup_database)
        file_menu.add_command(label="Open data folder", command=self.open_data_folder)
        file_menu.add_separator()
        file_menu.add_command(label="Sign out", command=self.logout)
        file_menu.add_command(label="Exit", command=self.root.destroy)
        menu.add_cascade(label="File", menu=file_menu)
        help_menu = tk.Menu(menu, tearoff=0)
        help_menu.add_command(label="About", command=self.show_about)
        menu.add_cascade(label="Help", menu=help_menu)
        self.root.config(menu=menu)

    # ------------------------------------------------------------------ pages
    def show_page(self, key: str) -> None:
        entry = next((item for item in self.registry if item[0] == key), None)
        if entry is None:
            return
        page = self.pages.get(key)
        if page is None:
            page = entry[3](self.content, self)
            page.grid(row=0, column=0, sticky="nsew")
            self.pages[key] = page
        for name, existing in self.pages.items():
            if name == key:
                existing.grid()
                existing.on_show()
            else:
                existing.grid_forget()
        self.current = key
        for name, button in self.nav_buttons.items():
            button.configure(style="SidebarActive.TButton" if name == key
                             else "Sidebar.TButton")
        self.status_var.set(f"{entry[1]}  \u2022  signed in as {self.user.username}")

    def refresh_all(self) -> None:
        for page in self.pages.values():
            if not page.is_built:
                continue
            try:
                page.refresh()
            except Exception:  # pragma: no cover - keep the other pages alive
                log.exception("Could not refresh page %s", page.TITLE)
        self.check_internet_async()

    # ---------------------------------------------------------------- actions
    def backup_database(self) -> None:
        from datetime import datetime

        target = filedialog.asksaveasfilename(
            parent=self.root, title="Backup database", defaultextension=".db",
            initialfile=f"rental_system_backup_{datetime.now():%Y%m%d_%H%M%S}.db",
            filetypes=[("SQLite database", "*.db"), ("All files", "*.*")])
        if not target:
            return
        try:
            destination = self.db.backup_to(target)
        except AppError as exc:
            messagebox.showerror(APP_NAME, str(exc), parent=self.root)
            return
        messagebox.showinfo(APP_NAME, f"Backup saved to:\n{destination}",
                            parent=self.root)

    def open_data_folder(self) -> None:
        folder = local_app_data_root()
        try:
            folder.mkdir(parents=True, exist_ok=True)
            if os.name == "nt":
                os.startfile(str(folder))  # type: ignore[attr-defined]
            else:
                import subprocess

                subprocess.run(["xdg-open", str(folder)], check=False)
        except Exception:  # pragma: no cover - platform specific
            messagebox.showinfo(APP_NAME, f"Application data folder:\n{folder}",
                                parent=self.root)

    def show_about(self) -> None:
        messagebox.showinfo(
            "About",
            f"{APP_NAME} {APP_VERSION}\n\n"
            "Rental operations with flood-risk monitoring for Windows 10 and 11.\n"
            f"Data folder: {local_app_data_root()}\n"
            f"PDF exports: {PDF_EXPORT_DIR}\n"
            f"CSV exports: {CSV_EXPORT_DIR}",
            parent=self.root)

    def logout(self) -> None:
        if not messagebox.askyesno("Sign out",
                                   "Sign out and return to the login screen?",
                                   parent=self.root):
            return
        self.root.withdraw()
        login = LoginWindow(self.root, self.services.auth)
        self.root.wait_window(login)
        if login.user is None:
            self.root.destroy()
            return
        self.user = login.user
        for child in self.content.winfo_children():
            child.destroy()
        self.pages = {}
        self._build_sidebar()
        self.root.deiconify()
        self.show_page("dashboard")
        self.check_internet_async(force=True)

    # -------------------------------------------------------------- connectivity
    def check_internet_async(self, force: bool = False) -> None:
        """Update the status bar; throttled so pages do not spam the network."""
        now = time.monotonic()
        if not force and now - self._last_net_check < 30:
            return
        self._last_net_check = now

        def worker() -> None:
            from .gps_map_page import check_internet

            online = check_internet()
            text = ("Internet: available (map tiles enabled)" if online
                    else "Internet: offline (records still work)")
            colour = PALETTE["ok"] if online else PALETTE["danger"]

            def apply() -> None:
                self.online_var.set(text)
                self.online_dot.configure(foreground=colour)

            try:
                self.root.after(0, apply)
            except Exception:  # pragma: no cover - window already closed
                log.debug("Status update skipped: %s", text)

        threading.Thread(target=worker, daemon=True).start()

    def _report_exception(self, exc_type: Any, exc_value: Any,
                          exc_traceback: Any) -> None:
        log.exception("Unhandled interface error",
                      exc_info=(exc_type, exc_value, exc_traceback))
        try:
            messagebox.showerror(
                APP_NAME,
                "An unexpected problem occurred and the action was cancelled.\n"
                "Technical details were written to the log file.\n\n"
                f"({exc_value})",
                parent=self.root)
        except Exception:  # pragma: no cover - no window left
            pass
