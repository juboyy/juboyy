import {
  scorePost,
  scoreLabel,
  FORMATS,
  POSTING_WINDOWS,
  WEIGHTS,
} from "./viralEngine.js";
import { HOOKS, THREAD_TEMPLATES } from "./library.js";

const $ = (id) => document.getElementById(id);

// ---- Popular selects ----
function fillSelect(el, options, selected) {
  el.innerHTML = "";
  for (const o of options) {
    const opt = document.createElement("option");
    opt.value = o.id;
    opt.textContent = o.label;
    if (o.id === selected) opt.selected = true;
    el.appendChild(opt);
  }
}
fillSelect($("g-format"), FORMATS, "thread");
fillSelect($("g-window"), POSTING_WINDOWS, "evening");
fillSelect($("a-format"), FORMATS, "single");
fillSelect($("a-window"), POSTING_WINDOWS, "evening");

// ---- Status da IA ----
fetch("/api/viralforge/health")
  .then((r) => r.json())
  .then((h) => {
    const el = $("aiStatus");
    if (h.aiConfigured) {
      el.textContent = `IA ativa · ${h.model}`;
      el.classList.add("on");
    } else {
      el.textContent = "IA off — só análise";
      el.classList.add("off");
    }
  })
  .catch(() => {
    $("aiStatus").textContent = "IA indisponível";
    $("aiStatus").classList.add("off");
  });

// ---- Render de breakdown reutilizável ----
function renderBreakdown(ul, breakdown) {
  ul.innerHTML = "";
  for (const d of breakdown) {
    const li = document.createElement("li");
    li.innerHTML = `
      <div class="bk-top">
        <span class="lbl">${d.label} <small style="color:var(--muted)">(${Math.round(d.weight * 100)}%)</small></span>
        <span class="val">${d.score}</span>
      </div>
      <div class="bar"><span style="width:${d.score}%"></span></div>
      <div class="bk-detail">${d.detail}</div>`;
    ul.appendChild(li);
  }
}

// ===== ANALISADOR (tempo real, determinístico) =====
function runAnalyzer() {
  const text = $("a-text").value;
  const result = scorePost(text, {
    format: $("a-format").value,
    window: $("a-window").value,
  });
  $("a-total").textContent = result.total;
  const lbl = scoreLabel(result.total);
  const tierEl = $("a-tier");
  tierEl.textContent = text.trim() ? lbl.tier : "—";
  tierEl.className = "gauge-tier " + (text.trim() ? lbl.cls : "");
  $("a-total").className = "gauge-num " + (text.trim() ? lbl.cls : "");

  const gauge = document.querySelector(".gauge");
  if (gauge) {
    gauge.style.setProperty("--p", text.trim() ? result.total : 0);
    gauge.dataset.tier = text.trim() ? lbl.cls : "";
  }

  renderBreakdown($("a-breakdown"), result.breakdown);

  const box = $("a-suggestions");
  if (result.suggestions.length) {
    box.innerHTML =
      `<h4>Como subir o score</h4><ul>` +
      result.suggestions.map((s) => `<li>${s}</li>`).join("") +
      `</ul>`;
  } else {
    box.innerHTML = text.trim()
      ? `<h4>✅ Post afiado</h4><p style="color:var(--muted);font-size:13px">Nenhum ponto fraco crítico. Publique na janela escolhida e responda os primeiros comentários na 1ª hora.</p>`
      : "";
  }
}

let debounce;
$("a-text").addEventListener("input", () => {
  clearTimeout(debounce);
  debounce = setTimeout(runAnalyzer, 150);
});
$("a-format").addEventListener("change", runAnalyzer);
$("a-window").addEventListener("change", runAnalyzer);
runAnalyzer();

// ===== GERADOR (IA + score híbrido) =====
function blendScore(deterministic, ai) {
  const a = Number.isFinite(ai) ? Math.max(0, Math.min(100, ai)) : deterministic;
  return Math.round(0.7 * deterministic + 0.3 * a);
}

function variantCard(v, window) {
  const fullText = `${v.hook}\n${v.body}`;
  const det = scorePost(fullText, { format: v.format, window });
  const final = blendScore(det.total, v.aiPredictedScore);
  const lbl = scoreLabel(final);

  const card = document.createElement("div");
  card.className = "variant";
  const tags = (v.hashtags || []).filter(Boolean);
  card.innerHTML = `
    <div class="variant-head">
      <span class="variant-score ${lbl.cls}">${final}</span>
      <span class="variant-meta">${lbl.tier} · regras ${det.total} / IA ${v.aiPredictedScore ?? "—"} · ${v.format}</span>
    </div>
    <div class="variant-text"><span class="hook">${escapeHtml(v.hook)}</span>\n${escapeHtml(v.body)}</div>
    ${tags.length ? `<div class="variant-tags">${tags.map((t) => (t.startsWith("#") ? t : "#" + t)).join(" ")}</div>` : ""}
    ${v.rationale ? `<div class="variant-rationale">${escapeHtml(v.rationale)}</div>` : ""}
    <div class="variant-actions">
      <button class="btn-ghost copy">Copiar</button>
      <button class="btn-ghost analyze">Abrir no analisador</button>
    </div>`;

  card.querySelector(".copy").addEventListener("click", () => {
    navigator.clipboard.writeText(fullText);
    const b = card.querySelector(".copy");
    b.textContent = "Copiado ✓";
    setTimeout(() => (b.textContent = "Copiar"), 1500);
  });
  card.querySelector(".analyze").addEventListener("click", () => {
    $("a-text").value = fullText;
    $("a-format").value = v.format;
    runAnalyzer();
    $("a-text").scrollIntoView({ behavior: "smooth", block: "center" });
  });
  return card;
}

function escapeHtml(s) {
  return (s || "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

$("g-run").addEventListener("click", async () => {
  const topic = $("g-topic").value.trim();
  const errEl = $("g-error");
  const resEl = $("g-results");
  errEl.hidden = true;
  if (!topic) {
    errEl.textContent = "Informe um tema.";
    errEl.hidden = false;
    return;
  }
  const btn = $("g-run");
  btn.disabled = true;
  btn.textContent = "Forjando…";
  resEl.innerHTML = `<div class="spinner">Gerando variações otimizadas e pontuando…</div>`;

  try {
    const r = await fetch("/api/viralforge/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        topic,
        niche: $("g-niche").value.trim(),
        format: $("g-format").value,
        window: $("g-window").value,
        count: parseInt($("g-count").value, 10),
      }),
    });
    const data = await r.json();
    if (!r.ok) throw new Error(data.error || "Falha na geração.");

    resEl.innerHTML = "";
    const window = $("g-window").value;
    const variants = (data.variants || []).slice().sort((a, b) => {
      const sa = blendScore(scorePost(`${a.hook}\n${a.body}`, { format: a.format, window }).total, a.aiPredictedScore);
      const sb = blendScore(scorePost(`${b.hook}\n${b.body}`, { format: b.format, window }).total, b.aiPredictedScore);
      return sb - sa;
    });
    if (!variants.length) {
      resEl.innerHTML = `<div class="spinner">Nenhuma variação retornada.</div>`;
    } else {
      for (const v of variants) resEl.appendChild(variantCard(v, window));
    }
  } catch (e) {
    resEl.innerHTML = "";
    errEl.textContent = e.message;
    errEl.hidden = false;
  } finally {
    btn.disabled = false;
    btn.textContent = "Gerar variações";
  }
});

// ===== BIBLIOTECA (hooks + templates) =====
function loadIntoAnalyzer(text, format) {
  $("a-text").value = text;
  $("a-format").value = format;
  runAnalyzer();
  $("a-text").scrollIntoView({ behavior: "smooth", block: "center" });
}

function renderLibrary(el, items, getPat, getText, format) {
  for (const item of items) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "chip";
    b.innerHTML = `<span class="pat">${escapeHtml(getPat(item))}</span>${escapeHtml(getText(item))}`;
    b.addEventListener("click", () => loadIntoAnalyzer(item.text, format));
    el.appendChild(b);
  }
}

renderLibrary($("lib-hooks"), HOOKS, (h) => h.pattern, (h) => h.text, "single");
renderLibrary(
  $("lib-templates"),
  THREAD_TEMPLATES,
  (t) => t.name,
  (t) => t.text.split("\n")[0] + " …",
  "thread"
);
