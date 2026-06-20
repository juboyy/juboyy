// ViralForge — motor determinístico de viralidade
// ES module usável tanto no navegador quanto no Node.
// Não depende de nenhuma API: pontua um post 0-100 a partir de parâmetros bem definidos.

export const POSTING_WINDOWS = [
  { id: "early", label: "06h–08h" },
  { id: "midday", label: "11h–13h" },
  { id: "evening", label: "17h–19h" },
  { id: "night", label: "21h–23h" },
  { id: "unknown", label: "Não sei / outro horário" },
];

export const FORMATS = [
  { id: "thread", label: "Thread (autoridade)" },
  { id: "single", label: "Single / Banger" },
  { id: "visual", label: "Visual (screenshot/código)" },
  { id: "listicle", label: "Listicle (lista)" },
  { id: "news", label: "News-jack (notícia)" },
  { id: "build", label: "Build in public (bastidor)" },
];

// Pesos das dimensões — somam 1.0. Estes são os "parâmetros bem definidos".
export const WEIGHTS = {
  hook: 0.24,
  emotion: 0.15,
  loop: 0.15,
  specificity: 0.12,
  scannability: 0.1,
  hygiene: 0.1,
  format: 0.08,
  timing: 0.06,
};

const DIMENSION_LABELS = {
  hook: "Força do hook",
  emotion: "Emoção / opinião",
  loop: "Gancho de engajamento",
  specificity: "Especificidade",
  scannability: "Escaneabilidade",
  hygiene: "Higiene de algoritmo",
  format: "Aderência ao formato",
  timing: "Horário",
};

// ---- Bancos de palavras (PT + EN, nicho IA/tech/money) ----
const CONTRARIAN = ["errado","ninguém","ninguem","pare de","não faça","nao faca","mito","esqueça","esqueca","impopular","todo mundo","a maioria","wrong","nobody","stop","unpopular","myth","everyone","most people"];
const CURIOSITY = ["segredo","ninguém fala","quase ninguém","o que ninguém","aqui está","aqui esta","descobri","o motivo","a razão","a razao","isso muda","plot twist","secret","here is why","here's why","the reason","nobody talks","truth about"];
const STAKES = ["perdendo","perde","custou","custa","erro","caro","prejuízo","prejuizo","risco","antes que","última chance","ultima chance","aviso","losing","costing","mistake","before it","warning","you're losing"];
const EMOTION = ["melhor","pior","sempre","nunca","garanto","odeio","amo","incrível","incrivel","absurdo","brutal","insano","insana","poderoso","poderosa","chocante","best","worst","always","never","insane","brutal","powerful","hate","love","shocking"];
const CTA = ["comenta","comente","marca","responde","responda","o que você acha","o que voce acha","concorda","salva","salve","compartilha","thoughts","agree","reply","share","what do you think","drop a"];
const LOOP = ["👇","🧵","thread","1/","continua","segue o fio","abre o fio","a seguir","read more","keep reading"];
const NEWSY = ["hoje","agora","acabou de","acaba de","breaking","today","just","novidade","lançou","lancou","anunciou","launched","announced"];
const BUILDY = ["dia","day","construindo","building","update","progresso","progress","ship","lancei","lancei hoje","semana","week"];

const has = (text, bank) => bank.some((w) => text.includes(w));
const countMatches = (text, bank) => bank.reduce((n, w) => (text.includes(w) ? n + 1 : n), 0);
const clamp = (n, lo = 0, hi = 100) => Math.max(lo, Math.min(hi, n));

function firstLineOf(text) {
  const lines = text.split(/\n/).map((l) => l.trim()).filter(Boolean);
  return lines[0] || "";
}

function scoreHook(text) {
  const fl = firstLineOf(text).toLowerCase();
  const triggers = [];
  let s = 28;
  if (has(fl, CONTRARIAN)) { s += 18; triggers.push("contrário"); }
  if (has(fl, CURIOSITY)) { s += 16; triggers.push("curiosidade/loop"); }
  if (has(fl, STAKES)) { s += 14; triggers.push("stakes"); }
  if (/\d/.test(fl)) { s += 12; triggers.push("número"); }
  const len = fl.length;
  if (len === 0) s = 0;
  else if (len < 15) { s -= 10; triggers.push("curto demais"); }
  else if (len <= 120) s += 10;
  else if (len <= 160) s += 4;
  else { s -= 8; triggers.push("longo demais"); }
  const detail = triggers.length ? `1ª linha: ${triggers.join(", ")}` : "1ª linha sem gatilho de parada de scroll";
  return { score: clamp(Math.round(s)), detail };
}

function scoreEmotion(text) {
  const t = text.toLowerCase();
  const c = countMatches(t, EMOTION) + countMatches(t, STAKES);
  const s = 32 + c * 15;
  return { score: clamp(Math.round(s)), detail: c ? `${c} marcador(es) de opinião/emoção` : "tom neutro — sem opinião forte" };
}

function scoreLoop(text) {
  const t = text.toLowerCase();
  const endsQ = text.trim().endsWith("?");
  let s = 18;
  const bits = [];
  if (endsQ) { s += 40; bits.push("pergunta final"); }
  if (has(t, CTA)) { s += 32; bits.push("CTA de reply"); }
  if (has(t, LOOP)) { s += 16; bits.push("loop aberto"); }
  return { score: clamp(Math.round(s)), detail: bits.length ? bits.join(", ") : "não puxa reply — sem pergunta/CTA/loop" };
}

function scoreSpecificity(text) {
  const numbers = (text.match(/\d+/g) || []).length;
  // nomes próprios aproximados: palavras Capitalizadas no meio da frase
  const proper = (text.match(/(?<!^)(?<![.!?\n]\s)\b[A-Z][a-zA-Z]{2,}/g) || []).length;
  const s = 30 + Math.min(numbers * 12, 40) + Math.min(proper * 5, 25);
  return { score: clamp(Math.round(s)), detail: `${numbers} número(s), ${proper} entidade(s) concreta(s)` };
}

function scoreScannability(text) {
  const lines = text.split(/\n/).map((l) => l.trim()).filter(Boolean);
  const longest = Math.max(0, ...text.split(/\n/).map((l) => l.length));
  let s = 50;
  if (lines.length >= 2) s += 20;
  if (/[•\-–]|\n\d/.test(text)) s += 10;
  if (/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/u.test(text)) s += 8;
  if (longest > 280) s -= 25;
  if (text.trim().length < 40) s -= 10;
  return { score: clamp(Math.round(s)), detail: `${lines.length} bloco(s), linha mais longa ${longest} chars` };
}

function scoreHygiene(text, format) {
  let s = 100;
  const flags = [];
  if (/https?:\/\/|www\./i.test(text)) { s -= 35; flags.push("link no corpo (-35)"); }
  const tags = (text.match(/#\w+/g) || []).length;
  if (tags > 2) { s -= Math.min((tags - 2) * 8, 30); flags.push(`${tags} hashtags (-)`); }
  const capWords = (text.match(/\b[A-ZÁÉÍÓÚÂÊÔÃÕ]{4,}\b/g) || []).length;
  if (capWords > 3) { s -= 15; flags.push("CAIXA ALTA em excesso (-15)"); }
  const emojis = (text.match(/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/gu) || []).length;
  if (emojis > 6) { s -= 10; flags.push("emojis demais (-10)"); }
  if (format !== "thread" && format !== "listicle" && text.length > 280) { s -= 10; flags.push(">280 chars fora de thread (-10)"); }
  return { score: clamp(Math.round(s)), detail: flags.length ? flags.join(" · ") : "limpo" };
}

function scoreFormat(text, format) {
  const t = text.toLowerCase();
  const lines = text.split(/\n/).filter((l) => l.trim()).length;
  let s = 60;
  let detail = "";
  switch (format) {
    case "thread":
      s = lines >= 3 || /\b1\/|🧵|\bthread\b/i.test(text) ? 92 : 55;
      detail = "thread quer múltiplos blocos / marcador de fio";
      break;
    case "single":
      s = lines <= 2 && text.length <= 280 ? 90 : 58;
      detail = "single quer 1–2 linhas e ≤280 chars";
      break;
    case "listicle":
      s = /[•\-–]|\n\s*\d/.test(text) ? 90 : 50;
      detail = "listicle quer marcadores de lista";
      break;
    case "visual":
      s = 72; detail = "visual depende da mídia (anexe screenshot/código)"; break;
    case "news":
      s = has(t, NEWSY) ? 90 : 55; detail = "news-jack quer marcador de recência (hoje/agora/breaking)"; break;
    case "build":
      s = has(t, BUILDY) ? 88 : 58; detail = "build in public quer marcador de jornada (dia/update/progresso)"; break;
    default:
      detail = "formato livre";
  }
  return { score: clamp(Math.round(s)), detail };
}

function scoreTiming(window) {
  if (!window || window === "unknown") return { score: 55, detail: "horário indefinido — escolha uma janela de pico" };
  const w = POSTING_WINDOWS.find((x) => x.id === window);
  return { score: 100, detail: `janela de pico ${w ? w.label : window}` };
}

// ---- Sugestões acionáveis a partir das dimensões fracas ----
function buildSuggestions(b) {
  const tips = [];
  if (b.hook.score < 65) tips.push("Reescreva a 1ª linha com um gatilho forte: contrário (\"Todo mundo está errado sobre X\"), número (\"Rodei 1.000 prompts...\") ou loop aberto.");
  if (b.loop.score < 60) tips.push("Termine com pergunta ou CTA de reply — o algoritmo do X premia replies acima de likes.");
  if (b.emotion.score < 55) tips.push("Adicione uma opinião contundente. Conteúdo morno não viraliza no nicho de IA/tech.");
  if (b.specificity.score < 55) tips.push("Troque o genérico pelo concreto: números, nomes de ferramentas, resultados específicos.");
  if (b.scannability.score < 55) tips.push("Quebre em linhas curtas. Pare de criar paredes de texto — o X corta no scroll.");
  if (b.hygiene.score < 80) tips.push("Tire o link do corpo (coloque no reply/bio) e reduza hashtags para no máximo 2.");
  if (b.format.score < 60) tips.push(`Ajuste ao formato: ${b.format.detail}.`);
  if (b.timing.score < 100) tips.push("Programe para uma das 4 janelas de pico (06–08, 11–13, 17–19, 21–23).");
  return tips;
}

/**
 * Pontua um post.
 * @param {string} text  O conteúdo do post (hook + corpo).
 * @param {{format?:string, window?:string}} params
 * @returns {{total:number, breakdown:Array, suggestions:string[]}}
 */
export function scorePost(text, params = {}) {
  const format = params.format || "single";
  const window = params.window || "unknown";
  const safe = (text || "").toString();

  const dims = {
    hook: scoreHook(safe),
    emotion: scoreEmotion(safe),
    loop: scoreLoop(safe),
    specificity: scoreSpecificity(safe),
    scannability: scoreScannability(safe),
    hygiene: scoreHygiene(safe, format),
    format: scoreFormat(safe, format),
    timing: scoreTiming(window),
  };

  let total = 0;
  const breakdown = Object.keys(WEIGHTS).map((key) => {
    total += dims[key].score * WEIGHTS[key];
    return {
      key,
      label: DIMENSION_LABELS[key],
      weight: WEIGHTS[key],
      score: dims[key].score,
      detail: dims[key].detail,
    };
  });

  return {
    total: safe.trim() ? Math.round(total) : 0,
    breakdown,
    suggestions: safe.trim() ? buildSuggestions(dims) : [],
  };
}

export function scoreLabel(total) {
  if (total >= 80) return { tier: "Alto potencial", cls: "tier-high" };
  if (total >= 60) return { tier: "Promissor", cls: "tier-mid" };
  if (total >= 40) return { tier: "Precisa de ajuste", cls: "tier-low" };
  return { tier: "Fraco", cls: "tier-bad" };
}
