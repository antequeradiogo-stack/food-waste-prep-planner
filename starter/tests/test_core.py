import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import pandas as pd
import pytest
import core

CSV = pathlib.Path(__file__).resolve().parents[2] / "data" / "synthetic_restaurant_daily.csv"


def test_load_synthetic_csv():
    df = core.load_data(CSV)
    assert len(df) > 0 and (df["data_source"] == "SYNTHETIC").all()


def test_weekday_average_uses_same_weekday_only():
    dates = pd.date_range("2026-01-05", periods=21)  # 3 weeks, Mon start
    df = pd.DataFrame({"date": dates, "item": "x", "sold_units": [10 if d.weekday() == 0 else 99 for d in dates]})
    f = core.weekday_moving_average(df, "2026-01-26", weeks=4)  # a Monday
    assert f.loc[0, "forecast"] == 10 and f.loc[0, "n_obs"] == 3


def test_recommend_buffer_and_low_data_flag():
    r = core.recommend(pd.DataFrame({"item": ["a", "b"], "forecast": [10.0, 5.0], "n_obs": [4, 1]}), 10)
    assert r["suggested_prep"].tolist() == [11, 6]
    assert "LOW DATA" in r.loc[1, "reason"]


def test_explain_falls_back_offline(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    r = core.recommend(pd.DataFrame({"item": ["a"], "forecast": [10.0], "n_obs": [4]}))
    assert "rule-based" in core.explain(r)


def test_missing_columns_rejected(tmp_path):
    p = tmp_path / "bad.csv"; p.write_text("date,foo\n2026-01-01,1\n")
    with pytest.raises(ValueError):
        core.load_data(p)
