// ViralForge — servidor local (Express).
// Serve o web app e expõe /api/generate com DOIS providers de geração:
//   PROVIDER=anthropic   → usa a API da Anthropic com ANTHROPIC_API_KEY (também usado na Vercel)
//   PROVIDER=claude-code → roteia para o SEU Claude Code (CLI `claude`, headless) — sem API key
// O provider claude-code só funciona localmente (precisa do CLI `claude` instalado e logado).

import express from "express";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { execFile, execSync } from "node:child_process";
import Anthropic from "@anthropic-ai/sdk";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// .env loader mínimo (dev local)
const envPath = path.join(__dirname, ".env");
if (fs.existsSync(envPath)) {
  for (const line of fs.readFileSync(envPath, "utf8").split("\n")) {
    const m = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*)\s*$/);
    if (m && !process.env[m[1]]) process.env[m[1]] = m[2].replace(/^["']|["']$/g, "");
  }
}

const PORT = process.env.PORT || 3000;
const PROVIDER = (process.env.PROVIDER || "anthropic").toLowerCase();
const MODEL = process.env.VIRAL_MODEL || "claude-opus-4-8";
const CC_MODEL = process.env.VIRAL_CC_MODEL || ""; // vazio = usa o modelo padrão do seu Claude Code

const apiKey = process.env.ANTHROPIC_API_KEY;
const anthropic = apiKey ? new Anthropic({ apiKey }) : null;

function claudeCliAvailable() {
  try { execSync("command -v claude", { stdio: "ignore" }); return true; } catch { return false; }
}
const CC_AVAILABLE = claudeCliAvailable();

const app = express();
app.use(express.json({ limit: "256kb" }));
app.use(express.static(path.join(__dirname, "public")));

app.get("/api/health", (_req, res) => {
  const aiConfigured = PROVIDER === "claude-code" ? CC_AVAILABLE : Boolean(anthropic);
  res.json({
    ok: true,
    provider: PROVIDER,
    aiConfigured,
    model: PROVIDER === "claude-code" ? CC_MODEL || "claude-code (padrão)" : MODEL,
  });
});

// ---------- Prompt compartilhado ----------
function systemPrompt(niche) {
  return [
    "Você é um estrategista de viralidade no X (Twitter), especialista no nicho:",
    niche || "Agentes de IA, tech, ciência, consciência, build in public, money, hacks, insights",
    "",
    "Princípios inegociáveis ao escrever cada post:",
    "- O HOOK (primeira linha) é 80% do jogo: contrário, numérico/específico, loop de curiosidade aberto, ou stakes.",
    "- SEM links no corpo (o X penaliza saída da plataforma). Link vai no reply/bio.",
    "- Termine SEMPRE com pergunta ou CTA que puxe reply.",
    "- Frases curtas, quebras de linha, nada de parede de texto.",
    "- Opinião forte e específica. Audiência de IA/tech é majoritariamente verificada.",
    "- No máximo 2 hashtags. Português do Brasil, tom direto, sem clichês de 'IA genérica'.",
  ].join("\n");
}

function userPromptBase({ topic, format, window, count }) {
  return [
    `Tema/assunto central: ${topic}`,
    `Formato alvo: ${format}`,
    `Janela de publicação: ${window}`,
    `Gere ${count} variações DISTINTAS, cada uma otimizada para esse formato.`,
  ].join("\n");
}

const VARIANT_SCHEMA = {
  type: "object",
  properties: {
    variants: {
      type: "array",
      items: {
        type: "object",
        properties: {
          format: { type: "string" },
          hook: { type: "string" },
          body: { type: "string" },
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

// ---------- Provider: Anthropic API ----------
async function generateAnthropic(params) {
  const response = await anthropic.messages.create({
    model: MODEL,
    max_tokens: 4096,
    thinking: { type: "adaptive" },
    output_config: { effort: "medium", format: { type: "json_schema", schema: VARIANT_SCHEMA } },
    system: systemPrompt(params.niche),
    messages: [{ role: "user", content: userPromptBase(params) + "\nPreencha hook, body, hashtags, aiPredictedScore (0-100) e rationale." }],
  });
  const textBlock = response.content.find((b) => b.type === "text");
  if (!textBlock) throw new Error("Resposta sem conteúdo de texto.");
  return { variants: JSON.parse(textBlock.text).variants || [], model: response.model };
}

// ---------- Provider: Claude Code (CLI headless) ----------
function extractJson(text) {
  const m = (text || "").match(/\{[\s\S]*\}/); // primeiro objeto JSON na resposta
  if (!m) throw new Error("Sem JSON na resposta do Claude Code.");
  return JSON.parse(m[0]);
}

function generateClaudeCode(params) {
  const userPrompt =
    userPromptBase(params) +
    "\n\nResponda APENAS com JSON válido (sem cercas de código, sem texto fora do JSON) no formato:" +
    '\n{"variants":[{"format":"...","hook":"...","body":"...","hashtags":["..."],"aiPredictedScore":0,"rationale":"..."}]}' +
    "\naiPredictedScore é 0-100 (probabilidade de viralidade).";

  const args = ["-p", userPrompt, "--output-format", "json", "--system-prompt", systemPrompt(params.niche)];
  if (CC_MODEL) args.push("--model", CC_MODEL);

  // Em ambiente Claude Code aninhado, esta env força stream-json; removemos para usar --output-format json.
  const childEnv = { ...process.env };
  delete childEnv.CLAUDE_CODE_INCLUDE_PARTIAL_MESSAGES;

  return new Promise((resolve, reject) => {
    execFile("claude", args, { env: childEnv, maxBuffer: 16 * 1024 * 1024, timeout: 180000 }, (err, stdout, stderr) => {
      if (err) return reject(new Error((stderr || err.message || "").toString().slice(0, 400)));
      let envelope;
      try { envelope = JSON.parse(stdout); } catch { return reject(new Error("Saída do Claude Code não é JSON.")); }
      if (envelope.is_error || envelope.subtype !== "success") return reject(new Error("Claude Code retornou erro."));
      try {
        const data = extractJson(envelope.result);
        resolve({ variants: data.variants || [], model: "claude-code" });
      } catch (e) { reject(e); }
    });
  });
}

// ---------- Rota ----------
app.post("/api/generate", async (req, res) => {
  const topic = (req.body?.topic || "").toString().trim();
  if (!topic) return res.status(400).json({ error: "Informe um tema." });

  const params = {
    topic,
    format: (req.body?.format || "single").toString(),
    window: (req.body?.window || "unknown").toString(),
    niche: (req.body?.niche || "").toString(),
    count: Math.min(Math.max(parseInt(req.body?.count, 10) || 5, 1), 8),
  };

  try {
    if (PROVIDER === "claude-code") {
      if (!CC_AVAILABLE) return res.status(503).json({ error: "CLI `claude` não encontrado. Instale/logue o Claude Code ou use PROVIDER=anthropic." });
      return res.json(await generateClaudeCode(params));
    }
    if (!anthropic) return res.status(503).json({ error: "ANTHROPIC_API_KEY não configurada (ou troque para PROVIDER=claude-code)." });
    return res.json(await generateAnthropic(params));
  } catch (err) {
    if (err instanceof Anthropic.RateLimitError) return res.status(429).json({ error: "Limite de requisições atingido." });
    if (err instanceof Anthropic.APIError) return res.status(502).json({ error: `Erro da API Claude (${err.status}): ${err.message}` });
    console.error(err);
    return res.status(500).json({ error: err.message || "Falha ao gerar variações." });
  }
});

app.listen(PORT, () => {
  console.log(`ViralForge em http://localhost:${PORT}`);
  console.log(`Provider: ${PROVIDER}` + (PROVIDER === "claude-code" ? ` · CLI claude ${CC_AVAILABLE ? "OK" : "NÃO encontrado"}` : ` · ${anthropic ? "API key OK" : "sem API key"}`));
});
