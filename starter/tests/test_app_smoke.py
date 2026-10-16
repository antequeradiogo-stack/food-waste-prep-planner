import pathlib
from streamlit.testing.v1 import AppTest

APP = str(pathlib.Path(__file__).resolve().parents[1] / "app.py")


def run_app():
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception
    return at


def test_prep_plan_requires_approval():
    at = run_app()
    assert at.button(key="approve").disabled  # can't approve without a role
    at.text_input(key="approver").input("head chef").run()
    at.button(key="approve").click().run()
    assert any("approved" in s.value for s in at.success)


def test_plate_waste_confirm_flow(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    at = run_app()
    at.selectbox(key="dish").select("burger").run()
    at.selectbox(key="sample").select("half_left").run()
    assert at.select_slider(key="confirmed_bucket").value == "half"   # heuristic pre-fills
    assert at.session_state.waste_log == []                            # nothing logged before confirm
    at.select_slider(key="confirmed_bucket").set_value("most").run()   # staff correct it
    at.button(key="confirm").click().run()
    log = at.session_state.waste_log
    assert len(log) == 4 and {r["confirmed_bucket"] for r in log} == {"most"}
    assert {r["estimated_bucket"] for r in log} == {"half"}
    assert abs(sum(r["grams_wasted"] for r in log) - 0.75 * (150 + 80 + 25 + 40)) < 0.5  # per-ingredient rounding
