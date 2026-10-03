-- Flood Ready Vehicle System - SQLite schema
-- Applied automatically on first launch (idempotent: CREATE TABLE IF NOT EXISTS).

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    full_name     TEXT    NOT NULL,
    role          TEXT    NOT NULL DEFAULT 'staff',
    password_salt TEXT    NOT NULL,
    password_hash TEXT    NOT NULL,
    is_active     INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT    NOT NULL,
    updated_at    TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS vehicles (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    plate_number    TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    brand           TEXT    NOT NULL,
    model           TEXT    NOT NULL,
    category        TEXT    NOT NULL DEFAULT 'Sedan',
    year            INTEGER NOT NULL DEFAULT 2020,
    seats           INTEGER NOT NULL DEFAULT 4,
    rate_per_day    REAL    NOT NULL DEFAULT 0,
    status          TEXT    NOT NULL DEFAULT 'available',
    is_archived     INTEGER NOT NULL DEFAULT 0,
    latitude        REAL,
    longitude       REAL,
    image_path      TEXT,
    notes           TEXT,
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS customers (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name      TEXT    NOT NULL,
    phone          TEXT    NOT NULL,
    email          TEXT,
    address        TEXT,
    id_type        TEXT    NOT NULL DEFAULT 'Drivers License',
    id_number      TEXT,
    license_number TEXT,
    is_archived    INTEGER NOT NULL DEFAULT 0,
    notes          TEXT,
    created_at     TEXT    NOT NULL,
    updated_at     TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS flood_zones (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    barangay    TEXT,
    risk_level  TEXT    NOT NULL DEFAULT 'moderate',
    latitude    REAL    NOT NULL,
    longitude   REAL    NOT NULL,
    radius_km   REAL    NOT NULL DEFAULT 1.0,
    is_active   INTEGER NOT NULL DEFAULT 1,
    notes       TEXT,
    created_at  TEXT    NOT NULL,
    updated_at  TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS bookings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    booking_code    TEXT    NOT NULL UNIQUE,
    vehicle_id      INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE RESTRICT,
    customer_id     INTEGER NOT NULL REFERENCES customers(id) ON DELETE RESTRICT,
    start_date      TEXT    NOT NULL,
    end_date        TEXT    NOT NULL,
    pickup_location TEXT,
    destination     TEXT,
    rental_days     INTEGER NOT NULL DEFAULT 1,
    rate_per_day    REAL    NOT NULL DEFAULT 0,
    total_amount    REAL    NOT NULL DEFAULT 0,
    deposit         REAL    NOT NULL DEFAULT 0,
    status          TEXT    NOT NULL DEFAULT 'pending',
    is_archived     INTEGER NOT NULL DEFAULT 0,
    notes           TEXT,
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS transactions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    reference    TEXT    NOT NULL UNIQUE,
    booking_id   INTEGER REFERENCES bookings(id) ON DELETE CASCADE,
    amount       REAL    NOT NULL DEFAULT 0,
    method       TEXT    NOT NULL DEFAULT 'cash',
    entry_type   TEXT    NOT NULL DEFAULT 'payment',
    paid_at      TEXT    NOT NULL,
    recorded_by  INTEGER REFERENCES users(id) ON DELETE SET NULL,
    notes        TEXT,
    created_at   TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS alerts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT    NOT NULL,
    message     TEXT    NOT NULL,
    severity    TEXT    NOT NULL DEFAULT 'info',
    source      TEXT    NOT NULL DEFAULT 'manual',
    vehicle_id  INTEGER REFERENCES vehicles(id) ON DELETE CASCADE,
    zone_id     INTEGER REFERENCES flood_zones(id) ON DELETE SET NULL,
    status      TEXT    NOT NULL DEFAULT 'new',
    created_by  INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at  TEXT    NOT NULL,
    updated_at  TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_vehicles_status   ON vehicles(status, is_archived);
CREATE INDEX IF NOT EXISTS idx_customers_name    ON customers(full_name);
CREATE INDEX IF NOT EXISTS idx_bookings_status   ON bookings(status, is_archived);
CREATE INDEX IF NOT EXISTS idx_bookings_dates    ON bookings(start_date, end_date);
CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(paid_at);
CREATE INDEX IF NOT EXISTS idx_alerts_status     ON alerts(status, created_at);
CREATE INDEX IF NOT EXISTS idx_zones_active      ON flood_zones(is_active);
