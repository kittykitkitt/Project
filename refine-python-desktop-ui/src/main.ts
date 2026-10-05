/**
 * Plain TypeScript entry point — no React, no framework.
 *
 * The deliverable is the Python desktop application (main.py). This page only
 * documents it, previews its interface, and hands over the single file.
 */
import "./index.css";
import appSource from "../main.py?raw";

const NAV: [string, string, string, boolean, string?][] = [
  ["Overview", "Dashboard", "◉", true],
  ["Operations", "Vehicles", "▤", false],
  ["Operations", "Customers", "☰", false],
  ["Operations", "Bookings", "▦", false],
  ["Operations", "Transactions", "₱", false],
  ["Monitoring", "GPS map", "⌖", false],
  ["Monitoring", "Flood zones", "◈", false],
  ["Monitoring", "Alerts", "⚑", false, "2"],
  ["Administration", "Reports", "≣", false],
  ["Administration", "Users", "◆", false],
  ["Administration", "Settings", "⚙", false],
];

const COLLECTIONS: [string, number][] = [
  ["Sep", 148],
  ["Oct", 186],
  ["Nov", 132],
  ["Dec", 214],
  ["Jan", 248],
  ["Feb", 176],
];

const RISKS: [string, number, string][] = [
  ["Low", 3, "var(--ok)"],
  ["Moderate", 2, "var(--warn)"],
  ["High", 3, "#c1703a"],
  ["Severe", 2, "var(--danger)"],
];

const MODULES: [string, string, string][] = [
  ["◉", "Dashboard", "Fleet counts, collections by month, risk distribution and nearest-zone exposure in one view."],
  ["▤", "Vehicles", "Inventory with status, rate, GPS position and live distance to the closest flood zone."],
  ["☰", "Customers", "Renter records, identification type, licence reference and contact details."],
  ["▦", "Bookings", "Rental periods, destinations, deposits and running totals with status filters."],
  ["₱", "Transactions", "Payments, deposits and refunds broken down by method, with a net cash figure."],
  ["⌖", "GPS map", "Vector basemap of Metro Manila — drag to pan, scroll to zoom, toggle layers."],
  ["◈", "Flood zones", "Monitored areas with severity scores, radius in kilometres and exposed units."],
  ["⚑", "Alerts", "Notices from the flood scan, staff and maintenance, with acknowledge and resolve."],
  ["≣", "Reports", "Six ledgers exported to CSV with timestamped filenames that never overwrite."],
  ["◆", "Users", "Accounts and roles. Passwords are PBKDF2-hashed with 260,000 iterations."],
  ["⚙", "Settings", "Organisation details, defaults, the data folder and one-click database backup."],
];

function icon(name: "download" | "copy" | "check" | "minus" | "square" | "x"): string {
  const paths: Record<string, string> = {
    download: "M12 3v12m0 0 4-4m-4 4-4-4M4 19h16",
    copy: "M9 9V5a1 1 0 0 1 1-1h9a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1h-4M5 9h9a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1v-9a1 1 0 0 1 1-1Z",
    check: "m5 13 4 4L19 7",
    minus: "M5 12h14",
    square: "M6 6h12v12H6z",
    x: "M6 6l12 12M18 6 6 18",
  };
  return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9"
    stroke-linecap="round" stroke-linejoin="round"><path d="${paths[name]}"/></svg>`;
}

function sidebar(): string {
  const groups: string[] = [];
  for (const group of [...new Set(NAV.map((item) => item[0]))]) {
    const items = NAV.filter((item) => item[0] === group)
      .map(
        ([, label, glyph, active, badge]) => `
        <div class="nav-item${active ? " active" : ""}">
          <i>${glyph}</i><span>${label}</span>
          ${badge ? `<span class="badge">${badge}</span>` : ""}
        </div>`
      )
      .join("");
    groups.push(`<div class="nav-group"><p>${group}</p>${items}</div>`);
  }
  return groups.join("");
}

function mapSvg(): string {
  const roads = [
    "M318 40 352 130 430 210 560 268 690 330 790 420 836 540",
    "M520 90 600 190 700 280 820 400 872 520",
    "M430 150 700 150",
    "M350 300 470 220 590 152",
    "M176 300 214 470 268 660",
    "M420 520 560 640 700 780",
    "M600 430 830 300",
    "M700 470 900 600",
    "M420 330 700 350",
  ];
  const zones: [number, number, number, string][] = [
    [350, 288, 56, "#b64f4a"],
    [100, 86, 93, "#b64f4a"],
    [566, 241, 70, "#c1703a"],
    [400, 412, 37, "#b3882a"],
    [907, 408, 116, "#b64f4a"],
    [800, 350, 84, "#c1703a"],
  ];
  const units: [number, number, string][] = [
    [331, 278, "#0e7c5b"],
    [371, 317, "#3468c0"],
    [72, 60, "#3468c0"],
    [550, 143, "#0e7c5b"],
    [300, 446, "#b3882a"],
    [330, 355, "#0e7c5b"],
    [650, 84, "#0e7c5b"],
    [501, 584, "#3468c0"],
    [696, 400, "#0e7c5b"],
    [200, 523, "#b3882a"],
  ];
  return `
  <svg viewBox="60 20 880 720" role="img" aria-label="Metro Manila fleet map">
    <rect x="-200" y="-200" width="1500" height="1400" fill="#dfe9e8"/>
    <path d="M96 40 150 160 140 300 176 420 196 560 176 700 120 900 1200 900 1200 -100 96 -100Z" fill="#f8f8f4"/>
    <ellipse cx="880" cy="950" rx="430" ry="210" fill="#dfe9e8" stroke="#cfdedb"/>
    <ellipse cx="392" cy="392" rx="34" ry="26" fill="#e4ecdf"/>
    <ellipse cx="560" cy="124" rx="48" ry="30" fill="#e4ecdf"/>
    <ellipse cx="744" cy="560" rx="40" ry="28" fill="#e4ecdf"/>
    ${roads.map((d) => `<path d="${d}" fill="none" stroke="#e2e5dd" stroke-width="7" stroke-linecap="round"/>`).join("")}
    ${roads.map((d) => `<path d="${d}" fill="none" stroke="#fff" stroke-width="3.4" stroke-linecap="round"/>`).join("")}
    ${zones
      .map(
        ([cx, cy, r, color]) =>
          `<circle cx="${cx}" cy="${cy}" r="${r}" fill="${color}" fill-opacity="0.08"/>
           <circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="${color}" stroke-opacity="0.5"
                   stroke-width="1.2" stroke-dasharray="5 4"/>
           <circle cx="${cx}" cy="${cy}" r="3.2" fill="${color}"/>`
      )
      .join("")}
    ${["MANILA|350|313", "QUEZON CITY|540|150", "MAKATI|512|594", "PASIG|800|437", "MALABON|110|122"]
      .map(
        (item) =>
          `<text x="${item.split("|")[1]}" y="${item.split("|")[2]}" text-anchor="middle" font-size="10"
             letter-spacing="1.4" fill="#a9b0a9" font-family="Inter, sans-serif" font-weight="500">${item.split("|")[0]}</text>`
      )
      .join("")}
    ${units
      .map(
        ([cx, cy, color]) =>
          `<circle cx="${cx}" cy="${cy}" r="4.6" fill="#fff" stroke="${color}" stroke-width="2.4"/>`
      )
      .join("")}
    <rect x="74" y="700" width="86" height="22" rx="5" fill="#fff" stroke="#e6e8e3"/>
    <rect x="80" y="709" width="46" height="3" rx="1.5" fill="#4e5a54"/>
    <text x="130" y="715" font-size="9" fill="#8b948e" font-family="Inter, sans-serif">5 km</text>
  </svg>`;
}

function windowPreview(): string {
  const peak = Math.max(...COLLECTIONS.map((item) => item[1]));
  return `
  <div class="window">
    <div class="titlebar">
      <span class="mark">◈</span>
      <p>Flood Ready Vehicle System — System Administrator</p>
      <span class="spacer"></span>
      <button class="wbtn" title="Minimise">${icon("minus")}</button>
      <button class="wbtn" title="Maximise">${icon("square")}</button>
      <button class="wbtn close" title="Close">${icon("x")}</button>
    </div>
    <div class="menubar">
      <b>File</b><b>Help</b>
      <span class="kbd">Search records <code>Ctrl K</code></span>
    </div>
    <div class="shell">
      <aside class="sidebar">
        <div class="brand">
          <strong>Flood Ready<br/>Vehicle System</strong>
          <span>PYTHON · v1.2.0</span>
        </div>
        <nav class="nav">${sidebar()}</nav>
        <div class="usercard">
          <strong>System Administrator</strong>
          <span>Admin</span>
          <button>Sign out</button>
        </div>
      </aside>
      <div class="content">
        <div class="page-head">
          <div>
            <h2>Dashboard</h2>
            <p>Fleet, bookings and flood risk at a glance · Saturday, 14 February 2026</p>
          </div>
          <span class="chip"><span class="dot"></span> Last GPS sync 07:56</span>
        </div>
        <div class="grid-4">
          ${[
            ["Vehicles", "10", "7 available · 2 rented · 1 in shop"],
            ["Active bookings", "09", "3 on the road · 3 scheduled"],
            ["Booking value", "₱79,700", "9 booking records"],
            ["Open alerts", "02", "Unacknowledged notices"],
          ]
            .map(([label, value, meta]) => `<div class="tile"><p>${label}</p><h3>${value}</h3><small>${meta}</small></div>`)
            .join("")}
        </div>
        <div class="grid-2">
          <div class="card">
            <h4>Collections by month</h4>
            <p class="hint">Net cash movement recorded in each month, in thousands</p>
            <div class="bars">
              ${COLLECTIONS.map(
                ([month, value]) =>
                  `<div><i style="height:${(value / peak) * 100}%"></i><span>${month}</span></div>`
              ).join("")}
            </div>
          </div>
          <div class="card">
            <h4>Flood-risk distribution</h4>
            <p class="hint">Units grouped by the risk of their nearest active zone</p>
            ${RISKS.map(
              ([label, count, color]) =>
                `<div class="meter-row"><span>${label}</span><span class="meter"><i style="width:${
                  (count / 10) * 100
                }%;background:${color}"></i></span><em>${count}</em></div>`
            ).join("")}
          </div>
        </div>
        <div class="grid-2">
          <div class="card">
            <h4>Fleet positions</h4>
            <p class="hint">Live positions with active flood zones overlaid</p>
            <div class="map">${mapSvg()}</div>
          </div>
          <div class="card">
            <h4>Nearest flood exposure</h4>
            <p class="hint">Distance from each unit to its closest active zone</p>
            ${[
              ["Toyota Vios 1.5 G", "España Boulevard Corridor", "0.42", true, "#b64f4a"],
              ["Suzuki Ertiga GL", "Governor Forbes – Lacson", "1.28", false, "#b3882a"],
              ["Hyundai H350 Shuttle", "Kalayaan Avenue", "2.11", false, "#c1703a"],
              ["Honda Click 125i", "España Boulevard Corridor", "0.19", true, "#b64f4a"],
              ["Toyota Innova J", "España Boulevard Corridor", "0.86", false, "#b64f4a"],
            ]
              .map(
                ([unit, zone, km, inside, color]) => `
                <div class="meter-row" style="grid-template-columns:3px 1fr auto auto">
                  <i style="width:3px;height:20px;border-radius:2px;background:${color}"></i>
                  <span style="line-height:1.35">
                    <strong style="display:block;font-weight:500;color:var(--ink)">${unit}</strong>
                    <small style="font-size:11px;color:var(--muted)">${zone}</small>
                  </span>
                  <em>${km} km</em>
                  <em style="color:${inside ? "var(--danger)" : "var(--muted)"};font-size:10px;letter-spacing:.06em">${
                    inside ? "INSIDE" : "CLEAR"
                  }</em>
                </div>`
              )
              .join("")}
          </div>
        </div>
      </div>
    </div>
    <div class="statusbar">
      <span class="dot"></span><span>Internet connection available</span>
      <span class="sep"></span><span>Rainline Rentals</span>
      <span class="right">
        <span class="path">%LOCALAPPDATA%\\FloodReadyVehicleSystem</span>
        <span class="sep"></span>
        <span>System Administrator (admin)</span>
      </span>
    </div>
  </div>`;
}

function page(): string {
  return `
  <div class="hero">
    <div class="wrap hero-inner">
      <div>
        <p class="eyebrow">Python desktop application · Tkinter · SQLite</p>
        <h1>Rental operations,<br/>ready for the rain.</h1>
        <p class="lede">
          Flood Ready Vehicle System is a single-file desktop application for a
          vehicle rental business: fleet records, bookings, payments, GPS
          tracking and flood-risk monitoring for Metro Manila. Standard library
          only — nothing to install, nothing to sign up for.
        </p>
        <div class="actions">
          <button class="btn btn-primary" id="download">${icon("download")} Download main.py</button>
          <button class="btn btn-ghost" id="copy">${icon("copy")} Copy source</button>
        </div>
        <div class="terminal">
          <div class="terminal-head"><span></span><span></span><span></span></div>
          <pre><span class="prompt">$</span> python main.py
<span class="note"># optional — build every page offscreen and check the services</span>
<span class="prompt">$</span> python main.py --smoke-test</pre>
        </div>
        <div class="meta">
          <div><strong>Python 3.9+</strong>Windows, macOS, Linux</div>
          <div><strong>0 dependencies</strong>Tkinter + SQLite only</div>
          <div><strong>Offline</strong>Data stays on your machine</div>
          <div><strong>1 file</strong>${(appSource.split("\n").length).toLocaleString()} lines</div>
        </div>
      </div>
      <div>${windowPreview()}</div>
    </div>
  </div>

  <section class="section">
    <div class="wrap">
      <h3>Eleven modules, one window</h3>
      <p class="sub">
        A sidebar groups the workflow into overview, operations, monitoring and
        administration. Every page is built from the same pieces — hairline
        cards, striped tables and slim meters — so the interface stays quiet
        while the data changes.
      </p>
      <div class="modules">
        ${MODULES.map(
          ([glyph, title, body]) =>
            `<article class="module"><span>${glyph}</span><h4>${title}</h4><p>${body}</p></article>`
        ).join("")}
      </div>
    </div>
  </section>

  <section class="section">
    <div class="wrap">
      <h3>Built to be run, not hosted</h3>
      <p class="sub">
        Launch it with <code class="mono">python main.py</code>. The database,
        exports and logs are created inside your own user profile on first run,
        and a portable data folder can be pointed anywhere.
      </p>
      <div class="notes">
        <div class="note-card">
          <h4>Where your data lives</h4>
          <table class="paths">
            <tr><td>Windows</td><td>%LOCALAPPDATA%\\FloodReadyVehicleSystem</td></tr>
            <tr><td>Linux</td><td>$XDG_DATA_HOME/FloodReadyVehicleSystem</td></tr>
            <tr><td>Portable</td><td>FLOODREADY_DATA_DIR=&lt;any folder&gt;</td></tr>
            <tr><td>Database</td><td>data/rental_system.db</td></tr>
            <tr><td>Exports</td><td>exports/*.csv</td></tr>
            <tr><td>Log</td><td>logs/application.log</td></tr>
          </table>
        </div>
        <div class="note-card">
          <h4>How the map works</h4>
          <p>
            The map is drawn on a plain <code>tk.Canvas</code> with an
            equirectangular projection tuned so one kilometre is the same length
            on both axes. Flood-zone rings are therefore true to scale, and the
            haversine formula decides whether a unit counts as exposed.
          </p>
          <ul>
            <li>Drag to pan, mouse wheel to zoom, reset to return</li>
            <li>Layer toggles for vehicles, zones and place labels</li>
            <li>Click a marker to focus a unit in the side panel</li>
          </ul>
        </div>
        <div class="note-card">
          <h4>Sign in and security</h4>
          <p>
            The first run seeds an admin account. Passwords are stored as
            PBKDF2-HMAC-SHA256 with a fresh 16-byte salt per user and 260,000
            iterations, compared in constant time.
          </p>
          <p style="margin-top:10px">
            Default login is <code>admin</code> / <code>admin123</code> — change
            it from the Users page once you are in.
          </p>
        </div>
      </div>
    </div>
  </section>

  <footer>
    <div class="wrap" style="display:flex;flex-wrap:wrap;gap:12px;align-items:center;justify-content:space-between">
      <span>Flood Ready Vehicle System v1.2.0 · Tkinter interface, SQLite storage, map data © OpenStreetMap contributors</span>
      <a href="https://github.com/kittykitkitt/Project/tree/main/Gps%20Project" target="_blank" rel="noreferrer">View the repository ↗</a>
    </div>
  </footer>
  <div class="toast" id="toast"></div>`;
}

function toast(message: string): void {
  const node = document.getElementById("toast");
  if (!node) return;
  node.textContent = message;
  node.classList.add("show");
  window.setTimeout(() => node.classList.remove("show"), 2200);
}

function download(): void {
  const blob = new Blob([appSource], { type: "text/x-python;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "main.py";
  document.body.append(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 2000);
  toast("main.py saved — run it with: python main.py");
}

async function copySource(): Promise<void> {
  try {
    await navigator.clipboard.writeText(appSource);
    toast(`Copied ${(appSource.length / 1024).toFixed(0)} KB of Python to the clipboard`);
  } catch {
    toast("Clipboard blocked by the browser — use Download instead");
  }
}

document.body.innerHTML = page();
document.getElementById("download")?.addEventListener("click", download);
document.getElementById("copy")?.addEventListener("click", () => void copySource());
