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
APP_VERSION = "1.2.0"

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
# Palette — one accent, warm neutrals, hairline borders
# ---------------------------------------------------------------------------

PALETTE: dict[str, str] = {
    "bg": "#FAFAF8",
    "surface": "#FFFFFF",
    "line": "#E6E8E3",
    "line_soft": "#F0F2ED",
    "sunken": "#F4F5F2",
    "ink": "#161B18",
    "ink_soft": "#4E5A54",
    "muted": "#8B948E",
    "faint": "#AAB2AD",
    "accent": "#0E7C5B",
    "accent_hover": "#0A6349",
    "accent_soft": "#ECF4F0",
    "accent_line": "#CFE4DB",
    "ok": "#178A63",
    "ok_soft": "#ECF5F0",
    "warn": "#B3882A",
    "warn_soft": "#FAF3E2",
    "danger": "#B64F4A",
    "danger_soft": "#FBEEED",
    "info": "#3468C0",
    "info_soft": "#EDF2FB",
    "water": "#DFE9E8",
    "land": "#F8F8F4",
    "park": "#E4ECDF",
    "road": "#FFFFFF",
    "road_edge": "#E2E5DD",
    "grid": "#E7E9E2",
}

RISK_COLORS = {
    "low": "#178A63",
    "moderate": "#B3882A",
    "high": "#C1703A",
    "severe": "#B64F4A",
}
RISK_SCORES = {"low": 12, "moderate": 31, "high": 52, "severe": 78}

STATUS_COLORS = {
    "available": "#0E7C5B",
    "rented": "#3468C0",
    "maintenance": "#B3882A",
}

SEVERITY_COLORS = {"info": "#3468C0", "warning": "#B3882A", "critical": "#B64F4A"}

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
            "nav": font(9),
            "body": font(10),
            "h2": font(11, "bold"),
            "title": font(16, "bold"),
            "value": font(17, "bold"),
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
    ):
        style.configure(name, background=background)

    def labels(background: str, suffix: str) -> None:
        style.configure(f"Title{suffix}", background=background, foreground=p["ink"], font=FONTS["h2"])
        style.configure(f"Body{suffix}", background=background, foreground=p["ink_soft"], font=FONTS["body"])
        style.configure(f"Muted{suffix}", background=background, foreground=p["muted"], font=FONTS["small"])
        style.configure(f"Micro{suffix}", background=background, foreground=p["faint"], font=FONTS["micro"])
        style.configure(f"Value{suffix}", background=background, foreground=p["ink"], font=FONTS["value"])

    labels(p["bg"], ".TLabel")
    labels(p["surface"], "Card.TLabel")
    labels(p["sunken"], "Sunken.TLabel")

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
            padding=(12, 7),
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
    flat("Quiet.TButton", p["accent_soft"], p["accent"], "#E1EFE9")
    flat("Ghost.TButton", p["sunken"], p["ink_soft"], "#EAECED")
    flat("Secondary.TButton", p["surface"], p["ink_soft"], p["sunken"], border=p["line"])

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
        padding=(9, 6),
        relief="flat",
    )
    style.map(
        "Field.TEntry",
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
        rowheight=34,
        borderwidth=0,
        font=FONTS["small"],
    )
    style.configure(
        "Data.Treeview.Heading",
        background=p["surface"],
        foreground=p["faint"],
        font=FONTS["micro_bold"],
        relief="flat",
        borderwidth=0,
        padding=(9, 7),
    )
    style.map("Data.Treeview", background=[("selected", p["accent_soft"])], foreground=[("selected", p["ink"])])
    style.map("Data.Treeview.Heading", background=[("active", p["surface"])])

    style.configure(
        "Thin.TScrollbar",
        background=p["line"],
        troughcolor=p["surface"],
        bordercolor=p["surface"],
        lightcolor=p["line"],
        darkcolor=p["line"],
        arrowsize=11,
        gripcount=0,
        relief="flat",
    )
    style.layout("Vertical.Thin.TScrollbar", style.layout("Vertical.TScrollbar"))
    style.layout("Horizontal.Thin.TScrollbar", style.layout("Horizontal.TScrollbar"))
    style.map(
        "Thin.TScrollbar",
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
        "PillLow": (RISK_COLORS["low"], "#ECF5F0"),
        "PillModerate": (RISK_COLORS["moderate"], "#FAF3E2"),
        "PillHigh": (RISK_COLORS["high"], "#FBF0E7"),
        "PillSevere": (RISK_COLORS["severe"], "#FBEEED"),
        "PillInfo": (SEVERITY_COLORS["info"], p["info_soft"]),
        "PillWarning": (SEVERITY_COLORS["warning"], p["warn_soft"]),
        "PillCritical": (SEVERITY_COLORS["critical"], p["danger_soft"]),
        "PillNeutral": (p["muted"], p["sunken"]),
    }
    for name, (foreground, background) in pills.items():
        style.configure(
            f"{name}Card.TLabel",
            background=background,
            foreground=foreground,
            font=FONTS["micro_bold"],
            padding=(9, 3),
        )
    return style


# ---------------------------------------------------------------------------
# Small building blocks
# ---------------------------------------------------------------------------


class Card(ttk.Frame):
    """White panel with a hairline border (ttk cannot draw one natively)."""

    def __init__(self, master: tk.Widget, padding: tuple[int, int] = (16, 14), style: str = "Card.TFrame") -> None:
        super().__init__(master, style="CardBorder.TFrame", padding=1)
        self.body = ttk.Frame(self, style=style, padding=padding)
        self.body.pack(fill="both", expand=True)


class Stat(ttk.Frame):
    """Compact metric tile."""

    def __init__(self, master: tk.Widget, label: str, meta: str = "", tone: str = "accent") -> None:
        super().__init__(master, style="CardBorder.TFrame", padding=1)
        body = ttk.Frame(self, style="Card.TFrame", padding=(14, 12))
        body.pack(fill="both", expand=True)
        dot = tk.Canvas(body, width=7, height=7, background=PALETTE["surface"], highlightthickness=0, bd=0)
        dot.create_oval(0, 0, 7, 7, fill=PALETTE.get(tone, PALETTE["accent"]), outline="")
        dot.pack(anchor="w")
        ttk.Label(body, text=label.upper(), style="MicroCard.TLabel").pack(anchor="w", pady=(6, 0))
        self.value = ttk.Label(body, text="—", style="ValueCard.TLabel")
        self.value.pack(anchor="w", pady=(4, 0))
        self.meta = ttk.Label(body, text=meta, style="MutedCard.TLabel", wraplength=180, justify="left")
        self.meta.pack(anchor="w", pady=(4, 0))

    def set(self, value: str, meta: str = "") -> None:
        self.value.configure(text=value)
        if meta:
            self.meta.configure(text=meta)


class Bar(tk.Canvas):
    """Slim progress meter that follows its container width."""

    def __init__(self, master: tk.Widget, height: int = 5, color: str | None = None, track: str | None = None) -> None:
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
        self.create_rectangle(0, 0, int(width * self.fraction), height, fill=self.color, outline="")


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
        if not self.data:
            return
        width, height = max(int(self.winfo_width()), 40), max(int(self.winfo_height()), 40)
        peak = max(value for _label, value in self.data) or 1.0
        count = len(self.data)
        gap = 14
        column = max((width - gap * (count - 1)) / count, 8)
        top, label_space = 20, 20
        for index, (label, value) in enumerate(self.data):
            x = index * (column + gap)
            bar_height = (height - top - label_space) * (value / peak)
            y = height - label_space - bar_height
            self.create_rectangle(x, y, x + column, height - label_space, fill=PALETTE["accent"], outline="")
            self.create_text(
                x + column / 2, y - 9, text=_short(value), font=FONTS["micro"], fill=PALETTE["muted"], anchor="s"
            )
            self.create_text(
                x + column / 2, height - 6, text=label, font=FONTS["small"], fill=PALETTE["muted"], anchor="s"
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
            self.tree.heading(key, text=heading, anchor="w")
            self.tree.column(key, width=width, minwidth=48, anchor=anchor, stretch=True)
        self.scroll = ttk.Scrollbar(holder, orient="vertical", command=self.tree.yview, style="Thin.TScrollbar")
        self.tree.configure(yscrollcommand=self.scroll.set)
        self.tree.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=6)
        self.scroll.pack(side="right", fill="y", pady=6, padx=(0, 4))
        self.tree.tag_configure("odd", background=PALETTE["surface"])
        self.tree.tag_configure("even", background="#FBFCFA")
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
        self.clear()
        for index, row in enumerate(rows):
            values = [row.get(key, "") for key in self.keys]
            tags = ["even" if index % 2 else "odd"]
            if tag_of:
                extra = tag_of(row)
                if extra:
                    tags.append(extra)
            self.tree.insert("", "end", iid=str(row.get("id", index)), values=values, tags=tags)

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
    ) -> None:
        super().__init__(master, style="Card.TFrame")
        ttk.Label(self, text=label.upper(), style="MicroCard.TLabel").pack(anchor="w")
        self.variable = tk.StringVar(value=value)
        if choices is None:
            widget: tk.Widget = ttk.Entry(
                self, textvariable=self.variable, width=width, style="Field.TEntry", show="•" if secret else ""
            )
        else:
            widget = ttk.Combobox(
                self, textvariable=self.variable, values=list(choices), width=width, state="readonly", style="Field.TCombobox"
            )
        widget.pack(fill="x", pady=(5, 0))
        if on_change:
            self.variable.trace_add("write", lambda *_args: on_change(self.variable.get()))

    def get(self) -> str:
        return self.variable.get().strip()


class Divider(ttk.Frame):
    """One pixel hairline used inside cards."""

    def __init__(self, master: tk.Widget) -> None:
        super().__init__(master, style="CardBorder.TFrame", height=1)
        self.pack_propagate(False)


def heading(
    parent: tk.Widget,
    title: str,
    subtitle: str,
    actions: Sequence[Callable[[tk.Widget], tk.Widget]] = (),
) -> ttk.Frame:
    """Page header: large title, quiet subtitle, actions on the right."""
    bar = ttk.Frame(parent, style="Page.TFrame")
    text = ttk.Frame(bar, style="Page.TFrame")
    text.pack(side="left", fill="x", expand=True)
    ttk.Label(text, text=title, style="Title.TLabel").pack(anchor="w")
    ttk.Label(text, text=subtitle, style="Muted.TLabel").pack(anchor="w", pady=(4, 0))
    if actions:
        tools = ttk.Frame(bar, style="Page.TFrame")
        tools.pack(side="right")
        for make in actions:
            widget = make(tools)
            widget.pack(side="left", padx=(6, 0))
    bar.pack(fill="x", pady=(0, 16))
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
    "low": "#E4F0EA",
    "moderate": "#F8F0DA",
    "high": "#F9EADC",
    "severe": "#F9E5E3",
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
        self.path = path
        self.distances: list[float] = []
        total = 0.0
        for index in range(len(path) - 1):
            total += distance_km(path[index][0], path[index][1], path[index + 1][0], path[index + 1][1])
            self.distances.append(total)
        self.total = max(total, 0.001)
        self.offset = _hash(self.id, 7) * self.total
        self.direction = 1.0 if _hash(self.id, 3) > 0.5 else -1.0
        self.lat, self.lon = path[0]
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

    def __init__(self, store: "Store", host: tk.Misc, speed: float = 1.0) -> None:
        self.store = store
        self.host = host
        self.speed = speed
        self.running = False
        self.units: dict[int, Unit] = {}
        self.subscribers: list["MapCanvas"] = []
        self._job: str | None = None
        self._last: datetime | None = None
        self._since_commit = 0.0
        self.elapsed = 0.0
        self.rebuild()

    # -- setup ------------------------------------------------------------
    def rebuild(self) -> None:
        self.units = {}
        for record in self.store.vehicles():
            route = _route_for(record["latitude"], record["longitude"])
            self.units[int(record["id"])] = Unit(record, route)

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
        if seconds > 0:
            self.elapsed += seconds
            for unit in self.units.values():
                unit.advance(seconds, self.speed)
            self._since_commit += seconds
            if self._since_commit >= self.COMMIT_SECONDS:
                self.commit()
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
        stamp = datetime.now().strftime(DATETIME_FORMAT)
        for unit in self.units.values():
            self.store.execute(
                "UPDATE vehicles SET latitude = ?, longitude = ?, updated_at = ? WHERE id = ?",
                (unit.lat, unit.lon, stamp, unit.id),
            )

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
        show_labels: bool = True,
        show_zones: bool = True,
        show_vehicles: bool = True,
        show_grid: bool = True,
        legend: bool = True,
        border: bool = True,
        feed: "TrackingFeed | None" = None,
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
        self.show_labels = show_labels
        self.show_zones = show_zones
        self.show_vehicles = show_vehicles
        self.show_grid = show_grid
        self.legend = legend
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
        self._anim: dict[str, Any] | None = None
        self._anim_job: str | None = None
        self._readout_box: int | None = None
        self._readout_text_id: int | None = None

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
        self.center_lon += dx / self.scale / KM_PER_DEG_LON
        self.center_lat += dy / self.scale / KM_PER_DEG_LAT
        self._drag = (event.x, event.y)
        self._apply_cursor()
        self.draw()

    def _on_release(self, _event: tk.Event) -> None:
        self._drag = None
        self._apply_cursor()
        if self._moved:
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
        for vehicle_id, (mx, my) in self._markers.items():
            if abs(x - mx) <= 9 and abs(y - my) <= 9:
                return vehicle_id
        return None

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
        if not self._vehicles:
            self.reset()
            return
        positions: list[tuple[float, float]] = []
        for vehicle in self._vehicles:
            live = self.feed.live(vehicle["id"]) if self.feed is not None else None
            positions.append(
                (live.lat, live.lon) if live is not None else (vehicle["latitude"], vehicle["longitude"])
            )
        lats = [position[0] for position in positions]
        lons = [position[1] for position in positions]
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
        if vehicle is None:
            self.draw()
            return
        span = min(self.span_km, 7.0)
        if animate:
            self.fly_to(vehicle["longitude"], vehicle["latitude"], span, ms=380)
        else:
            self.center_lon, self.center_lat, self.span_km = vehicle["longitude"], vehicle["latitude"], span
            self.draw()

    def select(self, vehicle_id: int | None, notify: bool = False) -> None:
        self.selected_id = vehicle_id
        self.draw()
        if notify and self.on_select is not None and vehicle_id is not None:
            self.on_select(vehicle_id)

    # -- painting ---------------------------------------------------------
    follow_id: int | None = None

    def draw(self) -> None:
        if self.follow_id is not None and self.feed is not None:
            unit = self.feed.live(self.follow_id)
            if unit is not None:
                self.center_lat, self.center_lon = unit.lat, unit.lon
        self.delete("all")
        self._markers.clear()
        if self.winfo_width() < 24 or self.winfo_height() < 24:
            return
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
        if self.show_vehicles:
            self._draw_links()
            self._draw_vehicles()
        self._draw_overlay()

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
        self.create_polygon(points, fill=PALETTE["land"], outline=PALETTE["line"], width=1)

        cx, cy = self.project(*LAKE_CENTER)
        rx, ry = LAKE_RADIUS[0] * self.scale, LAKE_RADIUS[1] * self.scale
        if not (cx + rx < 0 or cx - rx > width or cy + ry < 0 or cy - ry > height):
            self.create_oval(cx - rx, cy - ry, cx + rx, cy + ry, fill=PALETTE["water"], outline="#CFDEDB", width=1)

        for (dx, dy), sx, sy in PARKS:
            x, y = self.project(*_ll(dx, dy))
            rx, ry = sx / 4997 * KM_PER_DEG_LON * self.scale, sy / 5132 * KM_PER_DEG_LAT * self.scale
            if self._outside(x, y, max(rx, ry)):
                continue
            self.create_oval(x - rx, y - ry, x + rx, y + ry, fill=PALETTE["park"], outline="")

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
        lines = 0
        lon = math.floor(left_lon / step) * step
        while lon <= right_lon and lines < 40:
            x = self.project(CENTER_LAT, lon)[0]
            self.create_line(x, 0, x, height, fill="#E9EDE8", width=1)
            if x > 40:
                self.create_text(x + 3, 7, text=f"{lon:.3f}°E", anchor="nw", font=FONTS["micro"], fill="#B4BDB7")
            lon += step
            lines += 1
        lines = 0
        lat = math.floor(bottom_lat / step) * step
        while lat <= top_lat and lines < 40:
            y = self.project(lat, self.center_lon)[1]
            self.create_line(0, y, width, y, fill="#E9EDE8", width=1)
            if y < height - 40:
                self.create_text(4, y - 3, text=f"{lat:.3f}°N", anchor="sw", font=FONTS["micro"], fill="#B4BDB7")
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
            self.create_line(flat, fill="#CFDEDC", width=width + 1.2, smooth=True, capstyle="round")
            self.create_line(flat, fill="#D9E6E5", width=width, smooth=True, capstyle="round")

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
            self.create_line(x1, y1, x2, y2, fill=PALETTE["grid"], width=width)

    def _draw_roads(self) -> None:
        """Two passes so the casings merge underneath the white road surface."""
        casing = max(2.6, min(13.0, self.scale * 0.085))
        surface = max(1.2, min(8.5, self.scale * 0.055))
        paths: list[list[float]] = []
        for _name, points in ARTERIALS:
            flat: list[float] = []
            for lat, lon in points:
                flat.extend(self.project(lat, lon))
            if len(flat) >= 4:
                paths.append(flat)
        for flat in paths:
            self.create_line(flat, fill=PALETTE["road_edge"], width=casing, smooth=True, capstyle="round", joinstyle="round")
        for flat in paths:
            self.create_line(flat, fill=PALETTE["road"], width=surface, smooth=True, capstyle="round", joinstyle="round")

    def _draw_places(self) -> None:
        for text, lat, lon, kind in MAP_LABELS:
            if not self.visible(lat, lon, 50):
                continue
            x, y = self.project(lat, lon)
            label = text.upper() if kind == "city" else text
            fill = "#A7AFA9" if kind == "city" else "#94A9A6"
            for dx, dy in ((-0.8, 0), (0.8, 0), (0, -0.8), (0, 0.8)):
                self.create_text(x + dx, y + dy, text=label, font=FONTS["micro"], fill=PALETTE["land"])
            self.create_text(x, y, text=label, font=FONTS["micro"], fill=fill)

    def _draw_zones(self) -> None:
        taken: list[tuple[float, float, float, float]] = []
        ring = max(1.0, min(2.0, self.scale * 0.02))
        for zone in sorted(self._zones, key=lambda item: RISK_SCORES.get(item["risk_level"], 0), reverse=True):
            color = RISK_COLORS.get(zone["risk_level"], PALETTE["muted"])
            tint = ZONE_TINTS.get(zone["risk_level"], "#F1F2EC")
            cx, cy = self.project(zone["latitude"], zone["longitude"])
            radius = max(zone["radius_km"] * self.scale, 4)
            if self._outside(cx, cy, radius):
                continue
            if zone["is_active"]:
                self.create_oval(cx - radius, cy - radius, cx + radius, cy + radius, fill=tint, outline="")
                self.create_oval(cx - radius, cy - radius, cx + radius, cy + radius, outline=color, width=ring, dash=(5, 4))
            else:
                self.create_oval(cx - radius, cy - radius, cx + radius, cy + radius, outline=PALETTE["faint"], width=1, dash=(2, 4))
            self.create_oval(cx - 3, cy - 3, cx + 3, cy + 3, fill=color, outline="")
            if self.show_labels and self.span_km <= 34:
                self._chip(
                    cx, cy - radius - 18, zone["name"].upper(),
                    sub=ZONE_RISK_WORD.get(zone["risk_level"], ""), color=color, boxes=taken,
                )

    def _draw_secondary(self) -> None:
        """Minor arterials: thinner casing, slightly grey surface."""
        if self.scale < 3:
            return
        casing = max(1.6, min(7.0, self.scale * 0.045))
        surface = max(0.8, min(4.6, self.scale * 0.028))
        for points in SECONDARY_ROADS:
            flat: list[float] = []
            for lat, lon in points:
                flat.extend(self.project(lat, lon))
            if self._offscreen_polyline(flat, 120):
                continue
            self.create_line(flat, fill="#E6E8E0", width=casing, smooth=True, capstyle="round")
            self.create_line(flat, fill="#FBFBF8", width=surface, smooth=True, capstyle="round")

    def _draw_fabric(self) -> None:
        """City blocks under the road network, so street level reads as a city."""
        if self.scale < 26:
            return
        width, height = self.winfo_width(), self.winfo_height()
        block = 0.24
        columns = int(self.span_km / block) + 2
        rows = int(self.span_km * height / max(width, 1) / block) + 2
        if columns * rows > 620 or columns < 1 or rows < 1:
            return
        detailed = self.scale > 70
        fill = "#EFEFE8" if detailed else "#F0F0EA"
        edge = "#E7E7DF" if detailed else ""
        half_i, half_j = columns // 2, rows // 2
        for i in range(-half_i, half_i + 1):
            for j in range(-half_j, half_j + 1):
                x_km = i * block
                y_km = j * block
                lat = CENTER_LAT - y_km / KM_PER_DEG_LAT
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
                self.create_rectangle(ax, ay, bx, by, fill=fill, outline=edge)

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
            for dx, dy in ((-0.7, 0), (0.7, 0), (0, -0.7), (0, 0.7)):
                self.create_text(
                    middle_x + dx, middle_y + dy, text=name.upper(), angle=angle,
                    font=FONTS["micro"], fill=PALETTE["road"],
                )
            self.create_text(
                middle_x, middle_y, text=name.upper(), angle=angle,
                font=FONTS["micro"], fill="#ADB5AD",
            )

    def _draw_places(self) -> None:
        if self.scale > 85:
            for name, x, y in DISTRICTS:
                lat, lon = _ll(x, y)
                if not self.visible(lat, lon, 40):
                    continue
                px, py = self.project(lat, lon)
                for dx, dy in ((-0.7, 0), (0.7, 0), (0, -0.7), (0, 0.7)):
                    self.create_text(px + dx, py + dy, text=name, font=FONTS["micro"], fill=PALETTE["land"])
                self.create_text(px, py, text=name, font=FONTS["micro"], fill="#B4BBAF")
        for text, lat, lon, kind in MAP_LABELS:
            if not self.visible(lat, lon, 50):
                continue
            x, y = self.project(lat, lon)
            label = text.upper() if kind == "city" else text
            font = FONTS["small"] if kind == "city" else FONTS["micro"]
            fill = "#9CA49C" if kind == "city" else "#94A9A6"
            for dx, dy in ((-0.9, 0), (0.9, 0), (0, -0.9), (0, 0.9)):
                self.create_text(x + dx, y + dy, text=label, font=font, fill=PALETTE["land"])
            self.create_text(x, y, text=label, font=font, fill=fill)

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

    @staticmethod
    def _heading_polygon(x: float, y: float, bearing: float, size: float) -> tuple[float, float, float, float, float, float]:
        def point(angle: float, distance: float) -> tuple[float, float]:
            radians = math.radians(angle)
            return x + math.sin(radians) * distance, y - math.cos(radians) * distance

        tip = point(bearing, size * 2.1)
        left = point(bearing + 143, size)
        right = point(bearing - 143, size)
        return (*tip, *left, *right)

    def _draw_vehicles(self) -> None:
        radius = max(3.6, min(6.4, self.scale * 0.05))
        taken: list[tuple[float, float, float, float]] = []
        # Draw the focused unit last so it always sits on top of its neighbours.
        ordered = sorted(
            self._vehicles,
            key=lambda vehicle: (vehicle["id"] == self.selected_id, vehicle["id"] == self.hover_id),
        )
        for vehicle in ordered:
            live = self.feed.live(vehicle["id"]) if self.feed is not None else None
            lat = live.lat if live else vehicle["latitude"]
            lon = live.lon if live else vehicle["longitude"]
            x, y = self.project(lat, lon)
            self._markers[vehicle["id"]] = (x, y)
            if self._outside(x, y, 40):
                continue
            color = STATUS_COLORS.get(vehicle["status"], PALETTE["accent"])
            active = vehicle["id"] in (self.selected_id, self.hover_id)

            if live is not None and len(live.trail) > 2 and self.scale > 4:
                trail = live.trail if live.parked is False else live.trail[-14:]
                flat: list[float] = []
                for trail_lat, trail_lon in trail:
                    trail_x, trail_y = self.project(trail_lat, trail_lon)
                    if self._outside(trail_x, trail_y, 60):
                        continue
                    flat.extend((trail_x, trail_y))
                if len(flat) >= 6:
                    self.create_line(
                        flat, fill=_mix(PALETTE["land"], color, 0.42),
                        width=max(1.0, radius * 0.34), smooth=True, capstyle="round",
                    )
                total = len(trail)
                step = 1 if total <= 12 else 2
                for index in range(0, total, step):
                    trail_x, trail_y = self.project(*trail[index])
                    if self._outside(trail_x, trail_y, 30):
                        continue
                    depth = (index + 1) / total
                    halo = 0.9 + 1.9 * depth
                    self.create_oval(
                        trail_x - halo, trail_y - halo, trail_x + halo, trail_y + halo,
                        fill=_mix(PALETTE["land"], color, 0.26 + 0.6 * depth), outline="",
                    )

            if vehicle["id"] == self.selected_id:
                for halo in (radius + 7, radius + 13):
                    self.create_oval(x - halo, y - halo, x + halo, y + halo, outline=color, width=1)
                for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
                    self.create_line(
                        x + dx * (radius + 3), y + dy * (radius + 3),
                        x + dx * (radius + 9), y + dy * (radius + 9),
                        fill=color, width=1.2,
                    )

            if live is not None:
                self.create_polygon(
                    self._heading_polygon(x, y, live.heading, radius + 2.2),
                    fill=color, outline="",
                )
            marker = radius + 1.8 if active else radius
            self.create_oval(
                x - marker, y - marker, x + marker, y + marker,
                fill="#FFFFFF" if live is None else _mix("#FFFFFF", color, 0.18),
                outline=color, width=max(1.8, radius * 0.55),
            )

            if active:
                detail = vehicle["plate_number"]
                if live is not None:
                    detail = f"{vehicle['plate_number']}  ·  {live.speed:.0f} km/h {compass_text(live.heading)}"
                self._chip(
                    x + radius + 14, y, f"{vehicle['brand']} {vehicle['model']}",
                    sub=detail, color=color, boxes=taken, centered=False,
                )

    def _draw_links(self) -> None:
        """Join the focused unit to its nearest active zone with the distance."""
        if self.selected_id is None:
            return
        vehicle = next((item for item in self._vehicles if item["id"] == self.selected_id), None)
        if vehicle is None:
            return
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
        self.create_line(x1, y1, x2, y2, fill=color, width=1.2, dash=(4, 3))
        self._chip((x1 + x2) / 2, (y1 + y2) / 2, f"{kilometres:.2f} km", color=color)

    def _draw_overlay(self) -> None:
        """Scale bar, legend, north arrow, coordinate readout and attribution."""
        width, height = self.winfo_width(), self.winfo_height()

        kilometres = self._nice_distance()
        length = kilometres * self.scale
        self.create_rectangle(14, height - 32, 52 + length, height - 6, fill="#FFFFFF", outline=PALETTE["line"])
        self.create_line(24, height - 14, 24 + length, height - 14, fill=PALETTE["ink_soft"], width=2)
        for tick in (24, 24 + length):
            self.create_line(tick, height - 19, tick, height - 9, fill=PALETTE["ink_soft"], width=2)
        self.create_text(
            24 + length + 8, height - 14, text=f"{kilometres:g} km",
            anchor="w", font=FONTS["micro"], fill=PALETTE["muted"],
        )

        if self.legend and self.show_vehicles:
            entries = (
                ("Available", STATUS_COLORS["available"]),
                ("Rented", STATUS_COLORS["rented"]),
                ("Maintenance", STATUS_COLORS["maintenance"]),
            )
            box_width, box_height = 96, 10 + len(entries) * 14
            left, bottom = width - 14, height - 32
            self.create_rectangle(
                left - box_width, bottom - box_height, left, bottom,
                fill="#FFFFFF", outline=PALETTE["line"],
            )
            for index, (label, color) in enumerate(entries):
                cy = bottom - box_height + 11 + index * 14
                self.create_oval(left - box_width + 10, cy - 3, left - box_width + 16, cy + 3, fill="#FFFFFF", outline=color, width=2)
                self.create_text(left - box_width + 22, cy, text=label, anchor="w", font=FONTS["micro"], fill=PALETTE["ink_soft"])

        self.create_text(
            width - 10, height - 10, text="© OpenStreetMap contributors",
            anchor="e", font=FONTS["micro"], fill="#A7AFA9",
        )

        north = width - 23
        self.create_rectangle(width - 32, 12, width - 14, 40, fill="#FFFFFF", outline=PALETTE["line"])
        self.create_text(north, 22, text="N", font=FONTS["micro_bold"], fill=PALETTE["ink"])
        self.create_polygon(north - 4, 34, north + 4, 34, north, 26, fill=PALETTE["accent"], outline="")

        text = self._readout_text()
        box_width = self._text_width(FONTS["mono"], text) + 18
        self._readout_box = self.create_rectangle(14, 12, 14 + box_width, 34, fill="#FFFFFF", outline=PALETTE["line"])
        self._readout_text_id = self.create_text(
            23, 23, text=text, anchor="w", font=FONTS["mono"], fill=PALETTE["ink_soft"]
        )

    # -- helpers ----------------------------------------------------------
    def _chip(
        self,
        x: float,
        y: float,
        text: str,
        sub: str = "",
        color: str | None = None,
        boxes: list[tuple[float, float, float, float]] | None = None,
        centered: bool = True,
    ) -> None:
        """Small white label, skipped when it would cover an existing one."""
        width = max(self._text_width(FONTS["micro_bold"], text), self._text_width(FONTS["micro"], sub))
        padding = 20 if color else 12
        box_w = width + padding
        box_h = 26 if sub else 16
        x0 = x - box_w / 2 if centered else x
        y0 = y - box_h / 2
        box = (x0, y0, x0 + box_w, y0 + box_h)
        if boxes is not None:
            for other in boxes:
                if not (box[2] < other[0] or box[0] > other[2] or box[3] < other[1] or box[1] > other[3]):
                    return
            boxes.append(box)
        self.create_rectangle(*box, fill="#FFFFFF", outline=PALETTE["line"])
        if color:
            self.create_rectangle(box[0], box[1], box[0] + 2.5, box[3], fill=color, outline="")
        self.create_text(box[0] + (10 if color else 6), box[1] + (7 if sub else 8), text=text, anchor="w", font=FONTS["micro_bold"], fill=PALETTE["ink"])
        if sub:
            self.create_text(box[0] + (10 if color else 6), box[1] + 18, text=sub, anchor="w", font=FONTS["micro"], fill=PALETTE["muted"])

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
        if self._readout_text_id is None:
            return
        text = self._readout_text()
        try:
            self.itemconfigure(self._readout_text_id, text=text)
            self.coords(self._readout_box, 14, 12, 14 + self._text_width(FONTS["mono"], text) + 18, 34)
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


def _short(value: float) -> str:
    return f"{value:,.0f}" if value >= 1000 else f"{value:g}"


MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _monthly_labels(rows: list[tuple[str, float]]) -> list[tuple[str, float]]:
    """Turn '2026-02' into 'Feb' so the chart labels stay short."""
    result: list[tuple[str, float]] = []
    for key, value in rows:
        try:
            result.append((MONTH_NAMES[int(key.split("-")[1]) - 1], value))
        except (IndexError, ValueError):
            result.append((key, value))
    return result


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    h = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2) ** 2
    )
    return 2 * radius * math.asin(math.sqrt(h))


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

SEED_VEHICLES = [
    ("NCB 1234", "Toyota", "Vios 1.5 G", "Sedan", 2021, 5, 1800, "rented", 14.6018, 120.9871, 48210, "Current rental — Ayala Triangle pickup."),
    ("ABC 4567", "Toyota", "Innova J", "AUV", 2020, 7, 2200, "available", 14.6096, 120.9910, 91022, "Serviced 2026-01-18. Ready for release."),
    ("XYZ 7788", "Mitsubishi", "Montero Sport", "SUV", 2022, 7, 3000, "rented", 14.5531, 121.0324, 33480, "High-clearance unit reserved for habagat deployments."),
    ("PLT 9012", "Ford", "Ranger XLT 4x4", "Pickup", 2021, 5, 2800, "available", 14.6320, 120.9820, 66740, "Flood-rated to 450 mm wading depth."),
    ("VNL 3344", "Hyundai", "H350 Shuttle", "Van", 2020, 12, 4500, "maintenance", 14.5800, 121.0000, 128900, "Brake pads replacement — expected back 2026-02-20."),
    ("MTC 5566", "Honda", "Click 125i", "Motorcycle", 2023, 2, 500, "available", 14.6100, 120.9800, 8430, "Courier deliveries around Sampaloc."),
    ("TRK 2211", "Isuzu", "NLR Rescue Truck", "Truck", 2019, 6, 5500, "available", 14.6500, 121.0500, 154320, "Equipped with rescue boat trailer hitch."),
    ("BTT 8899", "Rainbow", "Rescue Boat + Trailer", "Boat", 2021, 8, 6000, "rented", 14.5305, 121.0202, 0, "Deployed with Malabon DRRMO until Friday."),
    ("RDY 4455", "Toyota", "Hiace Commuter", "Van", 2022, 14, 3800, "available", 14.5900, 121.0600, 51260, "Shuttle contract — Ortigas loop."),
    ("FLR 6677", "Suzuki", "Ertiga GL", "AUV", 2023, 7, 2000, "maintenance", 14.5700, 120.9600, 19870, "Aircon compressor warranty claim."),
]

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
    ("Maria Isabel Santos", "+63 917 220 8841", "mi.santos@mail.com", "Drivers License", "N02-15-004218", "N02-15-004218"),
    ("Jonas Dela Cruz", "+63 928 447 1190", "jonas.dc@mail.com", "PhilID", "PH-3391-2287-4510", "N03-19-110377"),
    ("Angeline Reyes", "+63 906 118 7725", "a.reyes@firmmail.com", "Passport", "PH7702194", "N01-21-099523"),
    ("Malabon DRRMO", "+63 2 8280 4411", "drrmo@malabon.gov.ph", "Company ID", "MLB-DRR-0093", ""),
    ("Roberto Lim", "+63 919 550 3308", "rlim@logistics.ph", "UMID", "06-334-9921", "N04-17-022301"),
    ("Katrina Villanueva", "+63 995 771 2046", "kv.villanueva@mail.com", "Drivers License", "N01-22-088612", "N01-22-088612"),
]

SEED_BOOKINGS = [
    ("BK-2026-0041", 1, 1, "2026-02-10", "2026-02-13", "Ayala Triangle, Makati", "Tagaytay City", 3, 1800, 5400, 2000, "ongoing"),
    ("BK-2026-0042", 3, 3, "2026-02-12", "2026-02-15", "Bonifacio Global City", "Infanta, Quezon", 3, 3000, 9000, 4500, "ongoing"),
    ("BK-2026-0043", 8, 4, "2026-02-11", "2026-02-14", "Malabon City Hall", "Sto. Niño, Malabon", 3, 6000, 18000, 9000, "ongoing"),
    ("BK-2026-0044", 9, 5, "2026-02-18", "2026-02-20", "Ortigas Center", "Batangas Port", 2, 3800, 7600, 3800, "confirmed"),
    ("BK-2026-0045", 4, 2, "2026-02-21", "2026-02-24", "Quezon Avenue Station", "Baguio City", 3, 2800, 8400, 4000, "pending"),
    ("BK-2026-0046", 6, 6, "2026-02-16", "2026-02-16", "Sampaloc Depot", "Quiapo, Manila", 1, 500, 500, 0, "pending"),
    ("BK-2026-0038", 2, 3, "2026-02-04", "2026-02-08", "Sampaloc Depot", "Vigan, Ilocos Sur", 4, 2200, 8800, 2200, "completed"),
    ("BK-2026-0039", 7, 4, "2026-02-05", "2026-02-09", "Cainta Depot", "Manggahan Floodway", 4, 5500, 22000, 11000, "completed"),
    ("BK-2026-0036", 10, 5, "2026-01-30", "2026-02-02", "Sampaloc Depot", "Antipolo City", 3, 2000, 6000, 3000, "cancelled"),
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
    ("Vehicle inside severe flood zone", "NCB 1234 (Toyota Vios) is 0.4 km from España Boulevard Corridor. Recommend re-routing via Lacson Avenue.", "critical", "flood scan", 1, 1, "new", "admin", "2026-02-14 07:42"),
    ("Heavy rainfall advisory", "PAGASA orange rainfall warning over Metro Manila until 14:00. Expect curb-level ponding in low-lying barangays.", "warning", "manual", None, None, "new", "admin", "2026-02-14 06:15"),
    ("Maintenance overdue", "VNL 3344 (Hyundai H350) has exceeded its 5,000 km service interval by 1,240 km.", "warning", "system", 5, None, "acknowledged", "admin", "2026-02-13 16:20"),
    ("Boat deployment confirmed", "BTT 8899 released to Malabon DRRMO. Return inspection scheduled 2026-02-14 16:00.", "info", "manual", 8, None, "acknowledged", "j.dizon", "2026-02-11 08:20"),
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
        self.path = path or DATABASE_FILE
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
            connection.executescript(SCHEMA_SQL)
            connection.commit()
        self.seed_if_needed()

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
                "INSERT INTO customers (full_name, phone, email, id_type, id_number, license_number, created_at, updated_at)"
                " VALUES (?,?,?,?,?,?,?,?)",
                [(*row, now, now) for row in SEED_CUSTOMERS],
            )
            connection.executemany(
                "INSERT INTO flood_zones (name, barangay, risk_level, latitude, longitude, radius_km, is_active, notes, created_at, updated_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)",
                [(*row, now, now) for row in SEED_ZONES],
            )
            connection.executemany(
                "INSERT INTO bookings (booking_code, vehicle_id, customer_id, start_date, end_date, pickup_location, destination, rental_days, rate_per_day, total_amount, deposit, status, created_at, updated_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
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
            sql += " WHERE (full_name LIKE ? OR email LIKE ? OR phone LIKE ? OR id_type LIKE ?)"
            params.extend([like, like, like, like])
        return self.rows(sql + " ORDER BY full_name", params)

    def create_customer(
        self,
        full_name: str,
        phone: str,
        email: str,
        id_type: str,
        id_number: str,
        license_number: str,
    ) -> int:
        full_name, phone = full_name.strip(), phone.strip()
        if not full_name:
            raise ValueError("Enter the customer's name.")
        if not phone:
            raise ValueError("Enter a contact number.")
        if id_type not in ID_TYPES:
            raise ValueError("Select a valid ID type.")
        now = datetime.now().strftime(DATETIME_FORMAT)
        customer_id = self.execute(
            "INSERT INTO customers (full_name, phone, email, id_type, id_number, license_number, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (full_name, phone, email.strip(), id_type, id_number.strip(), license_number.strip(), now, now),
        )
        logging.getLogger(__name__).info("Created customer %s", customer_id)
        return customer_id

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
            sql += " AND (b.booking_code LIKE ? OR c.full_name LIKE ? OR v.model LIKE ? OR b.destination LIKE ?)"
            params.extend([like, like, like, like])
        return self.rows(sql + " ORDER BY b.start_date DESC", params)

    def create_booking(
        self,
        vehicle_id: int,
        customer_id: int,
        start_date: str,
        end_date: str,
        pickup_location: str,
        destination: str,
        deposit: float,
    ) -> int:
        try:
            start = datetime.strptime(start_date.strip(), DATE_FORMAT).date()
            end = datetime.strptime(end_date.strip(), DATE_FORMAT).date()
        except ValueError as error:
            raise ValueError("Enter valid dates in YYYY-MM-DD format.") from error
        if end < start:
            raise ValueError("The return date cannot be before the pickup date.")
        if not math.isfinite(deposit) or deposit < 0:
            raise ValueError("Deposit must be a non-negative amount.")

        rental_days = max(1, (end - start).days)
        effective_end = max(end, start + timedelta(days=1))
        now = datetime.now()
        stamp = now.strftime(DATETIME_FORMAT)
        prefix = f"BK-{now:%Y}-"
        with self.connect() as connection:
            vehicle = connection.execute(
                "SELECT rate_per_day, status FROM vehicles WHERE id = ?", (vehicle_id,)
            ).fetchone()
            if vehicle is None:
                raise ValueError("Select a vehicle that still exists.")
            if vehicle["status"] == "maintenance":
                raise ValueError("A vehicle in maintenance cannot be booked.")
            if connection.execute("SELECT id FROM customers WHERE id = ?", (customer_id,)).fetchone() is None:
                raise ValueError("Select a customer that still exists.")

            existing = connection.execute(
                "SELECT start_date, end_date FROM bookings"
                " WHERE vehicle_id = ? AND status IN ('pending', 'confirmed', 'ongoing')",
                (vehicle_id,),
            ).fetchall()
            for booking in existing:
                occupied_start = datetime.strptime(booking["start_date"], DATE_FORMAT).date()
                occupied_end = datetime.strptime(booking["end_date"], DATE_FORMAT).date()
                occupied_end = max(occupied_end, occupied_start + timedelta(days=1))
                if occupied_start < effective_end and occupied_end > start:
                    raise ValueError("That vehicle already has a booking during these dates.")

            codes = connection.execute(
                "SELECT booking_code FROM bookings WHERE booking_code LIKE ?", (f"{prefix}%",)
            ).fetchall()
            sequence = max(
                (
                    int(code["booking_code"][len(prefix):])
                    for code in codes
                    if code["booking_code"][len(prefix):].isdigit()
                ),
                default=0,
            ) + 1
            booking_code = f"{prefix}{sequence:04d}"
            connection.execute(
                "INSERT INTO bookings (booking_code, vehicle_id, customer_id, start_date, end_date,"
                " pickup_location, destination, rental_days, rate_per_day, total_amount, deposit, status,"
                " created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,'pending',?,?)",
                (
                    booking_code,
                    vehicle_id,
                    customer_id,
                    start.strftime(DATE_FORMAT),
                    end.strftime(DATE_FORMAT),
                    pickup_location.strip(),
                    destination.strip(),
                    rental_days,
                    vehicle["rate_per_day"],
                    vehicle["rate_per_day"] * rental_days,
                    deposit,
                    stamp,
                    stamp,
                ),
            )
            booking_id = int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])
            connection.commit()
        logging.getLogger(__name__).info("Created booking %s", booking_code)
        return booking_id

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
    def nearest_zone(self, lat: float, lon: float) -> tuple[dict[str, Any], float] | None:
        best: tuple[dict[str, Any], float] | None = None
        for zone in self.zones():
            if not zone["is_active"]:
                continue
            kilometres = distance_km(lat, lon, zone["latitude"], zone["longitude"])
            if best is None or kilometres < best[1]:
                best = (zone, kilometres)
        return best

    def exposure(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for vehicle in self.vehicles():
            found = self.nearest_zone(vehicle["latitude"], vehicle["longitude"])
            if not found:
                continue
            zone, kilometres = found
            rows.append({**vehicle, "zone_name": zone["name"], "zone_risk": zone["risk_level"], "distance_km": kilometres, "inside": kilometres <= zone["radius_km"]})
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
        for item in self.exposure():
            if not item["inside"]:
                continue
            title = f"Flood scan: {item['plate_number']} exposed"
            if self.row("SELECT id FROM alerts WHERE title = ? AND status = 'new'", (title,)):
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
                    "critical" if item["zone_risk"] == "severe" else "warning",
                    "flood scan",
                    item["id"],
                    username,
                    now,
                    now,
                ),
            )
            created.append(title)
        return created

    def set_alert_status(self, alert_id: int, status: str) -> None:
        now = datetime.now().strftime(DATETIME_FORMAT)
        self.execute("UPDATE alerts SET status = ?, updated_at = ? WHERE id = ?", (status, now, alert_id))

    def set_zone_active(self, zone_id: int, active: bool) -> None:
        now = datetime.now().strftime(DATETIME_FORMAT)
        self.execute("UPDATE flood_zones SET is_active = ?, updated_at = ? WHERE id = ?", (1 if active else 0, now, zone_id))

    def backup(self, destination: str) -> Path:
        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            backup_connection = sqlite3.connect(str(target))
            connection.backup(backup_connection)
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
            return ["Zone", "Barangay", "Risk", "Radius km", "Active", "Exposed units"], [
                [row["name"], row["barangay"] or "", row["risk_level"], f"{row['radius_km']:.1f}", "yes" if row["is_active"] else "no", sum(1 for item in self.exposure() if item["zone_name"] == row["name"] and item["inside"])]
                for row in self.zones()
            ]
        return ["When", "Title", "Severity", "Source", "Status"], [
            [row["created_at"], row["title"], row["severity"], row["source"], row["status"]] for row in self.alerts()
        ]


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------


class Page(ttk.Frame):
    """Base page: header, body, and a refresh hook."""

    key = "dashboard"
    title = "Dashboard"
    subtitle = ""

    def __init__(self, master: tk.Widget, app: "MainWindow") -> None:
        super().__init__(master, style="Page.TFrame", padding=(24, 16))
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
        heading(self, self.title, self.subtitle)
        self.stat_row = ttk.Frame(self, style="Page.TFrame")
        self.stat_row.pack(fill="x", pady=(0, 12))
        self.stats = [
            Stat(self.stat_row, "Vehicles", tone="accent"),
            Stat(self.stat_row, "Active bookings", tone="info"),
            Stat(self.stat_row, "Booking value", tone="ok"),
            Stat(self.stat_row, "Open alerts", tone="danger"),
        ]
        for index, tile in enumerate(self.stats):
            self.stat_row.columnconfigure(index, weight=1, uniform="tiles")
            tile.grid(row=0, column=index, sticky="nsew", padx=(0 if index == 0 else 10, 0))

        _wrap, charts = grid_row(self, [lambda master: Card(master), lambda master: Card(master)], weights=[4, 3])
        left, right = charts
        card_title(left, "Collections by month", "Net cash movement recorded in each month")
        self.chart = Bars(left.body, height=150)
        self.chart.pack(fill="x", pady=(14, 2))

        card_title(right, "Flood-risk distribution", "Units grouped by the risk of their nearest active zone")
        self.bars: dict[str, Bar] = {}
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
            self.bars[f"{level}_label"] = label  # type: ignore[assignment]

        _wrap, pair = grid_row(self, [lambda master: Card(master), lambda master: Card(master)], weights=[11, 9])
        map_card, exposure_card = pair
        card_title(map_card, "Fleet positions", "Live positions with active flood zones overlaid")
        self.map = MapCanvas(
            map_card.body, self.store, height=290, show_grid=False, legend=False, show_labels=True,
            border=False, feed=self.app.feed,
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

    def refresh(self) -> None:
        stats = self.store.dashboard()
        self.stats[0].set(str(stats["vehicles"]), f"{stats['available']} available · {stats['rented']} rented · {stats['maintenance']} in shop")
        self.stats[1].set(str(stats["bookings"]), f"{stats['ongoing']} on the road")
        self.stats[2].set(money(stats["value"]), f"{stats['bookings']} booking records")
        self.stats[3].set(str(stats["open_alerts"]).zfill(2), "Unacknowledged notices")
        self.chart.set(_monthly_labels(self.store.collections_by_month()))
        total_units = max(stats["vehicles"], 1)
        for level, count in self.store.risk_distribution():
            self.bars[level].set(count / total_units)
            self.bars[f"{level}_label"].configure(text=str(count))  # type: ignore[union-attr]
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
            [lambda parent: ttk.Button(parent, text="Export CSV", style="Secondary.TButton", command=self.export)],
        )
        bar = ttk.Frame(self, style="Page.TFrame")
        bar.pack(fill="x", pady=(0, 12))
        entry = ttk.Entry(bar, textvariable=self.search, width=32, style="Field.TEntry")
        entry.pack(side="left")
        entry.bind("<KeyRelease>", lambda _event: self.refresh())
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
        self.refresh()

    def export(self) -> None:
        columns, rows = self.store.report("vehicles")
        export_csv(self, "vehicles", columns, rows)

    def refresh(self) -> None:
        rows = self.store.vehicles(self.status.get(), self.search.get())
        prepared = []
        for row in rows:
            found = self.store.nearest_zone(row["latitude"], row["longitude"])
            prepared.append(
                {
                    **row,
                    "unit": f"{row['brand']} {row['model']}  ·  {row['plate_number']}",
                    "rate_per_day": money(row["rate_per_day"]),
                    "distance": f"{found[1]:.2f} km" if found else "—",
                }
            )
        self.table.set_rows(prepared, tag_of=lambda row: {"available": "ok", "rented": "info", "maintenance": "warn"}.get(row["status"]))
        self.count.configure(text=f"{len(rows)} of {self.store.dashboard()['vehicles']} units")

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
            ("Latitude", f"{vehicle['latitude']:.4f}"),
            ("Longitude", f"{vehicle['longitude']:.4f}"),
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
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.canvas.bind("<Button-4>", lambda _event: self.canvas.yview_scroll(-1, "units"))
        self.canvas.bind("<Button-5>", lambda _event: self.canvas.yview_scroll(1, "units"))

    def _on_wheel(self, event: tk.Event) -> None:
        """Windows and macOS report wheel distance differently."""
        if abs(event.delta) >= 120:
            steps = -int(event.delta / 120)
        else:
            steps = -1 if event.delta > 0 else 1
        self.canvas.yview_scroll(steps, "units")


def fact(parent: tk.Widget, label: str, value: str) -> ttk.Frame:
    box = ttk.Frame(parent, style="Sunken.TFrame", padding=(10, 8))
    ttk.Label(box, text=label.upper(), style="MicroSunken.TLabel").pack(anchor="w")
    ttk.Label(box, text=value, style="BodySunken.TLabel").pack(anchor="w", pady=(1, 0))
    return box


class ListPage(Page):
    """Table page: search, optional filter, counter and a data table."""

    columns: list[tuple[str, str, int, str]] = []
    filters: list[str] = []
    report_key = ""

    def build(self) -> None:
        self.search = tk.StringVar()
        self.filter = tk.StringVar(value=self.filters[0] if self.filters else "all")
        heading(self, self.title, self.subtitle, self.actions())
        for widget in self.prefix():
            widget.pack(fill="x", pady=(0, 12))
        bar = ttk.Frame(self, style="Page.TFrame")
        bar.pack(fill="x", pady=(0, 12))
        entry = ttk.Entry(bar, textvariable=self.search, width=34, style="Field.TEntry")
        entry.pack(side="left")
        entry.bind("<KeyRelease>", lambda _event: self.refresh())
        if self.filters:
            box = ttk.Combobox(
                bar, textvariable=self.filter, values=self.filters, width=18, state="readonly", style="Field.TCombobox"
            )
            box.pack(side="left", padx=(8, 0))
            box.bind("<<ComboboxSelected>>", lambda _event: self.refresh())
        self.counter = ttk.Label(bar, text="", style="Muted.TLabel")
        self.counter.pack(side="right")
        holder = Card(self)
        self.table = Table(holder.body, self.columns)
        self.table.pack(fill="both", expand=True)
        self.refresh()

    def actions(self) -> list[Callable[[tk.Widget], tk.Widget]]:
        return []

    def prefix(self) -> list[tk.Widget]:
        return []

    def fetch(self) -> list[dict[str, Any]]:
        return []

    def tag_of(self, _row: dict[str, Any]) -> str | None:
        return None

    def refresh(self) -> None:
        rows = self.fetch()
        self.table.set_rows(rows, tag_of=self.tag_of)
        self.counter.configure(text=f"{len(rows)} records")


class CustomersPage(ListPage):
    key = "customers"
    title = "Customers"
    subtitle = "Renter records, identification and contact details held locally"
    columns = [
        ("full_name", "Customer", 190, "w"),
        ("phone", "Contact number", 150, "w"),
        ("email", "E-mail", 190, "w"),
        ("id_type", "ID type", 130, "w"),
        ("id_number", "ID number", 150, "w"),
    ]
    report_key = "customers"

    def actions(self) -> list[Callable[[tk.Widget], tk.Widget]]:
        return [
            lambda parent: ttk.Button(parent, text="Create customer", style="Primary.TButton", command=self.create_customer),
            lambda parent: ttk.Button(parent, text="Export CSV", style="Secondary.TButton", command=self.export),
        ]

    def create_customer(self) -> None:
        dialog = tk.Toplevel(self)
        dialog.title("Create customer")
        dialog.transient(self.winfo_toplevel())
        dialog.resizable(False, False)

        card = Card(dialog, padding=(22, 18))
        card.pack(fill="both", expand=True, padx=16, pady=16)
        ttk.Label(card.body, text="New customer", style="TitleCard.TLabel").pack(anchor="w")
        ttk.Label(
            card.body,
            text="Add renter contact and identification details.",
            style="MutedCard.TLabel",
        ).pack(anchor="w", pady=(4, 14))

        fields = ttk.Frame(card.body, style="Card.TFrame")
        fields.pack(fill="x")
        name = Field(fields, "Full name")
        phone = Field(fields, "Contact number")
        email = Field(fields, "E-mail")
        id_type = Field(fields, "ID type", ID_TYPES[0], choices=ID_TYPES)
        id_number = Field(fields, "ID number")
        license_number = Field(fields, "Driver's licence number")
        for index, field in enumerate((name, phone, email, id_type, id_number, license_number)):
            field.grid(row=index // 2, column=index % 2, sticky="nsew", padx=(0 if index % 2 == 0 else 12, 0), pady=(0, 12))
        fields.columnconfigure(0, weight=1)
        fields.columnconfigure(1, weight=1)

        buttons = ttk.Frame(card.body, style="Card.TFrame")
        buttons.pack(fill="x", pady=(4, 0))
        ttk.Button(buttons, text="Cancel", style="Ghost.TButton", command=dialog.destroy).pack(side="right")

        def save() -> None:
            try:
                self.store.create_customer(
                    name.get(),
                    phone.get(),
                    email.get(),
                    id_type.get(),
                    id_number.get(),
                    license_number.get(),
                )
            except (ValueError, RuntimeError) as error:
                logging.getLogger(__name__).exception("Could not create customer")
                messagebox.showerror(APP_NAME, str(error), parent=dialog)
                return
            dialog.destroy()
            self.refresh()
            messagebox.showinfo(APP_NAME, "Customer created.", parent=self)

        ttk.Button(buttons, text="Create customer", style="Primary.TButton", command=save).pack(side="right", padx=(0, 8))
        dialog.bind("<Return>", lambda _event: save())
        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        dialog.update_idletasks()
        x = max(0, (dialog.winfo_screenwidth() - dialog.winfo_reqwidth()) // 2)
        y = max(0, (dialog.winfo_screenheight() - dialog.winfo_reqheight()) // 3)
        dialog.geometry(f"+{x}+{y}")
        dialog.grab_set()
        dialog.wait_window()

    def export(self) -> None:
        columns, rows = self.store.report("customers")
        export_csv(self, "customers", columns, rows)

    def fetch(self) -> list[dict[str, Any]]:
        return self.store.customers(self.search.get())

    def tag_of(self, row: dict[str, Any]) -> str | None:
        return "info" if row.get("id_type") == "Company ID" else None


class BookingsPage(ListPage):
    key = "bookings"
    title = "Bookings"
    subtitle = "Rental periods, destinations, deposits and running totals"
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
    report_key = "bookings"

    def actions(self) -> list[Callable[[tk.Widget], tk.Widget]]:
        return [
            lambda parent: ttk.Button(parent, text="Create booking", style="Primary.TButton", command=self.create_booking),
            lambda parent: ttk.Button(parent, text="Export CSV", style="Secondary.TButton", command=self.export),
        ]

    def create_booking(self) -> None:
        customers = self.store.customers()
        vehicles = [vehicle for vehicle in self.store.vehicles() if vehicle["status"] != "maintenance"]
        if not customers:
            messagebox.showwarning(APP_NAME, "Create a customer before creating a booking.", parent=self)
            return
        if not vehicles:
            messagebox.showwarning(APP_NAME, "Add a vehicle before creating a booking.", parent=self)
            return

        customer_labels = {
            f"{customer['full_name']} · {customer['phone']}": int(customer["id"]) for customer in customers
        }
        vehicle_labels = {
            f"{vehicle['plate_number']} · {vehicle['brand']} {vehicle['model']}": int(vehicle["id"])
            for vehicle in vehicles
        }
        today = datetime.now().date()
        dialog = tk.Toplevel(self)
        dialog.title("Create booking")
        dialog.transient(self.winfo_toplevel())
        dialog.resizable(False, False)

        card = Card(dialog, padding=(22, 18))
        card.pack(fill="both", expand=True, padx=16, pady=16)
        ttk.Label(card.body, text="New booking", style="TitleCard.TLabel").pack(anchor="w")
        ttk.Label(
            card.body,
            text="Choose a renter, vehicle and rental period. The total uses the vehicle's daily rate.",
            style="MutedCard.TLabel",
            wraplength=520,
        ).pack(anchor="w", pady=(4, 14))

        fields = ttk.Frame(card.body, style="Card.TFrame")
        fields.pack(fill="x")
        customer = Field(fields, "Customer", next(iter(customer_labels)), choices=list(customer_labels))
        vehicle = Field(fields, "Vehicle", next(iter(vehicle_labels)), choices=list(vehicle_labels))
        start_date = Field(fields, "Pickup date (YYYY-MM-DD)", today.strftime(DATE_FORMAT))
        end_date = Field(fields, "Return date (YYYY-MM-DD)", (today + timedelta(days=1)).strftime(DATE_FORMAT))
        pickup = Field(fields, "Pickup location")
        destination = Field(fields, "Destination")
        deposit = Field(fields, "Deposit", "0")
        for index, field in enumerate((customer, vehicle, start_date, end_date, pickup, destination, deposit)):
            field.grid(row=index // 2, column=index % 2, sticky="nsew", padx=(0 if index % 2 == 0 else 12, 0), pady=(0, 12))
        fields.columnconfigure(0, weight=1)
        fields.columnconfigure(1, weight=1)

        buttons = ttk.Frame(card.body, style="Card.TFrame")
        buttons.pack(fill="x", pady=(4, 0))
        ttk.Button(buttons, text="Cancel", style="Ghost.TButton", command=dialog.destroy).pack(side="right")

        def save() -> None:
            try:
                vehicle_id = vehicle_labels[vehicle.get()]
                customer_id = customer_labels[customer.get()]
                deposit_amount = float(deposit.get() or "0")
                self.store.create_booking(
                    vehicle_id,
                    customer_id,
                    start_date.get(),
                    end_date.get(),
                    pickup.get(),
                    destination.get(),
                    deposit_amount,
                )
            except (KeyError, ValueError, RuntimeError) as error:
                logging.getLogger(__name__).exception("Could not create booking")
                messagebox.showerror(APP_NAME, str(error) or "Select a valid customer and vehicle.", parent=dialog)
                return
            dialog.destroy()
            self.refresh()
            messagebox.showinfo(APP_NAME, "Booking created.", parent=self)

        ttk.Button(buttons, text="Create booking", style="Primary.TButton", command=save).pack(side="right", padx=(0, 8))
        dialog.bind("<Return>", lambda _event: save())
        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        dialog.update_idletasks()
        x = max(0, (dialog.winfo_screenwidth() - dialog.winfo_reqwidth()) // 2)
        y = max(0, (dialog.winfo_screenheight() - dialog.winfo_reqheight()) // 3)
        dialog.geometry(f"+{x}+{y}")
        dialog.grab_set()
        dialog.wait_window()

    def export(self) -> None:
        columns, rows = self.store.report("bookings")
        export_csv(self, "bookings", columns, rows)

    def fetch(self) -> list[dict[str, Any]]:
        rows = self.store.bookings(self.filter.get(), self.search.get())
        return [
            {
                **row,
                "unit": f"{row['brand']} {row['model']}",
                "deposit": money(row["deposit"]),
                "total_amount": money(row["total_amount"]),
            }
            for row in rows
        ]

    def tag_of(self, row: dict[str, Any]) -> str | None:
        return {"ongoing": "info", "confirmed": "info", "pending": "warn", "completed": "ok", "cancelled": "danger"}.get(row["status"])

    def refresh(self) -> None:
        super().refresh()
        rows = self.store.bookings(self.filter.get(), self.search.get())
        total = sum(row["total_amount"] for row in rows if row["status"] != "cancelled")
        self.counter.configure(text=f"{len(rows)} bookings · {money(total)}")


class TransactionsPage(ListPage):
    key = "transactions"
    title = "Transactions"
    subtitle = "Payments, deposits and refunds recorded against each booking"
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
    report_key = "transactions"

    def actions(self) -> list[Callable[[tk.Widget], tk.Widget]]:
        return [lambda parent: ttk.Button(parent, text="Record payment", style="Primary.TButton")]

    def prefix(self) -> list[tk.Widget]:
        wrap = ttk.Frame(self, style="Page.TFrame")
        self.collected = Stat(wrap, "Collected", tone="ok")
        self.refunded = Stat(wrap, "Refunded", tone="danger")
        self.net = Stat(wrap, "Net cash", tone="accent")
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
        rows = self.store.transactions()
        collected = sum(row["amount"] for row in rows if row["entry_type"] != "refund")
        refunded = sum(row["amount"] for row in rows if row["entry_type"] == "refund")
        self.collected.set(money(collected), f"{len(rows)} entries")
        self.refunded.set(money(refunded), "Returned to renters")
        self.net.set(money(collected - refunded), "After refunds")


class UsersPage(ListPage):
    key = "users"
    title = "Users"
    subtitle = "Accounts, roles and password policy — hashes only, never plain text"
    columns = [
        ("full_name", "Account", 190, "w"),
        ("username", "Username", 130, "w"),
        ("role", "Role", 100, "w"),
        ("last_seen", "Last seen", 140, "w"),
        ("state", "State", 100, "w"),
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


class GpsMapPage(Page):
    key = "gps"
    title = "GPS map"
    subtitle = "Fleet positions with flood zones overlaid — drag to pan, scroll to zoom"

    def build(self) -> None:
        self.selected: dict[str, Any] | None = None
        heading(
            self,
            self.title,
            self.subtitle,
            [
                lambda parent: ttk.Button(parent, text="Fit fleet", style="Secondary.TButton", command=lambda: self.map.fit_fleet()),
                lambda parent: ttk.Button(parent, text="Reset view", style="Secondary.TButton", command=lambda: self.map.reset()),
                lambda parent: ttk.Button(parent, text="Zoom in", style="Ghost.TButton", command=lambda: self.map.zoom_in()),
                lambda parent: ttk.Button(parent, text="Zoom out", style="Ghost.TButton", command=lambda: self.map.zoom_out()),
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
            map_card.body, self.store, height=470, on_select=self.select, border=False, feed=self.app.feed
        )
        self.map.pack(fill="both", expand=True, pady=(12, 0))
        self.after_idle(self.map.fit_fleet)

        controls = ttk.Frame(map_card.body, style="Card.TFrame")
        controls.pack(fill="x", pady=(10, 0))
        self.play_button = ttk.Button(
            controls, text="Pause feed", style="Primary.TButton", command=self.toggle_feed
        )
        self.play_button.pack(side="left")
        self.speed_var = tk.StringVar(value="4×")
        ttk.Label(controls, text="SPEED", style="MicroCard.TLabel").pack(side="left", padx=(14, 4))
        speed_box = ttk.Combobox(
            controls, textvariable=self.speed_var, values=("1×", "4×", "16×", "60×"),
            width=5, state="readonly", style="Field.TCombobox",
        )
        speed_box.pack(side="left")
        speed_box.bind("<<ComboboxSelected>>", lambda _event: self.set_feed_speed())
        self.live_var = tk.StringVar(value="Live · 10 units")
        ttk.Label(controls, textvariable=self.live_var, style="MutedCard.TLabel").pack(side="right")
        self.bind("<Destroy>", lambda _event: self._stop_live_poll())
        self._poll_live()

        self.show_vehicles = tk.BooleanVar(value=True)
        self.show_zones = tk.BooleanVar(value=True)
        self.show_labels = tk.BooleanVar(value=True)
        self.show_grid = tk.BooleanVar(value=True)
        options = ttk.Frame(map_card.body, style="Card.TFrame")
        options.pack(fill="x", pady=(10, 0))
        for label, variable in (
            ("Vehicles", self.show_vehicles),
            ("Flood zones", self.show_zones),
            ("Place labels", self.show_labels),
            ("Lat/lon grid", self.show_grid),
        ):
            ttk.Checkbutton(
                options, text=label, variable=variable, style="Switch.TCheckbutton", command=self.apply_layers
            ).pack(side="left", padx=(0, 16))

        card_title(side_card, "Fleet list", "Select a unit to focus the map")
        self.listing = ttk.Frame(side_card.body, style="Card.TFrame")
        self.listing.pack(fill="x", pady=(12, 0))
        self.detail = ttk.Frame(side_card.body, style="Card.TFrame")
        self.detail.pack(fill="x", pady=(12, 0))
        self.refresh()

    def toggle_feed(self) -> None:
        running = self.app.feed.toggle()
        self.play_button.configure(text="Pause feed" if running else "Resume feed")
        self._update_live_status()

    def set_feed_speed(self) -> None:
        try:
            factor = float(self.speed_var.get().rstrip("×xX"))
        except ValueError:
            factor = 1.0
        self.app.feed.set_speed(factor)
        self._update_live_status()

    def _update_live_status(self) -> None:
        self.live_var.set(self.app.feed.status())

    def _poll_live(self) -> None:
        self._live_job = self.after(1200, self._poll_live_tick)

    def _poll_live_tick(self) -> None:
        if not self.winfo_exists():
            return
        self._update_live_status()
        if self.selected is not None:
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

    def apply_layers(self) -> None:
        self.map.show_vehicles = self.show_vehicles.get()
        self.map.show_zones = self.show_zones.get()
        self.map.show_labels = self.show_labels.get()
        self.map.show_grid = self.show_grid.get()
        self.map.draw()

    def select(self, vehicle_id: int) -> None:
        vehicle = self.store.row("SELECT * FROM vehicles WHERE id = ?", (vehicle_id,))
        if not vehicle:
            return
        self.selected = vehicle
        self.map.focus(vehicle_id)
        self.render_detail()

    def render_detail(self) -> None:
        for child in self.detail.winfo_children():
            child.destroy()
        vehicle = self.selected
        if not vehicle:
            return
        found = self.store.nearest_zone(vehicle["latitude"], vehicle["longitude"])
        ttk.Label(self.detail, text=f"{vehicle['brand']} {vehicle['model']}", style="TitleCard.TLabel").pack(anchor="w")
        ttk.Label(self.detail, text=f"{vehicle['plate_number']} · {vehicle['status']}", style="MutedCard.TLabel").pack(anchor="w", pady=(2, 8))
        for label, value in (
            ("Latitude", f"{vehicle['latitude']:.4f}"),
            ("Longitude", f"{vehicle['longitude']:.4f}"),
            ("Heading", "NNE 24°"),
            ("Last fix", "07:56"),
        ):
            row = ttk.Frame(self.detail, style="Card.TFrame")
            row.pack(fill="x", pady=2)
            ttk.Label(row, text=label, style="MutedCard.TLabel").pack(side="left")
            ttk.Label(row, text=value, style="BodyCard.TLabel").pack(side="right")
        if found:
            zone, kilometres = found
            ttk.Label(self.detail, text="NEAREST ZONE", style="MicroCard.TLabel").pack(anchor="w", pady=(12, 0))
            ttk.Label(self.detail, text=zone["name"], style="TitleCard.TLabel").pack(anchor="w")
            ttk.Label(
                self.detail,
                text=f"{kilometres:.2f} km · radius {zone['radius_km']:.1f} km · {zone['risk_level']}",
                style="MutedCard.TLabel",
            ).pack(anchor="w")

    def refresh(self) -> None:
        for child in self.listing.winfo_children():
            child.destroy()
        for vehicle in self.store.vehicles():
            found = self.store.nearest_zone(vehicle["latitude"], vehicle["longitude"])
            button = ttk.Button(
                self.listing,
                text=f"  {vehicle['plate_number']}   {vehicle['model']}"
                + (f"   {found[1]:.1f} km" if found else ""),
                style="Side.TButton",
                command=lambda vehicle_id=vehicle["id"]: self.select(vehicle_id),
            )
            button.pack(fill="x", pady=1)
        self.map.reload()
        if self.selected:
            self.render_detail()


class FloodZonesPage(Page):
    key = "zones"
    title = "Flood zones"
    subtitle = "Monitored areas, severity scores and the units exposed to each"

    def build(self) -> None:
        heading(
            self,
            self.title,
            self.subtitle,
            [lambda parent: ttk.Button(parent, text="Add zone", style="Primary.TButton")],
        )
        _wrap, pair = grid_row(self, [lambda master: ScrollColumn(master, height=520), lambda master: Card(master)], weights=[13, 11], gap=14)
        _wrap.pack_configure(expand=True)
        self.column, map_card = pair
        card_title(map_card, "Zone map", "Ring size reflects the monitored radius")
        self.map = MapCanvas(
            map_card.body, self.store, height=330, on_select=None, show_grid=False, legend=False,
            border=False, feed=self.app.feed,
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
            ttk.Label(
                footer,
                text=f"{zone['latitude']:.3f}, {zone['longitude']:.3f}",
                style="MicroCard.TLabel",
            ).pack(side="right")
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
            [lambda parent: ttk.Button(parent, text="Run flood risk scan", style="Primary.TButton", command=self.scan)],
        )
        wrap = ttk.Frame(self, style="Page.TFrame")
        wrap.pack(fill="x", pady=(0, 12))
        self.tiles = [Stat(wrap, "Unread", tone="accent"), Stat(wrap, "Acknowledged", tone="warn"), Stat(wrap, "Resolved", tone="ok"), Stat(wrap, "Critical open", tone="danger")]
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
                    ttk.Button(
                        buttons, text="Acknowledge", style="Secondary.TButton",
                        command=lambda alert_id=alert["id"]: self.set_status(alert_id, "acknowledged"),
                    ).pack(side="left", padx=(6, 0))
                ttk.Button(
                    buttons, text="Resolve", style="Quiet.TButton",
                    command=lambda alert_id=alert["id"]: self.set_status(alert_id, "resolved"),
                ).pack(side="left", padx=(6, 0))
        counts = {status: 0 for status in ALERT_STATUSES}
        for alert in self.store.alerts():
            counts[alert["status"]] = counts.get(alert["status"], 0) + 1
        critical = sum(1 for alert in self.store.alerts() if alert["severity"] == "critical" and alert["status"] != "resolved")
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
            ttk.Button(
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
                lambda parent: ttk.Button(parent, text="Backup now", style="Secondary.TButton", command=self.backup),
                lambda parent: ttk.Button(parent, text="Save changes", style="Primary.TButton", command=self.save),
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


# ---------------------------------------------------------------------------
# Windows
# ---------------------------------------------------------------------------


class LoginWindow(tk.Toplevel):
    """Centred sign-in card; the whole window is the card."""

    def __init__(self, master: tk.Tk, store: Store) -> None:
        super().__init__(master)
        self.store = store
        self.user: dict[str, Any] | None = None
        self.title(f"{APP_NAME} — Sign in")
        self.configure(background=PALETTE["bg"], padx=22, pady=22)
        self.resizable(False, False)

        card = ttk.Frame(self, style="CardBorder.TFrame", padding=1)
        card.pack(fill="both", expand=True)
        body = ttk.Frame(card, style="Card.TFrame", padding=(38, 32))
        body.pack(fill="both", expand=True)

        mark = tk.Canvas(body, width=38, height=38, background=PALETTE["surface"], highlightthickness=0, bd=0)
        mark.create_oval(0, 0, 38, 38, fill=PALETTE["accent_soft"], outline="")
        mark.create_text(19, 20, text="◈", font=FONTS["h2"], fill=PALETTE["accent"])
        mark.pack(anchor="w")
        ttk.Label(body, text=APP_NAME, style="TitleCard.TLabel").pack(anchor="w", pady=(14, 0))
        ttk.Label(
            body,
            text="Rental operations with flood-risk monitoring for Metro Manila.",
            style="MutedCard.TLabel",
            wraplength=300,
            justify="left",
        ).pack(anchor="w", pady=(4, 0))

        self.username = tk.StringVar(value=DEFAULT_ADMIN_USERNAME)
        self.password = tk.StringVar(value=DEFAULT_ADMIN_PASSWORD)
        self.error = tk.StringVar(value="")
        ttk.Label(body, text="USERNAME", style="MicroCard.TLabel").pack(anchor="w", pady=(22, 0))
        ttk.Entry(body, textvariable=self.username, width=32, style="Field.TEntry").pack(fill="x", pady=(5, 0))
        ttk.Label(body, text="PASSWORD", style="MicroCard.TLabel").pack(anchor="w", pady=(14, 0))
        self.password_entry = ttk.Entry(body, textvariable=self.password, width=32, style="Field.TEntry", show="•")
        self.password_entry.pack(fill="x", pady=(5, 0))
        ttk.Label(body, textvariable=self.error, style="DangerCard.TLabel", wraplength=300, justify="left").pack(anchor="w", pady=(12, 0))
        ttk.Button(body, text="Sign in", style="Primary.TButton", command=self.sign_in).pack(fill="x", pady=(4, 0))
        ttk.Label(
            body,
            text=f"Default account: {DEFAULT_ADMIN_USERNAME} / {DEFAULT_ADMIN_PASSWORD}\nData folder: {DATA_ROOT}",
            style="MicroCard.TLabel",
            justify="left",
        ).pack(anchor="w", pady=(18, 0))

        self.bind("<Return>", lambda _event: self.sign_in())
        self.protocol("WM_DELETE_WINDOW", self.close)
        self._centre()

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
        width, height = max(430, self.winfo_reqwidth()), max(560, self.winfo_reqheight())
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
        self.buttons: dict[str, ttk.Button] = {}
        self.sign_out = False
        self._closing = threading.Event()
        self._online: bool | None = None

        master.title(f"{APP_NAME} — {user['full_name']}")
        master.geometry("1200x780")
        master.minsize(1020, 660)
        master.protocol("WM_DELETE_WINDOW", self.close)
        self.feed = TrackingFeed(store, master)
        self._build_menu(master)
        self._build_status_bar()
        self._build_sidebar()

        self.container = ttk.Frame(self, style="Page.TFrame")
        self.container.pack(side="left", fill="both", expand=True)
        self.page_canvas = tk.Canvas(
            self.container,
            background=PALETTE["bg"],
            highlightthickness=0,
            bd=0,
        )
        self.page_scroll = ttk.Scrollbar(
            self.container,
            orient="vertical",
            command=self.page_canvas.yview,
            style="Thin.TScrollbar",
        )
        self.page_canvas.configure(yscrollcommand=self.page_scroll.set)
        self.page_canvas.pack(side="left", fill="both", expand=True)
        self.page_scroll.pack(side="right", fill="y")
        self.page_content = ttk.Frame(self.page_canvas, style="Page.TFrame")
        self._page_window = self.page_canvas.create_window((0, 0), window=self.page_content, anchor="nw")
        self.page_content.bind(
            "<Configure>",
            lambda _event: self._resize_page_window(),
        )
        self.page_canvas.bind(
            "<Configure>",
            lambda event: self._resize_page_window(event.width, event.height),
        )
        self.show_page("dashboard")
        self.pack(fill="both", expand=True)
        self.feed.start()
        self._start_connectivity_check()

    # -- chrome -----------------------------------------------------------
    def _build_menu(self, master: tk.Tk) -> None:
        menubar = tk.Menu(master, activebackground=PALETTE["sunken"], activeforeground=PALETTE["ink"], bd=0)
        file_menu = tk.Menu(menubar, tearoff=0, activebackground=PALETTE["sunken"], activeforeground=PALETTE["ink"])
        file_menu.add_command(label="Backup database…", command=self._backup)
        file_menu.add_separator()
        file_menu.add_command(label="Sign out", command=self._sign_out)
        file_menu.add_command(label="Exit", command=self.close)
        menubar.add_cascade(label="File", menu=file_menu)
        help_menu = tk.Menu(menubar, tearoff=0, activebackground=PALETTE["sunken"], activeforeground=PALETTE["ink"])
        help_menu.add_command(label=f"About {APP_NAME}", command=self._about)
        help_menu.add_command(label="Run a smoke test", command=lambda: self.show_page("dashboard"))
        menubar.add_cascade(label="Help", menu=help_menu)
        master.configure(menu=menubar)

    def _build_sidebar(self) -> None:
        sidebar = ttk.Frame(self, style="Bar.TFrame", width=232)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        brand = ttk.Frame(sidebar, style="Bar.TFrame", padding=(16, 18))
        brand.pack(fill="x")
        ttk.Label(brand, text="Flood Ready\nVehicle System", style="TitleBar.TLabel", justify="left").pack(anchor="w")
        ttk.Label(brand, text=f"PYTHON · v{APP_VERSION}", style="MicroBar.TLabel").pack(anchor="w", pady=(6, 0))

        nav = ttk.Frame(sidebar, style="Bar.TFrame")
        nav.pack(fill="both", expand=True, pady=(18, 0))
        for key, label, icon, _page in NAV_PAGES:
            if key == "users" and self.user["role"] != "admin":
                continue
            button = ttk.Button(
                nav,
                text=f" {icon}   {label}",
                style="Side.TButton",
                command=lambda bound=key: self.show_page(bound),
            )
            button.pack(fill="x", pady=1)
            self.buttons[key] = button

        user_card = ttk.Frame(sidebar, style="CardBorder.TFrame", padding=1)
        user_card.pack(side="bottom", fill="x", padx=12, pady=12)
        inner = ttk.Frame(user_card, style="Sunken.TFrame", padding=(12, 10))
        inner.pack(fill="both", expand=True)
        ttk.Label(inner, text=self.user["full_name"], style="TitleSunken.TLabel").pack(anchor="w")
        ttk.Label(inner, text=self.user["role"].title(), style="MutedSunken.TLabel").pack(anchor="w")
        ttk.Button(inner, text="Sign out", style="Ghost.TButton", command=self._sign_out).pack(fill="x", pady=(10, 0))

        ttk.Frame(self, style="CardBorder.TFrame", width=1).pack(side="left", fill="y")

    def _build_status_bar(self) -> None:
        bar = ttk.Frame(self, style="Bar.TFrame", padding=(14, 7))
        bar.pack(side="bottom", fill="x")
        self.dot = tk.Canvas(bar, width=9, height=9, background=PALETTE["surface"], highlightthickness=0, bd=0)
        self.dot.pack(side="left")
        self.status = ttk.Label(bar, text="Checking internet connection…", style="MutedBar.TLabel")
        self.status.pack(side="left", padx=(9, 0))
        self.organisation = tk.StringVar(value=self.store.settings().get("organisation", APP_NAME))
        ttk.Label(bar, textvariable=self.organisation, style="MutedBar.TLabel").pack(side="left", padx=(18, 0))
        ttk.Label(bar, text=f"{self.user['full_name']} ({self.user['role']})", style="MutedBar.TLabel").pack(side="right")
        ttk.Label(bar, text=str(DATA_ROOT), style="MicroBar.TLabel").pack(side="right", padx=(0, 18))

    # -- pages ------------------------------------------------------------
    def show_page(self, key: str) -> None:
        if self.current and self.current in self.pages:
            self.pages[self.current].pack_forget()
        self.current = key
        page = self.pages.get(key)
        if page is None:
            page = PAGE_BY_KEY[key](self.page_content, self)
            self.pages[key] = page
        page.pack(fill="both", expand=True)
        self._resize_page_window()
        self.page_canvas.yview_moveto(0)
        try:
            page.refresh()
        except Exception as error:  # one broken page must not stop the app
            logging.getLogger(__name__).exception("The '%s' page could not be refreshed", key)
            messagebox.showerror(APP_NAME, f"The {LABEL_BY_KEY.get(key, key)} page could not be refreshed:\n{error}", parent=self)
        page.update_idletasks()
        self._resize_page_window()
        for button_key, button in self.buttons.items():
            button.configure(style="SideActive.TButton" if button_key == key else "Side.TButton")

    def _resize_page_window(self, width: int | None = None, height: int | None = None) -> None:
        viewport_width = width if width is not None else self.page_canvas.winfo_width()
        viewport_height = height if height is not None else self.page_canvas.winfo_height()
        page = self.pages.get(self.current)
        page_height = page.winfo_reqheight() if page is not None else 0
        content_height = max(viewport_height, page_height)
        self.page_canvas.itemconfigure(self._page_window, width=viewport_width, height=content_height)
        self.page_canvas.configure(scrollregion=self.page_canvas.bbox("all"))

    def refresh_all(self) -> None:
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
            color, text = PALETTE["warn"], "Offline — map tiles may not load; saved data stays available"
        self.dot.delete("all")
        self.dot.create_oval(0, 0, 9, 9, fill=color, outline="")
        self.status.configure(text=text)
        self.after(10000, self._poll_connectivity)

    # -- actions ----------------------------------------------------------
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

    for label, check in (
        ("authentication", lambda: store.login(DEFAULT_ADMIN_USERNAME, DEFAULT_ADMIN_PASSWORD)),
        ("dashboard statistics", store.dashboard),
        ("flood risk scan", lambda: store.run_flood_scan(DEFAULT_ADMIN_USERNAME)),
        ("exposure distances", store.exposure),
        ("report builders", lambda: [store.report(key) for key in store.REPORTS]),
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
