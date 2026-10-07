import {html} from "npm:htl";
import {pct, pts} from "./theme.js";

// One ticket's explanation: probability, top reasons with size bars, and the four theme totals.
export function ticketDetail(t, {base, outcome = true} = {}) {
  if (!t) return html`<div class="detail muted">Select a ticket in the table to see why the model rates it as it does.</div>`;
  const max = Math.max(...t.reasons.map((r) => Math.abs(r.points)), 1);
  const point = t.point === "creation" ? "when it was filed" : "on day 7";
  return html`<div class="detail">
    <div class="head">
      <div><h3>${t.key}</h3><div class="sub">${t.project} · ${t.type} · created ${t.created}${t.age_days != null ? ` · open ${Math.round(t.age_days)} days` : ""}</div></div>
      <div style="text-align:right"><div class="prob">${pct(t.p)}</div><div class="sub">chance of running late, scored ${point}${base != null ? ` (typical: ${pct(base)})` : ""}</div></div>
    </div>
    <div style="margin:6px 0 4px">${t.top10 ? html`<span class="chip up" title="At or above the score only 10% of test-period tickets reached">High risk</span>` : html`<span class="chip">Not high risk</span>`}
      ${outcome && t.late != null ? html` <span class="outcome">What happened: ${t.late ? html`<span class="chip up">ran late</span>` : html`<span class="chip down">not late</span>`}</span>` : ""}</div>
    ${t.reasons.map((r) => html`<div class="reason">
      <div><span class="dir ${r.points >= 0 ? "up" : "down"}">${r.points >= 0 ? "Raises risk" : "Lowers risk"}</span> · ${r.text}</div>
      <div class="meter" aria-hidden="true"><i class="${r.points >= 0 ? "up" : "down"}" style="width:${(Math.abs(r.points) / max) * 100}%"></i></div>
      <small>${r.theme} · about ${pts(r.points)} points</small>
    </div>`)}
    <div class="themes" title="Sum of every feature in the theme, not only the five shown">${Object.entries(t.themes).map(([k, v]) => html`<span class="${v > 0.05 ? "up" : v < -0.05 ? "down" : ""}">${k} ${pts(v)}</span>`)}</div>
    <div class="sub">Reasons describe what the model associates with lateness, not what causes it. Sizes are approximate percentage points.</div>
  </div>`;
}

export const riskBar = (p) => html`<div class="riskbar"><i style="width:${p * 100}%"></i><b>${Math.round(p * 100)}%</b></div>`;
