import { readFile } from "node:fs/promises";
import path from "node:path";
import JSZip from "jszip";
import { db } from "@/db";
import { downloadEvents } from "@/db/schema";
import { PROJECT_DIR, listProjectFiles } from "@/lib/project";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const zip = new JSZip();
    const files = await listProjectFiles();
    for (const file of files) {
      const buffer = await readFile(path.join(PROJECT_DIR, file.path));
      zip.file(`flood_ready_vehicle_system/${file.path}`, buffer);
    }
    const archive = await zip.generateAsync({ type: "uint8array" });

    try {
      await db.insert(downloadEvents).values({ artifact: "flood_ready_vehicle_system" });
    } catch {
      // The download still works even if the counter table is unavailable.
    }

    const blob = new Blob([new Uint8Array(archive)], { type: "application/zip" });
    return new Response(blob, {
      headers: {
        "Content-Type": "application/zip",
        "Content-Disposition": 'attachment; filename="flood_ready_vehicle_system.zip"',
        "Cache-Control": "no-store",
      },
    });
  } catch {
    return Response.json({ error: "The archive could not be created." }, { status: 500 });
  }
}
