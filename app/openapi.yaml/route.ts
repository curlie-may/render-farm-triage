import fs from "node:fs";
import path from "node:path";

export const dynamic = "force-static";

/** Serves the repo's single-source openapi.yaml at /openapi.yaml, rather than
 * keeping a duplicate copy under public/ that would drift out of sync. This
 * route is force-static, so the file is read and embedded at build time —
 * no runtime file-system access on Vercel. */
export async function GET() {
  const filePath = path.join(process.cwd(), "openapi.yaml");
  const contents = fs.readFileSync(filePath, "utf-8");
  return new Response(contents, {
    status: 200,
    headers: { "Content-Type": "text/yaml; charset=utf-8" },
  });
}
