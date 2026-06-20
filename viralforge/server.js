// ViralForge — servidor Express.
// Serve o web app e expõe /api/generate, que usa Claude (claude-opus-4-8)
// para gerar variações de posts já otimizadas. A pontuação determinística
// roda no cliente (public/viralEngine.js), fonte única da verdade dos parâmetros.

import express from "express";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import Anthropic from "@anthropic-ai/sdk";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// .env loader mínimo (sem dependência) — só para dev local.
const envPath = path.join(__dirname, ".env");
if (fs.existsSync(envPath)) {
  for (const line of fs.readFileSync(envPath, "utf8").split("\n")) {
    const m = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*)\s*$/);
    if (m && !process.env[m[1]]) process.env[m[1]] = m[2].replace(/^["']|["']$/g, "");
  }
}

const PORT = process.env.PORT || 3000;
const MODEL = process.env.VIRAL_MODEL || "claude-opus-4-8";
const apiKey = process.env.ANTHROPIC_API_KEY;
const client = apiKey ? new Anthropic({ apiKey }) : null;

const app = express();
app.use(express.json({ limit: "256kb" }));
app.use(express.static(path.join(__dirname, "public")));

app.get("/api/health", (_req, res) => {
  res.json({ ok: true, aiConfigured: Boolean(client), model: MODEL });
});

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
          aiPredictedScore: { type: "integer", description: "Probabilidade de viralidade 0-100, julgada pelo modelo" },
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

function systemPrompt({ niche }) {
  return [
    "Você é um estrategista de viralidade no X (Twitter), especialista no nicho:",
    niche || "Agentes de IA, tech, ciência, consciência, build in public, money, hacks, insights",
    "",
    "Princípios inegociáveis ao escrever cada post:",
    "- O HOOK (primeira linha) é 80% do jogo. Use um destes padrões: contrário, numérico/específico, loop de curiosidade aberto, ou stakes (medo de perder).",
    "- SEM links no corpo (o X penaliza saída da plataforma). Link vai no reply/bio.",
    "- Termine SEMPRE com uma pergunta ou CTA que puxe reply — replies valem mais que likes no algoritmo.",
    "- Frases curtas, quebras de linha, nada de parede de texto.",
    "- Opinião forte e específica. Audiência de IA/tech é majoritariamente verificada (= paga melhor): escreva para ela.",
    "- No máximo 2 hashtags, e só se agregarem.",
    "- Escreva em português do Brasil, tom direto e confiante, sem clichês de 'IA genérica'.",
    "",
    "Você NÃO garante viralidade — você maximiza a probabilidade por post. Gere ângulos distintos entre si, não variações do mesmo.",
  ].join("\n");
}

function userPrompt({ topic, format, window, count }) {
  return [
    `Tema/assunto central: ${topic}`,
    `Formato alvo: ${format}`,
    `Janela de publicação: ${window}`,
    `Gere ${count} variações DISTINTAS, cada uma otimizada para esse formato.`,
    "Para cada uma, preencha hook, body, hashtags, aiPredictedScore (0-100) e rationale.",
  ].join("\n");
}

app.post("/api/generate", async (req, res) => {
  if (!client) {
    return res.status(503).json({
      error: "IA não configurada. Defina ANTHROPIC_API_KEY no ambiente para habilitar a geração. O analisador determinístico continua funcionando.",
    });
  }
  const topic = (req.body?.topic || "").toString().trim();
  if (!topic) return res.status(400).json({ error: "Informe um tema." });

  const format = (req.body?.format || "single").toString();
  const window = (req.body?.window || "unknown").toString();
  const niche = (req.body?.niche || "").toString();
  const count = Math.min(Math.max(parseInt(req.body?.count, 10) || 5, 1), 8);

  try {
    const response = await client.messages.create({
      model: MODEL,
      max_tokens: 4096,
      thinking: { type: "adaptive" },
      output_config: {
        effort: "medium",
        format: { type: "json_schema", schema: VARIANT_SCHEMA },
      },
      system: systemPrompt({ niche }),
      messages: [{ role: "user", content: userPrompt({ topic, format, window, count }) }],
    });

    const textBlock = response.content.find((b) => b.type === "text");
    if (!textBlock) throw new Error("Resposta sem conteúdo de texto.");
    const data = JSON.parse(textBlock.text);
    res.json({ variants: data.variants || [], model: response.model });
  } catch (err) {
    if (err instanceof Anthropic.RateLimitError) {
      return res.status(429).json({ error: "Limite de requisições atingido. Tente novamente em instantes." });
    }
    if (err instanceof Anthropic.APIError) {
      return res.status(502).json({ error: `Erro da API Claude (${err.status}): ${err.message}` });
    }
    console.error(err);
    res.status(500).json({ error: "Falha ao gerar variações." });
  }
});

app.listen(PORT, () => {
  console.log(`ViralForge rodando em http://localhost:${PORT}`);
  console.log(`Modelo: ${MODEL} · IA ${client ? "configurada" : "NÃO configurada (defina ANTHROPIC_API_KEY)"}`);
});
