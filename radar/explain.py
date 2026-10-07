"""Explanations: exact SHAP values from the boosting model, turned into short plain-English reasons.

SHAP values are in the model's log-odds. They add up exactly to the model's output (checked on every call), and one-hot
categories are summed back to the original feature. Each ticket gets its top reasons, each with a theme and an approximate
size in percentage points (local linearisation: points = SHAP x p x (1 - p), p the model's raw probability).
Explanations describe what the model associates with lateness; they are not causes.
"""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
import shap

from radar.data import feature_columns

THEMES = {
    "assignee_open": "Ownership", "has_assignee": "Ownership", "reporter_prior_tickets": "Ownership",
    "reporter_first_time": "Ownership", "commenters_by_day7": "Ownership",
    "priority_rank": "Scope", "issue_type": "Scope", "component_count": "Scope", "link_count": "Scope",
    "title_length": "Scope", "description_length": "Scope",
    "project_open": "Workload",
    "project_key": "History", "workflow_family": "History", "peer_n": "History", "peer_median_lead_days": "History",
    "peer_late_rate": "History", "project_median_lead_days": "History", "project_late_rate": "History",
    "events_by_day7": "History", "comments_by_day7": "History", "days_since_activity_day7": "History",
    "stage_at_day7": "History", "days_in_stage_day7": "History", "entered_active_by_day7": "History",
    "entered_review_by_day7": "History", "review_rounds_by_day7": "History",
}
THEME_ORDER = ["Ownership", "Scope", "Workload", "History"]
STAGE_TEXT = {"Waiting": "waiting to be worked on", "Building": "being worked on", "In review": "in review", "Done": "marked done"}


DISPLAY_RANGE = (0.05, 0.95)


def display_probability(p):
    """Probabilities shown to people stay within 5% to 95%. The isotonic calibrator flattens into 0% and 100% plateaus where
    its validation data is thin (about 1% of tickets): the '0%' tickets were late 8% of the time and the '100%' ones 91%.
    Ranking and all metrics use the unclipped scores."""
    return np.clip(p, *DISPLAY_RANGE)


def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def original_feature(transformed_name: str, categorical: list[str]) -> str:
    """'cat__project_key_SPARK' -> 'project_key'; 'num__link_count' -> 'link_count'."""
    kind, rest = transformed_name.split("__", 1)
    if kind == "num":
        return rest
    return max((c for c in categorical if rest.startswith(c + "_")), key=len)


class Explainer:
    def __init__(self, bundle: dict):
        self.pipe, self.iso, self.features, self.point = bundle["model"], bundle["isotonic"], bundle["features"], bundle["point"]
        self.pre, self.hgb = self.pipe.named_steps["pre"], self.pipe.named_steps["model"]
        names = list(self.pre.get_feature_names_out())
        cats = [n.split("__", 1)[1] for n in names if n.startswith("cat__")]
        self.cat_features = sorted({c for c in self.features if any(n.startswith(f"cat__{c}_") for n in names)}, key=len)
        self.origin = [original_feature(n, self.cat_features) for n in names]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self.tree = shap.TreeExplainer(self.hgb)
        self.base = float(np.ravel(self.tree.expected_value)[0])

    def probabilities(self, df: pd.DataFrame):
        """(raw probability, calibrated probability)."""
        raw = self.pipe.predict_proba(df[self.features])[:, 1]
        return raw, self.iso.predict(raw)

    def contributions(self, df: pd.DataFrame, tolerance=1e-6) -> pd.DataFrame:
        """SHAP values by original feature, in log-odds. Raises if they do not add up to the model's output."""
        X = self.pre.transform(df[self.features])
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            sv = self.tree.shap_values(X)
        gap = np.abs(sv.sum(axis=1) + self.base - self.hgb.decision_function(X)).max()
        if gap > tolerance:
            raise AssertionError(f"SHAP values do not add up to the model output (max gap {gap:.2e})")
        frame = pd.DataFrame(sv, index=df.index, columns=self.origin)
        return frame.T.groupby(level=0).sum().T

    def importance(self, df: pd.DataFrame) -> pd.Series:
        return self.contributions(df).abs().mean().sort_values(ascending=False)


class Typical:
    """Typical values from the training period (known labels only), per project, for 'compared with typical' wording."""
    FEATURES = ["title_length", "description_length", "project_open", "assignee_open", "link_count", "component_count"]

    def __init__(self, train: pd.DataFrame):
        self.by_project = train.groupby("project_key")[self.FEATURES].median()
        self.overall = train[self.FEATURES].median()
        self.project_late = train.groupby("project_key")["is_late"].mean()
        self.late_overall = float(train["is_late"].mean())

    def get(self, project: str, feature: str) -> float:
        if project in self.by_project.index and not np.isnan(self.by_project.loc[project, feature]):
            return float(self.by_project.loc[project, feature])
        return float(self.overall[feature])


def _isnan(v):
    return v is None or (isinstance(v, float) and np.isnan(v))


def _length_word(v, t):
    return "Short" if v < 0.6 * t else ("Long" if v > 1.5 * t else "Typical")


def describe(feature: str, row: pd.Series, typ: Typical, point: str) -> str:
    """One plain-English sentence stating the fact about this ticket (not the direction of the effect)."""
    v = row.get(feature)
    project = row.get("project_key")
    when = "when filed" if point == "creation" else "by day 7"
    NAN_HANDLED = {"assignee_open", "reporter_prior_tickets", "priority_rank", "peer_n", "peer_median_lead_days", "peer_late_rate"}
    if _isnan(v) and feature not in NAN_HANDLED:
        return f"{feature.replace('_', ' ').capitalize()} not available"
    plural = lambda k, word: f"{int(k)} {word}{'' if int(k) == 1 else 's'}"
    if feature == "assignee_open":
        return f"Not assigned {when}" if _isnan(v) else f"Assigned {when} (assignee has {int(v)} other open tickets)"
    if feature == "has_assignee":
        return "Assigned by day 7" if v else "Still unassigned on day 7"
    if feature == "reporter_prior_tickets":
        return "Reporter unknown" if _isnan(v) else ("First ticket this reporter has filed" if v == 0 else f"Reporter has filed {plural(v, 'earlier ticket')}")
    if feature == "reporter_first_time":
        return "First-time reporter" if v else "Returning reporter"
    if feature == "commenters_by_day7":
        return "Nobody had commented by day 7" if v == 0 else f"{plural(v, 'person')} had commented by day 7".replace("persons", "people")
    if feature == "priority_rank":
        if _isnan(v):
            return "No priority set"
        band = "top" if v >= 0.9 else "upper" if v >= 0.65 else "middle" if v >= 0.4 else "lower" if v >= 0.15 else "bottom"
        return f"Priority is in the {band} part of its project's scale"
    if feature == "issue_type":
        return f"Issue type: {v}"
    if feature == "component_count":
        return "No component set" if v == 0 else f"{plural(v, 'component')} set"
    if feature == "link_count":
        return "No linked tickets" if v == 0 else f"{plural(v, 'linked ticket')}"
    if feature in ("title_length", "description_length"):
        what = "title" if feature == "title_length" else "description"
        if feature == "description_length" and v == 0:
            return "No description"
        t = typ.get(project, feature)
        return f"{_length_word(v, t)} {what} ({int(v)} characters; typical here {int(t)})"
    if feature == "project_open":
        return f"{int(v)} other tickets open in the project (typical {int(typ.get(project, feature))})"
    if feature == "project_key":
        rate = typ.project_late.get(project, typ.late_overall)
        return f"{project}: {rate:.0%} of past tickets here ran late (all projects {typ.late_overall:.0%})"
    if feature == "workflow_family":
        return "Review happens in Jira statuses (Patch Available)" if v == "jira_review" else "Review happens on GitHub, outside Jira statuses"
    if feature == "peer_n":
        return "No similar resolved tickets to compare with" if _isnan(v) else (f"Only {int(v)} similar tickets resolved so far to compare with" if v < 30 else f"Compared with the last {int(v)} similar tickets")
    if feature == "peer_median_lead_days":
        return "No similar resolved tickets to compare with" if _isnan(v) else f"Similar recent tickets took a median of {v:.1f} days"
    if feature == "peer_late_rate":
        return "No similar resolved tickets to compare with" if _isnan(v) else f"{v:.0%} of similar recent tickets ran late"
    if feature == "project_median_lead_days":
        return f"Recent tickets in the project took a median of {v:.1f} days"
    if feature == "project_late_rate":
        return f"{v:.0%} of recent tickets in the project ran late"
    if feature == "events_by_day7":
        return "No changes recorded in the first week" if v == 0 else f"{plural(v, 'change')} recorded in the first week"
    if feature == "comments_by_day7":
        return "No comments in the first week" if v == 0 else f"{plural(v, 'comment')} in the first week"
    if feature == "days_since_activity_day7":
        return f"{v:.1f} days since the last activity on day 7"
    if feature == "stage_at_day7":
        return f"Still {STAGE_TEXT.get(v, str(v).lower())} on day 7"
    if feature == "days_in_stage_day7":
        return f"{v:.1f} days in its current stage on day 7"
    if feature == "entered_active_by_day7":
        return "Work had started by day 7" if v else "No work had started by day 7"
    if feature == "entered_review_by_day7":
        return "Had reached review by day 7" if v else "Not yet in review on day 7"
    if feature == "review_rounds_by_day7":
        return "No review rounds yet" if v == 0 else f"{plural(v, 'review round')} so far"
    raise KeyError(f"no wording for feature {feature!r}")


def reasons(row: pd.Series, contrib: pd.Series, p_raw: float, typ: Typical, point: str, k: int = 5) -> dict:
    """Top-k reasons by size, with the four theme totals. Sizes are in approximate percentage points."""
    scale = 100.0 * p_raw * (1.0 - p_raw)
    pts = contrib * scale
    top = pts.reindex(pts.abs().sort_values(ascending=False).index)[:k]
    items = [{"feature": f, "theme": THEMES[f], "text": describe(f, row, typ, point), "points": round(float(v), 1)} for f, v in top.items()]
    themes = {t: round(float(sum(pts[f] for f in pts.index if THEMES[f] == t)), 1) for t in THEME_ORDER}
    return {"reasons": items, "themes": themes}


def stability(point: str, train: pd.DataFrame, sample: pd.DataFrame, best_params: dict, main: Explainer, folds=("2017-01-01", "2018-01-01"), n_boot=5, seed=0) -> dict:
    """How much the global importance ranking moves when the model is refit on bootstrap samples or on earlier data only."""
    from scipy.stats import spearmanr
    from radar import modeling
    cols = main.features
    ref = main.importance(sample)
    out = {"bootstrap": [], "earlier_data": []}
    rng = np.random.default_rng(seed)

    def compare(pipe):
        e = Explainer({"model": pipe, "isotonic": main.iso, "features": cols, "point": point})
        imp = e.importance(sample).reindex(ref.index).fillna(0.0)
        rho = float(spearmanr(ref.values, imp.values)[0])
        top3 = len(set(ref.index[:3]) & set(imp.sort_values(ascending=False).index[:3]))
        return {"spearman": round(rho, 3), "top3_overlap": top3, "top3": list(imp.sort_values(ascending=False).index[:3])}

    for _ in range(n_boot):
        idx = rng.integers(0, len(train), len(train))
        b = train.iloc[idx]
        out["bootstrap"].append(compare(modeling.make("boosting", point, best_params).fit(b[cols], b["is_late"])))
    cutoffs = pd.to_datetime(train["created"])
    for f in folds:
        cut = pd.Timestamp(f)
        sub = train[modeling.known_at(train, cut)]
        out["earlier_data"].append({"trained_before": f, **compare(modeling.make("boosting", point, best_params).fit(sub[cols], sub["is_late"]))})
    out["reference_top5"] = [(str(f), round(float(v), 4)) for f, v in ref.head(5).items()]
    return out
