export default function App() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-[#FAFAF8] p-8">
      <div className="max-w-xl space-y-8 rounded-2xl border border-[#E6E8E3] bg-white p-10 shadow-sm">
        <div className="flex items-center gap-4">
          <div className="flex h-12 w-12 items-center justify-center rounded-full bg-[#ECF4F0] text-[#0E7C5B] text-xl">
            ◈
          </div>
          <div>
            <h1 className="text-2xl font-semibold text-[#161B18]">
              Flood Ready Vehicle System
            </h1>
            <p className="text-sm text-[#8B948E]">
              Python / Tkinter desktop application
            </p>
          </div>
        </div>

        <p className="text-[#4E5A54]">
          The desktop application has been loaded into this project. It is a
          single-file Python app using Tkinter and SQLite, with no third-party
          dependencies.
        </p>

        <div className="space-y-3 rounded-lg bg-[#F4F5F2] p-5">
          <p className="text-sm font-medium text-[#161B18]">Run it locally</p>
          <code className="block rounded bg-white px-4 py-3 text-sm text-[#0E7C5B]">
            python main.py
          </code>
          <p className="text-xs text-[#8B948E]">
            Default login: <span className="font-medium">admin</span> /{" "}
            <span className="font-medium">admin123</span>
          </p>
        </div>

        <div className="grid gap-4 text-sm text-[#4E5A54] sm:grid-cols-2">
          <div className="rounded-lg border border-[#E6E8E3] p-4">
            <p className="font-medium text-[#161B18]">Dashboard</p>
            <p className="mt-1">Fleet counts, collections, risk distribution</p>
          </div>
          <div className="rounded-lg border border-[#E6E8E3] p-4">
            <p className="font-medium text-[#161B18]">GPS Map</p>
            <p className="mt-1">Metro Manila vector map with flood zones</p>
          </div>
          <div className="rounded-lg border border-[#E6E8E3] p-4">
            <p className="font-medium text-[#161B18]">Vehicles & Bookings</p>
            <p className="mt-1">Rental inventory and transaction tracking</p>
          </div>
          <div className="rounded-lg border border-[#E6E8E3] p-4">
            <p className="font-medium text-[#161B18]">Reports & Alerts</p>
            <p className="mt-1">CSV exports and flood-risk notifications</p>
          </div>
        </div>
      </div>
    </div>
  );
}
