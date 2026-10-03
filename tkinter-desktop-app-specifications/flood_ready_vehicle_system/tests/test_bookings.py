"""Booking, status transition and payment tests."""
from __future__ import annotations

import pytest
from datetime import date, timedelta

from app import DataConflictError, OperationError, ValidationError
from app.services import ACTIVE_BOOKING_STATUSES


def test_quote_and_create_booking(vehicles, bookings, customer_id, vehicle_id):
    quote = bookings.quote(vehicle_id, "2026-07-01", "2026-07-03")
    assert quote["rental_days"] == 3
    assert quote["total_amount"] == 11400
    assert quote["vehicle"].startswith("BKG 707")

    booking_id = bookings.create(vehicle_id=vehicle_id, customer_id=customer_id,
                                 start_date="2026-07-01", end_date="2026-07-03")
    row = bookings.get(booking_id)
    assert row["booking_code"].startswith("BK-")
    assert row["rental_days"] == 3
    assert row["total_amount"] == 11400
    assert row["paid_amount"] == 0
    assert row["status"] == "pending"


def test_booking_code_is_unique(bookings, vehicles, customers, customer_id, vehicle_id):
    first = bookings.create(vehicle_id=vehicle_id, customer_id=customer_id,
                            start_date="2026-07-01", end_date="2026-07-02")
    second = bookings.create(vehicle_id=vehicle_id, customer_id=customer_id,
                             start_date="2026-08-01", end_date="2026-08-02")
    assert bookings.get(first)["booking_code"] != bookings.get(second)["booking_code"]


def test_invalid_dates_are_rejected(bookings, vehicle_id, customer_id):
    with pytest.raises(ValidationError):
        bookings.create(vehicle_id=vehicle_id, customer_id=customer_id,
                        start_date="2026-07-05", end_date="2026-07-01")
    with pytest.raises(ValidationError):
        bookings.create(vehicle_id=vehicle_id, customer_id=customer_id,
                        start_date="tomorrow", end_date="next week")


def test_overlapping_booking_is_rejected(bookings, vehicle_id, customer_id):
    bookings.create(vehicle_id=vehicle_id, customer_id=customer_id,
                    start_date="2026-07-01", end_date="2026-07-05")
    with pytest.raises(DataConflictError):
        bookings.create(vehicle_id=vehicle_id, customer_id=customer_id,
                        start_date="2026-07-05", end_date="2026-07-08")
    # a booking after the previous one has ended is allowed
    assert bookings.create(vehicle_id=vehicle_id, customer_id=customer_id,
                           start_date="2026-07-06", end_date="2026-07-07") > 0


def test_status_transitions_release_the_vehicle(vehicles, bookings, vehicle_id,
                                                customer_id):
    booking_id = bookings.create(vehicle_id=vehicle_id, customer_id=customer_id,
                                 start_date="2026-07-01", end_date="2026-07-02")
    assert vehicles.get(vehicle_id).status == "available"
    bookings.set_status(booking_id, "ongoing")
    assert vehicles.get(vehicle_id).status == "rented"
    bookings.set_status(booking_id, "completed")
    assert vehicles.get(vehicle_id).status == "available"
    with pytest.raises(OperationError):
        bookings.set_status(booking_id, "ongoing")  # completed bookings stay closed


def test_cancelled_booking_releases_the_vehicle(vehicles, bookings, vehicle_id,
                                                customer_id):
    booking_id = bookings.create(vehicle_id=vehicle_id, customer_id=customer_id,
                                 start_date="2026-07-01", end_date="2026-07-02")
    bookings.set_status(booking_id, "ongoing")
    bookings.set_status(booking_id, "cancelled")
    assert vehicles.get(vehicle_id).status == "available"


def test_maintenance_vehicle_cannot_be_booked(vehicles, bookings, customer_id, vehicle_id):
    vehicles.set_status(vehicle_id, "maintenance")
    with pytest.raises(OperationError):
        bookings.create(vehicle_id=vehicle_id, customer_id=customer_id,
                        start_date="2026-07-01", end_date="2026-07-02")


def test_payment_creates_transaction_and_confirms_booking(bookings, transactions,
                                                          vehicle_id, customer_id):
    booking_id = bookings.create(vehicle_id=vehicle_id, customer_id=customer_id,
                                 start_date="2026-07-01", end_date="2026-07-02")
    transactions.record_payment(booking_id=booking_id, amount=3800, method="cash")
    row = bookings.get(booking_id)
    assert row["status"] == "confirmed"
    assert row["paid_amount"] == 3800
    entries = transactions.list_transactions()
    assert entries[0]["reference"].startswith("TXN-")
    assert entries[0]["booking_code"] == row["booking_code"]
    assert transactions.paid_for_booking(booking_id) == 3800


def test_refund_reduces_the_collected_amount(transactions, bookings, vehicle_id,
                                             customer_id):
    booking_id = bookings.create(vehicle_id=vehicle_id, customer_id=customer_id,
                                 start_date="2026-07-01", end_date="2026-07-02")
    transactions.record_payment(booking_id=booking_id, amount=7600, method="card")
    transactions.record_payment(booking_id=booking_id, amount=1000, method="cash",
                                entry_type="refund")
    assert transactions.paid_for_booking(booking_id) == 6600
    totals = transactions.totals()
    assert totals["net"] == 6600
    assert totals["refunds"] == 1000


def test_transaction_date_filters(transactions, bookings, vehicle_id, customer_id):
    booking_id = bookings.create(vehicle_id=vehicle_id, customer_id=customer_id,
                                 start_date="2026-07-01", end_date="2026-07-02")
    today = date.today().isoformat()
    transactions.record_payment(booking_id=booking_id, amount=500, method="cash",
                                paid_at=f"{today} 10:00:00")
    assert len(transactions.list_transactions(start=today, end=today)) == 1
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    assert transactions.list_transactions(start=yesterday, end=yesterday) == []
    assert transactions.totals(start=today, end=today)["entries"] == 1


def test_upcoming_returns_only_future_bookings(bookings, vehicle_id, customer_id):
    today = date.today()
    bookings.create(vehicle_id=vehicle_id, customer_id=customer_id,
                    start_date=today.isoformat(),
                    end_date=(today + timedelta(days=2)).isoformat())
    bookings.create(vehicle_id=vehicle_id, customer_id=customer_id,
                    start_date=(today + timedelta(days=30)).isoformat(),
                    end_date=(today + timedelta(days=40)).isoformat())
    rows = bookings.upcoming_returns(days_ahead=7)
    assert 1 <= len(rows) <= 2
    assert all(row["end_date"] <= (today + timedelta(days=7)).isoformat() for row in rows)


def test_active_booking_statuses_match_database(bookings):
    placeholders = ",".join("?" for _ in ACTIVE_BOOKING_STATUSES)
    assert bookings.db.count("bookings", f"status IN ({placeholders})",
                             list(ACTIVE_BOOKING_STATUSES)) == 0
