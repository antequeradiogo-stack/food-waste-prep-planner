import pathlib
from streamlit.testing.v1 import AppTest

APP = str(pathlib.Path(__file__).resolve().parents[1] / "app.py")


def test_app_runs_and_requires_approval():
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception
    assert at.button[0].disabled  # can't approve without a name/role
    at.text_input[0].input("head chef").run()
    at.button[0].click().run()
    assert "approved" in at.success[0].value
