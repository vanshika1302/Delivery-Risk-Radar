---
title: Model quality
---

```js
import {palette, pct, label} from "./components/theme.js";
import {ticketDetail, riskBar} from "./components/reasons.js";
const meta = FileAttachment("data/meta.json").json();
const quality = FileAttachment("data/model_quality.json").json();
const drivers = FileAttachment("data/global.json").json();
const backtest = FileAttachment("data/backtest_tickets.json").json();
const C = palette(dark);
const NAMES = {baseline_project_rate: "Project late rate", baseline_peer_history: "Peer-group history", logistic: "Logistic regression", boosting: "Gradient boosting"};
const MODELS = Object.keys(NAMES);
```

# How good is the model?

<p class="lede">Tested on tickets filed between ${meta.test_window[0]} and ${meta.test_window[1]}, a period the model never saw while it was trained or tuned. Two models: one scores a ticket when it is filed, one scores it a week later.</p>

```js
const q = quality.points.creation.models.boosting, q7 = quality.points.day7.models.boosting;
display(html`<div class="kpis">
  <div class="kpi"><div class="n">${pct(q.precision_at_top10)}</div><div class="l">of the riskiest 10% of tickets at filing ran late, against ${pct(q.late_rate)} of all tickets (${q.lift_at_top10.toFixed(1)}× more)</div></div>
  <div class="kpi"><div class="n">${q.roc_auc.toFixed(2)}</div><div class="l">ROC-AUC at filing (0.5 is a coin flip, 1 is perfect): a moderate signal</div></div>
  <div class="kpi"><div class="n">${q7.roc_auc.toFixed(2)}</div><div class="l">ROC-AUC on day 7, for tickets still open (${pct(q7.late_rate)} of those ran late)</div></div>
</div>`);
```

## The model against simple baselines

Two baselines make the comparison honest: "the project's usual late rate" and "how late similar recent tickets were". PR-AUC is the headline measure. The 95% intervals from resampling the test tickets are about ±0.01, narrower than the dots.

```js
const pointLabel = {creation: "When filed", day7: "On day 7"};
const ci = [];
for (const point of ["creation", "day7"]) {
  const r = quality.points[point];
  for (const m of MODELS) ci.push({point: pointLabel[point], model: NAMES[m], pr: r.models[m].pr_auc, lo: r.bootstrap.pr_auc_ci[m][0], hi: r.bootstrap.pr_auc_ci[m][1], base: r.models[m].late_rate});
}
display(resize((width) => Plot.plot({
  width, height: 330, marginLeft: 150, marginRight: 80,
  x: {label: "PR-AUC (higher is better); the dashed line is what a coin weighted by the late rate would score", grid: true, domain: [0.3, 1]},
  y: {label: null, domain: Object.values(NAMES)},
  fy: {label: null, domain: ["When filed", "On day 7"]},
  marks: [
    Plot.ruleX(ci, Plot.groupZ({x: "first"}, {x: "base", fy: "point", stroke: "currentColor", strokeDasharray: "4 3", strokeOpacity: 0.6})),
    Plot.link(ci, {x1: "lo", x2: "hi", y: "model", fy: "point", stroke: (d) => (d.model === NAMES.boosting ? C.orange : C.blue), strokeWidth: 3}),
    Plot.dot(ci, {x: "pr", y: "model", fy: "point", r: 5, fill: (d) => (d.model === NAMES.boosting ? C.orange : C.blue), stroke: dark ? "#111" : "#fff", strokeWidth: 1.5}),
    Plot.text(ci, {x: "hi", y: "model", fy: "point", text: (d) => d.pr.toFixed(3), dx: 8, textAnchor: "start"})
  ]
})));
```

```js
const diffs = ["creation", "day7"].flatMap((p) => Object.entries(quality.points[p].bootstrap.diff_vs).filter(([k]) => k.startsWith("boosting")).map(([k, v]) => ({when: pointLabel[p], vs: NAMES[k.split(" - ")[1]], gain: v.mean, lo: v.ci95[0], hi: v.ci95[1], wins: v.wins})));
display(Inputs.table(diffs, {columns: ["when", "vs", "gain", "wins"], header: {when: "Scored", vs: "Gradient boosting compared with", gain: "PR-AUC difference (95% interval)", wins: "Clearly better?"},
  format: {gain: (g, i) => `${g >= 0 ? "+" : ""}${g.toFixed(3)} (${diffs[i].lo >= 0 ? "+" : ""}${diffs[i].lo.toFixed(3)} to ${diffs[i].hi >= 0 ? "+" : ""}${diffs[i].hi.toFixed(3)})`, wins: (w) => (w ? "Yes" : "No: tied")}, sort: null, layout: "auto"}));
```

<div class="note">When filed, boosting is clearly better than both baselines and than logistic regression. On day 7 both models beat both baselines by a wide margin but are tied with each other, so a simple logistic regression would do as well. Day 7 scores look high for every model because tickets still open after a week are late 72% of the time.</div>

## Are the probabilities honest?

If the model says 60%, about 60% of those tickets should run late. Each point is a tenth of the test tickets; points on the diagonal are perfectly calibrated.

```js
const cal = ["creation", "day7"].flatMap((p) => quality.points[p].models.boosting.calibration_table.map((d) => ({...d, when: pointLabel[p]})));
display(resize((width) => Plot.plot({
  width, height: 340, aspectRatio: 1, marginRight: 20,
  x: {label: "Predicted chance of running late", domain: [0, 1], tickFormat: "%", grid: true},
  y: {label: "What actually happened", domain: [0, 1], tickFormat: "%", grid: true},
  color: {domain: ["When filed", "On day 7"], range: [C.blue, C.orange], legend: true},
  marks: [
    Plot.line([[0, 0], [1, 1]], {stroke: "currentColor", strokeOpacity: 0.5, strokeDasharray: "4 3"}),
    Plot.line(cal, {x: "predicted", y: "observed", stroke: "when", strokeWidth: 2}),
    Plot.dot(cal, {x: "predicted", y: "observed", fill: "when", r: 4, stroke: dark ? "#111" : "#fff", strokeWidth: 1.5, title: (d) => `${d.when}: predicted ${pct(d.predicted)}, actual ${pct(d.observed)} (${d.n.toLocaleString("en-US")} tickets)`, tip: true})
  ]
})));
```

<div class="note">The middle is well calibrated. At the extremes the calibration flattens, which is why probabilities are shown limited to 5%–95%.</div>

## Every project beats its own late rate

```js
const whenPP = view(Inputs.radio(["When filed", "On day 7"], {label: "Model", value: "When filed"}));
```

```js
const ppKey = whenPP === "When filed" ? "creation" : "day7";
const pp = Object.entries(quality.points[ppKey].models.boosting.per_project).map(([project, v]) => ({project, n: v.n, base: v.late_rate, pr: v.pr_auc, lift: v.lift_at_top10})).sort((a, b) => b.n - a.n);
display(resize((width) => Plot.plot({
  width, height: 60 + pp.length * 30, marginLeft: 90,
  x: {label: "PR-AUC (orange) against the project's own late rate (grey)", domain: [0, 1], grid: true},
  y: {label: null, domain: pp.map((d) => d.project)},
  marks: [
    Plot.link(pp, {x1: "base", x2: "pr", y: "project", stroke: "currentColor", strokeOpacity: 0.3, strokeWidth: 3}),
    Plot.dot(pp, {x: "base", y: "project", fill: C.gap, r: 5, stroke: dark ? "#111" : "#fff", strokeWidth: 1.5}),
    Plot.dot(pp, {x: "pr", y: "project", fill: C.orange, r: 5, stroke: dark ? "#111" : "#fff", strokeWidth: 1.5}),
    Plot.text(pp, {x: "pr", y: "project", text: (d) => `${d.pr.toFixed(2)}  (n=${d.n.toLocaleString("en-US")})`, dx: 10, textAnchor: "start"})
  ]
})));
```

## How risk moves with five signals

Average effect on a ticket's risk, in percentage points, at filing. Positive means more likely to run late.

```js
const DEP = [["assignee_open", "Assigned when filed?"], ["reporter_prior_tickets", "Reporter's earlier tickets"], ["description_length", "Description length (characters)"], ["project_open", "Open tickets in the project"], ["priority_rank", "Priority within its project's scale"]];
function depChart([f, title]) {
  const bins = drivers.creation.dependence[f].filter((d) => d.bin !== "missing");
  const nice = (b) => b.replace(/^\((-?[\d.]+), ([\d.]+)\]$/, (_, a, c) => `${Math.round(+a)}–${Math.round(+c)}`);
  return html`<div><h4 style="margin:.6rem 0 .1rem">${title}</h4>${resize((width) => Plot.plot({
    width, height: 220, marginBottom: 42, x: {label: null, domain: bins.map((d) => nice(d.bin)), tickRotate: bins.length > 4 ? -20 : 0},
    y: {label: "points", grid: true},
    marks: [Plot.ruleY([0]), Plot.barY(bins, {x: (d) => nice(d.bin), y: "mean_points", fill: (d) => (d.mean_points >= 0 ? C.orange : C.aqua), inset: 1, title: (d) => `${nice(d.bin)}: ${d.mean_points > 0 ? "+" : ""}${d.mean_points} points (${d.n.toLocaleString("en-US")} tickets)`, tip: true})]
  }))}</div>`;
}
display(html`<div class="grid grid-cols-2" style="gap:1rem">${DEP.map(depChart)}</div>`);
```

<div class="note">Orange raises risk, green lowers it. Priority is not monotonic: both the top and bottom priorities lower risk. "Reporter's earlier tickets" counts how many tickets the reporter had filed before, never who they are.</div>

## Check the model against what happened

Pick a sample ticket from the test period and see what the model said at the time, why, and what happened.

```js
const bPoint = view(Inputs.radio(["When filed", "On day 7"], {label: "Score the ticket", value: "When filed"}));
const bOutcome = view(Inputs.select(["All", "Ran late", "Not late"], {label: "What happened"}));
const bFlag = view(Inputs.select(["All", "Riskiest 10%", "The rest"], {label: "Model's verdict"}));
const bProjects = [...new Set(backtest.map((d) => d.project))].sort();
const bChosen = view(Inputs.checkbox(bProjects, {label: "Projects", value: bProjects}));
```

```js
const bp = bPoint === "When filed" ? "creation" : "day7";
const pool = backtest.filter((d) => d.point === bp && bChosen.includes(d.project));
const shown = pool.filter((d) => (bOutcome === "All" || (bOutcome === "Ran late") === !!d.late) && (bFlag === "All" || (bFlag === "Riskiest 10%") === d.top10)).sort((a, b) => b.p - a.p);
const rate = (xs) => (xs.length ? xs.filter((d) => d.late).length / xs.length : NaN);
display(html`<p class="muted">${shown.length.toLocaleString("en-US")} of ${pool.length.toLocaleString("en-US")} sampled tickets. In this sample, ${pct(rate(pool.filter((d) => d.top10)))} of the riskiest 10% ran late against ${pct(rate(pool.filter((d) => !d.top10)))} of the rest.</p>`);
const picked = view(Inputs.table(shown, {
  columns: ["p", "key", "project", "type", "created", "late"],
  header: {p: "Risk", key: "Ticket", project: "Project", type: "Type", created: "Filed", late: "What happened"},
  format: {p: riskBar, late: (d) => (d ? "Ran late" : "Not late")},
  width: {p: 140, key: 150, project: 100, type: 120, created: 100, late: 110},
  multiple: false, required: false, value: shown[0], rows: 10, maxHeight: 380
}));
```

```js
display(ticketDetail(picked, {base: meta.points[bp].base_rate_test}));
```

## Limits

- One time split, one test window. This is not a rolling backtest.
- The late rate drifts up over time (${pct(meta.points.creation.base_rate_train)} in training, ${pct(meta.points.creation.base_rate_test)} in the test period at filing) because recent tickets stay open. Calibration, learned on the year before the test, held up.
- Results vary by about ±0.002 PR-AUC between identical runs.
- The model finds associations in past data, not causes. Do not read "assign tickets when filing them" as a recommendation.
