"""Load features and labels from DuckDB, and define which columns a model may use.

The allowlist is default-deny (see GLOSSARY.md, "Allowlisted feature"): only the columns named here reach a model.
NEVER_USE lists what must never reach one; tests check the two stay disjoint and that the features table holds nothing else.
"""
from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "processed" / "radar.duckdb"

CATEGORICAL = ["project_key", "workflow_family", "issue_type"]
# Counts and sizes with long right tails: modelled on a log scale by the linear model.
LOG_NUMERIC = ["component_count", "link_count", "title_length", "description_length", "project_open", "assignee_open",
               "reporter_prior_tickets", "peer_n", "peer_median_lead_days", "project_median_lead_days"]
LINEAR_NUMERIC = ["priority_rank", "reporter_first_time", "peer_late_rate", "project_late_rate"]

DAY7_CATEGORICAL = ["stage_at_day7"]
DAY7_LOG_NUMERIC = ["events_by_day7", "comments_by_day7", "commenters_by_day7", "days_since_activity_day7",
                    "days_in_stage_day7", "review_rounds_by_day7"]
DAY7_LINEAR_NUMERIC = ["has_assignee", "entered_active_by_day7", "entered_review_by_day7"]

IDENTIFIERS = ["issue_key", "point", "t_at"]
# What a model must never see: outcomes and anything known only after the prediction point.
NEVER_USE = {"resolution", "resolution_date", "status", "updated", "fix_versions", "is_late", "is_late_delivered_only",
             "label_status", "lead_days", "age_days", "threshold_days", "threshold_level", "train_eligible", "split",
             "reopen_count", "is_delivered", "is_resolved", "exclusion_reason", "created", "cycle_days",
             "wait_to_first_review_days", "first_active_at", "first_review_at", "review_rounds"}

LABEL_COLUMNS = ["is_late", "is_late_delivered_only", "label_status", "split", "train_eligible", "created", "resolution_date",
                 "lead_days", "threshold_days"]


def feature_lists(point: str) -> dict[str, list[str]]:
    """Feature columns for a prediction point, grouped by how the linear model treats them."""
    if point not in ("creation", "day7"):
        raise ValueError(f"unknown prediction point {point!r}")
    day7 = point == "day7"
    return {
        "categorical": CATEGORICAL + (DAY7_CATEGORICAL if day7 else []),
        "log": LOG_NUMERIC + (DAY7_LOG_NUMERIC if day7 else []),
        "linear": LINEAR_NUMERIC + (DAY7_LINEAR_NUMERIC if day7 else []),
    }


def feature_columns(point: str) -> list[str]:
    f = feature_lists(point)
    cols = f["categorical"] + f["log"] + f["linear"]
    if point == "creation":  # assignment is a day-7 signal; at creation only the assignee's workload (empty when unassigned)
        cols = [c for c in cols if c != "has_assignee"]
    return cols


def all_allowed_columns() -> set[str]:
    return set(IDENTIFIERS) | set(feature_columns("creation")) | set(feature_columns("day7"))


def normalise_dtypes(df: pd.DataFrame) -> pd.DataFrame:
    """Booleans and nullable integers (what DuckDB returns for columns with NULLs) become plain floats, with NaN for missing."""
    df = df.copy()
    for c in df.columns:
        if str(df[c].dtype) in ("bool", "boolean") or (pd.api.types.is_extension_array_dtype(df[c]) and pd.api.types.is_numeric_dtype(df[c])):
            df[c] = df[c].astype("float64")
    return df


def load(point: str, db: Path | str = DEFAULT_DB, projects=None) -> pd.DataFrame:
    """Features joined to labels for one prediction point. Booleans become 0/1 so every model sees numbers."""
    con = duckdb.connect(str(db), read_only=True)
    try:
        label_cols = ", ".join(f"l.{c}" for c in LABEL_COLUMNS)
        where = "f.point = ?" + (" AND f.project_key IN (SELECT unnest(?))" if projects else "")
        args = [point] + ([list(projects)] if projects else [])
        df = con.execute(f"SELECT f.*, {label_cols}, l.label_status AS _ls FROM features f JOIN labels l USING (issue_key) WHERE {where}", args).df()
    finally:
        con.close()
    df = normalise_dtypes(df.drop(columns=["_ls"]))
    for c in ("is_late", "is_late_delivered_only"):
        df[c] = df[c].astype("float64")
    return df
