# Flood Ready Vehicle System

A vehicle-rental desktop application with GPS tracking and flood-risk monitoring
for Metro Manila. One Python file, standard library only, offline by design.

```
python main.py
```

## Requirements

- Python 3.9 or newer (3.11+ recommended)
- Tkinter — bundled with the official installers on Windows and macOS
  (on Debian/Ubuntu: `sudo apt install python3-tk`)
- No third-party packages, no internet connection, no web server

## First launch

The application creates its own data folder on first run:

| Platform | Folder |
| --- | --- |
| Windows | `%LOCALAPPDATA%\FloodReadyVehicleSystem` |
| Linux/macOS | `$XDG_DATA_HOME/FloodReadyVehicleSystem` |
| Portable | set `FLOODREADY_DATA_DIR` to any folder (e.g. a USB stick) |

Inside it you get `data/rental_system.db` (SQLite), `exports/` (CSV reports)
and `logs/application.log`.

**Default sign-in:** `admin` / `admin123` — change it from the Users page.
The sample fleet includes 100 models across 20 makes. On an existing install,
the catalog is synchronized at startup; existing vehicle IDs and custom vehicle
records are preserved.

## What is inside

| Module | Purpose |
| --- | --- |
| Dashboard | Fleet counts, collections by month, risk distribution, live map, nearest-zone exposure |
| Vehicles | Inventory, status, rate, GPS position, exposure and notes per unit |
| Customers | Renter records, identification and licence references |
| Bookings | Rental periods, destinations, deposits and totals |
| Transactions | Payments, deposits and refunds with method breakdown |
| GPS map | Vector basemap of Metro Manila — drag to pan, scroll to zoom, layers toggle |
| Flood zones | Monitored areas, severity scores, radius and exposed units |
| Alerts | Notices from the flood scan, staff and maintenance checks |
| Reports | Six ledgers exportable to CSV with a timestamped filename |
| Users | Accounts, roles and PBKDF2 password policy |
| Settings | Organisation details, defaults, data folder and database backup |

## Design notes

The interface is deliberately quiet: one accent colour (`#0E7C5B`), warm neutral
surfaces, hairline `#E6E8E3` borders, an 8-point spacing rhythm and no heavy
shadows. Cards are built by nesting a one-pixel frame, which is how ttk draws a
border colour. Tables are `ttk.Treeview` with striped rows and coloured status
tags; the chart and map are plain `tk.Canvas` widgets so no charting or mapping
library is required.

Distances use the haversine formula, so flood-zone exposure is measured in real
kilometres and the map draws zone rings at true scale.

## Keyboard and mouse

- `Enter` on the sign-in window signs in
- Drag the map to pan, mouse wheel or `+` / `−` buttons to zoom, **Reset view** to return
- Click a vehicle marker or a fleet-list row to focus a unit
- `Run flood risk scan` writes a new alert for every unit inside an active zone

## Maintenance

```
python main.py --smoke-test   # build every page offscreen and check the services
```

The smoke test prints one `[ok]`/`[FAIL]` line per check and writes technical
detail to the log file. Backups are plain SQLite files — copy them anywhere.
