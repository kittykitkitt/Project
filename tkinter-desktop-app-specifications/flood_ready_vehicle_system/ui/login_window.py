"""Login window. Works completely offline - only the map needs internet."""
from __future__ import annotations

import logging
import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING, Any

from app import AppError
from app.config import APP_VERSION
from .styles import PALETTE, apply_theme

if TYPE_CHECKING:  # pragma: no cover
    from app.services import AuthService

log = logging.getLogger(__name__)


class LoginWindow(tk.Toplevel):
    def __init__(self, parent: tk.Tk, auth_service: "AuthService") -> None:
        super().__init__(parent)
        self.auth = auth_service
        self.user: Any = None
        self.title("Flood Ready Vehicle System - Sign in")
        self.resizable(False, False)
        self.configure(background=PALETTE["bg"])
        apply_theme(self)

        card = ttk.Frame(self, style="Card.TFrame", padding=(38, 32))
        card.pack(fill="both", expand=True, padx=28, pady=28)

        brand = ttk.Frame(card, style="Card.TFrame")
        brand.pack(anchor="w", fill="x")
        logo = self._logo(brand)
        if logo is not None:
            logo.pack(side="left", padx=(0, 14))
        titles = ttk.Frame(card, style="Card.TFrame")
        titles.pack(anchor="w", pady=(0 if logo is None else 6, 0))
        ttk.Label(titles, text="Flood Ready", style="H1.TLabel").pack(anchor="w")
        ttk.Label(titles, text="Vehicle System", style="H2.TLabel").pack(anchor="w")
        ttk.Label(card, text="Rental operations with flood-risk monitoring",
                  style="CardMuted.TLabel").pack(anchor="w", pady=(10, 0))
        ttk.Separator(card).pack(fill="x", pady=(16, 18))

        self.username_var = tk.StringVar()
        self.password_var = tk.StringVar()
        self.error_var = tk.StringVar()

        ttk.Label(card, text="Username", style="Field.TLabel").pack(anchor="w")
        username = ttk.Entry(card, textvariable=self.username_var, width=32, font=("Segoe UI", 11))
        username.pack(fill="x", pady=(4, 14))
        ttk.Label(card, text="Password", style="Field.TLabel").pack(anchor="w")
        password = ttk.Entry(card, textvariable=self.password_var, width=32,
                             show="\u2022", font=("Segoe UI", 11))
        password.pack(fill="x", pady=(4, 8))

        ttk.Label(card, textvariable=self.error_var, style="Danger.TLabel",
                  wraplength=340, justify="left").pack(anchor="w", pady=(0, 12))
        ttk.Button(card, text="Sign in", style="Primary.TButton",
                   command=self._login).pack(fill="x", ipady=2)
        ttk.Label(card, text="Default login: admin / admin123",
                  style="CardMuted.TLabel").pack(anchor="w", pady=(18, 0))
        ttk.Label(card, text="Works offline \u2014 only map tiles need internet",
                  style="CardMuted.TLabel").pack(anchor="w", pady=(4, 0))
        ttk.Label(card, text=f"Version {APP_VERSION}",
                  style="CardMuted.TLabel").pack(anchor="w", pady=(14, 0))

        username.focus_set()
        self.bind("<Return>", lambda _event: self._login())
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self._centre()

    # ------------------------------------------------------------------ helpers
    def _logo(self, parent: tk.Widget) -> tk.Label | None:
        """Bundled application icon, or nothing when it cannot be read."""
        try:
            from app.config import asset_path
            from PIL import Image, ImageTk

            path = asset_path("icons", "app_icon.png")
            if not path.exists():
                return None
            with Image.open(path) as picture:
                picture.thumbnail((56, 56),
                                   getattr(getattr(Image, "Resampling", Image), "LANCZOS"))
                photo = ImageTk.PhotoImage(picture)
        except Exception:  # pragma: no cover - cosmetic only
            return None
        label = tk.Label(parent, image=photo, background=PALETTE["card"])
        label.image = photo  # type: ignore[attr-defined]
        return label

    def _centre(self) -> None:
        """Centre the window, sized from its content (safe on high DPI displays)."""
        self.update_idletasks()
        width = max(440, self.winfo_reqwidth())
        height = max(520, self.winfo_reqheight())
        x = max(0, (self.winfo_screenwidth() - width) // 2)
        y = max(0, (self.winfo_screenheight() - height) // 3)
        self.geometry(f"{width}x{height}+{x}+{y}")

    # ------------------------------------------------------------------ actions
    def _login(self) -> None:
        try:
            self.user = self.auth.login(self.username_var.get(), self.password_var.get())
        except AppError as exc:
            self.error_var.set(str(exc))
            self.password_var.set("")
            return
        except Exception:  # pragma: no cover - defensive
            log.exception("Unexpected login failure")
            self.error_var.set("Sign in failed. Please check the application log.")
            return
        self.destroy()

    def _cancel(self) -> None:
        self.user = None
        self.destroy()
