"""Weekly order: one test per step, plus approve/save/history, assistant intents and an AppTest smoke test."""
import json
import pathlib
import re
import sys
from datetime import date, datetime

import pandas as pd
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import assistant  # noqa: E402
import core  # noqa: E402
import stock as stock_mod  # noqa: E402
import weekly  # noqa: E402

DATA = pathlib.Path(__file__).resolve().parents[2] / "data"


@pytest.fixture(scope="module")
def sales():
    return core.load_data(DATA / "synthetic_restaurant_daily.csv")


@pytest.fixture(scope="module")
def recipes():
    return pd.read_csv(DATA / "recipes.csv")


@pytest.fixture(scope="module")
def suppliers():
    return pd.read_csv(DATA / "suppliers.csv")


@pytest.fixture(scope="module")
def batches():
    return stock_mod.load_batches(DATA / "stock_batches.csv")


def tiny_sales(start="2026-06-01", weeks=4, sold=10, wasted=0):
    rows = []
    for i in range(7 * weeks):
        d = pd.Timestamp(start) + pd.Timedelta(days=i)
        rows.append({"date": d, "item": "burger", "category": "main", "sold_units": sold,
                     "prepared_units": sold + wasted, "wasted_units": wasted})
    return pd.DataFrame(rows)


# 1. forecast window
def test_week_starts_next_monday_after_last_sale(sales):
    ws = weekly.next_week_start(sales)
    assert pd.Timestamp(ws).weekday() == 0 and ws > sales["date"].max().date()
    assert (pd.Timestamp(ws) - sales["date"].max()).days <= 7
    fc = weekly.forecast_week(sales, ws)
    assert sorted(fc["date"].unique()) == weekly.week_dates(ws)
    assert set(fc["item"]) == set(sales["item"])


def test_next_week_start_from_midweek():
    s = tiny_sales(start="2026-06-03", weeks=1)            # Wed..Tue
    assert weekly.next_week_start(s) == date(2026, 6, 15)


def test_forecast_reuses_weekday_moving_average(sales):
    ws = weekly.next_week_start(sales)
    fc = weekly.forecast_week(sales, ws)
    ma = core.weekday_moving_average(sales, ws, 4).set_index("item")["forecast"]
    mon = fc[fc["date"] == ws].set_index("item")["forecast"]
    assert (mon - ma).abs().max() < 0.06


# 2. events
def test_event_covers_and_pct_scale_only_that_day():
    s = tiny_sales()
    ws = weekly.next_week_start(s)
    fc = weekly.forecast_week(s, ws)
    fri = weekly.week_dates(ws)[4]
    out = weekly.apply_events(fc, [{"date": fri, "extra_covers": 5}], s)
    assert out.loc[out["date"] == fri, "forecast_adj"].iloc[0] == 15.0          # 10 mains + 5 covers
    assert (out.loc[out["date"] != fri, "forecast_adj"] == 10.0).all()
    out = weekly.apply_events(fc, [{"date": fri, "extra_pct": 20}], s)
    assert out.loc[out["date"] == fri, "forecast_adj"].iloc[0] == 12.0


def test_event_flows_into_order(sales, recipes, suppliers, batches):
    base = weekly.build_week_order(sales, recipes, suppliers, batches=batches)
    fri = base["dates"][4]
    ev = weekly.build_week_order(sales, recipes, suppliers, batches=batches,
                                 events=[{"date": fri, "extra_covers": 40}])
    assert ev["plan"]["forecast_adj"].sum() > base["plan"]["forecast_adj"].sum()
    assert ev["lines"]["packs"].sum() >= base["lines"]["packs"].sum()


# 3. waste adjustment & cap
def test_waste_rate_and_cap():
    s = tiny_sales(sold=80, wasted=20)                                           # 20% waste
    ws = weekly.next_week_start(s)
    rates = weekly.waste_rates(s, ws)
    assert rates.set_index("item")["waste_rate_pct"]["burger"] == 20.0
    fc = weekly.apply_events(weekly.forecast_week(s, ws), [], s)
    p = weekly.plan_dishes(fc, rates, buffer_pct=30, max_cut_pct=10)
    assert (p["waste_cut_pct"] == 10.0).all()                                    # capped
    assert p["planned"].iloc[0] == round(80 * 1.3 * 0.9, 1)
    p = weekly.plan_dishes(fc, rates, buffer_pct=10, max_cut_pct=30)
    assert p["planned"].iloc[0] == 80.0                                          # never below forecast
    p = weekly.plan_dishes(fc, rates, buffer_pct=10, max_cut_pct=0)
    assert p["planned"].iloc[0] == 88.0                                          # cap 0 = no trim


# 4/5. stock netting with expiry
def test_net_stock_ignores_stock_that_expires_before_use():
    dates = weekly.week_dates(date(2026, 7, 6))
    needs = pd.DataFrame({"ingredient": ["bun"] * 7, "date": dates, "need_g": [100.0] * 7})
    lots = pd.DataFrame({"ingredient": ["bun", "bun"], "grams": [500.0, 150.0],
                         "expiry_date": pd.to_datetime(["2026-07-08", "2026-07-20"])})
    daily, lost = weekly.net_stock(needs, lots, dates)
    # Mon+Tue from the first lot (expires Wed), 300 g of it lost; 150 g of the second lot Wed + part Thu
    assert daily["from_stock_g"].sum() == 350.0
    assert lost.iloc[0]["grams"] == 300.0 and lost.iloc[0]["expiry_date"] == date(2026, 7, 8)
    assert daily.set_index("date")["short_g"][dates[3]] == 50.0


def test_stock_lots_from_batches_converts_packs(batches, suppliers):
    lots = weekly.stock_lots(batches, None, suppliers)
    bun = batches[batches["ingredient"] == "bun"]["quantity"].sum() * 1600
    assert lots[lots["ingredient"] == "bun"]["grams"].sum() == bun


# 6. packs + delivery split
def test_pack_rounding():
    assert weekly.packs_for(0, 1000) == 0 and weekly.packs_for(1, 1000) == 1
    assert weekly.packs_for(1000, 1000) == 1 and weekly.packs_for(1000.4, 1000) == 2


def test_delivery_split_fresh_twice_dry_weekly(sales, recipes, suppliers, batches):
    assert {"storage", "delivery_days"} <= set(suppliers.columns)
    r = weekly.build_week_order(sales, recipes, suppliers, batches=batches)
    lines = r["lines"]
    fresh = lines[lines["storage"] == "fresh"]
    long_life = lines[lines["storage"] != "fresh"]
    assert set(fresh["delivery_day"]) <= {"Mon", "Thu"} and (fresh["delivery_day"] == "Thu").any()
    assert set(long_life["delivery_day"]) == {"Mon"}
    assert (lines["order_g"] == lines["packs"] * lines["pack_size_g"]).all()
    for x in lines.itertuples():
        lead = int(suppliers.set_index("ingredient").loc[x.ingredient, "lead_time_days"])
        assert (pd.Timestamp(x.delivery_date) - pd.Timestamp(x.order_by)).days == lead


def test_order_covers_need(sales, recipes, suppliers, batches):
    r = weekly.build_week_order(sales, recipes, suppliers, batches=batches)
    for x in r["summary"].itertuples():
        assert x.from_stock_g + x.packs * x.facts["pack_size_g"] >= x.need_g - 1


# reasons
def test_reasons_contain_only_computed_numbers(sales, recipes, suppliers, batches):
    r = weekly.build_week_order(sales, recipes, suppliers, batches=batches,
                                events=[{"date": weekly.next_week_start(sales), "extra_pct": 15}])
    assert len(r["summary"])
    for x in r["summary"].itertuples():
        assert weekly.reason_numbers_grounded(x.reason, x.facts) == [], x.reason
        assert x.reason.startswith(x.ingredient.replace("_", " "))
    assert any("expire" in x for x in r["summary"]["reason"])


# 7. approve / save / history
def test_approve_save_history_and_actuals(tmp_path, sales, recipes, suppliers, batches):
    past = (pd.Timestamp(weekly.next_week_start(sales)) - pd.Timedelta(weeks=1)).date()
    r = weekly.build_week_order(sales, recipes, suppliers, past, batches=batches)
    assert weekly.list_orders(tmp_path) == []                                    # nothing ordered before approval
    with pytest.raises(ValueError):
        weekly.save_order(r, r["lines"], "  ", tmp_path)
    oid = weekly.save_order(r, r["lines"], "restaurant manager", tmp_path, now=datetime(2026, 7, 6, 9, 0))
    assert (tmp_path / f"order_{oid}.csv").exists() and (tmp_path / f"order_{oid}.json").exists()
    hist = weekly.list_orders(tmp_path)
    assert len(hist) == 1 and hist[0]["approved_by"] == "restaurant manager"
    assert hist[0]["packs"] == int(r["lines"]["packs"].sum())
    fva = weekly.forecast_vs_actual(hist[0], sales)
    assert fva.attrs["days_with_actuals"] == 7 and fva["actual"].notna().all()
    nxt = weekly.build_week_order(sales, recipes, suppliers, batches=batches)
    weekly.save_order(nxt, nxt["lines"], "chef", tmp_path, now=datetime(2026, 7, 6, 10, 0))
    fva2 = weekly.forecast_vs_actual(weekly.list_orders(tmp_path)[0], sales)
    assert fva2.attrs["days_with_actuals"] == 0 and fva2["actual"].isna().all()


def test_risks(sales, recipes, suppliers, batches):
    r = weekly.build_week_order(sales, recipes, suppliers, batches=batches)
    k = weekly.risks(r, sales)
    assert set(k) >= {"stockout_before_delivery", "expiring_unused", "recent_sellouts", "rising_waste"}
    assert k["expiring_unused"]


# assistant
@pytest.fixture
def data(sales, recipes, suppliers, batches):
    return assistant.AppData(sales, recipes, pd.read_csv(DATA / "stock.csv"), suppliers,
                             (sales.date.max() + pd.Timedelta(days=1)).date(), batches=batches)


@pytest.mark.parametrize("q,tools", [
    ("Plan next week's order", ["get_weekly_order", "get_week_risks"]),
    ("Big event Friday, +40 covers", ["get_weekly_order", "get_week_risks"]),
    ("What are the risks this week?", ["get_week_risks"]),
    ("Saturday wedding, 25% more", ["get_weekly_order", "get_week_risks"]),
])
def test_assistant_manager_intents_grounded(q, tools, data):
    r = assistant.answer_offline(q, data)
    assert [t["name"] for t in r["tools"]] == tools
    assert "Why:" in r["text"] and "approve" in r["text"].lower()
    assert assistant.ungrounded_numbers(r["text"], [t["result"] for t in r["tools"]], q) == []


def test_assistant_plan_reads_like_manager(data):
    t = assistant.answer_offline("Plan next week's order", data)["text"]
    for part in ("Summary", "Draft order", "Risks", "approve or edit"):
        assert part in t


def test_assistant_event_creates_draft_event(data):
    r = assistant.answer_offline("Big event Friday, +40 covers", data)
    ev = r["draft_events"][0]
    assert ev["extra_covers"] == 40 and pd.Timestamp(ev["date"]).weekday() == 4
    w = r["tools"][0]["result"]
    assert w["forecast_portions_with_events"] > w["forecast_portions"] and "DRAFT" in w["status"]


def test_old_intents_unchanged(data):
    assert assistant.answer_offline("How much did we waste last week?", data)["tools"][0]["name"] == "get_waste_summary"
    assert assistant.answer_offline("What should I order for the next 3 days?", data)["tools"][0]["name"] == "get_order_suggestions"


def test_tool_specs_include_weekly_tools():
    names = {t["function"]["name"] for t in assistant._tool_specs()}
    assert {"get_weekly_order", "get_week_risks"} <= names


def test_llm_path_can_call_weekly_tool(data):
    from types import SimpleNamespace as NS

    class Client:
        def __init__(self):
            self.n = 0
            self.chat = NS(completions=NS(create=self.create))

        def create(self, **kw):
            self.n += 1
            if self.n == 1:
                call = NS(id="c1", function=NS(name="get_weekly_order", arguments=json.dumps({"event_day": "Fri", "extra_covers": 40})))
                return NS(choices=[NS(message=NS(content="", tool_calls=[call]))])
            res = json.loads(kw["messages"][-1]["content"])
            return NS(choices=[NS(message=NS(content=f"Draft: {res['total_packs']} packs. Approve or edit. Why: tool.", tool_calls=None))])

    r = assistant.answer_llm("big event friday +40 covers", data, Client(), "m")
    assert r["mode"] == "llm" and r["tools"][0]["name"] == "get_weekly_order" and "Could not verify" not in r["text"]


# AppTest smoke test of the new page
def test_weekly_page_approve_flow(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv("LEFTOVER_ORDERS_DIR", str(tmp_path))
    at = AppTest.from_file(str(pathlib.Path(__file__).resolve().parents[1] / "app.py"), default_timeout=60).run()
    at.switch_page("views/weekly.py").run()
    assert not at.exception, at.exception
    assert any("Packs to order" in m.label for m in at.metric)
    assert at.button(key="wk_approve").disabled
    at.number_input(key="ev_covers").set_value(40).run()
    at.button(key="ev_add").click().run()
    assert len(at.session_state.weekly_events) == 1
    at.text_input(key="wk_approver").input("restaurant manager").run()
    at.button(key="wk_approve").click().run()
    assert not at.exception, at.exception
    assert any("Nothing was sent" in s.value for s in at.success)
    assert len(list(tmp_path.glob("order_*.json"))) == 1


def test_assistant_event_button_prefills_weekly_page(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv("LEFTOVER_ORDERS_DIR", str(tmp_path))
    at = AppTest.from_file(str(pathlib.Path(__file__).resolve().parents[1] / "app.py"), default_timeout=60).run()
    at.switch_page("views/chat.py").run()
    at.button(key="mgr_1").click().run()
    assert not at.exception, at.exception
    assert at.session_state.weekly_events[0]["extra_covers"] == 40
    at.switch_page("views/weekly.py").run()
    assert not at.exception, at.exception
    assert list(tmp_path.glob("order_*")) == []                                   # assistant never approves
