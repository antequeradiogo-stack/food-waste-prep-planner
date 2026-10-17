"""Leftover Lab — entry point. Run from the repo root: streamlit run starter/app.py"""
import pathlib
import sys

import streamlit as st

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import ui  # noqa: E402

st.set_page_config(page_title=ui.APP_NAME, page_icon=":material/eco:", layout="wide")
ui.init_state()

pages = [
    st.Page("views/home.py", title="Home", icon=":material/home:", default=True),
    st.Page("views/prep.py", title="Prep plan", icon=":material/checklist:"),
    st.Page("views/stock.py", title="Stock", icon=":material/inventory_2:"),
    st.Page("views/order.py", title="Ordering", icon=":material/local_shipping:"),
    st.Page("views/weekly.py", title="Weekly order", icon=":material/calendar_month:"),
    st.Page("views/cameras.py", title="Waste cameras", icon=":material/photo_camera:"),
    st.Page("views/chat.py", title="Assistant", icon=":material/smart_toy:"),
    st.Page("views/about.py", title="About & responsible AI", icon=":material/verified_user:"),
]
nav = st.navigation(pages)

with st.sidebar:
    st.markdown(f"### :material/eco: {ui.APP_NAME}")
    st.caption("Prep less, waste less. Demo with synthetic data.")

# One-time onboarding tip (until dismissed)
if not st.session_state.onboarded:
    with st.container(border=True):
        st.markdown(f"**Welcome to {ui.APP_NAME}!** Start on **Home**, then follow the steps: "
                    "Prep plan → Stock → Ordering / Weekly order → Waste cameras. Ask the **Assistant** anything about the data. "
                    "Nothing is ever ordered or sent without a manager clicking *Approve*.")
        if st.button("Got it", key="onboard_ok", icon=":material/thumb_up:"):
            st.session_state.onboarded = True
            st.rerun()

nav.run()
