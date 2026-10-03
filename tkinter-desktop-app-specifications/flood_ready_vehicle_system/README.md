# Flood Ready Vehicle System

A portable **Python 3.11+ desktop application** for Windows 10 and Windows 11 that manages a
vehicle rental operation together with **flood-risk monitoring**. The GUI is standard
**Tkinter/ttk**, data is stored in a local **SQLite** database, the GPS page uses
**TkinterMapView** (OpenStreetMap), images are handled with **Pillow** and reports are
produced with **ReportLab**.

Everything runs offline. Only the map tiles need an internet connection - if the computer is
offline the application still opens, login still works and every module (vehicles, customers,
bookings, transactions, alerts, flood risk, reports) keeps working.

---

## 1. Features

| Module | What it does |
| --- | --- |
| Dashboard | Icon summary cards, bookings due back, net-collections bar chart, fleet risk distribution, latest alerts, quick actions |
| Vehicles | Inventory with plate, brand/model, category, year, seats, daily rate, status, GPS position, picture (copied into the app data folder), archive/restore |
| Customers | Renter records with contact details, ID and licence numbers, archive/restore |
| Bookings | Rental contracts with automatic day/rate totals, overlap protection, status flow (pending → confirmed → ongoing → completed / cancelled), archive/restore |
| Transactions | Payments, deposits and refunds with reference numbers, date filters and running totals |
| GPS Map | **Live feed: vehicles drive along real roads (EDSA, Commonwealth, Quezon Avenue, Roxas Boulevard, C5, Aurora, Quirino Highway) while the rescue boat patrols the Pasig River.** Smooth marker movement, trails, 1x-16x speed, fit fleet, four map styles, risk links, tile caching, search and risk filters |
| Flood Zones | Flood prone areas with severity, radius and active/inactive monitoring |
| Alerts | Manual notices plus an automatic fleet scan that raises alerts at/above the configured threshold |
| Reports | Preview and export to PDF (ReportLab) and CSV (built-in `csv`): vehicles, bookings, transactions, customers, flood risk, flood zones |
| Users | Administrator-only account management with PBKDF2 password hashing and password resets |
| Settings | Organisation name, currency, map centre/zoom, alert threshold, data locations, backup |

## 2. Installation (source, Windows 10/11)

### One-click script
Double-click **`setup_windows.bat`**. It creates a virtual environment, upgrades pip,
installs the runtime requirements and starts the application.

### Manual commands
```bat
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python main.py
```

No administrator rights, no environment variables, no MySQL/PostgreSQL/XAMPP/Docker/Node.js and
no web server are required.

### Dependencies
`requirements.txt` contains only:

```
tkintermapview
Pillow
reportlab
```

`tkinter`, `sqlite3`, `csv`, `hashlib`, `logging`, `pathlib`, `datetime`, `math`, `json`, `os`,
`shutil`, `threading` and `urllib` are part of the Python standard library and are **not**
listed as requirements.

Development tools live in `requirements-dev.txt` (pytest + PyInstaller) and are never needed to
run the application:

```bat
pip install -r requirements-dev.txt
```

### Default login
| Username | Password |
| --- | --- |
| `admin` | `admin123` |

Change this password on the **Users** page after the first login. Passwords are never stored in
plain text: each account stores a random 16-byte salt plus a `hashlib.pbkdf2_hmac` SHA-256
digest (260,000 iterations), verified with `hmac.compare_digest`.

## 3. Data storage (Windows)

Editable data is **never** written inside the installed program folder:

```
%LOCALAPPDATA%\FloodReadyVehicleSystem\
    data\            rental_system.db        (SQLite database)
    images\          user uploaded vehicle pictures
    exports\pdf\     generated PDF reports
    exports\csv\     generated CSV reports
    logs\            application.log
    map_cache\       offline OpenStreetMap tiles
```

All folders and the database are created automatically on first launch, and the default
administrator, vehicle catalog and flood zones are inserted **once** (guarded by the
`seed_version` setting). If `%LOCALAPPDATA%` is unavailable the application falls back to an
`app_data` folder beside the project, so it can also run from a USB stick.

## 4. Project structure

```
flood_ready_vehicle_system/
    main.py                 entry point (python main.py)
    requirements.txt        runtime dependencies (3)
    requirements-dev.txt    pytest + pyinstaller
    setup_windows.bat       create venv, install, run
    README.md
    app/
        __init__.py         shared exception types
        config.py           paths, folders, logging, constants
        database.py         DatabaseManager (all SQLite access)
        models.py           data models + ReportData
        services.py         business logic (no Tkinter imports)
        tracking.py         demonstration GPS feed (road routes, movement)
        validators.py       reusable validation helpers
        security.py         PBKDF2 password hashing
    ui/
        __init__.py         Page + TablePage base classes
        styles.py           one consistent ttk theme
        dialogs.py          reusable forms, dialogs, message boxes
        login_window.py     sign-in window
        main_window.py      sidebar shell, status bar, menus
        dashboard_page.py   vehicles_page.py   customers_page.py
        bookings_page.py    transactions_page.py
        gps_map_page.py     flood_zones_page.py
        alerts_page.py      reports_page.py
        users_page.py       settings_page.py
    reports/
        pdf_exporter.py     ReportLab export
        csv_exporter.py     csv module export
    database/
        schema.sql          tables + indexes
        seed_data.py        first-launch defaults
    assets/
        icons/app_icon.png
        images/vehicle_placeholder.png
    tests/
        conftest.py                 fixtures (isolated temp data folder)
        test_auth.py                login, hashing, user administration
        test_vehicles.py            inventory, archiving, validation
        test_bookings.py            contracts, status flow, payments
        test_flood_risk.py          risk scoring, zones, alerts, dashboard
        test_tracking.py            routes, movement, water safety, GPS log import
        test_reports.py             report data, PDF and CSV export
        test_interface_imports.py   every interface module must import
```

Business logic (`app/`) is completely separated from the interface (`ui/`), so the same
functions are used by the GUI and by the tests.

## 5. Running the tests

```bat
.venv\Scripts\activate
pip install -r requirements-dev.txt
python -m pytest
```

The suite covers authentication/hashing, vehicles, bookings and payments, flood-risk
calculation and alerts, report/CSV/PDF export, and - importantly - imports **every**
interface module so a wrong import path can never stop the application from starting.
Tests redirect all data into a temporary folder, so they never touch `%LOCALAPPDATA%`.
The interface import tests are skipped automatically on systems where Tkinter is not
available (for example a headless build server); on Windows all of them run.

## 6. Building a Windows executable

Install the development requirements once, then run:

```bat
pyinstaller --noconfirm --clean --windowed --name FloodReadyVehicleSystem ^
  --add-data "database;database" ^
  --add-data "assets;assets" ^
  --hidden-import database.seed_data ^
  main.py
```

PowerShell version:

```powershell
pyinstaller --noconfirm --clean --windowed --name FloodReadyVehicleSystem `
  --add-data "database;database" `
  --add-data "assets;assets" `
  --hidden-import database.seed_data `
  main.py
```

The result in `dist\FloodReadyVehicleSystem\FloodReadyVehicleSystem.exe`:

* opens without a console window (`--windowed`);
* creates its local data folders and SQLite database automatically on first start;
* runs on a clean Windows computer without Python installed;
* shows a friendly message instead of crashing when the map is offline;
* does **not** include the tests, pytest, source databases, temporary files, logs or exported
  reports (use `--exclude-module pytest` if you want to be explicit).

### Portability limitation
The executable is built for **64-bit Windows 10 and Windows 11** only. A PyInstaller
executable must be built on the target operating system, so for macOS or Linux use the source
installation commands from section 2 instead:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python main.py
```

## 7. GPS tracking and offline behaviour

* **The demonstration feed moves the fleet.** Press **Start tracking** on the GPS page
  and every active vehicle drives along a real road corridor: EDSA, Commonwealth Avenue,
  Espana/Quezon Avenue, Roxas Boulevard, C5/Katipunan, Aurora Boulevard or Quirino Highway.
  Speeds are 18-34 km/h (Metro Manila traffic) and each vehicle keeps its route and speed
  between runs, so the demo is repeatable. The feed speed can be set to 1x, 4x, 8x or 16x,
  and **Reset positions** puts every unit back at the start of its route.
* **Vehicles never drive into the water.** Positions are interpolated along the road
  polyline and the routes were chosen on land - `app/tracking.py` contains a coarse water
  model (Manila Bay, Laguna de Bay) that the tests use to prove it. The only unit on the
  water is the rescue boat, which patrols the Pasig River because that is its job.
* Markers are moved in place (not rebuilt) so the animation stays smooth, and the selected
  vehicle leaves a trail on the map.
* Coordinates are **demonstration values** until a real feed is connected. To use real
  positions, press **Import GPS log** and choose a CSV file with the header
  `plate_number,latitude,longitude[,timestamp]`; unknown plates and invalid coordinates are
  skipped and reported. Individual positions can also be typed in the *Set GPS location*
  dialog on the Vehicles page.
* With internet: map tiles, vehicle markers coloured by flood risk, flood-zone circles and
  risk-link lines from high/severe vehicles to their nearest zone are drawn. Four map styles
  (OpenStreetMap streets, Carto light, Carto dark, OpenTopoMap) are available, and
  **Fit fleet** frames every positioned vehicle and zone at once.
* Without internet: the map area shows a clear "map tiles unavailable" message (or cached
  tiles when previously downloaded with **Cache map area**), while the risk summary, the
  coordinate table, the search and risk filters and the selected-vehicle assessment panel
  next to the map stay fully functional. The status bar also shows a green/red connectivity
  dot for the whole application.
* Flood-risk scoring is pure Python + SQLite and therefore always works offline.

Risk model: each vehicle is compared with every active flood zone using the haversine
distance. Inside a zone the full severity weight applies (`low 10 / moderate 30 / high 50 /
severe 70`); the weight decays linearly to zero at 5 km from the zone edge, and nearby zones
add a small bonus. The resulting score (0-100) is mapped to `low / moderate / high / severe`.

## 8. Troubleshooting

| Symptom | What to do |
| --- | --- |
| "Python was not found" | Install Python 3.11+ from python.org and tick *Add python.exe to PATH* |
| Map is grey / "map tiles unavailable" | The computer is offline; everything else still works. Use **Cache map area** while online |
| Vehicle picture does not appear | The picture is copied into `%LOCALAPPDATA%\FloodReadyVehicleSystem\images`; unsupported or damaged files are rejected with a message |
| Database error message | Check `%LOCALAPPDATA%\FloodReadyVehicleSystem\logs\application.log`; a backup can be created from **File → Backup database** |
| "The application interface could not be started" | The dialog shows the exact reason; the full traceback is in `logs\application.log`. Run `pip install -r requirements.txt` again inside `.venv` and start with `python main.py` |
| Forgot the admin password | Delete `data\rental_system.db` **and** keep a backup - a fresh database recreates `admin / admin123` on the next start |

Technical details are always written to `logs\application.log`; users only see short, friendly
messages, never raw Python tracebacks.
