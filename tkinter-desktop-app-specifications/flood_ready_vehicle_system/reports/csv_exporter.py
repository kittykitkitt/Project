"""CSV export using Python's built-in csv module (Excel friendly)."""
from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from app import AppError

if TYPE_CHECKING:  # pragma: no cover
    from app.models import ReportData

log = logging.getLogger(__name__)


def export_report(report: "ReportData", destination: str | Path) -> Path:
    """Write *report* as UTF-8 CSV (with BOM so Excel opens it cleanly)."""
    destination = Path(destination)
    if not report.rows:
        raise AppError(f"{report.title}: there is no data to export.")
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle)
            writer.writerow([column for column in report.columns])
            for row in report.rows:
                writer.writerow(["" if value is None else value for value in row])
            if report.summary:
                writer.writerow([])
                writer.writerow([])
                for line in report.summary:
                    writer.writerow([line])
    except OSError as exc:
        log.exception("CSV export failed for %s", report.title)
        raise AppError("The CSV file could not be created. See the log file.") from exc
    log.info("CSV report written to %s (%d rows)", destination, len(report.rows))
    return destination
