import { readdir, readFile, stat } from "node:fs/promises";
import path from "node:path";

export const PROJECT_DIR = path.join(process.cwd(), "flood_ready_vehicle_system");

const IGNORED = new Set([
  "__pycache__",
  ".pytest_cache",
  ".mypy_cache",
  ".ruff_cache",
  ".coverage",
  ".venv",
  "venv",
  "build",
  "dist",
  "app_data",
  "node_modules",
  ".git",
]);

const TEXT_EXTENSIONS = new Set([
  ".py",
  ".sql",
  ".md",
  ".txt",
  ".bat",
  ".gitignore",
  ".json",
  ".cfg",
  ".ini",
]);

export type ProjectFile = {
  path: string;
  directory: string;
  name: string;
  bytes: number;
  lines: number;
  language: string;
  binary: boolean;
};

export function languageFor(file: string): string {
  const extension = path.extname(file).toLowerCase();
  if (extension === ".py") return "python";
  if (extension === ".sql") return "sql";
  if (extension === ".md") return "markdown";
  if (extension === ".bat") return "batch";
  if (extension === ".png" || extension === ".jpg" || extension === ".jpeg") return "image";
  if (extension === ".txt") return "text";
  return "text";
}

function isTextFile(file: string): boolean {
  if (file.endsWith(".gitignore") || file.endsWith("requirements.txt")) return true;
  return TEXT_EXTENSIONS.has(path.extname(file).toLowerCase());
}

async function walk(directory: string, collected: string[] = []): Promise<string[]> {
  const entries = await readdir(directory, { withFileTypes: true });
  for (const entry of entries) {
    if (IGNORED.has(entry.name)) continue;
    const absolute = path.join(directory, entry.name);
    if (entry.isDirectory()) {
      await walk(absolute, collected);
    } else if (entry.isFile()) {
      collected.push(absolute);
    }
  }
  return collected;
}

export async function listProjectFiles(): Promise<ProjectFile[]> {
  const absolutePaths = await walk(PROJECT_DIR);
  const files: ProjectFile[] = [];
  for (const absolute of absolutePaths) {
    const relative = path.relative(PROJECT_DIR, absolute).split(path.sep).join("/");
    const info = await stat(absolute);
    const binary = !isTextFile(relative);
    let lines = 0;
    if (!binary) {
      const content = await readFile(absolute, "utf8");
      lines = content.split("\n").length;
    }
    files.push({
      path: relative,
      directory: relative.includes("/") ? relative.slice(0, relative.lastIndexOf("/")) : ".",
      name: path.basename(relative),
      bytes: info.size,
      lines,
      language: languageFor(relative),
      binary,
    });
  }
  return files.sort((a, b) => a.path.localeCompare(b.path));
}

export async function readProjectFile(relative: string): Promise<string | null> {
  const normalised = path.normalize(relative).replace(/^([.][.][/\\])+/, "");
  const absolute = path.join(PROJECT_DIR, normalised);
  if (!absolute.startsWith(PROJECT_DIR)) return null;
  try {
    const info = await stat(absolute);
    if (!info.isFile()) return null;
    if (!isTextFile(normalised)) return null;
    return await readFile(absolute, "utf8");
  } catch {
    return null;
  }
}

export async function projectStats() {
  const files = await listProjectFiles();
  const textFiles = files.filter((file) => !file.binary);
  return {
    files,
    totals: {
      files: files.length,
      python: files.filter((file) => file.language === "python").length,
      tests: files.filter((file) => file.path.startsWith("tests/")).length,
      lines: textFiles.reduce((total, file) => total + file.lines, 0),
      kilobytes: Math.round(
        textFiles.reduce((total, file) => total + file.bytes, 0) / 102.4,
      ) / 10,
    },
  };
}
