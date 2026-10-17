"""Streamlit AppTest checks: every page loads, approvals need a role, plate confirm flow, assistant chips."""
import pathlib

import pytest
from streamlit.testing.v1 import AppTest

STARTER = pathlib.Path(__file__).resolve().parents[1]
APP = str(STARTER / "app.py")
PAGES = ["views/home.py", "views/prep.py", "views/order.py", "views/cameras.py", "views/chat.py", "views/about.py"]


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)


def open_page(page=None):
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception, at.exception
    if page:
        at.switch_page(page).run()
        assert not at.exception, at.exception
    return at


@pytest.mark.parametrize("page", PAGES)
def test_each_page_loads(page):
    at = open_page(page)
    assert any("SYNTHETIC DEMO DATA" in w.value for w in at.warning)


def test_onboarding_tip_dismisses():
    at = open_page()
    assert any("Welcome to Leftover Lab" in m.value for m in at.markdown)
    at.button(key="onboard_ok").click().run()
    assert at.session_state.onboarded
    assert not any("Welcome to Leftover Lab" in m.value for m in at.markdown)


def test_prep_plan_requires_approval():
    at = open_page("views/prep.py")
    assert at.button(key="approve").disabled  # can't approve without a role
    at.text_input(key="approver").input("head chef").run()
    at.button(key="approve").click().run()
    assert any("approved" in s.value for s in at.success)


def test_order_requires_approval_and_sends_nothing():
    at = open_page("views/order.py")
    assert at.button(key="order_approve").disabled
    at.text_input(key="order_approver").input("kitchen manager").run()
    at.button(key="order_approve").click().run()
    assert any("Nothing was sent" in s.value for s in at.success)


def test_plate_waste_confirm_flow():
    at = open_page("views/cameras.py")
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


def test_kitchen_bin_needs_grams():
    at = open_page("views/cameras.py")
    assert at.button(key="bin_confirm").disabled
    at.number_input(key="bin_grams").set_value(350).run()
    at.button(key="bin_confirm").click().run()
    log = at.session_state.waste_log
    assert len(log) == 1 and log[0]["stream"] == "kitchen_bin" and log[0]["grams_wasted"] == 350


def test_assistant_chip_answers_from_data():
    at = open_page("views/chat.py")
    at.button(key="chip_1").click().run()                 # "What should I order for the next 3 days?"
    chat = at.session_state.chat
    assert chat[0]["role"] == "user" and chat[1]["role"] == "assistant"
    assert "Why:" in chat[1]["content"] and chat[1]["tools"][0]["name"] == "get_order_suggestions"


def test_assistant_typed_question():
    at = open_page("views/chat.py")
    at.chat_input[0].set_value("Which weekday is busiest?").run()
    assert "Busiest" in at.session_state.chat[-1]["content"]
