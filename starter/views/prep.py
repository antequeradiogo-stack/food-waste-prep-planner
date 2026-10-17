"""Today's prep plan: forecast + editable suggestions + manager approval."""
import pathlib
import sys

import pandas as pd
import streamlit as st

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import core  # noqa: E402
import ui  # noqa: E402

ui.page_header(":material/checklist: Prep plan",
               "Suggests how many portions of each dish to prep, based on the same weekday in recent weeks.",
               "Adjust the settings, edit any number in *Suggested prep*, then type your role and click **Approve plan**.")

with st.expander("Use your own sales CSV (optional)", icon=":material/upload_file:"):
    up = st.file_uploader("CSV with columns date, item, sold_units", type="csv")
    if up:
        st.session_state.uploaded_sales = core.load_data(up)

df = ui.sales()
c1, c2, c3 = st.columns(3)
target = c1.date_input("Plan for date", value=ui.plan_date())
weeks = c2.slider("Weeks of history", 1, 8, 4, help="How many past weeks of the same weekday to average.")
buffer = c3.slider("Safety buffer %", 0, 30, 10, help="Extra on top of the forecast. Lower = less waste, more risk of selling out.")

rec = core.recommend(core.weekday_moving_average(df, target, weeks), buffer)
st.subheader(f"Suggested prep for {target}")
edited = st.data_editor(rec[["item", "forecast", "suggested_prep", "reason"]], hide_index=True,
                        disabled=["item", "forecast", "reason"], key="rec", width="stretch")
with st.expander("Explanation", icon=":material/lightbulb:", expanded=False):
    st.markdown(core.explain(rec))

with st.expander("Sales history", icon=":material/show_chart:"):
    st.line_chart(df.pivot_table(index="date", columns="item", values="sold_units"))

st.subheader("Manager approval")
who = st.text_input("Approved by (role, not full name)", key="approver", placeholder="e.g. head chef")
if st.button("Approve plan", disabled=not who, key="approve", type="primary", icon=":material/check:"):
    st.session_state.approved_plan = edited
    st.success(f"Plan approved by {who}. (Demo: nothing is sent or ordered.)")
    st.download_button("Download approved plan", edited.to_csv(index=False), "approved_plan.csv")

with st.expander("Assumptions & limits", expanded=True, icon=":material/info:"):
    st.markdown("""
- Data is synthetic; numbers show how the tool works, not real results.
- Forecast = average of same weekday over recent weeks. Ignores weather, holidays, events, menu changes.
- History is *sold* units, which undercounts demand on days that sold out.
- Buffer is a manual setting. The chef decides; the tool never orders or discards food.
- LLM text (if enabled) only rephrases the table; check it against the numbers.
""")
