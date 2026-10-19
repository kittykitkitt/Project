#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Flood Ready Vehicle System — vehicle rental with flood-risk monitoring.

Launch:

    python main.py

Everything is standard library: Tkinter for the interface, SQLite for storage.
No third-party packages, no network required, no web server. Data lives in a
folder inside your own user profile (or beside this file when run portably).
"""

from __future__ import annotations

import csv
import hashlib
import hmac
import logging
import math
import os
import secrets
import sqlite3
import sys
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
import tkinter as tk
import tkinter.font as tkfont
from typing import Any, Callable, Iterator, Sequence

# ---------------------------------------------------------------------------
# Application constants
# ---------------------------------------------------------------------------

APP_NAME = "Flood Ready Vehicle System"
APP_SHORT_NAME = "FloodReadyVehicleSystem"
APP_VERSION = "2.6.0"

CURRENCY_SYMBOL = "₱"
DATE_FORMAT = "%Y-%m-%d"
DATETIME_FORMAT = "%Y-%m-%d %H:%M"

VEHICLE_CATEGORIES = ["Sedan", "SUV", "Van", "Pickup", "AUV", "Motorcycle", "Truck", "Boat"]
VEHICLE_STATUSES = ["available", "rented", "maintenance"]
BOOKING_STATUSES = ["pending", "confirmed", "ongoing", "completed", "cancelled"]
PAYMENT_METHODS = ["cash", "card", "bank transfer", "mobile wallet"]
PAYMENT_TYPES = ["payment", "deposit", "refund"]
USER_ROLES = ["admin", "manager", "staff"]
RISK_LEVELS = ["low", "moderate", "high", "severe"]
ID_TYPES = ["Drivers License", "Passport", "UMID", "PhilID", "Company ID", "Barangay ID"]
ALERT_SEVERITIES = ["info", "warning", "critical"]
ALERT_STATUSES = ["new", "acknowledged", "resolved"]

DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "admin123"
DEFAULT_ADMIN_NAME = "System Administrator"

# ---------------------------------------------------------------------------
# Palette — deep evergreen sidebar, cool mist canvas, emerald accent
# ---------------------------------------------------------------------------

PALETTE: dict[str, str] = {
    "bg": "#F3F5F6",
    "surface": "#FFFFFF",
    "line": "#E3E8EB",
    "line_soft": "#EEF1F3",
    "sunken": "#F5F7F8",
    "ink": "#0F1720",
    "ink_soft": "#33424E",
    "muted": "#64748B",
    "faint": "#98A6B3",
    "accent": "#0B8A5A",
    "accent_hover": "#086F49",
    "accent_soft": "#E6F4ED",
    "accent_line": "#C2E3D2",
    "sidebar": "#0D241D",
    "sidebar_deep": "#091A15",
    "sidebar_line": "#1E3B31",
    "sidebar_ink": "#EDF5F0",
    "sidebar_soft": "#C1D4CA",
    "sidebar_muted": "#8AA69A",
    "sidebar_hover": "#16352A",
    "sidebar_active": "#0E9A62",
    "ok": "#12855F",
    "ok_soft": "#E5F3EC",
    "warn": "#A9741C",
    "warn_soft": "#FAF0DA",
    "danger": "#C0483F",
    "danger_soft": "#FBECE9",
    "info": "#2F6BBF",
    "info_soft": "#EAF1FA",
    "water": "#CBDEE8",
    "water_deep": "#B7D0DE",
    "land": "#F6F7F2",
    "park": "#DCE9D5",
    "road": "#FFFFFF",
    "road_edge": "#D5D9CE",
    "grid": "#E9EBE3",
}

RISK_COLORS = {
    "low": "#12855F",
    "moderate": "#A9741C",
    "high": "#C05A21",
    "severe": "#C0483F",
}
RISK_SCORES = {"low": 12, "moderate": 31, "high": 52, "severe": 78}

STATUS_COLORS = {
    "available": "#0B8457",
    "rented": "#2F6BBF",
    "maintenance": "#A9741C",
}

SEVERITY_COLORS = {"info": "#2F6BBF", "warning": "#A9741C", "critical": "#C0483F"}

FONTS: dict[str, tkfont.Font] = {}


# ---------------------------------------------------------------------------
# Folders
# ---------------------------------------------------------------------------


def local_app_data_root() -> Path:
    """%LOCALAPPDATA%\\FloodReadyVehicleSystem (portable fallback beside the file)."""
    override = os.getenv("FLOODREADY_DATA_DIR")
    if override:
        return Path(override)
    local_app_data = os.getenv("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / APP_SHORT_NAME
    home = os.getenv("XDG_DATA_HOME")
    if home:
        return Path(home) / APP_SHORT_NAME
    return Path(__file__).resolve().parent / "app_data" / APP_SHORT_NAME


DATA_ROOT = local_app_data_root()
DATA_DIR = DATA_ROOT / "data"
EXPORT_DIR = DATA_ROOT / "exports"
LOG_DIR = DATA_ROOT / "logs"
LOG_FILE = LOG_DIR / "application.log"
DATABASE_FILE = DATA_DIR / "rental_system.db"


def setup_logging(level: int = logging.INFO) -> Path:
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:  # pragma: no cover - defensive
        pass
    handler = RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-8s | %(message)s"))
    root = logging.getLogger()
    root.setLevel(level)
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)
    logging.getLogger(__name__).info("%s %s starting | data=%s", APP_NAME, APP_VERSION, DATA_DIR)
    return LOG_FILE


def ensure_folders() -> None:
    for folder in (DATA_DIR, EXPORT_DIR, LOG_DIR):
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError:  # pragma: no cover - read-only profile
            fallback = Path(__file__).resolve().parent / "app_data" / folder.name
            fallback.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Fonts and theme
# ---------------------------------------------------------------------------


def build_fonts(root: tk.Tk) -> None:
    families = set(tkfont.families(root))
    default = str(tkfont.nametofont("TkDefaultFont").actual("family"))
    for name in ("Segoe UI", "SF Pro Text", "Helvetica Neue", "Inter", "Ubuntu", "DejaVu Sans", "Helvetica"):
        if name in families:
            family = name
            break
    else:
        family = default
    for name in ("JetBrains Mono", "Cascadia Mono", "Consolas", "Menlo", "DejaVu Sans Mono"):
        if name in families:
            mono = name
            break
    else:
        mono = "Courier New"

    def font(size: int, weight: str = "normal", family_name: str = family) -> tkfont.Font:
        return tkfont.Font(root=root, family=family_name, size=size, weight=weight)

    FONTS.update(
        {
            "micro": font(8),
            "micro_bold": font(8, "bold"),
            "small": font(9),
            "small_bold": font(9, "bold"),
            "nav": font(10),
            "nav_bold": font(10, "bold"),
            "body": font(10),
            "h2": font(13, "bold"),
            "title": font(21, "bold"),
            "display": font(23, "bold"),
            "value": font(22, "bold"),
            "value_small": font(17, "bold"),
            "mono": font(9, family_name=mono),
            "mono_bold": font(9, "bold", family_name=mono),
        }
    )


def apply_theme(root: tk.Tk) -> ttk.Style:
    """Install the light, hairline theme used across every window."""
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:  # pragma: no cover
        pass
    p = PALETTE
    style.configure(".", background=p["bg"], foreground=p["ink_soft"], font=FONTS["body"], borderwidth=0)

    for name, background in (
        ("Page.TFrame", p["bg"]),
        ("Card.TFrame", p["surface"]),
        ("Sunken.TFrame", p["sunken"]),
        ("CardBorder.TFrame", p["line"]),
        ("Bar.TFrame", p["surface"]),
        ("Sidebar.TFrame", p["sidebar"]),
        ("SidebarDeep.TFrame", p["sidebar_deep"]),
        ("SidebarBorder.TFrame", p["sidebar_line"]),
        ("SidebarCard.TFrame", p["sidebar_hover"]),
    ):
        style.configure(name, background=background)

    def labels(background: str, suffix: str) -> None:
        style.configure(f"Title{suffix}", background=background, foreground=p["ink"], font=FONTS["h2"])
        style.configure(f"Heading{suffix}", background=background, foreground=p["ink"], font=FONTS["h2"])
        style.configure(f"Body{suffix}", background=background, foreground=p["ink_soft"], font=FONTS["body"])
        style.configure(f"Muted{suffix}", background=background, foreground=p["muted"], font=FONTS["small"])
        style.configure(f"Micro{suffix}", background=background, foreground=p["faint"], font=FONTS["micro"])
        style.configure(f"Value{suffix}", background=background, foreground=p["ink"], font=FONTS["value"])

    labels(p["bg"], ".TLabel")
    labels(p["surface"], "Card.TLabel")
    labels(p["sunken"], "Sunken.TLabel")
    # page titles get the large display size; card titles stay at h2
    style.configure("Title.TLabel", background=p["bg"], foreground=p["ink"], font=FONTS["title"])

    # dark sidebar labels -------------------------------------------------
    style.configure("BrandSidebar.TLabel", background=p["sidebar"], foreground=p["sidebar_ink"], font=FONTS["h2"])
    style.configure("MutedSidebar.TLabel", background=p["sidebar"], foreground=p["sidebar_muted"], font=FONTS["small"])
    style.configure("MicroSidebar.TLabel", background=p["sidebar"], foreground=p["sidebar_muted"], font=FONTS["micro"])
    style.configure("GroupSidebar.TLabel", background=p["sidebar"], foreground=p["sidebar_muted"], font=FONTS["micro_bold"])
    style.configure("BrandMarkSidebar.TLabel", background=p["sidebar_active"], foreground="#FFFFFF", font=FONTS["h2"])
    style.configure("TitleSidebarCard.TLabel", background=p["sidebar_hover"], foreground=p["sidebar_ink"], font=FONTS["small_bold"])
    style.configure("MutedSidebarCard.TLabel", background=p["sidebar_hover"], foreground=p["sidebar_muted"], font=FONTS["micro"])

    # buttons -------------------------------------------------------------
    def flat(name: str, background: str, foreground: str, hover: str, border: str | None = None) -> None:
        edge = border or background
        style.configure(
            name,
            background=background,
            foreground=foreground,
            font=FONTS["small_bold"],
            bordercolor=edge,
            lightcolor=edge,
            darkcolor=edge,
            relief="flat",
            padding=(13, 8),
        )
        style.map(
            name,
            background=[("disabled", background), ("active", hover)],
            foreground=[("disabled", p["faint"])],
            bordercolor=[("active", hover)],
            lightcolor=[("active", hover)],
            darkcolor=[("active", hover)],
        )

    flat("Primary.TButton", p["accent"], "#FFFFFF", p["accent_hover"])
    flat("Quiet.TButton", p["accent_soft"], p["accent"], "#D6EAE0")
    flat("Ghost.TButton", p["sunken"], p["ink_soft"], "#E9EBE7")
    flat("Secondary.TButton", p["surface"], p["ink_soft"], p["sunken"], border=p["line"])
    flat("Danger.TButton", p["danger"], "#FFFFFF", "#A03A32")
    flat("Sidebar.TButton", p["sidebar"], p["sidebar_soft"], p["sidebar_hover"])
    flat("SidebarActive.TButton", p["sidebar_active"], "#FFFFFF", p["accent_hover"])
    flat("SidebarGhost.TButton", p["sidebar_hover"], p["sidebar_soft"], p["sidebar_line"], border=p["sidebar_line"])
    for sidebar_name in ("Sidebar.TButton", "SidebarActive.TButton"):
        style.configure(sidebar_name, anchor="w", padding=(14, 9))

    # fields --------------------------------------------------------------
    style.configure(
        "Field.TEntry",
        fieldbackground=p["surface"],
        background=p["surface"],
        foreground=p["ink"],
        bordercolor=p["line"],
        lightcolor=p["line"],
        darkcolor=p["line"],
        insertcolor=p["ink"],
        padding=(10, 8),
        relief="flat",
    )
    style.map(
        "Field.TEntry",
        bordercolor=[("focus", p["accent_line"])],
        lightcolor=[("focus", p["accent_line"])],
        darkcolor=[("focus", p["accent_line"])],
    )
    # password entry carries the in-field eye toggle in its right padding,
    # so the typed text never slides under the glyph
    style.configure(
        "PasswordField.TEntry",
        fieldbackground=p["surface"],
        background=p["surface"],
        foreground=p["ink"],
        bordercolor=p["line"],
        lightcolor=p["line"],
        darkcolor=p["line"],
        insertcolor=p["ink"],
        padding=(10, 8, 38, 8),
        relief="flat",
    )
    style.map(
        "PasswordField.TEntry",
        bordercolor=[("focus", p["accent_line"])],
        lightcolor=[("focus", p["accent_line"])],
        darkcolor=[("focus", p["accent_line"])],
    )
    style.configure(
        "Field.TCombobox",
        fieldbackground=p["surface"],
        background=p["surface"],
        foreground=p["ink"],
        bordercolor=p["line"],
        lightcolor=p["line"],
        darkcolor=p["line"],
        arrowsize=11,
        padding=(9, 5),
        relief="flat",
    )
    style.map(
        "Field.TCombobox",
        fieldbackground=[("readonly", p["surface"])],
        background=[("readonly", p["surface"])],
        bordercolor=[("focus", p["accent_line"])],
    )
    for option, value in (
        ("*TCombobox*Listbox.font", FONTS["small"]),
        ("*TCombobox*Listbox.background", p["surface"]),
        ("*TCombobox*Listbox.foreground", p["ink_soft"]),
        ("*TCombobox*Listbox.selectBackground", p["accent_soft"]),
        ("*TCombobox*Listbox.selectForeground", p["ink"]),
        ("*TCombobox*Listbox.borderWidth", 0),
        ("*TCombobox*Listbox.relief", "flat"),
        ("*TCombobox*Listbox.highlightThickness", 0),
    ):
        root.option_add(option, value)

    # data table ----------------------------------------------------------
    style.configure(
        "Data.Treeview",
        background=p["surface"],
        fieldbackground=p["surface"],
        foreground=p["ink_soft"],
        rowheight=36,
        borderwidth=0,
        font=FONTS["small"],
    )
    style.configure(
        "Data.Treeview.Heading",
        background=p["surface"],
        foreground=p["muted"],
        font=FONTS["micro_bold"],
        relief="flat",
        borderwidth=0,
        padding=(10, 9),
    )
    # toggle pills used by the GPS page layer switches ---------------------
    flat("ToggleOn.TButton", p["accent_soft"], p["accent"], "#D6EAE0", border=p["accent_line"])
    flat("ToggleOff.TButton", p["surface"], p["muted"], p["sunken"], border=p["line"])
    style.configure("ToggleOn.TButton", font=FONTS["micro_bold"], padding=(10, 5))
    style.configure("ToggleOff.TButton", font=FONTS["micro_bold"], padding=(10, 5))
    style.map("Data.Treeview", background=[("selected", p["accent_soft"])], foreground=[("selected", p["ink"])])
    style.map("Data.Treeview.Heading", background=[("active", p["surface"])])

    style.layout("Vertical.Thin.TScrollbar", style.layout("Vertical.TScrollbar"))
    style.configure(
        "Vertical.Thin.TScrollbar",
        background=p["line"],
        troughcolor=p["surface"],
        bordercolor=p["surface"],
        lightcolor=p["line"],
        darkcolor=p["line"],
        arrowsize=11,
        gripcount=0,
        relief="flat",
    )
    style.map(
        "Vertical.Thin.TScrollbar",
        background=[("active", p["faint"])],
        lightcolor=[("active", p["faint"])],
        darkcolor=[("active", p["faint"])],
    )

    style.configure("Switch.TCheckbutton", background=p["surface"], foreground=p["ink_soft"], font=FONTS["small"], focuscolor=p["surface"])
    style.map("Switch.TCheckbutton", background=[("active", p["surface"])])

    # sidebar, status bar and one-off labels -----------------------------
    style.configure("TitleBar.TLabel", background=p["surface"], foreground=p["ink"], font=FONTS["h2"])
    style.configure("MutedBar.TLabel", background=p["surface"], foreground=p["muted"], font=FONTS["small"])
    style.configure("MicroBar.TLabel", background=p["surface"], foreground=p["faint"], font=FONTS["micro"])
    style.configure("AccentCard.TLabel", background=p["surface"], foreground=p["accent"], font=FONTS["small"])
    style.configure("DangerCard.TLabel", background=p["surface"], foreground=p["danger"], font=FONTS["small"])
    style.configure("FieldPlaceholder.TLabel", background=p["surface"], foreground=p["faint"], font=FONTS["small"])

    style.configure(
        "Side.TButton",
        background=p["surface"],
        foreground=p["ink_soft"],
        font=FONTS["nav"],
        anchor="w",
        padding=(14, 7),
        relief="flat",
        bordercolor=p["surface"],
        lightcolor=p["surface"],
        darkcolor=p["surface"],
    )
    style.map(
        "Side.TButton",
        background=[("active", p["sunken"])],
        foreground=[("active", p["ink"])],
        lightcolor=[("active", p["sunken"])],
        darkcolor=[("active", p["sunken"])],
        bordercolor=[("active", p["sunken"])],
    )
    style.configure(
        "SideActive.TButton",
        background=p["accent_soft"],
        foreground=p["accent"],
        font=FONTS["small_bold"],
        anchor="w",
        padding=(14, 7),
        relief="flat",
        bordercolor=p["accent_soft"],
        lightcolor=p["accent_soft"],
        darkcolor=p["accent_soft"],
    )
    style.map(
        "SideActive.TButton",
        background=[("active", p["accent_soft"])],
        foreground=[("active", p["accent"])],
        lightcolor=[("active", p["accent_soft"])],
        darkcolor=[("active", p["accent_soft"])],
        bordercolor=[("active", p["accent_soft"])],
    )

    pills = {
        "PillLow": (RISK_COLORS["low"], "#E5F3EC"),
        "PillModerate": (RISK_COLORS["moderate"], "#FAF0DA"),
        "PillHigh": (RISK_COLORS["high"], "#FBE9DA"),
        "PillSevere": (RISK_COLORS["severe"], "#FBECE9"),
        "PillInfo": (SEVERITY_COLORS["info"], p["info_soft"]),
        "PillWarning": (SEVERITY_COLORS["warning"], p["warn_soft"]),
        "PillCritical": (SEVERITY_COLORS["critical"], p["danger_soft"]),
        "PillNeutral": (p["muted"], p["sunken"]),
        "PillAccent": (p["accent"], p["accent_soft"]),
    }
    for name, (foreground, background) in pills.items():
        style.configure(
            f"{name}Card.TLabel",
            background=background,
            foreground=foreground,
            font=FONTS["micro_bold"],
            padding=(10, 4),
        )
    return style


# ---------------------------------------------------------------------------
# Small building blocks
# ---------------------------------------------------------------------------


def round_rect(canvas: tk.Canvas, x1: float, y1: float, x2: float, y2: float, radius: float = 10, **kwargs: Any) -> int:
    """Draw a rounded rectangle on a canvas (polygon with smoothed corners)."""
    radius = max(0.0, min(radius, (x2 - x1) / 2, (y2 - y1) / 2))
    points = [
        x1 + radius, y1, x2 - radius, y1, x2, y1, x2, y1 + radius,
        x2, y2 - radius, x2, y2, x2 - radius, y2, x1 + radius, y2,
        x1, y2, x1, y2 - radius, x1, y1 + radius, x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, **kwargs)


# ---------------------------------------------------------------------------
# Rounded buttons — canvas-drawn so every control shares one crisp shape
# ---------------------------------------------------------------------------


# ttk style name -> visual recipe.  Callers keep using the familiar style
# names ("Primary.TButton", "Sidebar.TButton", ...) while the widget itself
# is a canvas that renders a true rounded rectangle with hover and press
# states — something ttk's flat rectangles cannot do.
BUTTON_KINDS: dict[str, dict[str, Any]] = {
    "Primary.TButton": dict(fill="accent", fg="#FFFFFF", hover="accent_hover", border=None, font="small_bold", height=34, padx=15, radius=9),
    "Secondary.TButton": dict(fill="surface", fg="ink_soft", hover="sunken", border="line", font="small_bold", height=34, padx=14, radius=9),
    "Quiet.TButton": dict(fill="accent_soft", fg="accent", hover="#D8EBE1", border=None, font="small_bold", height=34, padx=14, radius=9),
    "Ghost.TButton": dict(fill="sunken", fg="ink_soft", hover="line_soft", border=None, font="small_bold", height=30, padx=12, radius=8),
    "Danger.TButton": dict(fill="danger", fg="#FFFFFF", hover="#A03A32", border=None, font="small_bold", height=34, padx=14, radius=9),
    "Sidebar.TButton": dict(fill="sidebar", fg="sidebar_soft", hover="sidebar_hover", border=None, font="nav", height=36, padx=12, radius=9, anchor="w"),
    "SidebarActive.TButton": dict(fill="sidebar_active", fg="#FFFFFF", hover="accent_hover", border=None, font="nav_bold", height=36, padx=12, radius=9, anchor="w"),
    "SidebarGhost.TButton": dict(fill="sidebar_hover", fg="sidebar_soft", hover="sidebar_line", border="sidebar_line", font="small", height=30, padx=10, radius=8),
    "ToggleOn.TButton": dict(fill="accent_soft", fg="accent", hover="#D8EBE1", border="accent_line", font="micro_bold", height=26, padx=11, radius=8),
    "ToggleOff.TButton": dict(fill="surface", fg="muted", hover="sunken", border="line", font="micro_bold", height=26, padx=11, radius=8),
    "Hero.TButton": dict(fill="accent", fg="#FFFFFF", hover="accent_hover", border=None, font="small_bold", height=44, padx=15, radius=11),
}

# ttk frames whose background colour the buttons must blend into.
_STYLE_BG: dict[str, str] = {
    "Page.TFrame": "bg",
    "Card.TFrame": "surface",
    "Sunken.TFrame": "sunken",
    "CardBorder.TFrame": "line",
    "Bar.TFrame": "surface",
    "Sidebar.TFrame": "sidebar",
    "SidebarDeep.TFrame": "sidebar_deep",
    "SidebarBorder.TFrame": "sidebar_line",
    "SidebarCard.TFrame": "sidebar_hover",
}


def _host_surface(widget: tk.Widget) -> str:
    """Best guess at the colour behind a button so its corners look cut out."""
    try:
        style_name = str(widget.cget("style"))
    except tk.TclError:
        style_name = ""
    if style_name in _STYLE_BG:
        return PALETTE[_STYLE_BG[style_name]]
    try:
        return str(widget.cget("background"))
    except (tk.TclError, KeyError):
        return PALETTE["surface"]


class Button(tk.Canvas):
    """Rounded flat button that speaks the ttk.Button dialect.

    Supports the keyword arguments used across this application — ``text``,
    ``command``, ``style`` and ``width`` (a minimum width in pixels) — and the
    ``configure(style=...)`` restyling the shell performs for the active page.
    The button is drawn as a smooth rounded rectangle with quiet hover and
    press states, so it reads as a modern control rather than a grey ttk slab.
    """

    def __init__(
        self,
        master: tk.Widget,
        text: str = "",
        command: Callable[[], None] | None = None,
        style: str = "Primary.TButton",
        width: int | None = None,
        **_ignored: Any,
    ) -> None:
        self._kind = style if style in BUTTON_KINDS else "Primary.TButton"
        self.text = str(text)
        self._command = command
        self._state = "normal"
        self._hover = False
        self._pressed = False
        self._min_width = int(width) if width else 0
        self._flash_job: str | None = None
        super().__init__(master, highlightthickness=0, bd=0, background=_host_surface(master), cursor="hand2")
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_press)
        self.bind("<Configure>", lambda _event: self._render())
        self._fit()
        self._render()

    # -- geometry ----------------------------------------------------------
    def _font(self) -> tkfont.Font:
        return FONTS[BUTTON_KINDS[self._kind]["font"]]

    def _fit(self) -> None:
        kind = BUTTON_KINDS[self._kind]
        try:
            text_width = self._font().measure(self.text)
        except tk.TclError:  # fonts not built yet (design-time preview)
            text_width = len(self.text) * 7
        width = max(int(text_width) + kind["padx"] * 2, self._min_width, 24)
        height = kind["height"]
        if str(self.cget("width")) != str(width) or str(self.cget("height")) != str(height):
            super().configure(width=width, height=height)

    # -- painting ----------------------------------------------------------
    def _render(self) -> None:
        self.delete("all")
        kind = BUTTON_KINDS[self._kind]
        p = PALETTE
        disabled = self._state == "disabled"
        fill_key = kind["fill"] if kind["fill"] in p else None
        fill = p.get(fill_key, kind["fill"]) if fill_key else kind["fill"]
        if fill_key:
            hover = p[kind["hover"]] if kind["hover"] in p else kind["hover"]
        else:
            hover = kind["hover"]
        press = _mix(fill, "#000000", 0.16)
        if self._pressed and not disabled:
            fill = press
        elif self._hover and not disabled:
            fill = hover
        if kind.get("border"):
            edge = p[kind["border"]]
        else:
            edge = fill
        width = max(int(self.winfo_width()), 1)
        height = max(int(self.winfo_height()), 1) or kind["height"]
        round_rect(self, 0, 0, width - 1, height - 1, radius=kind["radius"], fill=fill, outline=edge)
        if disabled:
            colour = p["sidebar_muted"] if self._kind.startswith("Sidebar") else p["faint"]
        else:
            colour = p[kind["fg"]] if kind["fg"] in p else kind["fg"]
        anchor = kind.get("anchor", "center")
        x = kind["padx"] if anchor == "w" else width / 2
        self.create_text(
            x, height / 2 + 1, text=self.text, font=self._font(), fill=colour,
            anchor="w" if anchor == "w" else "center",
        )

    # -- interaction ---------------------------------------------------------
    def _on_enter(self, _event: tk.Event) -> None:
        self._hover = True
        self._render()

    def _on_leave(self, _event: tk.Event) -> None:
        self._hover = False
        self._pressed = False
        self._render()

    def _on_press(self, _event: tk.Event) -> None:
        if self._state == "disabled":
            return
        self._pressed = True
        self._render()
        if self._flash_job is not None:
            try:
                self.after_cancel(self._flash_job)
            except tk.TclError:
                pass
        try:
            self._flash_job = self.after(140, self._release_flash)
        except tk.TclError:
            self._flash_job = None
        if self._command is not None:
            try:
                self._command()
            except Exception:  # a dialog error must never look like a crash
                logging.getLogger(__name__).exception("Button action failed")

    def _release_flash(self) -> None:
        self._flash_job = None
        if self._pressed:
            self._pressed = False
            self._render()

    def invoke(self) -> None:
        if self._state == "normal" and self._command is not None:
            self._command()

    # -- ttk-compatible configuration ----------------------------------------
    def configure(self, cnf: Any = None, **kw: Any) -> None:
        if cnf is not None:
            kw = {**cnf, **kw}
        changed = False
        for key, value in kw.items():
            if key == "text":
                self.text = str(value)
                changed = True
            elif key == "command":
                self._command = value
                changed = True
            elif key == "state":
                self._state = str(value)
                super().configure(cursor="hand2" if self._state == "normal" else "arrow")
                changed = True
            elif key == "style":
                name = str(value)
                if name in BUTTON_KINDS and name != self._kind:
                    self._kind = name
                    changed = True
            elif key == "width":
                self._min_width = int(value)
                changed = True
            else:
                super().configure({key: value})
        if changed:
            self._fit()
            self._render()

    def cget(self, key: str) -> Any:
        if key == "text":
            return self.text
        if key == "state":
            return self._state
        if key == "style":
            return self._kind
        if key == "command":
            return self._command
        return super().cget(key)

    def keys(self) -> list[str]:  # pragma: no cover - introspection helper
        return ["text", "state", "style", "command", *super().keys()]


class Card(ttk.Frame):
    """White panel with a hairline border (ttk cannot draw one natively)."""

    def __init__(self, master: tk.Widget, padding: tuple[int, int] = (16, 14), style: str = "Card.TFrame") -> None:
        super().__init__(master, style="CardBorder.TFrame", padding=1)
        self.body = ttk.Frame(self, style=style, padding=padding)
        self.body.pack(fill="both", expand=True)


class Stat(ttk.Frame):
    """Metric tile: tinted icon chip, oversized value, quiet context line."""

    def __init__(
        self,
        master: tk.Widget,
        label: str,
        meta: str = "",
        tone: str = "accent",
        glyph: str = "◆",
        command: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(master, style="CardBorder.TFrame", padding=1)
        body = ttk.Frame(self, style="Card.TFrame", padding=(17, 15))
        body.pack(fill="both", expand=True)
        top = ttk.Frame(body, style="Card.TFrame")
        top.pack(fill="x")
        chip = tk.Canvas(top, width=32, height=32, background=PALETTE["surface"], highlightthickness=0, bd=0)
        chip.pack(side="left")
        round_rect(chip, 1, 1, 31, 31, radius=10, fill=PALETTE.get(f"{tone}_soft", PALETTE["accent_soft"]), outline="")
        chip.create_text(16, 17, text=glyph, font=FONTS["small_bold"], fill=PALETTE.get(tone, PALETTE["accent"]))
        ttk.Label(top, text=label.upper(), style="MicroCard.TLabel").pack(side="left", padx=(11, 0), pady=(10, 0))
        ttk.Label(top, text="›", style="MicroCard.TLabel", font=FONTS["h2"]).pack(side="right", pady=(4, 0))
        self.value = ttk.Label(body, text="—", style="ValueCard.TLabel")
        self.value.pack(anchor="w", pady=(14, 0))
        self.meta = ttk.Label(body, text=meta, style="MutedCard.TLabel", wraplength=220, justify="left")
        self.meta.pack(anchor="w", pady=(5, 0))
        if command is not None:
            for widget in (body, self.value, self.meta, top):
                widget.configure(cursor="hand2")
                widget.bind("<Button-1>", lambda _event: command())

    def set(self, value: str, meta: str = "") -> None:
        self.value.configure(text=value)
        if meta:
            self.meta.configure(text=meta)


class Bar(tk.Canvas):
    """Slim rounded progress meter that follows its container width."""

    def __init__(self, master: tk.Widget, height: int = 6, color: str | None = None, track: str | None = None) -> None:
        super().__init__(master, height=height, background=track or PALETTE["sunken"], highlightthickness=0, bd=0)
        self.color = color or PALETTE["accent"]
        self.fraction = 0.0
        self.bind("<Configure>", lambda _event: self._draw())

    def set(self, fraction: float) -> None:
        self.fraction = max(0.0, min(1.0, fraction))
        self._draw()

    def _draw(self) -> None:
        self.delete("all")
        width = max(int(self.winfo_width()), 1)
        height = max(int(self.winfo_height()), 1)
        filled = int(width * self.fraction)
        if filled > 0:
            round_rect(self, 0, 0, max(filled, height), height, radius=height / 2, fill=self.color, outline="")


class Bars(tk.Canvas):
    """Column chart drawn on a plain canvas — no chart library needed."""

    def __init__(self, master: tk.Widget, height: int = 150) -> None:
        super().__init__(master, height=height, background=PALETTE["surface"], highlightthickness=0, bd=0)
        self.data: list[tuple[str, float]] = []
        self.bind("<Configure>", lambda _event: self._draw())

    def set(self, data: list[tuple[str, float]]) -> None:
        self.data = data
        self._draw()

    def _draw(self) -> None:
        self.delete("all")
        width, height = max(int(self.winfo_width()), 40), max(int(self.winfo_height()), 40)
        if not self.data:
            return
        top, label_space = 26, 24
        baseline = height - label_space
        peak = max(value for _label, value in self.data)
        if peak <= 0:
            self.create_text(
                width / 2, height / 2, text="No transactions recorded yet",
                font=FONTS["small"], fill=PALETTE["faint"],
            )
            self.create_line(0, baseline, width, baseline, fill=PALETTE["line"], width=1)
            return
        count = len(self.data)
        gap = 16
        column = max((width - gap * (count - 1)) / count, 8)
        # faint guides at the midpoint and the peak give the eye a reference
        for fraction in (1.0, 0.5):
            y = baseline - (baseline - top) * fraction
            self.create_line(0, y, width, y, fill=PALETTE["line_soft"], width=1)
        self.create_line(0, baseline + 1, width, baseline + 1, fill=PALETTE["line"], width=1)
        peak_index = max(range(count), key=lambda index: self.data[index][1])
        for index, (label, value) in enumerate(self.data):
            x = index * (column + gap)
            bar_height = (baseline - top) * (value / peak)
            y = baseline - bar_height
            radius = max(0.0, min(column / 2, 5.0))
            color = PALETTE["accent"] if index == peak_index and value > 0 else "#A0D2BE"
            if bar_height > radius:
                round_rect(self, x, y, x + column, baseline, radius=radius, fill=color, outline="")
            elif bar_height > 0:
                self.create_rectangle(x, y, x + column, baseline, fill=color, outline="")
            if value > 0:
                self.create_text(
                    x + column / 2, y - 9, text=_short(value), font=FONTS["micro"],
                    fill=PALETTE["ink_soft"] if index == peak_index else PALETTE["muted"], anchor="s",
                )
            self.create_text(
                x + column / 2, height - 6, text=label, font=FONTS["small"],
                fill=PALETTE["ink_soft"] if index == peak_index else PALETTE["muted"], anchor="s",
            )


class Table(ttk.Frame):
    """Data table: heading row, striped rows, coloured status tags."""

    def __init__(
        self,
        master: tk.Widget,
        columns: Sequence[tuple[str, str, int, str]],
        on_select: Callable[[str], None] | None = None,
        on_double: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(master, style="CardBorder.TFrame", padding=1)
        holder = ttk.Frame(self, style="Card.TFrame")
        holder.pack(fill="both", expand=True)
        self.keys = [column[0] for column in columns]
        self.tree = ttk.Treeview(
            holder, style="Data.Treeview", columns=self.keys, show="headings", selectmode="browse", height=12
        )
        for key, heading, width, anchor in columns:
            self.tree.heading(key, text=str(heading).upper(), anchor="w")
            self.tree.column(key, width=width, minwidth=48, anchor=anchor, stretch=True)
        self.scroll = ttk.Scrollbar(holder, orient="vertical", command=self.tree.yview, style="Thin.TScrollbar")
        self.tree.configure(yscrollcommand=self.scroll.set)
        self.tree.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=7)
        self.scroll.pack(side="right", fill="y", pady=7, padx=(0, 5))
        self.tree.tag_configure("odd", background=PALETTE["surface"])
        self.tree.tag_configure("even", background="#F7F9FA")
        for name, color in (
            ("ok", PALETTE["ok"]),
            ("warn", PALETTE["warn"]),
            ("danger", PALETTE["danger"]),
            ("info", PALETTE["info"]),
            ("accent", PALETTE["accent"]),
            ("muted", PALETTE["muted"]),
        ):
            self.tree.tag_configure(name, foreground=color)
        if on_select:
            self.tree.bind("<<TreeviewSelect>>", lambda _event: on_select(self.selected()))
        if on_double:
            self.tree.bind("<Double-1>", lambda _event: on_double(self.selected()))

    def clear(self) -> None:
        for item in self.tree.get_children(""):
            self.tree.delete(item)

    def set_rows(self, rows: Sequence[dict[str, Any]], tag_of: Callable[[dict[str, Any]], str] | None = None) -> None:
        previous = self.selected()  # keep the highlighted row across refreshes
        self.clear()
        for index, row in enumerate(rows):
            values = [row.get(key, "") for key in self.keys]
            tags = ["even" if index % 2 else "odd"]
            if tag_of:
                extra = tag_of(row)
                if extra:
                    tags.append(extra)
            self.tree.insert("", "end", iid=str(row.get("id", index)), values=values, tags=tags)
        if previous and self.tree.exists(previous):
            self.tree.selection_set(previous)
            self.tree.see(previous)

    def selected(self) -> str:
        selection = self.tree.selection()
        return selection[0] if selection else ""


class Field(ttk.Frame):
    """Label plus entry (or combobox) in one tidy block."""

    def __init__(
        self,
        master: tk.Widget,
        label: str,
        value: str = "",
        width: int = 26,
        choices: Sequence[str] | None = None,
        on_change: Callable[[str], None] | None = None,
        secret: bool = False,
        editable: bool = False,
    ) -> None:
        super().__init__(master, style="Card.TFrame")
        ttk.Label(self, text=label.upper(), style="MicroCard.TLabel").pack(anchor="w")
        self.variable = tk.StringVar(value=value)
        self.widget: tk.Widget
        if choices is None:
            self.widget = ttk.Entry(
                self, textvariable=self.variable, width=width, style="Field.TEntry", show="•" if secret else ""
            )
        else:
            self.widget = ttk.Combobox(
                self,
                textvariable=self.variable,
                values=list(choices),
                width=width,
                state="normal" if editable else "readonly",
                style="Field.TCombobox",
            )
        self.widget.pack(fill="x", pady=(5, 0))
        if on_change:
            self.variable.trace_add("write", lambda *_args: on_change(self.variable.get()))

    def get(self) -> str:
        return self.variable.get().strip()


class Divider(ttk.Frame):
    """One pixel hairline used inside cards."""

    def __init__(self, master: tk.Widget) -> None:
        super().__init__(master, style="CardBorder.TFrame", height=1)
        self.pack_propagate(False)


def heading(parent: tk.Widget, title: str, subtitle: str, actions: Sequence[tk.Widget] = ()) -> ttk.Frame:
    """Page header: large title, quiet subtitle, actions on the right, hairline below."""
    bar = ttk.Frame(parent, style="Page.TFrame")
    text = ttk.Frame(bar, style="Page.TFrame")
    text.pack(side="left", fill="x", expand=True)
    ttk.Label(text, text=title, style="Title.TLabel").pack(anchor="w")
    ttk.Label(text, text=subtitle, style="Muted.TLabel").pack(anchor="w", pady=(6, 0))
    if actions:
        tools = ttk.Frame(bar, style="Page.TFrame")
        tools.place(in_=bar, relx=1.0, rely=0.5, anchor="e", x=-2)
        for widget in actions:
            widget.pack(in_=tools, side="left", padx=(8, 0))
            # action buttons are page children packed into the header bar;
            # raise them through Tcl so canvases and ttk widgets behave alike.
            widget.tk.call("raise", widget._w)
    bar.pack(fill="x", pady=(0, 10))
    ttk.Frame(parent, style="CardBorder.TFrame", height=1).pack(fill="x", pady=(0, 18))
    return bar


def grid_row(
    parent: tk.Widget, makers: Sequence[Callable[[tk.Widget], tk.Widget]], weights: Sequence[int] | None = None, gap: int = 12
) -> tuple[ttk.Frame, list[tk.Widget]]:
    """Build a row of panels; weights decide how extra width is shared.

    Each maker receives the row container so the panel is a real child of it —
    Tkinter grids a widget inside its own parent, never into `in=` targets.
    """
    wrap = ttk.Frame(parent, style="Page.TFrame")
    wrap.pack(fill="both", pady=(0, gap))
    weights = list(weights) if weights else [1] * len(makers)
    items: list[tk.Widget] = []
    for index, make in enumerate(makers):
        item = make(wrap)
        wrap.columnconfigure(index, weight=weights[index])
        item.grid(row=0, column=index, sticky="nsew", padx=(0 if index == 0 else gap, 0))
        items.append(item)
    wrap.rowconfigure(0, weight=1)
    return wrap, items


def card_title(card: Card, title: str, hint: str = "", action: tk.Widget | None = None) -> None:
    head = ttk.Frame(card.body, style="Card.TFrame")
    head.pack(fill="x")
    left = ttk.Frame(head, style="Card.TFrame")
    left.pack(side="left", fill="x", expand=True)
    ttk.Label(left, text=title, style="TitleCard.TLabel").pack(anchor="w")
    if hint:
        ttk.Label(left, text=hint, style="MutedCard.TLabel").pack(anchor="w", pady=(2, 0))
    if action is not None:
        action.pack(side="right")


# ---------------------------------------------------------------------------
# Map canvas — equirectangular, 1 km equal on both axes, pan and zoom
# ---------------------------------------------------------------------------

KM_PER_DEG_LAT = 110.574
CENTER_LAT = 14.6
KM_PER_DEG_LON = 111.320 * math.cos(math.radians(CENTER_LAT))


def _ll(x: float, y: float) -> tuple[float, float]:
    """Convert a point on the design grid to (latitude, longitude)."""
    return 14.68 - y / 5132.0, 120.92 + x / 4997.0


def _path(points: Sequence[tuple[float, float]]) -> list[tuple[float, float]]:
    return [_ll(x, y) for x, y in points]


ARTERIALS: list[tuple[str, list[tuple[float, float]]]] = [
    ("EDSA", _path([(318, 40), (352, 130), (430, 210), (560, 268), (690, 330), (790, 420), (836, 540)])),
    ("C-5", _path([(520, 90), (600, 190), (700, 280), (820, 400), (872, 520)])),
    ("Commonwealth", _path([(430, 150), (700, 150)])),
    ("Quezon Avenue", _path([(350, 300), (470, 220), (590, 152)])),
    ("Roxas Boulevard", _path([(176, 300), (214, 470), (268, 660)])),
    ("SLEX", _path([(420, 520), (560, 640), (700, 780)])),
    ("Ortigas Avenue", _path([(600, 430), (830, 300)])),
    ("Marcos Highway", _path([(700, 470), (900, 600)])),
    ("Aurora Boulevard", _path([(420, 330), (700, 350)])),
]

STREETS: list[tuple[tuple[float, float], tuple[float, float]]] = [
    ((x, y), (x + 46, y + 18)) for x, y in (
        (280, 380), (420, 300), (560, 250), (680, 200), (780, 300), (320, 460),
        (460, 420), (620, 400), (720, 500), (840, 620), (360, 540), (520, 560),
        (640, 640), (500, 700), (260, 560),
    )
] + [((x, y), (x + 20, y + 40)) for x, y in (
    (280, 380), (420, 300), (560, 250), (680, 200), (780, 300), (320, 460),
    (460, 420), (620, 400), (720, 500), (360, 540), (520, 560),
)]

PARKS: list[tuple[tuple[float, float], float, float]] = [
    ((392, 392), 34, 26),
    ((252, 560), 26, 40),
    ((560, 124), 48, 30),
    ((744, 560), 40, 28),
]

COASTLINE = _path([(96, 40), (150, 160), (140, 300), (176, 420), (196, 560), (176, 700), (120, 900)])

LAKE_CENTER = _ll(880, 950)
LAKE_RADIUS = (430 / 4997 * KM_PER_DEG_LON, 210 / 5132 * KM_PER_DEG_LAT)

# Rivers matter on a flood map: the Pasig and San Juan are the two channels
# that overflow first during heavy rain.
RIVERS: list[tuple[str, list[tuple[float, float]], float]] = [
    ("Pasig River", _path([(846, 862), (742, 742), (640, 620), (548, 540), (462, 482), (372, 484), (286, 520), (222, 566), (188, 592)]), 1.0),
    ("San Juan River", _path([(452, 486), (508, 438), (570, 400), (636, 366)]), 0.55),
    ("Tullahan River", _path([(150, 120), (246, 168), (346, 210), (448, 250)]), 0.5),
]

ZONE_TINTS = {
    "low": "#E2F2EA",
    "moderate": "#F8EFDA",
    "high": "#F9E8D8",
    "severe": "#F9E3E0",
}

ZONE_RISK_WORD = {"low": "LOW", "moderate": "MODERATE", "high": "HIGH", "severe": "SEVERE"}

NICE_STEPS = (0.5, 1, 2, 5, 10, 20, 50, 100)

MAP_LABELS: list[tuple[str, float, float, str]] = [
    ("MANILA", 14.5995, 120.9842, "city"),
    ("QUEZON CITY", 14.6339, 121.0281, "city"),
    ("MAKATI", 14.5631, 121.0244, "city"),
    ("PASIG", 14.5995, 121.0755, "city"),
    ("MALABON", 14.6598, 120.9573, "city"),
    ("CAINTA", 14.5752, 121.1018, "city"),
    ("PARAÑAQUE", 14.5102, 121.0002, "city"),
    ("Manila Bay", 14.5800, 120.9455, "water"),
    ("Laguna de Bay", 14.4900, 121.0900, "water"),
]


# ---------------------------------------------------------------------------
# Live tracking feed — units drive along the road network
# ---------------------------------------------------------------------------

UNIT_SPEEDS = {
    "Sedan": 27.0,
    "SUV": 30.0,
    "AUV": 26.0,
    "Van": 24.0,
    "Pickup": 28.0,
    "Motorcycle": 34.0,
    "Truck": 21.0,
    "Boat": 13.0,
}

# Barangay and district names, placed on the design grid.
DISTRICTS: list[tuple[str, float, float]] = [
    ("Sampaloc", 340, 350), ("Quiapo", 310, 424), ("Malate", 305, 532),
    ("Ermita", 296, 500), ("Pandacan", 376, 474), ("Santa Cruz", 320, 396),
    ("Tondo", 246, 326), ("Grace Park", 310, 258), ("Novaliches", 476, 144),
    ("Cubao", 656, 302), ("New Manila", 506, 338), ("San Juan", 556, 390),
    ("Mandaluyong", 606, 488), ("Taguig", 652, 666), ("Pateros", 750, 692),
    ("Marikina", 900, 462), ("Pasay", 376, 642), ("Caloocan", 276, 206),
    ("Navotas", 126, 104), ("Valenzuela", 276, 52), ("Pasig", 806, 438),
    ("Makati", 508, 588),
]

SECONDARY_ROADS: list[list[tuple[float, float]]] = [
    _path(points)
    for points in (
        [(300, 330), (330, 420), (352, 520)],   # Taft Avenue
        [(330, 300), (400, 330), (455, 360)],   # Recto / Legarda
        [(455, 300), (520, 250)],               # España to QC Circle
        [(470, 150), (470, 250)],               # West Avenue
        [(520, 160), (520, 250)],               # East Avenue
        [(420, 110), (560, 112)],               # Congressional Avenue
        [(600, 190), (640, 300)],               # Katipunan Avenue
        [(640, 300), (700, 340)],               # Aurora Boulevard
        [(600, 430), (740, 470)],               # Shaw Boulevard
        [(700, 420), (780, 462)],               # Julia Vargas
        [(760, 480), (700, 620)],               # C-5 to SLEX
        [(500, 570), (560, 600)],               # Ayala Avenue
        [(560, 640), (470, 700)],               # Sucat Road
        [(280, 620), (360, 662)],               # Airport Road
        [(300, 60), (330, 200), (352, 300)],    # North Luzon Expressway
        [(440, 130), (580, 172)],               # Mindanao Avenue
        [(480, 200), (600, 232)],               # Tandang Sora
        [(400, 250), (440, 320)],               # Banawe Street
        [(400, 320), (470, 400)],               # Araneta Avenue
        [(760, 430), (822, 472)],               # C. Raymundo Avenue
    )
]

COMPASS = ("N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW")


def _hash(*keys: int) -> float:
    """Stable pseudo-random value in [0, 1) so the map never flickers."""
    value = 17
    for key in keys:
        value = (value * 1_000_003 + int(key) * 2_654_435_761) % 4_294_967_296
    return (value % 100_000) / 100_000


def _mix(first: str, second: str, amount: float) -> str:
    """Blend two #RRGGBB colours; 0 returns the first, 1 the second."""
    amount = max(0.0, min(1.0, amount))

    def channel(index: int) -> int:
        start = int(first[index : index + 2], 16)
        end = int(second[index : index + 2], 16)
        return round(start + (end - start) * amount)

    return f"#{channel(1):02X}{channel(3):02X}{channel(5):02X}"


def compass_text(bearing: float) -> str:
    return COMPASS[int(((bearing % 360) + 11.25) // 22.5) % 16]


def _nearest_vertex(lat: float, lon: float) -> tuple[int, int, bool]:
    """Road index, vertex index and travel direction for the closest road point."""
    best: tuple[float, int, int, bool] | None = None
    for road_index, (_name, points) in enumerate(ARTERIALS):
        for vertex, (point_lat, point_lon) in enumerate(points):
            kilometres = distance_km(lat, lon, point_lat, point_lon)
            if best is None or kilometres < best[0]:
                best = (kilometres, road_index, vertex, vertex <= len(points) // 2)
    assert best is not None
    return best[1], best[2], best[3]


def _nearest_end(lat: float, lon: float, used: set[int]) -> tuple[int, int, bool] | None:
    best: tuple[float, int, int, bool] | None = None
    for road_index, (_name, points) in enumerate(ARTERIALS):
        if road_index in used:
            continue
        for vertex, forward in ((0, True), (len(points) - 1, False)):
            point_lat, point_lon = points[vertex]
            kilometres = distance_km(lat, lon, point_lat, point_lon)
            if best is None or kilometres < best[0]:
                best = (kilometres, road_index, vertex, forward)
    if best is None:
        return None
    return best[1], best[2], best[3]


def _route_for(lat: float, lon: float, hops: int = 4) -> list[tuple[float, float]]:
    """Chain a few roads together so a unit drives a believable route."""
    road_index, vertex, forward = _nearest_vertex(lat, lon)
    path: list[tuple[float, float]] = []
    used: set[int] = set()
    for _step in range(hops):
        if road_index is None or road_index >= len(ARTERIALS):
            break
        used.add(road_index)
        _name, points = ARTERIALS[road_index]
        leg = list(points[vertex:]) if forward else list(reversed(points[: vertex + 1]))
        if path:
            leg = leg[1:]
        path.extend(leg)
        if not path:
            break
        found = _nearest_end(path[-1][0], path[-1][1], used)
        if found is None:
            break
        road_index, vertex, forward = found
    cleaned: list[tuple[float, float]] = []
    for point in path:
        if not cleaned or point != cleaned[-1]:
            cleaned.append(point)
    if len(cleaned) < 2:
        cleaned = [(lat, lon), (lat + 0.005, lon + 0.005)]
    return cleaned


class Unit:
    """One vehicle following a route along the road network."""

    def __init__(self, record: dict[str, Any], path: list[tuple[float, float]]) -> None:
        self.id = int(record["id"])
        self.category = str(record["category"])
        self.plate = str(record["plate_number"])
        # Units in the shop do not move; available units are only repositioned.
        self.status = str(record["status"])
        throttle = {"rented": 1.0, "available": 0.32, "maintenance": 0.0}.get(self.status, 0.5)
        base = UNIT_SPEEDS.get(self.category, 26.0) * throttle
        self.speed = base * (0.85 + 0.4 * _hash(self.id, 13))
        self.parked = self.speed <= 0.01
        # Start exactly on the saved GPS pin: prepend it to the route so the
        # first frame agrees with the fleet list and the stored coordinates,
        # instead of snapping to the nearest road vertex.
        origin = (float(record["latitude"]), float(record["longitude"]))
        if tuple(path[0]) != origin:
            path = [origin, *path]
        self.path = path
        self.distances: list[float] = []
        total = 0.0
        for index in range(len(path) - 1):
            total += distance_km(path[index][0], path[index][1], path[index + 1][0], path[index + 1][1])
            self.distances.append(total)
        self.total = max(total, 0.001)
        self.offset = 0.0
        self.direction = 1.0
        self.lat, self.lon = origin
        self.heading = 0.0
        self.trail: list[tuple[float, float]] = []
        self.distance_travelled = 0.0
        self._place()

    def advance(self, seconds: float, multiplier: float) -> None:
        if self.parked:
            return
        kilometres = self.speed * seconds * multiplier / 3600.0
        self.offset += kilometres * self.direction
        if self.offset >= self.total:
            self.offset = self.total
            self.direction = -1.0
        elif self.offset <= 0.0:
            self.offset = 0.0
            self.direction = 1.0
        self.distance_travelled += kilometres
        self._place()
        self.trail.append((self.lat, self.lon))
        if len(self.trail) > 40:
            self.trail.pop(0)

    def _place(self) -> None:
        previous = 0.0
        index = 0
        for position, reached in enumerate(self.distances):
            if reached >= self.offset:
                index = position
                break
            previous = reached
            index = position
        start = self.path[index]
        end = self.path[index + 1] if index + 1 < len(self.path) else start
        span = self.distances[index] - previous if index < len(self.distances) else 0.0
        fraction = 0.0 if span <= 0 else max(0.0, min(1.0, (self.offset - previous) / span))
        self.lat = start[0] + (end[0] - start[0]) * fraction
        self.lon = start[1] + (end[1] - start[1]) * fraction
        north = (end[0] - start[0]) * KM_PER_DEG_LAT
        east = (end[1] - start[1]) * KM_PER_DEG_LON
        if abs(north) + abs(east) > 1e-9:
            self.heading = math.degrees(math.atan2(east, north)) % 360.0


class TrackingFeed:
    """Simulated GPS feed: every unit drives a route at a realistic speed."""

    TICK_MS = 90
    COMMIT_SECONDS = 15.0
    DRAW_MIN_SECONDS = 0.11  # feed-driven repaints cap near 9 fps; physics stays at 90 ms

    def __init__(self, store: "Store", host: tk.Misc, speed: float = 1.0) -> None:
        self.store = store
        self.host = host
        self.speed = speed
        self.running = False
        self.units: dict[int, Unit] = {}
        self._known: dict[int, tuple[Any, ...]] = {}
        self.subscribers: list["MapCanvas"] = []
        self._job: str | None = None
        self._last: datetime | None = None
        self._since_commit = 0.0
        self._last_draw: datetime | None = None
        self.elapsed = 0.0
        self.rebuild()

    # -- setup ------------------------------------------------------------
    def rebuild(self) -> None:
        self.units = {}
        self._known = {}
        for record in self.store.vehicles():
            self._admit(record)

    def _admit(self, record: dict[str, Any]) -> None:
        """Create (or refresh) the live unit for one fleet row.

        A unit is only rebuilt when its identity, status or saved position
        actually changed — otherwise a driving unit would be needlessly
        teleported back to its route start on every page refresh.
        """
        vehicle_id = int(record["id"])
        if record["latitude"] is None or record["longitude"] is None:
            self.units.pop(vehicle_id, None)
            self._known.pop(vehicle_id, None)
            return
        fingerprint = (
            str(record["plate_number"]),
            str(record["status"]),
            str(record["category"]),
            round(float(record["latitude"]), 4),
            round(float(record["longitude"]), 4),
        )
        if self._known.get(vehicle_id) == fingerprint and vehicle_id in self.units:
            return
        route = _route_for(float(record["latitude"]), float(record["longitude"]))
        self.units[vehicle_id] = Unit(record, route)
        self._known[vehicle_id] = fingerprint

    def sync(self) -> None:
        """Pick up fleet changes so every unit on the fleet list gets tracked.

        Call this after vehicles are added, edited or deleted (and whenever a
        page refreshes) — previously the feed only learned about the fleet at
        application start, so new or moved units never appeared on the GPS.
        """
        current_ids: set[int] = set()
        for record in self.store.vehicles():
            vehicle_id = int(record["id"])
            current_ids.add(vehicle_id)
            self._admit(record)
        for vehicle_id in set(self.units) - current_ids:
            self.units.pop(vehicle_id, None)
            self._known.pop(vehicle_id, None)

    def subscribe(self, canvas: "MapCanvas") -> None:
        if canvas not in self.subscribers:
            self.subscribers.append(canvas)

    def unsubscribe(self, canvas: "MapCanvas") -> None:
        if canvas in self.subscribers:
            self.subscribers.remove(canvas)

    # -- control ----------------------------------------------------------
    def start(self) -> None:
        if self.running:
            return
        self.running = True
        self._last = None
        self._schedule()

    def stop(self) -> None:
        self.running = False
        if self._job is not None:
            try:
                self.host.after_cancel(self._job)
            except tk.TclError:  # pragma: no cover
                pass
            self._job = None

    def toggle(self) -> bool:
        if self.running:
            self.stop()
        else:
            self.start()
        return self.running

    def set_speed(self, value: float) -> None:
        self.speed = max(0.25, min(120.0, value))

    # -- loop -------------------------------------------------------------
    def _schedule(self) -> None:
        if not self.running:
            return
        try:
            self._job = self.host.after(self.TICK_MS, self._tick)
        except tk.TclError:  # pragma: no cover - window already closed
            self.running = False

    def _tick(self) -> None:
        if not self.running:
            return
        now = datetime.now()
        seconds = 0.0
        if self._last is not None:
            seconds = min((now - self._last).total_seconds(), 1.5)
        self._last = now
        moved = False
        if seconds > 0:
            self.elapsed += seconds
            for unit in self.units.values():
                unit.advance(seconds, self.speed)
            moved = any(not unit.parked for unit in self.units.values())
            self._since_commit += seconds
            if self._since_commit >= self.COMMIT_SECONDS:
                self.commit()
        if moved and (self._last_draw is None or (now - self._last_draw).total_seconds() >= self.DRAW_MIN_SECONDS):
            self._last_draw = now
            # Parked fleets repaint nothing — the canvas keeps its last frame
            # until the user pans, zooms or the feed resumes.
            for canvas in list(self.subscribers):
                try:
                    if canvas.winfo_ismapped():
                        canvas.draw()
                except tk.TclError:
                    self.unsubscribe(canvas)
        self._schedule()

    def commit(self) -> None:
        """Persist live positions so the other pages agree with the map."""
        self._since_commit = 0.0
        if not self.units:
            return
        stamp = datetime.now().strftime(DATETIME_FORMAT)
        payload = [(unit.lat, unit.lon, stamp, unit.id) for unit in self.units.values()]
        try:
            # One connection and one transaction for the whole fleet — the old
            # per-unit commits opened a hundred connections every fifteen seconds.
            with self.store.connect() as connection:
                connection.executemany(
                    "UPDATE vehicles SET latitude = ?, longitude = ?, updated_at = ? WHERE id = ?",
                    payload,
                )
                connection.commit()
        except RuntimeError as error:
            # A transient database problem must never kill the feed loop; the
            # next commit interval will simply try again.
            logging.getLogger(__name__).warning("Live position commit skipped: %s", error)
            return
        for unit in self.units.values():
            known = self._known.get(unit.id)
            if known is not None:
                # Keep the fingerprint in step with the persisted position so
                # sync() does not mistake normal driving for a manual pin edit.
                self._known[unit.id] = known[:3] + (round(unit.lat, 4), round(unit.lon, 4))

    # -- reporting --------------------------------------------------------
    def status(self) -> str:
        if not self.running:
            return f"Feed paused · {len(self.units)} units"
        speeds = [unit.speed for unit in self.units.values()] or [0.0]
        return (
            f"Live · {len(self.units)} units · {sum(speeds) / len(speeds):.0f} km/h mean"
            f" · {self.speed:g}× · {self.elapsed / 60:.1f} min"
        )

    def live(self, vehicle_id: int) -> Unit | None:
        return self.units.get(vehicle_id)


class MapCanvas(tk.Canvas):
    """Vector basemap of Metro Manila with flood zones and fleet markers.

    The snapshot is read from the database once per ``reload()`` and cached, so
    dragging and zooming never touch SQLite. The projection is equirectangular
    with a per-axis kilometre scale, which keeps flood-zone rings round and
    true to scale at any zoom level.
    """

    MIN_SPAN = 1.2
    MAX_SPAN = 90.0
    HOME = (120.9890, 14.6050, 13.0)

    def __init__(
        self,
        master: tk.Widget,
        store: "Store",
        height: int = 320,
        on_select: Callable[[int], None] | None = None,
        on_click: Callable[[tuple[float, float]], None] | None = None,
        show_labels: bool = True,
        show_zones: bool = True,
        show_vehicles: bool = True,
        show_grid: bool = True,
        show_bookings: bool = False,
        show_customers: bool = False,
        legend: bool = True,
        border: bool = True,
        feed: "TrackingFeed | None" = None,
        detail: str = "medium",
    ) -> None:
        super().__init__(
            master,
            height=height,
            background=PALETTE["water"],
            highlightthickness=1 if border else 0,
            highlightbackground=PALETTE["line"],
            bd=0,
            takefocus=True,
        )
        self.store = store
        self.on_select = on_select
        self.on_click = on_click
        self.show_labels = show_labels
        self.show_zones = show_zones
        self.show_vehicles = show_vehicles
        self.show_grid = show_grid
        self.show_bookings = show_bookings
        self.show_customers = show_customers
        self.legend = legend
        self.detail = detail
        self.feed = feed
        self.center_lon, self.center_lat, self.span_km = self.HOME
        self.selected_id: int | None = None
        self.hover_id: int | None = None
        self.readout: tuple[float, float] = (self.center_lat, self.center_lon)
        self._drag: tuple[float, float] | None = None
        self._moved = False
        self._markers: dict[int, tuple[float, float]] = {}
        self._vehicles: list[dict[str, Any]] = []
        self._zones: list[dict[str, Any]] = []
        self._bookings: list[dict[str, Any]] = []
        self._customers: list[dict[str, Any]] = []
        self._anim: dict[str, Any] | None = None
        self._anim_job: str | None = None
        self._readout_box: int | None = None
        self._readout_text_id: int | None = None
        # layered rendering: the basemap only repaints when the view or the
        # data snapshot changes; feed ticks redraw just the live layer
        self._snapshot_version = 0
        self._base_signature: tuple[Any, ...] | None = None
        self._readout_shown: str | None = None

        self.bind("<Button-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Motion>", self._on_motion)
        self.bind("<Leave>", lambda _event: self._set_readout(None))
        self.bind("<Double-1>", self._on_double)
        self.bind("<MouseWheel>", self._on_wheel)
        self.bind("<Button-4>", lambda _event: self.zoom_by(0.86))
        self.bind("<Button-5>", lambda _event: self.zoom_by(1.16))
        self.bind("<Configure>", lambda _event: self.draw())
        for key in ("<Left>", "<Right>", "<Up>", "<Down>"):
            self.bind(key, self._on_arrow)
        for key in ("<plus>", "<equal>", "<KP_Add>"):
            self.bind(key, lambda _event: self.zoom_by(0.72))
        for key in ("<minus>", "<KP_Subtract>"):
            self.bind(key, lambda _event: self.zoom_by(1.38))
        self.bind("<Key-0>", lambda _event: self.reset())
        self.bind("<Key-f>", lambda _event: self.fit_fleet())
        self.bind("<Escape>", lambda _event: self.select(None))
        self.bind("<Destroy>", self._on_destroy)
        self.reload()
        if feed is not None:
            feed.subscribe(self)

    def _on_destroy(self, _event: tk.Event) -> None:
        self._cancel_anim()
        if self.feed is not None:
            self.feed.unsubscribe(self)

    # -- projection -------------------------------------------------------
    @property
    def scale(self) -> float:
        """Pixels per kilometre — identical on both axes."""
        return max(self.winfo_width(), 10) / self.span_km

    def project(self, lat: float, lon: float) -> tuple[float, float]:
        """(lat, lon) → canvas pixels, relative to the current camera centre.

        Both axes must measure from ``center_lat``/``center_lon`` — the y axis
        used to be pinned to the fixed CENTER_LAT constant, which silently
        broke vertical panning, follow-cam and zoom-to-point.
        """
        width, height = self.winfo_width(), self.winfo_height()
        x_km = (lon - self.center_lon) * KM_PER_DEG_LON
        y_km = (self.center_lat - lat) * KM_PER_DEG_LAT
        return width / 2 + x_km * self.scale, height / 2 + y_km * self.scale

    def unproject(self, x: float, y: float) -> tuple[float, float]:
        width, height = self.winfo_width(), self.winfo_height()
        x_km = (x - width / 2) / self.scale
        y_km = (y - height / 2) / self.scale
        return self.center_lat - y_km / KM_PER_DEG_LAT, self.center_lon + x_km / KM_PER_DEG_LON

    def visible(self, lat: float, lon: float, margin: float = 0.0) -> bool:
        x, y = self.project(lat, lon)
        return not self._outside(x, y, margin)

    # -- data -------------------------------------------------------------
    def reload(self) -> None:
        """Read a fresh snapshot from the database, then repaint."""
        self._vehicles = self.store.vehicles()
        self._zones = self.store.zones()
        self._bookings = (
            [row for row in self.store.bookings() if row.get("latitude") is not None and row.get("longitude") is not None]
            if self.show_bookings
            else []
        )
        self._customers = (
            [row for row in self.store.customers() if row.get("latitude") is not None and row.get("longitude") is not None]
            if self.show_customers
            else []
        )
        self._snapshot_version += 1
        self.draw()

    # -- interaction ------------------------------------------------------
    def _on_press(self, event: tk.Event) -> None:
        self._cancel_anim()
        self._drag = (event.x, event.y)
        self._moved = False
        self.focus_set()
        self._apply_cursor()

    def _on_drag(self, event: tk.Event) -> None:
        if not self._drag:
            return
        dx, dy = self._drag[0] - event.x, self._drag[1] - event.y
        if abs(dx) + abs(dy) > 2:
            self._moved = True
            self.follow_id = None  # a manual pan takes the camera off follow
        self.center_lon += dx / self.scale / KM_PER_DEG_LON
        self.center_lat += dy / self.scale / KM_PER_DEG_LAT
        self._drag = (event.x, event.y)
        self._apply_cursor()
        self.draw()

    def _on_release(self, event: tk.Event) -> None:
        self._drag = None
        self._apply_cursor()
        if self._moved:
            return
        if self.on_click is not None:
            self.on_click(self.unproject(event.x, event.y))
            return
        self.select(self.hover_id, notify=True)

    def _on_motion(self, event: tk.Event) -> None:
        self._set_readout(self.unproject(event.x, event.y))
        found = self._marker_at(event.x, event.y)
        if found != self.hover_id:
            self.hover_id = found
            self._apply_cursor()
            self.draw()

    def _marker_at(self, x: float, y: float) -> int | None:
        """Nearest vehicle marker within an eleven-pixel radius of the cursor."""
        best: tuple[float, int] | None = None
        for vehicle_id, (marker_x, marker_y) in self._markers.items():
            distance = (x - marker_x) ** 2 + (y - marker_y) ** 2
            if distance <= 121.0 and (best is None or distance < best[0]):
                best = (distance, vehicle_id)
        if best is not None:
            return best[1]
        if self.feed is None:
            return None
        # At high feed speeds the cached marker positions trail the live ones;
        # measure against the live feed before giving up.
        for vehicle in self._vehicles:
            if vehicle.get("latitude") is None or vehicle.get("longitude") is None:
                continue
            unit = self.feed.live(int(vehicle["id"]))
            if unit is None:
                continue
            live_x, live_y = self.project(unit.lat, unit.lon)
            if self._outside(live_x, live_y, 12):
                continue
            distance = (x - live_x) ** 2 + (y - live_y) ** 2
            if distance <= 121.0 and (best is None or distance < best[0]):
                best = (distance, int(vehicle["id"]))
        return best[1] if best is not None else None

    def _on_wheel(self, event: tk.Event) -> None:
        self.zoom_by(0.86 if event.delta > 0 else 1.16, at=(event.x, event.y))

    def _on_double(self, event: tk.Event) -> None:
        lat, lon = self.unproject(event.x, event.y)
        self.fly_to(lon, lat, self.span_km * 0.55)

    def _on_arrow(self, event: tk.Event) -> None:
        step = 70 / self.scale
        moves = {
            "Left": (-step, 0.0),
            "Right": (step, 0.0),
            "Up": (0.0, step),
            "Down": (0.0, -step),
        }
        dx, dy = moves.get(event.keysym, (0.0, 0.0))
        self.center_lon += dx / KM_PER_DEG_LON
        self.center_lat += dy / KM_PER_DEG_LAT
        self.draw()

    def _apply_cursor(self) -> None:
        if self._drag is not None:
            cursor = "fleur"
        elif self.hover_id is not None:
            cursor = "hand2"
        else:
            cursor = "crosshair"
        self.configure(cursor=cursor)

    # -- zoom and animation ----------------------------------------------
    def zoom_by(self, factor: float, at: tuple[float, float] | None = None) -> None:
        """Change the span, keeping the point under the cursor still."""
        self._cancel_anim()
        new_span = max(self.MIN_SPAN, min(self.MAX_SPAN, self.span_km * factor))
        if at is not None and new_span != self.span_km:
            width, height = self.winfo_width(), self.winfo_height()
            off_x_km = (at[0] - width / 2) / self.scale
            off_y_km = (at[1] - height / 2) / self.scale
            ratio = new_span / self.span_km
            self.center_lon += off_x_km * (1 - ratio) / KM_PER_DEG_LON
            self.center_lat -= off_y_km * (1 - ratio) / KM_PER_DEG_LAT
        self.span_km = new_span
        self.draw()

    def fly_to(self, lon: float, lat: float, span_km: float | None = None, ms: int = 340) -> None:
        """Ease the view towards a new centre and span."""
        self._cancel_anim()
        start = (self.center_lon, self.center_lat, self.span_km)
        end = (lon, lat, span_km if span_km else self.span_km)
        if sum(abs(start[index] - end[index]) for index in range(3)) < 1e-6:
            self.draw()
            return
        self._anim = {
            "start": start,
            "end": end,
            "steps": max(5, min(28, int(ms / 16))),
            "index": 0,
        }
        self._step_anim()

    def _step_anim(self) -> None:
        state = self._anim
        if state is None:
            return
        state["index"] += 1
        progress = min(state["index"] / state["steps"], 1.0)
        eased = 1 - (1 - progress) ** 3
        (s_lon, s_lat, s_span), (e_lon, e_lat, e_span) = state["start"], state["end"]
        self.center_lon = s_lon + (e_lon - s_lon) * eased
        self.center_lat = s_lat + (e_lat - s_lat) * eased
        self.span_km = s_span * (e_span / s_span) ** eased
        self.draw()
        if progress >= 1.0:
            self._anim = None
            self._anim_job = None
            return
        self._anim_job = self.after(16, self._step_anim)

    def _cancel_anim(self) -> None:
        self._anim = None
        if self._anim_job is not None:
            try:
                self.after_cancel(self._anim_job)
            except tk.TclError:  # pragma: no cover - already cancelled
                pass
            self._anim_job = None

    # -- public view controls --------------------------------------------
    def zoom_in(self) -> None:
        self.zoom_by(0.7)

    def zoom_out(self) -> None:
        self.zoom_by(1.42)

    def reset(self) -> None:
        self.follow_id = None
        lon, lat, span = self.HOME
        self.fly_to(lon, lat, span, ms=380)

    def fit_fleet(self) -> None:
        """Frame every unit in the fleet with a comfortable margin."""
        self.follow_id = None
        positioned: list[tuple[float, float]] = []
        for item in self._vehicles:
            live = self.feed.live(int(item["id"])) if self.feed is not None else None
            lat = live.lat if live is not None else item.get("latitude")
            lon = live.lon if live is not None else item.get("longitude")
            if lat is None or lon is None:
                continue
            positioned.append((float(lat), float(lon)))
        if not positioned:
            self.reset()
            return
        lats = [item[0] for item in positioned]
        lons = [item[1] for item in positioned]
        width_km = (max(lons) - min(lons)) * KM_PER_DEG_LON
        height_km = (max(lats) - min(lats)) * KM_PER_DEG_LAT
        aspect = self.winfo_width() / max(self.winfo_height(), 1)
        span = max(width_km, height_km * aspect) * 1.4 + 2.0
        self.fly_to(
            (min(lons) + max(lons)) / 2,
            (min(lats) + max(lats)) / 2,
            max(self.MIN_SPAN, min(self.MAX_SPAN, span)),
            ms=440,
        )

    def focus(self, vehicle_id: int | None, animate: bool = True, follow: bool = True) -> None:
        """Centre on a unit and keep the view locked while it drives."""
        self.selected_id = vehicle_id
        self.follow_id = vehicle_id if follow else None
        vehicle = next((item for item in self._vehicles if item["id"] == vehicle_id), None)
        if vehicle is None and vehicle_id is not None:
            # The cached snapshot may predate a just-added unit — ask the store
            # directly so pin-pointing a new unit never silently fails.
            vehicle = self.store.row("SELECT * FROM vehicles WHERE id = ?", (vehicle_id,))
        if vehicle is None or vehicle.get("latitude") is None or vehicle.get("longitude") is None:
            self.draw()
            return
        span = min(self.span_km, 7.0)
        if animate:
            self.fly_to(vehicle["longitude"], vehicle["latitude"], span, ms=380)
        else:
            self.center_lon, self.center_lat, self.span_km = vehicle["longitude"], vehicle["latitude"], span
            self.draw()

    def select(self, vehicle_id: int | None, notify: bool = False) -> None:
        if vehicle_id is None:
            self.follow_id = None  # clearing the selection releases the camera
        self.selected_id = vehicle_id
        self.draw()
        if notify and self.on_select is not None and vehicle_id is not None:
            self.on_select(vehicle_id)

    # -- painting ---------------------------------------------------------
    follow_id: int | None = None

    def draw(self, force: bool = False) -> None:
        """Repaint the map in two layers.

        The basemap (land, roads, labels, zones, pins) only rebuilds when the
        view or the data snapshot actually changes. The live layer — vehicle
        markers, trails, links and the overlay furniture — is redrawn on every
        call. The tracking feed lands here around ten times per second, and
        redrawing roughly a hundred canvas items instead of the whole city is
        what keeps pan, zoom and the animation smooth.
        """
        if self.follow_id is not None and self.feed is not None:
            unit = self.feed.live(self.follow_id)
            if unit is not None:
                self.center_lat, self.center_lon = unit.lat, unit.lon
        if self.winfo_width() < 24 or self.winfo_height() < 24:
            return
        signature = (
            round(self.center_lat, 7),
            round(self.center_lon, 7),
            round(self.span_km, 5),
            self.winfo_width(),
            self.winfo_height(),
            self._snapshot_version,
            self.show_labels,
            self.show_zones,
            self.show_grid,
            self.show_bookings,
            self.show_customers,
            self.detail,
        )
        if force or signature != self._base_signature:
            self._base_signature = signature
            self.delete("all")
            self._markers.clear()
            self._readout_box = None
            self._readout_text_id = None
            self._readout_shown = None
            self._draw_static()
        self._draw_dynamic()

    def _draw_static(self) -> None:
        """Everything that only changes with the view or a data reload."""
        self._draw_land()
        if self.show_grid:
            self._draw_graticule()
        self._draw_fabric()
        self._draw_rivers()
        self._draw_streets()
        self._draw_secondary()
        self._draw_roads()
        self._draw_road_names()
        if self.show_labels:
            self._draw_places()
        if self.show_zones:
            self._draw_zones()
        if self.show_bookings:
            self._draw_bookings()
        if self.show_customers:
            self._draw_customers()

    def _draw_dynamic(self) -> None:
        """Fleet markers and overlay furniture — cheap enough for every tick."""
        self.delete("live")
        self._markers.clear()
        if self.show_vehicles:
            self._draw_links()
            self._draw_vehicles()
        # Zone name pills belong to the top stratum: markers driving past must
        # never punch holes in the label text (they used to, because the live
        # layer is always stacked above the static one).
        if self.show_zones and self.show_labels and self.span_km <= 26:
            self._draw_zone_labels()
        self._draw_overlay()
        if self.show_vehicles:
            self.tag_raise("chip")  # the focused unit's caption stays on top

    def _draw_zone_labels(self) -> None:
        """Active-zone name pills, kept above the vehicle markers."""
        taken = self._reserved_boxes()
        for zone in sorted(self._zones, key=lambda item: RISK_SCORES.get(item["risk_level"], 0), reverse=True):
            if not zone["is_active"]:
                continue
            cx, cy = self.project(zone["latitude"], zone["longitude"])
            radius = max(zone["radius_km"] * self.scale, 4)
            if self._outside(cx, cy, radius):
                continue
            color = RISK_COLORS.get(zone["risk_level"], PALETTE["muted"])
            self._pill(
                cx, cy - radius - 14, zone["name"].upper(),
                suffix=ZONE_RISK_WORD.get(zone["risk_level"], ""), color=color, boxes=taken,
            )

    def _draw_land(self) -> None:
        width, height = self.winfo_width(), self.winfo_height()
        margin_x, margin_y = width * 1.5, height * 1.5
        points: list[float] = []
        for lat, lon in COASTLINE:
            points.extend(self.project(lat, lon))
        # Close the land mass well outside the visible area, but never in the
        # huge coordinates a degree-based margin would produce.
        right, bottom, top, left = width + margin_x, height + margin_y, -margin_y, -margin_x
        points.extend((right, bottom))
        points.extend((right, top))
        points.extend((left, top))
        self.create_polygon(points, fill=PALETTE["land"], outline=PALETTE["line"], width=1, tags=("base",))

        cx, cy = self.project(*LAKE_CENTER)
        rx, ry = LAKE_RADIUS[0] * self.scale, LAKE_RADIUS[1] * self.scale
        if not (cx + rx < 0 or cx - rx > width or cy + ry < 0 or cy - ry > height):
            self.create_oval(cx - rx, cy - ry, cx + rx, cy + ry, fill=PALETTE["water"], outline=PALETTE["water_deep"], width=1, tags=("base",))

        for (dx, dy), sx, sy in PARKS:
            x, y = self.project(*_ll(dx, dy))
            rx, ry = sx / 4997 * KM_PER_DEG_LON * self.scale, sy / 5132 * KM_PER_DEG_LAT * self.scale
            if self._outside(x, y, max(rx, ry)):
                continue
            self.create_oval(x - rx, y - ry, x + rx, y + ry, fill=PALETTE["park"], outline="", tags=("base",))

    def _draw_graticule(self) -> None:
        """Faint lat/lon grid that adapts its spacing to the zoom level."""
        width, height = self.winfo_width(), self.winfo_height()
        step = 0.5
        for candidate in (0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 0.25, 0.5, 1.0):
            step = candidate
            if candidate * KM_PER_DEG_LON * self.scale >= 110:
                break
        top_lat, left_lon = self.unproject(0, 0)
        bottom_lat, right_lon = self.unproject(width, height)
        # Keep the edge labels clear of the overlay furniture: the coordinate
        # readout sits top-left, the north arrow top-right, the scale bar
        # bottom-left, so labels are suppressed inside those rectangles.
        readout_right = self._text_width(FONTS["mono"], self._readout_text()) + 46
        lines = 0
        lon = math.floor(left_lon / step) * step
        while lon <= right_lon and lines < 40:
            x = self.project(CENTER_LAT, lon)[0]
            self.create_line(x, 0, x, height, fill="#E9ECE5", width=1, tags=("base",))
            if 40 < x < width - 74 and not (x < readout_right):
                self.create_text(x + 3, 7, text=f"{lon:.3f}°E", anchor="nw", font=FONTS["micro"], fill="#B3BCB4", tags=("base",))
            lon += step
            lines += 1
        lines = 0
        lat = math.floor(bottom_lat / step) * step
        while lat <= top_lat and lines < 40:
            y = self.project(lat, self.center_lon)[1]
            self.create_line(0, y, width, y, fill="#E9ECE5", width=1, tags=("base",))
            if 48 < y < height - 48:
                self.create_text(4, y - 3, text=f"{lat:.3f}°N", anchor="sw", font=FONTS["micro"], fill="#B3BCB4", tags=("base",))
            lat += step
            lines += 1

    def _draw_rivers(self) -> None:
        for _name, points, weight in RIVERS:
            flat: list[float] = []
            for lat, lon in points:
                flat.extend(self.project(lat, lon))
            if len(flat) < 4:
                continue
            width = max(1.6, min(9.0, self.scale * 0.05 * weight))
            self.create_line(flat, fill=PALETTE["water_deep"], width=width + 1.2, smooth=True, capstyle="round", tags=("base",))
            self.create_line(flat, fill=PALETTE["water"], width=width, smooth=True, capstyle="round", tags=("base",))

    def _draw_streets(self) -> None:
        """Minor street grid, faded out until there is room for it."""
        if self.scale < 11:
            return
        width = max(0.8, min(2.2, self.scale * 0.012))
        for start, end in STREETS:
            x1, y1 = self.project(*_ll(*start))
            x2, y2 = self.project(*_ll(*end))
            if self._outside(x1, y1, 260) and self._outside(x2, y2, 260):
                continue
            self.create_line(x1, y1, x2, y2, fill=PALETTE["grid"], width=width, tags=("base",))

    def _draw_roads(self) -> None:
        """Two passes so the casings merge underneath the white road surface."""
        casing = max(3.0, min(14.0, self.scale * 0.09))
        surface = max(1.6, min(9.2, self.scale * 0.06))
        paths: list[list[float]] = []
        for _name, points in ARTERIALS:
            flat: list[float] = []
            for lat, lon in points:
                flat.extend(self.project(lat, lon))
            if len(flat) >= 4:
                paths.append(flat)
        for flat in paths:
            self.create_line(flat, fill=PALETTE["road_edge"], width=casing, smooth=True, capstyle="round", joinstyle="round", tags=("base",))
        for flat in paths:
            self.create_line(flat, fill=PALETTE["road"], width=surface, smooth=True, capstyle="round", joinstyle="round", tags=("base",))

    def _reserved_boxes(self) -> list[tuple[float, float, float, float]]:
        """Regions claimed by the overlay furniture, so labels never collide."""
        width, height = self.winfo_width(), self.winfo_height()
        boxes: list[tuple[float, float, float, float]] = [
            (14, 12, 14 + self._text_width(FONTS["mono"], self._readout_text()) + 18, 36),  # coordinate readout
            (width - 37, 10, width - 9, 46),      # north arrow
            (14, height - 38, 235, height - 4),   # scale bar
        ]
        if self.legend and self.show_vehicles:
            boxes.append((width - 118, height - 97, width - 10, height - 30))
        if self.follow_id is not None:
            followed = next((item for item in self._vehicles if item["id"] == self.follow_id), None)
            if followed is not None:
                text = f"Following {followed['plate_number']} · Esc releases the camera"
                box_w = self._text_width(FONTS["micro_bold"], text) + 20
                centre_x = width / 2
                top = 44 if centre_x - box_w / 2 < 150 else 12
                boxes.append((centre_x - box_w / 2, top, centre_x + box_w / 2, top + 22))
        return boxes

    def _draw_zones(self) -> None:
        for zone in sorted(self._zones, key=lambda item: RISK_SCORES.get(item["risk_level"], 0), reverse=True):
            color = RISK_COLORS.get(zone["risk_level"], PALETTE["muted"])
            tint = ZONE_TINTS.get(zone["risk_level"], "#F1F2EC")
            cx, cy = self.project(zone["latitude"], zone["longitude"])
            radius = max(zone["radius_km"] * self.scale, 4)
            if self._outside(cx, cy, radius):
                continue
            if zone["is_active"]:
                self.create_oval(cx - radius, cy - radius, cx + radius, cy + radius, fill=tint, outline="", tags=("base",))
                # a quiet solid ring — dashed strokes read as "drafting" noise
                self.create_oval(cx - radius, cy - radius, cx + radius, cy + radius, outline=_mix(color, "#FFFFFF", 0.30), width=1.4, tags=("base",))
                self.create_oval(cx - 2.4, cy - 2.4, cx + 2.4, cy + 2.4, fill=color, outline="", tags=("base",))
            else:
                self.create_oval(cx - radius, cy - radius, cx + radius, cy + radius, outline=PALETTE["faint"], width=1, dash=(2, 4), tags=("base",))
                self.create_oval(cx - 2, cy - 2, cx + 2, cy + 2, fill=PALETTE["faint"], outline="", tags=("base",))

    def _draw_bookings(self) -> None:
        """Pickup pins for bookings that carry a map position."""
        taken = self._reserved_boxes()
        for booking in self._bookings:
            if booking["status"] not in ("pending", "confirmed", "ongoing"):
                continue
            x, y = self.project(booking["latitude"], booking["longitude"])
            if self._outside(x, y, 60):
                continue
            size = 5.5
            self.create_polygon(
                x, y - size, x + size, y, x, y + size, x - size, y,
                fill=PALETTE["info"], outline="", smooth=False, tags=("base",),
            )
            self.create_oval(x - 1.6, y - 1.6, x + 1.6, y + 1.6, fill="#FFFFFF", outline="", tags=("base",))
            if self.show_labels and self.span_km <= 24:
                self._pill(
                    x, y - size - 13, booking["booking_code"],
                    suffix=str(booking.get("customer_name") or ""), color=PALETTE["info"],
                    suffix_color=PALETTE["muted"], boxes=taken,
                )

    def _draw_customers(self) -> None:
        """Saved home pins for customers who were given a map position."""
        taken = self._reserved_boxes()
        for customer in self._customers:
            x, y = self.project(customer["latitude"], customer["longitude"])
            if self._outside(x, y, 60):
                continue
            round_rect(self, x - 5.5, y - 5.5, x + 5.5, y + 5.5, radius=3.5, fill=PALETTE["ink"], outline="", tags=("base",))
            initial = str(customer.get("full_name") or "?").strip()[:1].upper() or "?"
            self.create_text(x, y + 0.2, text=initial, font=FONTS["micro_bold"], fill="#FFFFFF", tags=("base",))
            if self.show_labels and self.span_km <= 20:
                self._pill(x, y - 17, str(customer.get("full_name") or ""), color=PALETTE["ink"], boxes=taken)

    def _draw_secondary(self) -> None:
        """Minor arterials: thinner casing, slightly grey surface."""
        if self.scale < 3 * self._detail_factor():
            return
        casing = max(1.6, min(7.0, self.scale * 0.045))
        surface = max(0.8, min(4.6, self.scale * 0.028))
        for points in SECONDARY_ROADS:
            flat: list[float] = []
            for lat, lon in points:
                flat.extend(self.project(lat, lon))
            if self._offscreen_polyline(flat, 120):
                continue
            self.create_line(flat, fill="#E3E6DC", width=casing, smooth=True, capstyle="round", tags=("base",))
            self.create_line(flat, fill="#FAFAF6", width=surface, smooth=True, capstyle="round", tags=("base",))

    def _detail_factor(self) -> float:
        """Zoom threshold multiplier driven by the 'map detail' setting."""
        return {"low": 1.7, "medium": 1.0, "high": 0.55}.get(self.detail, 1.0)

    def _draw_fabric(self) -> None:
        """City blocks under the road network, so street level reads as a city."""
        if self.scale < 26 * self._detail_factor():
            return
        width, height = self.winfo_width(), self.winfo_height()
        block = 0.24
        columns = int(self.span_km / block) + 2
        rows = int(self.span_km * height / max(width, 1) / block) + 2
        if columns * rows > 620 or columns < 1 or rows < 1:
            return
        detailed = self.scale > 70
        fill = "#EDEEE5" if detailed else "#EEEFE8"
        edge = "#E4E5DC" if detailed else ""
        half_i, half_j = columns // 2, rows // 2
        for i in range(-half_i, half_i + 1):
            for j in range(-half_j, half_j + 1):
                x_km = i * block
                y_km = j * block
                lat = self.center_lat - y_km / KM_PER_DEG_LAT
                lon = self.center_lon + x_km / KM_PER_DEG_LON
                if not self._on_land(lat, lon):
                    continue
                width_km = block * (0.34 + 0.30 * _hash(i, j, 1))
                height_km = block * (0.30 + 0.34 * _hash(i, j, 2))
                cx, cy = self.project(lat, lon)
                if self._outside(cx, cy, block * self.scale):
                    continue
                ax = cx - width_km / 2 * self.scale
                bx = cx + width_km / 2 * self.scale
                ay = cy - height_km / 2 * self.scale
                by = cy + height_km / 2 * self.scale
                self.create_rectangle(ax, ay, bx, by, fill=fill, outline=edge, tags=("base",))

    def _draw_road_names(self) -> None:
        """Arterial names along the road, rotated to match the segment."""
        if self.scale < 16:
            return
        width, height = self.winfo_width(), self.winfo_height()
        cx, cy = width / 2, height / 2
        for name, points in ARTERIALS:
            best: tuple[float, float, float, float, float] | None = None
            for index in range(len(points) - 1):
                ax, ay = self.project(*points[index])
                bx, by = self.project(*points[index + 1])
                if max(ax, bx) < 30 or min(ax, bx) > width - 30 or max(ay, by) < 30 or min(ay, by) > height - 30:
                    continue
                middle_x, middle_y = (ax + bx) / 2, (ay + by) / 2
                offset = math.hypot(middle_x - cx, middle_y - cy)
                length = math.hypot(bx - ax, by - ay)
                if length < 52:
                    continue
                if best is None or offset < best[0]:
                    best = (offset, ax, ay, bx, by)
            if best is None:
                continue
            _offset, ax, ay, bx, by = best
            angle = math.degrees(math.atan2(by - ay, bx - ax))
            if angle > 90:
                angle -= 180
            elif angle < -90:
                angle += 180
            middle_x, middle_y = (ax + bx) / 2, (ay + by) / 2
            for dx, dy in ((-0.7, 0), (0, -0.7)):
                self.create_text(
                    middle_x + dx, middle_y + dy, text=name.upper(), angle=angle,
                    font=FONTS["micro"], fill=PALETTE["road"], tags=("base",),
                )
            self.create_text(
                middle_x, middle_y, text=name.upper(), angle=angle,
                font=FONTS["micro"], fill="#A8B1A8", tags=("base",),
            )

    def _draw_places(self) -> None:
        if self.scale > 85:
            for name, x, y in DISTRICTS:
                lat, lon = _ll(x, y)
                if not self.visible(lat, lon, 40):
                    continue
                px, py = self.project(lat, lon)
                for dx, dy in ((-0.7, 0), (0, -0.7)):
                    self.create_text(px + dx, py + dy, text=name, font=FONTS["micro"], fill=PALETTE["land"], tags=("base",))
                self.create_text(px, py, text=name, font=FONTS["micro"], fill="#B4BBAF", tags=("base",))
        for text, lat, lon, kind in MAP_LABELS:
            if not self.visible(lat, lon, 50):
                continue
            x, y = self.project(lat, lon)
            label = text.upper() if kind == "city" else text
            font = FONTS["small"] if kind == "city" else FONTS["micro"]
            fill = "#9CA49C" if kind == "city" else "#94A9A6"
            for dx, dy in ((-0.9, 0), (0, -0.9)):
                self.create_text(x + dx, y + dy, text=label, font=font, fill=PALETTE["land"], tags=("base",))
            self.create_text(x, y, text=label, font=font, fill=fill, tags=("base",))

    def _on_land(self, lat: float, lon: float) -> bool:
        """East of the coast, outside the lake and clear of the parks."""
        if lat < COASTLINE[-1][0] or lat > COASTLINE[0][0]:
            return False
        boundary = self._coast_lon(lat)
        if boundary is None or lon < boundary:
            return False
        delta_lat = (lat - LAKE_CENTER[0]) * KM_PER_DEG_LAT
        delta_lon = (lon - LAKE_CENTER[1]) * KM_PER_DEG_LON
        if (delta_lat / max(LAKE_RADIUS[1], 0.1)) ** 2 + (delta_lon / max(LAKE_RADIUS[0], 0.1)) ** 2 < 1.6:
            return False
        for (dx, dy), sx, sy in PARKS:
            park_lat, park_lon = _ll(dx, dy)
            if abs(lat - park_lat) * KM_PER_DEG_LAT < sy / 5132 * KM_PER_DEG_LAT and abs(lon - park_lon) * KM_PER_DEG_LON < sx / 4997 * KM_PER_DEG_LON:
                return False
        return True

    @staticmethod
    def _coast_lon(lat: float) -> float | None:
        previous = COASTLINE[0]
        for point in COASTLINE[1:]:
            if previous[0] >= lat >= point[0]:
                span = previous[0] - point[0]
                if span <= 0:
                    return previous[1]
                ratio = (previous[0] - lat) / span
                return previous[1] + (point[1] - previous[1]) * ratio
            previous = point
        return None

    def _offscreen_polyline(self, flat: list[float], pad: float) -> bool:
        if len(flat) < 4:
            return True
        width, height = self.winfo_width(), self.winfo_height()
        xs = flat[0::2]
        ys = flat[1::2]
        return (
            max(xs) < -pad or min(xs) > width + pad or max(ys) < -pad or min(ys) > height + pad
        )

    def _draw_vehicles(self) -> None:
        radius = max(3.6, min(6.2, self.scale * 0.048))
        taken: list[tuple[float, float, float, float]] = []
        # Draw the focused unit last so it always sits on top of its neighbours.
        ordered = sorted(
            self._vehicles,
            key=lambda vehicle: (vehicle["id"] == self.selected_id, vehicle["id"] == self.hover_id),
        )
        for vehicle in ordered:
            if vehicle.get("latitude") is None or vehicle.get("longitude") is None:
                continue
            live = self.feed.live(vehicle["id"]) if self.feed is not None else None
            lat = live.lat if live else vehicle["latitude"]
            lon = live.lon if live else vehicle["longitude"]
            x, y = self.project(lat, lon)
            if not self._outside(x, y, 12):
                # Register the marker only when it is actually reachable by
                # the cursor, so edge clicks never select an off-screen unit.
                self._markers[vehicle["id"]] = (x, y)
            if self._outside(x, y, 40):
                continue
            color = STATUS_COLORS.get(vehicle["status"], PALETTE["accent"])
            active = vehicle["id"] in (self.selected_id, self.hover_id)

            # Trails and fading breadcrumbs are reserved for the focused unit —
            # on a hundred-unit fleet they turn the whole map into speckle.
            if active and live is not None and len(live.trail) > 2 and self.scale > 4:
                trail = live.trail if not live.parked else live.trail[-14:]
                flat: list[float] = []
                for trail_lat, trail_lon in trail:
                    trail_x, trail_y = self.project(trail_lat, trail_lon)
                    if self._outside(trail_x, trail_y, 60):
                        continue
                    flat.extend((trail_x, trail_y))
                if len(flat) >= 6:
                    self.create_line(
                        flat, fill=_mix(PALETTE["land"], color, 0.34),
                        width=max(1.0, radius * 0.3), smooth=True, capstyle="round", tags=("live",),
                    )
                    total = len(trail)
                    step = 2 if total > 10 else 1
                    for index in range(0, total, step):
                        trail_x, trail_y = self.project(*trail[index])
                        if self._outside(trail_x, trail_y, 30):
                            continue
                        depth = (index + 1) / total
                        halo = 0.8 + 1.4 * depth
                        self.create_oval(
                            trail_x - halo, trail_y - halo, trail_x + halo, trail_y + halo,
                            fill=_mix(PALETTE["land"], color, 0.22 + 0.55 * depth), outline="", tags=("live",),
                        )

            # A slim heading arrow that starts past the halo — motion without
            # turning the marker into a pin-shaped blob.
            if live is not None and not live.parked and self.scale > 3:
                radians = math.radians(live.heading)
                north_s, east_w = math.sin(radians), -math.cos(radians)
                self.create_line(
                    x + east_w * (radius + 2.6), y + north_s * (radius + 2.6),
                    x + east_w * (radius + 7.4), y + north_s * (radius + 7.4),
                    fill=_mix(color, "#FFFFFF", 0.10), width=1.8, capstyle="round",
                    arrow="last", arrowshape=(3.4, 5.2, 2.0), tags=("live",),
                )

            # White halo underneath keeps the disc crisp over roads and tints.
            halo = radius + 1.9
            self.create_oval(x - halo, y - halo, x + halo, y + halo, fill="#FFFFFF", outline="", tags=("live",))
            disc = radius + 1.1 if active else radius
            self.create_oval(x - disc, y - disc, x + disc, y + disc, fill=color, outline="", tags=("live",))

            if vehicle["id"] == self.selected_id:
                for ring_radius, fade in ((radius + 6.0, 0.42), (radius + 10.0, 0.20)):
                    self.create_oval(
                        x - ring_radius, y - ring_radius, x + ring_radius, y + ring_radius,
                        outline=_mix(color, "#FFFFFF", fade), width=1.4, tags=("live",),
                    )

            if active:
                detail = vehicle["plate_number"]
                if live is not None and not live.parked:
                    detail = f"{vehicle['plate_number']}  ·  {live.speed:.0f} km/h {compass_text(live.heading)}"
                elif live is not None:
                    detail = f"{vehicle['plate_number']}  ·  parked"
                self._chip(
                    x + radius + 14, y, f"{vehicle['brand']} {vehicle['model']}",
                    sub=detail, color=color, boxes=taken, centered=False, tags="live",
                )

    def _draw_links(self) -> None:
        """Join the focused unit to its nearest active zone with the distance."""
        if self.selected_id is None:
            return
        vehicle = next((item for item in self._vehicles if item["id"] == self.selected_id), None)
        if vehicle is None:
            return
        if vehicle.get("latitude") is None or vehicle.get("longitude") is None:
            return  # unit without a GPS fix — nothing to anchor the link to
        best: tuple[dict[str, Any], float] | None = None
        for zone in self._zones:
            if not zone["is_active"]:
                continue
            kilometres = distance_km(vehicle["latitude"], vehicle["longitude"], zone["latitude"], zone["longitude"])
            if best is None or kilometres < best[1]:
                best = (zone, kilometres)
        if best is None:
            return
        zone, kilometres = best
        color = RISK_COLORS.get(zone["risk_level"], PALETTE["muted"])
        x1, y1 = self.project(vehicle["latitude"], vehicle["longitude"])
        x2, y2 = self.project(zone["latitude"], zone["longitude"])
        self.create_line(x1, y1, x2, y2, fill=_mix(color, "#FFFFFF", 0.18), width=1.2, dash=(4, 3), tags=("live",))
        self._pill((x1 + x2) / 2, (y1 + y2) / 2, f"{kilometres:.2f} km", color=color, tags="live")

    def _draw_overlay(self) -> None:
        """Scale bar, legend, north arrow, coordinate readout and attribution."""
        width, height = self.winfo_width(), self.winfo_height()

        kilometres = self._nice_distance()
        length = kilometres * self.scale
        round_rect(self, 14, height - 34, 52 + length, height - 8, radius=7, fill=PALETTE["surface"], outline=PALETTE["line"], tags=("live",))
        self.create_line(24, height - 15, 24 + length, height - 15, fill=PALETTE["ink_soft"], width=2, tags=("live",))
        for tick in (24, 24 + length):
            self.create_line(tick, height - 20, tick, height - 10, fill=PALETTE["ink_soft"], width=2, tags=("live",))
        self.create_text(
            24 + length + 8, height - 15, text=f"{kilometres:g} km",
            anchor="w", font=FONTS["micro"], fill=PALETTE["muted"], tags=("live",),
        )

        if self.legend and self.show_vehicles:
            entries = (
                ("Available", STATUS_COLORS["available"]),
                ("Rented", STATUS_COLORS["rented"]),
                ("Maintenance", STATUS_COLORS["maintenance"]),
            )
            box_width, box_height = 108, 14 + len(entries) * 16
            left, bottom = width - 14, height - 34
            round_rect(self, left - box_width, bottom - box_height, left, bottom, radius=9, fill=PALETTE["surface"], outline=PALETTE["line"], tags=("live",))
            for index, (label, color) in enumerate(entries):
                cy = bottom - box_height + 15 + index * 16
                self.create_oval(left - box_width + 11, cy - 3, left - box_width + 17, cy + 3, fill=color, outline="", tags=("live",))
                self.create_text(left - box_width + 24, cy, text=label, anchor="w", font=FONTS["micro"], fill=PALETTE["ink_soft"], tags=("live",))

        self.create_text(
            width - 10, height - 10, text="© OpenStreetMap contributors",
            anchor="e", font=FONTS["micro"], fill="#A7AFA9", tags=("live",),
        )

        north = width - 23
        round_rect(self, width - 33, 12, width - 13, 42, radius=7, fill=PALETTE["surface"], outline=PALETTE["line"], tags=("live",))
        self.create_text(north, 22, text="N", font=FONTS["micro_bold"], fill=PALETTE["ink"], tags=("live",))
        self.create_polygon(north - 4, 36, north + 4, 36, north, 27, fill=PALETTE["accent"], outline="", tags=("live",))

        if self.follow_id is not None:
            followed = next((item for item in self._vehicles if item["id"] == self.follow_id), None)
            if followed is not None:
                text = f"Following {followed['plate_number']} · Esc releases the camera"
                box_width = self._text_width(FONTS["micro_bold"], text) + 20
                centre_x = width / 2
                # Sit below the coordinate readout so the two never collide.
                top = 44 if centre_x - box_width / 2 < 150 else 12
                round_rect(
                    self, centre_x - box_width / 2, top, centre_x + box_width / 2, top + 22,
                    radius=7, fill=PALETTE["surface"], outline=PALETTE["line"], tags=("live",),
                )
                self.create_text(
                    centre_x, top + 11, text=text, font=FONTS["micro_bold"], fill=PALETTE["accent"], tags=("live",),
                )

        text = self._readout_text()
        box_width = self._text_width(FONTS["mono"], text) + 18
        self._readout_box = round_rect(self, 14, 12, 14 + box_width, 36, radius=9, fill=PALETTE["surface"], outline=PALETTE["line"], tags=("live",))
        self._readout_text_id = self.create_text(
            23, 24, text=text, anchor="w", font=FONTS["mono"], fill=PALETTE["ink_soft"], tags=("live",)
        )
        self._readout_shown = text

    # -- helpers ----------------------------------------------------------
    def _pill(
        self,
        x: float,
        y: float,
        text: str,
        suffix: str = "",
        color: str | None = None,
        suffix_color: str | None = None,
        boxes: list[tuple[float, float, float, float]] | None = None,
        centered: bool = True,
        tags: str = "base",
    ) -> None:
        """Compact single-line label: coloured dot, bold name, quiet suffix.

        Skipped entirely when it would cover a label that is already down.
        """
        dot_w = 15.0 if color else 6.0
        name_w = max(self._text_width(FONTS["micro_bold"], text), 10)
        suffix_w = self._text_width(FONTS["micro_bold"], suffix) + 6 if suffix else 0.0
        box_w = dot_w + name_w + suffix_w + 12
        box_h = 18
        x0 = x - box_w / 2 if centered else x
        y0 = y - box_h / 2
        box = (x0, y0, x0 + box_w, y0 + box_h)
        if boxes is not None:
            for other in boxes:
                if not (box[2] < other[0] or box[0] > other[2] or box[3] < other[1] or box[1] > other[3]):
                    return
            boxes.append(box)
        round_rect(self, box[0] + 1, box[1] + 2, box[2] + 1, box[3] + 2, radius=9, fill=PALETTE["line_soft"], outline="", tags=(tags,))
        round_rect(self, *box, radius=9, fill=PALETTE["surface"], outline=PALETTE["line"], tags=(tags,))
        left = box[0] + 6
        if color:
            self.create_oval(left, y - 2.3, left + 4.6, y + 2.3, fill=color, outline="", tags=(tags,))
        cursor = left + (10.5 if color else 0)
        self.create_text(cursor, y, text=text, anchor="w", font=FONTS["micro_bold"], fill=PALETTE["ink"], tags=(tags,))
        if suffix:
            self.create_text(
                cursor + name_w + 5, y, text=suffix, anchor="w", font=FONTS["micro_bold"],
                fill=suffix_color or color or PALETTE["muted"], tags=(tags,),
            )

    def _chip(
        self,
        x: float,
        y: float,
        text: str,
        sub: str = "",
        color: str | None = None,
        boxes: list[tuple[float, float, float, float]] | None = None,
        centered: bool = True,
        tags: str = "base",
    ) -> None:
        """Two-line label for the focused unit — title, quiet detail line."""
        width = max(self._text_width(FONTS["micro_bold"], text), self._text_width(FONTS["micro"], sub))
        padding = 22 if color else 14
        box_w = width + padding
        box_h = 28 if sub else 18
        x0 = x - box_w / 2 if centered else x
        y0 = y - box_h / 2
        box = (x0, y0, x0 + box_w, y0 + box_h)
        if boxes is not None:
            for other in boxes:
                if not (box[2] < other[0] or box[0] > other[2] or box[3] < other[1] or box[1] > other[3]):
                    return
            boxes.append(box)
        round_rect(self, box[0] + 1, box[1] + 2, box[2] + 1, box[3] + 2, radius=8, fill=PALETTE["line_soft"], outline="", tags=(tags, "chip"))
        round_rect(self, *box, radius=8, fill=PALETTE["surface"], outline=PALETTE["line"], tags=(tags, "chip"))
        if color:
            self.create_rectangle(box[0], box[1] + 1, box[0] + 2.5, box[3] - 1, fill=color, outline="", tags=(tags, "chip"))
        self.create_text(box[0] + (11 if color else 7), box[1] + (7 if sub else 9), text=text, anchor="w", font=FONTS["micro_bold"], fill=PALETTE["ink"], tags=(tags, "chip"))
        if sub:
            self.create_text(box[0] + (11 if color else 7), box[1] + 19, text=sub, anchor="w", font=FONTS["micro"], fill=PALETTE["muted"], tags=(tags, "chip"))

    @staticmethod
    def _text_width(font: tkfont.Font, text: str) -> int:
        return max(int(font.measure(text)), 8)

    def _outside(self, x: float, y: float, pad: float = 0.0) -> bool:
        return x < -pad or x > self.winfo_width() + pad or y < -pad or y > self.winfo_height() + pad

    def _nice_distance(self) -> float:
        """Round distance whose bar measures roughly ninety pixels."""
        for step in NICE_STEPS:
            if step * self.scale >= 92:
                return step
        return NICE_STEPS[-1]

    def _readout_text(self) -> str:
        lat, lon = self.readout
        return f"{lat:.4f}°N {lon:.4f}°E  ·  {self.span_km:.1f} km"

    def _set_readout(self, position: tuple[float, float] | None) -> None:
        self.readout = position if position is not None else (self.center_lat, self.center_lon)
        text = self._readout_text()
        if text == self._readout_shown:
            return  # same corner of the map — leave the overlay untouched
        self._readout_shown = text
        try:
            if self._readout_text_id is None or not self.type(self._readout_text_id):
                return
            self.itemconfigure(self._readout_text_id, text=text)
            wanted = self._text_width(FONTS["mono"], text) + 18
            if self._readout_box is not None:
                coords = self.coords(self._readout_box)
                if coords and abs((coords[2] - coords[0]) - wanted) > 6:
                    self.delete(self._readout_box)
                    self._readout_box = round_rect(
                        self, 14, 12, 14 + wanted, 36,
                        radius=9, fill=PALETTE["surface"], outline=PALETTE["line"], tags=("live",),
                    )
            self.tag_raise(self._readout_text_id)
        except tk.TclError:  # widget already gone
            pass


# ---------------------------------------------------------------------------
# Security and validation
# ---------------------------------------------------------------------------

PBKDF2_ITERATIONS = 260_000


def hash_password(password: str) -> tuple[str, str]:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return salt.hex(), digest.hex()


def verify_password(password: str, salt_hex: str, digest_hex: str) -> bool:
    try:
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
    except (TypeError, ValueError):
        return False
    if not password or not salt or not expected:
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return hmac.compare_digest(digest, expected)


def money(value: Any) -> str:
    try:
        amount = float(value or 0)
    except (TypeError, ValueError):
        amount = 0.0
    return f"{CURRENCY_SYMBOL}{amount:,.0f}"


def valid_date(text: str) -> bool:
    """True when the text is a real YYYY-MM-DD calendar date."""
    try:
        datetime.strptime(str(text).strip(), DATE_FORMAT)
        return True
    except (TypeError, ValueError):
        return False


def normalise_date(text: Any) -> str:
    """Canonical YYYY-MM-DD for storage, or a clear error the UI can show."""
    cleaned = str(text or "").strip()
    try:
        return datetime.strptime(cleaned, DATE_FORMAT).strftime(DATE_FORMAT)
    except ValueError:
        raise ValueError(f"'{cleaned or 'empty'}' is not a valid date — use YYYY-MM-DD.") from None


def rental_days_between(start: str, end: str) -> int | None:
    """Whole days between two ISO dates, or None when the range is invalid."""
    if not valid_date(start) or not valid_date(end):
        return None
    fmt = "%Y-%m-%d"
    start_day = datetime.strptime(start.strip(), fmt)
    end_day = datetime.strptime(end.strip(), fmt)
    days = (end_day - start_day).days
    return days if days >= 0 else None


def _short(value: float) -> str:
    return f"{value:,.0f}" if value >= 1000 else f"{value:g}"


MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _monthly_labels(rows: list[tuple[str, float]]) -> list[tuple[str, float]]:
    """Chart window: the last six calendar months, zero-filled, 'Feb' labels.

    Padding the empty months keeps the columns comparable — previously a
    single month of data rendered as one oversized block filling the card.
    """
    totals: dict[str, float] = {}
    for key, value in rows:
        try:
            totals[key] = totals.get(key, 0.0) + float(value)
        except (TypeError, ValueError):
            continue
    now = datetime.now()
    window: list[tuple[str, float]] = []
    for offset in range(5, -1, -1):
        month = now.month - offset
        year = now.year
        while month <= 0:
            month += 12
            year -= 1
        key = f"{year:04d}-{month:02d}"
        label = MONTH_NAMES[month - 1]
        window.append((label, round(totals.get(key, 0.0), 2)))
    if rows and not any(value for _label, value in window):
        # all activity predates the window — anchor six months on the newest
        # month that actually has data, zero-filling the months before it
        latest = max(totals)
        try:
            anchor_year, anchor_month = int(latest.split("-")[0]), int(latest.split("-")[1])
        except (IndexError, ValueError):
            anchor_year, anchor_month = now.year, now.month
        window = []
        for offset in range(5, -1, -1):
            month = anchor_month - offset
            year = anchor_year
            while month <= 0:
                month += 12
                year -= 1
            key = f"{year:04d}-{month:02d}"
            window.append((MONTH_NAMES[month - 1], round(totals.get(key, 0.0), 2)))
    return window


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    h = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2) ** 2
    )
    return 2 * radius * math.asin(math.sqrt(h))


def coordinate_text(value: Any) -> str:
    """Render a coordinate for the UI, tolerating units without a GPS fix."""
    try:
        return "—" if value is None else f"{float(value):.4f}"
    except (TypeError, ValueError):
        return "—"


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    full_name TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'staff',
    password_salt TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    last_seen TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS vehicles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plate_number TEXT NOT NULL UNIQUE COLLATE NOCASE,
    brand TEXT NOT NULL,
    model TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'Sedan',
    year INTEGER NOT NULL DEFAULT 2020,
    seats INTEGER NOT NULL DEFAULT 4,
    rate_per_day REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'available',
    latitude REAL,
    longitude REAL,
    odometer INTEGER NOT NULL DEFAULT 0,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    phone TEXT NOT NULL,
    email TEXT,
    id_type TEXT NOT NULL DEFAULT 'Drivers License',
    id_number TEXT,
    license_number TEXT,
    address TEXT,
    latitude REAL,
    longitude REAL,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS flood_zones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    barangay TEXT,
    risk_level TEXT NOT NULL DEFAULT 'moderate',
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    radius_km REAL NOT NULL DEFAULT 1.0,
    is_active INTEGER NOT NULL DEFAULT 1,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bookings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    booking_code TEXT NOT NULL UNIQUE,
    vehicle_id INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE RESTRICT,
    customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE RESTRICT,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    pickup_location TEXT,
    destination TEXT,
    rental_days INTEGER NOT NULL DEFAULT 1,
    rate_per_day REAL NOT NULL DEFAULT 0,
    total_amount REAL NOT NULL DEFAULT 0,
    deposit REAL NOT NULL DEFAULT 0,
    pickup_latitude REAL,
    pickup_longitude REAL,
    status TEXT NOT NULL DEFAULT 'pending',
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reference TEXT NOT NULL UNIQUE,
    booking_id INTEGER REFERENCES bookings(id) ON DELETE CASCADE,
    amount REAL NOT NULL DEFAULT 0,
    method TEXT NOT NULL DEFAULT 'cash',
    entry_type TEXT NOT NULL DEFAULT 'payment',
    paid_at TEXT NOT NULL,
    recorded_by TEXT,
    notes TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'info',
    source TEXT NOT NULL DEFAULT 'manual',
    vehicle_id INTEGER REFERENCES vehicles(id) ON DELETE CASCADE,
    zone_id INTEGER REFERENCES flood_zones(id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'new',
    created_by TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

VEHICLE_CATALOG = (
    ("Toyota", ("Land Cruiser 300", "Hilux 4×4", "Fortuner", "4Runner", "Tacoma TRD Pro")),
    ("Land Rover", ("Defender 110", "Defender 130", "Range Rover", "Discovery", "Range Rover Sport")),
    ("Ford", ("Ranger Raptor", "Bronco", "Everest", "F-150 Raptor", "Expedition")),
    ("Jeep", ("Wrangler Rubicon", "Gladiator", "Grand Cherokee Trailhawk", "Cherokee Trailhawk", "Renegade Trailhawk")),
    ("Nissan", ("Patrol", "Navara 4×4", "Terra", "Pathfinder", "Armada")),
    ("Isuzu", ("D-Max 4×4", "mu-X", "D-Max AT35", "mu-X RS", "D-Max X-Terrain")),
    ("Mitsubishi", ("Pajero Sport", "Strada / Triton 4×4", "Montero Sport", "Outlander PHEV", "L200 4×4")),
    ("Chevrolet", ("Colorado ZR2", "Tahoe", "Suburban", "Silverado Trail Boss", "Trailblazer")),
    ("GMC", ("Sierra AT4X", "Yukon XL", "Canyon AT4", "Acadia AT4", "Hummer EV SUV")),
    ("Subaru", ("Crosstrek Wilderness", "Outback Wilderness", "Forester Wilderness", "Ascent", "WRX")),
    ("Mercedes-Benz", ("G-Class", "G 63", "GLE 4×4²", "GLS", "GLC Off-Road")),
    ("Suzuki", ("Jimny Sierra", "Jimny 5-Door", "Ertiga", "Vitara AllGrip", "SX4 S-Cross")),
    ("Kia", ("Mohave / Borrego", "Sorento X-Pro", "Telluride X-Pro", "Sportage X-Line", "Seltos")),
    ("Hyundai", ("Terracan", "Palisade XRT", "Tucson XRT", "Santa Fe XRT", "Kona")),
    ("Ram", ("1500 TR", "1500 Rebel", "2500 Power Wagon", "1500 Off-Road", "3500 Heavy Duty")),
    ("Mazda", ("BT-50 4×4", "CX-50", "CX-70", "CX-90", "CX-60")),
    ("BYD", ("Yangwang U8", "Shark Pickup", "Fangchengbao Bao 5", "Fangchengbao Bao 8", "Dolphin Off-Road")),
    ("Rivian", ("R1S", "R1T", "R2", "R3", "R3X")),
    ("Honda", ("Passport TrailSport", "Pilot TrailSport", "CR-V Hybrid", "Ridgeline", "HR-V")),
    ("Tesla", ("Model Y", "Model X", "Cybertruck", "Model 3 Highland", "Model S")),
)

LEGACY_SEED_VEHICLES = (
    ("NCB 1234", "Toyota", "Vios 1.5 G"),
    ("ABC 4567", "Toyota", "Innova J"),
    ("XYZ 7788", "Mitsubishi", "Montero Sport"),
    ("PLT 9012", "Ford", "Ranger XLT 4x4"),
    ("VNL 3344", "Hyundai", "H350 Shuttle"),
    ("MTC 5566", "Honda", "Click 125i"),
    ("TRK 2211", "Isuzu", "NLR Rescue Truck"),
    ("BTT 8899", "Rainbow", "Rescue Boat + Trailer"),
    ("RDY 4455", "Toyota", "Hiace Commuter"),
    ("FLR 6677", "Suzuki", "Ertiga GL"),
)

SEED_VEHICLE_STATUSES = ("rented", "available", "rented", "available", "maintenance", "available", "available", "rented", "available", "available")
SEED_VEHICLE_PLATES = tuple(item[0] for item in LEGACY_SEED_VEHICLES)
PICKUP_MODEL_PREFIXES = (
    "hilux", "tacoma", "ranger", "f-150", "navara", "d-max", "strada", "l200",
    "colorado", "silverado", "sierra", "canyon", "1500", "2500", "3500",
    "shark pickup", "r1t", "ridgeline", "bt-50", "cybertruck", "gladiator",
)
SEDAN_MODELS = {"dolphin off-road", "model 3 highland", "model s", "wrx"}


def vehicle_catalog_models() -> list[tuple[str, str]]:
    return [(brand, model) for brand, models in VEHICLE_CATALOG for model in models]


def vehicle_category(model: str) -> str:
    normalized = model.casefold()
    if normalized in SEDAN_MODELS:
        return "Sedan"
    if normalized.startswith(PICKUP_MODEL_PREFIXES):
        return "Pickup"
    return "SUV"


def seed_vehicle_rows() -> list[tuple[Any, ...]]:
    rows: list[tuple[Any, ...]] = []
    for index, (brand, model) in enumerate(vehicle_catalog_models()):
        row, column = divmod(index, 10)
        category = vehicle_category(model)
        plate = SEED_VEHICLE_PLATES[index] if index < len(SEED_VEHICLE_PLATES) else f"FRV-{index + 1:04d}"
        status = SEED_VEHICLE_STATUSES[index] if index < len(SEED_VEHICLE_STATUSES) else "available"
        seats = 7 if model in {"Land Cruiser 300", "Defender 130", "Expedition", "Tahoe", "Suburban", "Yukon XL", "Telluride X-Pro", "Palisade XRT", "GLS"} else 5
        rate = {"Pickup": 4500, "SUV": 4000, "Sedan": 3000}[category]
        rows.append(
            (
                plate, brand, model, category, 2024 + index % 3, seats, rate, status,
                14.53 + row * 0.016, 120.94 + column * 0.014, 0,
                "Sample catalogue entry; update plate, rate, availability and GPS position for your fleet.",
            )
        )
    return rows


SEED_VEHICLES = seed_vehicle_rows()

SEED_ZONES = [
    ("España Boulevard Corridor", "Sampaloc, Manila", "severe", 14.6058, 120.9900, 1.2, 1, "Knee to waist deep water within 30 minutes of heavy rain."),
    ("Sto. Niño Street", "Malabon City", "severe", 14.6580, 120.9400, 2.0, 1, "Tidal plus storm water; usually impassable during habagat."),
    ("Kalayaan Avenue", "Diliman, Quezon City", "high", 14.6330, 121.0005, 1.5, 1, "Curb-level ponding at the Commonwealth underpass."),
    ("Governor Forbes – Lacson", "San Miguel, Manila", "moderate", 14.6000, 120.9850, 0.8, 1, "Slow drainage; clears within an hour after rain stops."),
    ("Floodway Interchange", "Cainta, Rizal", "severe", 14.5752, 121.1018, 2.5, 1, "Manggahan Floodway overflow path. Avoid all light vehicles."),
    ("Ortigas Avenue Extension", "Pasig City", "high", 14.5901, 121.0802, 1.8, 1, "Rising water near Rosario junction; monitor every 15 min."),
    ("NAIA Road", "Parañaque City", "low", 14.5102, 121.0002, 1.0, 0, "Historically passable; retained for reference only."),
]

SEED_CUSTOMERS = [
    ("Maria Isabel Santos", "+63 917 220 8841", "mi.santos@mail.com", "Drivers License", "N02-15-004218", "N02-15-004218", "18 Sampaloc Street, Manila", 14.6082, 120.9987),
    ("Jonas Dela Cruz", "+63 928 447 1190", "jonas.dc@mail.com", "PhilID", "PH-3391-2287-4510", "N03-19-110377", "44 Mindanao Avenue, Quezon City", 14.6690, 121.0160),
    ("Angeline Reyes", "+63 906 118 7725", "a.reyes@firmmail.com", "Passport", "PH7702194", "N01-21-099523", "9F Ayala Avenue, Makati", 14.5600, 121.0180),
    ("Malabon DRRMO", "+63 2 8280 4411", "drrmo@malabon.gov.ph", "Company ID", "MLB-DRR-0093", "", "Malabon City Hall Compound", 14.6575, 120.9565),
    ("Roberto Lim", "+63 919 550 3308", "rlim@logistics.ph", "UMID", "06-334-9921", "N04-17-022301", "72 Shaw Boulevard, Mandaluyong", 14.5810, 121.0370),
    ("Katrina Villanueva", "+63 995 771 2046", "kv.villanueva@mail.com", "Drivers License", "N01-22-088612", "N01-22-088612", "31 Kamias Road, Quezon City", 14.6300, 121.0530),
]

SEED_BOOKINGS = [
    ("BK-2026-0041", 1, 1, "2026-02-10", "2026-02-13", "Ayala Triangle, Makati", "Tagaytay City", 3, 1800, 5400, 2000, "ongoing", 14.5636, 121.0220),
    ("BK-2026-0042", 3, 3, "2026-02-12", "2026-02-15", "Bonifacio Global City", "Infanta, Quezon", 3, 3000, 9000, 4500, "ongoing", 14.5520, 121.0480),
    ("BK-2026-0043", 8, 4, "2026-02-11", "2026-02-14", "Malabon City Hall", "Sto. Niño, Malabon", 3, 6000, 18000, 9000, "ongoing", 14.6575, 120.9565),
    ("BK-2026-0044", 9, 5, "2026-02-18", "2026-02-20", "Ortigas Center", "Batangas Port", 2, 3800, 7600, 3800, "confirmed", 14.5840, 121.0560),
    ("BK-2026-0045", 4, 2, "2026-02-21", "2026-02-24", "Quezon Avenue Station", "Baguio City", 3, 2800, 8400, 4000, "pending", 14.6200, 121.0100),
    ("BK-2026-0046", 6, 6, "2026-02-16", "2026-02-16", "Sampaloc Depot", "Quiapo, Manila", 1, 500, 500, 0, "pending", 14.6050, 120.9950),
    ("BK-2026-0038", 2, 3, "2026-02-04", "2026-02-08", "Sampaloc Depot", "Vigan, Ilocos Sur", 4, 2200, 8800, 2200, "completed", 14.6050, 120.9950),
    ("BK-2026-0039", 7, 4, "2026-02-05", "2026-02-09", "Cainta Depot", "Manggahan Floodway", 4, 5500, 22000, 11000, "completed", 14.5752, 121.1018),
    ("BK-2026-0036", 10, 5, "2026-01-30", "2026-02-02", "Sampaloc Depot", "Antipolo City", 3, 2000, 6000, 3000, "cancelled", 14.6050, 120.9950),
]

SEED_TRANSACTIONS = [
    ("TXN-2026-0211", 3, 9000, "bank transfer", "deposit", "2026-02-11 08:12", "admin"),
    ("TXN-2026-0212", 1, 5400, "card", "payment", "2026-02-10 09:41", "admin"),
    ("TXN-2026-0213", 2, 4500, "mobile wallet", "deposit", "2026-02-12 14:05", "m.reyes"),
    ("TXN-2026-0214", 8, 22000, "bank transfer", "payment", "2026-02-09 17:22", "admin"),
    ("TXN-2026-0215", 7, 2200, "cash", "deposit", "2026-02-04 08:02", "j.dizon"),
    ("TXN-2026-0216", 7, 6600, "cash", "payment", "2026-02-08 19:30", "j.dizon"),
    ("TXN-2026-0217", 9, 3000, "mobile wallet", "refund", "2026-02-03 10:14", "admin"),
    ("TXN-2026-0218", 4, 3800, "card", "deposit", "2026-02-13 11:48", "m.reyes"),
]

SEED_ALERTS = [
    ("Vehicle inside severe flood zone", "NCB 1234 (Toyota Land Cruiser 300) is 0.4 km from España Boulevard Corridor. Recommend re-routing via Lacson Avenue.", "critical", "flood scan", 1, 1, "new", "admin", "2026-02-14 07:42"),
    ("Heavy rainfall advisory", "PAGASA orange rainfall warning over Metro Manila until 14:00. Expect curb-level ponding in low-lying barangays.", "warning", "manual", None, None, "new", "admin", "2026-02-14 06:15"),
    ("Maintenance overdue", "VNL 3344 (Toyota 4Runner) has exceeded its 5,000 km service interval by 1,240 km.", "warning", "system", 5, None, "acknowledged", "admin", "2026-02-13 16:20"),
    ("Vehicle deployment confirmed", "BTT 8899 (Land Rover Range Rover) deployed to Malabon DRRMO. Return inspection scheduled 2026-02-14 16:00.", "info", "manual", 8, None, "acknowledged", "j.dizon", "2026-02-11 08:20"),
    ("Floodway Interchange impassable", "Zone radius widened to 2.5 km after Manggahan Floodway overflow reported by Cainta DRRMO.", "critical", "flood scan", None, 5, "resolved", "admin", "2026-02-09 21:04"),
]

SEED_USERS = [
    ("m.reyes", "Miguel Reyes", "manager"),
    ("j.dizon", "Jasmine Dizon", "staff"),
    ("p.navarro", "Paolo Navarro", "staff"),
]

DEFAULT_SETTINGS = {
    "organisation": "Rainline Rentals",
    "contact_number": "+63 2 8123 4455",
    "currency": "PHP",
    "date_format": DATE_FORMAT,
    "alert_threshold": "warning",
    "zone_buffer_km": "0.5",
    "map_detail": "medium",
    "map_zoom": "12",
    "sound_alerts": "1",
    "auto_scan": "1",
    "confirm_exit": "1",
}


class Store:
    """Thin SQLite wrapper plus the queries the pages need."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path is not None else DATABASE_FILE
        self.initialise()

    # -- plumbing ---------------------------------------------------------
    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(str(self.path), timeout=15)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            yield connection
        except sqlite3.Error as error:
            connection.rollback()
            raise RuntimeError(f"A database error occurred: {error}") from error
        finally:
            connection.close()

    def initialise(self) -> None:
        ensure_folders()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            try:
                # Write-ahead logging survives crashes better and stops
                # "database is locked" when antivirus tools touch the file.
                # Not every filesystem supports it — ignore failures quietly.
                connection.execute("PRAGMA journal_mode = WAL")
            except sqlite3.Error:  # pragma: no cover - exotic filesystems
                pass
            connection.executescript(SCHEMA_SQL)
            self._migrate(connection)
            connection.commit()
        self.seed_if_needed()
        self._sync_catalog_once()

    @staticmethod
    def _migrate(connection: sqlite3.Connection) -> None:
        """Add columns introduced after the very first release, idempotently."""
        log = logging.getLogger(__name__)
        vehicle_columns = {row["name"] for row in connection.execute("PRAGMA table_info(vehicles)")}
        if "odometer" not in vehicle_columns:
            connection.execute("ALTER TABLE vehicles ADD COLUMN odometer INTEGER NOT NULL DEFAULT 0")
            log.info("Database schema updated: added vehicles.odometer")
        for column in ("latitude", "longitude"):
            if column not in vehicle_columns:
                connection.execute(f"ALTER TABLE vehicles ADD COLUMN {column} REAL")
                log.info("Database schema updated: added vehicles.%s", column)
        # Older fleets may carry units without a GPS fix — those would show in
        # the fleet list yet never appear on the map. Give every unit a
        # deterministic position around the home city so it is always detected.
        missing_fix = connection.execute(
            "SELECT id FROM vehicles WHERE latitude IS NULL OR longitude IS NULL"
        ).fetchall()
        for row in missing_fix:
            vehicle_id = int(row["id"])
            angle = _hash(vehicle_id, 21) * 2 * math.pi
            radius_km = 1.5 + _hash(vehicle_id, 22) * 7.5
            latitude = MapCanvas.HOME[1] + (radius_km * math.cos(angle)) / KM_PER_DEG_LAT
            longitude = MapCanvas.HOME[0] + (radius_km * math.sin(angle)) / KM_PER_DEG_LON
            connection.execute(
                "UPDATE vehicles SET latitude = ?, longitude = ? WHERE id = ?",
                (round(latitude, 6), round(longitude, 6), vehicle_id),
            )
        if missing_fix:
            log.info("Backfilled GPS coordinates for %d unit(s) without a fix", len(missing_fix))
        customer_columns = {row["name"] for row in connection.execute("PRAGMA table_info(customers)")}
        for column, ddl in (
            ("address", "ALTER TABLE customers ADD COLUMN address TEXT"),
            ("latitude", "ALTER TABLE customers ADD COLUMN latitude REAL"),
            ("longitude", "ALTER TABLE customers ADD COLUMN longitude REAL"),
        ):
            if column not in customer_columns:
                connection.execute(ddl)
                log.info("Database schema updated: added customers.%s", column)
        booking_columns = {row["name"] for row in connection.execute("PRAGMA table_info(bookings)")}
        for column in ("pickup_latitude", "pickup_longitude"):
            if column not in booking_columns:
                connection.execute(f"ALTER TABLE bookings ADD COLUMN {column} REAL")
                log.info("Database schema updated: added bookings.%s", column)

    def _sync_catalog_once(self) -> None:
        """Refresh the demo fleet once per database; never resurrect deleted units."""
        if self.value("SELECT value FROM settings WHERE key = 'catalog_synced'") is not None:
            return
        self.ensure_vehicle_catalog()
        self.set_setting("catalog_synced", datetime.now().strftime(DATETIME_FORMAT))

    def rows(self, sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
        with self.connect() as connection:
            return [dict(row) for row in connection.execute(sql, tuple(params)).fetchall()]

    def row(self, sql: str, params: Sequence[Any] = ()) -> dict[str, Any] | None:
        found = self.rows(sql, params)
        return found[0] if found else None

    def value(self, sql: str, params: Sequence[Any] = ()) -> Any:
        found = self.row(sql, params)
        return next(iter(found.values())) if found else None

    def execute(self, sql: str, params: Sequence[Any] = ()) -> int:
        with self.connect() as connection:
            cursor = connection.execute(sql, tuple(params))
            connection.commit()
            return int(cursor.lastrowid or 0)

    def update(self, sql: str, params: Sequence[Any] = ()) -> int:
        with self.connect() as connection:
            cursor = connection.execute(sql, tuple(params))
            connection.commit()
            return int(cursor.rowcount or 0)

    # -- seed -------------------------------------------------------------
    def seed_if_needed(self) -> bool:
        if self.value("SELECT id FROM users LIMIT 1") is not None:
            return False
        now = datetime.now().strftime(DATETIME_FORMAT)
        salt, digest = hash_password(DEFAULT_ADMIN_PASSWORD)
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO users (username, full_name, role, password_salt, password_hash, is_active, last_seen, created_at, updated_at)"
                " VALUES (?,?,?,?,?,1,?,?,?)",
                (DEFAULT_ADMIN_USERNAME, DEFAULT_ADMIN_NAME, "admin", salt, digest, now, now, now),
            )
            for username, full_name, role in SEED_USERS:
                user_salt, user_digest = hash_password("changeme123")
                connection.execute(
                    "INSERT INTO users (username, full_name, role, password_salt, password_hash, is_active, last_seen, created_at, updated_at)"
                    " VALUES (?,?,?,?,?,1,NULL,?,?)",
                    (username, full_name, role, user_salt, user_digest, now, now),
                )
            connection.executemany(
                "INSERT INTO vehicles (plate_number, brand, model, category, year, seats, rate_per_day, status, latitude, longitude, odometer, notes, created_at, updated_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                [(*row, now, now) for row in SEED_VEHICLES],
            )
            connection.executemany(
                "INSERT INTO customers (full_name, phone, email, id_type, id_number, license_number, address, latitude, longitude, created_at, updated_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                [(*row, now, now) for row in SEED_CUSTOMERS],
            )
            connection.executemany(
                "INSERT INTO flood_zones (name, barangay, risk_level, latitude, longitude, radius_km, is_active, notes, created_at, updated_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)",
                [(*row, now, now) for row in SEED_ZONES],
            )
            connection.executemany(
                "INSERT INTO bookings (booking_code, vehicle_id, customer_id, start_date, end_date, pickup_location, destination, rental_days, rate_per_day, total_amount, deposit, status, pickup_latitude, pickup_longitude, created_at, updated_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                [(*row, now, now) for row in SEED_BOOKINGS],
            )
            connection.executemany(
                "INSERT INTO transactions (reference, booking_id, amount, method, entry_type, paid_at, recorded_by, created_at)"
                " VALUES (?,?,?,?,?,?,?,?)",
                [(*row, now) for row in SEED_TRANSACTIONS],
            )
            connection.executemany(
                "INSERT INTO alerts (title, message, severity, source, vehicle_id, zone_id, status, created_by, created_at, updated_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)",
                [(*row, now) for row in SEED_ALERTS],
            )
            for key, value in DEFAULT_SETTINGS.items():
                connection.execute(
                    "INSERT INTO settings (key, value, updated_at) VALUES (?,?,?)", (key, value, now)
                )
            connection.commit()
        logging.getLogger(__name__).info("Seed data inserted into %s", self.path)
        return True

    def ensure_vehicle_catalog(self) -> None:
        """Refresh legacy demo vehicles and add any missing catalog models."""
        now = datetime.now().strftime(DATETIME_FORMAT)
        models = vehicle_catalog_models()
        renamed = 0
        added = 0
        with self.connect() as connection:
            for index, (plate, old_brand, old_model) in enumerate(LEGACY_SEED_VEHICLES):
                brand, model = models[index]
                record = connection.execute(
                    "SELECT id FROM vehicles WHERE plate_number = ? AND brand = ? AND model = ?",
                    (plate, old_brand, old_model),
                ).fetchone()
                if record is not None:
                    connection.execute(
                        "UPDATE vehicles SET brand = ?, model = ?, category = ?, updated_at = ? WHERE id = ?",
                        (brand, model, vehicle_category(model), now, record["id"]),
                    )
                    renamed += 1

            existing_models = {
                (record["brand"], record["model"])
                for record in connection.execute("SELECT brand, model FROM vehicles")
            }
            existing_plates = {
                record["plate_number"]
                for record in connection.execute("SELECT plate_number FROM vehicles")
            }
            for index, row in enumerate(SEED_VEHICLES):
                if (row[1], row[2]) in existing_models:
                    continue
                vehicle = list(row)
                if vehicle[0] in existing_plates:
                    plate_number = index + 1
                    while f"FRV-{plate_number:04d}" in existing_plates:
                        plate_number += 1
                    vehicle[0] = f"FRV-{plate_number:04d}"
                connection.execute(
                    "INSERT INTO vehicles (plate_number, brand, model, category, year, seats, rate_per_day, status, latitude, longitude, odometer, notes, created_at, updated_at)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (*vehicle, now, now),
                )
                existing_models.add((vehicle[1], vehicle[2]))
                existing_plates.add(vehicle[0])
                added += 1
            connection.commit()
        if renamed or added:
            logging.getLogger(__name__).info(
                "Vehicle catalog synchronized | refreshed=%d added=%d", renamed, added
            )

    # -- lookups ----------------------------------------------------------
    def vehicles(self, status: str = "", search: str = "") -> list[dict[str, Any]]:
        sql = "SELECT * FROM vehicles WHERE 1=1"
        params: list[Any] = []
        if status and status != "all":
            sql += " AND status = ?"
            params.append(status)
        if search:
            sql += " AND (plate_number LIKE ? OR brand LIKE ? OR model LIKE ? OR category LIKE ?)"
            like = f"%{search}%"
            params.extend([like, like, like, like])
        return self.rows(sql + " ORDER BY plate_number", params)

    def customers(self, search: str = "") -> list[dict[str, Any]]:
        sql = "SELECT * FROM customers"
        params: list[Any] = []
        if search:
            like = f"%{search}%"
            sql += (
                " WHERE (full_name LIKE ? OR email LIKE ? OR phone LIKE ? OR id_type LIKE ?"
                " OR id_number LIKE ? OR license_number LIKE ?)"
            )
            params.extend([like, like, like, like, like, like])
        return self.rows(sql + " ORDER BY full_name", params)

    def bookings(self, status: str = "", search: str = "") -> list[dict[str, Any]]:
        sql = (
            "SELECT b.*, v.plate_number, v.brand, v.model, c.full_name AS customer_name"
            " FROM bookings b JOIN vehicles v ON v.id = b.vehicle_id"
            " JOIN customers c ON c.id = b.customer_id WHERE 1=1"
        )
        params: list[Any] = []
        if status and status != "all":
            sql += " AND b.status = ?"
            params.append(status)
        if search:
            like = f"%{search}%"
            sql += (
                " AND (b.booking_code LIKE ? OR c.full_name LIKE ? OR v.model LIKE ? OR v.plate_number LIKE ?"
                " OR b.destination LIKE ? OR b.pickup_location LIKE ?)"
            )
            params.extend([like, like, like, like, like, like])
        return self.rows(sql + " ORDER BY b.start_date DESC", params)

    def transactions(self, entry_type: str = "", search: str = "") -> list[dict[str, Any]]:
        sql = (
            "SELECT t.*, b.booking_code FROM transactions t"
            " LEFT JOIN bookings b ON b.id = t.booking_id WHERE 1=1"
        )
        params: list[Any] = []
        if entry_type and entry_type != "all":
            sql += " AND t.entry_type = ?"
            params.append(entry_type)
        if search:
            like = f"%{search}%"
            sql += " AND (t.reference LIKE ? OR t.recorded_by LIKE ? OR b.booking_code LIKE ?)"
            params.extend([like, like, like])
        return self.rows(sql + " ORDER BY t.paid_at DESC", params)

    def zones(self) -> list[dict[str, Any]]:
        return self.rows("SELECT * FROM flood_zones ORDER BY name")

    def alerts(self, status: str = "") -> list[dict[str, Any]]:
        sql = "SELECT * FROM alerts"
        params: list[Any] = []
        if status and status != "all":
            sql += " WHERE status = ?"
            params.append(status)
        return self.rows(sql + " ORDER BY created_at DESC", params)

    def users(self) -> list[dict[str, Any]]:
        return self.rows("SELECT * FROM users ORDER BY id")

    def settings(self) -> dict[str, str]:
        return {row["key"]: row["value"] for row in self.rows("SELECT key, value FROM settings")}

    def set_setting(self, key: str, value: str) -> None:
        now = datetime.now().strftime(DATETIME_FORMAT)
        self.execute(
            "INSERT INTO settings (key, value, updated_at) VALUES (?,?,?)"
            " ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
            (key, value, now),
        )

    # -- authentication ---------------------------------------------------
    def login(self, username: str, password: str) -> dict[str, Any]:
        account = self.row("SELECT * FROM users WHERE username = ?", (username.strip(),))
        if account is None or not account["is_active"]:
            raise ValueError("That account does not exist or is disabled.")
        if not verify_password(password, account["password_salt"], account["password_hash"]):
            raise ValueError("Incorrect password. Try admin / admin123.")
        self.execute("UPDATE users SET last_seen = ? WHERE id = ?", (datetime.now().strftime(DATETIME_FORMAT), account["id"]))
        return account

    # -- derived ----------------------------------------------------------
    @staticmethod
    def closest_zone(
        zones: list[dict[str, Any]], lat: float | None, lon: float | None
    ) -> tuple[dict[str, Any], float] | None:
        """Nearest active zone from a pre-fetched list — no extra queries.

        Pages that score a whole fleet pass their zones list once instead of
        asking the database again for every row.
        """
        if lat is None or lon is None:
            return None
        best: tuple[dict[str, Any], float] | None = None
        for zone in zones:
            if not zone["is_active"]:
                continue
            kilometres = distance_km(lat, lon, zone["latitude"], zone["longitude"])
            if best is None or kilometres < best[1]:
                best = (zone, kilometres)
        return best

    def nearest_zone(self, lat: float, lon: float) -> tuple[dict[str, Any], float] | None:
        return self.closest_zone(self.zones(), lat, lon)

    def exposure(self) -> list[dict[str, Any]]:
        try:
            buffer = float(self.settings().get("zone_buffer_km", "0.5") or 0)
        except (TypeError, ValueError):
            buffer = 0.0
        rows: list[dict[str, Any]] = []
        for vehicle in self.vehicles():
            if vehicle["latitude"] is None or vehicle["longitude"] is None:
                continue
            found = self.nearest_zone(vehicle["latitude"], vehicle["longitude"])
            if not found:
                continue
            zone, kilometres = found
            rows.append({**vehicle, "zone_name": zone["name"], "zone_risk": zone["risk_level"], "distance_km": kilometres, "inside": kilometres <= zone["radius_km"] + buffer})
        return sorted(rows, key=lambda item: item["distance_km"])

    def dashboard(self) -> dict[str, Any]:
        vehicles = self.vehicles()
        bookings = self.bookings()
        return {
            "vehicles": len(vehicles),
            "available": sum(1 for row in vehicles if row["status"] == "available"),
            "rented": sum(1 for row in vehicles if row["status"] == "rented"),
            "maintenance": sum(1 for row in vehicles if row["status"] == "maintenance"),
            "bookings": len(bookings),
            "ongoing": sum(1 for row in bookings if row["status"] == "ongoing"),
            "value": sum(row["total_amount"] for row in bookings if row["status"] != "cancelled"),
            "open_alerts": self.value("SELECT COUNT(*) AS total FROM alerts WHERE status != 'resolved'"),
        }

    def collections_by_month(self) -> list[tuple[str, float]]:
        rows = self.rows(
            "SELECT substr(paid_at, 1, 7) AS month, SUM(CASE WHEN entry_type = 'refund' THEN -amount ELSE amount END) AS total"
            " FROM transactions GROUP BY month ORDER BY month"
        )
        return [(row["month"], float(row["total"] or 0)) for row in rows]

    def risk_distribution(self) -> list[tuple[str, int]]:
        counts = {level: 0 for level in RISK_LEVELS}
        for item in self.exposure():
            counts[item["zone_risk"]] = counts.get(item["zone_risk"], 0) + 1
        return [(level, counts[level]) for level in RISK_LEVELS]

    def run_flood_scan(self, username: str) -> list[str]:
        created: list[str] = []
        now = datetime.now().strftime(DATETIME_FORMAT)
        threshold = {"info": 0, "warning": 1, "critical": 2}.get(self.settings().get("alert_threshold", "info"), 0)
        for item in self.exposure():
            if not item["inside"]:
                continue
            severity = "critical" if item["zone_risk"] == "severe" else "warning"
            if {"info": 0, "warning": 1, "critical": 2}.get(severity, 0) < threshold:
                continue
            title = f"Flood scan: {item['plate_number']} exposed"
            # Skip while any alert for this unit is still open — otherwise an
            # acknowledged notice would be duplicated on every rescan.
            if self.row("SELECT id FROM alerts WHERE title = ? AND status != 'resolved'", (title,)):
                continue
            message = (
                f"{item['brand']} {item['model']} is {item['distance_km']:.2f} km from {item['zone_name']}"
                f" ({item['zone_risk']} risk). Recommend moving the unit before the next rainfall."
            )
            self.execute(
                "INSERT INTO alerts (title, message, severity, source, vehicle_id, status, created_by, created_at, updated_at)"
                " VALUES (?,?,?,?,?, 'new', ?, ?, ?)",
                (
                    title,
                    message,
                    severity,
                    "flood scan",
                    item["id"],
                    username,
                    now,
                    now,
                ),
            )
            created.append(title)
        return created

    def raise_alert(
        self,
        title: str,
        message: str,
        severity: str = "info",
        source: str = "manual",
        vehicle_id: int | None = None,
        zone_id: int | None = None,
        username: str = "",
    ) -> None:
        """Record a notice from any part of the app (booking checks, manual notes…)."""
        now = datetime.now().strftime(DATETIME_FORMAT)
        self.execute(
            "INSERT INTO alerts (title, message, severity, source, vehicle_id, zone_id, status, created_by, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?, 'new', ?, ?, ?)",
            (title, message, severity, source, vehicle_id, zone_id, username, now, now),
        )

    def open_alert_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {status: 0 for status in ALERT_STATUSES}
        for row in self.rows("SELECT status, COUNT(*) AS n FROM alerts GROUP BY status"):
            counts[row["status"]] = int(row["n"])
        return counts

    def set_alert_status(self, alert_id: int, status: str) -> None:
        now = datetime.now().strftime(DATETIME_FORMAT)
        self.execute("UPDATE alerts SET status = ?, updated_at = ? WHERE id = ?", (status, now, alert_id))

    def set_zone_active(self, zone_id: int, active: bool) -> None:
        now = datetime.now().strftime(DATETIME_FORMAT)
        self.execute("UPDATE flood_zones SET is_active = ?, updated_at = ? WHERE id = ?", (1 if active else 0, now, zone_id))

    # -- customer management ----------------------------------------------
    def add_customer(self, data: dict[str, Any]) -> int:
        now = datetime.now().strftime(DATETIME_FORMAT)
        name = str(data.get("full_name") or "").strip()
        phone = str(data.get("phone") or "").strip()
        if not name:
            raise ValueError("The customer needs a full name.")
        if not phone:
            raise ValueError("The customer needs at least one contact number.")
        return self.execute(
            "INSERT INTO customers (full_name, phone, email, id_type, id_number, license_number, address, latitude, longitude, notes, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                name,
                phone,
                str(data.get("email") or "").strip() or None,
                data.get("id_type") or "Drivers License",
                str(data.get("id_number") or "").strip() or None,
                str(data.get("license_number") or "").strip() or None,
                str(data.get("address") or "").strip() or None,
                data.get("latitude"),
                data.get("longitude"),
                str(data.get("notes") or "").strip() or None,
                now,
                now,
            ),
        )

    def update_customer(self, customer_id: int, data: dict[str, Any]) -> None:
        customer = self.row("SELECT * FROM customers WHERE id = ?", (customer_id,))
        if customer is None:
            raise ValueError("That customer no longer exists.")
        name = str(data.get("full_name") or "").strip()
        phone = str(data.get("phone") or "").strip()
        if not name:
            raise ValueError("The customer needs a full name.")
        if not phone:
            raise ValueError("The customer needs at least one contact number.")
        latitude = data.get("latitude", customer["latitude"])
        longitude = data.get("longitude", customer["longitude"])
        now = datetime.now().strftime(DATETIME_FORMAT)
        self.execute(
            "UPDATE customers SET full_name = ?, phone = ?, email = ?, id_type = ?, id_number = ?, license_number = ?,"
            " address = ?, latitude = ?, longitude = ?, notes = ?, updated_at = ? WHERE id = ?",
            (
                name,
                phone,
                str(data.get("email") or "").strip() or None,
                data.get("id_type") or "Drivers License",
                str(data.get("id_number") or "").strip() or None,
                str(data.get("license_number") or "").strip() or None,
                str(data.get("address") or "").strip() or None,
                latitude,
                longitude,
                str(data.get("notes") or "").strip() or None,
                now,
                customer_id,
            ),
        )

    def delete_customer(self, customer_id: int) -> None:
        used = self.value("SELECT COUNT(*) AS n FROM bookings WHERE customer_id = ?", (customer_id,)) or 0
        if used:
            raise ValueError("This customer has bookings on file and cannot be deleted.")
        self.execute("DELETE FROM customers WHERE id = ?", (customer_id,))

    def customer_bookings(self, customer_id: int) -> list[dict[str, Any]]:
        return self.rows(
            "SELECT b.*, v.plate_number, v.brand, v.model FROM bookings b"
            " JOIN vehicles v ON v.id = b.vehicle_id WHERE b.customer_id = ?"
            " ORDER BY b.start_date DESC",
            (customer_id,),
        )

    def customer_profile(self, customer_id: int) -> dict[str, Any]:
        customer = self.row("SELECT * FROM customers WHERE id = ?", (customer_id,))
        if customer is None:
            raise ValueError("That customer no longer exists.")
        history = self.customer_bookings(customer_id)
        spend = sum(float(row["total_amount"] or 0) for row in history if row["status"] != "cancelled")
        return {**customer, "bookings": history, "booking_count": len(history), "lifetime_value": spend}

    # -- vehicle management ------------------------------------------------
    def add_vehicle(self, data: dict[str, Any]) -> int:
        now = datetime.now().strftime(DATETIME_FORMAT)
        plate = str(data.get("plate_number") or "").strip().upper()
        brand = str(data.get("brand") or "").strip()
        model = str(data.get("model") or "").strip()
        if not plate:
            raise ValueError("The unit needs a plate number.")
        if not brand or not model:
            raise ValueError("The unit needs both a brand and a model.")
        if self.row("SELECT id FROM vehicles WHERE plate_number = ? COLLATE NOCASE", (plate,)):
            raise ValueError(f"Plate {plate} is already in the fleet.")
        try:
            rate = max(0.0, float(data.get("rate_per_day") or 0))
        except (TypeError, ValueError):
            rate = 0.0
        try:
            year = int(data.get("year") or datetime.now().year)
        except (TypeError, ValueError):
            year = datetime.now().year
        try:
            seats = max(1, int(data.get("seats") or 4))
        except (TypeError, ValueError):
            seats = 4
        try:
            odometer = max(0, int(data.get("odometer") or 0))
        except (TypeError, ValueError):
            odometer = 0
        status = data.get("status") or "available"
        if status not in VEHICLE_STATUSES or status == "rented":
            # A brand-new unit cannot be rented — that flag only comes from
            # starting a booking, exactly like set_vehicle_status enforces.
            status = "available"
        latitude = data.get("latitude")
        longitude = data.get("longitude")
        if latitude is None or longitude is None:
            latitude, longitude = MapCanvas.HOME[1], MapCanvas.HOME[0]
        return self.execute(
            "INSERT INTO vehicles (plate_number, brand, model, category, year, seats, rate_per_day, status, latitude, longitude, odometer, notes, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                plate, brand, model,
                data.get("category") or vehicle_category(model),
                year, seats, rate, status,
                latitude, longitude,
                odometer,
                str(data.get("notes") or "").strip() or None,
                now, now,
            ),
        )

    def update_vehicle(self, vehicle_id: int, data: dict[str, Any]) -> None:
        vehicle = self.row("SELECT * FROM vehicles WHERE id = ?", (vehicle_id,))
        if vehicle is None:
            raise ValueError("That vehicle no longer exists.")
        plate = str(data.get("plate_number") or "").strip().upper()
        brand = str(data.get("brand") or "").strip()
        model = str(data.get("model") or "").strip()
        if not plate:
            raise ValueError("The unit needs a plate number.")
        if not brand or not model:
            raise ValueError("The unit needs both a brand and a model.")
        clash = self.row("SELECT id FROM vehicles WHERE plate_number = ? COLLATE NOCASE AND id != ?", (plate, vehicle_id))
        if clash:
            raise ValueError(f"Plate {plate} belongs to another unit.")
        latitude = data.get("latitude")
        longitude = data.get("longitude")
        if latitude is None:
            latitude = vehicle["latitude"]
        if longitude is None:
            longitude = vehicle["longitude"]
        if latitude is None or longitude is None:
            latitude, longitude = MapCanvas.HOME[1], MapCanvas.HOME[0]
        status = data.get("status") or vehicle["status"]
        if status not in VEHICLE_STATUSES:
            status = vehicle["status"]
        if status == "rented":
            ongoing = self.value(
                "SELECT COUNT(*) AS n FROM bookings WHERE vehicle_id = ? AND status = 'ongoing'",
                (vehicle_id,),
            ) or 0
            if not ongoing:
                raise ValueError("Units are marked rented by starting a booking, not by hand.")
        try:
            year = int(data.get("year") or vehicle["year"])
        except (TypeError, ValueError):
            year = int(vehicle["year"] or datetime.now().year)
        try:
            seats = max(1, int(data.get("seats") or vehicle["seats"]))
        except (TypeError, ValueError):
            seats = int(vehicle["seats"] or 4)
        try:
            rate = max(0.0, float(data.get("rate_per_day") or vehicle["rate_per_day"]))
        except (TypeError, ValueError):
            rate = float(vehicle["rate_per_day"] or 0)
        try:
            odometer = max(0, int(data.get("odometer") or vehicle["odometer"]))
        except (TypeError, ValueError):
            odometer = int(vehicle["odometer"] or 0)
        now = datetime.now().strftime(DATETIME_FORMAT)
        self.execute(
            "UPDATE vehicles SET plate_number = ?, brand = ?, model = ?, category = ?, year = ?, seats = ?,"
            " rate_per_day = ?, status = ?, latitude = ?, longitude = ?, odometer = ?, notes = ?, updated_at = ? WHERE id = ?",
            (
                plate, brand, model,
                data.get("category") or vehicle_category(model),
                year, seats, rate, status,
                latitude, longitude,
                odometer,
                str(data.get("notes") or "").strip() or None,
                now,
                vehicle_id,
            ),
        )
        # Reconcile the flag with the rental ledger: an ongoing booking pulls a
        # unit back to 'rented', a finished one releases it to 'available'.
        self.sync_vehicle_status(vehicle_id)

    def delete_vehicle(self, vehicle_id: int) -> None:
        used = self.value("SELECT COUNT(*) AS n FROM bookings WHERE vehicle_id = ?", (vehicle_id,)) or 0
        if used:
            raise ValueError("This unit has bookings on file and cannot be deleted. Cancel or complete them first.")
        self.execute("DELETE FROM vehicles WHERE id = ?", (vehicle_id,))

    def vehicle_bookings(self, vehicle_id: int) -> list[dict[str, Any]]:
        return self.rows(
            "SELECT b.*, c.full_name AS customer_name FROM bookings b"
            " JOIN customers c ON c.id = b.customer_id WHERE b.vehicle_id = ?"
            " ORDER BY b.start_date DESC LIMIT 6",
            (vehicle_id,),
        )

    # -- booking management -------------------------------------------------
    def next_booking_code(self) -> str:
        year = datetime.now().year
        prefix = f"BK-{year}-"
        last = self.value(
            "SELECT booking_code FROM bookings WHERE booking_code LIKE ? ORDER BY booking_code DESC LIMIT 1",
            (prefix + "%",),
        )
        try:
            number = int(str(last).rsplit("-", 1)[-1]) + 1 if last else 1
        except ValueError:
            number = 1
        return f"{prefix}{number:04d}"

    def booking_conflicts(
        self,
        vehicle_id: int,
        start: str,
        end: str,
        exclude_booking: int | None = None,
    ) -> list[dict[str, Any]]:
        """Active bookings of one unit whose dates overlap the given range.

        Overlap is strict — each side must start before the other ends — so a
        rental that returns on the same day the next one picks up stays legal
        while genuine double-bookings are caught before they are written.
        """
        rows = self.rows(
            "SELECT id, booking_code, start_date, end_date, status FROM bookings"
            " WHERE vehicle_id = ? AND status NOT IN ('completed', 'cancelled')"
            " AND start_date < ? AND end_date > ?",
            (vehicle_id, end, start),
        )
        if exclude_booking is not None:
            rows = [row for row in rows if int(row["id"]) != int(exclude_booking)]
        return rows

    def add_booking(self, data: dict[str, Any]) -> int:
        now = datetime.now().strftime(DATETIME_FORMAT)
        vehicle = self.row("SELECT * FROM vehicles WHERE id = ?", (data.get("vehicle_id"),))
        if vehicle is None:
            raise ValueError("Choose a unit for this booking.")
        customer = self.row("SELECT id FROM customers WHERE id = ?", (data.get("customer_id"),))
        if customer is None:
            raise ValueError("Choose the customer making this booking.")
        start = normalise_date(data.get("start_date"))
        end = normalise_date(data.get("end_date"))
        days = rental_days_between(start, end)
        if days is None or days < 1:
            raise ValueError("The return date must be on or after the pickup date.")
        clash = self.booking_conflicts(int(vehicle["id"]), start, end)
        if clash:
            first = clash[0]
            raise ValueError(
                f"{vehicle['plate_number']} is already booked {first['start_date']} to {first['end_date']}"
                f" ({first['booking_code']}, {first['status']}). Pick other dates or another unit."
            )
        try:
            rate = max(0.0, float(data.get("rate_per_day") or vehicle["rate_per_day"]))
        except (TypeError, ValueError):
            rate = float(vehicle["rate_per_day"] or 0)
        try:
            deposit = max(0.0, float(data.get("deposit") or 0))
        except (TypeError, ValueError):
            deposit = 0.0
        status = data.get("status") or "pending"
        if status not in BOOKING_STATUSES:
            status = "pending"
        total = round(days * rate, 2)
        booking_id = self.execute(
            "INSERT INTO bookings (booking_code, vehicle_id, customer_id, start_date, end_date, pickup_location, destination,"
            " rental_days, rate_per_day, total_amount, deposit, pickup_latitude, pickup_longitude, status, notes, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                self.next_booking_code(),
                int(vehicle["id"]),
                int(customer["id"]),
                start,
                end,
                str(data.get("pickup_location") or "").strip() or None,
                str(data.get("destination") or "").strip() or None,
                days,
                rate,
                total,
                deposit,
                data.get("pickup_latitude"),
                data.get("pickup_longitude"),
                status,
                str(data.get("notes") or "").strip() or None,
                now,
                now,
            ),
        )
        self.sync_vehicle_status(int(vehicle["id"]))
        return booking_id

    def update_booking(self, booking_id: int, data: dict[str, Any]) -> None:
        booking = self.row("SELECT * FROM bookings WHERE id = ?", (booking_id,))
        if booking is None:
            raise ValueError("That booking no longer exists.")
        vehicle_id = int(data.get("vehicle_id") or booking["vehicle_id"])
        if self.row("SELECT id FROM vehicles WHERE id = ?", (vehicle_id,)) is None:
            raise ValueError("Choose a unit for this booking.")
        customer_id = int(data.get("customer_id") or booking["customer_id"])
        if self.row("SELECT id FROM customers WHERE id = ?", (customer_id,)) is None:
            raise ValueError("Choose the customer making this booking.")
        start = normalise_date(data.get("start_date") or booking["start_date"])
        end = normalise_date(data.get("end_date") or booking["end_date"])
        days = rental_days_between(start, end)
        if days is None or days < 1:
            raise ValueError("The return date must be on or after the pickup date.")
        clash = self.booking_conflicts(vehicle_id, start, end, exclude_booking=booking_id)
        if clash:
            first = clash[0]
            raise ValueError(
                f"{first['booking_code']} already holds this unit {first['start_date']} to {first['end_date']}"
                f" ({first['status']}). Pick other dates or another unit."
            )
        try:
            rate = max(0.0, float(data.get("rate_per_day") or booking["rate_per_day"]))
        except (TypeError, ValueError):
            rate = float(booking["rate_per_day"] or 0)
        try:
            deposit = max(0.0, float(data.get("deposit") or booking["deposit"]))
        except (TypeError, ValueError):
            deposit = float(booking["deposit"] or 0)
        status = data.get("status") or booking["status"]
        if status not in BOOKING_STATUSES:
            status = booking["status"]
        now = datetime.now().strftime(DATETIME_FORMAT)
        self.execute(
            "UPDATE bookings SET customer_id = ?, vehicle_id = ?, start_date = ?, end_date = ?, pickup_location = ?, destination = ?,"
            " rental_days = ?, rate_per_day = ?, total_amount = ?, deposit = ?, pickup_latitude = ?, pickup_longitude = ?,"
            " status = ?, notes = ?, updated_at = ? WHERE id = ?",
            (
                customer_id,
                vehicle_id,
                start,
                end,
                str(data.get("pickup_location") or "").strip() or None,
                str(data.get("destination") or "").strip() or None,
                days,
                rate,
                round(days * rate, 2),
                deposit,
                data.get("pickup_latitude"),
                data.get("pickup_longitude"),
                status,
                str(data.get("notes") or "").strip() or None,
                now,
                booking_id,
            ),
        )
        self.sync_vehicle_status(vehicle_id)
        if vehicle_id != int(booking["vehicle_id"]):
            self.sync_vehicle_status(int(booking["vehicle_id"]))

    def cancel_booking(self, booking_id: int) -> None:
        booking = self.row("SELECT * FROM bookings WHERE id = ?", (booking_id,))
        if booking is None:
            raise ValueError("That booking no longer exists.")
        if booking["status"] in ("completed", "cancelled"):
            raise ValueError(f"Booking {booking['booking_code']} is already {booking['status']}.")
        now = datetime.now().strftime(DATETIME_FORMAT)
        self.execute("UPDATE bookings SET status = 'cancelled', updated_at = ? WHERE id = ?", (now, booking_id))
        self.sync_vehicle_status(int(booking["vehicle_id"]), exclude_booking=booking_id)

    BOOKING_TRANSITIONS: dict[str, tuple[str, ...]] = {
        "pending": ("confirmed", "ongoing", "cancelled"),
        "confirmed": ("ongoing", "cancelled"),
        "ongoing": ("completed", "cancelled"),
        "completed": (),
        "cancelled": (),
    }

    def set_booking_status(self, booking_id: int, status: str) -> None:
        """Move a booking along the rental workflow with transition guards.

        pending → confirmed → ongoing → completed, with cancellations allowed
        until the rental finishes. Vehicle availability is reconciled after
        every change so the fleet list and the GPS map stay truthful.
        """
        if status not in BOOKING_STATUSES:
            raise ValueError("That booking status is not recognised.")
        booking = self.row("SELECT * FROM bookings WHERE id = ?", (booking_id,))
        if booking is None:
            raise ValueError("That booking no longer exists.")
        current = str(booking["status"])
        if status == current:
            return
        if status not in self.BOOKING_TRANSITIONS.get(current, ()):
            raise ValueError(f"A {current} booking cannot move to {status}.")
        self.execute(
            "UPDATE bookings SET status = ?, updated_at = ? WHERE id = ?",
            (status, datetime.now().strftime(DATETIME_FORMAT), booking_id),
        )
        self.sync_vehicle_status(int(booking["vehicle_id"]))

    def extend_booking(self, booking_id: int, new_end_date: str) -> int:
        """Push the return date out and re-price the rental in one step."""
        booking = self.row("SELECT * FROM bookings WHERE id = ?", (booking_id,))
        if booking is None:
            raise ValueError("That booking no longer exists.")
        if booking["status"] in ("completed", "cancelled"):
            raise ValueError(f"Booking {booking['booking_code']} is already {booking['status']}.")
        new_end = normalise_date(new_end_date)
        days = rental_days_between(str(booking["start_date"]), new_end)
        if days is None:
            raise ValueError("Enter the new return date as YYYY-MM-DD.")
        if days < int(booking["rental_days"] or 0):
            raise ValueError("The new return date would shorten the rental — edit the booking instead.")
        clash = self.booking_conflicts(int(booking["vehicle_id"]), str(booking["start_date"]), new_end, exclude_booking=booking_id)
        if clash:
            first = clash[0]
            raise ValueError(
                f"{first['booking_code']} already holds this unit from {first['start_date']}"
                f" ({first['status']}) — the extension would overlap it."
            )
        total = round(days * float(booking["rate_per_day"] or 0), 2)
        self.execute(
            "UPDATE bookings SET end_date = ?, rental_days = ?, total_amount = ?, updated_at = ? WHERE id = ?",
            (
                new_end,
                days,
                total,
                datetime.now().strftime(DATETIME_FORMAT),
                booking_id,
            ),
        )
        self.sync_vehicle_status(int(booking["vehicle_id"]))
        return days

    def set_vehicle_status(self, vehicle_id: int, status: str) -> None:
        """Front-desk shortcut for the shop floor — without touching bookings."""
        if status not in VEHICLE_STATUSES:
            raise ValueError("That vehicle status is not recognised.")
        vehicle = self.row("SELECT * FROM vehicles WHERE id = ?", (vehicle_id,))
        if vehicle is None:
            raise ValueError("That vehicle no longer exists.")
        if str(vehicle["status"]) == status:
            return
        if status == "rented":
            ongoing = self.value(
                "SELECT COUNT(*) AS n FROM bookings WHERE vehicle_id = ? AND status = 'ongoing'",
                (vehicle_id,),
            ) or 0
            if not ongoing:
                raise ValueError("Units are marked rented by starting a booking, not by hand.")
        self.execute(
            "UPDATE vehicles SET status = ?, updated_at = ? WHERE id = ?",
            (status, datetime.now().strftime(DATETIME_FORMAT), vehicle_id),
        )

    def sync_vehicle_status(self, vehicle_id: int, exclude_booking: int | None = None) -> None:
        """Keep vehicles.rented in step with the bookings that hold each unit."""
        vehicle = self.row("SELECT status FROM vehicles WHERE id = ?", (vehicle_id,))
        if vehicle is None:
            return
        sql = "SELECT COUNT(*) AS n FROM bookings WHERE vehicle_id = ? AND status = 'ongoing'"
        params: list[Any] = [vehicle_id]
        if exclude_booking is not None:
            sql += " AND id != ?"
            params.append(exclude_booking)
        ongoing = self.value(sql, params) or 0
        now = datetime.now().strftime(DATETIME_FORMAT)
        if ongoing and vehicle["status"] != "rented" and vehicle["status"] != "maintenance":
            self.execute("UPDATE vehicles SET status = 'rented', updated_at = ? WHERE id = ?", (now, vehicle_id))
        elif not ongoing and vehicle["status"] == "rented":
            self.execute("UPDATE vehicles SET status = 'available', updated_at = ? WHERE id = ?", (now, vehicle_id))

    def booking_balance(self, booking_id: int) -> float:
        booking = self.row("SELECT total_amount FROM bookings WHERE id = ?", (booking_id,))
        if booking is None:
            return 0.0
        paid = self.value(
            "SELECT COALESCE(SUM(CASE WHEN entry_type = 'refund' THEN -amount ELSE amount END), 0) AS paid"
            " FROM transactions WHERE booking_id = ?",
            (booking_id,),
        ) or 0
        return float(booking["total_amount"] or 0) - float(paid)

    # -- payments -----------------------------------------------------------
    def next_transaction_reference(self) -> str:
        prefix = f"TXN-{datetime.now().strftime('%Y%m')}-"
        last = self.value(
            "SELECT reference FROM transactions WHERE reference LIKE ? ORDER BY reference DESC LIMIT 1",
            (prefix + "%",),
        )
        try:
            number = int(str(last).rsplit("-", 1)[-1]) + 1 if last else 1
        except ValueError:
            number = 1
        return f"{prefix}{number:04d}"

    def record_payment(self, data: dict[str, Any]) -> str:
        booking_id = int(data.get("booking_id") or 0)
        if self.row("SELECT id FROM bookings WHERE id = ?", (booking_id,)) is None:
            raise ValueError("Choose the booking this payment belongs to.")
        try:
            amount = float(data.get("amount") or 0)
        except (TypeError, ValueError):
            amount = 0.0
        if amount <= 0:
            raise ValueError("Enter an amount greater than zero.")
        entry_type = data.get("entry_type") or "payment"
        if entry_type not in PAYMENT_TYPES:
            raise ValueError("Choose a valid entry type.")
        method = data.get("method") or "cash"
        if method not in PAYMENT_METHODS:
            raise ValueError("Choose a valid payment method.")
        now = datetime.now().strftime(DATETIME_FORMAT)
        paid_at = str(data.get("paid_at") or "").strip() or now
        try:
            paid_at = datetime.strptime(paid_at, DATETIME_FORMAT).strftime(DATETIME_FORMAT)
        except ValueError:
            raise ValueError("Enter the paid-at time as YYYY-MM-DD HH:MM.") from None
        reference = self.next_transaction_reference()
        self.execute(
            "INSERT INTO transactions (reference, booking_id, amount, method, entry_type, paid_at, recorded_by, notes, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (
                reference,
                booking_id,
                amount,
                method,
                entry_type,
                paid_at,
                str(data.get("recorded_by") or "").strip() or None,
                str(data.get("notes") or "").strip() or None,
                now,
            ),
        )
        return reference

    # -- flood zone management ----------------------------------------------
    def add_zone(self, data: dict[str, Any]) -> int:
        now = datetime.now().strftime(DATETIME_FORMAT)
        name = str(data.get("name") or "").strip()
        if not name:
            raise ValueError("The flood zone needs a name.")
        risk = data.get("risk_level") or "moderate"
        if risk not in RISK_LEVELS:
            risk = "moderate"
        try:
            latitude = float(data["latitude"])
            longitude = float(data["longitude"])
        except (KeyError, TypeError, ValueError):
            raise ValueError("Pin the zone on the map or enter its coordinates.") from None
        try:
            radius = max(0.1, float(data.get("radius_km") or 1.0))
        except (TypeError, ValueError):
            radius = 1.0
        return self.execute(
            "INSERT INTO flood_zones (name, barangay, risk_level, latitude, longitude, radius_km, is_active, notes, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                name,
                str(data.get("barangay") or "").strip() or None,
                risk,
                latitude,
                longitude,
                radius,
                1 if data.get("is_active", True) else 0,
                str(data.get("notes") or "").strip() or None,
                now,
                now,
            ),
        )

    def update_zone(self, zone_id: int, data: dict[str, Any]) -> None:
        zone = self.row("SELECT * FROM flood_zones WHERE id = ?", (zone_id,))
        if zone is None:
            raise ValueError("That flood zone no longer exists.")
        name = str(data.get("name") or zone["name"]).strip()
        if not name:
            raise ValueError("The flood zone needs a name.")
        risk = data.get("risk_level") or zone["risk_level"]
        if risk not in RISK_LEVELS:
            risk = zone["risk_level"]
        try:
            latitude = float(data.get("latitude") or zone["latitude"])
            longitude = float(data.get("longitude") or zone["longitude"])
        except (TypeError, ValueError):
            latitude, longitude = zone["latitude"], zone["longitude"]
        try:
            radius = max(0.1, float(data.get("radius_km") or zone["radius_km"]))
        except (TypeError, ValueError):
            radius = zone["radius_km"]
        now = datetime.now().strftime(DATETIME_FORMAT)
        self.execute(
            "UPDATE flood_zones SET name = ?, barangay = ?, risk_level = ?, latitude = ?, longitude = ?,"
            " radius_km = ?, is_active = ?, notes = ?, updated_at = ? WHERE id = ?",
            (
                name,
                str(data.get("barangay") or "").strip() or None,
                risk,
                latitude,
                longitude,
                radius,
                1 if data.get("is_active", bool(zone["is_active"])) else 0,
                str(data.get("notes") or "").strip() or None,
                now,
                zone_id,
            ),
        )

    def delete_zone(self, zone_id: int) -> None:
        self.execute("DELETE FROM flood_zones WHERE id = ?", (zone_id,))

    # -- user management -----------------------------------------------------
    def add_user(self, username: str, full_name: str, role: str, password: str) -> int:
        username = username.strip()
        full_name = full_name.strip()
        if len(username) < 3:
            raise ValueError("Usernames need at least 3 characters.")
        if not full_name:
            raise ValueError("Enter the account holder's full name.")
        if role not in USER_ROLES:
            raise ValueError("Choose a valid role.")
        if len(password) < 8:
            raise ValueError("Passwords need at least 8 characters.")
        if self.row("SELECT id FROM users WHERE username = ? COLLATE NOCASE", (username,)):
            raise ValueError(f"The username '{username}' is already taken.")
        salt, digest = hash_password(password)
        now = datetime.now().strftime(DATETIME_FORMAT)
        return self.execute(
            "INSERT INTO users (username, full_name, role, password_salt, password_hash, is_active, last_seen, created_at, updated_at)"
            " VALUES (?,?,?,?,?,1,NULL,?,?)",
            (username, full_name, role, salt, digest, now, now),
        )

    def set_user_active(self, user_id: int, active: bool) -> None:
        user = self.row("SELECT * FROM users WHERE id = ?", (user_id,))
        if user is None:
            raise ValueError("That account no longer exists.")
        if not active:
            if user["role"] == "admin":
                others = self.value(
                    "SELECT COUNT(*) AS n FROM users WHERE role = 'admin' AND is_active = 1 AND id != ?",
                    (user_id,),
                ) or 0
                if others == 0:
                    raise ValueError("At least one active administrator must remain.")
            if user["username"] == DEFAULT_ADMIN_USERNAME:
                raise ValueError("The built-in administrator account cannot be disabled.")
        self.execute("UPDATE users SET is_active = ?, updated_at = ? WHERE id = ?", (1 if active else 0, datetime.now().strftime(DATETIME_FORMAT), user_id))

    def reset_password(self, user_id: int, password: str) -> None:
        if len(password) < 8:
            raise ValueError("Passwords need at least 8 characters.")
        if self.row("SELECT id FROM users WHERE id = ?", (user_id,)) is None:
            raise ValueError("That account no longer exists.")
        salt, digest = hash_password(password)
        self.execute(
            "UPDATE users SET password_salt = ?, password_hash = ?, updated_at = ? WHERE id = ?",
            (salt, digest, datetime.now().strftime(DATETIME_FORMAT), user_id),
        )

    def backup(self, destination: str) -> Path:
        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            backup_connection = sqlite3.connect(str(target))
            try:
                connection.backup(backup_connection)
            finally:
                backup_connection.close()
        return target

    # -- reports ----------------------------------------------------------
    REPORTS: dict[str, tuple[str, str]] = {
        "vehicles": ("Vehicle inventory", "Plate, category, seats, rate and status"),
        "customers": ("Customer directory", "Contact details and identification"),
        "bookings": ("Booking ledger", "Periods, destinations, deposits and totals"),
        "transactions": ("Cash and payments", "Payments, deposits and refunds by method"),
        "flood": ("Flood risk assessment", "Active zones, severity and exposed units"),
        "alerts": ("Alert log", "Every notice raised, its source and status"),
    }

    def report(self, key: str) -> tuple[list[str], list[list[Any]]]:
        if key == "vehicles":
            return ["Plate", "Unit", "Category", "Seats", "Rate", "Status"], [
                [row["plate_number"], f"{row['brand']} {row['model']}", row["category"], row["seats"], money(row["rate_per_day"]), row["status"]]
                for row in self.vehicles()
            ]
        if key == "customers":
            return ["Name", "Phone", "E-mail", "ID type", "ID number"], [
                [row["full_name"], row["phone"], row["email"] or "", row["id_type"], row["id_number"] or ""]
                for row in self.customers()
            ]
        if key == "bookings":
            return ["Code", "Customer", "Unit", "Start", "End", "Days", "Deposit", "Total", "Status"], [
                [row["booking_code"], row["customer_name"], f"{row['brand']} {row['model']}", row["start_date"], row["end_date"], row["rental_days"], money(row["deposit"]), money(row["total_amount"]), row["status"]]
                for row in self.bookings()
            ]
        if key == "transactions":
            return ["Reference", "Booking", "Type", "Method", "Paid at", "Recorded by", "Amount"], [
                [row["reference"], row["booking_code"] or "", row["entry_type"], row["method"], row["paid_at"], row["recorded_by"] or "", money(row["amount"])]
                for row in self.transactions()
            ]
        if key == "flood":
            exposure = self.exposure()  # scored once, not once per zone
            return ["Zone", "Barangay", "Risk", "Radius km", "Active", "Exposed units"], [
                [row["name"], row["barangay"] or "", row["risk_level"], f"{row['radius_km']:.1f}", "yes" if row["is_active"] else "no", sum(1 for item in exposure if item["zone_name"] == row["name"] and item["inside"])]
                for row in self.zones()
            ]
        return ["When", "Title", "Severity", "Source", "Status"], [
            [row["created_at"], row["title"], row["severity"], row["source"], row["status"]] for row in self.alerts()
        ]


# ---------------------------------------------------------------------------
# Record dialogs — add and edit customers, vehicles, bookings, payments, zones
# ---------------------------------------------------------------------------


class PinMapCanvas(MapCanvas):
    """Map canvas with one editable marker, used by the record dialogs."""

    def __init__(self, master: tk.Widget, store: "Store", pin: tuple[float, float] | None = None, **kwargs: Any) -> None:
        self.pin = None  # set before super().__init__ because MapCanvas draws on creation
        kwargs.setdefault("show_vehicles", False)
        kwargs.setdefault("show_grid", False)
        kwargs.setdefault("legend", False)
        super().__init__(master, store, **kwargs)
        # pin maps start closer to street level; recentre on an existing pin
        self.span_km = 9.0
        if pin is not None:
            self.center_lat, self.center_lon = pin[0], pin[1]
        self.pin = pin
        self.draw()

    def draw(self) -> None:
        super().draw()
        if self.pin is None:
            return
        x, y = self.project(*self.pin)
        self.create_oval(x - 10, y - 10, x + 10, y + 10, fill=_mix(PALETTE["accent"], "#FFFFFF", 0.55), outline="")
        self.create_oval(x - 6, y - 6, x + 6, y + 6, fill=PALETTE["accent"], outline="#FFFFFF", width=2)

    def set_pin(self, position: tuple[float, float] | None) -> None:
        self.pin = position
        self.draw()


class FormDialog(tk.Toplevel):
    """Modal card window: heading, two-column fields, optional map pin, save/cancel."""

    def __init__(self, parent: tk.Widget, title: str, subtitle: str) -> None:
        super().__init__(parent)
        self.result = False
        self.fields: dict[str, Field] = {}
        self.checks: dict[str, tk.BooleanVar] = {}
        self._row = 0
        self._col = 0
        self.pin_map: PinMapCanvas | None = None
        self.pin_text = tk.StringVar(value="none")
        self.title(title)
        self.configure(background=PALETTE["bg"], padx=18, pady=18)
        self.resizable(False, False)
        self.transient(parent.winfo_toplevel())
        card = ttk.Frame(self, style="CardBorder.TFrame", padding=1)
        card.pack(fill="both", expand=True)
        self.body = ttk.Frame(card, style="Card.TFrame", padding=(26, 22))
        self.body.pack(fill="both", expand=True)
        # header — title and subtitle share a tight block, separated from the
        # form below by a quiet hairline so the dialog reads as one card
        header = ttk.Frame(self.body, style="Card.TFrame")
        header.pack(fill="x")
        ttk.Label(header, text=title, style="HeadingCard.TLabel").pack(anchor="w")
        ttk.Label(
            header, text=subtitle, style="MutedCard.TLabel", wraplength=460, justify="left"
        ).pack(anchor="w", pady=(3, 0))
        ttk.Frame(self.body, style="CardBorder.TFrame", height=1).pack(fill="x", pady=(14, 0))
        self.form = ttk.Frame(self.body, style="Card.TFrame")
        self.form.pack(fill="x", pady=(14, 0))
        self.error = tk.StringVar(value="")
        ttk.Frame(self.body, style="CardBorder.TFrame", height=1).pack(fill="x", pady=(16, 0))
        footer = ttk.Frame(self.body, style="Card.TFrame")
        footer.pack(fill="x", pady=(12, 0))
        self.error_label = ttk.Label(
            footer, textvariable=self.error, style="DangerCard.TLabel", wraplength=320, justify="left"
        )
        self.error_label.pack(side="left", fill="x", expand=True)
        buttons = ttk.Frame(footer, style="Card.TFrame")
        buttons.pack(side="right")
        Button(buttons, text="Cancel", style="Secondary.TButton", command=self.destroy).pack(side="left", padx=(0, 8))
        Button(buttons, text="Save", style="Primary.TButton", command=self.save).pack(side="left")
        self.bind("<Return>", lambda _event: self.save())
        self.bind("<Escape>", lambda _event: self.destroy())
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.grab_set()

    # -- form building -----------------------------------------------------
    def _wide_row(self) -> None:
        if self._col == 1:
            self._row += 1
            self._col = 0

    def add_field(
        self,
        key: str,
        label: str,
        value: str = "",
        choices: Sequence[str] | None = None,
        secret: bool = False,
        editable: bool = False,
        wide: bool = False,
        on_change: Callable[[str], None] | None = None,
    ) -> Field:
        if wide:
            self._wide_row()
        field = Field(self.form, label, value=value, choices=choices, secret=secret, editable=editable, on_change=on_change)
        column = 0 if wide else self._col
        field.grid(
            row=self._row,
            column=column,
            columnspan=2 if wide else 1,
            sticky="ew",
            padx=(0 if column == 0 else 12, 0),
            pady=(0, 10),
        )
        if wide or self._col == 1:
            self._row += 1
            self._col = 0
        else:
            self._col = 1
        self.form.columnconfigure(0, weight=1)
        self.form.columnconfigure(1, weight=1)
        self.fields[key] = field
        return field

    def add_check(self, key: str, label: str, checked: bool) -> tk.BooleanVar:
        self._wide_row()
        variable = tk.BooleanVar(value=checked)
        box = ttk.Frame(self.form, style="Card.TFrame")
        box.grid(row=self._row, column=0, columnspan=2, sticky="w", pady=(0, 10))
        ttk.Checkbutton(box, text=label, variable=variable, style="Switch.TCheckbutton").pack(anchor="w")
        self._row += 1
        self.checks[key] = variable
        return variable

    def add_summary(self) -> ttk.Label:
        self._wide_row()
        label = ttk.Label(self.form, text="", style="AccentCard.TLabel")
        label.grid(row=self._row, column=0, columnspan=2, sticky="w", pady=(0, 2))
        self._row += 1
        return label

    def add_pin_map(self, store: "Store", label: str, lat: float | None, lon: float | None) -> None:
        self._wide_row()
        pin = (float(lat), float(lon)) if lat is not None and lon is not None else None
        box = ttk.Frame(self.form, style="Card.TFrame")
        box.grid(row=self._row, column=0, columnspan=2, sticky="ew", pady=(2, 10))
        head = ttk.Frame(box, style="Card.TFrame")
        head.pack(fill="x")
        ttk.Label(head, text=label.upper(), style="MicroCard.TLabel").pack(side="left")
        ttk.Label(head, textvariable=self.pin_text, style="MutedCard.TLabel").pack(side="left", padx=(10, 0))
        Button(head, text="Clear pin", style="Ghost.TButton", command=lambda: self.set_pin(None)).pack(side="right")
        self.pin_map = PinMapCanvas(
            box, store, pin=pin, height=185, show_labels=True, show_zones=True, detail="medium"
        )
        self.pin_map.pack(fill="x", pady=(6, 0))
        self.pin_map.on_click = self._handle_click
        self.set_pin(pin)
        self._row += 1

    # -- pin -----------------------------------------------------------------
    def _handle_click(self, position: tuple[float, float]) -> None:
        self.set_pin(position)

    def set_pin(self, position: tuple[float, float] | None) -> None:
        if self.pin_map is not None:
            self.pin_map.set_pin(position)
        self.pin_text.set("none" if position is None else f"{position[0]:.4f}, {position[1]:.4f}")

    def pin(self) -> tuple[float | None, float | None]:
        if self.pin_map is None or self.pin_map.pin is None:
            return None, None
        lat, lon = self.pin_map.pin
        return float(lat), float(lon)

    # -- saving --------------------------------------------------------------
    def value(self, key: str) -> str:
        return self.fields[key].get()

    def save(self) -> None:
        try:
            self.commit()
        except (ValueError, RuntimeError) as error:
            self.error.set(str(error))
            return
        self.result = True
        self.destroy()

    def commit(self) -> None:
        """Subclasses validate and write to the store here."""
        return

    def _centre(self) -> None:
        self.update_idletasks()
        x = max(0, (self.winfo_screenwidth() - self.winfo_reqwidth()) // 2)
        y = max(0, (self.winfo_screenheight() - self.winfo_reqheight()) // 3)
        self.geometry(f"+{x}+{y}")


def confirm_delete(parent: tk.Widget, what: str) -> bool:
    return bool(messagebox.askyesno(APP_NAME, f"Delete {what}? This cannot be undone.", parent=parent))


def handle_store_error(parent: tk.Widget, error: Exception) -> None:
    messagebox.showerror(APP_NAME, str(error), parent=parent)


class CustomerDialog(FormDialog):
    """Add or edit a renter, with an optional home pin for the GPS map."""

    def __init__(self, parent: tk.Widget, store: "Store", customer: dict[str, Any] | None = None) -> None:
        self.store = store
        self.customer = customer
        record = customer or {}
        super().__init__(
            parent,
            "Edit customer" if customer else "Add customer",
            "Renter contact and identification. The map pin appears on the GPS page.",
        )
        self.add_field("full_name", "Full name", str(record.get("full_name") or ""))
        self.add_field("phone", "Contact number", str(record.get("phone") or ""))
        self.add_field("email", "E-mail", str(record.get("email") or ""))
        self.add_field("id_type", "ID type", str(record.get("id_type") or "Drivers License"), choices=ID_TYPES)
        self.add_field("id_number", "ID number", str(record.get("id_number") or ""))
        self.add_field("license_number", "License number", str(record.get("license_number") or ""))
        self.add_field("address", "Address", str(record.get("address") or ""), wide=True)
        self.add_field("notes", "Notes", str(record.get("notes") or ""), wide=True)
        self.add_pin_map(store, "Home pin · click to place", record.get("latitude"), record.get("longitude"))
        self._centre()

    def commit(self) -> None:
        data: dict[str, Any] = {key: field.get() for key, field in self.fields.items()}
        data["latitude"], data["longitude"] = self.pin()
        if self.customer:
            self.store.update_customer(int(self.customer["id"]), data)
        else:
            self.store.add_customer(data)


class VehicleDialog(FormDialog):
    """Add or edit a fleet unit, including its GPS position."""

    def __init__(self, parent: tk.Widget, store: "Store", vehicle: dict[str, Any] | None = None) -> None:
        self.store = store
        self.vehicle = vehicle
        record = vehicle or {}
        super().__init__(
            parent,
            "Edit unit" if vehicle else "Add unit",
            "Fleet record with rate, capacity and last known GPS position.",
        )
        brands = [brand for brand, _models in VEHICLE_CATALOG]
        # A brand-new unit cannot be 'rented' — that flag is owned by bookings.
        status_choices = VEHICLE_STATUSES if vehicle else ("available", "maintenance")
        self.add_field("plate_number", "Plate number", str(record.get("plate_number") or ""))
        self.add_field("status", "Status", str(record.get("status") or "available"), choices=status_choices)
        self.add_field(
            "brand", "Brand", str(record.get("brand") or "Toyota"), choices=brands, editable=True, on_change=self._on_brand
        )
        self.add_field(
            "model",
            "Model",
            str(record.get("model") or ""),
            choices=list(self._models_for(str(record.get("brand") or "Toyota"))),
            editable=True,
            on_change=self._on_model,
        )
        self.add_field("category", "Category", str(record.get("category") or "SUV"), choices=VEHICLE_CATEGORIES)
        self.add_field("year", "Year", str(record.get("year") or datetime.now().year))
        self.add_field("seats", "Seats", str(record.get("seats") or 5))
        self.add_field("rate_per_day", "Rate per day", str(record.get("rate_per_day") or 3500))
        self.add_field("odometer", "Odometer (km)", str(record.get("odometer") or 0))
        self.add_field("notes", "Notes", str(record.get("notes") or ""), wide=True)
        self.add_pin_map(store, "GPS position · click to place", record.get("latitude"), record.get("longitude"))
        self._centre()

    @staticmethod
    def _models_for(brand: str) -> tuple[str, ...]:
        wanted = str(brand).strip().casefold()
        for name, models in VEHICLE_CATALOG:
            if name.casefold() == wanted:
                return models
        return ()

    def _on_brand(self, brand: str) -> None:
        if "model" not in self.fields:
            return
        models = self._models_for(brand)
        self.fields["model"].widget.configure(values=list(models))
        if models and self.value("model") not in models:
            self.fields["model"].variable.set(models[0])

    def _on_model(self, model: str) -> None:
        if model.strip() and "category" in self.fields:
            self.fields["category"].variable.set(vehicle_category(model))

    def commit(self) -> None:
        data: dict[str, Any] = {key: field.get() for key, field in self.fields.items()}
        data["latitude"], data["longitude"] = self.pin()
        if self.vehicle:
            self.store.update_vehicle(int(self.vehicle["id"]), data)
        else:
            self.store.add_vehicle(data)


class ZoneDialog(FormDialog):
    """Add or edit a monitored flood zone."""

    def __init__(self, parent: tk.Widget, store: "Store", zone: dict[str, Any] | None = None) -> None:
        self.store = store
        self.zone = zone
        record = zone or {}
        super().__init__(
            parent,
            "Edit flood zone" if zone else "Add flood zone",
            "Monitored area used by the risk scan and drawn as a ring on the map.",
        )
        self.add_field("name", "Zone name", str(record.get("name") or ""))
        self.add_field("barangay", "Barangay / district", str(record.get("barangay") or ""))
        self.add_field("risk_level", "Risk level", str(record.get("risk_level") or "moderate"), choices=RISK_LEVELS)
        self.add_field("radius_km", "Radius (km)", str(record.get("radius_km") or 1.0))
        self.add_check("is_active", "Active in risk scans", bool(record.get("is_active", 1)))
        self.add_field("notes", "Notes", str(record.get("notes") or ""), wide=True)
        self.add_pin_map(store, "Centre · click to place", record.get("latitude"), record.get("longitude"))
        self._centre()

    def commit(self) -> None:
        data: dict[str, Any] = {key: field.get() for key, field in self.fields.items()}
        for key, variable in self.checks.items():
            data[key] = bool(variable.get())
        data["latitude"], data["longitude"] = self.pin()
        if self.zone:
            self.store.update_zone(int(self.zone["id"]), data)
        else:
            self.store.add_zone(data)


class BookingDialog(FormDialog):
    """Create or amend a booking, with a live total and a flood-zone check."""

    def __init__(
        self,
        parent: tk.Widget,
        store: "Store",
        booking: dict[str, Any] | None = None,
        customer: dict[str, Any] | None = None,
        vehicle: dict[str, Any] | None = None,
    ) -> None:
        self.store = store
        self.booking = booking
        record = booking or {}
        # Fetch and validate before the window is built — raising after
        # super().__init__ would leave a modal grab blocking the whole app.
        customers = store.customers()
        self.customer_map = {str(row["full_name"]): int(row["id"]) for row in customers}
        vehicles = store.vehicles()
        self.vehicle_map: dict[str, int] = {}
        self.vehicle_rate: dict[int, float] = {}
        self.vehicle_status: dict[int, str] = {}
        for row in vehicles:
            label = f"{row['plate_number']} · {row['brand']} {row['model']}"
            self.vehicle_rate[int(row["id"])] = float(row["rate_per_day"] or 0)
            self.vehicle_status[int(row["id"])] = str(row["status"])
            if booking or row["status"] == "available":
                self.vehicle_map[label] = int(row["id"])
        if not self.customer_map:
            raise ValueError("Add a customer before creating a booking.")
        if not self.vehicle_map:
            raise ValueError("No available unit — free one up or add a vehicle first.")
        super().__init__(
            parent,
            "Edit booking" if booking else "New booking",
            "Choose the customer and unit, set the rental period and pin the pickup point.",
        )

        customer_label = str(record.get("customer_name") or (customer or {}).get("full_name") or "")
        if customer_label not in self.customer_map:
            customer_label = next(iter(self.customer_map))
        vehicle_label = ""
        if record.get("plate_number"):
            vehicle_label = f"{record['plate_number']} · {record['brand']} {record['model']}"
        elif vehicle is not None:
            vehicle_label = f"{vehicle['plate_number']} · {vehicle['brand']} {vehicle['model']}"
        if vehicle_label not in self.vehicle_map:
            vehicle_label = next(iter(self.vehicle_map))
        status_choices = BOOKING_STATUSES if booking else ("pending", "confirmed")
        today = datetime.now().strftime(DATE_FORMAT)
        fallback_end = (datetime.now() + timedelta(days=1)).strftime(DATE_FORMAT)

        self.add_field("customer", "Customer", customer_label, choices=sorted(self.customer_map))
        self.add_field("vehicle", "Unit", vehicle_label, choices=sorted(self.vehicle_map), on_change=self._on_vehicle)
        self.add_field("start_date", "Pickup date (YYYY-MM-DD)", str(record.get("start_date") or today), on_change=lambda _v: self._update_summary())
        self.add_field("end_date", "Return date (YYYY-MM-DD)", str(record.get("end_date") or fallback_end), on_change=lambda _v: self._update_summary())
        self.add_field("status", "Status", str(record.get("status") or "pending"), choices=status_choices)
        self.add_field("pickup_location", "Pickup point", str(record.get("pickup_location") or ""), wide=True)
        self.add_field("destination", "Destination", str(record.get("destination") or ""), wide=True)
        self.add_field("rate_per_day", "Rate per day", str(record.get("rate_per_day") or self.vehicle_rate[self.vehicle_map[vehicle_label]]), on_change=lambda _v: self._update_summary())
        self.add_field("deposit", "Deposit", str(record.get("deposit") or 0))
        self.add_field("notes", "Notes", str(record.get("notes") or ""), wide=True)
        self.total_label = self.add_summary()
        self.add_pin_map(store, "Pickup pin · click to place", record.get("pickup_latitude"), record.get("pickup_longitude"))
        self._update_summary()
        self._centre()

    def _on_vehicle(self, label: str) -> None:
        vehicle_id = self.vehicle_map.get(label)
        if vehicle_id is not None and "rate_per_day" in self.fields:
            self.fields["rate_per_day"].variable.set(f"{self.vehicle_rate[vehicle_id]:g}")
        self._update_summary()

    def _update_summary(self) -> None:
        if "start_date" not in self.fields or "end_date" not in self.fields:
            return
        days = rental_days_between(self.value("start_date"), self.value("end_date"))
        if days is None:
            self.total_label.configure(text="Enter the pickup and return dates as YYYY-MM-DD.")
            return
        try:
            rate = float(self.value("rate_per_day") or 0)
        except ValueError:
            rate = 0.0
        note = ""
        vehicle_id = self.vehicle_map.get(self.value("vehicle"))
        if vehicle_id is not None and self.vehicle_status.get(vehicle_id) == "maintenance":
            note = "  ·  unit is in the shop"
        self.total_label.configure(text=f"{days} day(s) × {money(rate)} / day = {money(days * rate)}{note}")

    def commit(self) -> None:
        customer_name = self.value("customer")
        vehicle_label = self.value("vehicle")
        if customer_name not in self.customer_map:
            raise ValueError("Choose the customer making this booking.")
        if vehicle_label not in self.vehicle_map:
            raise ValueError("Choose a unit for this booking.")
        data: dict[str, Any] = {
            "customer_id": self.customer_map[customer_name],
            "vehicle_id": self.vehicle_map[vehicle_label],
            "start_date": self.value("start_date"),
            "end_date": self.value("end_date"),
            "status": self.value("status"),
            "pickup_location": self.value("pickup_location"),
            "destination": self.value("destination"),
            "rate_per_day": self.value("rate_per_day"),
            "deposit": self.value("deposit"),
            "notes": self.value("notes"),
        }
        data["pickup_latitude"], data["pickup_longitude"] = self.pin()
        lat, lon = data["pickup_latitude"], data["pickup_longitude"]
        if lat is not None and lon is not None:
            found = self.store.nearest_zone(lat, lon)
            if found is not None:
                zone, kilometres = found
                if kilometres <= float(zone["radius_km"]) and zone["risk_level"] in ("high", "severe"):
                    proceed = messagebox.askyesno(
                        APP_NAME,
                        f"The pickup pin sits {kilometres:.2f} km from {zone['name']} ({zone['risk_level']} risk).\n\n"
                        "Record the booking anyway and raise a flood alert?",
                        parent=self,
                    )
                    if proceed:
                        self.store.raise_alert(
                            f"Booking pickup in {zone['risk_level']} risk zone",
                            f"{customer_name} booked a unit with pickup {kilometres:.2f} km from {zone['name']}"
                            f" ({zone['risk_level']} risk). Confirm the route before release.",
                            severity="critical" if zone["risk_level"] == "severe" else "warning",
                            source="booking check",
                            zone_id=int(zone["id"]),
                        )
                    else:
                        return
        if self.booking:
            self.store.update_booking(int(self.booking["id"]), data)
        else:
            self.store.add_booking(data)


class PaymentDialog(FormDialog):
    """Record a payment, deposit or refund against a booking."""

    def __init__(self, parent: tk.Widget, store: "Store", booking_id: int | None = None, username: str = "") -> None:
        self.store = store
        self.username = username
        # Validate before the window is built so a failed construction can
        # never leave a modal grab behind.
        bookings = store.bookings()
        self.booking_map = {f"{row['booking_code']} · {row['customer_name']}": int(row["id"]) for row in bookings}
        if not self.booking_map:
            raise ValueError("Create a booking before recording a payment.")
        super().__init__(
            parent,
            "Record payment",
            "Payments, deposits and refunds are written straight into the ledger.",
        )
        chosen = ""
        for label, value in self.booking_map.items():
            if value == booking_id:
                chosen = label
                break
        if not chosen:
            chosen = next(iter(self.booking_map))
        self.add_field("booking", "Booking", chosen, choices=sorted(self.booking_map), wide=True, on_change=lambda _v: self._prefill())
        self.balance_label = self.add_summary()
        self.add_field("entry_type", "Type", "payment", choices=PAYMENT_TYPES)
        self.add_field("method", "Method", "cash", choices=PAYMENT_METHODS)
        self.amount_field = self.add_field("amount", "Amount", "0")
        self.add_field("paid_at", "Paid at (YYYY-MM-DD HH:MM)", datetime.now().strftime(DATETIME_FORMAT))
        self.add_field("notes", "Notes", "", wide=True)
        self._prefill()
        self._centre()

    def _selected_booking(self) -> int | None:
        return self.booking_map.get(self.value("booking"))

    def _prefill(self) -> None:
        booking_id = self._selected_booking()
        if booking_id is None:
            self.balance_label.configure(text="")
            return
        booking = self.store.row("SELECT total_amount FROM bookings WHERE id = ?", (booking_id,))
        balance = self.store.booking_balance(booking_id)
        self.balance_label.configure(
            text=f"Booking total {money(booking['total_amount'] if booking else 0)} · outstanding {money(balance)}"
        )
        if "amount" in self.fields and not self.fields["amount"].get().strip("0. "):
            self.fields["amount"].variable.set(f"{max(balance, 0):.0f}")

    def commit(self) -> None:
        booking_id = self._selected_booking()
        if booking_id is None:
            raise ValueError("Choose the booking this payment belongs to.")
        self.store.record_payment(
            {
                "booking_id": booking_id,
                "entry_type": self.value("entry_type"),
                "method": self.value("method"),
                "amount": self.value("amount"),
                "paid_at": self.value("paid_at"),
                "notes": self.value("notes"),
                "recorded_by": self.username,
            }
        )


class ExtendDialog(FormDialog):
    """Push a booking's return date out and re-price it in one step."""

    def __init__(self, parent: tk.Widget, store: "Store", booking: dict[str, Any]) -> None:
        self.store = store
        self.booking = booking
        try:
            fallback = (
                datetime.strptime(str(booking["end_date"]), DATE_FORMAT) + timedelta(days=1)
            ).strftime(DATE_FORMAT)
        except ValueError:  # stored date malformed — fall back to tomorrow
            fallback = (datetime.now() + timedelta(days=1)).strftime(DATE_FORMAT)
        super().__init__(
            parent,
            f"Extend rental — {booking['booking_code']}",
            "Enter a later return date; the total is recalculated from the daily rate.",
        )
        self.add_field("end_date", "New return date (YYYY-MM-DD)", fallback, on_change=lambda _v: self._update_summary())
        self.summary = self.add_summary()
        self._update_summary()
        self._centre()

    def _update_summary(self) -> None:
        days = rental_days_between(str(self.booking["start_date"]), self.value("end_date"))
        if days is None:
            self.summary.configure(text="Enter the new return date as YYYY-MM-DD.")
            return
        rate = float(self.booking["rate_per_day"] or 0)
        extra = days - int(self.booking["rental_days"] or 0)
        note = f" · +{extra} day(s) · +{money(extra * rate)}" if extra > 0 else " · no change"
        self.summary.configure(
            text=f"{days} day(s) × {money(rate)} / day = {money(days * rate)}{note}"
        )

    def commit(self) -> None:
        self.store.extend_booking(int(self.booking["id"]), self.value("end_date"))


class UserDialog(FormDialog):
    """Create a staff account with its own password."""

    def __init__(self, parent: tk.Widget, store: "Store") -> None:
        self.store = store
        super().__init__(parent, "Add user", "Each account signs in with its own credentials; passwords are hashed.")
        self.add_field("username", "Username")
        self.add_field("full_name", "Full name")
        self.add_field("role", "Role", "staff", choices=USER_ROLES)
        self.add_field("password", "Password (min 8 characters)", secret=True)
        self._centre()

    def commit(self) -> None:
        self.store.add_user(
            self.value("username"),
            self.value("full_name"),
            self.value("role"),
            self.fields["password"].variable.get(),
        )


class PasswordDialog(FormDialog):
    """Reset an account password (admin action)."""

    def __init__(self, parent: tk.Widget, store: "Store", user: dict[str, Any]) -> None:
        self.store = store
        self.user = user
        super().__init__(parent, f"Reset password — {user['username']}", "The new password is hashed with PBKDF2 before it is stored.")
        self.add_field("password", "New password (min 8 characters)", secret=True)
        self.add_field("confirm", "Repeat password", secret=True)
        self._centre()

    def commit(self) -> None:
        password = self.fields["password"].variable.get()
        if password != self.fields["confirm"].variable.get():
            raise ValueError("The two passwords do not match.")
        self.store.reset_password(int(self.user["id"]), password)


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------


class Page(ttk.Frame):
    """Base page: header, body, and a refresh hook."""

    key = "dashboard"
    title = "Dashboard"
    subtitle = ""

    def __init__(self, master: tk.Widget, app: "MainWindow") -> None:
        super().__init__(master, style="Page.TFrame", padding=(26, 20))
        self.app = app
        self.store = app.store
        self.build()

    def build(self) -> None:
        heading(self, self.title, self.subtitle)

    def refresh(self) -> None:
        return


class DashboardPage(Page):
    key = "dashboard"
    title = "Dashboard"
    subtitle = "Fleet, bookings and flood risk at a glance"

    def build(self) -> None:
        heading(
            self,
            self.title,
            self.subtitle,
            [
                Button(self, text="Add customer", style="Secondary.TButton", command=self.add_customer),
                Button(self, text="New booking", style="Primary.TButton", command=lambda: self.app.open_new_booking()),
            ],
        )
        self.stat_row = ttk.Frame(self, style="Page.TFrame")
        self.stat_row.pack(fill="x", pady=(0, 14))
        self.stats = [
            Stat(self.stat_row, "Vehicles", tone="accent", glyph="▤", command=lambda: self.app.show_page("vehicles")),
            Stat(self.stat_row, "Active bookings", tone="info", glyph="▦", command=lambda: self.app.show_page("bookings")),
            Stat(self.stat_row, "Booking value", tone="ok", glyph="₱", command=lambda: self.app.show_page("transactions")),
            Stat(self.stat_row, "Open alerts", tone="danger", glyph="⚑", command=lambda: self.app.show_page("alerts")),
        ]
        for index, tile in enumerate(self.stats):
            self.stat_row.columnconfigure(index, weight=1, uniform="tiles")
            tile.grid(row=0, column=index, sticky="nsew", padx=(0 if index == 0 else 12, 0))

        _wrap, charts = grid_row(self, [lambda master: Card(master), lambda master: Card(master)], weights=[4, 3])
        left, right = charts
        card_title(left, "Collections by month", "Net cash movement recorded in each month")
        self.chart = Bars(left.body, height=150)
        self.chart.pack(fill="x", pady=(14, 2))

        card_title(right, "Flood-risk distribution", "Units grouped by the risk of their nearest active zone")
        self.bars: dict[str, Bar] = {}
        self.risk_counts: dict[str, ttk.Label] = {}
        self.risk_wrap = ttk.Frame(right.body, style="Card.TFrame")
        self.risk_wrap.pack(fill="x", pady=(14, 4))
        for level in RISK_LEVELS:
            row = ttk.Frame(self.risk_wrap, style="Card.TFrame")
            row.pack(fill="x", pady=4)
            ttk.Label(row, text=level.title(), style="BodyCard.TLabel", width=9, anchor="w").pack(side="left")
            meter = Bar(row, color=RISK_COLORS[level])
            meter.pack(side="left", fill="x", expand=True, padx=(8, 8))
            self.bars[level] = meter
            label = ttk.Label(row, text="0", style="MutedCard.TLabel", width=3, anchor="e")
            label.pack(side="right")
            self.risk_counts[level] = label

        _wrap, pair = grid_row(self, [lambda master: Card(master), lambda master: Card(master)], weights=[11, 9])
        map_card, exposure_card = pair
        card_title(map_card, "Fleet positions", "Live positions with active flood zones overlaid")
        self.map = MapCanvas(
            map_card.body, self.store, height=300, show_grid=False, legend=False, show_labels=True,
            border=False, feed=self.app.feed, detail="low",
        )
        self.map.pack(fill="both", expand=True, pady=(12, 0))
        card_title(exposure_card, "Nearest flood exposure", "Distance from each unit to its closest active zone")
        self.exposure_list = ttk.Frame(exposure_card.body, style="Card.TFrame")
        self.exposure_list.pack(fill="x", pady=(12, 0))

        _wrap, tables = grid_row(self, [lambda master: Card(master), lambda master: Card(master)], weights=[12, 9])
        booking_card, alert_card = tables
        card_title(booking_card, "Upcoming rentals", "Pending and confirmed bookings awaiting release")
        self.bookings_table = Table(
            booking_card.body,
            [
                ("booking_code", "Booking", 96, "w"),
                ("customer_name", "Customer", 150, "w"),
                ("start_date", "Start", 84, "w"),
                ("total_amount", "Total", 84, "e"),
                ("status", "Status", 92, "w"),
            ],
        )
        self.bookings_table.pack(fill="x", pady=(12, 0))
        card_title(alert_card, "Recent notices", "Alerts raised by the flood scan and by staff")
        self.alert_list = ttk.Frame(alert_card.body, style="Card.TFrame")
        self.alert_list.pack(fill="x", pady=(12, 0))
        self.refresh()

    def add_customer(self) -> None:
        """Open the Add-customer dialog straight from the dashboard."""
        dialog = CustomerDialog(self, self.store)
        self.wait_window(dialog)
        if not dialog.result:
            return
        self.refresh()
        self.app.refresh_all()

    def refresh(self) -> None:
        stats = self.store.dashboard()
        self.stats[0].set(str(stats["vehicles"]), f"{stats['available']} available · {stats['rented']} rented · {stats['maintenance']} in shop")
        self.stats[1].set(str(stats["bookings"]), f"{stats['ongoing']} on the road")
        self.stats[2].set(money(stats["value"]), f"{stats['bookings']} booking records")
        self.stats[3].set(str(stats["open_alerts"]), "Unacknowledged notices")
        self.chart.set(_monthly_labels(self.store.collections_by_month()))
        total_units = max(stats["vehicles"], 1)
        for level, count in self.store.risk_distribution():
            self.bars[level].set(count / total_units)
            self.risk_counts[level].configure(text=str(count))
        self.map.reload()

        for child in self.exposure_list.winfo_children():
            child.destroy()
        for item in self.store.exposure()[:6]:
            row = ttk.Frame(self.exposure_list, style="Card.TFrame")
            row.pack(fill="x", pady=3)
            swatch = tk.Canvas(row, width=3, height=22, background=PALETTE["surface"], highlightthickness=0, bd=0)
            swatch.create_rectangle(0, 0, 3, 22, fill=RISK_COLORS.get(item["zone_risk"], PALETTE["muted"]), outline="")
            swatch.pack(side="left", padx=(0, 8))
            text = ttk.Frame(row, style="Card.TFrame")
            text.pack(side="left", fill="x", expand=True)
            ttk.Label(text, text=f"{item['brand']} {item['model']}", style="BodyCard.TLabel").pack(anchor="w")
            ttk.Label(text, text=item["zone_name"], style="MutedCard.TLabel").pack(anchor="w")
            ttk.Label(row, text=f"{item['distance_km']:.2f} km", style="BodyCard.TLabel").pack(side="right", padx=(8, 0))
            ttk.Label(row, text="inside" if item["inside"] else "clear", style="DangerCard.TLabel" if item["inside"] else "MutedCard.TLabel").pack(side="right")

        upcoming = [row for row in self.store.bookings() if row["status"] in ("pending", "confirmed")]
        self.bookings_table.set_rows(
            [{**row, "total_amount": money(row["total_amount"])} for row in upcoming],
            tag_of=lambda row: {"pending": "warn", "confirmed": "info"}.get(row["status"]),
        )

        for child in self.alert_list.winfo_children():
            child.destroy()
        for alert in self.store.alerts()[:4]:
            block = ttk.Frame(self.alert_list, style="Card.TFrame")
            block.pack(fill="x", pady=4)
            dot = tk.Canvas(block, width=8, height=8, background=PALETTE["surface"], highlightthickness=0, bd=0)
            dot.create_oval(0, 0, 8, 8, fill=SEVERITY_COLORS.get(alert["severity"], PALETTE["muted"]), outline="")
            dot.pack(side="left", padx=(0, 8))
            text = ttk.Frame(block, style="Card.TFrame")
            text.pack(side="left", fill="x", expand=True)
            ttk.Label(text, text=alert["title"], style="BodyCard.TLabel").pack(anchor="w")
            ttk.Label(text, text=alert["created_at"], style="MutedCard.TLabel").pack(anchor="w")


class VehiclesPage(Page):
    key = "vehicles"
    title = "Vehicles"
    subtitle = "Inventory, availability, standing rate and last GPS position"

    def build(self) -> None:
        self.search = tk.StringVar()
        self.status = tk.StringVar(value="all")
        heading(
            self,
            self.title,
            self.subtitle,
            [
                Button(self, text="Export CSV", style="Secondary.TButton", command=self.export),
                Button(self, text="Edit unit", style="Quiet.TButton", command=self.edit_selected),
                Button(self, text="Add unit", style="Primary.TButton", command=self.add_unit),
            ],
        )
        bar = ttk.Frame(self, style="Page.TFrame")
        bar.pack(fill="x", pady=(0, 12))
        entry = PlaceholderEntry(bar, textvariable=self.search, placeholder="Search plate, brand or model...", width=32, style="Field.TEntry")
        entry.pack(side="left")
        entry.entry.bind("<KeyRelease>", lambda _event: self._schedule_refresh())
        self._refresh_job: str | None = None
        self.status_box = ttk.Combobox(
            bar, textvariable=self.status, values=["all", *VEHICLE_STATUSES], width=16, state="readonly", style="Field.TCombobox"
        )
        self.status_box.pack(side="left", padx=(8, 0))
        self.status_box.bind("<<ComboboxSelected>>", lambda _event: self.refresh())
        self.count = ttk.Label(bar, text="", style="Muted.TLabel")
        self.count.pack(side="right")

        _wrap, pair = grid_row(self, [lambda master: Card(master), lambda master: Card(master)], weights=[13, 8], gap=14)
        table_card, detail_card = pair
        self.table = Table(
            table_card.body,
            [
                ("unit", "Unit", 190, "w"),
                ("category", "Category", 96, "w"),
                ("seats", "Seats", 54, "e"),
                ("rate_per_day", "Rate / day", 92, "e"),
                ("status", "Status", 104, "w"),
                ("distance", "Nearest zone", 110, "e"),
            ],
            on_select=lambda key: self.show_detail(int(key) if key else None),
        )
        self.table.pack(fill="both", expand=True)
        self.detail = detail_card.body
        card_title(detail_card, "Vehicle record", "Select a row to inspect telemetry and exposure")
        self.show_detail(None)
        self.refresh()

    def export(self) -> None:
        columns, rows = self.store.report("vehicles")
        export_csv(self, "vehicles", columns, rows)

    def _schedule_refresh(self) -> None:
        """Debounce keystrokes so filtering stays instant on large fleets."""
        job = getattr(self, "_refresh_job", None)
        if job is not None:
            try:
                self.after_cancel(job)
            except tk.TclError:
                pass
        self._refresh_job = self.after(200, self._debounced_refresh)

    def _debounced_refresh(self) -> None:
        self._refresh_job = None
        if self.winfo_exists():
            self.refresh()

    # -- fleet management --------------------------------------------------
    def selected_vehicle(self) -> dict[str, Any] | None:
        key = self.table.selected()
        if not key:
            return None
        return self.store.row("SELECT * FROM vehicles WHERE id = ?", (int(key),))

    def add_unit(self) -> None:
        dialog = VehicleDialog(self, self.store)
        self.wait_window(dialog)
        if not dialog.result:
            return
        self.refresh()
        self.app.refresh_all()

    def edit_selected(self) -> None:
        vehicle = self.selected_vehicle()
        if vehicle is None:
            messagebox.showinfo(APP_NAME, "Select a unit to edit first.", parent=self)
            return
        dialog = VehicleDialog(self, self.store, vehicle)
        self.wait_window(dialog)
        if not dialog.result:
            return
        self.refresh()
        self.show_detail(int(vehicle["id"]))
        self.app.refresh_all()

    def delete_selected(self) -> None:
        vehicle = self.selected_vehicle()
        if vehicle is None:
            messagebox.showinfo(APP_NAME, "Select a unit to delete first.", parent=self)
            return
        if not confirm_delete(self, f"unit '{vehicle['plate_number']}'"):
            return
        try:
            self.store.delete_vehicle(int(vehicle["id"]))
        except (ValueError, RuntimeError) as error:
            handle_store_error(self, error)
            return
        self.refresh()
        self.show_detail(None)
        self.app.refresh_all()

    def new_booking_for(self) -> None:
        vehicle = self.selected_vehicle()
        if vehicle is None:
            return
        self.app.open_new_booking(vehicle=vehicle)

    def locate_on_map(self) -> None:
        vehicle = self.selected_vehicle()
        if vehicle is None:
            return
        self.app.focus_vehicle_on_map(int(vehicle["id"]))

    def toggle_shop(self) -> None:
        """One-click status flip between the shop floor and the yard."""
        vehicle = self.selected_vehicle()
        if vehicle is None:
            return
        target = "available" if vehicle["status"] == "maintenance" else "maintenance"
        try:
            self.store.set_vehicle_status(int(vehicle["id"]), target)
        except (ValueError, RuntimeError) as error:
            handle_store_error(self, error)
            return
        self.refresh()
        self.show_detail(int(vehicle["id"]))
        self.app.refresh_all()

    def view_bookings(self) -> None:
        vehicle = self.selected_vehicle()
        if vehicle is None:
            return
        self.app.open_bookings_for(str(vehicle["plate_number"]))

    def refresh(self) -> None:
        rows = self.store.vehicles(self.status.get(), self.search.get())
        zones = self.store.zones()  # one query for the whole table, not one per row
        prepared = []
        for row in rows:
            found = self.store.closest_zone(zones, row["latitude"], row["longitude"])
            prepared.append(
                {
                    **row,
                    "unit": f"{row['brand']} {row['model']}  ·  {row['plate_number']}",
                    "rate_per_day": money(row["rate_per_day"]),
                    "distance": f"{found[1]:.2f} km" if found else "—",
                }
            )
        self.table.set_rows(prepared, tag_of=lambda row: {"available": "ok", "rented": "info", "maintenance": "warn"}.get(row["status"]))
        total = self.store.value("SELECT COUNT(*) FROM vehicles") or 0
        self.count.configure(text=f"{len(rows)} of {total} units")

    def show_detail(self, vehicle_id: int | None) -> None:
        for child in self.detail.winfo_children():
            child.destroy()
        if vehicle_id is None:
            ttk.Label(
                self.detail,
                text="Select a vehicle to see its telemetry, exposure and service notes.",
                style="MutedCard.TLabel",
                wraplength=270,
                justify="left",
            ).pack(anchor="w", pady=(6, 0))
            return
        vehicle = self.store.row("SELECT * FROM vehicles WHERE id = ?", (vehicle_id,))
        if not vehicle:
            return
        found = self.store.nearest_zone(vehicle["latitude"], vehicle["longitude"])
        card_title_widget = ttk.Frame(self.detail, style="Card.TFrame")
        card_title_widget.pack(fill="x")
        ttk.Label(card_title_widget, text=f"{vehicle['brand']} {vehicle['model']}", style="TitleCard.TLabel").pack(anchor="w")
        ttk.Label(card_title_widget, text=f"{vehicle['plate_number']} · {vehicle['category']} · {vehicle['year']}", style="MutedCard.TLabel").pack(anchor="w", pady=(2, 6))

        facts = ttk.Frame(self.detail, style="Card.TFrame")
        facts.pack(fill="x", pady=(4, 0))
        items = [
            ("Seats", str(vehicle["seats"])),
            ("Rate / day", money(vehicle["rate_per_day"])),
            ("Odometer", f"{vehicle['odometer']:,} km"),
            ("Status", vehicle["status"]),
            ("Latitude", coordinate_text(vehicle["latitude"])),
            ("Longitude", coordinate_text(vehicle["longitude"])),
        ]
        for index, (label, value) in enumerate(items):
            box = ttk.Frame(facts, style="Card.TFrame")
            box.grid(row=index // 2, column=index % 2, sticky="nsew", padx=(0, 8), pady=3)
            ttk.Label(box, text=label.upper(), style="MicroCard.TLabel").pack(anchor="w")
            ttk.Label(box, text=value, style="BodyCard.TLabel").pack(anchor="w")
        facts.columnconfigure(0, weight=1)
        facts.columnconfigure(1, weight=1)

        if found:
            zone, kilometres = found
            panel = Card(self.detail, style="Card.TFrame", padding=(12, 10))
            panel.pack(fill="x", pady=(10, 0))
            ttk.Label(panel.body, text="NEAREST ZONE", style="MicroCard.TLabel").pack(anchor="w")
            ttk.Label(panel.body, text=zone["name"], style="TitleCard.TLabel").pack(anchor="w", pady=(2, 0))
            ttk.Label(
                panel.body,
                text=f"{kilometres:.2f} km away · radius {zone['radius_km']:.1f} km · {zone['risk_level']} risk",
                style="MutedCard.TLabel",
            ).pack(anchor="w")
        if vehicle["notes"]:
            ttk.Label(self.detail, text=vehicle["notes"], style="MutedCard.TLabel", wraplength=280, justify="left").pack(anchor="w", pady=(12, 0))

        history = self.store.vehicle_bookings(int(vehicle["id"]))
        if history:
            ttk.Label(self.detail, text="RECENT BOOKINGS", style="MicroCard.TLabel").pack(anchor="w", pady=(12, 4))
            for booking in history:
                row = ttk.Frame(self.detail, style="Card.TFrame")
                row.pack(fill="x", pady=1)
                ttk.Label(row, text=booking["booking_code"], style="BodyCard.TLabel").pack(side="left")
                ttk.Label(row, text=booking["customer_name"], style="MicroCard.TLabel").pack(side="left", padx=(8, 0))
                ttk.Label(row, text=booking["status"], style="MutedCard.TLabel").pack(side="right")

        buttons = ttk.Frame(self.detail, style="Card.TFrame")
        buttons.pack(fill="x", pady=(14, 0))
        Button(buttons, text="New booking", style="Primary.TButton", command=self.new_booking_for).pack(side="left")
        Button(buttons, text="View bookings", style="Secondary.TButton", command=self.view_bookings).pack(side="left", padx=(8, 0))
        buttons2 = ttk.Frame(self.detail, style="Card.TFrame")
        buttons2.pack(fill="x", pady=(8, 0))
        Button(
            buttons2,
            text="Mark available" if vehicle["status"] == "maintenance" else "Mark in shop",
            style="Quiet.TButton",
            command=self.toggle_shop,
        ).pack(side="left")
        Button(buttons2, text="Locate on map", style="Secondary.TButton", command=self.locate_on_map).pack(side="left", padx=(8, 0))
        Button(buttons2, text="Delete", style="Ghost.TButton", command=self.delete_selected).pack(side="left", padx=(8, 0))


# ---------------------------------------------------------------------------
# Shared page scaffolding
# ---------------------------------------------------------------------------


def export_csv(parent: tk.Widget, stem: str, columns: list[str], rows: list[list[Any]]) -> None:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    destination = filedialog.asksaveasfilename(
        parent=parent,
        title="Export report",
        defaultextension=".csv",
        initialfile=f"{stem}_{stamp}.csv",
        filetypes=[("CSV file", "*.csv"), ("All files", "*.*")],
    )
    if not destination:
        return
    try:
        with open(destination, "w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle)
            writer.writerow(columns)
            writer.writerows(rows)
    except OSError as error:
        messagebox.showerror(APP_NAME, f"The file could not be written:\n{error}", parent=parent)
        return
    logging.getLogger(__name__).info("Exported %s rows to %s", len(rows), destination)
    messagebox.showinfo(APP_NAME, f"Saved {len(rows)} rows to:\n{destination}", parent=parent)


_SCROLLCOLUMNS: list["ScrollColumn"] = []
_WHEEL_ROUTER_BOUND = False


def _route_wheel(event: tk.Event) -> None:
    """Send a mouse-wheel event to the ScrollColumn under the cursor.

    Wheel events land on whatever child widget sits beneath the pointer (the
    fleet-list buttons, alert cards…), so a binding on the canvas alone never
    fires there. A single app-wide router resolves the owning column from the
    event's widget path instead.
    """
    path = str(getattr(event, "widget", ""))
    for column in list(_SCROLLCOLUMNS):
        base = str(column.inner)
        if path == str(column.canvas) or path == base or path.startswith(base + "."):
            column.scroll_from_event(event)
            return


class ScrollColumn(ttk.Frame):
    """Vertically scrollable column of cards."""

    def __init__(self, master: tk.Widget, height: int = 380) -> None:
        super().__init__(master, style="CardBorder.TFrame", padding=1)
        holder = ttk.Frame(self, style="Card.TFrame")
        holder.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(holder, background=PALETTE["surface"], highlightthickness=0, bd=0)
        self.scroll = ttk.Scrollbar(holder, orient="vertical", command=self.canvas.yview, style="Thin.TScrollbar")
        self.inner = ttk.Frame(self.canvas, style="Card.TFrame")
        self.window_id = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scroll.set)
        self.canvas.pack(side="left", fill="both", expand=True, padx=(4, 0), pady=4)
        self.scroll.pack(side="right", fill="y", pady=4, padx=(0, 4))
        self.canvas.configure(height=height)
        self.inner.bind("<Configure>", lambda _event: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda event: self.canvas.itemconfigure(self.window_id, width=event.width))
        global _WHEEL_ROUTER_BOUND
        if not _WHEEL_ROUTER_BOUND:
            for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
                self.bind_all(sequence, _route_wheel, add="+")
            _WHEEL_ROUTER_BOUND = True
        _SCROLLCOLUMNS.append(self)

    def scroll_from_event(self, event: tk.Event) -> None:
        """Scroll one notch, whatever platform shape the event arrived in."""
        if event.type == tk.EventType.ButtonPress:  # Linux Button-4 / Button-5
            self.canvas.yview_scroll(-1 if getattr(event, "num", 5) == 4 else 1, "units")
            return
        delta = getattr(event, "delta", 0)
        if abs(delta) >= 120:  # Windows notches
            steps = -int(delta / 120)
        else:  # macOS smooth deltas
            steps = -1 if delta > 0 else 1
        self.canvas.yview_scroll(steps, "units")

    def destroy(self) -> None:
        if self in _SCROLLCOLUMNS:
            _SCROLLCOLUMNS.remove(self)
        super().destroy()


def fact(parent: tk.Widget, label: str, value: str) -> ttk.Frame:
    box = ttk.Frame(parent, style="Sunken.TFrame", padding=(10, 8))
    ttk.Label(box, text=label.upper(), style="MicroSunken.TLabel").pack(anchor="w")
    ttk.Label(box, text=value, style="BodySunken.TLabel").pack(anchor="w", pady=(1, 0))
    return box


class TogglePill(Button):
    """A layer switch that reads as a pill, not as a checkbox."""

    def __init__(self, master: tk.Widget, text: str, variable: tk.BooleanVar, command: Callable[[], None]) -> None:
        self.pill_text = text
        self.variable = variable
        super().__init__(master, text="", style="ToggleOn.TButton", command=self.toggle)
        self.command_hook = command
        self._apply()

    def toggle(self) -> None:
        self.variable.set(not self.variable.get())
        self._apply()
        if self.command_hook is not None:
            self.command_hook()

    def sync(self) -> None:
        """Re-read the variable (used when code toggles the layer directly)."""
        self._apply()

    def _apply(self) -> None:
        on = bool(self.variable.get())
        self.configure(
            text=f"●  {self.pill_text}" if on else f"○  {self.pill_text}",
            style="ToggleOn.TButton" if on else "ToggleOff.TButton",
        )


class PlaceholderEntry(ttk.Frame):
    """Single-line search field that shows quiet placeholder text.

    The hint lives on a label floating inside the entry, so the bound
    ``StringVar`` never contains placeholder text and search logic stays
    untouched. The hint clears the moment the field gains focus or holds a
    value, and returns when the field loses focus while empty.
    """

    def __init__(
        self,
        master: tk.Widget,
        textvariable: tk.StringVar | None = None,
        placeholder: str = "",
        **kwargs: Any,
    ) -> None:
        super().__init__(master, style="Card.TFrame")
        self._variable = textvariable if textvariable is not None else tk.StringVar()
        self._focused = False
        self.entry = ttk.Entry(self, textvariable=self._variable, **kwargs)
        self.entry.pack(fill="both", expand=True)
        self.hint = ttk.Label(
            self.entry, text=placeholder, style="FieldPlaceholder.TLabel", padding=(10, 0), anchor="w"
        )
        self.hint.place(x=0, y=0, relwidth=1, relheight=1)
        self.hint.bind("<Button-1>", lambda _event: self.entry.focus_set())
        self._variable.trace_add("write", lambda *_args: self._sync())
        self.entry.bind("<FocusIn>", self._on_focus_in)
        self.entry.bind("<FocusOut>", lambda _event: self._on_focus_out())
        self._sync()

    # expose the variable so callers can read the query straight away
    @property
    def variable(self) -> tk.StringVar:
        return self._variable

    def _on_focus_in(self, _event: tk.Event) -> None:
        self._focused = True
        self._sync()

    def _on_focus_out(self) -> None:
        self._focused = False
        self.after(10, self._sync)  # wait until the focus has actually moved

    def _sync(self) -> None:
        try:
            if self._focused or self._variable.get():
                self.hint.place_forget()
            else:
                self.hint.place(x=0, y=0, relwidth=1, relheight=1)
        except tk.TclError:  # widget already gone
            pass


class FleetList(ttk.Frame):
    """Fast canvas-drawn fleet roster.

    One canvas instead of a column of ttk buttons: refreshing the list on
    every keystroke stays instant even with a thousand units, each row gets a
    proper two-line layout (plate on top, model and zone distance beneath),
    and hover/selection are repainted without touching Tkinter widgets.
    """

    ROW_H = 46

    def __init__(self, master: tk.Widget, on_select: Callable[[int], None] | None = None, height: int = 260) -> None:
        super().__init__(master, style="CardBorder.TFrame", padding=1)
        self.on_select = on_select
        holder = ttk.Frame(self, style="Card.TFrame")
        holder.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(holder, background=PALETTE["surface"], highlightthickness=0, bd=0)
        self.scroll = ttk.Scrollbar(holder, orient="vertical", command=self.canvas.yview, style="Thin.TScrollbar")
        self.canvas.configure(yscrollcommand=self.scroll.set)
        self.canvas.pack(side="left", fill="both", expand=True, padx=(3, 0), pady=3)
        self.scroll.pack(side="right", fill="y", pady=3, padx=(0, 3))
        self.canvas.configure(height=height)
        # The app-wide wheel router resolves columns via `.canvas`/`.inner`;
        # pointing both at the canvas registers this list with the router.
        self.inner = self.canvas
        _SCROLLCOLUMNS.append(self)
        self.rows: list[dict[str, Any]] = []
        self.selected_id: int | None = None
        self.hover_index: int = -1
        self._width = 10
        self.canvas.bind("<Button-1>", self._on_click)
        self.canvas.bind("<Motion>", self._on_motion)
        self.canvas.bind("<Leave>", lambda _event: self._set_hover(-1))
        self.canvas.bind("<Configure>", lambda _event: self._on_resize())

    # -- data -------------------------------------------------------------
    def set_rows(self, rows: Sequence[dict[str, Any]], selected_id: int | None = None) -> None:
        self.rows = list(rows)
        self.selected_id = selected_id
        self.hover_index = -1
        self.canvas.configure(scrollregion=(0, 0, 0, max(len(self.rows) * self.ROW_H, 1)))
        self.redraw()

    def set_selected(self, vehicle_id: int | None) -> None:
        """Highlight a row without rebuilding the list."""
        if vehicle_id == self.selected_id:
            return
        previous = self.selected_id
        self.selected_id = vehicle_id
        for row_id in {previous, vehicle_id}:
            index = next((i for i, row in enumerate(self.rows) if row["id"] == row_id), None)
            if index is not None:
                self._paint_row(index)

    # -- painting ---------------------------------------------------------
    def redraw(self) -> None:
        canvas = self.canvas
        canvas.delete("all")
        self._width = max(canvas.winfo_width(), 10)
        if not self.rows:
            centre_y = max(canvas.winfo_height() / 2, 60)
            canvas.create_text(
                self._width / 2, centre_y - 10, text="No units match this filter",
                font=FONTS["small_bold"], fill=PALETTE["ink_soft"],
            )
            canvas.create_text(
                self._width / 2, centre_y + 12, text="Try a different plate, brand or model",
                font=FONTS["micro"], fill=PALETTE["faint"],
            )
            return
        for index in range(len(self.rows)):
            self._paint_row(index)

    def _paint_row(self, index: int) -> None:
        canvas = self.canvas
        row = self.rows[index]
        top = index * self.ROW_H
        selected = row["id"] == self.selected_id
        hovered = index == self.hover_index
        if selected:
            fill = PALETTE["accent_soft"]
        elif hovered:
            fill = PALETTE["sunken"]
        else:
            fill = PALETTE["surface"]
        canvas.create_rectangle(1, top, self._width - 1, top + self.ROW_H, fill=fill, outline="", tags=(f"row{index}",))
        if selected:
            canvas.create_rectangle(1, top + 5, 3.5, top + self.ROW_H - 5, fill=PALETTE["accent"], outline="", tags=(f"row{index}",))
        # status dot — filled when the unit is on the move, hollow without a fix
        dot_x, dot_y = 17, top + self.ROW_H / 2
        state = row.get("state", "")
        if state == "no fix":
            canvas.create_oval(dot_x - 3.2, dot_y - 3.2, dot_x + 3.2, dot_y + 3.2, outline=PALETTE["faint"], width=1.2, tags=(f"row{index}",))
        else:
            color = STATUS_COLORS.get(row.get("status"), PALETTE["accent"])
            if state == "maintenance":
                color = PALETTE["warn"]
            canvas.create_oval(dot_x - 3.8, dot_y - 3.8, dot_x + 3.8, dot_y + 3.8, fill=color, outline="", tags=(f"row{index}",))
            if state == "moving":
                canvas.create_oval(dot_x - 6.2, dot_y - 6.2, dot_x + 6.2, dot_y + 6.2, outline=_mix(color, "#FFFFFF", 0.35), width=1.2, tags=(f"row{index}",))
        ink = PALETTE["ink"] if selected else PALETTE["ink_soft"]
        canvas.create_text(
            31, top + 12, text=row.get("plate", ""), anchor="w",
            font=FONTS["small_bold"], fill=ink, tags=(f"row{index}",),
        )
        canvas.create_text(
            31, top + 30, text=row.get("model", ""), anchor="w",
            font=FONTS["micro"], fill=PALETTE["muted"], tags=(f"row{index}",),
        )
        right = row.get("right", "")
        if right:
            canvas.create_text(
                self._width - 12, top + 12, text=right, anchor="e",
                font=FONTS["micro_bold"], fill=PALETTE["accent"] if selected else PALETTE["muted"],
                tags=(f"row{index}",),
            )
        state_color = {
            "moving": PALETTE["ok"],
            "parked": PALETTE["muted"],
            "maintenance": PALETTE["warn"],
            "no fix": PALETTE["faint"],
        }.get(state, PALETTE["muted"])
        canvas.create_text(
            self._width - 12, top + 30, text=state, anchor="e",
            font=FONTS["micro"], fill=state_color, tags=(f"row{index}",),
        )

    # -- events -----------------------------------------------------------
    def _index_at(self, y: float) -> int:
        index = int(self.canvas.canvasy(y) // self.ROW_H)
        return index if 0 <= index < len(self.rows) else -1

    def _on_click(self, event: tk.Event) -> None:
        index = self._index_at(event.y)
        if index < 0 or self.on_select is None:
            return
        self.on_select(int(self.rows[index]["id"]))

    def _on_motion(self, event: tk.Event) -> None:
        self._set_hover(self._index_at(event.y))

    def _set_hover(self, index: int) -> None:
        if index == self.hover_index:
            return
        previous, self.hover_index = self.hover_index, index
        if 0 <= previous < len(self.rows):
            self._paint_row(previous)
        if 0 <= index < len(self.rows):
            self._paint_row(index)
            self.canvas.configure(cursor="hand2")
        else:
            self.canvas.configure(cursor="")

    def _on_resize(self) -> None:
        if self.rows:
            self.redraw()

    def scroll_from_event(self, event: tk.Event) -> None:
        """Scroll one notch, whatever platform shape the event arrived in."""
        if event.type == tk.EventType.ButtonPress:  # Linux Button-4 / Button-5
            self.canvas.yview_scroll(-1 if getattr(event, "num", 5) == 4 else 1, "units")
            return
        delta = getattr(event, "delta", 0)
        if abs(delta) >= 120:  # Windows notches
            steps = -int(delta / 120)
        else:  # macOS smooth deltas
            steps = -1 if delta > 0 else 1
        self.canvas.yview_scroll(steps, "units")

    def destroy(self) -> None:
        if self in _SCROLLCOLUMNS:
            _SCROLLCOLUMNS.remove(self)
        super().destroy()


class ListPage(Page):
    """Table page: search, optional filter, counter, data table and detail panel."""

    columns: list[tuple[str, str, int, str]] = []
    filters: list[str] = []
    search_hint = "Type to filter this list..."
    uses_detail = False
    detail_title = "Details"
    detail_hint = "Select a row to see more"

    def build(self) -> None:
        self.search = tk.StringVar()
        self.filter = tk.StringVar(value=self.filters[0] if self.filters else "all")
        heading(self, self.title, self.subtitle, self.actions())
        for widget in self.prefix():
            widget.pack(fill="x", pady=(0, 12))
        bar = ttk.Frame(self, style="Page.TFrame")
        bar.pack(fill="x", pady=(0, 12))
        entry = PlaceholderEntry(bar, textvariable=self.search, placeholder=self.search_hint, width=34, style="Field.TEntry")
        entry.pack(side="left")
        entry.entry.bind("<KeyRelease>", lambda _event: self._schedule_refresh())
        self._refresh_job: str | None = None
        if self.filters:
            box = ttk.Combobox(
                bar, textvariable=self.filter, values=self.filters, width=18, state="readonly", style="Field.TCombobox"
            )
            box.pack(side="left", padx=(8, 0))
            box.bind("<<ComboboxSelected>>", lambda _event: self.refresh())
        self.counter = ttk.Label(bar, text="", style="Muted.TLabel")
        self.counter.pack(side="right")
        if self.uses_detail:
            _wrap, pair = grid_row(self, [lambda master: Card(master), lambda master: Card(master)], weights=[13, 8], gap=14)
            table_card, detail_card = pair
            _wrap.pack_configure(expand=True)
            self.table = Table(table_card.body, self.columns, on_select=self.on_row_select, on_double=self.on_row_double)
            self.table.pack(fill="both", expand=True)
            self.detail = detail_card.body
            card_title(detail_card, self.detail_title, self.detail_hint)
            self.detail_body = ttk.Frame(self.detail, style="Card.TFrame")
            self.detail_body.pack(fill="x", pady=(12, 0))
            self.render_detail()
        else:
            holder = Card(self)
            self.table = Table(holder.body, self.columns, on_select=self.on_row_select, on_double=self.on_row_double)
            self.table.pack(fill="both", expand=True)
        self.refresh()

    def actions(self) -> list[tk.Widget]:
        return []

    def _schedule_refresh(self) -> None:
        """Debounce keystrokes so filtering stays instant on long lists."""
        job = getattr(self, "_refresh_job", None)
        if job is not None:
            try:
                self.after_cancel(job)
            except tk.TclError:
                pass
        self._refresh_job = self.after(200, self._debounced_refresh)

    def _debounced_refresh(self) -> None:
        self._refresh_job = None
        if self.winfo_exists():
            self.refresh()

    def prefix(self) -> list[tk.Widget]:
        return []

    def fetch(self) -> list[dict[str, Any]]:
        return []

    def tag_of(self, _row: dict[str, Any]) -> str | None:
        return None

    def on_row_select(self, _key: str) -> None:
        return

    def on_row_double(self, _key: str) -> None:
        return

    def render_detail(self) -> None:
        return

    def refresh(self) -> None:
        rows = self.fetch()
        self.table.set_rows(rows, tag_of=self.tag_of)
        self.counter.configure(text=f"{len(rows)} records")


class CustomersPage(ListPage):
    key = "customers"
    title = "Customers"
    subtitle = "Renter records, identification and contact details held locally"
    search_hint = "Search name, phone or e-mail..."
    columns = [
        ("full_name", "Customer", 190, "w"),
        ("phone", "Contact number", 150, "w"),
        ("email", "E-mail", 190, "w"),
        ("id_type", "ID type", 130, "w"),
        ("id_number", "ID number", 150, "w"),
    ]
    uses_detail = True
    detail_title = "Customer profile"
    detail_hint = "Contact, history and quick actions"

    def actions(self) -> list[tk.Widget]:
        return [
            Button(self, text="Export CSV", style="Secondary.TButton", command=self.export),
            Button(self, text="Delete", style="Secondary.TButton", command=self.delete_selected),
            Button(self, text="Edit customer", style="Quiet.TButton", command=self.edit_selected),
            Button(self, text="Add customer", style="Primary.TButton", command=self.add_customer),
        ]

    def export(self) -> None:
        columns, rows = self.store.report("customers")
        export_csv(self, "customers", columns, rows)

    def fetch(self) -> list[dict[str, Any]]:
        return self.store.customers(self.search.get())

    def tag_of(self, row: dict[str, Any]) -> str | None:
        return "info" if row.get("id_type") == "Company ID" else None

    # -- selection helpers ---------------------------------------------------
    def selected_profile(self) -> dict[str, Any] | None:
        key = self.table.selected()
        if not key:
            return None
        try:
            return self.store.customer_profile(int(key))
        except ValueError:
            return None

    def on_row_select(self, _key: str) -> None:
        self.render_detail()

    def on_row_double(self, _key: str) -> None:
        self.edit_selected()

    def focus_query(self, query: str) -> None:
        """Pre-filter the directory when another page deep-links here."""
        self.search.set(query)
        self.refresh()

    # -- actions --------------------------------------------------------------
    def add_customer(self) -> None:
        dialog = CustomerDialog(self, self.store)
        self.wait_window(dialog)
        if not dialog.result:
            return
        self.refresh()
        self.app.refresh_all()

    def edit_selected(self) -> None:
        key = self.table.selected()
        if not key:
            messagebox.showinfo(APP_NAME, "Select a customer to edit first.", parent=self)
            return
        customer = self.store.row("SELECT * FROM customers WHERE id = ?", (int(key),))
        if customer is None:
            return
        dialog = CustomerDialog(self, self.store, customer)
        self.wait_window(dialog)
        if not dialog.result:
            return
        self.refresh()
        self.render_detail()
        self.app.refresh_all()

    def delete_selected(self) -> None:
        key = self.table.selected()
        if not key:
            messagebox.showinfo(APP_NAME, "Select a customer to delete first.", parent=self)
            return
        customer = self.store.row("SELECT full_name FROM customers WHERE id = ?", (int(key),))
        if customer is None:
            return
        if not confirm_delete(self, f"customer '{customer['full_name']}'"):
            return
        try:
            self.store.delete_customer(int(key))
        except (ValueError, RuntimeError) as error:
            handle_store_error(self, error)
            return
        self.refresh()
        self.render_detail()
        self.app.refresh_all()

    def new_booking(self) -> None:
        profile = self.selected_profile()
        if profile is None:
            messagebox.showinfo(APP_NAME, "Select a customer first.", parent=self)
            return
        self.app.open_new_booking(customer=profile)

    def view_bookings(self) -> None:
        """Open the bookings page pre-filtered on this renter's full history."""
        profile = self.selected_profile()
        if profile is None:
            return
        self.app.open_bookings_for(str(profile["full_name"]))

    def locate_pin(self) -> None:
        profile = self.selected_profile()
        if profile is None or profile.get("latitude") is None:
            return
        self.app.focus_customer_on_map(int(profile["id"]))

    # -- detail rendering -------------------------------------------------------
    def render_detail(self) -> None:
        for child in self.detail_body.winfo_children():
            child.destroy()
        profile = self.selected_profile()
        if profile is None:
            ttk.Label(
                self.detail_body,
                text="Select a customer to see their contact details, booking history and quick actions.",
                style="MutedCard.TLabel",
                wraplength=260,
                justify="left",
            ).pack(anchor="w")
            return
        ttk.Label(self.detail_body, text=profile["full_name"], style="HeadingCard.TLabel").pack(anchor="w")
        ttk.Label(self.detail_body, text=f"{profile['phone']}  ·  {profile['email'] or 'no e-mail'}", style="MutedCard.TLabel", wraplength=260, justify="left").pack(anchor="w", pady=(3, 0))
        facts = ttk.Frame(self.detail_body, style="Card.TFrame")
        facts.pack(fill="x", pady=(12, 0))
        items = [
            ("ID", f"{profile['id_type']} · {profile['id_number'] or '—'}"),
            ("License", profile["license_number"] or "—"),
            ("Bookings", str(profile["booking_count"])),
            ("Lifetime value", money(profile["lifetime_value"])),
        ]
        for index, (label, value) in enumerate(items):
            box = ttk.Frame(facts, style="Sunken.TFrame", padding=(9, 7))
            box.grid(row=index // 2, column=index % 2, sticky="nsew", padx=(0, 8), pady=(0, 8))
            ttk.Label(box, text=label.upper(), style="MicroSunken.TLabel").pack(anchor="w")
            ttk.Label(box, text=value, style="BodySunken.TLabel", wraplength=150, justify="left").pack(anchor="w")
        facts.columnconfigure(0, weight=1)
        facts.columnconfigure(1, weight=1)
        if profile["address"]:
            ttk.Label(self.detail_body, text=profile["address"], style="MutedCard.TLabel", wraplength=260, justify="left").pack(anchor="w", pady=(2, 0))

        history = profile["bookings"][:4]
        if history:
            ttk.Label(self.detail_body, text="RECENT BOOKINGS", style="MicroCard.TLabel").pack(anchor="w", pady=(12, 4))
            for booking in history:
                row = ttk.Frame(self.detail_body, style="Card.TFrame")
                row.pack(fill="x", pady=1)
                ttk.Label(row, text=booking["booking_code"], style="BodyCard.TLabel").pack(side="left")
                ttk.Label(row, text=f"{booking['start_date']} → {booking['end_date']}", style="MicroCard.TLabel").pack(side="left", padx=(8, 0))
                ttk.Label(row, text=booking["status"], style="MutedCard.TLabel").pack(side="right")

        buttons = ttk.Frame(self.detail_body, style="Card.TFrame")
        buttons.pack(fill="x", pady=(14, 0))
        Button(buttons, text="New booking", style="Primary.TButton", command=self.new_booking).pack(side="left")
        Button(buttons, text="All bookings", style="Secondary.TButton", command=self.view_bookings).pack(side="left", padx=(8, 0))
        if profile.get("latitude") is not None and profile.get("longitude") is not None:
            Button(buttons, text="Locate pin", style="Secondary.TButton", command=self.locate_pin).pack(side="left", padx=(8, 0))


class BookingsPage(ListPage):
    key = "bookings"
    title = "Bookings"
    subtitle = "Rental periods, destinations, deposits and running totals"
    search_hint = "Search code, customer or unit..."
    columns = [
        ("booking_code", "Code", 104, "w"),
        ("customer_name", "Customer", 160, "w"),
        ("unit", "Unit", 170, "w"),
        ("start_date", "Start", 88, "w"),
        ("end_date", "End", 88, "w"),
        ("rental_days", "Days", 50, "e"),
        ("deposit", "Deposit", 84, "e"),
        ("total_amount", "Total", 92, "e"),
        ("status", "Status", 100, "w"),
    ]
    filters = ["all", *BOOKING_STATUSES]
    uses_detail = True
    detail_title = "Booking detail"
    detail_hint = "Rental summary and quick actions"

    def actions(self) -> list[tk.Widget]:
        return [
            Button(self, text="Export CSV", style="Secondary.TButton", command=self.export),
            Button(self, text="Extend booking", style="Secondary.TButton", command=self.extend_selected),
            Button(self, text="Cancel booking", style="Secondary.TButton", command=self.cancel_selected),
            Button(self, text="Edit booking", style="Quiet.TButton", command=self.edit_selected),
            Button(self, text="New booking", style="Primary.TButton", command=self.new_booking),
        ]

    def export(self) -> None:
        columns, rows = self.store.report("bookings")
        export_csv(self, "bookings", columns, rows)

    def fetch(self) -> list[dict[str, Any]]:
        rows = self.store.bookings(self.filter.get(), self.search.get())
        return [
            {
                **row,
                "_total": float(row["total_amount"] or 0),
                "unit": f"{row['brand']} {row['model']}",
                "deposit": money(row["deposit"]),
                "total_amount": money(row["total_amount"]),
            }
            for row in rows
        ]

    def tag_of(self, row: dict[str, Any]) -> str | None:
        return {"ongoing": "info", "confirmed": "info", "pending": "warn", "completed": "ok", "cancelled": "danger"}.get(row["status"])

    def refresh(self) -> None:
        rows = self.fetch()
        self.table.set_rows(rows, tag_of=self.tag_of)
        total = sum(row["_total"] for row in rows if row["status"] != "cancelled")
        self.counter.configure(text=f"{len(rows)} bookings · {money(total)}")
        self.render_detail()

    # -- selection ------------------------------------------------------------
    def selected_booking(self) -> dict[str, Any] | None:
        key = self.table.selected()
        if not key:
            return None
        return self.store.row(
            "SELECT b.*, v.plate_number, v.brand, v.model, v.status AS vehicle_status, c.full_name AS customer_name,"
            " c.phone AS customer_phone FROM bookings b JOIN vehicles v ON v.id = b.vehicle_id"
            " JOIN customers c ON c.id = b.customer_id WHERE b.id = ?",
            (int(key),),
        )

    def on_row_select(self, _key: str) -> None:
        self.render_detail()

    def on_row_double(self, _key: str) -> None:
        self.edit_selected()

    # -- actions ---------------------------------------------------------------
    def new_booking(self) -> None:
        self.app.open_new_booking()

    def focus_query(self, query: str) -> None:
        """Pre-filter the table when another page deep-links here."""
        self.search.set(query)
        self.filter.set("all")
        self.refresh()

    def set_status(self, status: str) -> None:
        """One-click workflow step: confirm, start or finish the rental."""
        booking = self.selected_booking()
        if booking is None:
            return
        try:
            self.store.set_booking_status(int(booking["id"]), status)
        except (ValueError, RuntimeError) as error:
            handle_store_error(self, error)
            return
        self.refresh()
        self.app.refresh_all()

    def extend_selected(self) -> None:
        booking = self.selected_booking()
        if booking is None:
            messagebox.showinfo(APP_NAME, "Select a booking to extend first.", parent=self)
            return
        if booking["status"] in ("completed", "cancelled"):
            messagebox.showinfo(APP_NAME, f"Booking {booking['booking_code']} is already {booking['status']}.", parent=self)
            return
        dialog = ExtendDialog(self, self.store, booking)
        self.wait_window(dialog)
        if not dialog.result:
            return
        self.refresh()
        self.app.refresh_all()

    def open_customer(self) -> None:
        booking = self.selected_booking()
        if booking is None:
            return
        self.app.open_customers_for(str(booking["customer_name"]))

    def edit_selected(self) -> None:
        booking = self.selected_booking()
        if booking is None:
            messagebox.showinfo(APP_NAME, "Select a booking to edit first.", parent=self)
            return
        dialog = BookingDialog(self, self.store, booking)
        self.wait_window(dialog)
        if not dialog.result:
            return
        self.refresh()
        self.app.refresh_all()

    def cancel_selected(self) -> None:
        booking = self.selected_booking()
        if booking is None:
            messagebox.showinfo(APP_NAME, "Select a booking to cancel first.", parent=self)
            return
        if booking["status"] in ("completed", "cancelled"):
            messagebox.showinfo(APP_NAME, f"Booking {booking['booking_code']} is already {booking['status']}.", parent=self)
            return
        if not messagebox.askyesno(APP_NAME, f"Cancel booking {booking['booking_code']} for {booking['customer_name']}?", parent=self):
            return
        try:
            self.store.cancel_booking(int(booking["id"]))
        except (ValueError, RuntimeError) as error:
            handle_store_error(self, error)
            return
        self.refresh()
        self.app.refresh_all()

    def record_payment(self) -> None:
        booking = self.selected_booking()
        self.app.open_payment_dialog(int(booking["id"]) if booking else None)

    def locate_unit(self) -> None:
        booking = self.selected_booking()
        if booking is None:
            return
        self.app.focus_vehicle_on_map(int(booking["vehicle_id"]))

    def locate_pickup(self) -> None:
        booking = self.selected_booking()
        if booking is None or booking.get("pickup_latitude") is None:
            return
        self.app.focus_point_on_map(float(booking["pickup_latitude"]), float(booking["pickup_longitude"]), span=5.0)

    # -- detail -----------------------------------------------------------------
    def render_detail(self) -> None:
        if not hasattr(self, "detail_body"):
            return
        for child in self.detail_body.winfo_children():
            child.destroy()
        booking = self.selected_booking()
        if booking is None:
            ttk.Label(
                self.detail_body,
                text="Select a booking to see the rental summary, balance and quick actions.",
                style="MutedCard.TLabel",
                wraplength=260,
                justify="left",
            ).pack(anchor="w")
            return
        ttk.Label(self.detail_body, text=booking["booking_code"], style="HeadingCard.TLabel").pack(anchor="w")
        ttk.Label(self.detail_body, text=f"{booking['customer_name']} · {booking['customer_phone'] or 'no contact'}", style="MutedCard.TLabel", wraplength=260, justify="left").pack(anchor="w", pady=(3, 0))
        facts = ttk.Frame(self.detail_body, style="Card.TFrame")
        facts.pack(fill="x", pady=(12, 0))
        balance = self.store.booking_balance(int(booking["id"]))
        items = [
            ("Unit", f"{booking['brand']} {booking['model']}"),
            ("Plate", booking["plate_number"]),
            ("Period", f"{booking['start_date']} → {booking['end_date']}"),
            ("Days", str(booking["rental_days"])),
            ("Rate / day", money(booking["rate_per_day"])),
            ("Total", money(booking["total_amount"])),
            ("Deposit", money(booking["deposit"])),
            ("Balance", money(balance)),
        ]
        for index, (label, value) in enumerate(items):
            box = ttk.Frame(facts, style="Sunken.TFrame", padding=(9, 7))
            box.grid(row=index // 2, column=index % 2, sticky="nsew", padx=(0, 8), pady=(0, 8))
            ttk.Label(box, text=label.upper(), style="MicroSunken.TLabel").pack(anchor="w")
            ttk.Label(box, text=value, style="BodySunken.TLabel", wraplength=150, justify="left").pack(anchor="w")
        facts.columnconfigure(0, weight=1)
        facts.columnconfigure(1, weight=1)
        route = []
        if booking["pickup_location"]:
            route.append(f"Pickup: {booking['pickup_location']}")
        if booking["destination"]:
            route.append(f"Destination: {booking['destination']}")
        if route:
            ttk.Label(self.detail_body, text="\n".join(route), style="MutedCard.TLabel", wraplength=260, justify="left").pack(anchor="w", pady=(4, 0))

        transitions: dict[str, list[tuple[str, str, str]]] = {
            "pending": [("Confirm booking", "confirmed", "Primary.TButton"), ("Start rental", "ongoing", "Quiet.TButton")],
            "confirmed": [("Start rental", "ongoing", "Primary.TButton")],
            "ongoing": [("Complete rental", "completed", "Primary.TButton")],
        }
        workflow = ttk.Frame(self.detail_body, style="Card.TFrame")
        workflow.pack(fill="x", pady=(14, 0))
        for text, target, style_name in transitions.get(str(booking["status"]), []):
            Button(
                workflow, text=text, style=style_name,
                command=lambda target_status=target: self.set_status(target_status),
            ).pack(side="left", padx=(0, 8))
        if not transitions.get(str(booking["status"])):
            ttk.Label(
                self.detail_body,
                text=f"This booking is {booking['status']} — no further workflow steps.",
                style="MutedCard.TLabel",
            ).pack(anchor="w", pady=(14, 0))
        buttons = ttk.Frame(self.detail_body, style="Card.TFrame")
        buttons.pack(fill="x", pady=(10, 0))
        Button(buttons, text="Record payment", style="Secondary.TButton", command=self.record_payment).pack(side="left")
        Button(buttons, text="Open customer", style="Secondary.TButton", command=self.open_customer).pack(side="left", padx=(8, 0))
        Button(buttons, text="Locate unit", style="Ghost.TButton", command=self.locate_unit).pack(side="left", padx=(8, 0))
        if booking.get("pickup_latitude") is not None:
            Button(buttons, text="Pickup pin", style="Ghost.TButton", command=self.locate_pickup).pack(side="left", padx=(8, 0))


class TransactionsPage(ListPage):
    key = "transactions"
    title = "Transactions"
    subtitle = "Payments, deposits and refunds recorded against each booking"
    search_hint = "Search reference or booking code..."
    columns = [
        ("reference", "Reference", 118, "w"),
        ("booking_code", "Booking", 108, "w"),
        ("entry_type", "Type", 92, "w"),
        ("method", "Method", 118, "w"),
        ("recorded_by", "Recorded by", 108, "w"),
        ("paid_at", "Paid at", 140, "w"),
        ("amount", "Amount", 100, "e"),
    ]
    filters = ["all", *PAYMENT_TYPES]

    def actions(self) -> list[tk.Widget]:
        return [
            Button(self, text="Export CSV", style="Secondary.TButton", command=self.export),
            Button(self, text="Record payment", style="Primary.TButton", command=self.record_payment),
        ]

    def export(self) -> None:
        columns, rows = self.store.report("transactions")
        export_csv(self, "transactions", columns, rows)

    def record_payment(self) -> None:
        self.app.open_payment_dialog()

    def prefix(self) -> list[tk.Widget]:
        wrap = ttk.Frame(self, style="Page.TFrame")
        self.collected = Stat(wrap, "Collected", tone="ok", glyph="₱")
        self.refunded = Stat(wrap, "Refunded", tone="danger", glyph="↩")
        self.net = Stat(wrap, "Net cash", tone="accent", glyph="≡")
        for index, tile in enumerate((self.collected, self.refunded, self.net)):
            wrap.columnconfigure(index, weight=1, uniform="money")
            tile.grid(row=0, column=index, sticky="nsew", padx=(0 if index == 0 else 10, 0))
        return [wrap]

    def fetch(self) -> list[dict[str, Any]]:
        return [
            {**row, "amount": money(row["amount"])}
            for row in self.store.transactions(self.filter.get(), self.search.get())
        ]

    def tag_of(self, row: dict[str, Any]) -> str | None:
        return {"payment": "ok", "deposit": "info", "refund": "danger"}.get(row["entry_type"])

    def refresh(self) -> None:
        super().refresh()
        collected = float(self.store.value(
            "SELECT COALESCE(SUM(CASE WHEN entry_type != 'refund' THEN amount ELSE 0 END), 0) FROM transactions"
        ) or 0)
        refunded = float(self.store.value(
            "SELECT COALESCE(SUM(CASE WHEN entry_type = 'refund' THEN amount ELSE 0 END), 0) FROM transactions"
        ) or 0)
        count = int(self.store.value("SELECT COUNT(*) FROM transactions") or 0)
        self.collected.set(money(collected), f"{count} entries")
        self.refunded.set(money(refunded), "Returned to renters")
        self.net.set(money(collected - refunded), "After refunds")


class UsersPage(ListPage):
    key = "users"
    title = "Users"
    subtitle = "Accounts, roles and password policy — hashes only, never plain text"
    search_hint = "Search account or username..."
    columns = [
        ("full_name", "Account", 190, "w"),
        ("username", "Username", 130, "w"),
        ("role", "Role", 100, "w"),
        ("last_seen", "Last seen", 140, "w"),
        ("state", "State", 100, "w"),
    ]
    uses_detail = True
    detail_title = "Account"
    detail_hint = "Role summary and admin actions"

    def actions(self) -> list[tk.Widget]:
        return [
            Button(self, text="Disable account", style="Secondary.TButton", command=self.toggle_selected),
            Button(self, text="Reset password", style="Quiet.TButton", command=self.reset_password),
            Button(self, text="Add user", style="Primary.TButton", command=self.add_user),
        ]

    def prefix(self) -> list[tk.Widget]:
        wrap = ttk.Frame(self, style="Page.TFrame")
        for index, (role, description) in enumerate(
            (
                ("Admin", "Full access, including user accounts, backups and settings."),
                ("Manager", "Fleet, bookings, transactions, zones, reports and alerts."),
                ("Staff", "Bookings, customers and vehicle lookup only."),
            )
        ):
            card = Card(wrap, padding=(14, 12))
            wrap.columnconfigure(index, weight=1, uniform="roles")
            card.grid(row=0, column=index, sticky="nsew", padx=(0 if index == 0 else 10, 0))
            ttk.Label(card.body, text=role, style="TitleCard.TLabel").pack(anchor="w")
            ttk.Label(card.body, text=description, style="MutedCard.TLabel", wraplength=200, justify="left").pack(anchor="w", pady=(4, 0))
        return [wrap]

    def fetch(self) -> list[dict[str, Any]]:
        return [
            {**row, "state": "active" if row["is_active"] else "disabled", "last_seen": row["last_seen"] or "never"}
            for row in self.store.users()
        ]

    def tag_of(self, row: dict[str, Any]) -> str | None:
        return {"admin": "accent", "manager": "info", "staff": "muted"}.get(row["role"])

    # -- selection ------------------------------------------------------------
    def selected_user(self) -> dict[str, Any] | None:
        key = self.table.selected()
        if not key:
            return None
        return self.store.row("SELECT * FROM users WHERE id = ?", (int(key),))

    def on_row_select(self, _key: str) -> None:
        self.render_detail()

    # -- actions ---------------------------------------------------------------
    def add_user(self) -> None:
        dialog = UserDialog(self, self.store)
        self.wait_window(dialog)
        if not dialog.result:
            return
        self.refresh()
        self.render_detail()

    def reset_password(self) -> None:
        user = self.selected_user()
        if user is None:
            messagebox.showinfo(APP_NAME, "Select an account first.", parent=self)
            return
        dialog = PasswordDialog(self, self.store, user)
        self.wait_window(dialog)
        if not dialog.result:
            return
        messagebox.showinfo(APP_NAME, f"The password for {user['username']} was reset.", parent=self)

    def toggle_selected(self) -> None:
        user = self.selected_user()
        if user is None:
            messagebox.showinfo(APP_NAME, "Select an account first.", parent=self)
            return
        disable = bool(user["is_active"])
        verb = "Disable" if disable else "Re-enable"
        if not messagebox.askyesno(APP_NAME, f"{verb} the account '{user['username']}'?", parent=self):
            return
        try:
            self.store.set_user_active(int(user["id"]), not disable)
        except (ValueError, RuntimeError) as error:
            handle_store_error(self, error)
            return
        self.refresh()
        self.render_detail()

    # -- detail ------------------------------------------------------------------
    def render_detail(self) -> None:
        if not hasattr(self, "detail_body"):
            return
        for child in self.detail_body.winfo_children():
            child.destroy()
        user = self.selected_user()
        if user is None:
            ttk.Label(
                self.detail_body,
                text="Select an account to review its role, activity and available admin actions.",
                style="MutedCard.TLabel",
                wraplength=260,
                justify="left",
            ).pack(anchor="w")
            return
        ttk.Label(self.detail_body, text=user["full_name"], style="HeadingCard.TLabel").pack(anchor="w")
        ttk.Label(self.detail_body, text=f"@{user['username']} · {user['role'].title()} · {'active' if user['is_active'] else 'disabled'}", style="MutedCard.TLabel").pack(anchor="w", pady=(3, 0))
        box = ttk.Frame(self.detail_body, style="Sunken.TFrame", padding=(10, 8))
        box.pack(fill="x", pady=(12, 0))
        ttk.Label(box, text="LAST SEEN", style="MicroSunken.TLabel").pack(anchor="w")
        ttk.Label(box, text=user["last_seen"] or "never signed in", style="BodySunken.TLabel").pack(anchor="w")
        ttk.Label(self.detail_body, text="PASSWORDS", style="MicroCard.TLabel").pack(anchor="w", pady=(12, 2))
        ttk.Label(
            self.detail_body,
            "Passwords are stored as PBKDF2-SHA256 hashes with a random salt. "
            "Use 'Reset password' to hand a colleague a fresh temporary password.",
            style="MutedCard.TLabel",
            wraplength=260,
            justify="left",
        ).pack(anchor="w")


class GpsMapPage(Page):
    key = "gps"
    title = "GPS map"
    subtitle = "Fleet positions with flood zones overlaid · drag to pan, scroll to zoom"

    def build(self) -> None:
        self.selected: dict[str, Any] | None = None
        heading(
            self,
            self.title,
            self.subtitle,
            [
                Button(self, text="Fit fleet", style="Secondary.TButton", command=lambda: self.map.fit_fleet()),
                Button(self, text="Reset view", style="Secondary.TButton", command=lambda: self.map.reset()),
                Button(self, text="Zoom in", style="Ghost.TButton", command=lambda: self.map.zoom_in()),
                Button(self, text="Zoom out", style="Ghost.TButton", command=lambda: self.map.zoom_out()),
            ],
        )
        _wrap, pair = grid_row(self, [lambda master: Card(master), lambda master: Card(master)], weights=[16, 7], gap=14)
        _wrap.pack_configure(expand=True)
        map_card, side_card = pair
        card_title(
            map_card,
            "Metro Manila",
            "Drag to pan · wheel or double-click to zoom · arrows to step · F fits the fleet",
        )
        self.map = MapCanvas(
            map_card.body,
            self.store,
            height=470,
            on_select=self.select,
            border=False,
            feed=self.app.feed,
            show_bookings=True,
            show_customers=False,
            detail=self.app.store.settings().get("map_detail", "medium"),
        )
        self.map.pack(fill="both", expand=True, pady=(12, 0))
        try:
            zoom_span = {"10": 55.0, "11": 30.0, "12": 20.0, "13": 13.0, "14": 8.0}.get(
                self.app.store.settings().get("map_zoom", "13"), 13.0
            )
            self.map.span_km = zoom_span
        except (TypeError, ValueError):
            pass

        controls = ttk.Frame(map_card.body, style="Card.TFrame")
        controls.pack(fill="x", pady=(10, 0))
        self.play_button = Button(
            controls, text="Pause feed", style="Primary.TButton", command=self.toggle_feed
        )
        self.play_button.pack(side="left")
        self.speed_var = tk.StringVar(value=f"{self.app.feed.speed:g}×")
        ttk.Label(controls, text="SPEED", style="MicroCard.TLabel").pack(side="left", padx=(14, 6))
        # segmented pills instead of a spinbox — one click, visible state
        self.speed_buttons: list[Button] = []
        for choice in ("1×", "4×", "16×", "60×"):
            button = Button(
                controls, text=choice, width=52, style="ToggleOff.TButton",
                command=lambda picked=choice: self.set_feed_speed(picked),
            )
            button.pack(side="left", padx=(0, 4))
            self.speed_buttons.append(button)
        self._style_speed_buttons()
        self.live_var = tk.StringVar(value=self.app.feed.status())
        ttk.Label(controls, textvariable=self.live_var, style="MutedCard.TLabel").pack(side="right")
        self.bind("<Destroy>", lambda _event: self._stop_live_poll())
        self._poll_live()

        # layer switches — pill toggles that match the app chrome
        self.show_vehicles = tk.BooleanVar(value=True)
        self.show_zones = tk.BooleanVar(value=True)
        self.show_labels = tk.BooleanVar(value=True)
        self.show_grid = tk.BooleanVar(value=True)
        self.show_bookings = tk.BooleanVar(value=True)
        self.show_customers = tk.BooleanVar(value=False)
        options = ttk.Frame(map_card.body, style="Card.TFrame")
        options.pack(fill="x", pady=(10, 0))
        self.pills: dict[str, TogglePill] = {}
        for key, label, variable in (
            ("vehicles", "Vehicles", self.show_vehicles),
            ("zones", "Flood zones", self.show_zones),
            ("bookings", "Booking pins", self.show_bookings),
            ("customers", "Customer pins", self.show_customers),
            ("labels", "Place labels", self.show_labels),
            ("grid", "Lat/lon grid", self.show_grid),
        ):
            pill = TogglePill(options, label, variable, self.apply_layers)
            pill.pack(side="left", padx=(0, 8))
            self.pills[key] = pill

        card_title(side_card, "Fleet list", "Select a unit to focus the map")
        search_row = ttk.Frame(side_card.body, style="Card.TFrame")
        search_row.pack(fill="x", pady=(12, 0))
        self.query = tk.StringVar()
        list_entry = PlaceholderEntry(
            search_row, textvariable=self.query, placeholder="Search plate or model...", width=22, style="Field.TEntry"
        )
        list_entry.pack(side="left", fill="x", expand=True)
        list_entry.entry.bind("<KeyRelease>", lambda _event: self._schedule_list_refresh())
        self.list_count = ttk.Label(search_row, text="", style="MutedCard.TLabel")
        self.list_count.pack(side="right", padx=(8, 0))
        self.listing = FleetList(side_card.body, on_select=self.select, height=248)
        self.listing.pack(fill="both", expand=True, pady=(8, 0))
        self.detail = ttk.Frame(side_card.body, style="Card.TFrame")
        self.detail.pack(fill="x", pady=(12, 0))
        self._refresh_job: str | None = None
        self._data_seen: int | None = None
        self.refresh()

    def toggle_feed(self) -> None:
        running = self.app.feed.toggle()
        self.play_button.configure(text="Pause feed" if running else "Resume feed")
        self._update_live_status()

    def set_feed_speed(self, choice: str | None = None) -> None:
        if choice is not None:
            self.speed_var.set(choice)
        try:
            factor = float(self.speed_var.get().rstrip("×xX"))
        except ValueError:
            factor = 1.0
        self.app.feed.set_speed(factor)
        self._style_speed_buttons()
        self._update_live_status()

    def _style_speed_buttons(self) -> None:
        """Highlight the pill matching the current speed factor."""
        current = self.speed_var.get()
        for button in getattr(self, "speed_buttons", []):
            on = button.cget("text") == current
            button.configure(style="ToggleOn.TButton" if on else "ToggleOff.TButton")

    def _update_live_status(self) -> None:
        self.live_var.set(self.app.feed.status())

    def _poll_live(self) -> None:
        self._live_job = self.after(1200, self._poll_live_tick)

    def _poll_live_tick(self) -> None:
        if not self.winfo_exists():
            return
        self._update_live_status()
        if self.selected is not None:
            if getattr(self, "_detail_values", None):
                self._update_detail_values()
            else:
                self.render_detail()
        self._poll_live()

    def _stop_live_poll(self) -> None:
        job = getattr(self, "_live_job", None)
        if job is not None:
            try:
                self.after_cancel(job)
            except tk.TclError:
                pass
            self._live_job = None

    def _schedule_list_refresh(self) -> None:
        """Debounce the search box so typing stays instant on big fleets."""
        job = getattr(self, "_refresh_job", None)
        if job is not None:
            try:
                self.after_cancel(job)
            except tk.TclError:
                pass
        self._refresh_job = self.after(200, self._debounced_refresh)

    def _debounced_refresh(self) -> None:
        self._refresh_job = None
        if self.winfo_exists():
            self.refresh()

    def apply_layers(self) -> None:
        self.map.show_vehicles = self.show_vehicles.get()
        self.map.show_zones = self.show_zones.get()
        self.map.show_labels = self.show_labels.get()
        self.map.show_grid = self.show_grid.get()
        self.map.show_bookings = self.show_bookings.get()
        self.map.show_customers = self.show_customers.get()
        self.map.reload()

    # -- cross-page focus hooks ------------------------------------------------
    def focus_vehicle(self, vehicle_id: int) -> None:
        self.show_vehicles.set(True)
        self.pills["vehicles"].sync()
        self.apply_layers()
        self.select(vehicle_id)
        self.map.focus(vehicle_id)

    def focus_customer(self, customer_id: int) -> None:
        self.show_customers.set(True)
        self.pills["customers"].sync()
        self.apply_layers()
        customer = self.store.row("SELECT * FROM customers WHERE id = ?", (customer_id,))
        if (
            customer is not None
            and customer.get("latitude") is not None
            and customer.get("longitude") is not None
        ):
            self.map.fly_to(float(customer["longitude"]), float(customer["latitude"]), 6.0)

    def focus_point(self, lat: float, lon: float, span: float = 5.0) -> None:
        self.map.fly_to(lon, lat, span)

    def select(self, vehicle_id: int) -> None:
        vehicle = self.store.row("SELECT * FROM vehicles WHERE id = ?", (vehicle_id,))
        if not vehicle:
            return
        self.selected = vehicle
        self.listing.set_selected(int(vehicle_id))
        self.map.focus(vehicle_id)
        self.render_detail()

    def render_detail(self) -> None:
        for child in self.detail.winfo_children():
            child.destroy()
        self._detail_values: dict[str, ttk.Label] = {}
        vehicle = self.selected
        if not vehicle:
            self._render_detail_placeholder()
            return
        has_fix = vehicle["latitude"] is not None and vehicle["longitude"] is not None
        found = self.store.nearest_zone(vehicle["latitude"], vehicle["longitude"]) if has_fix else None
        live = self.app.feed.live(int(vehicle["id"])) if self.app.feed is not None else None
        lat = live.lat if live else vehicle["latitude"]
        lon = live.lon if live else vehicle["longitude"]
        if live is not None and not live.parked:
            heading_value = f"{compass_text(live.heading)} {live.heading:.0f}°"
            last_fix = "live feed"
        else:
            heading_value = "stationary"
            last_fix = str(vehicle.get("updated_at") or "—")
        head = ttk.Frame(self.detail, style="Card.TFrame")
        head.pack(fill="x")
        ttk.Label(head, text=f"{vehicle['brand']} {vehicle['model']}", style="TitleCard.TLabel").pack(anchor="w")
        plate_row = ttk.Frame(head, style="Card.TFrame")
        plate_row.pack(anchor="w", pady=(2, 8))
        ttk.Label(plate_row, text=vehicle["plate_number"], style="BodyCard.TLabel").pack(side="left")
        status = str(vehicle["status"])
        pill_style = {"available": "PillAccent", "rented": "PillInfo", "maintenance": "PillWarning"}.get(status, "PillNeutral")
        ttk.Label(plate_row, text=status.upper(), style=f"{pill_style}Card.TLabel").pack(side="left", padx=(8, 0))
        for key, label, value in (
            ("lat", "Latitude", coordinate_text(lat)),
            ("lon", "Longitude", coordinate_text(lon)),
            ("heading", "Heading", heading_value),
            ("fix", "Last fix", last_fix),
        ):
            row = ttk.Frame(self.detail, style="Card.TFrame")
            row.pack(fill="x", pady=2)
            ttk.Label(row, text=label, style="MutedCard.TLabel").pack(side="left")
            value_label = ttk.Label(row, text=value, style="BodyCard.TLabel")
            value_label.pack(side="right")
            self._detail_values[key] = value_label
        if found:
            zone, kilometres = found
            ttk.Label(self.detail, text="NEAREST ZONE", style="MicroCard.TLabel").pack(anchor="w", pady=(12, 0))
            ttk.Label(self.detail, text=zone["name"], style="TitleCard.TLabel").pack(anchor="w")
            ttk.Label(
                self.detail,
                text=f"{kilometres:.2f} km · radius {zone['radius_km']:.1f} km · {zone['risk_level']}",
                style="MutedCard.TLabel",
            ).pack(anchor="w")
        buttons = ttk.Frame(self.detail, style="Card.TFrame")
        buttons.pack(fill="x", pady=(14, 0))
        Button(
            buttons, text="New booking", style="Primary.TButton",
            command=lambda: self.app.open_new_booking(vehicle=self.selected),
        ).pack(side="left")
        Button(buttons, text="Edit unit", style="Secondary.TButton", command=self.edit_unit).pack(side="left", padx=(8, 0))
        Button(buttons, text="Fleet list", style="Secondary.TButton", command=lambda: self.app.show_page("vehicles")).pack(side="left", padx=(8, 0))

    def _render_detail_placeholder(self) -> None:
        """Quiet how-to card shown before any unit is picked."""
        ttk.Label(self.detail, text="NO UNIT SELECTED", style="MicroCard.TLabel").pack(anchor="w")
        for line in (
            "Pick a marker on the map or a row in the fleet list",
            "to see live telemetry, flood exposure and quick actions.",
        ):
            ttk.Label(self.detail, text=line, style="MutedCard.TLabel", wraplength=250, justify="left").pack(anchor="w", pady=(2, 0))
        legend = ttk.Frame(self.detail, style="Card.TFrame")
        legend.pack(fill="x", pady=(12, 0))
        for status, color in STATUS_COLORS.items():
            row = ttk.Frame(legend, style="Card.TFrame")
            row.pack(fill="x", pady=2)
            dot = tk.Canvas(row, width=8, height=8, background=PALETTE["surface"], highlightthickness=0, bd=0)
            dot.create_oval(0, 0, 8, 8, fill=color, outline="")
            dot.pack(side="left", padx=(0, 7))
            ttk.Label(row, text=status.title(), style="MutedCard.TLabel").pack(side="left")

    def _update_detail_values(self) -> None:
        """Refresh the live telemetry labels in place, without a rebuild."""
        refs = getattr(self, "_detail_values", None)
        vehicle = self.selected
        if not refs or not vehicle:
            return
        live = self.app.feed.live(int(vehicle["id"])) if self.app.feed is not None else None
        if live is not None and not live.parked:
            heading_value = f"{compass_text(live.heading)} {live.heading:.0f}°"
            last_fix = "live feed"
        else:
            heading_value = "stationary"
            last_fix = str(vehicle.get("updated_at") or "—")
        refs["lat"].configure(text=coordinate_text(live.lat if live else vehicle["latitude"]))
        refs["lon"].configure(text=coordinate_text(live.lon if live else vehicle["longitude"]))
        refs["heading"].configure(text=heading_value)
        refs["fix"].configure(text=last_fix)

    def edit_unit(self) -> None:
        """Edit the selected unit without leaving the map."""
        if not self.selected:
            return
        dialog = VehicleDialog(self, self.store, self.selected)
        self.wait_window(dialog)
        if not dialog.result:
            return
        self.refresh()
        self.app.refresh_all()

    def refresh(self) -> None:
        self.app.feed.sync()  # pick up added / edited / deleted units immediately
        if self.selected is not None and not self.store.row(
            "SELECT id FROM vehicles WHERE id = ?", (int(self.selected["id"]),)
        ):
            self.selected = None  # the selected unit was deleted elsewhere
            self.map.select(None)
        vehicles = self.store.vehicles()
        zones = self.store.zones()  # one query for the whole listing, not one per row
        wanted = self.query.get().strip().casefold() if hasattr(self, "query") else ""
        shown = [
            vehicle
            for vehicle in vehicles
            if not wanted
            or wanted
            in f"{vehicle['plate_number']} {vehicle['brand']} {vehicle['model']} {vehicle['category']} {vehicle['status']}".casefold()
        ]
        selected_id = int(self.selected["id"]) if self.selected else None
        rows = []
        for vehicle in shown:
            found = self.store.closest_zone(zones, vehicle["latitude"], vehicle["longitude"])
            unit = self.app.feed.live(int(vehicle["id"])) if self.app.feed is not None else None
            if vehicle["latitude"] is None or vehicle["longitude"] is None:
                state = "no fix"
            elif unit is not None and not unit.parked:
                state = "moving"
            else:
                state = "parked"
            rows.append(
                {
                    "id": int(vehicle["id"]),
                    "plate": str(vehicle["plate_number"]),
                    "model": f"{vehicle['brand']} {vehicle['model']}",
                    "status": str(vehicle["status"]),
                    "state": state,
                    "right": f"{found[1]:.1f} km" if found else "",
                }
            )
        self.listing.set_rows(rows, selected_id=selected_id)
        self.list_count.configure(text=f"{len(shown)} of {len(vehicles)}")
        # Only re-read the map snapshot when the underlying data changed; a
        # keystroke in the search box then costs a cheap dynamic repaint only.
        fingerprint = (
            tuple((v["id"], v["status"], v["plate_number"], v["latitude"], v["longitude"]) for v in vehicles),
            tuple((z["id"], z["is_active"], z["radius_km"], z["risk_level"]) for z in zones),
        )
        if fingerprint != getattr(self, "_data_fingerprint", None):
            self._data_fingerprint = fingerprint
            self.map.reload()
        else:
            self.map.draw()
        if self.selected:
            self.render_detail()


class FloodZonesPage(Page):
    key = "zones"
    title = "Flood zones"
    subtitle = "Monitored areas, severity scores and the units exposed to each"

    def build(self) -> None:
        heading(self, self.title, self.subtitle, [Button(self, text="Add zone", style="Primary.TButton", command=self.add_zone)])
        _wrap, pair = grid_row(self, [lambda master: ScrollColumn(master, height=520), lambda master: Card(master)], weights=[13, 11], gap=14)
        _wrap.pack_configure(expand=True)
        self.column, map_card = pair
        card_title(map_card, "Zone map", "Ring size reflects the monitored radius")
        self.map = MapCanvas(
            map_card.body, self.store, height=330, on_select=None, show_grid=False, legend=False,
            border=False, feed=self.app.feed, detail=self.app.store.settings().get("map_detail", "medium"),
        )
        self.map.pack(fill="x", pady=(12, 0))
        scale_card = Card(map_card.body)
        scale_card.pack(fill="x", pady=(12, 0))
        card_title(scale_card, "Severity scale", "Scores assigned during each risk scan")
        rows = ttk.Frame(scale_card.body, style="Card.TFrame")
        rows.pack(fill="x", pady=(10, 0))
        for level in RISK_LEVELS:
            row = ttk.Frame(rows, style="Card.TFrame")
            row.pack(fill="x", pady=4)
            swatch = tk.Canvas(row, width=9, height=9, background=PALETTE["surface"], highlightthickness=0, bd=0)
            swatch.create_oval(0, 0, 9, 9, fill=RISK_COLORS[level], outline="")
            swatch.pack(side="left", padx=(0, 8))
            ttk.Label(row, text=f"{level.title()} risk", style="BodyCard.TLabel", width=14, anchor="w").pack(side="left")
            meter = Bar(row, color=RISK_COLORS[level])
            meter.pack(side="left", fill="x", expand=True, padx=(6, 8))
            meter.set(RISK_SCORES[level] / 100)
            ttk.Label(row, text=str(RISK_SCORES[level]), style="MutedCard.TLabel", width=4, anchor="e").pack(side="right")
        self.refresh()

    def add_zone(self) -> None:
        dialog = ZoneDialog(self, self.store)
        self.wait_window(dialog)
        if not dialog.result:
            return
        self.refresh()
        self.app.refresh_all()

    def edit_zone(self, zone_id: int) -> None:
        zone = self.store.row("SELECT * FROM flood_zones WHERE id = ?", (zone_id,))
        if zone is None:
            return
        dialog = ZoneDialog(self, self.store, zone)
        self.wait_window(dialog)
        if not dialog.result:
            return
        self.refresh()
        self.app.refresh_all()

    def delete_zone(self, zone_id: int, name: str) -> None:
        if not confirm_delete(self, f"flood zone '{name}'"):
            return
        try:
            self.store.delete_zone(zone_id)
        except (ValueError, RuntimeError) as error:
            handle_store_error(self, error)
            return
        self.refresh()
        self.app.refresh_all()

    def refresh(self) -> None:
        for child in self.column.inner.winfo_children():
            child.destroy()
        exposure = self.store.exposure()
        for zone in self.store.zones():
            card = Card(self.column.inner, padding=(16, 14))
            card.pack(fill="x", pady=(0, 10))
            head = ttk.Frame(card.body, style="Card.TFrame")
            head.pack(fill="x")
            text = ttk.Frame(head, style="Card.TFrame")
            text.pack(side="left", fill="x", expand=True)
            ttk.Label(text, text=zone["name"], style="TitleCard.TLabel").pack(anchor="w")
            ttk.Label(text, text=zone["barangay"] or "", style="MutedCard.TLabel").pack(anchor="w", pady=(2, 0))
            ttk.Label(head, text=zone["risk_level"].upper(), style=f"Pill{zone['risk_level'].capitalize()}Card.TLabel").pack(side="right")

            facts = ttk.Frame(card.body, style="Card.TFrame")
            facts.pack(fill="x", pady=(12, 0))
            exposed = sum(1 for item in exposure if item["zone_name"] == zone["name"] and item["inside"])
            for index, value in enumerate((f"{RISK_SCORES[zone['risk_level']]}", f"{zone['radius_km']:.1f} km", str(exposed))):
                box = fact(facts, ("Score", "Radius", "Units inside")[index], value)
                box.grid(row=0, column=index, sticky="nsew", padx=(0 if index == 0 else 8, 0))
            for column in range(3):
                facts.columnconfigure(column, weight=1)

            meter = Bar(card.body, color=RISK_COLORS[zone["risk_level"]])
            meter.pack(fill="x", pady=(12, 0))
            meter.set(RISK_SCORES[zone["risk_level"]] / 100)

            if zone["notes"]:
                ttk.Label(card.body, text=zone["notes"], style="MutedCard.TLabel", wraplength=300, justify="left").pack(anchor="w", pady=(10, 0))
            footer = ttk.Frame(card.body, style="Card.TFrame")
            footer.pack(fill="x", pady=(12, 0))
            variable = tk.BooleanVar(value=bool(zone["is_active"]))
            ttk.Checkbutton(
                footer,
                text="Active in risk scans",
                variable=variable,
                style="Switch.TCheckbutton",
                command=lambda zone_id=zone["id"], flag=variable: self.toggle(zone_id, flag.get()),
            ).pack(side="left")
            actions = ttk.Frame(footer, style="Card.TFrame")
            actions.pack(side="right")
            ttk.Label(
                actions,
                text=f"{zone['latitude']:.3f}, {zone['longitude']:.3f}  ",
                style="MicroCard.TLabel",
            ).pack(side="left")
            Button(
                actions, text="Edit", style="Secondary.TButton",
                command=lambda zone_id=zone["id"]: self.edit_zone(zone_id),
            ).pack(side="left")
            Button(
                actions, text="Delete", style="Ghost.TButton",
                command=lambda zone_id=zone["id"], zone_name=zone["name"]: self.delete_zone(zone_id, zone_name),
            ).pack(side="left", padx=(6, 0))
        self.map.reload()

    def toggle(self, zone_id: int, active: bool) -> None:
        self.store.set_zone_active(zone_id, active)
        self.refresh()
        self.app.refresh_all()


class AlertsPage(Page):
    key = "alerts"
    title = "Alerts"
    subtitle = "Notices raised by the flood scan, by staff and by maintenance checks"

    def build(self) -> None:
        heading(
            self,
            self.title,
            self.subtitle,
            [Button(self, text="Run flood risk scan", style="Primary.TButton", command=self.scan)],
        )
        wrap = ttk.Frame(self, style="Page.TFrame")
        wrap.pack(fill="x", pady=(0, 12))
        self.tiles = [
            Stat(wrap, "Unread", tone="accent", glyph="◉"),
            Stat(wrap, "Acknowledged", tone="warn", glyph="◐"),
            Stat(wrap, "Resolved", tone="ok", glyph="✓"),
            Stat(wrap, "Critical open", tone="danger", glyph="⚑"),
        ]
        for index, tile in enumerate(self.tiles):
            wrap.columnconfigure(index, weight=1, uniform="alerts")
            tile.grid(row=0, column=index, sticky="nsew", padx=(0 if index == 0 else 10, 0))
        bar = ttk.Frame(self, style="Page.TFrame")
        bar.pack(fill="x", pady=(0, 12))
        self.filter = tk.StringVar(value="all")
        box = ttk.Combobox(bar, textvariable=self.filter, values=["all", *ALERT_STATUSES], width=18, state="readonly", style="Field.TCombobox")
        box.pack(side="left")
        box.bind("<<ComboboxSelected>>", lambda _event: self.refresh())
        self.counter = ttk.Label(bar, text="", style="Muted.TLabel")
        self.counter.pack(side="right")
        self.column = ScrollColumn(self, height=430)
        self.column.pack(fill="both", expand=True)
        self.refresh()

    def scan(self) -> None:
        created = self.store.run_flood_scan(self.app.user["username"])
        self.refresh()
        self.app.refresh_all()
        if created:
            critical_now = int(self.store.value(
                "SELECT COUNT(*) FROM alerts WHERE status = 'new' AND severity = 'critical'"
            ) or 0)
            if self.app.store.settings().get("sound_alerts", "1") == "1" and critical_now:
                try:
                    self.winfo_toplevel().bell()
                except tk.TclError:
                    pass
            messagebox.showinfo(APP_NAME, f"{len(created)} new alert(s) raised.", parent=self)
        else:
            messagebox.showinfo(APP_NAME, "No vehicle currently sits inside an active flood zone.", parent=self)

    def refresh(self) -> None:
        alerts = self.store.alerts(self.filter.get())
        for child in self.column.inner.winfo_children():
            child.destroy()
        for alert in alerts:
            card = Card(self.column.inner, padding=(16, 13))
            card.pack(fill="x", pady=(0, 9))
            head = ttk.Frame(card.body, style="Card.TFrame")
            head.pack(fill="x")
            ttk.Label(head, text=alert["title"], style="TitleCard.TLabel").pack(side="left")
            ttk.Label(head, text=alert["severity"].upper(), style=f"Pill{alert['severity'].capitalize()}Card.TLabel").pack(side="right")
            ttk.Label(card.body, text=alert["message"], style="MutedCard.TLabel", wraplength=430, justify="left").pack(anchor="w", pady=(6, 0))
            meta = ttk.Frame(card.body, style="Card.TFrame")
            meta.pack(fill="x", pady=(10, 0))
            ttk.Label(
                meta,
                text=f"{alert['created_at']}  ·  source {alert['source']}  ·  {alert['status']}",
                style="MicroCard.TLabel",
            ).pack(side="left")
            buttons = ttk.Frame(meta, style="Card.TFrame")
            buttons.pack(side="right")
            if alert["status"] != "resolved":
                if alert["status"] == "new":
                    Button(
                        buttons, text="Acknowledge", style="Secondary.TButton",
                        command=lambda alert_id=alert["id"]: self.set_status(alert_id, "acknowledged"),
                    ).pack(side="left", padx=(6, 0))
                Button(
                    buttons, text="Resolve", style="Quiet.TButton",
                    command=lambda alert_id=alert["id"]: self.set_status(alert_id, "resolved"),
                ).pack(side="left", padx=(6, 0))
        counts = self.store.open_alert_counts()
        critical = int(self.store.value(
            "SELECT COUNT(*) FROM alerts WHERE severity = 'critical' AND status != 'resolved'"
        ) or 0)
        self.tiles[0].set(str(counts["new"]).zfill(2), "Waiting for a response")
        self.tiles[1].set(str(counts["acknowledged"]).zfill(2), "Seen by staff")
        self.tiles[2].set(str(counts["resolved"]).zfill(2), "Closed")
        self.tiles[3].set(str(critical).zfill(2), "Needs attention now")
        self.counter.configure(text=f"{len(alerts)} notices")

    def set_status(self, alert_id: int, status: str) -> None:
        self.store.set_alert_status(alert_id, status)
        self.refresh()
        self.app.refresh_all()


class ReportsPage(Page):
    key = "reports"
    title = "Reports"
    subtitle = "Every ledger can be exported to CSV into your local exports folder"

    def build(self) -> None:
        heading(self, self.title, self.subtitle)
        grid = ttk.Frame(self, style="Page.TFrame")
        grid.pack(fill="x", pady=(0, 12))
        for index, key in enumerate(self.store.REPORTS):
            title, description = self.store.REPORTS[key]
            columns, rows = self.store.report(key)
            card = Card(grid, padding=(16, 14))
            card.grid(row=index // 3, column=index % 3, sticky="nsew", padx=(0 if index % 3 == 0 else 10), pady=(0 if index < 3 else 10))
            ttk.Label(card.body, text=title, style="TitleCard.TLabel").pack(anchor="w")
            ttk.Label(card.body, text=f"{len(rows)} rows", style="MicroCard.TLabel").pack(anchor="w", pady=(2, 0))
            ttk.Label(card.body, text=description, style="MutedCard.TLabel", wraplength=220, justify="left").pack(anchor="w", pady=(8, 0))
            Button(
                card.body, text="Export CSV", style="Secondary.TButton",
                command=lambda k=key: export_csv(self, k, *self.store.report(k)),
            ).pack(anchor="w", pady=(12, 0))
        for column in range(3):
            grid.columnconfigure(column, weight=1, uniform="reports")
        preview = Card(self)
        preview.pack(fill="both", expand=True)
        card_title(preview, "Preview", "Rows that will be written, before any file is created")
        self.table = Table(preview.body, [("0", "Column 1", 160, "w"), ("1", "Column 2", 200, "w"), ("2", "Column 3", 200, "w")])
        self.table.pack(fill="both", expand=True)
        self.refresh()

    def refresh(self) -> None:
        columns, rows = self.store.report("bookings")
        keys = [f"col{index}" for index in range(len(columns))]
        self.table.tree.configure(columns=keys)
        for index, name in enumerate(columns):
            self.table.tree.heading(keys[index], text=name)
            self.table.tree.column(keys[index], width=120, anchor="w")
        self.table.keys = keys
        self.table.set_rows(
            [{**{key: "" for key in keys}, **{keys[index]: str(value) for index, value in enumerate(row)}} for row in rows[:8]]
        )


class SettingsPage(Page):
    key = "settings"
    title = "Settings"
    subtitle = "Organisation details, defaults and the local data folder used by the app"

    FIELDS = (
        ("organisation", "Organisation", None),
        ("contact_number", "Contact number", None),
        ("currency", "Currency", ["PHP", "USD", "SGD", "JPY"]),
        ("date_format", "Date format", [DATE_FORMAT, "%d/%m/%Y", "%m/%d/%Y"]),
        ("alert_threshold", "Minimum severity to alert", ALERT_SEVERITIES),
        ("zone_buffer_km", "Zone buffer", ["0.0", "0.5", "1.0", "2.0"]),
        ("map_detail", "Map detail", ["low", "medium", "high"]),
        ("map_zoom", "Map zoom", ["10", "11", "12", "13", "14"]),
    )
    SWITCHES = (
        ("sound_alerts", "Play a sound for critical alerts"),
        ("auto_scan", "Run the flood scan automatically every 15 minutes"),
        ("confirm_exit", "Ask before closing the application"),
    )

    def build(self) -> None:
        self.values: dict[str, tk.Variable] = {}
        self.status = tk.StringVar(value="")
        heading(
            self,
            self.title,
            self.subtitle,
            [
                Button(self, text="Backup now", style="Secondary.TButton", command=self.backup),
                Button(self, text="Save changes", style="Primary.TButton", command=self.save),
            ],
        )
        _wrap, pair = grid_row(self, [lambda master: Card(master), lambda master: Card(master)], weights=[13, 10], gap=14)
        form_card, side_card = pair

        card_title(form_card, "Organisation", "Shown in the window title and the status bar")
        form = ttk.Frame(form_card.body, style="Card.TFrame")
        form.pack(fill="x", pady=(14, 0))
        settings = self.store.settings()
        for index, (key, label, choices) in enumerate(self.FIELDS):
            widget = Field(form, label, settings.get(key, ""), choices=choices, width=24)
            widget.grid(row=index // 2, column=index % 2, sticky="nsew", padx=(0, 12), pady=(0, 10))
            self.values[key] = widget.variable
        form.columnconfigure(0, weight=1)
        form.columnconfigure(1, weight=1)

        ttk.Label(form_card.body, text="BEHAVIOUR", style="MicroCard.TLabel").pack(anchor="w", pady=(14, 4))
        for key, label in self.SWITCHES:
            variable = tk.BooleanVar(value=settings.get(key, "1") == "1")
            self.values[key] = variable
            ttk.Checkbutton(form_card.body, text=label, variable=variable, style="Switch.TCheckbutton").pack(anchor="w", pady=3)
        ttk.Label(form_card.body, textvariable=self.status, style="AccentCard.TLabel").pack(anchor="w", pady=(10, 0))

        card_title(side_card, "Local storage", "Everything the application writes stays on this machine")
        paths = ttk.Frame(side_card.body, style="Card.TFrame")
        paths.pack(fill="x", pady=(14, 0))
        for label, value in (
            ("Data folder", str(DATA_ROOT)),
            ("Database", str(DATABASE_FILE)),
            ("Exports", str(EXPORT_DIR)),
            ("Log file", str(LOG_FILE)),
        ):
            row = ttk.Frame(paths, style="Sunken.TFrame", padding=(10, 8))
            row.pack(fill="x", pady=3)
            ttk.Label(row, text=label.upper(), style="MicroSunken.TLabel").pack(anchor="w")
            ttk.Label(row, text=value, style="BodySunken.TLabel", wraplength=260, justify="left").pack(anchor="w")

        about = Card(side_card)
        about.pack(fill="x", pady=(12, 0))
        card_title(about, "About", "Build information")
        for label, value in (
            ("Application", APP_NAME),
            ("Version", APP_VERSION),
            ("Interface", "Tkinter / ttk"),
            ("Database", "SQLite 3 (single local file)"),
            ("Map data", "OpenStreetMap contributors"),
            ("Python", f"{sys.version.split()[0]}"),
        ):
            row = ttk.Frame(about.body, style="Card.TFrame")
            row.pack(fill="x", pady=2)
            ttk.Label(row, text=label, style="MutedCard.TLabel").pack(side="left")
            ttk.Label(row, text=value, style="BodyCard.TLabel").pack(side="right")
        self.refresh()

    def refresh(self) -> None:
        settings = self.store.settings()
        for key, variable in self.values.items():
            if isinstance(variable, tk.BooleanVar):
                variable.set(settings.get(key, "1") == "1")
            else:
                variable.set(settings.get(key, ""))

    def save(self) -> None:
        for key, variable in self.values.items():
            if isinstance(variable, tk.BooleanVar):
                value = "1" if variable.get() else "0"
            else:
                value = str(variable.get()).strip()
            self.store.set_setting(key, value)
        self.status.set("Settings saved.")
        self.app.refresh_all()
        self.after(2600, lambda: self.status.set(""))

    def backup(self) -> None:
        """Same flow as the File menu — one implementation, two entry points."""
        self.app._backup()


NAV_PAGES: list[tuple[str, str, str, type[Page]]] = [
    ("dashboard", "Dashboard", "◉", DashboardPage),
    ("vehicles", "Vehicles", "▤", VehiclesPage),
    ("customers", "Customers", "☰", CustomersPage),
    ("bookings", "Bookings", "▦", BookingsPage),
    ("transactions", "Transactions", "₱", TransactionsPage),
    ("gps", "GPS map", "⌖", GpsMapPage),
    ("zones", "Flood zones", "◈", FloodZonesPage),
    ("alerts", "Alerts", "⚑", AlertsPage),
    ("reports", "Reports", "≣", ReportsPage),
    ("users", "Users", "◆", UsersPage),
    ("settings", "Settings", "⚙", SettingsPage),
]
PAGE_BY_KEY = {entry[0]: entry[3] for entry in NAV_PAGES}
LABEL_BY_KEY = {entry[0]: entry[1] for entry in NAV_PAGES}

NAV_GROUPS: list[tuple[str, tuple[str, ...]]] = [
    ("Operations", ("dashboard", "vehicles", "customers", "bookings", "transactions")),
    ("Fleet and map", ("gps", "zones", "alerts")),
    ("Administration", ("reports", "users", "settings")),
]


# ---------------------------------------------------------------------------
# Windows
# ---------------------------------------------------------------------------


class PasswordEntry(ttk.Frame):
    """Entry with an in-field eye toggle for showing or hiding the password.

    The eye glyph sits inside the field's right padding (38 px reserved by the
    ``PasswordField.TEntry`` style) so it reads as a native affordance rather
    than a separate button row. ttk does not expose the entry interior, so the
    toggle is a small canvas placed over the field's right edge with ``place``.
    """

    def __init__(self, master: tk.Widget, textvariable: tk.StringVar, **kwargs: Any) -> None:
        super().__init__(master, style="Card.TFrame")
        self._shown = False
        kwargs.setdefault("style", "PasswordField.TEntry")
        kwargs.setdefault("show", "•")
        self.entry = ttk.Entry(self, textvariable=textvariable, **kwargs)
        self.entry.pack(fill="x", expand=True)
        self.eye = tk.Canvas(
            self, width=24, height=24,
            background=PALETTE["surface"], highlightthickness=0, bd=0, cursor="hand2",
        )
        self.eye.place(relx=1.0, rely=0.5, anchor="e", x=-8)
        self.eye.bind("<Button-1>", lambda _event: self.toggle())
        self.eye.bind("<Enter>", lambda _event: self._draw_eye(hover=True))
        self.eye.bind("<Leave>", lambda _event: self._draw_eye(hover=False))
        self._draw_eye(hover=False)

    def toggle(self) -> None:
        self._shown = not self._shown
        self.entry.configure(show="" if self._shown else "•")
        self._draw_eye()

    def focus_set(self) -> None:
        self.entry.focus_set()

    def _draw_eye(self, hover: bool = False) -> None:
        self.eye.delete("all")
        if self._shown:
            base = PALETTE["accent"]
            pupil = PALETTE["accent_hover"]
        else:
            base = PALETTE["ink_soft"] if hover else PALETTE["muted"]
            pupil = PALETTE["ink_soft"] if hover else PALETTE["muted"]
        cx, cy = 12, 12
        # almond eye outline
        self.eye.create_oval(cx - 7, cy - 4, cx + 7, cy + 4, outline=base, width=1.5)
        # pupil
        self.eye.create_oval(cx - 2.4, cy - 2.4, cx + 2.4, cy + 2.4, fill=pupil, outline="")
        if not self._shown:
            # subtle slash — this eye is closed
            self.eye.create_line(cx - 7, cy - 4, cx + 7, cy + 4, fill=PALETTE["line"], width=1.4)


class LoginWindow(tk.Toplevel):
    """Split sign-in window — refined brand panel on the left, form on the right.

    A tighter 760×500 split hero: a deep evergreen panel on the left carries the
    brand mark, a concentric-ring motif and a compact three-feature stack; a
    white form on the right uses an in-field password eye toggle so the whole
    sign-in card stays compact and uncluttered.
    """

    WINDOW_W = 760
    WINDOW_H = 500
    PANEL_W = 320
    FEATURES = (
        ("⌖", "Live GPS tracking", "Every unit streams its position along the road network."),
        ("◈", "Flood-zone exposure", "Instant alerts the moment a unit drifts near a risk area."),
        ("▦", "Offline-first records", "SQLite storage with CSV export — no internet required."),
    )

    def __init__(self, master: tk.Tk, store: Store) -> None:
        super().__init__(master)
        self.store = store
        self.user: dict[str, Any] | None = None
        self.title(f"{APP_NAME} — Sign in")
        self.configure(background=PALETTE["surface"])
        self.resizable(False, False)

        shell = ttk.Frame(self, style="CardBorder.TFrame", padding=1)
        shell.pack(fill="both", expand=True)
        content = ttk.Frame(shell, style="Card.TFrame")
        content.pack(fill="both", expand=True)

        self._build_brand_panel(content)
        self._build_form(content)

        self.bind("<Return>", lambda _event: self.sign_in())
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.geometry(f"{self.WINDOW_W}x{self.WINDOW_H}")
        self._centre()

    # -- left panel ---------------------------------------------------------
    def _build_brand_panel(self, parent: tk.Widget) -> None:
        panel = tk.Canvas(
            parent, width=self.PANEL_W, height=self.WINDOW_H,
            background=PALETTE["sidebar_deep"], highlightthickness=0, bd=0,
        )
        panel.pack(side="left", fill="y")
        panel.pack_propagate(False)
        p = PALETTE
        # quiet concentric rings anchored to the upper-right corner — a
        # subtle motif that fades into the dark panel instead of dominating it
        anchor_x = self.PANEL_W - 60
        anchor_y = 88
        for radius in (54, 92, 132, 176):
            panel.create_oval(
                anchor_x - radius, anchor_y - radius, anchor_x + radius, anchor_y + radius,
                outline=p["sidebar_line"], width=1,
            )
        # a quiet accent halo behind the brand mark
        panel.create_oval(
            anchor_x - 28, anchor_y - 28, anchor_x + 28, anchor_y + 28,
            outline=_mix(p["sidebar_active"], p["sidebar_deep"], 0.35), width=1.4,
        )
        # brand chip
        round_rect(panel, 30, 56, 70, 96, radius=12, fill=p["sidebar_active"], outline="")
        panel.create_text(50, 76, text="◈", font=FONTS["h2"], fill="#FFFFFF")
        panel.create_text(30, 126, text="Flood Ready", font=FONTS["display"], fill=p["sidebar_ink"], anchor="w")
        panel.create_text(30, 156, text="Vehicle System", font=FONTS["display"], fill=p["sidebar_ink"], anchor="w")
        panel.create_text(
            30, 196, text="Rental operations with flood-risk monitoring for Metro Manila.",
            font=FONTS["small"], fill=p["sidebar_muted"], anchor="w", width=252, justify="left",
        )
        # feature stack — tighter rows with a hairline above each entry
        y = 258
        for index, (glyph, title, description) in enumerate(self.FEATURES):
            if index:
                panel.create_line(30, y - 12, self.PANEL_W - 30, y - 12, fill=p["sidebar_line"], width=1)
            round_rect(panel, 30, y, 54, y + 24, radius=7, fill=p["sidebar_hover"], outline="")
            panel.create_text(42, y + 12, text=glyph, font=FONTS["small_bold"], fill="#7FD3AB")
            panel.create_text(64, y + 4, text=title, font=FONTS["small_bold"], fill=p["sidebar_ink"], anchor="w")
            panel.create_text(
                64, y + 20, text=description, font=FONTS["micro"], fill=p["sidebar_muted"],
                anchor="w", width=222, justify="left",
            )
            y += 56
        panel.create_text(
            30, self.WINDOW_H - 28, text=f"v{APP_VERSION}  ·  Tkinter + SQLite  ·  Offline-first",
            font=FONTS["micro"], fill=p["sidebar_muted"], anchor="w",
        )

    # -- right panel ----------------------------------------------------------
    def _build_form(self, parent: tk.Widget) -> None:
        panel = ttk.Frame(parent, style="Card.TFrame", padding=(36, 8))
        panel.pack(side="left", fill="both", expand=True)
        # shrink-wrapped column, top-centred — pack keeps it centred without
        # pinning a fixed height, so the fields always size to their content
        column = ttk.Frame(panel, style="Card.TFrame")
        column.pack(anchor="n", pady=(32, 0))

        ttk.Label(column, text="WELCOME BACK", style="AccentCard.TLabel").pack(anchor="w")
        tk.Label(
            column, text="Sign in", font=FONTS["title"],
            fg=PALETTE["ink"], background=PALETTE["surface"],
        ).pack(anchor="w", pady=(5, 0))
        ttk.Label(
            column,
            text="Use your staff account to open the operations dashboard.",
            style="MutedCard.TLabel", wraplength=320, justify="left",
        ).pack(anchor="w", pady=(5, 0))

        self.username = tk.StringVar(master=self, value=DEFAULT_ADMIN_USERNAME)
        self.password = tk.StringVar(master=self, value=DEFAULT_ADMIN_PASSWORD)
        self.error = tk.StringVar(master=self, value="")

        ttk.Label(column, text="USERNAME", style="MicroCard.TLabel").pack(anchor="w", pady=(24, 0))
        username_entry = ttk.Entry(column, textvariable=self.username, width=32, style="Field.TEntry")
        username_entry.pack(fill="x", pady=(5, 0))

        ttk.Label(column, text="PASSWORD", style="MicroCard.TLabel").pack(anchor="w", pady=(15, 0))
        self.password_entry = PasswordEntry(column, self.password, width=32)
        self.password_entry.pack(fill="x", pady=(5, 0))

        ttk.Label(
            column, textvariable=self.error, style="DangerCard.TLabel", wraplength=320, justify="left"
        ).pack(anchor="w", pady=(12, 0))
        Button(column, text="Sign in", style="Hero.TButton", command=self.sign_in).pack(fill="x", pady=(8, 0))

        ttk.Frame(column, style="CardBorder.TFrame", height=1).pack(fill="x", pady=(22, 0))
        ttk.Label(
            column,
            text=f"Demo account · {DEFAULT_ADMIN_USERNAME} / {DEFAULT_ADMIN_PASSWORD}",
            style="MicroCard.TLabel", justify="left",
        ).pack(anchor="w", pady=(12, 0))
        # truncate DATA_ROOT visually so a long path doesn't blow out the form
        root_text = str(DATA_ROOT)
        if len(root_text) > 48:
            root_text = "…" + root_text[-47:]
        ttk.Label(column, text=f"Local data: {root_text}", style="MicroCard.TLabel", justify="left").pack(anchor="w")

        username_entry.focus_set()

    def sign_in(self) -> None:
        try:
            self.user = self.store.login(self.username.get(), self.password.get())
        except ValueError as error:
            self.error.set(str(error))
            self.password.set("")
            return
        except RuntimeError as error:
            self.error.set(str(error))
            return
        logging.getLogger(__name__).info("Signed in as %s", self.user["username"])
        self.destroy()

    def close(self) -> None:
        self.user = None
        self.destroy()

    def _centre(self) -> None:
        self.update_idletasks()
        width, height = max(self.WINDOW_W, self.winfo_reqwidth()), max(self.WINDOW_H, self.winfo_reqheight())
        x = max(0, (self.winfo_screenwidth() - width) // 2)
        y = max(0, (self.winfo_screenheight() - height) // 3)
        self.geometry(f"{width}x{height}+{x}+{y}")


class MainWindow(ttk.Frame):
    """Sidebar shell with a menu bar, status bar and one page at a time."""

    def __init__(self, master: tk.Tk, store: Store, user: dict[str, Any]) -> None:
        super().__init__(master, style="Page.TFrame")
        self.store = store
        self.user = user
        self.pages: dict[str, Page] = {}
        self.current: str = ""
        self.buttons: dict[str, Button] = {}
        self.sign_out = False
        self._closing = threading.Event()
        self._online: bool | None = None

        master.title(f"{APP_NAME} — {user['full_name']}")
        master.geometry("1280x800")
        master.minsize(1080, 680)
        master.protocol("WM_DELETE_WINDOW", self.close)
        self.feed = TrackingFeed(store, master)
        self._build_menu(master)
        self._build_status_bar()
        self._build_sidebar()

        self.container = ttk.Frame(self, style="Page.TFrame")
        self.container.pack(side="left", fill="both", expand=True)
        self.show_page("dashboard")
        self.pack(fill="both", expand=True)
        # Give the window one paint cycle before the feed kicks in — startup
        # reads as instant instead of a brief freeze while routes are built.
        self.after(350, self._start_feed)
        self._start_connectivity_check()
        self._start_auto_scan()

    def _start_feed(self) -> None:
        try:
            self.feed.start()
        except tk.TclError:  # window closed before the feed could start
            pass

    # -- chrome -----------------------------------------------------------
    def _build_menu(self, master: tk.Tk) -> None:
        menubar = tk.Menu(
            master,
            activebackground=PALETTE["accent_soft"],
            activeforeground=PALETTE["ink"],
            activeborderwidth=0,
            background=PALETTE["surface"],
            foreground=PALETTE["ink_soft"],
            font=FONTS["nav"],
            bd=0,
            relief="flat",
        )
        file_menu = tk.Menu(
            menubar, tearoff=0,
            activebackground=PALETTE["accent_soft"], activeforeground=PALETTE["ink"],
            activeborderwidth=0,
            background=PALETTE["surface"], foreground=PALETTE["ink_soft"],
            font=FONTS["nav"], bd=0, relief="flat",
        )
        file_menu.add_command(label="Backup database…", command=self._backup)
        file_menu.add_separator()
        file_menu.add_command(label="Sign out", command=self._sign_out)
        file_menu.add_command(label="Exit", command=self.close)
        menubar.add_cascade(label="File", menu=file_menu)
        help_menu = tk.Menu(
            menubar, tearoff=0,
            activebackground=PALETTE["accent_soft"], activeforeground=PALETTE["ink"],
            activeborderwidth=0,
            background=PALETTE["surface"], foreground=PALETTE["ink_soft"],
            font=FONTS["nav"], bd=0, relief="flat",
        )
        help_menu.add_command(label=f"About {APP_NAME}", command=self._about)
        menubar.add_cascade(label="Help", menu=help_menu)
        master.configure(menu=menubar)

    def _build_sidebar(self) -> None:
        sidebar = ttk.Frame(self, style="Sidebar.TFrame", width=242)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        brand = ttk.Frame(sidebar, style="Sidebar.TFrame", padding=(20, 22))
        brand.pack(fill="x")
        head = ttk.Frame(brand, style="Sidebar.TFrame")
        head.pack(fill="x")
        mark = tk.Canvas(head, width=40, height=40, background=PALETTE["sidebar"], highlightthickness=0, bd=0)
        mark.pack(side="left")
        round_rect(mark, 1, 1, 39, 39, radius=12, fill=PALETTE["sidebar_active"], outline="")
        mark.create_text(20, 21, text="◈", font=FONTS["h2"], fill="#FFFFFF")
        name = ttk.Frame(head, style="Sidebar.TFrame")
        name.pack(side="left", padx=(12, 0))
        ttk.Label(name, text="Flood Ready", style="BrandSidebar.TLabel").pack(anchor="w")
        ttk.Label(name, text="Vehicle System", style="BrandSidebar.TLabel").pack(anchor="w")
        ttk.Label(brand, text=f"FLEET OPERATIONS · v{APP_VERSION}", style="MicroSidebar.TLabel").pack(anchor="w", pady=(9, 0))

        nav = ttk.Frame(sidebar, style="Sidebar.TFrame")
        nav.pack(fill="both", expand=True, pady=(12, 0))
        for group_index, (group, keys) in enumerate(NAV_GROUPS):
            if group_index:
                ttk.Frame(nav, style="SidebarBorder.TFrame", height=1).pack(fill="x", padx=20, pady=(12, 4))
            ttk.Label(nav, text=group.upper(), style="GroupSidebar.TLabel").pack(fill="x", padx=(20, 0), pady=(6, 6))
            for key in keys:
                if key == "users" and self.user["role"] != "admin":
                    continue
                entry = next(item for item in NAV_PAGES if item[0] == key)
                _key, label, icon, _page = entry
                button = Button(
                    nav,
                    text=f"{icon}   {label}",
                    style="Sidebar.TButton",
                    command=lambda bound=key: self.show_page(bound),
                )
                button.pack(fill="x", padx=12, pady=2)
                self.buttons[key] = button

        user_card = ttk.Frame(sidebar, style="SidebarBorder.TFrame", padding=1)
        user_card.pack(side="bottom", fill="x", padx=14, pady=14)
        inner = ttk.Frame(user_card, style="SidebarCard.TFrame", padding=(12, 12))
        inner.pack(fill="both", expand=True)
        identity = ttk.Frame(inner, style="SidebarCard.TFrame")
        identity.pack(fill="x")
        avatar = tk.Canvas(identity, width=36, height=36, background=PALETTE["sidebar_hover"], highlightthickness=0, bd=0)
        avatar.pack(side="left")
        initials = "".join(part[0] for part in str(self.user["full_name"]).split()[:2]).upper() or "?"
        avatar.create_oval(1, 1, 35, 35, fill=PALETTE["sidebar_active"], outline="")
        avatar.create_text(18, 19, text=initials, font=FONTS["micro_bold"], fill="#FFFFFF")
        who = ttk.Frame(identity, style="SidebarCard.TFrame")
        who.pack(side="left", padx=(10, 0))
        ttk.Label(who, text=self.user["full_name"], style="TitleSidebarCard.TLabel").pack(anchor="w")
        ttk.Label(who, text=self.user["role"].title(), style="MutedSidebarCard.TLabel").pack(anchor="w")
        Button(inner, text="Sign out", style="SidebarGhost.TButton", command=self._sign_out).pack(fill="x", pady=(11, 0))

        ttk.Frame(self, style="CardBorder.TFrame", width=1).pack(side="left", fill="y")

    def _build_status_bar(self) -> None:
        bar = ttk.Frame(self, style="Bar.TFrame", padding=(16, 7))
        bar.pack(side="bottom", fill="x")
        ttk.Frame(self, style="CardBorder.TFrame", height=1).pack(side="bottom", fill="x")
        # connectivity dot — small ring instead of a flat disc, so it reads
        # as a status indicator rather than a stray pixel
        self.dot = tk.Canvas(bar, width=12, height=12, background=PALETTE["surface"], highlightthickness=0, bd=0)
        self.dot.pack(side="left", pady=2)
        self.status = ttk.Label(bar, text="Checking internet connection…", style="MutedBar.TLabel")
        self.status.pack(side="left", padx=(8, 0))
        # hairline separator before the organisation chunk
        sep = ttk.Frame(bar, style="Bar.TFrame", width=1)
        sep.pack(side="left", padx=(14, 0), pady=4, fill="y")
        # paint the hairline via a small overlay canvas since ttk.Frame won't
        # draw a single-pixel vertical line on a Bar.TFrame background cleanly
        sep_canvas = tk.Canvas(bar, width=1, height=14, background=PALETTE["surface"], highlightthickness=0, bd=0)
        sep_canvas.create_line(0, 0, 0, 14, fill=PALETTE["line"], width=1)
        sep_canvas.pack(side="left", padx=(0, 14))
        self.organisation = tk.StringVar(value=self.store.settings().get("organisation", APP_NAME))
        ttk.Label(bar, textvariable=self.organisation, style="MutedBar.TLabel").pack(side="left")
        # right-hand side — user identity first, then a quiet data-path chip
        ttk.Label(
            bar, text=f"{self.user['full_name']}  ·  {self.user['role'].title()}",
            style="MutedBar.TLabel",
        ).pack(side="right")
        root_text = str(DATA_ROOT)
        if len(root_text) > 42:
            root_text = "…" + root_text[-41:]
        ttk.Label(bar, text=root_text, style="MicroBar.TLabel").pack(side="right", padx=(0, 18))

    # -- pages ------------------------------------------------------------
    def show_page(self, key: str) -> None:
        if self.current and self.current in self.pages:
            self.pages[self.current].pack_forget()
        self.current = key
        page = self.pages.get(key)
        if page is None:
            page = PAGE_BY_KEY[key](self.container, self)
            self.pages[key] = page
        page.pack(fill="both", expand=True)
        try:
            page.refresh()
        except Exception as error:  # one broken page must not stop the app
            logging.getLogger(__name__).exception("The '%s' page could not be refreshed", key)
            messagebox.showerror(APP_NAME, f"The {LABEL_BY_KEY.get(key, key)} page could not be refreshed:\n{error}", parent=self)
        for button_key, button in self.buttons.items():
            button.configure(style="SidebarActive.TButton" if button_key == key else "Sidebar.TButton")

    def refresh_all(self) -> None:
        self.feed.sync()  # every dialog that touches the fleet updates the GPS feed too
        page = self.pages.get(self.current)
        if page is not None:
            page.refresh()
        self.organisation.set(self.store.settings().get("organisation", APP_NAME))

    # -- connectivity -----------------------------------------------------
    def _start_connectivity_check(self) -> None:
        worker = threading.Thread(target=self._connectivity_worker, daemon=True)
        worker.start()
        self.after(5000, self._poll_connectivity)

    def _connectivity_worker(self) -> None:
        import urllib.error
        import urllib.request

        while not self._closing.is_set():
            try:
                with urllib.request.urlopen("https://www.openstreetmap.org", timeout=3) as response:
                    self._online = response.getcode() == 200
            except (urllib.error.URLError, OSError, ValueError):
                self._online = False
            self._closing.wait(30)

    def _poll_connectivity(self) -> None:
        if not self.winfo_exists():
            return
        if self._online is None:
            color, text = PALETTE["muted"], "Checking internet connection…"
        elif self._online:
            color, text = PALETTE["ok"], "Internet connection available"
        else:
            color, text = PALETTE["warn"], "Offline — every feature still works, the map is drawn locally"
        self.dot.delete("all")
        # outer ring + inner dot reads as a clean status indicator on white
        self.dot.create_oval(1, 1, 11, 11, outline=_mix(color, "#FFFFFF", 0.45), width=1)
        self.dot.create_oval(3, 3, 9, 9, fill=color, outline="")
        self.status.configure(text=text)
        self.after(10000, self._poll_connectivity)

    # -- cross-page helpers -------------------------------------------------
    def open_new_booking(self, customer: dict[str, Any] | None = None, vehicle: dict[str, Any] | None = None) -> None:
        try:
            dialog = BookingDialog(self, self.store, customer=customer, vehicle=vehicle)
        except ValueError as error:
            messagebox.showinfo(APP_NAME, str(error), parent=self)
            return
        self.wait_window(dialog)
        if dialog.result:
            self.refresh_all()

    def open_payment_dialog(self, booking_id: int | None = None) -> None:
        try:
            dialog = PaymentDialog(self, self.store, booking_id=booking_id, username=self.user["username"])
        except ValueError as error:
            messagebox.showinfo(APP_NAME, str(error), parent=self)
            return
        self.wait_window(dialog)
        if dialog.result:
            self.refresh_all()

    def focus_vehicle_on_map(self, vehicle_id: int) -> None:
        self.show_page("gps")
        page = self.pages.get("gps")
        if page is not None:
            page.focus_vehicle(vehicle_id)

    def focus_customer_on_map(self, customer_id: int) -> None:
        self.show_page("gps")
        page = self.pages.get("gps")
        if page is not None:
            page.focus_customer(customer_id)

    def focus_point_on_map(self, lat: float, lon: float, span: float = 5.0) -> None:
        self.show_page("gps")
        page = self.pages.get("gps")
        if page is not None:
            page.focus_point(lat, lon, span)

    def open_bookings_for(self, query: str) -> None:
        """Jump to the bookings page pre-filtered on a plate or customer name."""
        self.show_page("bookings")
        page = self.pages.get("bookings")
        if page is not None:
            page.focus_query(query)

    def open_customers_for(self, query: str) -> None:
        """Jump to the customer directory pre-filtered on a name."""
        self.show_page("customers")
        page = self.pages.get("customers")
        if page is not None:
            page.focus_query(query)

    # -- scheduled work ------------------------------------------------------
    def _start_auto_scan(self) -> None:
        if self.store.settings().get("auto_scan", "1") != "1":
            return
        self.after(15 * 60 * 1000, self._auto_scan_tick)

    def _auto_scan_tick(self) -> None:
        if not self.winfo_exists() or self._closing.is_set():
            return
        if self.store.settings().get("auto_scan", "1") != "1":
            return  # the setting was switched off — stop the timer
        created: list[str] = []
        try:
            created = self.store.run_flood_scan(self.user["username"])
        except Exception:  # one bad scan must never kill the schedule
            logging.getLogger(__name__).exception("Automatic flood scan failed")
            created = []
        if created:
            if self.store.settings().get("sound_alerts", "1") == "1":
                try:
                    self.winfo_toplevel().bell()
                except tk.TclError:
                    pass
            self.refresh_all()
        self.after(15 * 60 * 1000, self._auto_scan_tick)

    def _backup(self) -> None:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        destination = filedialog.asksaveasfilename(
            parent=self,
            title="Backup database",
            defaultextension=".db",
            initialfile=f"rental_system_backup_{stamp}.db",
            filetypes=[("SQLite database", "*.db"), ("All files", "*.*")],
        )
        if not destination:
            return
        try:
            saved = self.store.backup(destination)
        except (RuntimeError, sqlite3.Error) as error:
            messagebox.showerror(APP_NAME, f"The backup could not be created:\n{error}", parent=self)
            return
        messagebox.showinfo(APP_NAME, f"The database was backed up to:\n{saved}", parent=self)

    def _about(self) -> None:
        messagebox.showinfo(
            APP_NAME,
            f"{APP_NAME} v{APP_VERSION}\n\nRental operations with flood-risk monitoring"
            f" for Metro Manila.\n\nInterface: Tkinter · Storage: SQLite · Map data: OpenStreetMap\n"
            f"Data folder: {DATA_ROOT}\n\nDefault login: {DEFAULT_ADMIN_USERNAME} / {DEFAULT_ADMIN_PASSWORD}",
            parent=self,
        )

    def _sign_out(self) -> None:
        if not messagebox.askyesno(APP_NAME, "Sign out and return to the sign-in window?", parent=self):
            return
        self.sign_out = True
        self.close()

    def close(self) -> None:
        if not self.sign_out and self.store.settings().get("confirm_exit", "1") == "1":
            if not messagebox.askyesno(APP_NAME, "Quit Flood Ready Vehicle System?", parent=self):
                return
        self._closing.set()
        self.feed.stop()
        self.winfo_toplevel().quit()


# ---------------------------------------------------------------------------
# Launcher
# ---------------------------------------------------------------------------


def run_smoke_test(log_path: str) -> int:
    """Build every page offscreen and exercise the services."""
    print(f"{APP_NAME} {APP_VERSION} — smoke test")
    print("-" * 56)
    failures: list[str] = []
    try:
        store = Store()
        print(" [ok] folders, database, schema and seed data")
    except Exception as error:  # noqa: BLE001 - report and stop
        print(f" [FAIL] database preparation: {type(error).__name__}: {error}")
        print(f"\nTechnical details were written to {log_path}")
        return 1

    def _status_guards() -> None:
        """Completed rentals and manual 'rented' flags must be rejected."""
        completed = store.row("SELECT id FROM bookings WHERE status = 'completed' LIMIT 1")
        if completed is not None:
            try:
                store.set_booking_status(int(completed["id"]), "confirmed")
            except ValueError:
                pass
            else:
                raise AssertionError("a completed booking accepted a status transition")
        free = store.row(
            "SELECT id FROM vehicles WHERE status = 'available' AND id NOT IN"
            " (SELECT vehicle_id FROM bookings WHERE status IN ('pending', 'confirmed', 'ongoing')) LIMIT 1"
        )
        if free is not None:
            try:
                store.set_vehicle_status(int(free["id"]), "rented")
            except ValueError:
                pass
            else:
                raise AssertionError("a unit was marked rented without an ongoing booking")

    def _booking_workflow() -> None:
        """Drive one scratch booking through the full rental lifecycle."""
        vehicle = store.row(
            "SELECT * FROM vehicles WHERE status = 'available' AND id NOT IN"
            " (SELECT vehicle_id FROM bookings WHERE status IN ('pending', 'confirmed', 'ongoing')) LIMIT 1"
        )
        customer = store.row("SELECT id FROM customers LIMIT 1")
        if vehicle is None or customer is None:
            return
        today = datetime.now().strftime(DATE_FORMAT)
        soon = (datetime.now() + timedelta(days=2)).strftime(DATE_FORMAT)
        later = (datetime.now() + timedelta(days=5)).strftime(DATE_FORMAT)
        booking_id = store.add_booking(
            {"vehicle_id": vehicle["id"], "customer_id": customer["id"], "start_date": today, "end_date": soon, "status": "pending"}
        )
        try:
            store.set_booking_status(booking_id, "confirmed")
            store.set_booking_status(booking_id, "ongoing")
            flag = store.value("SELECT status FROM vehicles WHERE id = ?", (vehicle["id"],))
            if flag != "rented":
                raise AssertionError("starting a rental did not mark the unit rented")
            days = store.extend_booking(booking_id, later)
            if days < 2:
                raise AssertionError("extend_booking returned an unexpected duration")
            store.set_booking_status(booking_id, "completed")
            flag = store.value("SELECT status FROM vehicles WHERE id = ?", (vehicle["id"],))
            if flag != "available":
                raise AssertionError("completing a rental did not free the unit")
        finally:
            store.execute("DELETE FROM transactions WHERE booking_id = ?", (booking_id,))
            store.execute("DELETE FROM bookings WHERE id = ?", (booking_id,))
            store.sync_vehicle_status(int(vehicle["id"]))

    def _overlap_guards() -> None:
        """Double-bookings must be rejected; back-to-back rentals must pass."""
        vehicle = store.row(
            "SELECT * FROM vehicles WHERE status = 'available' AND id NOT IN"
            " (SELECT vehicle_id FROM bookings WHERE status IN ('pending', 'confirmed', 'ongoing')) LIMIT 1"
        )
        customer = store.row("SELECT id FROM customers LIMIT 1")
        if vehicle is None or customer is None:
            return
        today = datetime.now().strftime(DATE_FORMAT)
        soon = (datetime.now() + timedelta(days=2)).strftime(DATE_FORMAT)
        after = (datetime.now() + timedelta(days=4)).strftime(DATE_FORMAT)
        booking_id = store.add_booking(
            {"vehicle_id": vehicle["id"], "customer_id": customer["id"], "start_date": today, "end_date": soon, "status": "pending"}
        )
        try:
            try:
                store.add_booking(
                    {"vehicle_id": vehicle["id"], "customer_id": customer["id"], "start_date": today, "end_date": soon, "status": "pending"}
                )
            except ValueError:
                pass
            else:
                raise AssertionError("an overlapping booking was accepted")
            back_to_back = store.add_booking(
                {"vehicle_id": vehicle["id"], "customer_id": customer["id"], "start_date": soon, "end_date": after, "status": "pending"}
            )
            try:
                store.extend_booking(booking_id, after)
            except ValueError:
                pass
            else:
                raise AssertionError("an extension overlapping another booking was accepted")
            store.execute("DELETE FROM bookings WHERE id = ?", (back_to_back,))
        finally:
            store.execute("DELETE FROM transactions WHERE booking_id = ?", (booking_id,))
            store.execute("DELETE FROM bookings WHERE id = ?", (booking_id,))
            store.sync_vehicle_status(int(vehicle["id"]))

    for label, check in (
        ("authentication", lambda: store.login(DEFAULT_ADMIN_USERNAME, DEFAULT_ADMIN_PASSWORD)),
        ("dashboard statistics", store.dashboard),
        ("flood risk scan", lambda: store.run_flood_scan(DEFAULT_ADMIN_USERNAME)),
        ("exposure distances", store.exposure),
        ("report builders", lambda: [store.report(key) for key in store.REPORTS]),
        ("booking workflow", _booking_workflow),
        ("double-booking guards", _overlap_guards),
        ("status guards", _status_guards),
    ):
        try:
            check()
            print(f" [ok] {label}")
        except Exception as error:  # noqa: BLE001
            failures.append(f"{label}: {type(error).__name__}: {error}")
            print(f" [FAIL] {label}: {type(error).__name__}: {error}")

    root = tk.Tk()
    root.withdraw()
    build_fonts(root)
    apply_theme(root)
    user = store.login(DEFAULT_ADMIN_USERNAME, DEFAULT_ADMIN_PASSWORD)
    try:
        window = MainWindow(root, store, user)
        for key, label, _icon, _page in NAV_PAGES:
            if key == "users" and user["role"] != "admin":
                continue
            try:
                window.show_page(key)
                root.update_idletasks()
                print(f" [ok] {label.lower()} page")
            except Exception as error:  # noqa: BLE001
                failures.append(f"{label.lower()} page: {type(error).__name__}: {error}")
                print(f" [FAIL] {label.lower()} page: {type(error).__name__}: {error}")
        try:
            window.feed.sync()
            untracked = [
                vehicle["plate_number"]
                for vehicle in store.vehicles()
                if int(vehicle["id"]) not in window.feed.units
            ]
            if untracked:
                failures.append(
                    f"feed detection: {len(untracked)} unit(s) not tracked: {', '.join(untracked[:4])}"
                )
                print(f" [FAIL] feed detection ({len(untracked)} unit(s) untracked)")
            else:
                print(f" [ok] feed detection ({len(window.feed.units)} units tracked live)")
        except Exception as error:  # noqa: BLE001
            failures.append(f"feed detection: {type(error).__name__}: {error}")
            print(f" [FAIL] feed detection: {type(error).__name__}: {error}")
        try:
            fleet = store.vehicles()
            gps_page = window.pages.get("gps")
            if gps_page is not None and fleet:
                gps_page.select(int(fleet[0]["id"]))
                gps_page.map.focus(int(fleet[0]["id"]))
                root.update_idletasks()
                print(" [ok] fleet list selection and pin focus")
            else:
                print(" [skip] fleet list selection (no gps page or empty fleet)")
        except Exception as error:  # noqa: BLE001
            failures.append(f"fleet selection: {type(error).__name__}: {error}")
            print(f" [FAIL] fleet selection: {type(error).__name__}: {error}")
        window.destroy()
    except Exception as error:  # noqa: BLE001
        failures.append(f"main window: {type(error).__name__}: {error}")
        print(f" [FAIL] main window: {type(error).__name__}: {error}")
    finally:
        root.destroy()

    print("-" * 56)
    if failures:
        print(f"{len(failures)} problem(s) found:")
        for failure in failures:
            print(f"  - {failure}")
        print(f"\nTechnical details were written to {log_path}")
        return 1
    print("Everything works. Start the application with:\n  python main.py")
    return 0


def _fatal(message: str, log_path: str) -> None:
    logging.getLogger(__name__).critical(message)
    try:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(APP_NAME, f"{message}\n\nData folder: {DATA_DIR}\nLog file: {log_path}")
        root.destroy()
    except Exception:  # pragma: no cover - no display available
        print(message, file=sys.stderr)


def main() -> int:
    log_path = setup_logging()
    sys.excepthook = lambda kind, value, trace: logging.getLogger(__name__).exception(
        "Unhandled exception", exc_info=(kind, value, trace)
    )
    if sys.platform == "win32":  # crisp text on high-DPI Windows displays
        try:
            import ctypes

            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:  # pragma: no cover - older Windows releases
            pass
    if "--smoke-test" in sys.argv[1:]:
        return run_smoke_test(str(log_path))

    try:
        store = Store()
    except Exception as error:  # noqa: BLE001 - friendly startup failure
        logging.getLogger(__name__).exception("Startup failed")
        _fatal(f"The application could not prepare its local database.\n\n{type(error).__name__}: {error}", str(log_path))
        return 1

    try:
        root = tk.Tk()
    except Exception as error:  # pragma: no cover - python without tcl/tk
        _fatal(
            "Python's Tkinter module is not available on this computer.\n\n"
            "Reinstall Python 3.11 or newer and make sure the 'tcl/tk and IDLE' "
            "option is ticked in the installer.",
            str(log_path),
        )
        logging.getLogger(__name__).debug("tkinter import error: %s", error)
        return 1

    build_fonts(root)
    apply_theme(root)
    root.withdraw()

    try:
        while True:
            login = LoginWindow(root, store)
            root.wait_window(login)
            if login.user is None:
                root.destroy()
                return 0
            window = MainWindow(root, store, login.user)
            root.deiconify()
            root.mainloop()
            window.destroy()
            if not window.sign_out:
                root.destroy()
                return 0
            root.withdraw()
    except Exception as error:  # noqa: BLE001
        logging.getLogger(__name__).exception("Interface failure")
        _fatal(
            f"The application interface could not be started.\n\n{type(error).__name__}: {error}",
            str(log_path),
        )
        return 1
    finally:
        logging.getLogger(__name__).info("Application closed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
