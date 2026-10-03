"""ReportLab based PDF export.

The exporter only needs a :class:`~app.models.ReportData` object, so the same
code produces the vehicle, booking, transaction and flood-risk reports.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app import AppError
from app.config import APP_NAME, APP_VERSION
from app.models import now_iso

if TYPE_CHECKING:  # pragma: no cover
    from app.models import ReportData

log = logging.getLogger(__name__)


def _cell(value: Any) -> Any:
    text = "" if value is None else str(value)
    try:  # ReportLab default fonts are limited to Latin-1.
        text.encode("latin-1")
    except UnicodeEncodeError:
        text = text.encode("latin-1", "replace").decode("latin-1")
    return text


def export_report(report: "ReportData", destination: str | Path) -> Path:
    """Write *report* as a PDF file and return the path that was created."""
    destination = Path(destination)
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
    except ImportError as exc:  # pragma: no cover - packaging problem
        raise AppError("The PDF library (reportlab) is not installed.") from exc

    if not report.rows:
        raise AppError(f"{report.title}: there is no data to export.")

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ReportTitle", parent=styles["Title"], fontSize=16, spaceAfter=2 * mm
    )
    subtitle_style = ParagraphStyle(
        "ReportSubtitle", parent=styles["Normal"], fontSize=9, textColor=colors.grey
    )
    heading_style = ParagraphStyle(
        "ColumnHead",
        parent=styles["Normal"],
        fontSize=8,
        leading=10,
        textColor=colors.white,
        fontName="Helvetica-Bold",
    )
    body_style = ParagraphStyle(
        "Cell", parent=styles["Normal"], fontSize=8, leading=10
    )

    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        document = SimpleDocTemplate(
            str(destination),
            pagesize=landscape(A4) if len(report.columns) > 6 else A4,
            title=report.title,
            author=APP_NAME,
        )
        story: list[Any] = [
            Paragraph(report.title, title_style),
            Paragraph(
                f"{APP_NAME} v{APP_VERSION} | {report.subtitle} | generated {now_iso()}",
                subtitle_style,
            ),
            Spacer(1, 4 * mm),
        ]
        header = [Paragraph(_cell(column).upper(), heading_style) for column in report.columns]
        body = [[Paragraph(_cell(value), body_style) for value in row] for row in report.rows]
        table = Table([header, *body], repeatRows=1, hAlign="LEFT")
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#14304d")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#c9d3de")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1),
                     [colors.white, colors.HexColor("#f4f7fa")]),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]
            )
        )
        story.append(table)
        story.append(Spacer(1, 5 * mm))
        for line in report.summary:
            story.append(Paragraph(f"<b>{_cell(line)}</b>", body_style))
        document.build(story)
    except AppError:
        raise
    except Exception as exc:  # reportlab raises many error types
        log.exception("PDF export failed for %s", report.title)
        raise AppError("The PDF report could not be created. See the log file.") from exc

    log.info("PDF report written to %s (%d rows)", destination, len(report.rows))
    return destination
