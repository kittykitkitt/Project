import { StrictMode, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Activity,
  ArrowRight,
  Bell,
  CalendarRange,
  Car,
  CreditCard,
  Download,
  FileText,
  LayoutDashboard,
  MapPin,
  Settings,
  ShieldCheck,
  Users,
  Waves,
} from "lucide-react";
import "./index.css";
import appSource from "../public/flood_ready_vehicle_system/main.py?raw";

const modules = [
  [LayoutDashboard, "Dashboard", "A clear view of fleet, bookings and alerts."],
  [Car, "Vehicles", "Manage inventory, availability and locations."],
  [Users, "Customers", "Keep renter and licence records together."],
  [CalendarRange, "Bookings", "Track rentals, dates and booking status."],
  [CreditCard, "Transactions", "Record payments, deposits and refunds."],
  [MapPin, "GPS map", "View fleet positions and movement on a live map."],
  [Waves, "Flood zones", "Monitor flood-prone areas and severity."],
  [Bell, "Alerts", "Review notices and run fleet risk scans."],
  [FileText, "Reports", "Export fleet, booking and risk reports."],
  [ShieldCheck, "Users", "Manage roles and securely stored passwords."],
  [Settings, "Settings", "Set organisation, currency and alert defaults."],
] as const;

const risks = [
  { name: "Low", range: "0–19", value: 18, color: "#16805d" },
  { name: "Moderate", range: "20–39", value: 42, color: "#a77a10" },
  { name: "High", range: "40–59", value: 68, color: "#c56a25" },
  { name: "Severe", range: "60–100", value: 90, color: "#bb4b46" },
];

function downloadApp(): void {
  const blob = new Blob([appSource], { type: "text/x-python;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "main.py";
  document.body.append(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 2000);
}

function Site() {
  const [downloaded, setDownloaded] = useState(false);

  function handleDownload() {
    downloadApp();
    setDownloaded(true);
    window.setTimeout(() => setDownloaded(false), 2400);
  }

  return (
    <div className="min-h-screen bg-[#f7f8f6] text-[#172521]">
      <header className="sticky top-0 z-10 border-b border-[#e7ebe7] bg-[#f7f8f6]/95 backdrop-blur">
        <nav className="mx-auto flex h-14 max-w-6xl items-center justify-between px-5">
          <a href="#top" className="text-sm font-semibold tracking-tight">
            Flood Ready <span className="font-normal text-[#687771]">/ Vehicle System</span>
          </a>
          <div className="flex items-center gap-5 text-sm text-[#687771]">
            <a className="hidden hover:text-[#172521] sm:block" href="#features">Features</a>
            <a className="hidden hover:text-[#172521] sm:block" href="#setup">Setup</a>
            <button
              className="inline-flex items-center gap-2 rounded-md bg-[#176b50] px-3 py-2 font-medium text-white transition hover:bg-[#12583f]"
              onClick={handleDownload}
              type="button"
            >
              <Download size={16} />
              {downloaded ? "Downloaded" : "Get the app"}
            </button>
          </div>
        </nav>
      </header>

      <main id="top">
        <section className="mx-auto grid max-w-6xl items-center gap-12 px-5 py-16 sm:py-24 lg:grid-cols-[1fr_0.9fr]">
          <div>
            <p className="mb-4 text-xs font-semibold uppercase tracking-[0.18em] text-[#176b50]">
              Desktop app · Python · SQLite
            </p>
            <h1 className="max-w-xl text-4xl font-semibold leading-tight tracking-tight sm:text-5xl">
              Rental operations, ready for the rain.
            </h1>
            <p className="mt-5 max-w-xl text-base leading-7 text-[#687771]">
              A practical vehicle-rental system with fleet tracking and
              flood-risk monitoring. One Python file, local data, and offline
              access to every core feature.
            </p>
            <div className="mt-7 flex flex-wrap items-center gap-3">
              <button
                className="inline-flex items-center gap-2 rounded-md bg-[#176b50] px-4 py-2.5 text-sm font-medium text-white transition hover:bg-[#12583f]"
                onClick={handleDownload}
                type="button"
              >
                <Download size={16} />
                {downloaded ? "Saved to downloads" : "Download the .py"}
              </button>
              <a
                className="inline-flex items-center gap-2 rounded-md border border-[#d9e0da] px-4 py-2.5 text-sm font-medium text-[#34443d] transition hover:bg-white"
                href="#setup"
              >
                How to run it <ArrowRight size={15} />
              </a>
            </div>
            <p className="mt-4 text-xs text-[#78847e]">
              Python 3.11+ · Windows, macOS and Linux · no web server required
            </p>
          </div>

          <div className="rounded-lg border border-[#e3e8e3] bg-white p-4 shadow-sm sm:p-5">
            <div className="mb-4 flex items-center justify-between border-b border-[#edf0ed] pb-3">
              <span className="text-sm font-semibold">Example dashboard</span>
              <span className="flex items-center gap-1.5 text-xs text-[#687771]">
                <span className="h-2 w-2 rounded-full bg-[#16805d]" />
                Illustrative data
              </span>
            </div>
            <div className="grid grid-cols-3 gap-3">
              {[
                ["Vehicles", "24"],
                ["Bookings", "08"],
                ["Open alerts", "03"],
              ].map(([label, value]) => (
                <div key={label} className="rounded-md bg-[#f7f8f6] p-3">
                  <p className="text-xs text-[#78847e]">{label}</p>
                  <p className="mt-1 text-xl font-semibold">{value}</p>
                </div>
              ))}
            </div>
            <div className="mt-4 rounded-md border border-[#edf0ed] p-3">
              <div className="mb-3 flex items-center gap-2 text-xs font-medium text-[#687771]">
                <Activity size={14} /> Flood-risk distribution
              </div>
              <div className="space-y-2.5">
                {risks.map((risk) => (
                  <div key={risk.name} className="grid grid-cols-[72px_1fr_42px] items-center gap-2 text-xs">
                    <span className="text-[#687771]">{risk.name}</span>
                    <div className="h-1.5 overflow-hidden rounded bg-[#edf0ed]">
                      <div
                        className="h-full rounded"
                        style={{ width: `${risk.value}%`, backgroundColor: risk.color }}
                      />
                    </div>
                    <span className="text-right text-[#78847e]">{risk.range}</span>
                  </div>
                ))}
              </div>
            </div>
            <div className="mt-3 flex items-center gap-2 text-xs text-[#78847e]">
              <Activity size={14} /> SQLite data stays on your device
            </div>
          </div>
        </section>

        <section id="features" className="border-y border-[#e7ebe7] bg-white">
          <div className="mx-auto max-w-6xl px-5 py-14 sm:py-16">
            <div className="max-w-2xl">
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[#176b50]">
                One app, one file
              </p>
              <h2 className="mt-2 text-2xl font-semibold tracking-tight">
                The essentials for a ready fleet
              </h2>
            </div>
            <div className="mt-8 grid gap-x-8 gap-y-6 sm:grid-cols-2 lg:grid-cols-3">
              {modules.map(([Icon, name, description]) => (
                <article key={name} className="flex gap-3">
                  <Icon className="mt-0.5 shrink-0 text-[#176b50]" size={18} strokeWidth={1.8} />
                  <div>
                    <h3 className="text-sm font-semibold">{name}</h3>
                    <p className="mt-1 text-sm leading-6 text-[#687771]">{description}</p>
                  </div>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section className="mx-auto grid max-w-6xl gap-10 px-5 py-14 sm:py-16 lg:grid-cols-2">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[#176b50]">
              Flood-risk model
            </p>
            <h2 className="mt-2 text-2xl font-semibold tracking-tight">
              Understand risk at a glance
            </h2>
            <p className="mt-3 text-sm leading-6 text-[#687771]">
              Vehicles are scored against active flood zones using distance,
              severity and proximity. Scoring runs locally and works offline.
            </p>
            <div className="mt-6 space-y-4">
              {risks.map((risk) => (
                <div key={risk.name} className="grid grid-cols-[80px_1fr_64px] items-center gap-3">
                  <span className="text-sm text-[#34443d]">{risk.name}</span>
                  <div className="h-2 overflow-hidden rounded bg-[#e8ece8]">
                    <div
                      className="h-full rounded"
                      style={{ width: `${risk.value}%`, backgroundColor: risk.color }}
                    />
                  </div>
                  <span className="text-right text-xs text-[#78847e]">{risk.range}</span>
                </div>
              ))}
            </div>
          </div>
          <div id="setup" className="rounded-lg border border-[#e3e8e3] bg-white p-5 sm:p-6">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[#176b50]">
              Get started
            </p>
            <h2 className="mt-2 text-2xl font-semibold tracking-tight">Run it locally</h2>
            <ol className="mt-5 space-y-4 text-sm">
              <li className="flex gap-3">
                <span className="font-mono text-[#176b50]">01</span>
                <span>Install Python 3.11 or newer with Tkinter.</span>
              </li>
              <li className="flex gap-3">
                <span className="font-mono text-[#176b50]">02</span>
                <span>Download the single Python file above.</span>
              </li>
              <li className="flex gap-3">
                <span className="font-mono text-[#176b50]">03</span>
                <span>
                  Run <code className="rounded bg-[#f0f3f0] px-1.5 py-0.5">python main.py</code>
                </span>
              </li>
            </ol>
            <p className="mt-5 border-t border-[#edf0ed] pt-4 text-xs leading-5 text-[#78847e]">
              Map tiles, vehicle images and PDF export are optional extras.
              The app and its SQLite data work without them. Default sign-in:
              <span className="ml-1 font-medium text-[#34443d]">admin / admin123</span>
              {" "}— change the password after signing in.
            </p>
            <p className="mt-3 text-xs text-[#78847e]">
              Optional features:{" "}
              <code className="rounded bg-[#f0f3f0] px-1.5 py-0.5">
                python -m pip install tkintermapview reportlab
              </code>
            </p>
          </div>
        </section>

        <section className="border-y border-[#e7ebe7] bg-white">
          <div className="mx-auto max-w-6xl px-5 py-12">
            <details className="group">
              <summary className="cursor-pointer list-none text-sm font-semibold">
                View the Python source
                <span className="ml-2 text-xs font-normal text-[#78847e]">
                  {appSource.split("\n").length.toLocaleString()} lines · one file
                </span>
              </summary>
              <pre className="mt-4 max-h-[32rem] overflow-auto rounded-md bg-[#172521] p-4 text-xs leading-5 text-[#e1e9e3]">
                <code>{appSource}</code>
              </pre>
            </details>
          </div>
        </section>
      </main>

      <footer className="mx-auto flex max-w-6xl flex-col gap-2 px-5 py-7 text-xs text-[#78847e] sm:flex-row sm:items-center sm:justify-between">
        <span>Flood Ready Vehicle System</span>
        <span className="flex items-center gap-1.5">
          <MapPin size={13} /> Local-first · OpenStreetMap
        </span>
      </footer>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Site />
  </StrictMode>,
);
