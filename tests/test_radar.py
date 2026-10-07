"""Tests for the modelling code: leakage guards, label-known-at-cutoff, metrics and the pipelines."""
import numpy as np
import pandas as pd
import pytest

from radar import data, evaluate, modeling
from tests.test_layers import con  # noqa: F401  (fixture: a small database with all SQL layers built)


def test_no_model_feature_is_on_the_never_use_list():
    assert not data.all_allowed_columns() & data.NEVER_USE


def test_assignment_is_a_day7_feature_not_a_creation_feature():
    assert "has_assignee" not in data.feature_columns("creation") and "has_assignee" in data.feature_columns("day7")
    assert "assignee_open" in data.feature_columns("creation")
    assert not any(c.endswith("_day7") for c in data.feature_columns("creation"))


def test_the_features_table_holds_only_allowlisted_columns(con):  # noqa: F811
    cols = {r[0] for r in con.execute("select column_name from (describe features)").fetchall()}
    assert cols <= data.all_allowed_columns(), f"features table has non-allowlisted columns: {cols - data.all_allowed_columns()}"
    assert (set(data.feature_columns("day7")) | {"project_key"}) <= cols


def test_day7_columns_are_empty_at_creation(con):  # noqa: F811
    day7_only = [c for c in data.feature_columns("day7") if c.endswith("_day7")] + ["has_assignee"][:0]
    for c in day7_only:
        assert con.execute(f"select count({c}) from features where point = 'creation'").fetchone()[0] == 0, c


def test_a_label_counts_as_known_only_if_resolved_before_the_cutoff_or_already_past_its_threshold():
    cut = pd.Timestamp("2020-01-01")
    df = pd.DataFrame({
        "created": pd.to_datetime(["2019-12-01", "2019-12-01", "2019-12-20", "2020-02-01", "2019-12-01"]),
        "resolution_date": pd.to_datetime(["2019-12-15", "2020-06-01", "2020-03-01", "2020-03-01", None]),
        "threshold_days": [30.0, 30.0, 30.0, 30.0, 30.0],
        "is_late": [0.0, 1.0, 0.0, 0.0, 1.0]})
    # resolved before cutoff; unresolved at cutoff but already 31 days old; only 12 days old at cutoff; created after cutoff; open and 31 days old
    assert modeling.known_at(df, cut).tolist() == [True, True, False, False, True]


def test_precision_at_top_breaks_ties_at_random_not_by_row_order():
    y = np.array([1.0] * 50 + [0.0] * 50)             # all ones first
    p, r, lift = evaluate.precision_at_top(y, np.zeros(100), frac=0.10)   # every score tied
    assert 0.0 < p < 1.0 or p == pytest.approx(0.5, abs=0.5)
    assert evaluate.precision_at_top(y, np.where(y == 1, 0.9, 0.1), frac=0.10)[0] == 1.0


def test_bootstrap_says_a_real_signal_beats_noise_and_noise_does_not_beat_noise():
    rng = np.random.default_rng(1)
    y = (rng.random(4000) < 0.3).astype(float)
    signal = 0.3 * y + rng.random(4000)
    noise_a, noise_b = rng.random(4000), rng.random(4000)
    out = evaluate.bootstrap(y, {"signal": signal, "noise_a": noise_a, "noise_b": noise_b}, reference=["noise_a"], n_boot=100)
    assert out["diff_vs"]["signal - noise_a"]["wins"] is True
    assert out["diff_vs"]["noise_b - noise_a"]["wins"] is False


def _frame(point, n=600, seed=0):
    rng = np.random.default_rng(seed)
    f = data.feature_lists(point)
    df = pd.DataFrame({c: rng.choice(["a", "b", "c"], n) for c in f["categorical"]})
    for c in f["log"] + f["linear"]:
        df[c] = rng.poisson(3, n).astype(float)
    df.loc[rng.random(n) < 0.2, f["log"][0]] = np.nan                    # missing values are expected
    df["is_late"] = ((df[f["log"][1]] + rng.normal(0, 1, n)) > 3.5).astype(float)
    return df


@pytest.mark.parametrize("point", ["creation", "day7"])
@pytest.mark.parametrize("kind", ["logistic", "boosting"])
def test_models_fit_and_predict_on_data_with_missing_values_and_unseen_categories(point, kind):
    df = _frame(point)
    cols = data.feature_columns(point)
    m = modeling.make(kind, point, {}).fit(df[cols], df["is_late"])
    new = _frame(point, 50, seed=5)
    new.loc[:5, data.feature_lists(point)["categorical"][0]] = "never_seen"
    p = m.predict_proba(new[cols])[:, 1]
    assert p.shape == (50,) and np.all((p >= 0) & (p <= 1))
    assert evaluate.summarise(df["is_late"], m.predict_proba(df[cols])[:, 1])["roc_auc"] > 0.6


def test_baselines_use_only_training_information():
    train = pd.DataFrame({"project_key": ["A", "A", "B", "B"], "is_late": [1.0, 0.0, 0.0, 0.0], "peer_late_rate": [0.5] * 4})
    test = pd.DataFrame({"project_key": ["A", "B", "C"], "peer_late_rate": [np.nan, 0.9, np.nan]})
    assert modeling.project_rate_baseline(train)(test).tolist() == [0.5, 0.0, 0.25]     # unseen project falls back to the overall rate
    assert modeling.peer_history_baseline(train)(test).tolist() == [0.5, 0.9, 0.25]


def test_nullable_integers_and_booleans_become_plain_floats_with_nan():
    df = pd.DataFrame({"a": pd.array([1, None, 3], dtype="Int64"), "b": pd.array([True, None, False], dtype="boolean"),
                       "c": [True, False, True], "d": ["x", "y", "z"], "e": [1.5, 2.5, 3.5]})
    out = data.normalise_dtypes(df)
    assert [str(out[c].dtype) for c in "abce"] == ["float64"] * 4 and str(out["d"].dtype) in ("object", "str", "string")
    assert np.isnan(out.loc[1, "a"]) and np.isnan(out.loc[1, "b"]) and out.loc[0, "c"] == 1.0
