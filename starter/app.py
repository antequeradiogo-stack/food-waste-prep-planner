"""Streamlit skeleton. Run: streamlit run app.py"""
import pathlib
import pandas as pd
import streamlit as st
import core

DEFAULT_CSV = pathlib.Path(__file__).resolve().parent.parent / "data" / "synthetic_restaurant_daily.csv"

st.set_page_config(page_title="Prep planner (starter)", layout="wide")
st.title("Prep planner — starter template")
st.warning("Demo uses SYNTHETIC data. Suggestions are not orders; a person must approve.")

up = st.sidebar.file_uploader("CSV (date, item, sold_units)", type="csv")
df = core.load_data(up if up else DEFAULT_CSV)
target = st.sidebar.date_input("Plan for date", value=(df["date"].max() + pd.Timedelta(days=1)).date())
weeks = st.sidebar.slider("Weeks of history", 1, 8, 4)
buffer = st.sidebar.slider("Safety buffer %", 0, 30, 10)

st.subheader("History")
st.line_chart(df.pivot_table(index="date", columns="item", values="sold_units"))

rec = core.recommend(core.weekday_moving_average(df, target, weeks), buffer)
st.subheader(f"Suggested prep for {target}")
edited = st.data_editor(rec[["item", "forecast", "suggested_prep", "reason"]],
                        disabled=["item", "forecast", "reason"], key="rec")
st.markdown(core.explain(rec))

st.subheader("Human approval")
who = st.text_input("Approved by (role, not full name)")
if st.button("Approve plan", disabled=not who):
    st.success(f"Plan approved by {who}. (Demo: nothing is sent or ordered.)")
    st.download_button("Download approved plan", edited.to_csv(index=False), "approved_plan.csv")

with st.expander("Assumptions & limits", expanded=True):
    st.markdown("""
- Data is synthetic; numbers show how the tool works, not real results.
- Forecast = average of same weekday over recent weeks. Ignores weather, holidays, events, menu changes.
- History is *sold* units, which undercounts demand on days that sold out.
- Buffer is a manual setting. The chef decides; the tool never orders or discards food.
- LLM text (if enabled) only rephrases the table; check it against the numbers.
""")
