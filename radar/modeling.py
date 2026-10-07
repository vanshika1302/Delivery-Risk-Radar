"""Baselines, the two models, rolling-origin tuning and calibration."""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, OneHotEncoder, StandardScaler

from radar.data import feature_columns, feature_lists

LABELLED = ("labelled", "open_known_late")


def known_at(df: pd.DataFrame, cutoff: pd.Timestamp) -> pd.Series:
    """Tickets created before the cutoff whose label was already known at the cutoff: resolved before it,
    or already older than their threshold (so certainly late)."""
    created = pd.to_datetime(df["created"])
    resolved = pd.to_datetime(df["resolution_date"])
    age_at_cutoff = (cutoff - created).dt.total_seconds() / 86400.0
    return (created < cutoff) & df["is_late"].notna() & ((resolved < cutoff) | (age_at_cutoff > df["threshold_days"]))


def _log1p(x):
    return np.log1p(np.clip(x, 0, None))


def logistic_pipeline(point: str, C: float = 1.0) -> Pipeline:
    f = feature_lists(point)
    cols = feature_columns(point)
    log_cols = [c for c in f["log"] if c in cols]
    lin_cols = [c for c in f["linear"] if c in cols]
    pre = ColumnTransformer([
        ("log", Pipeline([("impute", SimpleImputer(strategy="median", add_indicator=True)),
                          ("log", FunctionTransformer(_log1p, feature_names_out="one-to-one")), ("scale", StandardScaler())]), log_cols),
        ("lin", Pipeline([("impute", SimpleImputer(strategy="median", add_indicator=True)), ("scale", StandardScaler())]), lin_cols),
        ("cat", OneHotEncoder(handle_unknown="ignore"), f["categorical"]),
    ])
    return Pipeline([("pre", pre), ("model", LogisticRegression(C=C, max_iter=3000))])


def boosting_pipeline(point: str, learning_rate=0.1, max_depth=None, l2=0.0, seed=0) -> Pipeline:
    """Gradient boosting on one-hot categories and raw numbers (missing values stay missing).

    Categories are one-hot encoded on purpose: scikit-learn's native categorical splits are not understood by SHAP's tree
    explainer, whose values then fail to add up to the model's output. With numeric splits only, explanations are exact.
    """
    f = feature_lists(point)
    cols = feature_columns(point)
    cat = f["categorical"]
    num = [c for c in cols if c not in cat]
    pre = ColumnTransformer([
        ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), cat),
        ("num", "passthrough", num),
    ])
    model = HistGradientBoostingClassifier(learning_rate=learning_rate, max_depth=max_depth, l2_regularization=l2, max_iter=400,
                                           early_stopping=True, n_iter_no_change=20, validation_fraction=0.1, random_state=seed)
    return Pipeline([("pre", pre), ("model", model)])


LOGISTIC_GRID = [{"C": c} for c in (0.03, 0.3, 3.0)]
BOOSTING_GRID = [{"learning_rate": lr, "max_depth": d} for lr, d in itertools.product((0.05, 0.1), (4, 8))]


def make(kind: str, point: str, params: dict):
    return logistic_pipeline(point, **params) if kind == "logistic" else boosting_pipeline(point, **params)


@dataclass
class Folds:
    """Rolling-origin folds: train on tickets created before a cutoff (labels known then), validate on the next year."""
    cutoffs: tuple = ("2016-01-01", "2017-01-01", "2018-01-01")
    folds: list = field(default_factory=list)

    def split(self, df: pd.DataFrame):
        for c in self.cutoffs:
            cut = pd.Timestamp(c)
            nxt = cut + pd.DateOffset(years=1)
            created = pd.to_datetime(df["created"])
            train = known_at(df, cut)
            val = (created >= cut) & (created < nxt) & df["is_late"].notna()
            yield c, df[train], df[val]


def tune(kind: str, point: str, df: pd.DataFrame, folds: Folds | None = None):
    """Pick hyperparameters by mean validation PR-AUC over the rolling-origin folds."""
    folds = folds or Folds()
    cols = feature_columns(point)
    grid = LOGISTIC_GRID if kind == "logistic" else BOOSTING_GRID
    scores = []
    for params in grid:
        per_fold = []
        for _, tr, va in folds.split(df):
            if len(tr) < 200 or len(va) < 50 or tr["is_late"].nunique() < 2 or va["is_late"].nunique() < 2:
                continue
            m = make(kind, point, params).fit(tr[cols], tr["is_late"])
            per_fold.append(average_precision_score(va["is_late"], m.predict_proba(va[cols])[:, 1]))
        scores.append((float(np.mean(per_fold)) if per_fold else float("-inf"), params, per_fold))
    best = max(scores, key=lambda s: s[0])
    return best[1], [{"params": p, "mean_pr_auc": s, "fold_pr_auc": pf} for s, p, pf in scores]


def fit_calibrated(kind: str, point: str, df: pd.DataFrame, params: dict, train_cutoff: str, folds: Folds | None = None):
    """Final model on every ticket whose label was known at the training cutoff.

    Probabilities are calibrated with an isotonic map learned on the last rolling fold (a model trained on earlier tickets,
    scoring the next year), so the calibration never sees the test period.
    """
    cols = feature_columns(point)
    final_train = df[known_at(df, pd.Timestamp(train_cutoff))]
    model = make(kind, point, params).fit(final_train[cols], final_train["is_late"])
    folds = folds or Folds()
    *_, (_, tr, va) = list(folds.split(df))
    calib_model = make(kind, point, params).fit(tr[cols], tr["is_late"])
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0).fit(calib_model.predict_proba(va[cols])[:, 1], va["is_late"])
    return model, iso, len(final_train), len(va)


def project_rate_baseline(train: pd.DataFrame):
    """Score = the project's late rate in the training period."""
    rate = train.groupby("project_key")["is_late"].mean()
    overall = float(train["is_late"].mean())
    return lambda d: d["project_key"].map(rate).fillna(overall).to_numpy()


def peer_history_baseline(train: pd.DataFrame):
    """Score = the late rate of the last 200 delivered tickets in the peer group (falls back to the project rate)."""
    fallback = project_rate_baseline(train)
    return lambda d: d["peer_late_rate"].fillna(pd.Series(fallback(d), index=d.index)).to_numpy()
