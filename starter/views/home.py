"""Home: what the app does, today's cards, start-here links."""
import pathlib
import sys

import pandas as pd
import streamlit as st

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import assistant  # noqa: E402
import stock as stock_mod  # noqa: E402
import ui  # noqa: E402
import weekly  # noqa: E402

ui.page_header(f":material/eco: {ui.APP_NAME}",
               "Helps a restaurant kitchen prep the right amount, order only what's missing, and see what gets thrown away.",
               "Check today's cards, then use the buttons below to go step by step.")

data = ui.app_data()
plan = assistant.tool_prep_plan(data)
waste = assistant.tool_waste_summary(data, days=7)

st.subheader(f"At a glance — plan for {plan['date']}")
c1, c2, c5, c3, c4 = st.columns(5)
with c1.container(border=True):
    st.metric("Forecast portions", plan["total_portions"], help="Sum of suggested prep for all dishes (incl. 10% buffer).")
with c2.container(border=True):
    st.markdown("**Top 3 to prep**")
    for i in plan["items"][:3]:
        st.markdown(f"- {i['item']}: **{i['suggested_prep']}**")
with c5.container(border=True):
    exp = stock_mod.expiring(ui.batches(), ui.plan_date(), 2)
    st.metric("Expiring ≤ 2 days", len(exp), help="Stock batches expiring within 2 days (synthetic or confirmed this session). See Stock → Expiry.")
    if len(exp):
        st.caption("Use first: " + ", ".join(exp["ingredient"].drop_duplicates().head(4)))
with c3.container(border=True):
    logged = ui.waste_log_df()["grams_wasted"].sum()
    st.metric("Waste logged", f"{logged:,.0f} g", help="This session: confirmed plate/bin entries on the Waste cameras page.")
with c4.container(border=True):
    now, before = waste["wasted_portions"], waste["previous_period_wasted_portions"]
    delta = None if before == 0 else f"{100 * (now - before) / before:+.0f}% vs prior 7 days"
    st.metric("Wasted, last 7 days", now, delta=delta, delta_color="inverse",
              help="Wasted portions in the last 7 days, estimated from the synthetic history (prepared − sold).")

with st.container(border=True):
    st.markdown(f"**:material/calendar_month: Weekly order** — plan next week's stock (from {weekly.next_week_start(data.sales)}): "
                "forecast per dish per day, buffer trimmed for dishes we keep wasting, stock that expires first not counted, "
                "packs split into fresh (twice a week) and dry (weekly) deliveries. Nothing is ordered until you approve.")
    st.page_link("views/weekly.py", label="Open Weekly order", icon=":material/arrow_forward:")

st.subheader("Waste trend (synthetic history)")
daily = data.sales.groupby("date")["wasted_units"].sum().rename("wasted portions")
st.area_chart(daily.rolling(7).mean().dropna().rename("7-day average wasted portions"), height=200)

st.subheader("How it works")
ui.how_it_works()

st.subheader("Start here")
b = st.columns(7)
b[0].page_link("views/prep.py", label="Prep plan", icon=":material/checklist:")
b[1].page_link("views/stock.py", label="Stock", icon=":material/inventory_2:")
b[2].page_link("views/order.py", label="Ordering", icon=":material/local_shipping:")
b[3].page_link("views/weekly.py", label="Weekly order", icon=":material/calendar_month:")
b[4].page_link("views/cameras.py", label="Waste cameras", icon=":material/photo_camera:")
b[5].page_link("views/chat.py", label="Ask the assistant", icon=":material/smart_toy:")
b[6].page_link("views/about.py", label="About & responsible AI", icon=":material/verified_user:")
