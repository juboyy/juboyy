import Anthropic from "@anthropic-ai/sdk";

// Next.js App Router route handler — POST /api/viralforge/generate
export const runtime = "nodejs";
export const maxDuration = 60;

const MODEL = process.env.VIRAL_MODEL || "claude-opus-4-8";

const VARIANT_SCHEMA = {
  type: "object",
  properties: {
    variants: {
      type: "array",
      items: {
        type: "object",
        properties: {
          format: { type: "string" },
          hook: { type: "string", description: "Primeira linha — gatilho de parada de scroll" },
          body: { type: "string", description: "Corpo com quebras de linha. Termina com pergunta/CTA. Sem links." },
          hashtags: { type: "array", items: { type: "string" } },
          aiPredictedScore: { type: "integer" },
          rationale: { type: "string" },
        },
        required: ["format", "hook", "body", "hashtags", "aiPredictedScore", "rationale"],
        additionalProperties: false,
      },
    },
  },
  required: ["variants"],
  additionalProperties: false,
};

function systemPrompt(niche: string) {
  return [
    "Você é um estrategista de viralidade no X (Twitter), especialista no nicho:",
    niche || "Agentes de IA, tech, ciência, consciência, build in public, money, hacks, insights",
    "",
    "Princípios inegociáveis ao escrever cada post:",
    "- O HOOK (primeira linha) é 80% do jogo: contrário, numérico/específico, loop de curiosidade aberto, ou stakes.",
    "- SEM links no corpo. Link vai no reply/bio.",
    "- Termine SEMPRE com pergunta ou CTA que puxe reply.",
    "- Frases curtas, quebras de linha, nada de parede de texto.",
    "- Opinião forte e específica. No máximo 2 hashtags. Português do Brasil, tom direto.",
  ].join("\n");
}

export async function POST(req: Request) {
  if (!process.env.ANTHROPIC_API_KEY) {
    return Response.json(
      { error: "ANTHROPIC_API_KEY não configurada nas variáveis de ambiente do projeto." },
      { status: 503 }
    );
  }

  const body = await req.json().catch(() => ({} as any));
  const topic = (body.topic || "").toString().trim();
  if (!topic) return Response.json({ error: "Informe um tema." }, { status: 400 });

  const format = (body.format || "single").toString();
  const window = (body.window || "unknown").toString();
  const niche = (body.niche || "").toString();
  const count = Math.min(Math.max(parseInt(body.count, 10) || 5, 1), 8);

  const client = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });

  try {
    const response = await client.messages.create({
      model: MODEL,
      max_tokens: 4096,
      thinking: { type: "adaptive" },
      output_config: { effort: "medium", format: { type: "json_schema", schema: VARIANT_SCHEMA } },
      system: systemPrompt(niche),
      messages: [
        {
          role: "user",
          content: [
            `Tema/assunto central: ${topic}`,
            `Formato alvo: ${format}`,
            `Janela de publicação: ${window}`,
            `Gere ${count} variações DISTINTAS, otimizadas para esse formato.`,
            "Preencha hook, body, hashtags, aiPredictedScore (0-100) e rationale.",
          ].join("\n"),
        },
      ],
    } as any);

    const textBlock = (response.content as any[]).find((b) => b.type === "text");
    if (!textBlock) throw new Error("Resposta sem conteúdo de texto.");
    const data = JSON.parse(textBlock.text);
    return Response.json({ variants: data.variants || [], model: response.model });
  } catch (err: any) {
    const status = err?.status && Number.isInteger(err.status) ? 502 : 500;
    return Response.json({ error: err?.message || "Falha ao gerar variações." }, { status });
  }
}
