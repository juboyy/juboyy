// Vercel serverless function — GET /api/health
export default function handler(_req, res) {
  res.status(200).json({
    ok: true,
    aiConfigured: Boolean(process.env.ANTHROPIC_API_KEY),
    model: process.env.VIRAL_MODEL || "claude-opus-4-8",
  });
}
