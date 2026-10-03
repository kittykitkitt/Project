"""One consistent visual theme for the whole application.

Every page uses the same palette, fonts and widget styles - there is no
additional theming package and no second GUI framework.  The module also
provides the reusable building blocks (badges, stripes, headers) used by all
pages so the interface stays uniform.
"""
from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk
from typing import Any

PALETTE: dict[str, str] = {
    "bg": "#eef2f7",
    "card": "#ffffff",
    "sidebar": "#12293f",
    "sidebar_soft": "#1b3854",
    "sidebar_hover": "#1d3c5c",
    "sidebar_active": "#2563eb",
    "accent": "#2563eb",
    "accent_active": "#1d4ed8",
    "text": "#1b2733",
    "muted": "#64748b",
    "border": "#dbe3ec",
    "danger": "#b3261e",
    "warning": "#b06a00",
    "ok": "#15803d",
    "stripe": "#f6f9fc",
    "head": "#e7eef7",
    "chart": "#93b4d8",
}
PALETTE["sidebar_soft"] = "#1b3854"

# Keys double as Treeview row tags and badge styles: a status or risk value can
# be turned into a colour without any extra mapping code.
RISK_COLORS: dict[str, str] = {
    "low": "#15803d",
    "moderate": "#8a6d00",
    "high": "#d97706",
    "severe": "#b3261e",
    "unknown": "#64748b",
    "available": "#15803d",
    "rented": "#2563eb",
    "maintenance": "#b06a00",
    "pending": "#64748b",
    "confirmed": "#2563eb",
    "ongoing": "#15803d",
    "completed": "#64748b",
    "cancelled": "#b3261e",
    "new": "#b3261e",
    "acknowledged": "#b06a00",
    "resolved": "#15803d",
    "info": "#334155",
    "warning": "#b06a00",
    "critical": "#b3261e",
    "archived": "#64748b",
    "muted": "#64748b",
    "stripe": "#f6f9fc",
}

DOT = "\u25cf"
BASE_FONT = "Segoe UI"


def badge_style(value: object) -> str:
    """ttk style name for a coloured badge matching a status/risk value."""
    key = str(value or "").strip().lower().replace(" ", "_")
    return f"badge_{key}.TLabel"


def apply_theme(root: tk.Tk | tk.Toplevel) -> ttk.Style:
    """Install the application theme and return the ttk.Style instance."""
    root.configure(background=PALETTE["bg"])
    for name, size in (("TkDefaultFont", 10), ("TkTextFont", 10),
                       ("TkMenuFont", 10), ("TkHeadingFont", 9)):
        try:
            tkfont.nametofont(name).configure(family=BASE_FONT, size=size)
        except tk.TclError:  # pragma: no cover - non-standard font set
            pass

    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:  # pragma: no cover - fall back to the platform theme
        pass

    style.configure(".", background=PALETTE["bg"], foreground=PALETTE["text"],
                    font=(BASE_FONT, 10), bordercolor=PALETTE["border"],
                    lightcolor=PALETTE["card"], darkcolor=PALETTE["border"])
    # ---------------------------------------------------------------- frames
    style.configure("TFrame", background=PALETTE["bg"])
    style.configure("Card.TFrame", background=PALETTE["card"], relief="flat")
    style.configure("Page.TFrame", background=PALETTE["bg"])
    style.configure("Sidebar.TFrame", background=PALETTE["sidebar"])
    style.configure("SidebarSoft.TFrame", background=PALETTE["sidebar_soft"])
    style.configure("TLabelframe", background=PALETTE["card"],
                    bordercolor=PALETTE["border"], relief="solid", borderwidth=1)
    style.configure("TLabelframe.Label", background=PALETTE["card"],
                    foreground=PALETTE["muted"], font=(BASE_FONT, 9, "bold"),
                    padding=(6, 0))
    # ---------------------------------------------------------------- labels
    style.configure("TLabel", background=PALETTE["bg"], foreground=PALETTE["text"])
    style.configure("Card.TLabel", background=PALETTE["card"],
                    foreground=PALETTE["text"])
    style.configure("H1.TLabel", background=PALETTE["card"],
                    foreground=PALETTE["sidebar"], font=(BASE_FONT, 15, "bold"))
    style.configure("H2.TLabel", background=PALETTE["card"],
                    foreground=PALETTE["sidebar"], font=(BASE_FONT, 11, "bold"))
    style.configure("Muted.TLabel", background=PALETTE["bg"],
                    foreground=PALETTE["muted"])
    style.configure("CardMuted.TLabel", background=PALETTE["card"],
                    foreground=PALETTE["muted"])
    style.configure("Field.TLabel", background=PALETTE["card"],
                    foreground=PALETTE["muted"], font=(BASE_FONT, 9, "bold"))
    style.configure("Value.TLabel", background=PALETTE["card"],
                    foreground=PALETTE["text"], font=(BASE_FONT, 10, "bold"))
    style.configure("Danger.TLabel", background=PALETTE["card"],
                    foreground=PALETTE["danger"])
    style.configure("Sidebar.TLabel", background=PALETTE["sidebar"],
                    foreground="#c9d8e8")
    style.configure("SidebarTitle.TLabel", background=PALETTE["sidebar"],
                    foreground="#ffffff", font=(BASE_FONT, 14, "bold"))
    style.configure("SidebarSection.TLabel", background=PALETTE["sidebar"],
                    foreground="#7f9cb8", font=(BASE_FONT, 8, "bold"))
    style.configure("SidebarUser.TLabel", background=PALETTE["sidebar_soft"],
                    foreground="#dbe6f2", font=(BASE_FONT, 10, "bold"))
    style.configure("SidebarUserRole.TLabel", background=PALETTE["sidebar_soft"],
                    foreground="#8fb0cf", font=(BASE_FONT, 9))
    style.configure("Status.TLabel", background=PALETTE["card"],
                    foreground=PALETTE["muted"])
    # ---------------------------------------------------------------- buttons
    style.configure("TButton", padding=(12, 6), font=(BASE_FONT, 10))
    style.configure("Primary.TButton", background=PALETTE["accent"],
                    foreground="#ffffff", padding=(16, 7),
                    font=(BASE_FONT, 10, "bold"), borderwidth=0)
    style.map("Primary.TButton",
              background=[("active", PALETTE["accent_active"]),
                          ("disabled", "#a8c4ea")])
    style.configure("Secondary.TButton", background=PALETTE["card"],
                    foreground=PALETTE["text"], padding=(14, 6),
                    bordercolor=PALETTE["border"])
    style.map("Secondary.TButton", background=[("active", PALETTE["head"])])
    style.configure("Danger.TButton", background=PALETTE["danger"],
                    foreground="#ffffff", padding=(14, 6), borderwidth=0)
    style.map("Danger.TButton", background=[("active", "#8f1e18"),
                                            ("disabled", "#d8a09c")])
    style.configure("Sidebar.TButton", background=PALETTE["sidebar"],
                    foreground="#c9d8e8", anchor="w", padding=(16, 9),
                    font=(BASE_FONT, 10), borderwidth=0)
    style.map("Sidebar.TButton", background=[("active", PALETTE["sidebar_hover"])])
    style.configure("SidebarActive.TButton", background=PALETTE["sidebar_active"],
                    foreground="#ffffff", anchor="w", padding=(16, 9),
                    font=(BASE_FONT, 10, "bold"), borderwidth=0)
    style.map("SidebarActive.TButton",
              background=[("active", PALETTE["accent_active"])])
    style.configure("SidebarSignOut.TButton", background=PALETTE["sidebar_soft"],
                    foreground="#c9d8e8", anchor="w", padding=(16, 9), borderwidth=0)
    style.map("SidebarSignOut.TButton",
              background=[("active", "#24476b")])
    # ---------------------------------------------------------------- inputs
    style.configure("TEntry", padding=6, fieldbackground=PALETTE["card"],
                    bordercolor=PALETTE["border"])
    style.map("TEntry", bordercolor=[("focus", PALETTE["accent"])])
    style.configure("TCombobox", padding=5, fieldbackground=PALETTE["card"],
                    arrowsize=14)
    style.configure("TCheckbutton", background=PALETTE["card"],
                    foreground=PALETTE["text"])
    style.map("TCheckbutton", background=[("active", PALETTE["card"])])
    # ---------------------------------------------------------------- tables
    style.configure("Treeview", background=PALETTE["card"],
                    fieldbackground=PALETTE["card"], foreground=PALETTE["text"],
                    rowheight=28, bordercolor=PALETTE["border"],
                    font=(BASE_FONT, 10))
    style.configure("Treeview.Heading", background=PALETTE["head"],
                    foreground=PALETTE["sidebar"], font=(BASE_FONT, 9, "bold"),
                    padding=(8, 8), relief="flat")
    style.map("Treeview", background=[("selected", PALETTE["accent"])],
              foreground=[("selected", "#ffffff")])
    style.map("Treeview.Heading", background=[("active", PALETTE["head"])])
    # ---------------------------------------------------------------- tabs
    style.configure("TNotebook", background=PALETTE["bg"], borderwidth=0)
    style.configure("TNotebook.Tab", background=PALETTE["head"],
                    foreground=PALETTE["text"], padding=(14, 7),
                    font=(BASE_FONT, 10))
    style.map("TNotebook.Tab", background=[("selected", PALETTE["card"])],
              foreground=[("selected", PALETTE["accent"])])

    # Coloured badges and dots for every status/risk value.
    for key, colour in RISK_COLORS.items():
        style.configure(f"badge_{key}.TLabel", background=colour,
                        foreground="#ffffff", padding=(10, 3),
                        font=(BASE_FONT, 9, "bold"))
    return style


# --------------------------------------------------------------------- widgets
def make_treeview(parent: tk.Widget, columns: list[tuple[str, str, int, Any]],
                  height: int = 14, selectmode: Any = "browse"
                  ) -> tuple[ttk.Frame, ttk.Treeview]:
    """Create a consistently styled Treeview with a vertical scrollbar.

    ``columns`` items are ``(key, heading, width, anchor)`` tuples.  Row tags are
    pre-configured for every status/risk value plus a striped background tag.
    """
    keys = [column[0] for column in columns]
    frame = ttk.Frame(parent, style="Card.TFrame")
    tree = ttk.Treeview(frame, columns=keys, show="headings", height=height,
                        selectmode=selectmode)
    scrollbar = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=scrollbar.set)
    for key, heading, width, anchor in columns:
        tree.heading(key, text=heading)
        tree.column(key, width=width, anchor=anchor, stretch=True)
    tree.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")
    for tag, colour in RISK_COLORS.items():
        tree.tag_configure(tag, foreground=colour)
    tree.tag_configure("stripe", background=PALETTE["stripe"])
    return frame, tree


def page_header(parent: tk.Widget, title: str, subtitle: str = "",
                actions: tk.Widget | None = None) -> ttk.Frame:
    """Standard page header: icon + title, subtitle and an optional action area."""
    header = ttk.Frame(parent, style="Card.TFrame", padding=(18, 14, 18, 12))
    header.columnconfigure(0, weight=1)
    ttk.Label(header, text=title, style="H1.TLabel").grid(row=0, column=0, sticky="w")
    if subtitle:
        ttk.Label(header, text=subtitle, style="CardMuted.TLabel").grid(
            row=1, column=0, sticky="w", pady=(3, 0))
    if actions is not None:
        actions.grid(row=0, column=1, rowspan=2, sticky="e")
    return header


def money(value: Any, currency: str = "PHP") -> str:
    """Format a money value for labels, tables and reports."""
    try:
        amount = float(value)
    except (TypeError, ValueError):
        amount = 0.0
    return f"{currency} {amount:,.2f}"
