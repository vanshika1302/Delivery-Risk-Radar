"""Tests for the SQL layers (scope, stages, labels) on hand-made tickets with known answers."""
import tomllib
from datetime import datetime, timedelta
from pathlib import Path

import duckdb
import pytest

from etl import transform

D = lambda s: datetime.fromisoformat(s)
PARAMS = {
    "scope": {"projects": ["P1"], "excluded_issue_types": ["Epic", "Sub-task"],
              "delivered_resolutions": ["Fixed", "Done"], "min_created": "2001-01-01", "snapshot": "2021-06-01",
              "too_fast_hours": 1, "bulk_min_tickets": 10},
    "late": {"percentile": 0.75, "min_group_size": 30},
    "split": {"train_cutoff": "2020-01-01", "test_start": "2020-02-01", "test_end": "2021-01-01"},
    "features": {"jira_review_projects": ["P1"], "day7_after_days": 7, "peer_window": 200},
}
ISSUES = []     # (key, type, status, resolution, created, resolved)
EVENTS = []     # (key, history_id, at, from, to)


def ticket(key, created, resolved=None, resolution="Fixed", type_="Bug", status=None, project="P1"):
    ISSUES.append((key, project, type_, status or ("Closed" if resolved else "Open"),
                   resolution if resolved else None, D(created), D(resolved) if resolved else None))


def status_change(key, at, frm, to):
    EVENTS.append((key, str(len(EVENTS) + 1), D(at), frm, to))


@pytest.fixture(scope="module")
def con():
    ISSUES.clear(); EVENTS.clear()
    base = D("2019-01-01")
    for i in range(40):  # training pool: Bugs with lead 1..40 days, P75 = 30.25
        c = base + timedelta(days=i)
        ticket(f"T{i}", c.isoformat(), (c + timedelta(days=i + 1)).isoformat())
    ticket("A_not_late", "2020-03-01T00:00", "2020-03-11T00:00")           # lead 10
    ticket("B_late", "2020-03-01T00:00", "2020-04-01T00:00")               # lead 31 > 30.25
    ticket("C_on_threshold", "2020-03-01T00:00", "2020-03-31T00:00")       # lead 30
    ticket("D_duplicate", "2020-03-01T00:00", "2020-03-05T00:00", resolution="Duplicate")
    ticket("E_open_old", "2020-03-01T00:00")                                # open, age far above threshold
    ticket("F_open_young", "2021-05-25T00:00")                              # open, 7 days old
    ticket("G_too_fast", "2020-03-01T00:00", "2020-03-01T00:30")
    ticket("H_bad_date", "1999-01-01T00:00", "1999-03-01T00:00")
    ticket("I_epic", "2020-03-01T00:00", "2020-06-01T00:00", type_="Epic")
    ticket("J_task_fallback", "2020-03-01T00:00", "2020-04-15T00:00", type_="Task")  # type group too small -> project level
    ticket("K_reopened", "2020-03-01T00:00", "2020-04-20T00:00")           # final resolution on day 50
    ticket("L_known_late_at_cutoff", "2019-12-01T00:00", "2020-06-01T00:00")   # age 31 days at cutoff > 30.25
    ticket("M_unknown_at_cutoff", "2019-12-20T00:00", "2020-03-01T00:00")      # age 12 days at cutoff
    ticket("N_other_project", "2020-03-01T00:00", "2020-03-05T00:00", project="P2")
    ticket("O_flow", "2020-03-01T00:00", "2020-03-11T00:00")
    ticket("P_rework", "2020-03-01T00:00", "2020-03-21T00:00")
    ticket("Q_weird", "2020-03-01T00:00", "2020-03-06T00:00")
    ticket("S_fast", "2020-03-01T00:00", "2020-03-06T00:00")
    ticket("R_too_recent", "2021-05-30T00:00")
    status_change("K_reopened", "2020-03-06T00:00", "Open", "Resolved")
    status_change("K_reopened", "2020-03-10T00:00", "Resolved", "Reopened")
    status_change("K_reopened", "2020-04-20T00:00", "Reopened", "Resolved")
    status_change("O_flow", "2020-03-03T00:00", "Open", "Patch Available")
    status_change("O_flow", "2020-03-11T00:00", "Patch Available", "Resolved")
    status_change("P_rework", "2020-03-02T00:00", "Open", "Patch Available")
    status_change("P_rework", "2020-03-05T00:00", "Patch Available", "Open")
    status_change("P_rework", "2020-03-08T00:00", "Open", "In Progress")
    status_change("P_rework", "2020-03-12T00:00", "In Progress", "Patch Available")
    status_change("P_rework", "2020-03-21T00:00", "Patch Available", "Resolved")
    status_change("Q_weird", "2020-03-03T00:00", "Open", "Weird Status")
    status_change("Q_weird", "2020-03-06T00:00", "Weird Status", "Resolved")

    # Real resolved tickets always carry their resolve transition in the changelog; give the plain fixture tickets one too.
    with_events = {e[0] for e in EVENTS}
    for key, _proj, _type, status, resolution, _created, resolved in ISSUES:
        if resolved is not None and key not in with_events:
            status_change(key, resolved.isoformat(), "Open", status)

    c = duckdb.connect()
    c.execute("create table issues (issue_key varchar, project_key varchar, issue_type varchar, status varchar, resolution varchar, created timestamp, resolution_date timestamp, priority varchar, assignee varchar, reporter varchar, components varchar[], link_count integer, comment_count integer)")
    c.executemany("insert into issues (issue_key, project_key, issue_type, status, resolution, created, resolution_date) values (?,?,?,?,?,?,?)", ISSUES)
    c.execute("create table changelog (issue_key varchar, history_id varchar, created timestamp, author varchar, field varchar, from_value varchar, from_string varchar, to_value varchar, to_string varchar)")
    c.executemany("insert into changelog (issue_key, history_id, created, field, from_string, to_string) values (?,?,?, 'status', ?, ?)", EVENTS)
    c.execute("create table comments (issue_key varchar, comment_id varchar, created timestamp, updated timestamp, author varchar, body_length integer)")
    c.execute("create table issue_text_stats (issue_key varchar, summary_length bigint, description_length bigint)")
    c.execute("insert into issue_text_stats select issue_key, 20, 100 from issues")
    transform.run_layers(c, PARAMS)
    return c


def label(con, key):
    r = con.execute("select label_status, is_late, is_late_delivered_only, threshold_level, round(threshold_days, 2), split, train_eligible from labels where issue_key = ?", [key]).fetchone()
    return r


def test_only_chosen_projects_and_types_are_in_scope(con):
    keys = {r[0] for r in con.execute("select issue_key from tickets").fetchall()}
    assert "I_epic" not in keys and "N_other_project" not in keys and "A_not_late" in keys


def test_threshold_is_the_peer_group_percentile_from_training_only(con):
    assert label(con, "A_not_late")[4] == 30.25 and label(con, "A_not_late")[3] == "project_type"


def test_late_means_strictly_above_the_threshold(con):
    assert label(con, "A_not_late")[:2] == ("labelled", False)
    assert label(con, "C_on_threshold")[:2] == ("labelled", False)
    assert label(con, "B_late")[:2] == ("labelled", True)


def test_non_delivered_and_excluded_tickets_get_no_label(con):
    assert label(con, "D_duplicate")[:3] == ("not_delivered", None, None)
    assert label(con, "G_too_fast")[0] == "excluded:too_fast"
    assert label(con, "H_bad_date")[0] == "excluded:bad_created"


def test_open_tickets_late_only_once_past_threshold(con):
    assert label(con, "E_open_old")[:3] == ("open_known_late", True, None)  # delivered-only variant leaves it out
    assert label(con, "F_open_young")[:3] == ("open_unlabelled", None, None)


def test_small_peer_group_falls_back_to_the_project(con):
    assert label(con, "J_task_fallback")[3:5] == ("project", 30.25)


def test_reopened_ticket_uses_its_final_resolution(con):
    assert label(con, "K_reopened")[:2] == ("labelled", True)  # lead 50 days, not 5


def test_training_only_uses_labels_known_at_the_cutoff(con):
    assert label(con, "L_known_late_at_cutoff")[5:] == ("train", True)
    assert label(con, "M_unknown_at_cutoff")[5:] == ("train", False)


def test_splits_follow_creation_time(con):
    assert label(con, "T0")[5] == "train"
    assert label(con, "A_not_late")[5] == "test"        # created 2020-03-01
    assert label(con, "F_open_young")[5] == "after"     # created 2021-05-25


def stages(con, key):
    return dict(zip(("waiting", "building", "in_review", "rounds", "reopens"), con.execute(
        "select round(waiting_days, 1), round(building_days, 1), round(in_review_days, 1), review_rounds, reopen_count from ticket_stages where issue_key = ?", [key]).fetchone()))


def test_stage_durations_from_status_history(con):
    assert stages(con, "O_flow") == {"waiting": 2.0, "building": 0.0, "in_review": 8.0, "rounds": 0, "reopens": 0}


def test_rework_loops_are_counted_and_time_is_summed(con):
    s = stages(con, "P_rework")
    assert s["rounds"] == 1 and s["in_review"] == 3.0 + 9.0 and s["building"] == 4.0 and s["waiting"] == 1.0 + 3.0


def test_cycle_time_and_wait_to_first_review(con):
    r = con.execute("select round(cycle_days, 1), round(wait_to_first_review_days, 1) from ticket_flow where issue_key = 'O_flow'").fetchone()
    assert r == (8.0, 2.0)      # active from day 2 to day 10; first review after 2 days
    r = con.execute("select cycle_days, wait_to_first_review_days from ticket_flow where issue_key = 'A_not_late'").fetchone()
    assert r == (None, None)    # never entered an active stage


def test_reopened_ticket_counts_the_reopen_and_the_resolved_gap(con):
    s = stages(con, "K_reopened")
    assert s["reopens"] == 1
    assert con.execute("select round(resolved_gap_days, 1) from ticket_stages where issue_key = 'K_reopened'").fetchone()[0] == 4.0


def test_unmapped_status_is_reported(con):
    text, problems = transform.report(con, PARAMS)
    assert any("Weird Status" in p for p in problems)


def test_shipped_params_file_is_complete():
    params = tomllib.loads((Path(transform.ROOT) / "config" / "params.toml").read_text())
    assert set(transform.substitutions(params)) >= {"$PROJECTS", "$TRAIN_CUTOFF", "$TEST_END", "$PERCENTILE"}


def test_analysis_covers_only_labelled_delivered_tickets(con):
    keys = {r[0] for r in con.execute("select issue_key from analysis_base").fetchall()}
    assert {"A_not_late", "B_late", "C_on_threshold", "K_reopened"} <= keys
    assert not keys & {"D_duplicate", "E_open_old", "F_open_young", "G_too_fast", "H_bad_date"}


def test_analysis_late_rate_is_delivered_only(con):
    late, n = con.execute("select round(100 * avg(is_late::int), 1), count(*) from analysis_base where issue_key in ('A_not_late', 'B_late', 'C_on_threshold', 'K_reopened')").fetchone()
    assert (late, n) == (50.0, 4)   # B_late and K_reopened are late; open tickets are not in this table


def test_stage_shares_add_up_to_the_whole_lead_time(con):
    row = con.execute("select waiting_pct + building_pct + in_review_pct + resolved_gap_pct from analysis_stage_share where project_key = 'P1'").fetchone()[0]
    assert abs(row - 100) < 1.0


def test_day7_point_needs_the_ticket_to_be_open_on_day_7_and_inside_the_data(con):
    pts = {r[0]: r[1] for r in con.execute("select issue_key, string_agg(point, ',' order by point) from features group by 1").fetchall()}
    assert pts["A_not_late"] == "creation,day7"   # resolved on day 10, so still open on day 7
    assert pts["S_fast"] == "creation"            # resolved on day 5, before day 7
    assert pts["E_open_old"] == "creation,day7"
    assert pts["F_open_young"] == "creation,day7" # day 7 is exactly the snapshot, still inside the data
    assert pts["R_too_recent"] == "creation"      # day 7 falls after the snapshot: its state at day 7 is unknown
    # Resolved on day 5, reopened on day 9, finally resolved on day 50: it was not open on day 7, so no day-7 row.
    assert pts["K_reopened"] == "creation"


def test_creation_features_use_as_of_values(con):
    r = con.execute("select priority_rank, component_count, link_count from features where issue_key = 'A_not_late' and point = 'creation'").fetchone()
    assert r[1] == 0 and r[2] == 0
