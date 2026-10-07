"""Train and evaluate the late-ticket models for both prediction points.

For each point (creation, day 7): fit two baselines (project late rate; recent peer-group late rate), tune and fit a logistic
regression and a gradient boosting model with rolling-origin validation, calibrate probabilities on the last validation year,
then score the untouched test period (tickets created after the training cutoff). Writes metrics, calibration tables, per-project
results and paired bootstrap comparisons to docs/model_results.json; test predictions and fitted models go to data/processed/.

Run from the repo root:  python -m radar.train                      (full)
                         python -m radar.train --projects SPARK CASSANDRA --quick   (smoke run)
"""
from __future__ import annotations

import argparse
import json
import time
import tomllib
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from radar import data, evaluate, modeling

ROOT = Path(__file__).resolve().parent.parent
PARAMS = ROOT / "config" / "params.toml"
BASELINES = ["baseline_project_rate", "baseline_peer_history"]
MODELS = ["logistic", "boosting"]


def run_point(point: str, db, params: dict, projects=None, n_boot=300, out_dir: Path = ROOT / "data" / "processed", log=print) -> tuple[dict, pd.DataFrame]:
    cutoff = pd.Timestamp(params["split"]["train_cutoff"])
    df = data.load(point, db, projects)
    df["created"] = pd.to_datetime(df["created"])
    df["resolution_date"] = pd.to_datetime(df["resolution_date"])
    cols = data.feature_columns(point)
    train_all = df[modeling.known_at(df, cutoff)]
    test = df[(df["split"] == "test") & df["is_late"].notna()].copy()
    log(f"[{point}] features {len(cols)}; train {len(train_all):,} (label known at {cutoff.date()}), test {len(test):,}; late rate train {train_all['is_late'].mean():.1%}, test {test['is_late'].mean():.1%}")

    scores = {"baseline_project_rate": modeling.project_rate_baseline(train_all)(test),
              "baseline_peer_history": modeling.peer_history_baseline(train_all)(test)}
    result = {"n_train": int(len(train_all)), "n_test": int(len(test)), "features": cols, "tuning": {}, "best_params": {}, "models": {}}
    raw, models = {}, {}
    for kind in MODELS:
        t0 = time.time()
        best, grid = modeling.tune(kind, point, df)
        model, iso, n_final, n_calib = modeling.fit_calibrated(kind, point, df, best, params["split"]["train_cutoff"])
        raw[kind] = model.predict_proba(test[cols])[:, 1]
        scores[kind] = iso.predict(raw[kind])
        models[kind] = {"model": model, "isotonic": iso, "features": cols, "params": best, "point": point}
        result["best_params"][kind], result["tuning"][kind] = best, grid
        result["n_calibration"] = int(n_calib)
        log(f"[{point}] {kind}: best {best}  ({time.time() - t0:.0f}s)")

    y = test["is_late"].to_numpy()
    for name, s in scores.items():
        result["models"][name] = evaluate.summarise(y, s)
    for kind in MODELS:
        result["models"][kind]["uncalibrated"] = {k: v for k, v in evaluate.summarise(y, raw[kind]).items() if k in ("brier", "log_loss")}
        result["models"][kind]["calibration_table"] = evaluate.calibration_table(y, scores[kind])
        result["models"][kind]["per_project"] = evaluate.per_project(y, scores[kind], test["project_key"])
    result["bootstrap"] = evaluate.bootstrap(y, scores, reference=BASELINES + ["logistic"], n_boot=n_boot)

    sub = test[test["is_late_delivered_only"].notna()]  # robustness: delivered tickets only (no open tickets in the label)
    if sub["is_late_delivered_only"].nunique() == 2:
        keep = test.index.get_indexer(sub.index)
        result["robustness_delivered_only"] = {name: evaluate.summarise(sub["is_late_delivered_only"].to_numpy(), s[keep]) for name, s in scores.items()}

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "models").mkdir(exist_ok=True)
    for kind, bundle in models.items():
        joblib.dump(bundle, out_dir / "models" / f"{point}_{kind}.joblib")
    preds = test[["issue_key", "point", "project_key", "created", "is_late"]].copy()
    for name, s in scores.items():
        preds[name] = s
    return result, preds


def run(db=data.DEFAULT_DB, projects=None, points=("creation", "day7"), n_boot=300, out_json=ROOT / "docs" / "model_results.json", out_dir=ROOT / "data" / "processed", quick=False):
    params = tomllib.loads(PARAMS.read_text())
    results, all_preds = {"train_cutoff": params["split"]["train_cutoff"], "test_window": [params["split"]["test_start"], params["split"]["test_end"]],
                          "projects": list(projects or params["scope"]["projects"]), "points": {}}, []
    for point in points:
        r, p = run_point(point, db, params, projects, 40 if quick else n_boot, Path(out_dir))
        results["points"][point] = r
        all_preds.append(p)
    Path(out_json).parent.mkdir(parents=True, exist_ok=True)
    Path(out_json).write_text(json.dumps(results, indent=2))
    pd.concat(all_preds).to_parquet(Path(out_dir) / "predictions_test.parquet", index=False)
    return results


def summary(results: dict) -> str:
    lines = []
    for point, r in results["points"].items():
        lines.append(f"\n{point}: train {r['n_train']:,}  test {r['n_test']:,}  test late rate {r['models']['logistic']['late_rate']:.1%}")
        lines.append(f"  {'model':<24}{'PR-AUC':>8}{'[95% CI]':>18}{'ROC':>7}{'Brier':>8}{'P@10%':>8}{'lift':>6}")
        for name in BASELINES + MODELS:
            m = r["models"][name]
            lo, hi = r["bootstrap"]["pr_auc_ci"][name]
            lines.append(f"  {name:<24}{m['pr_auc']:>8.3f}  [{lo:.3f}, {hi:.3f}]{m['roc_auc']:>7.3f}{m['brier']:>8.3f}{m['precision_at_top10']:>8.3f}{m['lift_at_top10']:>6.2f}")
        for k, d in r["bootstrap"]["diff_vs"].items():
            if k.startswith("boosting"):
                lines.append(f"  {k:<40} {d['mean']:+.3f}  [{d['ci95'][0]:+.3f}, {d['ci95'][1]:+.3f}]  {'beats' if d['wins'] else 'does not clearly beat'}")
    return "\n".join(lines)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--db", default=str(data.DEFAULT_DB))
    p.add_argument("--projects", nargs="*", default=None)
    p.add_argument("--points", nargs="*", default=["creation", "day7"])
    p.add_argument("--quick", action="store_true", help="fewer bootstrap resamples (smoke run)")
    p.add_argument("--out-json", default=str(ROOT / "docs" / "model_results.json"))
    p.add_argument("--out-dir", default=str(ROOT / "data" / "processed"))
    a = p.parse_args(argv)
    res = run(a.db, a.projects, tuple(a.points), out_json=a.out_json, out_dir=a.out_dir, quick=a.quick)
    print(summary(res))


if __name__ == "__main__":
    main()
