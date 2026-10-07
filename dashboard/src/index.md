---
title: Overview
---

```js
import {palette, pct, label, JIRA_REVIEW, GITHUB_REVIEW} from "./components/theme.js";
const meta = FileAttachment("data/meta.json").json();
const overview = FileAttachment("data/overview.json").json();
const quality = FileAttachment("data/model_quality.json").json();
const drivers = FileAttachment("data/global.json").json();
const C = palette(dark);
```

# Delivery Risk Radar

<p class="lede">Which Apache Jira tickets run late, and why. Eight large open-source projects, 2007 to 2021, from a public snapshot of their Jira history.</p>

```js
const delivered = d3.sum(overview.lead_time_by_project, (d) => d.tickets);
const lateRate = d3.sum(overview.lead_time_by_project, (d) => d.tickets * d.late_pct) / delivered / 100;
const bt = quality.points.creation.models.boosting;
display(html`<div class="kpis">
  <div class="kpi"><div class="n">${delivered.toLocaleString("en-US")}</div><div class="l">delivered tickets studied across 8 projects</div></div>
  <div class="kpi"><div class="n">${pct(lateRate)}</div><div class="l">of them ran late: slower than 3 in 4 comparable tickets in their project</div></div>
  <div class="kpi"><div class="n">${pct(bt.precision_at_top10)}</div><div class="l">of the 10% of tickets the model rated riskiest when filed were late, against ${pct(bt.late_rate)} overall</div></div>
</div>`);
```

<div class="note"><b>What "late" means here.</b> Almost no Apache ticket has a due date, so lateness is relative: a ticket is late when it took longer than 75% of comparable tickets (same project and type). It is a measure of being slow compared with peers, not of missing a promise. The data is a snapshot as of ${meta.snapshot}.</div>

## Where the time goes

Tickets spend most of their life waiting. The stage with active work is a few percent of lead time in most projects, and review takes a fifth to a third where it happens in Jira.

```js
const STAGES = ["Waiting", "Building", "In review", "Resolved, before reopen"];
const stageColor = [C.blue, C.orange, C.aqua, C.gap];
function stageChart(projects, title) {
  const rows = [];
  for (const p of projects) {
    const d = overview.stage_share.find((s) => s.project_key === p);
    let x0 = 0;
    for (const [stage, v] of [["Waiting", d.waiting_pct], ["Building", d.building_pct], ["In review", d.in_review_pct], ["Resolved, before reopen", d.resolved_gap_pct]]) {
      rows.push({project: p, stage, x0, x1: x0 + v, v});
      x0 += v;
    }
  }
  return html`<div><h3 style="margin:1rem 0 .2rem">${title}</h3>${resize((width) => Plot.plot({
    width, height: 40 + projects.length * 34, marginLeft: 86,
    x: {domain: [0, 100], label: "Share of lead time (%)", grid: true},
    y: {domain: projects, label: null},
    color: {domain: STAGES, range: stageColor},
    marks: [
      Plot.barX(rows, {x1: "x0", x2: "x1", y: "project", fill: "stage", inset: 0.5, tip: {format: {x1: false, x2: false}}, title: (d) => `${d.project}: ${d.stage} ${d.v.toFixed(1)}%`}),
      Plot.text(rows.filter((d) => d.v >= 7), {x: (d) => (d.x0 + d.x1) / 2, y: "project", text: (d) => `${Math.round(d.v)}%`, fill: (d) => (d.stage === "Resolved, before reopen" && !dark ? "#0b0b0b" : "#fff"), fontWeight: 600})
    ]
  }))}</div>`;
}
display(html`<div style="display:flex;flex-wrap:wrap;gap:6px 18px;font-size:.85rem;margin:.4rem 0">${STAGES.map((s, i) => html`<span><span style="display:inline-block;width:11px;height:11px;border-radius:2px;background:${stageColor[i]};margin-right:5px"></span>${s}</span>`)}</div>`);
display(stageChart(JIRA_REVIEW, "Review happens in Jira statuses (Patch Available)"));
display(stageChart(GITHUB_REVIEW, "Review happens on GitHub, outside Jira"));
```

<div class="note">Compare stage shares within a group, not across. In the GitHub-review projects the review is invisible to Jira, so it shows up as waiting.</div>

## Waiting for a first review

In the four projects that review through Jira statuses, a typical ticket reaches review quickly. The slowest quarter is where the delay is.

```js
const wait = overview.review_flow.filter((d) => JIRA_REVIEW.includes(d.project_key))
  .flatMap((d) => [{project: d.project_key, measure: "Median", days: d.median_wait_to_review_days}, {project: d.project_key, measure: "Slowest quarter (75th percentile)", days: d.p75_wait_to_review_days}]);
const waitOrder = overview.review_flow.filter((d) => JIRA_REVIEW.includes(d.project_key)).sort((a, b) => b.p75_wait_to_review_days - a.p75_wait_to_review_days).map((d) => d.project_key);
display(resize((width) => Plot.plot({
  width, height: 330, marginLeft: 90, marginRight: 50,
  x: {label: "Days from filing to first review", grid: true},
  y: {axis: null, domain: ["Median", "Slowest quarter (75th percentile)"]},
  fy: {domain: waitOrder, label: null, padding: 0.25},
  color: {domain: ["Median", "Slowest quarter (75th percentile)"], range: [C.blue, C.orange], legend: true},
  marks: [
    Plot.barX(wait, {x: "days", y: "measure", fy: "project", fill: "measure", inset: 1}),
    Plot.text(wait, {x: "days", y: "measure", fy: "project", text: (d) => `${d.days < 1 ? d.days.toFixed(2) : d.days.toFixed(1)} d`, dx: 4, textAnchor: "start"})
  ]
})));
```

## Counting only delivered tickets understates lateness

Among delivered tickets the late rate seems to fall for recent tickets. That is censoring: the slow ones are not delivered yet. Counting open tickets that are already past their threshold as late removes the bias, and the model is trained on that version.

```js
const trendRows = overview.late_trend.flatMap((d) => [{year: d.year, v: d.all_labelled, k: "All tickets (open ones past their threshold count as late)"}, {year: d.year, v: d.delivered_only, k: "Delivered tickets only"}]);
const trendKeys = ["All tickets (open ones past their threshold count as late)", "Delivered tickets only"];
display(resize((width) => Plot.plot({
  width, height: 330, marginRight: 56,
  x: {label: "Year the ticket was filed", tickFormat: "d", ticks: 7},
  y: {label: "Late rate (%)", grid: true, domain: [0, 55]},
  color: {domain: trendKeys, range: [C.blue, C.orange], legend: true},
  marks: [
    Plot.ruleY([0]),
    Plot.lineY(trendRows, {x: "year", y: "v", stroke: "k", strokeWidth: 2, marker: "circle-stroke"}),
    Plot.text(trendRows.filter((d) => d.year === 2021), {x: "year", y: "v", text: (d) => `${Math.round(d.v)}%`, dx: 20, fontWeight: 600}),
    Plot.tip(trendRows, Plot.pointerX({x: "year", y: "v", title: (d) => `${d.year}: ${d.v}% (${d.k})`}))
  ]
})));
```

## What the model relies on

At creation, the biggest signal is whether the ticket was **assigned when it was filed**. Tickets filed with an assignee are late far less often than unassigned ones (HIVE 34% against 72%). Who filed it and how it is described also matter. Priority barely separates late from on-time tickets.

```js
const which = view(Inputs.radio(["When filed", "On day 7"], {label: "Model", value: "When filed"}));
```

```js
const key = which === "When filed" ? "creation" : "day7";
const top = drivers[key].importance.slice(0, 10);
display(resize((width) => Plot.plot({
  width, height: 360, marginLeft: 190, marginRight: 90,
  x: {label: "Average push on the model's risk score (log-odds)", grid: true},
  y: {label: null, domain: top.map((d) => label(d.feature))},
  marks: [
    Plot.barX(top, {x: "mean_abs", y: (d) => label(d.feature), fill: C.blue, inset: 1}),
    Plot.text(top, {x: "mean_abs", y: (d) => label(d.feature), text: (d) => d.theme, dx: 5, textAnchor: "start", fill: "currentColor", fillOpacity: 0.7})
  ]
})));
```

<div class="note">Bars show how far each feature moves a ticket's score on average, from a test period the model never saw. These are associations: assigning a ticket does not make it faster. See <a href="./model-quality">Model quality</a> and <a href="./method">Method</a> for how this was measured.</div>
