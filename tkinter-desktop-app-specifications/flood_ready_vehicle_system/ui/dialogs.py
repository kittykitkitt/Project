"""Reusable dialogs, forms and message helpers (kept free of business logic)."""
from __future__ import annotations

import logging
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any, Callable, Sequence

from app import AppError
from .styles import PALETTE, badge_style

log = logging.getLogger(__name__)


# ------------------------------------------------------------------- messages
def show_error(message: str, parent: Any = None) -> None:
    log.error("User error: %s", message)
    messagebox.showerror("Flood Ready Vehicle System", message, parent=parent)


def show_info(message: str, parent: Any = None) -> None:
    messagebox.showinfo("Flood Ready Vehicle System", message, parent=parent)


def show_warning(message: str, parent: Any = None) -> None:
    log.warning("User warning: %s", message)
    messagebox.showwarning("Flood Ready Vehicle System", message, parent=parent)


def confirm(message: str, parent: Any = None, title: str = "Please confirm") -> bool:
    return bool(messagebox.askyesno(title, message, parent=parent))


# ------------------------------------------------------------------ form dialog
FieldSpec = dict[str, Any]


class FormDialog(tk.Toplevel):
    """Modal form built from a field description list.

    Supported kinds: ``entry``, ``number``, ``password``, ``combo``, ``text``,
    ``check`` and ``readonly``.  ``on_save`` receives a dict of values and may
    raise :class:`~app.AppError` to keep the dialog open.

    The dialog is modal and blocking: ``values`` is ``None`` when the user
    cancelled, otherwise it holds the accepted values.
    """

    def __init__(self, parent: tk.Widget, title: str, fields: Sequence[FieldSpec],
                 on_save: Callable[[dict[str, Any]], Any] | None = None,
                 columns: int = 2, ok_text: str = "Save",
                 width: int = 640) -> None:
        super().__init__(parent.winfo_toplevel())
        self.title(title)
        self.resizable(False, False)
        self.transient(parent.winfo_toplevel())
        self.values: dict[str, Any] | None = None
        self._vars: dict[str, Any] = {}
        self._texts: dict[str, tk.Text] = {}
        self._entries: dict[str, tk.Widget] = {}
        self._combo_options: dict[str, list[Any]] = {}
        self._fields = list(fields)
        self._on_save = on_save

        body = ttk.Frame(self, padding=18, style="Card.TFrame")
        body.pack(fill="both", expand=True)
        for column in range(columns):
            body.columnconfigure(column, weight=1, uniform="fields")

        row = 0
        column = 0
        for spec in self._fields:
            wide = bool(spec.get("span")) or spec.get("kind") == "text"
            self._build_field(body, spec, row, column, columns)
            if wide:
                column = columns - 1
            column += 1
            if column >= columns:
                column = 0
                row += 1

        self._error_var = tk.StringVar(value="")
        ttk.Label(body, textvariable=self._error_var, style="Danger.TLabel",
                  wraplength=max(220, width - 40), justify="left").grid(
            row=row + 1, column=0, columnspan=columns, sticky="w", pady=(10, 0))
        footer = ttk.Frame(body, style="Card.TFrame")
        footer.grid(row=row + 2, column=0, columnspan=columns, sticky="ew", pady=(14, 0))
        ttk.Button(footer, text="Cancel", style="Secondary.TButton",
                   command=self._cancel).pack(side="right")
        ttk.Button(footer, text=ok_text, style="Primary.TButton",
                   command=self._save).pack(side="right", padx=(0, 8))
        ttk.Label(footer, text="Enter saves  ·  Esc cancels",
                  style="CardMuted.TLabel").pack(side="left")

        self.bind("<Return>", lambda _event: self._save())
        self.bind("<Escape>", lambda _event: self._cancel())
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self._centre_over_parent()
        self.grab_set()
        for widget in self._entries.values():
            widget.focus_set()
            break
        self.wait_visibility()
        self.wait_window(self)

    # ------------------------------------------------------------------ fields
    def _build_field(self, parent: tk.Widget, spec: FieldSpec, row: int,
                     column: int, columns: int) -> None:
        name = spec["name"]
        kind = spec.get("kind", "entry")
        label = spec.get("label", name.replace("_", " ").title())
        required = spec.get("required", kind != "check")
        span = bool(spec.get("span")) or kind == "text"
        marker = "" if required else "  (optional)"
        frame = ttk.Frame(parent, style="Card.TFrame", padding=(0, 0, 12, 10))
        frame.grid(row=row, column=column, columnspan=columns if span else 1,
                   sticky="ew")
        frame.columnconfigure(0, weight=1)
        ttk.Label(frame, text=f"{label}{marker}", style="Field.TLabel").pack(anchor="w")
        value = spec.get("value", "")

        if kind == "readonly":
            ttk.Label(frame, text=str(value or "-"), style="Card.TLabel",
                      wraplength=280, justify="left").pack(anchor="w", pady=(4, 0))
            return

        if kind in {"entry", "number", "password"}:
            var: Any = tk.StringVar(value=str(value if value not in (None, "") else ""))
            widget = ttk.Entry(frame, textvariable=var, width=spec.get("width", 30),
                               show="\u2022" if kind == "password" else "")
            widget.pack(fill="x", pady=(4, 0))
            self._vars[name] = var
            self._entries[name] = widget
            if spec.get("hint"):
                ttk.Label(frame, text=str(spec["hint"]),
                          style="CardMuted.TLabel").pack(anchor="w")
        elif kind == "combo":
            options = list(spec.get("options") or [])
            self._combo_options[name] = options
            paired = any(isinstance(option, (tuple, list)) for option in options)
            labels = [str(option[0]) if paired else str(option) for option in options]
            if paired:
                label_for_value = {option[1]: str(option[0]) for option in options}
                initial = label_for_value.get(value, "")
            else:
                initial = str(value if value not in (None, "") else "")
            if initial not in labels:
                initial = labels[0] if labels else ""
            var = tk.StringVar(value=initial)
            box = ttk.Combobox(frame, textvariable=var, values=labels,
                               state="readonly")
            box.pack(fill="x", pady=(4, 0))
            self._vars[name] = var
            self._entries[name] = box
        elif kind == "text":
            text = tk.Text(frame, height=spec.get("height", 4),
                           width=spec.get("width", 46), wrap="word", relief="solid",
                           bd=1, background=PALETTE["card"],
                           foreground=PALETTE["text"], highlightthickness=0,
                           padx=6, pady=4)
            if value not in (None, ""):
                text.insert("1.0", str(value))
            text.pack(fill="x", pady=(4, 0))
            self._texts[name] = text
        elif kind == "check":
            var = tk.BooleanVar(value=bool(value))
            ttk.Checkbutton(frame, text=spec.get("check_label", label),
                            variable=var).pack(anchor="w", pady=(6, 0))
            self._vars[name] = var
        else:  # pragma: no cover - guards against typos in field specs
            raise AppError(f"Unknown form field type '{kind}'.")

    # ----------------------------------------------------------------- actions
    def collect(self) -> dict[str, Any]:
        data: dict[str, Any] = {}
        for spec in self._fields:
            name = spec["name"]
            kind = spec.get("kind", "entry")
            if kind == "readonly":
                continue
            if kind == "text":
                data[name] = self._texts[name].get("1.0", "end").strip()
            elif kind == "combo":
                raw = str(self._vars[name].get())
                options = self._combo_options.get(name, [])
                if any(isinstance(option, (tuple, list)) for option in options):
                    mapping = {str(option[0]): option[1] for option in options}
                    data[name] = mapping.get(raw, raw)
                else:
                    data[name] = raw
            elif kind == "check":
                data[name] = bool(self._vars[name].get())
            else:
                data[name] = str(self._vars[name].get()).strip()
        return data

    def _save(self) -> None:
        values = self.collect()
        if self._on_save is not None:
            try:
                self._on_save(values)
            except AppError as exc:
                self._error_var.set(str(exc))
                return
            except Exception:  # pragma: no cover - unexpected
                log.exception("Unexpected error while saving the form")
                self._error_var.set("The record could not be saved. See the log file.")
                return
        self.values = values
        self._close()

    def _cancel(self) -> None:
        self.values = None
        self._close()

    def _close(self) -> None:
        try:
            self.grab_release()
        except tk.TclError:  # pragma: no cover - window already closed
            pass
        self.destroy()

    def _centre_over_parent(self) -> None:
        try:
            self.update_idletasks()
            parent = self.master
            offset_x = parent.winfo_rootx()
            offset_y = parent.winfo_rooty()
            parent_width = parent.winfo_width()
            parent_height = parent.winfo_height()
            width = max(self.winfo_reqwidth(), 360)
            height = max(self.winfo_reqheight(), 240)
            x = max(0, offset_x + (parent_width - width) // 2)
            y = max(0, offset_y + max(40, (parent_height - height) // 3))
            self.geometry(f"+{x}+{y}")
        except tk.TclError:  # pragma: no cover - headless/withdrawn parent
            pass


# ---------------------------------------------------------------- detail dialog
class DetailDialog(tk.Toplevel):
    """Read-only record viewer with coloured status badges (also modal)."""

    BADGE_LABELS = {"Status", "Flood risk", "Severity", "Risk level", "Active",
                    "Archived", "Role"}

    def __init__(self, parent: tk.Widget, title: str, rows: Sequence[tuple[str, Any]],
                 notes: str = "", image_path: Any = None) -> None:
        super().__init__(parent.winfo_toplevel())
        self.title(title)
        self.resizable(False, False)
        body = ttk.Frame(self, padding=(20, 18), style="Card.TFrame")
        body.pack(fill="both", expand=True)
        ttk.Label(body, text=title, style="H2.TLabel",
                  wraplength=440).pack(anchor="w")
        ttk.Separator(body).pack(fill="x", pady=(10, 12))
        if image_path:
            picture = load_image_widget(body, image_path, (440, 240))
            if picture is not None:
                picture.pack(anchor="w", pady=(0, 12))
        grid = ttk.Frame(body, style="Card.TFrame")
        grid.pack(fill="both", expand=True)
        grid.columnconfigure(1, weight=1)
        for index, (label, value) in enumerate(rows):
            ttk.Label(grid, text=label, style="Field.TLabel").grid(
                row=index, column=0, sticky="nw", padx=(0, 16), pady=3)
            display = "-" if value in (None, "") else str(value)
            if label in self.BADGE_LABELS:
                ttk.Label(grid, text=display,
                          style=badge_style(display)).grid(
                    row=index, column=1, sticky="w", pady=3)
            else:
                ttk.Label(grid, text=display, style="Value.TLabel", wraplength=430,
                          justify="left").grid(row=index, column=1, sticky="w", pady=3)
        if notes:
            ttk.Separator(body).pack(fill="x", pady=(12, 8))
            ttk.Label(body, text="Notes", style="Field.TLabel").pack(anchor="w")
            ttk.Label(body, text=notes or "-", style="Card.TLabel", wraplength=440,
                      justify="left").pack(anchor="w", pady=(4, 12))
        else:
            ttk.Frame(body, height=12, style="Card.TFrame").pack()
        ttk.Button(body, text="Close", style="Secondary.TButton",
                   command=self.destroy).pack(anchor="e")
        self.transient(parent.winfo_toplevel())
        self._centre_over_parent()
        self.grab_set()
        self.wait_visibility()
        self.wait_window(self)

    def _centre_over_parent(self) -> None:
        try:
            self.update_idletasks()
            parent = self.master
            x = max(0, parent.winfo_rootx()
                    + (parent.winfo_width() - self.winfo_reqwidth()) // 2)
            y = max(0, parent.winfo_rooty()
                    + max(40, (parent.winfo_height() - self.winfo_reqheight()) // 3))
            self.geometry(f"+{x}+{y}")
        except tk.TclError:  # pragma: no cover
            pass


# -------------------------------------------------------------------- images
def load_image_widget(parent: tk.Widget, source: Any,
                      size: tuple[int, int]) -> tk.Label | None:
    """Return a Label showing *source*, or the bundled placeholder when missing."""
    from app.config import asset_path
    from app.services import resolve_image_path

    path = resolve_image_path(source)
    if path is None:
        fallback = asset_path("images", "vehicle_placeholder.png")
        path = fallback if fallback.exists() else None
    try:
        from PIL import Image, ImageTk

        if path is None:
            raise FileNotFoundError(str(source))
        resampling = getattr(getattr(Image, "Resampling", Image), "LANCZOS")
        with Image.open(path) as picture:
            picture.thumbnail(size, resampling)
            photo = ImageTk.PhotoImage(picture)
    except Exception:
        log.info("Vehicle image unavailable: %s", source)
        return None
    label = tk.Label(parent, image=photo, background=PALETTE["card"], bd=1,
                     relief="solid")
    label.image = photo  # type: ignore[attr-defined]  # keep a reference
    return label
