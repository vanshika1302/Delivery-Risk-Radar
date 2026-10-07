"""Build the analysis layers in DuckDB: scope and data quality, status stages, and the "late" label.

Runs sql/02_*.sql, sql/03_*.sql and sql/04_*.sql in order, with parameters from config/params.toml,
then prints a report and runs checks (unmapped statuses, how labelable the test window is).

Run from the repo root:  python -m etl.transform
"""
from __future__ import annotations

import argparse
import tomllib
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "data" / "processed" / "radar.duckdb"
DEFAULT_PARAMS = ROOT / "config" / "params.toml"
SQL_DIR = ROOT / "sql"
STAGE_CSV = ROOT / "config" / "stage_mapping.csv"
PRIORITY_CSV = ROOT / "config" / "priority_rank.csv"
MIN_TEST_LABELABLE = 0.90


def sql_list(values) -> str:
    return "(SELECT unnest([" + ", ".join("'" + str(v).replace("'", "''") + "'" for v in values) + "]))"


def substitutions(params: dict) -> dict:
    return {
        "$PROJECTS": sql_list(params["scope"]["projects"]),
        "$EXCLUDED_TYPES": sql_list(params["scope"]["excluded_issue_types"]),
        "$DELIVERED": sql_list(params["scope"]["delivered_resolutions"]),
        "$MIN_CREATED": params["scope"]["min_created"],
        "$SNAPSHOT": params["scope"]["snapshot"],
        "$TOO_FAST_HOURS": str(params["scope"]["too_fast_hours"]),
        "$BULK_MIN": str(params["scope"]["bulk_min_tickets"]),
        "$PERCENTILE": str(params["late"]["percentile"]),
        "$MIN_GROUP": str(params["late"]["min_group_size"]),
        "$TRAIN_CUTOFF": params["split"]["train_cutoff"],
        "$TEST_START": params["split"]["test_start"],
        "$TEST_END": params["split"]["test_end"],
        "$STAGE_CSV": str(STAGE_CSV),
        "$PRIORITY_CSV": str(PRIORITY_CSV),
        "$JIRA_REVIEW_PROJECTS": sql_list(params.get("features", {}).get("jira_review_projects", [])),
        "$POINT_DAYS": str(params.get("features", {}).get("day7_after_days", 7)),
        "$PEER_PRECEDING": str(params.get("features", {}).get("peer_window", 200) - 1),
    }


def render(sql: str, subs: dict) -> str:
    for key in sorted(subs, key=len, reverse=True):
        sql = sql.replace(key, subs[key])
    return sql


def transform(db=DEFAULT_DB, params_path=DEFAULT_PARAMS):
    """Run the SQL layers. Returns (report text, list of problems)."""
    params = tomllib.loads(Path(params_path).read_text())
    con = duckdb.connect(str(db))
    try:
        from etl.load import configure
        configure(con, params)
        run_layers(con, params)
        return report(con, params)
    finally:
        con.close()


def run_layers(con, params):
    subs = substitutions(params)
    for f in sorted(SQL_DIR.glob("0[2-9]_*.sql")):
        con.execute(render(f.read_text(), subs))


def report(con, params) -> tuple[str, list[str]]:
    q = lambda s: con.execute(s).fetchall()
    pct = lambda v: "-" if v is None else f"{v}%"
    out, problems = [], []
    out.append("Tickets in the chosen projects, by exclusion reason (None = kept):")
    for r in q("select coalesce(exclusion_reason, 'kept'), count(*) from tickets group by 1 order by 2 desc"):
        out.append(f"  {r[0]:<16}{r[1]:>9,}")
    out.append("\nLabel status:")
    for r in q("select label_status, count(*) from labels group by 1 order by 2 desc"):
        out.append(f"  {r[0]:<24}{r[1]:>9,}")
    out.append("\nLate rate by split (train counts train_eligible tickets only). 'all' includes open tickets already past their threshold:")
    for r in q("""select split, count(is_late), round(100 * avg(is_late::int), 1), count(is_late_delivered_only), round(100 * avg(is_late_delivered_only::int), 1)
                  from labels where (split <> 'train' or train_eligible) group by 1 order by 1"""):
        out.append(f"  {r[0]:<8} all: {r[1]:>7,} tickets {pct(r[2]):>6} late   delivered only: {r[3]:>7,} tickets {pct(r[4]):>6} late")
    out.append("\nThreshold level used, labelled tickets:")
    for r in q("select threshold_level, count(*) from labels where label_status in ('labelled','open_known_late') group by 1 order by 2 desc"):
        out.append(f"  {str(r[0]):<14}{r[1]:>9,}")
    out.append("\nPer project: delivered tickets, P75 lead days (peer-group fallback level 'project'), late rate")
    for r in q("""select l.project_key, count(*), round(any_value(p.threshold_days), 1), round(100 * avg(l.is_late::int), 1)
                  from labels l left join peer_thresholds p on p.level = 'project' and p.project_key = l.project_key
                  where l.label_status = 'labelled' group by 1 order by 2 desc"""):
        out.append(f"  {r[0]:<10}{r[1]:>8,}   P75 {r[2]!s:>6}   late {pct(r[3]):>6}")
    unmapped = q("select status, count(*) from status_intervals where stage = 'Unmapped' group by 1 order by 2 desc")
    if unmapped:
        problems.append("statuses missing from config/stage_mapping.csv: " + ", ".join(f"{s} ({n})" for s, n in unmapped))
    out.append("\nStage mapping: " + ("complete" if not unmapped else "INCOMPLETE"))
    share = q(f"""select count(*) filter (where label_status in ('labelled','open_known_late')),
                         count(*) filter (where label_status in ('labelled','open_known_late','open_unlabelled'))
                  from labels where split = 'test' and label_status not like 'excluded:%' and label_status <> 'not_delivered'""")[0]
    labelable = share[0] / share[1] if share[1] else 0.0
    out.append(f"Test window labelable: {labelable:.1%} of {share[1]:,} tickets (needs at least {MIN_TEST_LABELABLE:.0%})")
    if labelable < MIN_TEST_LABELABLE:
        problems.append(f"test window is only {labelable:.1%} labelable; move split.test_end earlier")
    return "\n".join(out), problems


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--db", default=str(DEFAULT_DB))
    p.add_argument("--params", default=str(DEFAULT_PARAMS))
    a = p.parse_args(argv)
    text, problems = transform(Path(a.db), Path(a.params))
    print(text)
    if problems:
        print("\nPROBLEMS:\n  " + "\n  ".join(problems))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
