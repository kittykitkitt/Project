import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";

export const metadata: Metadata = {
  title: "Flood Ready Vehicle System - Python/Tkinter desktop project",
  description:
    "Portable Python 3.11+ Tkinter + SQLite desktop application for vehicle rental operations with flood-risk monitoring. Browse the source or download the project ZIP.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-slate-100 text-slate-900 antialiased">{children}</body>
    </html>
  );
}
