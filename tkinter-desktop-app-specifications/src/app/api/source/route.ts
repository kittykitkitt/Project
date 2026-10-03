import { readProjectFile } from "@/lib/project";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const url = new URL(request.url);
  const file = url.searchParams.get("path");
  if (!file) {
    return Response.json({ error: "Missing path parameter." }, { status: 400 });
  }
  const content = await readProjectFile(file);
  if (content === null) {
    return Response.json({ error: "File not found." }, { status: 404 });
  }
  return Response.json({ path: file, content });
}
