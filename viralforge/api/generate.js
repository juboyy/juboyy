// Vercel serverless function — POST /api/generate
// Gera variações de posts otimizadas com Claude (structured outputs).
import Anthropic from "@anthropic-ai/sdk";

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
          hook: { type: "string", description: "Primeira linha — o gatilho de parada de scroll" },
          body: { type: "string", description: "Corpo do post, com quebras de linha. Termina com pergunta ou CTA de reply. Sem links." },
          hashtags: { type: "array", items: { type: "string" } },
          aiPredictedScore: { type: "integer", description: "Probabilidade de viralidade 0-100" },
          rationale: { type: "string", description: "1 frase: por que esse ângulo tende a pegar" },
        },
        required: ["format", "hook", "body", "hashtags", "aiPredictedScore", "rationale"],
        additionalProperties: false,
      },
    },
  },
  required: ["variants"],
  additionalProperties: false,
};

function systemPrompt(niche) {
  return [
    "Você é um estrategista de viralidade no X (Twitter), especialista no nicho:",
    niche || "Agentes de IA, tech, ciência, consciência, build in public, money, hacks, insights",
    "",
    "Princípios inegociáveis ao escrever cada post:",
    "- O HOOK (primeira linha) é 80% do jogo. Use: contrário, numérico/específico, loop de curiosidade aberto, ou stakes.",
    "- SEM links no corpo (o X penaliza saída da plataforma). Link vai no reply/bio.",
    "- Termine SEMPRE com pergunta ou CTA que puxe reply — replies valem mais que likes.",
    "- Frases curtas, quebras de linha, nada de parede de texto.",
    "- Opinião forte e específica. Audiência de IA/tech é majoritariamente verificada (= paga melhor).",
    "- No máximo 2 hashtags, e só se agregarem.",
    "- Português do Brasil, tom direto e confiante, sem clichês de 'IA genérica'.",
    "",
    "Você NÃO garante viralidade — maximiza a probabilidade por post. Gere ângulos distintos entre si.",
  ].join("\n");
}

export default async function handler(req, res) {
  if (req.method !== "POST") return res.status(405).json({ error: "Método não permitido." });
  if (!process.env.ANTHROPIC_API_KEY) {
    return res.status(503).json({
      error: "IA não configurada. Defina ANTHROPIC_API_KEY nas variáveis de ambiente do projeto. O analisador determinístico continua funcionando.",
    });
  }

  const body = req.body || {};
  const topic = (body.topic || "").toString().trim();
  if (!topic) return res.status(400).json({ error: "Informe um tema." });

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
      messages: [{
        role: "user",
        content: [
          `Tema/assunto central: ${topic}`,
          `Formato alvo: ${format}`,
          `Janela de publicação: ${window}`,
          `Gere ${count} variações DISTINTAS, cada uma otimizada para esse formato.`,
          "Preencha hook, body, hashtags, aiPredictedScore (0-100) e rationale.",
        ].join("\n"),
      }],
    });

    const textBlock = response.content.find((b) => b.type === "text");
    if (!textBlock) throw new Error("Resposta sem conteúdo de texto.");
    const data = JSON.parse(textBlock.text);
    res.status(200).json({ variants: data.variants || [], model: response.model });
  } catch (err) {
    if (err instanceof Anthropic.RateLimitError) return res.status(429).json({ error: "Limite de requisições atingido." });
    if (err instanceof Anthropic.APIError) return res.status(502).json({ error: `Erro da API Claude (${err.status}): ${err.message}` });
    console.error(err);
    res.status(500).json({ error: "Falha ao gerar variações." });
  }
}
