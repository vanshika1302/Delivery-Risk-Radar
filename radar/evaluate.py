"""Metrics, calibration tables, per-project breakdowns and paired bootstrap comparisons."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, roc_auc_score


def precision_at_top(y, score, frac=0.10, seed=0):
    """Precision, recall and lift among the riskiest `frac` of tickets. Ties are broken at random, not by row order."""
    y, score = np.asarray(y, dtype=float), np.asarray(score, dtype=float)
    rng = np.random.default_rng(seed)
    order = np.lexsort((rng.random(len(y)), -score))
    k = max(int(np.ceil(frac * len(y))), 1)
    top = y[order[:k]]
    base = y.mean()
    return float(top.mean()), float(top.sum() / max(y.sum(), 1)), float(top.mean() / base) if base > 0 else float("nan")


def summarise(y, score) -> dict:
    y, score = np.asarray(y, dtype=float), np.asarray(score, dtype=float)
    p, r, lift = precision_at_top(y, score)
    clipped = np.clip(score, 1e-6, 1 - 1e-6)
    return {"n": int(len(y)), "late_rate": float(y.mean()), "pr_auc": float(average_precision_score(y, score)),
            "roc_auc": float(roc_auc_score(y, score)), "brier": float(brier_score_loss(y, clipped)),
            "log_loss": float(log_loss(y, clipped)), "precision_at_top10": p, "recall_at_top10": r, "lift_at_top10": lift}


def calibration_table(y, prob, bins=10) -> list[dict]:
    d = pd.DataFrame({"y": np.asarray(y, dtype=float), "p": np.asarray(prob, dtype=float)})
    d["bin"] = pd.qcut(d["p"].rank(method="first"), bins, labels=False)
    g = d.groupby("bin").agg(predicted=("p", "mean"), observed=("y", "mean"), n=("y", "size")).reset_index()
    return g.round(4).to_dict("records")


def per_project(y, score, projects) -> dict:
    d = pd.DataFrame({"y": np.asarray(y, dtype=float), "s": np.asarray(score, dtype=float), "p": np.asarray(projects)})
    out = {}
    for proj, g in d.groupby("p"):
        if g["y"].nunique() < 2:
            continue
        pr, _, lift = precision_at_top(g["y"], g["s"])
        out[proj] = {"n": int(len(g)), "late_rate": float(g["y"].mean()), "pr_auc": float(average_precision_score(g["y"], g["s"])),
                     "precision_at_top10": pr, "lift_at_top10": lift}
    return out


def bootstrap(y, scores: dict, reference: list[str], n_boot=300, seed=0) -> dict:
    """PR-AUC with 95% intervals, and paired differences between each model and each reference model, on shared resamples."""
    y = np.asarray(y, dtype=float)
    scores = {k: np.asarray(v, dtype=float) for k, v in scores.items()}
    rng = np.random.default_rng(seed)
    n = len(y)
    draws = {k: [] for k in scores}
    for _ in range(n_boot):
        idx = rng.integers(0, n, n)
        if y[idx].sum() in (0, n):
            continue
        for k, s in scores.items():
            draws[k].append(average_precision_score(y[idx], s[idx]))
    draws = {k: np.array(v) for k, v in draws.items()}
    ci = lambda a: [float(np.percentile(a, 2.5)), float(np.percentile(a, 97.5))]
    out = {"pr_auc_ci": {k: ci(v) for k, v in draws.items()}, "diff_vs": {}}
    for k in scores:
        for ref in reference:
            if k == ref or ref not in draws:
                continue
            d = draws[k] - draws[ref]
            out["diff_vs"][f"{k} - {ref}"] = {"mean": float(d.mean()), "ci95": ci(d), "wins": bool(np.percentile(d, 2.5) > 0)}
    return out
