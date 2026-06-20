"use strict";

const REFRESH_MS = 3000;
const $ = (id) => document.getElementById(id);

function fmtUsd(v, signed = true) {
  if (v === null || v === undefined) return "—";
  const n = Number(v);
  const s = (signed && n > 0 ? "+" : "") + "$" + n.toFixed(2);
  return s;
}
function pnlClass(v) {
  if (v === null || v === undefined) return "";
  return Number(v) > 0 ? "pos" : Number(v) < 0 ? "neg" : "";
}
function fmtPct(v) { return v === null || v === undefined ? "—" : Number(v).toFixed(1) + "%"; }
function fmtDur(sec) {
  if (sec === null || sec === undefined) return "—";
  sec = Math.max(0, Math.floor(sec));
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
  if (h) return `${h}h ${m}m`;
  if (m) return `${m}m ${s}s`;
  return `${s}s`;
}
function hhmmss(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d)) return "—";
  return d.toISOString().slice(11, 19);
}

async function fetchJSON(url) {
  const r = await fetch(url, { cache: "no-store" });
  if (!r.ok) throw new Error(url + " -> " + r.status);
  return r.json();
}

let CONFIG = null;

async function loadConfig() {
  try {
    CONFIG = await fetchJSON("/api/config");
    $("runtime-dir").textContent = CONFIG.runtime_dir || "—";
  } catch (e) { /* ignore */ }
}

function renderStatus(st) {
  const stEl = $("bot-state");
  if (st.running) {
    stEl.textContent = "● RODANDO";
    stEl.className = "pill pill-ok";
  } else {
    stEl.textContent = "○ PARADO";
    stEl.className = "pill pill-off";
  }
  $("profile").textContent = "profile: " + (st.profile || "—");
  $("uptime").textContent = st.running ? fmtDur(st.uptime_sec) : "—";
  $("uptime-sub").textContent = st.pid ? "pid " + st.pid : "";

  // params chips
  const p = st.params || {};
  const chips = [];
  const keys = ["threshold", "stake_usd", "stop_loss_pct", "exit_before_sec",
    "min_entry_seconds_left", "poll_sec", "execute"];
  for (const k of keys) {
    if (p[k] !== undefined) chips.push(`<span class="chip">${k}=${p[k]}</span>`);
  }
  $("params").innerHTML = chips.join("");
}

function renderSummary(s) {
  $("pnl-today").innerHTML = `<span class="${pnlClass(s.pnl_today)}">${fmtUsd(s.pnl_today)}</span>`;
  $("pnl-total").innerHTML = `<span class="${pnlClass(s.pnl_total)}">${fmtUsd(s.pnl_total)}</span>`;
  $("pnl-total-sub").textContent = `${s.wins||0}W / ${s.losses||0}L`;
  $("winrate").textContent = fmtPct(s.win_rate);
  $("winrate-sub").textContent = s.best_trade != null
    ? `best ${fmtUsd(s.best_trade)} · worst ${fmtUsd(s.worst_trade)}` : "";
  $("trades-today").textContent = s.trades_today ?? "—";
  $("trades-today-sub").textContent = s.max_trades_per_day
    ? `de ${s.max_trades_per_day} max` : `${s.trades_total||0} total`;

  // loss cap gauge
  const lossUsed = s.loss_cap_used_pct;
  $("losscap-bar").style.width = (lossUsed != null ? Math.min(100, lossUsed) : 0) + "%";
  $("losscap-txt").textContent = s.daily_loss_cap_usd != null
    ? `${fmtUsd(Math.abs(Math.min(0, s.pnl_today||0)), false)} / $${s.daily_loss_cap_usd} (${lossUsed!=null?lossUsed:0}%)`
    : `${s.daily_loss_cap_pct != null ? s.daily_loss_cap_pct + "% equity" : "—"}`;

  // trades cap gauge
  const tUsed = s.trades_cap_used_pct;
  $("tradescap-bar").style.width = (tUsed != null ? Math.min(100, tUsed) : 0) + "%";
  $("tradescap-txt").textContent = s.max_trades_per_day != null
    ? `${s.trades_today||0} / ${s.max_trades_per_day}` : `${s.trades_today||0}`;

  // open position
  const op = s.open_position;
  if (op) {
    const cls = op.side === "UP" ? "side-up" : "side-down";
    $("open-pos").innerHTML =
      `<span class="${cls}">${op.side||"?"}</span> · ${fmtUsd(op.cost_usdc, false)} · `
      + `<span class="muted">${op.market_slug||""}</span>`;
  } else {
    $("open-pos").innerHTML = `<span class="muted">nenhuma</span>`;
  }
}

function renderSignal(sig) {
  const banner = $("signal-window");
  const ids = ["sig-up","sig-down","sig-sl","sig-skew","sig-spread","sig-gamma"];
  if (!sig) {
    banner.textContent = "sem sinal recente";
    banner.className = "signal-banner idle";
    ids.forEach(i => $(i).textContent = "—");
    $("sig-market").textContent = "—";
    $("sig-age").textContent = "";
    $("sig-source").textContent = "";
    $("skewbar-up").style.width = "50%"; $("skewbar-down").style.width = "50%";
    return;
  }
  const armed = !!sig.in_entry_window;
  banner.textContent = armed ? "🎯 JANELA DE ENTRADA ATIVA" : "monitorando…";
  banner.className = "signal-banner " + (armed ? "armed" : "idle");
  $("sig-up").textContent = sig.up_ask != null ? Number(sig.up_ask).toFixed(2) : "—";
  $("sig-down").textContent = sig.down_ask != null ? Number(sig.down_ask).toFixed(2) : "—";
  $("sig-sl").textContent = sig.seconds_left != null ? sig.seconds_left + "s" : "—";
  $("sig-skew").textContent = sig.skew != null ? (Number(sig.skew)*100).toFixed(0) + "%" : "—";
  $("sig-spread").textContent = sig.min_spread != null ? Number(sig.min_spread).toFixed(3) : "—";
  $("sig-gamma").textContent = (sig.gamma_up != null && sig.gamma_down != null)
    ? `${Number(sig.gamma_up).toFixed(2)} / ${Number(sig.gamma_down).toFixed(2)}` : "—";
  $("sig-market").textContent = sig.market_slug || "—";
  $("sig-age").textContent = sig.age_sec != null ? `há ${sig.age_sec}s` : "";

  // Be explicit about data freshness: live hook vs. last completed session.
  if (sig.source === "session_report") {
    const extra = sig.last_result ? ` · último: ${sig.last_result}` : "";
    $("sig-source").textContent = `fonte: última sessão concluída${extra}`;
  } else {
    $("sig-source").textContent = "fonte: heartbeat ao vivo";
  }

  const up = Number(sig.up_ask)||0, down = Number(sig.down_ask)||0, tot = up+down || 1;
  $("skewbar-up").style.width = (up/tot*100) + "%";
  $("skewbar-down").style.width = (down/tot*100) + "%";
}

function renderTrades(trades) {
  const tb = $("trades").querySelector("tbody");
  $("trades-count").textContent = `${trades.length} registros`;
  if (!trades.length) {
    tb.innerHTML = `<tr><td colspan="9" class="muted">sem trades ainda</td></tr>`;
    return;
  }
  tb.innerHTML = trades.map(t => {
    const sideCls = t.side === "UP" ? "side-up" : t.side === "DOWN" ? "side-down" : "muted";
    return `<tr>
      <td>${hhmmss(t.ts)}</td>
      <td class="${sideCls}">${t.side||"—"}</td>
      <td>${t.btc_move_usd!=null?"$"+Number(t.btc_move_usd).toFixed(0):"—"}</td>
      <td>${t.skew!=null?(Number(t.skew)*100).toFixed(0)+"%":"—"}</td>
      <td>${t.entry_price!=null?Number(t.entry_price).toFixed(2):"—"}</td>
      <td>${t.cost_usdc!=null?fmtUsd(t.cost_usdc,false):"—"}</td>
      <td class="${pnlClass(t.pnl_usdc)}">${fmtUsd(t.pnl_usdc)}</td>
      <td class="muted">${t.close_status||t.result||"—"}</td>
      <td class="muted">${t.market_slug||"—"}</td>
    </tr>`;
  }).join("");
}

function renderEquity(points) {
  const svg = $("equity");
  const W = 1000, H = 240, pad = 28;
  svg.innerHTML = "";
  if (!points || points.length < 1) {
    svg.innerHTML = `<text x="500" y="120" fill="#8b94a7" text-anchor="middle" font-size="14">sem dados</text>`;
    return;
  }
  const ys = points.map(p => p.cum_pnl);
  let min = Math.min(0, ...ys), max = Math.max(0, ...ys);
  if (min === max) { max = min + 1; }
  const n = points.length;
  const x = i => pad + (i / Math.max(1, n - 1)) * (W - 2 * pad);
  const y = v => H - pad - ((v - min) / (max - min)) * (H - 2 * pad);

  // zero line
  const yZero = y(0);
  let svgStr = `<line x1="${pad}" y1="${yZero}" x2="${W-pad}" y2="${yZero}" stroke="#2a3346" stroke-dasharray="4 4"/>`;
  // area + line
  let d = "", area = `M ${x(0)} ${yZero} `;
  points.forEach((p, i) => {
    d += (i === 0 ? "M" : "L") + ` ${x(i).toFixed(1)} ${y(p.cum_pnl).toFixed(1)} `;
    area += `L ${x(i).toFixed(1)} ${y(p.cum_pnl).toFixed(1)} `;
  });
  area += `L ${x(n-1)} ${yZero} Z`;
  const last = ys[ys.length-1];
  const col = last >= 0 ? "#2ecc71" : "#ff5d5d";
  svgStr += `<path d="${area}" fill="${col}" opacity="0.12"/>`;
  svgStr += `<path d="${d}" fill="none" stroke="${col}" stroke-width="2.2" stroke-linejoin="round"/>`;
  // last point marker + label
  svgStr += `<circle cx="${x(n-1)}" cy="${y(last)}" r="3.5" fill="${col}"/>`;
  svgStr += `<text x="${x(n-1)-6}" y="${y(last)-8}" fill="${col}" text-anchor="end" font-size="13" font-family="monospace">${(last>0?"+":"")+"$"+last.toFixed(2)}</text>`;
  // y labels
  svgStr += `<text x="4" y="${y(max)+4}" fill="#8b94a7" font-size="11" font-family="monospace">$${max.toFixed(1)}</text>`;
  svgStr += `<text x="4" y="${y(min)+4}" fill="#8b94a7" font-size="11" font-family="monospace">$${min.toFixed(1)}</text>`;
  svg.innerHTML = svgStr;
}

async function refresh() {
  try {
    const [state, logs] = await Promise.all([
      fetchJSON("/api/state"),
      fetchJSON("/api/logs").catch(() => ({ lines: [] })),
    ]);
    renderStatus(state.status || {});
    renderSummary(state.summary || {});
    renderSignal(state.signal);
    renderTrades(state.trades || []);
    renderEquity(state.equity_curve || []);
    $("logs").textContent = (logs.lines || []).join("\n") || "—";
    $("conn").textContent = "online";
    $("conn").className = "pill pill-ok";
  } catch (e) {
    $("conn").textContent = "offline";
    $("conn").className = "pill pill-off";
  }
}

function tickClock() {
  $("clock").textContent = new Date().toISOString().slice(11, 19) + " UTC";
}

(async function main() {
  $("refresh-sec").textContent = (REFRESH_MS / 1000).toString();
  await loadConfig();
  await refresh();
  setInterval(refresh, REFRESH_MS);
  tickClock();
  setInterval(tickClock, 1000);
})();
