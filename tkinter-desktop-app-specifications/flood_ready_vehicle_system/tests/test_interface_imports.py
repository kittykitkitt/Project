"""Guard against broken import paths inside the interface package.

A single wrong ``from .x import ...`` is enough to stop the application from
starting, so every interface module is imported here.  The tests need Tkinter
but no display, no external dependency and no database, and they are skipped
automatically on systems without Tk support.
"""
from __future__ import annotations

import importlib
import pathlib
import sys

import pytest

pytest.importorskip("tkinter")

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

INTERFACE_MODULES = [
    "main",
    "ui",
    "ui.styles",
    "ui.dialogs",
    "ui.login_window",
    "ui.main_window",
    "ui.dashboard_page",
    "ui.vehicles_page",
    "ui.customers_page",
    "ui.bookings_page",
    "ui.transactions_page",
    "ui.gps_map_page",
    "ui.flood_zones_page",
    "ui.alerts_page",
    "ui.reports_page",
    "ui.users_page",
    "ui.settings_page",
    "reports",
    "reports.csv_exporter",
    "reports.pdf_exporter",
]


@pytest.mark.parametrize("module_name", INTERFACE_MODULES)
def test_module_imports(module_name: str) -> None:
    """Every module must be importable without optional dependencies."""
    importlib.import_module(module_name)


def test_navigation_registry_matches_the_page_classes() -> None:
    from ui.main_window import page_classes

    registry = page_classes()
    assert len(registry) == 11
    assert registry[0][0] == "dashboard"
    for key, title, _icon, page_class in registry:
        assert key and page_class is not None
        assert page_class.TITLE == title, f"{key} title mismatch"
        assert hasattr(page_class, "on_show"), f"{key} is not a page"


def test_no_interface_module_uses_a_relative_import_outside_ui() -> None:
    """``from .x`` must only reference modules that really live in ``ui``."""
    ui_folder = PROJECT_ROOT / "ui"
    for module_path in sorted(ui_folder.glob("*.py")):
        for line in module_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("from .") and "import" in stripped:
                target = stripped.split("from")[1].split("import")[0].strip().lstrip(".")
                target = target.split(" ")[0]
                assert (ui_folder / f"{target}.py").exists() or target == "", (
                    f"{module_path.name}: {stripped} does not exist inside ui/")
