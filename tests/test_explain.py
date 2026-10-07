"""Tests for the explanation layer: SHAP must add up to the model, every feature needs a theme and wording."""
import numpy as np
import pandas as pd
import pytest
from sklearn.isotonic import IsotonicRegression

from radar import data, explain, modeling
from tests.test_radar import _frame


def _explainer(point="creation", seed=0):
    df = _frame(point, 900, seed)
    cols = data.feature_columns(point)
    pipe = modeling.boosting_pipeline(point, learning_rate=0.1, max_depth=4).fit(df[cols], df["is_late"])
    iso = IsotonicRegression(out_of_bounds="clip").fit(pipe.predict_proba(df[cols])[:, 1], df["is_late"])
    return explain.Explainer({"model": pipe, "isotonic": iso, "features": cols, "point": point}), df


@pytest.mark.parametrize("point", ["creation", "day7"])
def test_shap_values_add_up_to_the_model_output_even_with_missing_values_and_unseen_categories(point):
    ex, df = _explainer(point)
    new = _frame(point, 200, seed=9)
    new.loc[:20, data.feature_lists(point)["categorical"][0]] = "never_seen"
    c = ex.contributions(new)                                   # raises if SHAP does not add up
    assert set(c.columns) <= set(data.feature_columns(point)) and len(c) == 200
    raw, cal = ex.probabilities(new)
    assert np.allclose(explain.sigmoid(c.sum(axis=1) + ex.base), raw, atol=1e-9)


def test_the_additivity_guard_fires_when_values_do_not_add_up():
    ex, df = _explainer()
    with pytest.raises(AssertionError, match="do not add up"):
        ex.contributions(df.head(50), tolerance=-1.0)


def test_one_hot_categories_are_summed_back_to_their_feature():
    ex, df = _explainer()
    c = ex.contributions(df.head(30))
    assert "project_key" in c.columns and not any(col.startswith("project_key_") for col in c.columns)


def test_every_model_feature_has_a_theme_and_wording_that_renders_for_missing_and_ordinary_values():
    typ = explain.Typical(pd.DataFrame({"project_key": ["P", "P"], "is_late": [1.0, 0.0], **{f: [10.0, 20.0] for f in explain.Typical.FEATURES}}))
    for point in ("creation", "day7"):
        for feat in data.feature_columns(point):
            assert feat in explain.THEMES, f"{feat} has no reason theme"
            for value in (np.nan, 0.0, 3.0, 250.0, "x"):
                if feat in data.CATEGORICAL + data.DAY7_CATEGORICAL and not isinstance(value, str):
                    continue
                if feat not in data.CATEGORICAL + data.DAY7_CATEGORICAL and isinstance(value, str):
                    continue
                row = pd.Series({"project_key": "P", feat: value})
                text = explain.describe(feat, row, typ, point)
                assert isinstance(text, str) and text and "nan" not in text.lower(), (feat, value, text)


def test_reasons_are_ordered_by_size_and_signed_and_themes_sum_the_features():
    typ = explain.Typical(pd.DataFrame({"project_key": ["P", "P"], "is_late": [1.0, 0.0], **{f: [10.0, 20.0] for f in explain.Typical.FEATURES}}))
    row = pd.Series({"project_key": "P", "assignee_open": np.nan, "link_count": 0.0, "priority_rank": 0.5, "description_length": 30.0,
                     "project_open": 5.0, "reporter_prior_tickets": 0.0})
    contrib = pd.Series({"assignee_open": 0.5, "link_count": -0.1, "priority_rank": 0.02, "description_length": 0.3, "project_open": -0.05, "reporter_prior_tickets": 0.2})
    out = explain.reasons(row, contrib, p_raw=0.5, typ=typ, point="creation", k=3)
    assert [r["feature"] for r in out["reasons"]] == ["assignee_open", "description_length", "reporter_prior_tickets"]
    assert out["reasons"][0]["points"] == pytest.approx(0.5 * 25, abs=0.06)            # 0.5 log-odds at p=0.5 is 12.5 points
    assert out["reasons"][0]["text"] == "Not assigned when filed"
    assert out["themes"]["Ownership"] == pytest.approx((0.5 + 0.2) * 25, abs=0.1) and out["themes"]["Scope"] == pytest.approx((-0.1 + 0.02 + 0.3) * 25, abs=0.1)


def test_displayed_probabilities_never_claim_certainty():
    shown = explain.display_probability(np.array([0.0, 0.03, 0.4, 0.97, 1.0]))
    assert shown.tolist() == [0.05, 0.05, 0.4, 0.95, 0.95]
