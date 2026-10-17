import json, pathlib, sys
from types import SimpleNamespace as NS
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import pandas as pd
import pytest
import assistant
import cameras
import core

DATA = pathlib.Path(__file__).resolve().parents[2] / "data"


@pytest.fixture
def data():
    sales = core.load_data(DATA / "synthetic_restaurant_daily.csv")
    return assistant.AppData(sales, pd.read_csv(DATA / "recipes.csv"), pd.read_csv(DATA / "stock.csv"),
                             pd.read_csv(DATA / "suppliers.csv"), (sales.date.max() + pd.Timedelta(days=1)).date())


@pytest.mark.parametrize("q,tool", [
    ("What should I prep tomorrow?", "get_prep_plan"),
    ("What should I order for the next 5 days?", "get_order_suggestions"),
    ("Which dishes waste the most?", "get_worst_waste_dishes"),
    ("How much did we waste last week?", "get_waste_summary"),
    ("Which weekday is busiest for burger?", "get_weekday_pattern"),
    ("Any advice to cut waste?", "get_worst_waste_dishes"),
])
def test_offline_intents_pick_right_tool_and_explain(q, tool, data):
    r = assistant.answer_offline(q, data)
    assert r["tools"][0]["name"] == tool and "Why:" in r["text"]
    assert assistant.ungrounded_numbers(r["text"], [t["result"] for t in r["tools"]], q) == []


def test_offline_numbers_match_tools(data):
    r = assistant.answer_offline("What should I order for the next 5 days?", data)
    res = r["tools"][0]["result"]
    assert res["days"] == 5 and str(res["total_est_cost_nok"]) in r["text"]
    plan = assistant.tool_prep_plan(data)
    assert plan["total_portions"] == sum(i["suggested_prep"] for i in plan["items"])


def test_unknown_question_gets_help(data):
    r = assistant.answer_offline("tell me a joke", data)
    assert r["tools"] == [] and "I can answer" in r["text"]


def test_grounding_flags_invented_numbers():
    results = [{"wasted_portions": 42, "rate": 12.5}]
    assert assistant.ungrounded_numbers("We wasted 42 portions (12.5%).", results) == []
    assert assistant.ungrounded_numbers("We wasted 42 portions, saving 900 NOK.", results) == ["900"]


class FakeLLM:
    """Mimics an OpenAI-compatible client: first asks for a tool, then answers."""
    def __init__(self, final_text):
        self.final_text, self.calls = final_text, []
        self.chat = NS(completions=NS(create=self.create))

    def create(self, **kw):
        self.calls.append(kw)
        if len(self.calls) == 1:
            call = NS(id="c1", function=NS(name="get_waste_summary", arguments=json.dumps({"days": 7})))
            return NS(choices=[NS(message=NS(content="", tool_calls=[call]))])
        return NS(choices=[NS(message=NS(content=self.final_text, tool_calls=None))])


def test_llm_uses_tools_and_is_checked(data):
    real = assistant.tool_waste_summary(data, 7)["wasted_portions"]
    ok = assistant.answer("waste?", data, client=FakeLLM(f"{real} portions wasted. Why: get_waste_summary"))
    assert ok["mode"] == "llm" and ok["tools"][0]["name"] == "get_waste_summary" and "⚠️" not in ok["text"]
    bad = assistant.answer("waste?", data, client=FakeLLM("We wasted 123456 portions."))
    assert "⚠️" in bad["text"] and "123456" in bad["text"]


def test_llm_error_falls_back_offline(data):
    broken = NS(chat=NS(completions=NS(create=lambda **kw: (_ for _ in ()).throw(ConnectionError()))))
    r = assistant.answer("What should I prep tomorrow?", data, client=broken)
    assert r["mode"] == "offline" and "LLM unavailable" in r["text"]


def test_rtsp_helper_validates_and_explains():
    img, msg = cameras.grab_rtsp_frame("file:///etc/passwd")
    assert img is None and "rtsp://" in msg
    img, msg = cameras.grab_rtsp_frame("rtsp://camera.local/stream")
    try:
        import cv2  # noqa: F401
    except ImportError:
        assert img is None and "OpenCV is not installed" in msg
