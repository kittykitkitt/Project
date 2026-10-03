"""GPS map page with a live demonstration tracking feed.

The map uses OpenStreetMap tiles from the internet.  Vehicles can be moved along
real Metro Manila road corridors (see :mod:`app.tracking`) so the fleet actually
drives somewhere, and the rescue boat patrols the Pasig River.  When the
computer is offline the page stays fully usable: coordinates, flood-risk scores
and the assessment details are always available, previously cached tiles are
used when available, and a clear message replaces the map otherwise.

Positions are demonstration values until a real GPS log is imported.
"""
from __future__ import annotations

import logging
import math
import threading
import urllib.request
from typing import Any

import tkinter as tk
from tkinter import ttk

from app import AppError
from app.config import (
    DEFAULT_CENTER,
    DEFAULT_ZOOM,
    MAP_CACHE_DIR,
    OFFLINE_CHECK_URL,
    OFFLINE_TIMEOUT,
    RISK_LEVELS,
)
from app.services import RISK_WEIGHTS, assess_position
from . import Page
from .dialogs import show_error, show_info, show_warning
from .styles import PALETTE, RISK_COLORS, make_treeview, page_header

log = logging.getLogger(__name__)

CACHE_DB = MAP_CACHE_DIR / "offline_tiles.db"
OFFLINE_MESSAGE = (
    "Map tiles are unavailable - this computer appears to be offline and no cached "
    "tiles have been stored yet.\n\n"
    "Vehicle positions, flood-risk scores and the live feed still work in the table "
    "on the right. Use \"Cache map area\" while online to store tiles for later use.")

TILE_SERVERS: list[tuple[str, str]] = [
    ("Streets (OpenStreetMap)", "https://a.tile.openstreetmap.org/{z}/{x}/{y}.png"),
    ("Light (Carto)", "https://cartodb-basemaps-a.global.ssl.fastly.net/light_all/{z}/{x}/{y}.png"),
    ("Dark (Carto)", "https://cartodb-basemaps-a.global.ssl.fastly.net/dark_all/{z}/{x}/{y}.png"),
    ("Topographic (OpenTopoMap)", "https://a.tile.opentopomap.org/{z}/{x}/{y}.png"),
]
DEFAULT_TILE_SERVER = TILE_SERVERS[0][1]

ZOOM_SPANS = ((0.02, 16), (0.05, 15), (0.10, 14), (0.25, 13), (0.60, 12),
              (1.50, 11), (4.00, 10), (99.0, 9))

RISK_FILTERS: list[tuple[str, str]] = [
    ("All vehicles", ""),
    ("High and severe only", "high"),
    ("Severe only", "severe"),
    ("Vehicles without GPS", "unknown"),
]


def check_internet(timeout: int | None = None) -> bool:
    """Small, dependency free connectivity probe (never raises)."""
    try:
        request = urllib.request.Request(
            OFFLINE_CHECK_URL, method="HEAD",
            headers={"User-Agent": "FloodReadyVehicleSystem/1.0"})
        with urllib.request.urlopen(request, timeout=timeout or OFFLINE_TIMEOUT):
            return True
    except Exception:
        return False


def circle_points(latitude: float, longitude: float, radius_km: float,
                  steps: int = 36) -> list[tuple[float, float]]:
    """Approximate a circle of *radius_km* around a coordinate."""
    dlat = radius_km / 111.32
    cosine = math.cos(math.radians(latitude))
    dlon = radius_km / (111.32 * cosine) if abs(cosine) > 0.01 else 0.0
    return [(latitude + dlat * math.sin(2 * math.pi * index / steps),
             longitude + dlon * math.cos(2 * math.pi * index / steps))
            for index in range(steps)]


def zoom_for_span(span_degrees: float) -> int:
    for limit, zoom in ZOOM_SPANS:
        if span_degrees <= limit:
            return zoom
    return DEFAULT_ZOOM


class GpsMapPage(Page):
    TITLE = "GPS Map"
    SUBTITLE = "Live demonstration feed with a flood-risk overlay"
    ICON = "\u25c9"

    TICK_MS = 1500          # wall clock between feed updates
    TICK_SECONDS = 3        # simulated seconds per update at 1x
    TRAIL_POINTS = 24       # positions kept per vehicle for the trail
    TRACK_SPEEDS: list[tuple[str, int]] = [("1x real time", 1), ("4x", 4),
                                           ("8x", 8), ("16x", 16)]

    def __init__(self, parent: tk.Widget, app: Any) -> None:
        super().__init__(parent, app)
        self.map_widget: Any = None
        self.rows: list[dict[str, Any]] = []
        self.zones: list[dict[str, Any]] = []
        self.status_var = tk.StringVar(value="Checking...")
        self.tracking_var = tk.StringVar(value="Demonstration feed stopped")
        self.search_var = tk.StringVar()
        self.risk_filter_var = tk.StringVar(value=RISK_FILTERS[0][0])
        self.tile_var = tk.StringVar(value=TILE_SERVERS[0][0])
        self.speed_var = tk.StringVar(value="4x")
        self.show_vehicles_var = tk.BooleanVar(value=True)
        self.show_zones_var = tk.BooleanVar(value=True)
        self.show_links_var = tk.BooleanVar(value=True)
        self.summary_vars: dict[str, tk.StringVar] = {}
        self._tracking = False
        self._tick_job: str | None = None
        self._marker_objects: dict[int, Any] = {}
        self.trails: dict[int, list[tuple[float, float]]] = {}

    # ------------------------------------------------------------------ layout
    def build(self) -> None:
        page_header(self, f"{self.ICON}  {self.TITLE}", self.SUBTITLE).pack(fill="x")
        self._build_toolbar().pack(fill="x")
        self._build_body().pack(fill="both", expand=True, pady=(12, 0))
        ttk.Frame(self, style="Page.TFrame", height=12).pack()
        self.after(200, self._initialise_map)

    def _build_toolbar(self) -> ttk.Frame:
        bar = ttk.Frame(self, style="Card.TFrame", padding=(16, 10))
        bar.columnconfigure(14, weight=1)

        self.tracking_button = ttk.Button(bar, text="\u25b6  Start tracking",
                                          style="Primary.TButton",
                                          command=self.toggle_tracking)
        self.tracking_button.grid(row=0, column=0, padx=(0, 8))
        speed_box = ttk.Combobox(bar, textvariable=self.speed_var, state="readonly",
                                 width=8,
                                 values=[label for label, _v in self.TRACK_SPEEDS])
        speed_box.grid(row=0, column=1, padx=(0, 8))
        ttk.Button(bar, text="Fit fleet", style="Secondary.TButton",
                   command=self.fit_fleet).grid(row=0, column=2, padx=(0, 4))
        ttk.Button(bar, text="+", style="Secondary.TButton", width=3,
                   command=self.zoom_in).grid(row=0, column=3, padx=(0, 4))
        ttk.Button(bar, text="\u2013", style="Secondary.TButton", width=3,
                   command=self.zoom_out).grid(row=0, column=4, padx=(0, 8))
        style_box = ttk.Combobox(bar, textvariable=self.tile_var, state="readonly",
                                 width=20,
                                 values=[label for label, _url in TILE_SERVERS])
        style_box.grid(row=0, column=5, padx=(0, 10))
        style_box.bind("<<ComboboxSelected>>", lambda _e: self.change_tile_server())
        for index, (label, variable) in enumerate(
                (("Vehicles", self.show_vehicles_var),
                 ("Flood zones", self.show_zones_var),
                 ("Risk links", self.show_links_var))):
            ttk.Checkbutton(bar, text=label, variable=variable,
                            command=self.draw_map).grid(row=0, column=6 + index,
                                                        padx=(0, 10))
        ttk.Button(bar, text="Cache tiles", style="Secondary.TButton",
                   command=self.cache_area).grid(row=0, column=9, padx=(0, 8))
        ttk.Button(bar, text="Import log", style="Secondary.TButton",
                   command=self.import_gps_log).grid(row=0, column=10, padx=(0, 8))
        ttk.Button(bar, text="Reset", style="Secondary.TButton",
                   command=self.reset_positions).grid(row=0, column=11, padx=(0, 12))
        self.status_dot = tk.Label(bar, text="\u25cf", background=PALETTE["card"],
                                   foreground=PALETTE["muted"],
                                   font=("Segoe UI", 12, "bold"))
        self.status_dot.grid(row=0, column=12, sticky="e")
        ttk.Label(bar, textvariable=self.status_var,
                  style="CardMuted.TLabel").grid(row=0, column=13, sticky="e",
                                                 padx=(5, 0))
        ttk.Label(bar, textvariable=self.tracking_var,
                  style="CardMuted.TLabel").grid(row=0, column=14, sticky="e",
                                                 padx=(14, 0))

        return bar

    def _build_body(self) -> ttk.Frame:
        body = ttk.Frame(self, style="Card.TFrame", padding=(16, 12))
        body.columnconfigure(0, weight=5, uniform="map")
        body.columnconfigure(1, weight=4, uniform="map")
        body.rowconfigure(1, weight=1)

        self.map_frame = tk.Frame(body, background="#dfe8f2", bd=1, relief="solid")
        self.map_frame.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=(0, 14))
        self._build_map_placeholder()

        summary = ttk.Labelframe(body, text="  Fleet risk  ", padding=(10, 6))
        summary.grid(row=0, column=1, sticky="ew")
        chip_row = ttk.Frame(summary, style="Card.TFrame")
        chip_row.pack(fill="x")
        for level in (*RISK_LEVELS, "unknown"):
            frame = ttk.Frame(chip_row, style="Card.TFrame")
            frame.pack(side="left", padx=(0, 10))
            var = tk.StringVar(value="0")
            self.summary_vars[level] = var
            tk.Label(frame, text="\u25cf", background=PALETTE["card"],
                     foreground=RISK_COLORS.get(level, PALETTE["muted"]),
                     font=("Segoe UI", 13, "bold")).pack(side="left")
            ttk.Label(frame, textvariable=var, style="Value.TLabel",
                      font=("Segoe UI", 13, "bold")).pack(side="left", padx=(4, 4))
            ttk.Label(frame, text=level.title(), style="CardMuted.TLabel").pack(
                side="left")


        table_bar = ttk.Frame(body, style="Card.TFrame")
        table_bar.grid(row=1, column=1, sticky="nsew")
        table_bar.columnconfigure(1, weight=1)
        search_entry = ttk.Entry(table_bar, textvariable=self.search_var, width=20)
        search_entry.grid(row=0, column=1, sticky="e", padx=(10, 6), pady=(6, 0))
        search_entry.bind("<Return>", lambda _event: self.refresh())
        risk_box = ttk.Combobox(table_bar, textvariable=self.risk_filter_var,
                                state="readonly", width=20,
                                values=[label for label, _v in RISK_FILTERS])
        risk_box.grid(row=0, column=2, sticky="e", pady=(6, 0))
        risk_box.bind("<<ComboboxSelected>>", lambda _e: self.refresh())
        self._table_container = ttk.Frame(table_bar, style="Card.TFrame")
        self._table_container.grid(row=1, column=0, columnspan=3, sticky="nsew",
                                   pady=(8, 0))
        table_bar.rowconfigure(1, weight=1)

        self._build_table()
        self._build_detail_panel(table_bar)
        return body

    def _build_map_placeholder(self) -> None:
        placeholder = ttk.Frame(self.map_frame, style="Card.TFrame", padding=30)
        placeholder.pack(fill="both", expand=True)
        ttk.Label(placeholder, text="\u25c9", style="H1.TLabel",
                  font=("Segoe UI", 26, "bold")).pack(anchor="w")
        ttk.Label(placeholder, text="Preparing the map...",
                  style="CardMuted.TLabel", wraplength=420,
                  justify="left").pack(anchor="w", pady=(8, 0))

    def _build_table(self) -> None:
        for child in self._table_container.winfo_children():
            child.destroy()
        frame, tree = make_treeview(
            self._table_container,
            [("plate_number", "Plate", 95, "w"),
             ("vehicle", "Vehicle", 140, "w"),
             ("status", "Status", 85, "w"),
             ("risk", "Flood risk", 85, "w"),
             ("score", "Score", 55, "center"),
             ("zone", "Nearest flood zone", 140, "w"),
             ("latitude", "Latitude", 80, "e"),
             ("longitude", "Longitude", 80, "e")],
            height=9)
        frame.pack(fill="both", expand=True)
        self.tree = tree
        tree.bind("<Double-1>", lambda _event: self.focus_selected())
        tree.bind("<<TreeviewSelect>>", lambda _event: self._show_details())

    def _build_detail_panel(self, parent: tk.Widget) -> None:
        """Flood-risk assessment of the vehicle selected in the table."""
        panel = ttk.Labelframe(parent, text="  Selected vehicle  ",
                               style="Card.TFrame", padding=(12, 8))
        panel.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        grid = ttk.Frame(panel, style="Card.TFrame")
        grid.pack(fill="x")
        grid.columnconfigure(1, weight=1)
        grid.columnconfigure(3, weight=1)
        self._detail_vars: dict[str, tk.StringVar] = {}
        fields = [("plate", "Plate"), ("vehicle", "Vehicle"),
                  ("status", "Status"), ("risk", "Risk"),
                  ("zone", "Nearest zone"), ("distance", "Distance"),
                  ("route", "Route"), ("speed", "Speed"),
                  ("position", "Position")]
        for index, (name, label) in enumerate(fields):
            row, column = divmod(index, 2)
            ttk.Label(grid, text=label, style="Field.TLabel").grid(
                row=row, column=column * 2, sticky="w", padx=(0, 8), pady=3)
            var = tk.StringVar(value="-")
            self._detail_vars[name] = var
            ttk.Label(grid, textvariable=var, style="Value.TLabel").grid(
                row=row, column=column * 2 + 1, sticky="w", padx=(0, 18), pady=3)
        self._reasons_var = tk.StringVar(
            value="Select a vehicle to see its flood-risk assessment.")
        ttk.Label(panel, textvariable=self._reasons_var, style="CardMuted.TLabel",
                  wraplength=620, justify="left").pack(anchor="w", pady=(8, 0))
        actions = ttk.Frame(panel, style="Card.TFrame")
        actions.pack(fill="x", pady=(8, 0))
        ttk.Button(actions, text="Centre map", style="Secondary.TButton",
                   command=self.focus_selected).pack(side="left")

    # --------------------------------------------------------------------- map
    def map_centre(self) -> tuple[float, float, int]:
        try:
            latitude = float(self.db.setting("map_center_latitude", str(DEFAULT_CENTER[0])))
            longitude = float(self.db.setting("map_center_longitude", str(DEFAULT_CENTER[1])))
            zoom = int(self.db.setting("map_zoom", str(DEFAULT_ZOOM)))
        except (TypeError, ValueError):
            return DEFAULT_CENTER[0], DEFAULT_CENTER[1], DEFAULT_ZOOM
        return latitude, longitude, zoom

    def tile_server_url(self) -> str:
        for label, url in TILE_SERVERS:
            if label == self.tile_var.get():
                return url
        return DEFAULT_TILE_SERVER

    def change_tile_server(self) -> None:
        if self.map_widget is None:
            return
        try:
            self.map_widget.set_tile_server(self.tile_server_url(), max_zoom=18)
        except Exception as exc:  # pragma: no cover - widget specific
            log.debug("Tile server change failed: %s", exc)

    def _initialise_map(self) -> None:
        online = check_internet()
        if online or CACHE_DB.exists():
            self._create_map(use_cache_only=not online)
        else:
            self._show_offline_message(OFFLINE_MESSAGE)
        self.refresh()

    def _show_offline_message(self, message: str) -> None:
        for child in self.map_frame.winfo_children():
            child.destroy()
        self.map_widget = None
        self._marker_objects = {}
        frame = ttk.Frame(self.map_frame, style="Card.TFrame", padding=30)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="\u26c8  Map unavailable",
                  style="H1.TLabel").pack(anchor="w")
        ttk.Label(frame, text=message, style="CardMuted.TLabel", wraplength=440,
                  justify="left").pack(anchor="w", pady=(10, 0))
        ttk.Button(frame, text="Try again", style="Secondary.TButton",
                   command=self._initialise_map).pack(anchor="w", pady=(16, 0))
        self._set_status("Offline", PALETTE["danger"])

    def _create_map(self, use_cache_only: bool = False) -> None:
        for child in self.map_frame.winfo_children():
            child.destroy()
        self.map_widget = None
        self._marker_objects = {}
        try:
            from tkintermapview import TkinterMapView
        except Exception as exc:
            log.error("TkinterMapView is unavailable: %s", exc)
            self._show_offline_message(
                "The map module (tkintermapview) could not be loaded.\n"
                "Install it with:  pip install tkintermapview")
            return
        try:
            if use_cache_only and CACHE_DB.exists():
                self.map_widget = TkinterMapView(
                    self.map_frame, corner_radius=0, use_database_only=True,
                    max_zoom=14, database_path=str(CACHE_DB))
                self._set_status("Cached tiles", PALETTE["warning"])
            else:
                self.map_widget = TkinterMapView(self.map_frame, corner_radius=0)
                self._set_status("Online", PALETTE["ok"])
        except Exception as exc:
            log.exception("Map widget could not be created")
            self._show_offline_message(f"The map could not be started.\n({exc})")
            return
        try:
            latitude, longitude, zoom = self.map_centre()
            self.map_widget.pack(fill="both", expand=True)
            self.map_widget.set_position(latitude, longitude)
            self.map_widget.set_zoom(zoom)
            self.map_widget.set_tile_server(self.tile_server_url(), max_zoom=18)
        except Exception as exc:
            log.exception("Map could not be initialised")
            self.map_widget = None
            self._show_offline_message(f"The map could not be initialised.\n({exc})")
            return

    def _set_status(self, text: str, colour: str) -> None:
        self.status_var.set(text)
        try:
            self.status_dot.configure(foreground=colour)
        except AttributeError:  # pragma: no cover - toolbar not built yet
            pass

    # -------------------------------------------------------------------- data
    def refresh(self) -> None:
        self._load_rows()
        self._render_table()
        self.draw_map()
        self._show_details()

    def _load_rows(self) -> None:
        self.zones = self.services.zones.list_zones(active_only=True)
        self.rows = []
        for vehicle in self.services.vehicles.list_vehicles():
            assessment = assess_position(
                float(vehicle["latitude"] or 0), float(vehicle["longitude"] or 0),
                self.zones)
            vehicle["assessment"] = assessment
            vehicle["risk"] = assessment["level"]
            vehicle["risk_score"] = (assessment["score"] if assessment["has_position"]
                                     else "-")
            vehicle["zone"] = assessment["nearest_zone"]
            vehicle["distance"] = (f"{assessment['distance_km']:.2f} km"
                                   if assessment["has_position"] else "-")
            self.rows.append(vehicle)
        counts = {level: 0 for level in (*RISK_LEVELS, "unknown")}
        for row in self.rows:
            counts[str(row["risk"])] = counts.get(str(row["risk"]), 0) + 1
        for level, var in self.summary_vars.items():
            var.set(str(counts.get(level, 0)))

    def _render_table(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for index, row in enumerate(self._visible_rows()):
            self.tree.insert(
                "", "end",
                tags=[str(row["risk"]), "stripe" if index % 2 else ""],
                values=[row["plate_number"], f"{row['brand']} {row['model']}",
                        row["status"], row["risk"], row["risk_score"],
                        row["zone"] or "-",
                        f"{float(row['latitude'] or 0):.5f}",
                        f"{float(row['longitude'] or 0):.5f}"])

    def _visible_rows(self) -> list[dict[str, Any]]:
        term = self.search_var.get().strip().lower()
        risk = ""
        for label, value in RISK_FILTERS:
            if label == self.risk_filter_var.get():
                risk = value
        rows = []
        for row in self.rows:
            if term and term not in " ".join(str(row.get(key, "")) for key in (
                    "plate_number", "brand", "model", "status", "zone")).lower():
                continue
            if risk == "unknown":
                if str(row["risk"]) != "unknown":
                    continue
            elif risk and RISK_WEIGHTS.get(str(row["risk"]), 0) < RISK_WEIGHTS[risk]:
                continue
            rows.append(row)
        return rows

    # --------------------------------------------------------------------- map
    def draw_map(self) -> None:
        """Full redraw: zone circles, markers, risk links and the trail."""
        if self.map_widget is None:
            return
        try:
            self.map_widget.delete_all_marker()
            self._marker_objects = {}
            try:
                self.map_widget.delete_all_polygon()
            except Exception:  # pragma: no cover - older widget versions
                pass
            if self.show_zones_var.get():
                for zone in self.zones:
                    colour = RISK_COLORS.get(str(zone["risk_level"]), PALETTE["muted"])
                    self._draw_polygon(
                        circle_points(float(zone["latitude"]), float(zone["longitude"]),
                                      float(zone["radius_km"] or 1)), colour)
                    self._draw_marker(float(zone["latitude"]), float(zone["longitude"]),
                                      f"{zone['name']} ({zone['risk_level']})",
                                      colour, prefix="\u26c8")
            if self.show_vehicles_var.get():
                for row in self._visible_rows():
                    latitude = float(row["latitude"] or 0)
                    longitude = float(row["longitude"] or 0)
                    if not latitude or not longitude:
                        continue
                    colour = RISK_COLORS.get(str(row["risk"]), PALETTE["accent"])
                    marker = self._draw_marker(
                        latitude, longitude,
                        f"{row['plate_number']} - {row['risk']} risk", colour)
                    if marker is not None:
                        self._marker_objects[int(row["id"])] = marker
            self._draw_overlays()
        except Exception as exc:
            log.exception("Could not draw map markers")
            self._set_status(f"Map drawing problem: {exc}", PALETTE["danger"])

    def _animate_markers(self) -> None:
        """Move the existing markers instead of rebuilding them (smooth feed)."""
        if self.map_widget is None:
            return
        visible = {int(row["id"]): row for row in self._visible_rows()
                   if float(row["latitude"] or 0) and float(row["longitude"] or 0)}
        if set(visible) != set(self._marker_objects):
            self.draw_map()
            return
        try:
            for vehicle_id, row in visible.items():
                marker = self._marker_objects[vehicle_id]
                marker.set_position(float(row["latitude"]), float(row["longitude"]))
                marker.set_text(f"{row['plate_number']} - {row['risk']} risk")
        except Exception:
            self.draw_map()
            return
        self._draw_overlays()

    def _draw_overlays(self) -> None:
        """Risk link lines and the trail of the selected vehicle."""
        if self.map_widget is None:
            return
        try:
            self.map_widget.delete_all_path()
        except Exception:  # pragma: no cover - older widget versions
            pass
        if self.show_links_var.get():
            for row in self._visible_rows():
                if RISK_WEIGHTS.get(str(row["risk"]), 0) < RISK_WEIGHTS["high"]:
                    continue
                nearest = self._zone_named(str(row["zone"]))
                if nearest is not None:
                    colour = RISK_COLORS.get(str(row["risk"]), PALETTE["accent"])
                    self._draw_path([(float(row["latitude"]), float(row["longitude"])),
                                     (float(nearest["latitude"]),
                                      float(nearest["longitude"]))], colour)
        trail = self._selected_trail()
        if len(trail) >= 2:
            self._draw_path(trail, PALETTE["accent"], width=3)

    def _zone_named(self, name: str) -> dict[str, Any] | None:
        for zone in self.zones:
            if str(zone["name"]) == name:
                return zone
        return None

    def _draw_marker(self, latitude: float, longitude: float, text: str,
                     colour: str, prefix: str = "") -> Any:
        label = f"{prefix} {text}".strip()
        try:
            return self.map_widget.set_marker(
                latitude, longitude, text=label, marker_color_circle=colour,
                marker_color_outside=PALETTE["card"])
        except Exception:
            try:
                return self.map_widget.set_marker(latitude, longitude, label)
            except Exception:  # pragma: no cover - widget specific
                log.debug("Marker could not be drawn", exc_info=True)
        return None

    def _draw_polygon(self, points: list[tuple[float, float]], colour: str) -> None:
        try:
            self.map_widget.set_polygon(points, fill_color=colour,
                                        outline_color=colour, border_width=2,
                                        is_visible=True)
        except Exception:
            try:
                self.map_widget.set_polygon(points)
            except Exception:  # pragma: no cover - widget specific
                log.debug("Polygon could not be drawn", exc_info=True)

    def _draw_path(self, points: list[tuple[float, float]], colour: str,
                   width: int = 2) -> None:
        try:
            self.map_widget.set_path(points, color=colour, width=width)
        except Exception:  # pragma: no cover - widget specific
            log.debug("Path could not be drawn", exc_info=True)

    # ------------------------------------------------------------ live tracking
    def _speed_value(self) -> int:
        for label, value in self.TRACK_SPEEDS:
            if label == self.speed_var.get():
                return value
        return 4

    def toggle_tracking(self) -> None:
        """Start or stop the demonstration GPS feed."""
        if self._tracking:
            self._stop_tracking()
            return
        try:
            count = self.services.tracking.start()
        except AppError as exc:
            show_error(str(exc), self)
            return
        self._tracking = True
        self.trails = {}
        for row in self.rows:
            self.trails[int(row["id"])] = [(float(row["latitude"] or 0),
                                            float(row["longitude"] or 0))]
        self.tracking_button.configure(text="\u23f8  Stop tracking",
                                       style="Danger.TButton")
        self._set_tracking_status(count)
        self.refresh()
        self._schedule_tick()

    def _stop_tracking(self) -> None:
        self._tracking = False
        if self._tick_job is not None:
            try:
                self.after_cancel(self._tick_job)
            except tk.TclError:  # pragma: no cover - widget already gone
                pass
            self._tick_job = None
        self.services.tracking.stop()
        self.tracking_button.configure(text="\u25b6  Start tracking",
                                       style="Primary.TButton")
        self.tracking_var.set("Tracking stopped")

    def _schedule_tick(self) -> None:
        try:
            self._tick_job = self.after(self.TICK_MS, self._tick)
        except tk.TclError:  # pragma: no cover - page destroyed
            self._tracking = False

    def _tick(self) -> None:
        if not self._tracking:
            return
        try:
            self.services.tracking.step(self.TICK_SECONDS * self._speed_value())
            self._load_rows()
            self._render_table()
            self._record_trails()
            self._animate_markers()
            self._show_details()
            self._set_tracking_status(len(self.rows))
            self._tick_job = self.after(self.TICK_MS, self._tick)
        except tk.TclError:  # pragma: no cover - page destroyed (sign out)
            self._tracking = False
        except AppError as exc:
            show_error(str(exc), self)
            self._stop_tracking()

    def _record_trails(self) -> None:
        for row in self.rows:
            latitude = float(row["latitude"] or 0)
            longitude = float(row["longitude"] or 0)
            if not latitude or not longitude:
                continue
            trail = self.trails.setdefault(int(row["id"]), [])
            trail.append((latitude, longitude))
            if len(trail) > self.TRAIL_POINTS:
                del trail[:len(trail) - self.TRAIL_POINTS]

    def _selected_trail(self) -> list[tuple[float, float]]:
        row = self.selected_row()
        if row is None:
            return []
        return self.trails.get(int(row["id"]), [])

    def _set_tracking_status(self, count: int) -> None:
        minutes, seconds = divmod(int(self.services.tracking.elapsed_seconds), 60)
        self.tracking_var.set(
            f"Live: {count} vehicles  \u00b7  {self._speed_value()}x  \u00b7  "
            f"{minutes:02d}:{seconds:02d}")

    def reset_positions(self) -> None:
        """Place every vehicle back at the start of its route."""
        self._stop_tracking()
        try:
            count = self.services.tracking.reset()
        except AppError as exc:
            show_error(str(exc), self)
            return
        self.trails = {}
        self.refresh()
        show_info(f"{count} vehicle(s) were placed back at the start of their "
                  "route.", self)

    def import_gps_log(self) -> None:
        """Use real positions from a CSV GPS log instead of the demo feed."""
        from tkinter import filedialog

        source = filedialog.askopenfilename(
            parent=self, title="Import GPS log (CSV)",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if not source:
            return
        self._stop_tracking()
        try:
            updated = self.services.tracking.apply_gps_log(source)
        except AppError as exc:
            show_error(str(exc), self)
            return
        self.trails = {}
        self.refresh()
        show_info(f"{updated} vehicle position(s) were updated from the GPS log.\n\n"
                  "Expected columns: plate_number, latitude, longitude.", self)

    # ----------------------------------------------------------------- actions
    def selected_row(self) -> dict[str, Any] | None:
        selection = self.tree.selection()
        if not selection:
            return None
        index = self.tree.index(selection[0])
        rows = self._visible_rows()
        return rows[index] if 0 <= index < len(rows) else None

    def _show_details(self) -> None:
        row = self.selected_row()
        if row is None:
            for var in self._detail_vars.values():
                var.set("-")
            self._reasons_var.set("Select a vehicle in the table to see its "
                                  "flood-risk assessment.")
            return
        assessment = row["assessment"]
        tracking = self.services.tracking.status()
        feed = tracking.get(int(row["id"]), {})
        values = {
            "plate": row["plate_number"],
            "vehicle": f"{row['brand']} {row['model']}",
            "status": str(row["status"]).title(),
            "risk": f"{str(row['risk']).title()} ({row['risk_score']}/100)",
            "distance": row["distance"],
            "zone": row["zone"] or "-",
            "route": feed.get("route", "-"),
            "speed": (f"{feed['speed_kmh']:.0f} km/h, {feed['direction']}"
                      if feed else "-"),
            "position": (f"{float(row['latitude'] or 0):.5f}, "
                         f"{float(row['longitude'] or 0):.5f}"),
        }
        for name, value in values.items():
            self._detail_vars[name].set(str(value))
        self._reasons_var.set(" ".join(assessment["reasons"]))

    def focus_selected(self) -> None:
        row = self.selected_row()
        if row is None:
            show_warning("Select a vehicle in the table first.", self)
            return
        latitude = float(row["latitude"] or 0)
        longitude = float(row["longitude"] or 0)
        if self.map_widget is None:
            show_warning("The map is unavailable, so the vehicle cannot be centred. "
                         "Its coordinates are shown in the detail panel.", self)
            return
        if not latitude or not longitude:
            show_warning("No GPS coordinates are recorded for this vehicle.", self)
            return
        try:
            self.map_widget.set_position(latitude, longitude)
            self.map_widget.set_zoom(15)
        except Exception as exc:  # pragma: no cover - defensive
            log.debug("Could not focus the map: %s", exc)

    def fit_fleet(self) -> None:
        """Centre and zoom the map so every positioned vehicle is visible."""
        if self.map_widget is None:
            show_warning("The map is not available.", self)
            return
        positions = [(float(row["latitude"] or 0), float(row["longitude"] or 0))
                     for row in self.rows]
        positions = [(lat, lon) for lat, lon in positions if lat or lon]
        if not positions:
            show_warning("No vehicle has GPS coordinates recorded yet.", self)
            return
        for zone in self.zones:
            positions.append((float(zone["latitude"]), float(zone["longitude"])))
        latitudes = [position[0] for position in positions]
        longitudes = [position[1] for position in positions]
        span = max(max(latitudes) - min(latitudes), max(longitudes) - min(longitudes))
        try:
            self.map_widget.set_position((max(latitudes) + min(latitudes)) / 2,
                                         (max(longitudes) + min(longitudes)) / 2)
            self.map_widget.set_zoom(zoom_for_span(span))
        except Exception as exc:  # pragma: no cover - defensive
            log.debug("Could not fit the map: %s", exc)

    def zoom_in(self) -> None:
        if self.map_widget is not None:
            try:
                self.map_widget.set_zoom(min(19, int(self.map_widget.zoom) + 1))
            except Exception:  # pragma: no cover - widget specific
                pass

    def zoom_out(self) -> None:
        if self.map_widget is not None:
            try:
                self.map_widget.set_zoom(max(1, int(self.map_widget.zoom) - 1))
            except Exception:  # pragma: no cover - widget specific
                pass

    def cache_area(self) -> None:
        """Store OpenStreetMap tiles locally so the map also works offline."""
        if not check_internet():
            show_warning(
                "An internet connection is required to download map tiles.\n"
                "Everything else in the application keeps working offline.", self)
            return
        MAP_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self._set_status("Downloading map tiles for offline use - please wait...",
                         PALETTE["warning"])

        def worker() -> None:
            try:
                import tkintermapview

                loader = tkintermapview.OfflineLoader(path=str(CACHE_DB),
                                                      tile_server=DEFAULT_TILE_SERVER)
                centre_lat, centre_lon, _zoom = self.map_centre()
                loader.save_offline_tiles((centre_lat + 0.2, centre_lon - 0.3),
                                          (centre_lat - 0.2, centre_lon + 0.3), 10, 14)
                message = "Tiles cached"
                colour = PALETTE["ok"]
            except Exception as exc:
                log.exception("Offline tile caching failed")
                message = f"Tile caching failed: {exc}"
                colour = PALETTE["danger"]
            try:
                self.after(0, lambda: self._set_status(message, colour))
            except Exception:  # pragma: no cover - page already destroyed
                log.debug("Tile cache status update skipped")

        threading.Thread(target=worker, daemon=True).start()
