---
title: Open tickets
---

```js
import {pct} from "./components/theme.js";
import {ticketDetail, riskBar} from "./components/reasons.js";
const meta = FileAttachment("data/meta.json").json();
const open = FileAttachment("data/open_tickets.json").json();
```

# Open tickets at risk

<p class="lede">The ${meta.points.creation.n_open_scored} tickets that were open at the snapshot (${meta.snapshot}) and not yet past their late threshold, ranked by the model's chance that they will run late.</p>

<div class="note">This is a snapshot from January 2022, not live data. Tickets already past their threshold are late by definition, so they are not scored. Scores are the chance of running late, calibrated on tickets the model had not seen; "High risk" means a score at or above <b>${pct(meta.points.creation.top10_cutoff)}</b> when filed (<b>${pct(meta.points.day7.top10_cutoff)}</b> on day 7), the level that only 10% of tickets in the test period reached.</div>

```js
const when = view(Inputs.radio(["When filed", "On day 7"], {label: "Score the ticket", value: "When filed"}));
const projectsAll = [...new Set(open.map((d) => d.project))].sort();
const chosen = view(Inputs.checkbox(projectsAll, {label: "Projects", value: projectsAll}));
```

```js
const point = when === "When filed" ? "creation" : "day7";
const rows = open.filter((d) => d.point === point && chosen.includes(d.project)).sort((a, b) => b.p - a.p);
display(html`<p class="muted">${rows.length} tickets${point === "day7" ? " (only tickets at least 7 days old have a day-7 score)" : ""}. ${rows.filter((d) => d.top10).length} are high risk.</p>`);
const selected = view(Inputs.table(rows, {
  columns: ["p", "key", "project", "type", "age_days", "top10"],
  header: {p: "Risk", key: "Ticket", project: "Project", type: "Type", age_days: "Open (days)", top10: "High risk"},
  format: {p: riskBar, age_days: (d) => Math.round(d), top10: (d) => (d ? "Yes" : "")},
  width: {p: 140, key: 150, project: 100, type: 120, age_days: 90, top10: 80},
  multiple: false, required: false, value: rows[0], rows: 12, maxHeight: 440
}));
```

```js
display(ticketDetail(selected, {base: meta.points[point].base_rate_test, outcome: false}));
```

## How to read a ticket

- **Risk** is the model's calibrated chance that the ticket will run late, limited to 5% to 95% because the model cannot be that certain.
- **Reasons** are the five features that pushed this ticket's score the most, with a plain-English description and an approximate size in percentage points. The four theme totals add up every feature, not only the five shown.
- **Comparisons** ("typical here") use the project's median in the training period.
- Nothing here is about people: reasons mention how many tickets a reporter filed or whether a ticket was assigned, never who.
