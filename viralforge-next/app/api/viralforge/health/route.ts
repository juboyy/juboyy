// Next.js App Router route handler — GET /api/viralforge/health
export const runtime = "nodejs";

export async function GET() {
  return Response.json({
    ok: true,
    provider: "anthropic",
    aiConfigured: Boolean(process.env.ANTHROPIC_API_KEY),
    model: process.env.VIRAL_MODEL || "claude-opus-4-8",
  });
}
