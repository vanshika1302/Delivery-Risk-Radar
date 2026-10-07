"""Load the extracted Parquet files into a DuckDB file and report what is in it.

Runs sql/01_load_tables.sql (typing the date columns), then checks the load against the
Parquet files and prints row counts and column names for every table.

Run from the repo root:  python -m etl.load
"""
from __future__ import annotations

import argparse
import tomllib
from pathlib import Path

import duckdb

DEFAULT_RAW = Path("data/raw/apache_jira")
DEFAULT_DB = Path("data/processed/radar.duckdb")
ROOT = Path(__file__).resolve().parent.parent
SQL_FILE = ROOT / "sql" / "01_load_tables.sql"
PARAMS_FILE = ROOT / "config" / "params.toml"
TABLES = ["issues", "changelog", "comments", "issue_text_stats"]
PARQUET = {"issues": "issues", "changelog": "changelog", "comments": "comments", "issue_text_stats": "issue_text"}


def sql_list(values) -> str:
    return "(SELECT unnest([" + ", ".join("'" + str(v).replace("'", "''") + "'" for v in values) + "]))"


def configure(con, params: dict | None = None):
    """Cap DuckDB's memory and temporary spill space so a heavy query cannot fill the disk."""
    d = (params or {}).get("duckdb", {})
    con.execute(f"SET memory_limit = '{d.get('memory_limit', '3GB')}'")
    con.execute(f"SET max_temp_directory_size = '{d.get('max_temp_size', '2GB')}'")


def load(raw: Path = DEFAULT_RAW, db: Path = DEFAULT_DB, projects=None, params: dict | None = None) -> list[str]:
    """Build the DuckDB tables. Returns a list of problems (empty means all checks passed).

    projects: keep changelog, comments and ticket text only for these project keys (None keeps all).
    """
    raw, db = Path(raw), Path(db)
    missing = [f for f in PARQUET.values() if not (raw / f"{f}.parquet").exists()]
    if missing:
        raise FileNotFoundError(f"{raw} is missing {missing}. Run `python -m etl.extract` first.")
    db.parent.mkdir(parents=True, exist_ok=True)
    for stale in (db, Path(str(db) + ".wal")):  # derived data: rebuild from scratch so the file stays small
        stale.unlink(missing_ok=True)
    con = duckdb.connect(str(db))
    try:
        configure(con, params)
        keep = sql_list(projects) if projects else "(SELECT DISTINCT project_key FROM read_parquet('" + str(raw.resolve()) + "/issues.parquet'))"
        con.execute(SQL_FILE.read_text().replace("$RAW", str(raw.resolve())).replace("$KEEP_PROJECTS", keep))
        return verify(con, raw, projects)
    finally:
        con.close()


def verify(con, raw: Path, projects=None) -> list[str]:
    """Check the load against the Parquet files. Rows may only be dropped as duplicates of a doubled ticket."""
    raw = Path(raw).resolve()
    problems = []
    in_scope = f"issue_key in (select issue_key from read_parquet('{raw}/issues.parquet') where project_key in {sql_list(projects)})" if projects else "true"
    dup_keys = f"(select issue_key from read_parquet('{raw}/issues.parquet') group by 1 having count(*) > 1)"
    for table, file in PARQUET.items():
        scope = "true" if table == "issues" else in_scope   # `issues` keeps every project; the child tables keep the chosen ones
        loaded = con.execute(f"select count(*) from {table}").fetchone()[0]
        source = con.execute(f"select count(*) from read_parquet('{raw}/{file}.parquet') where {scope}").fetchone()[0]
        in_dups = con.execute(f"select count(*) from read_parquet('{raw}/{file}.parquet') where {scope} and issue_key in {dup_keys}").fetchone()[0]
        if loaded > source or source - loaded > in_dups:
            problems.append(f"{table}: {loaded} rows loaded from {source} in the Parquet file ({in_dups} belong to doubled tickets)")
    dupes = con.execute("select count(*) from (select issue_key from issues group by 1 having count(*) > 1)").fetchone()[0]
    if dupes:
        problems.append(f"issues: {dupes} duplicate issue_key values")
    for t in ("changelog", "comments", "issue_text_stats"):
        orphans = con.execute(f"select count(*) from {t} where issue_key not in (select issue_key from issues)").fetchone()[0]
        if orphans:
            problems.append(f"{t}: {orphans} rows point at a ticket that is not in issues")
    for col in ("created", "resolution_date"):
        lost = con.execute(
            f"select count(*) from read_parquet('{raw}/issues.parquet') "
            f"where {col} is not null and try_strptime({col}, '%Y-%m-%dT%H:%M:%S.%g%z') is null").fetchone()[0]
        if lost:
            problems.append(f"issues.{col}: {lost} dates could not be parsed")
    return problems


def describe(db: Path = DEFAULT_DB) -> str:
    """Row counts and column names (with types) for every table, as text."""
    con = duckdb.connect(str(db), read_only=True)
    try:
        lines = []
        for t in TABLES:
            n = con.execute(f"select count(*) from {t}").fetchone()[0]
            cols = con.execute(f"select column_name, column_type from (describe {t})").fetchall()
            lines.append(f"{t}: {n:,} rows, {len(cols)} columns")
            lines.extend(f"    {name:<22} {typ}" for name, typ in cols)
        return "\n".join(lines)
    finally:
        con.close()


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--raw", default=str(DEFAULT_RAW))
    p.add_argument("--db", default=str(DEFAULT_DB))
    p.add_argument("--projects", nargs="*", default=None, help="keep history only for these projects (default: the scope in config/params.toml)")
    p.add_argument("--all-projects", action="store_true", help="keep the changelog and comments of every project (large)")
    a = p.parse_args(argv)
    params = tomllib.loads(PARAMS_FILE.read_text())
    projects = None if a.all_projects else (a.projects or params["scope"]["projects"])
    problems = load(Path(a.raw), Path(a.db), projects, params)
    print(describe(Path(a.db)))
    if problems:
        print("\nPROBLEMS:\n  " + "\n  ".join(problems))
        raise SystemExit(1)
    size = Path(a.db).stat().st_size / 1e9
    print(f"\nAll checks passed. DuckDB file: {a.db} ({size:.2f} GB)")


if __name__ == "__main__":
    main()
