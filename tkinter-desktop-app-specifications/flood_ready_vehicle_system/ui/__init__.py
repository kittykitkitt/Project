"""Tkinter user-interface package.

:class:`Page` is the shared base class for every sidebar page, and
:class:`TablePage` adds the reusable search + filter + Treeview + action button
layout so each module only supplies its own columns and business actions.
"""
from __future__ import annotations

from functools import partial

import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING, Any

from .styles import make_treeview, page_header

if TYPE_CHECKING:  # pragma: no cover
    from .main_window import MainWindow


class Page(ttk.Frame):
    """Base class for a sidebar page (built on first display, then refreshed)."""

    TITLE = "Page"
    SUBTITLE = ""
    ICON = "\u25cf"

    def __init__(self, parent: tk.Widget, app: "MainWindow") -> None:
        super().__init__(parent, padding=(0,), style="Page.TFrame")
        self.app = app
        self.db = app.db
        self.user = app.user
        self.services = app.services
        self._built = False

    def build(self) -> None:
        """Create the widgets of the page. Called once."""

    def refresh(self) -> None:
        """Reload data into the widgets. Called on every visit."""

    def on_show(self) -> None:
        if not self._built:
            self.build()
            self._built = True
        self.refresh()

    @property
    def is_built(self) -> bool:
        return self._built


class TablePage(Page):
    """Search bar + filter + date range + Treeview table + standard buttons."""

    COLUMNS: list[tuple[str, str, int, str]] = []
    FILTERS: list[tuple[str, str]] = []
    DEFAULT_FILTER = ""
    SHOW_ADD = True
    SHOW_EDIT = True
    SHOW_VIEW = True
    SHOW_ARCHIVE = False
    SHOW_DELETE = False
    SHOW_DATE_RANGE = False
    EXTRA_ACTIONS: list[tuple[str, str]] = []   # (label, method) - needs a selection
    GLOBAL_ACTIONS: list[tuple[str, str]] = []  # (label, method) - always enabled
    TREE_HEIGHT = 16

    def __init__(self, parent: tk.Widget, app: "MainWindow") -> None:
        super().__init__(parent, app)
        self.rows: list[dict[str, Any]] = []
        self.tree: ttk.Treeview | None = None
        self.search_var = tk.StringVar()
        self.filter_var = tk.StringVar(value=self.DEFAULT_FILTER)
        self.include_archived_var = tk.BooleanVar(value=False)
        self.date_from_var = tk.StringVar(value="")
        self.date_to_var = tk.StringVar(value="")
        self.count_var = tk.StringVar(value="")
        self.action_buttons: dict[str, ttk.Button] = {}

    # ------------------------------------------------------------------ layout
    def build(self) -> None:
        page_header(self, f"{self.ICON}  {self.TITLE}", self.SUBTITLE).pack(fill="x")
        self._build_toolbar().pack(fill="x")
        self._build_table().pack(fill="both", expand=True, pady=(12, 0))
        self._build_actions().pack(fill="x")

    def _build_toolbar(self) -> ttk.Frame:
        bar = ttk.Frame(self, style="Card.TFrame", padding=(16, 12))
        entry = ttk.Entry(bar, textvariable=self.search_var, width=26)
        entry.pack(side="left")
        entry.bind("<Return>", lambda _event: self.refresh())
        ttk.Button(bar, text="Search", style="Secondary.TButton",
                   command=self.refresh).pack(side="left", padx=(6, 0))
        ttk.Button(bar, text="Reset", style="Secondary.TButton",
                   command=self.reset_filters).pack(side="left", padx=(6, 0))
        if self.FILTERS:
            box = ttk.Combobox(bar, textvariable=self.filter_var, width=16,
                               state="readonly",
                               values=[label for label, _value in self.FILTERS])
            box.pack(side="left", padx=(14, 0))
            box.bind("<<ComboboxSelected>>", lambda _event: self.refresh())
        if self.SHOW_ARCHIVE:
            ttk.Checkbutton(bar, text="Show archived",
                            variable=self.include_archived_var,
                            command=self.refresh).pack(side="left", padx=(14, 0))
        if self.SHOW_DATE_RANGE:
            ttk.Label(bar, text="From", style="CardMuted.TLabel").pack(
                side="left", padx=(14, 4))
            ttk.Entry(bar, textvariable=self.date_from_var, width=11).pack(side="left")
            ttk.Label(bar, text="To", style="CardMuted.TLabel").pack(
                side="left", padx=(6, 4))
            ttk.Entry(bar, textvariable=self.date_to_var, width=11).pack(side="left")
        ttk.Label(bar, textvariable=self.count_var, style="CardMuted.TLabel").pack(
            side="right")
        return bar

    def _build_table(self) -> ttk.Frame:
        frame, tree = make_treeview(self, self.COLUMNS, height=self.TREE_HEIGHT)
        self.tree = tree
        tree.bind("<<TreeviewSelect>>", lambda _event: self._update_buttons())
        tree.bind("<Double-1>", lambda _event: self.on_view())
        return frame

    def _build_actions(self) -> ttk.Frame:
        bar = ttk.Frame(self, style="Card.TFrame", padding=(16, 10))
        actions: list[tuple[str, str, str, bool]] = []
        if self.SHOW_ADD:
            actions.append(("add", "Add", "Primary.TButton", False))
        if self.SHOW_EDIT:
            actions.append(("edit", "Edit", "Secondary.TButton", True))
        if self.SHOW_VIEW:
            actions.append(("view", "View", "Secondary.TButton", True))
        for text, method in self.EXTRA_ACTIONS:
            actions.append((method, text, "Secondary.TButton", True))
        if self.SHOW_ARCHIVE:
            actions.append(("archive", "Archive", "Secondary.TButton", True))
        if self.SHOW_DELETE:
            actions.append(("delete", "Delete", "Danger.TButton", True))
        for key, text, style, _needs_selection in actions:
            button = ttk.Button(bar, text=text, style=style,
                                command=partial(self._run, key))
            button.pack(side="left", padx=(0, 8))
            self.action_buttons[key] = button
        for text, method in self.GLOBAL_ACTIONS:
            ttk.Button(bar, text=text, style="Primary.TButton",
                       command=partial(self._run_method, method)).pack(
                side="right", padx=(6, 0))
        self._update_buttons()
        return bar

    # -------------------------------------------------------------------- data
    def load_rows(self) -> list[dict[str, Any]]:
        """Return the rows to display (already filtered)."""
        return []

    def row_values(self, row: dict[str, Any]) -> list[Any]:
        return [row.get(column[0], "") for column in self.COLUMNS]

    def row_tags(self, row: dict[str, Any]) -> list[str]:
        status = str(row.get("status") or row.get("risk_level") or "").lower()
        return [status] if status else []

    def refresh(self) -> None:
        self.rows = self.load_rows()
        if self.tree is not None:
            self.tree.delete(*self.tree.get_children())
            for index, row in enumerate(self.rows):
                self.tree.insert("", "end", values=self.row_values(row),
                                 tags=[*self.row_tags(row),
                                       "stripe" if index % 2 else ""])
        total = len(self.rows)
        archived = sum(1 for row in self.rows if row.get("is_archived"))
        self.count_var.set(f"{total} records"
                           + (f" ({archived} archived)" if archived else ""))
        self._update_buttons()

    def reset_filters(self) -> None:
        self.search_var.set("")
        self.filter_var.set(self.DEFAULT_FILTER)
        self.include_archived_var.set(False)
        self.date_from_var.set("")
        self.date_to_var.set("")
        self.refresh()

    # ---------------------------------------------------------------- helpers
    def filter_value(self) -> str:
        for label, value in self.FILTERS:
            if label == self.filter_var.get():
                return value
        return ""

    def date_range(self) -> tuple[str, str]:
        return self.date_from_var.get().strip(), self.date_to_var.get().strip()

    def selected_row(self) -> dict[str, Any] | None:
        if self.tree is None:
            return None
        selection = self.tree.selection()
        if not selection:
            return None
        index = self.tree.index(selection[0])
        if 0 <= index < len(self.rows):
            return self.rows[index]
        return None

    # ---------------------------------------------------------------- actions
    def _update_buttons(self) -> None:
        has_selection = self.selected_row() is not None
        for key, button in self.action_buttons.items():
            if key == "add":
                continue
            button.configure(state="normal" if has_selection else "disabled")
        archive = self.action_buttons.get("archive")
        row = self.selected_row()
        if archive is not None and row is not None:
            archive.configure(text="Restore" if row.get("is_archived") else "Archive")

    def _run(self, key: str) -> None:
        handler = getattr(self, f"on_{key}", None)
        if handler is None:
            return
        if key != "add" and self.selected_row() is None:
            return
        handler()

    def _run_method(self, method: str) -> None:
        handler = getattr(self, f"on_{method}", None)
        if handler is not None:
            handler()

    # Default actions: subclasses override what they need.
    def on_add(self) -> None:
        return

    def on_edit(self) -> None:
        return

    def on_view(self) -> None:
        return

    def on_archive(self) -> None:
        return

    def on_delete(self) -> None:
        return
