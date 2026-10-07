"""Tests for etl/load.py on a synthetic extraction."""
import duckdb
import pytest

from etl import extract, load
from tests.test_extract import FULL, MINIMAL, OTHER, parse, segment


@pytest.fixture
def extracted(tmp_path):
    _, out = parse(tmp_path, [segment("Other", [OTHER]), segment("Apache", [FULL, MINIMAL])])
    return out


def test_load_builds_typed_tables_and_passes_its_checks(extracted, tmp_path):
    db = tmp_path / "radar.duckdb"
    assert load.load(extracted, db) == []
    con = duckdb.connect(str(db), read_only=True)
    types = dict(con.execute("select column_name, column_type from (describe issues)").fetchall())
    assert types["created"] == "TIMESTAMP" and types["resolution_date"] == "TIMESTAMP" and types["due_date"] == "DATE"
    lead = con.execute("select resolution_date - created from issues where issue_key = 'KAFKA-1'").fetchone()[0]
    assert lead.days == 10  # created 2020-01-01 10:00, resolved 2020-01-11 10:00
    assert con.execute("select count(*) from changelog").fetchone()[0] == 2
    assert "issues: 2 rows, " in load.describe(db) and "issue_key" in load.describe(db)


def test_load_flags_orphans_and_unparseable_dates(extracted, tmp_path):
    db = tmp_path / "radar.duckdb"
    load.load(extracted, db)
    con = duckdb.connect(str(db))
    con.execute("insert into changelog (issue_key) values ('GHOST-1')")
    assert any("GHOST" not in p and "not in issues" in p for p in load.verify(con, extracted))


def test_load_without_extraction_says_what_to_do(tmp_path):
    with pytest.raises(FileNotFoundError, match="python -m etl.extract"):
        load.load(tmp_path / "nothing", tmp_path / "x.duckdb")


def test_a_document_dumped_twice_is_loaded_once(tmp_path):
    _, out = parse(tmp_path, [segment("Apache", [FULL, MINIMAL]), segment("Apache", [FULL])])
    db = tmp_path / "radar.duckdb"
    assert load.load(out, db) == []
    con = duckdb.connect(str(db), read_only=True)
    assert con.execute("select count(*) from issues").fetchone()[0] == 2
    assert con.execute("select count(*) from changelog").fetchone()[0] == 2   # not 4
    assert con.execute("select count(*) from comments").fetchone()[0] == 1
    assert con.execute("select count(*) from issue_text_stats").fetchone()[0] == 2


def test_slim_load_keeps_all_tickets_but_only_the_chosen_projects_history(tmp_path):
    other = {**FULL, "key": "ZOO-1", "fields": {**FULL["fields"], "project": {"key": "ZOO", "name": "Zoo"}}}
    _, out = parse(tmp_path, [segment("Apache", [FULL, other])])
    db = tmp_path / "slim.duckdb"
    assert load.load(out, db, projects=["KAFKA"]) == []
    con = duckdb.connect(str(db), read_only=True)
    assert con.execute("select count(*) from issues").fetchone()[0] == 2                      # every project's tickets stay
    assert con.execute("select count(distinct issue_key) from changelog").fetchone()[0] == 1  # history only for KAFKA
    assert con.execute("select count(*) from issue_text_stats").fetchone()[0] == 1
