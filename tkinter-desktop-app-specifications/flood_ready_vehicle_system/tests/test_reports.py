"""Report generation and export tests."""
from __future__ import annotations

import csv

import pytest

from app import AppError
from app.models import ReportData
from reports import csv_exporter, pdf_exporter


def test_vehicle_report_lists_the_seeded_fleet(reports):
    report = reports.vehicle_report()
    assert report.title == "Vehicle Inventory Report"
    assert len(report.rows) == 10
    assert "Plate" in report.columns
    assert any("Vehicles listed" in line for line in report.summary)


def test_booking_report_totals(reports, bookings, vehicles, customer_id):
    vehicle_id = vehicles.create(plate_number="rep 808", brand="Toyota",
                                 model="Vios", rate_per_day=2000)
    bookings.create(vehicle_id=vehicle_id, customer_id=customer_id,
                    start_date="2026-07-01", end_date="2026-07-03")
    report = reports.booking_report()
    assert len(report.rows) == 1
    assert "Contract value: 6,000.00" in report.summary


def test_booking_report_date_filter(reports, bookings, vehicle_id, customer_id):
    bookings.create(vehicle_id=vehicle_id, customer_id=customer_id,
                    start_date="2026-07-01", end_date="2026-07-02")
    assert len(reports.booking_report(start="2026-07-01",
                                      end="2026-07-31").rows) == 1
    assert reports.booking_report(start="2025-01-01", end="2025-01-31").rows == []


def test_flood_risk_report_scores_every_vehicle(reports):
    report = reports.flood_risk_report()
    assert len(report.rows) == 10
    assert report.rows[0][-1] in {"low", "moderate", "high", "severe"}


def test_zone_report(reports, zones):
    zones.create(name="Report Zone", risk_level="high", latitude=14.6, longitude=121.0)
    report = reports.zone_report()
    assert len(report.rows) >= 7  # six seeded zones plus the new one


def test_transaction_report(reports, transactions, bookings, vehicle_id, customer_id):
    booking_id = bookings.create(vehicle_id=vehicle_id, customer_id=customer_id,
                                 start_date="2026-07-01", end_date="2026-07-02")
    transactions.record_payment(booking_id=booking_id, amount=3800, method="cash")
    report = reports.transaction_report()
    assert len(report.rows) == 1
    assert "Net collected" in " ".join(report.summary)


def test_csv_export_writes_a_readable_file(reports, tmp_path):
    report = reports.vehicle_report()
    target = tmp_path / "vehicles.csv"
    path = csv_exporter.export_report(report, target)
    assert path.exists()
    with path.open(encoding="utf-8-sig") as handle:
        rows = list(csv.reader(handle))
    assert rows[0][:3] == ["Plate", "Brand / Model", "Category"]
    assert len(rows) >= 11


def test_pdf_export_writes_a_file(reports, tmp_path):
    pytest.importorskip("reportlab")
    report = reports.vehicle_report()
    target = tmp_path / "vehicles.pdf"
    path = pdf_exporter.export_report(report, target)
    assert path.exists() and path.stat().st_size > 500
    assert path.read_bytes()[:5] == b"%PDF-"


def test_pdf_export_of_empty_report_is_rejected(tmp_path):
    pytest.importorskip("reportlab")
    report = ReportData(title="Empty", columns=["A"], rows=[])
    with pytest.raises(AppError):
        pdf_exporter.export_report(report, tmp_path / "empty.pdf")


def test_csv_export_of_empty_report_is_rejected(tmp_path):
    report = ReportData(title="Empty", columns=["A"], rows=[])
    with pytest.raises(AppError):
        csv_exporter.export_report(report, tmp_path / "empty.csv")


def test_csv_export_handles_unwritable_path(reports, tmp_path):
    report = reports.vehicle_report()
    blocked = tmp_path / "blocked.csv"
    blocked.mkdir()
    with pytest.raises(AppError):
        csv_exporter.export_report(report, blocked)
