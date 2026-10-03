import { sql } from "drizzle-orm";
import { db } from "@/db";
import { downloadEvents } from "@/db/schema";
import { projectStats, readProjectFile } from "@/lib/project";
import SourceBrowser from "./source-browser";

export const dynamic = "force-dynamic";

const MODULES: { title: string; detail: string; icon: string }[] = [
  { title: "Dashboard", detail: "Icon cards, revenue chart, risk distribution, returns due", icon: "▦" },
  { title: "Vehicles", detail: "Inventory, rates, pictures, GPS position, archive/restore", icon: "▤" },
  { title: "Customers", detail: "Renter records with ID and licence details", icon: "☺" },
  { title: "Bookings", detail: "Contracts, day/rate totals, overlap protection, status flow", icon: "▥" },
  { title: "Transactions", detail: "Payments, deposits, refunds with date filters", icon: "₱" },
  { title: "GPS Map", detail: "Live feed: cars drive real roads, boat patrols the river", icon: "◉" },
  { title: "Flood Zones", detail: "Severity, radius and monitoring on/off", icon: "⛈" },
  { title: "Alerts", detail: "Automatic fleet scan plus manual notices", icon: "⚠" },
  { title: "Reports", detail: "PDF (ReportLab) and CSV exports with on-screen preview", icon: "≡" },
  { title: "Users", detail: "PBKDF2 hashing, roles, password resets", icon: "▸" },
  { title: "Settings", detail: "Map centre, currency, alert threshold, backup", icon: "⚙" },
  { title: "Tests", detail: "pytest suite: services, exports, flood risk and interface imports", icon: "✓" },
];

const CHECKS = [
  "python main.py starts and the GUI opens with one consistent ttk theme",
  "Database, folders, default admin and vehicle catalog created automatically (once)",
  "Login works with PBKDF2 salted hashes - no plain-text passwords",
  "All sidebar pages open; Treeview tables load with search, filters and archive toggles",
  "Add / edit / view / archive / restore actions work on every module",
  "Vehicles drive along real road corridors and never enter the bay - proven by tests",
  "Flood-risk maths, the risk distribution and alerts work with no internet connection",
  "GPS page degrades to a clear offline message and keeps the coordinate table",
  "PDF and CSV exports write into %LOCALAPPDATA%\\FloodReadyVehicleSystem\\exports",
  "All paths built with pathlib from the install location - the folder can be moved",
  "Every interface module is import-checked by pytest, so a bad import cannot stop start-up",
  "Missing images, bad coordinates and database errors raise friendly message boxes",
  "requirements.txt holds only tkintermapview, Pillow and reportlab",
];

function Code({ children, label }: { children: string; label: string }) {
  return (
    <div className="min-w-0">
      <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
        {label}
      </p>
      <pre className="overflow-x-auto rounded-2xl bg-slate-950 p-4 text-[12.5px] leading-relaxed text-slate-200">
        <code className="font-mono">{children}</code>
      </pre>
    </div>
  );
}

export default async function HomePage() {
  const { files, totals } = await projectStats();
  const readme = (await readProjectFile("README.md")) ?? "";

  let downloads = 0;
  try {
    const [row] = await db
      .select({ count: sql<number>`count(*)::int` })
      .from(downloadEvents);
    downloads = row?.count ?? 0;
  } catch {
    downloads = 0;
  }

  return (
    <main className="mx-auto w-full max-w-6xl px-5 py-12 sm:px-8">
      <header className="rounded-3xl border border-slate-200 bg-white p-8 shadow-[0_24px_60px_rgba(16,24,40,0.10)] sm:p-10">
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-blue-700">
          Python 3.11+ · Tkinter · SQLite · Windows 10/11
        </p>
        <h1 className="mt-4 text-[clamp(2rem,4.6vw,3.1rem)] font-semibold leading-[1.05] text-slate-950">
          Flood Ready Vehicle System
        </h1>
        <p className="mt-4 max-w-3xl text-base text-slate-700">
          A clean, portable desktop application for vehicle rental operations with
          flood-risk monitoring. Standard Tkinter and <code>ttk</code> for the interface, the
          built-in <code>sqlite3</code> module for storage, TkinterMapView for the GPS map,
          Pillow for vehicle pictures and ReportLab for PDF reports. Everything works offline -
          only the map tiles need internet.
        </p>

        <div className="mt-7 flex flex-wrap items-center gap-3">
          <a
            href="/api/download"
            className="rounded-xl bg-blue-600 px-5 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-blue-700"
          >
            ⬇ Download project ZIP
          </a>
          <a
            href="#install"
            className="rounded-xl border border-slate-300 bg-white px-5 py-3 text-sm font-semibold text-slate-800 transition hover:border-blue-400 hover:text-blue-700"
          >
            Installation &amp; build
          </a>
          <span className="text-sm text-slate-500">
            {downloads > 0 ? `${downloads} download${downloads === 1 ? "" : "s"} so far` : "No downloads yet"}
          </span>
        </div>

        <dl className="mt-8 grid grid-cols-2 gap-4 sm:grid-cols-4">
          {[
            { label: "Project files", value: totals.files },
            { label: "Python modules", value: totals.python },
            { label: "Lines of code", value: totals.lines },
            { label: "Test files", value: totals.tests },
          ].map((stat) => (
            <div key={stat.label} className="rounded-2xl bg-slate-50 px-4 py-3">
              <dt className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                {stat.label}
              </dt>
              <dd className="mt-1 text-2xl font-semibold text-slate-900">{stat.value}</dd>
            </div>
          ))}
        </dl>
      </header>

      <section className="mt-10">
        <h2 className="text-xl font-semibold text-slate-900">Modules</h2>
        <div className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {MODULES.map((module) => (
            <article
              key={module.title}
              className="rounded-2xl border border-slate-200 bg-white p-5 shadow-[0_10px_30px_rgba(16,24,40,0.06)]"
            >
              <p className="text-lg" aria-hidden>
                {module.icon}
              </p>
              <h3 className="mt-1 text-base font-semibold text-slate-900">{module.title}</h3>
              <p className="mt-1 text-sm text-slate-600">{module.detail}</p>
            </article>
          ))}
        </div>
      </section>

      <section id="install" className="mt-10 grid gap-6 lg:grid-cols-2">
        <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-[0_18px_50px_rgba(16,24,40,0.08)]">
          <h2 className="text-xl font-semibold text-slate-900">Source installation</h2>
          <p className="mt-2 text-sm text-slate-600">
            Double-click <code>setup_windows.bat</code> or run the commands below. No
            administrator rights, no environment variables, no MySQL/PostgreSQL/Docker/Node.
          </p>
          <div className="mt-4 space-y-4">
            <Code label="setup_windows.bat does this for you">{`python -m venv .venv
.venv\\Scripts\\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python main.py`}</Code>
            <Code label="requirements.txt">{`tkintermapview
Pillow
reportlab`}</Code>
            <Code label="requirements-dev.txt (tests + packaging only)">{`-r requirements.txt
pytest
pyinstaller`}</Code>
          </div>
        </div>

        <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-[0_18px_50px_rgba(16,24,40,0.08)]">
          <h2 className="text-xl font-semibold text-slate-900">Windows executable</h2>
          <p className="mt-2 text-sm text-slate-600">
            Build on the target machine (64-bit Windows 10/11). The packaged app opens without a
            console window and creates its database and folders automatically.
          </p>
          <div className="mt-4 space-y-4">
            <Code label="PyInstaller">{`pyinstaller --noconfirm --clean --windowed --name FloodReadyVehicleSystem ^
  --add-data "database;database" ^
  --add-data "assets;assets" ^
  --hidden-import database.seed_data ^
  main.py`}</Code>
            <div className="rounded-2xl bg-slate-50 p-4">
              <h3 className="text-sm font-semibold text-slate-900">Data storage</h3>
              <pre className="mt-2 overflow-x-auto text-[12px] leading-relaxed text-slate-700">{`%LOCALAPPDATA%\\FloodReadyVehicleSystem\\
    data\\rental_system.db
    images\\
    exports\\pdf\\   exports\\csv\\
    logs\\application.log
    map_cache\\`}</pre>
              <p className="mt-3 text-sm text-slate-600">
                Editable data never lives inside the program folder. If
                <code> %LOCALAPPDATA%</code> is unavailable the app falls back to an
                <code> app_data</code> folder beside the source, so it also runs from a USB stick.
              </p>
            </div>
          </div>
        </div>
      </section>

      <section className="mt-10 rounded-3xl border border-slate-200 bg-white p-6 shadow-[0_18px_50px_rgba(16,24,40,0.08)] sm:p-8">
        <h2 className="text-xl font-semibold text-slate-900">Quality check</h2>
        <ul className="mt-4 grid gap-3 sm:grid-cols-2">
          {CHECKS.map((check) => (
            <li key={check} className="flex gap-3 text-sm text-slate-700">
              <span className="mt-0.5 text-green-600">✔</span>
              <span>{check}</span>
            </li>
          ))}
        </ul>
      </section>

      <SourceBrowser files={files} initialPath="README.md" initialContent={readme} />

      <footer className="mt-10 pb-6 text-center text-xs text-slate-500">
        Desktop application targets 64-bit Windows 10 and Windows 11 · macOS and Linux use the
        source installation · this page is the browser preview for the project.
      </footer>
    </main>
  );
}
