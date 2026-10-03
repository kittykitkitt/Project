"""Flood Ready Vehicle System - application entry point.

Runs on Python 3.11+ with the standard Tkinter GUI and a local SQLite database.
Start with:  python main.py
"""
from __future__ import annotations

import logging
import sys

from app import AppError
from app.config import APP_NAME, APP_VERSION, DATA_DIR, setup_logging
from app.database import DatabaseManager

log = logging.getLogger(__name__)


def _fatal(message: str, log_path: str = "") -> None:
    """Show a friendly fatal error (never a raw traceback)."""
    log.critical(message)
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            APP_NAME,
            f"{message}\n\nApplication data folder: {DATA_DIR}"
            + (f"\nLog file: {log_path}" if log_path else ""),
        )
        root.destroy()
    except Exception:  # pragma: no cover - no display available
        print(message, file=sys.stderr)


def _fatal_cause(prefix: str, exc: Exception, log_path: str) -> None:
    """Fatal error that also shows *why* it happened (never a raw traceback)."""
    log.critical("%s: %s", prefix, exc, exc_info=exc)
    _fatal(f"{prefix}\n\nReason: {type(exc).__name__}: {exc}\n\n"
           f"Technical details were written to the log file below.", log_path)


def _excepthook(exc_type, exc_value, exc_traceback) -> None:  # pragma: no cover
    logging.exception("Unhandled exception",
                      exc_info=(exc_type, exc_value, exc_traceback))
    try:
        from tkinter import messagebox

        messagebox.showerror(
            APP_NAME,
            "An unexpected problem occurred and the action was cancelled.\n"
            f"Technical details were written to the log file.\n\n({exc_value})")
    except Exception:
        pass


def prepare_database() -> DatabaseManager:
    """Create folders, the database file, tables and the one-time seed data."""
    manager = DatabaseManager()
    manager.initialise()
    if manager.seed_if_needed():
        log.info("First launch preparation finished (defaults inserted once)")
    return manager


def main() -> int:
    log_path = setup_logging()
    sys.excepthook = _excepthook
    log.info("%s %s starting", APP_NAME, APP_VERSION)

    try:
        database = prepare_database()
    except AppError as exc:
        _fatal(str(exc), str(log_path))
        return 1
    except Exception as exc:
        log.exception("Startup failed")
        _fatal_cause("The application could not prepare its local database.",
                     exc, str(log_path))
        return 1

    try:
        import tkinter as tk
    except ImportError as exc:  # Python installed without tcl/tk
        _fatal(
            "Python's Tkinter module is not available on this computer.\n\n"
            "Reinstall Python 3.11 or newer and make sure the 'tcl/tk and IDLE' "
            "option is ticked in the installer.", str(log_path))
        log.debug("tkinter import error: %s", exc)
        return 1

    from app.services import AuthService
    from ui.login_window import LoginWindow
    from ui.main_window import MainWindow

    root = tk.Tk()
    root.withdraw()
    try:
        login = LoginWindow(root, AuthService(database))
        root.wait_window(login)
        if login.user is None:
            root.destroy()
            return 0
        MainWindow(root, database, login.user)
        root.deiconify()
        root.mainloop()
    except Exception as exc:
        log.exception("Interface failure")
        _fatal_cause("The application interface could not be started.",
                     exc, str(log_path))
        return 1
    finally:
        log.info("Application closed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
