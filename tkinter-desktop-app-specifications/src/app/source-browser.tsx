"use client";

import { useEffect, useMemo, useState } from "react";
import type { ProjectFile } from "@/lib/project";

type Props = {
  files: ProjectFile[];
  initialPath: string;
  initialContent: string;
};

export default function SourceBrowser({ files, initialPath, initialContent }: Props) {
  const [selected, setSelected] = useState(initialPath);
  const [content, setContent] = useState(initialContent);
  const [loading, setLoading] = useState(false);

  const groups = useMemo(() => {
    const map = new Map<string, ProjectFile[]>();
    for (const file of files) {
      const list = map.get(file.directory) ?? [];
      list.push(file);
      map.set(file.directory, list);
    }
    return [...map.entries()].sort((a, b) => {
      if (a[0] === ".") return -1;
      if (b[0] === ".") return 1;
      return a[0].localeCompare(b[0]);
    });
  }, [files]);

  const current = files.find((file) => file.path === selected);

  useEffect(() => {
    if (!current || current.binary) return;
    let cancelled = false;
    setLoading(true);
    fetch(`/api/source?path=${encodeURIComponent(selected)}`)
      .then((response) => response.json())
      .then((data: { content?: string }) => {
        if (!cancelled && typeof data.content === "string") setContent(data.content);
      })
      .catch(() => {
        if (!cancelled) setContent("// The file could not be loaded.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selected, current]);

  const lines = content ? content.split("\n") : [];

  return (
    <section className="mt-10 rounded-3xl border border-slate-200 bg-white p-4 shadow-[0_18px_50px_rgba(16,24,40,0.08)] sm:p-6">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-xl font-semibold text-slate-900">Project source</h2>
        <p className="text-sm text-slate-500">
          {files.length} files · browse the complete Python project
        </p>
      </div>

      <div className="mt-5 grid gap-5 lg:grid-cols-[280px_minmax(0,1fr)]">
        <div className="max-h-[560px] overflow-auto rounded-2xl border border-slate-200 bg-slate-50 p-3">
          {groups.map(([directory, group]) => (
            <div key={directory} className="mb-3">
              <p className="px-2 pb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                {directory === "." ? "flood_ready_vehicle_system/" : `${directory}/`}
              </p>
              <ul className="space-y-0.5">
                {group.map((file) => (
                  <li key={file.path}>
                    <button
                      type="button"
                      onClick={() => {
                        setSelected(file.path);
                        setContent(file.binary ? "" : content);
                      }}
                      className={`w-full truncate rounded-lg px-2 py-1.5 text-left text-sm transition ${
                        selected === file.path
                          ? "bg-blue-600 text-white shadow-sm"
                          : "text-slate-700 hover:bg-white hover:text-blue-700"
                      }`}
                    >
                      {file.name}
                      {file.binary ? " 🖼" : ""}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div className="min-w-0">
          <div className="flex flex-wrap items-center justify-between gap-2 rounded-t-2xl bg-slate-900 px-4 py-2.5 text-slate-200">
            <code className="text-sm">flood_ready_vehicle_system/{selected}</code>
            <span className="text-xs text-slate-400">
              {current?.binary
                ? "binary asset (PNG)"
                : `${current?.lines ?? 0} lines · ${current?.language ?? "text"}`}
            </span>
          </div>
          <div className="max-h-[520px] overflow-auto rounded-b-2xl border border-t-0 border-slate-800 bg-slate-950">
            {current?.binary ? (
              <div className="p-6 text-sm text-slate-300">
                Binary image asset. It is bundled with the project and used by Tkinter/Pillow
                for the window icon and the vehicle picture placeholder.
              </div>
            ) : (
              <pre className="min-w-full p-0 text-[12.5px] leading-[1.55]">
                <code className="block font-mono">
                  {loading && !content ? (
                    <span className="p-4 text-slate-400">Loading…</span>
                  ) : (
                    lines.map((line, index) => (
                      <span key={index} className="flex">
                        <span className="w-12 shrink-0 select-none border-r border-slate-800 px-2 text-right text-slate-600">
                          {index + 1}
                        </span>
                        <span className="whitespace-pre px-3 text-slate-200">
                          {line || " "}
                        </span>
                      </span>
                    ))
                  )}
                </code>
              </pre>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
