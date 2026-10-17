"""Weekly order: next Monday-Sunday forecast -> waste-aware plan -> ingredients - usable stock -> packs per delivery.
Nothing counts as ordered until a person clicks Approve; no supplier is ever contacted."""
import pathlib
import sys

import pandas as pd
import streamlit as st

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import ui  # noqa: E402
import weekly  # noqa: E402

ui.page_header(":material/calendar_month: Weekly order",
               "Plans next week's stock order: forecast per dish per day, trimmed for dishes that keep being wasted, "
               "turned into ingredients, minus stock that will still be good, rounded to supplier packs and split into deliveries.",
               "Add any events (extra covers), check the reasons, edit packs if needed, then approve. Approved orders appear in the history below.")

if "weekly_events" not in st.session_state:
    st.session_state.weekly_events = []
sales = ui.sales()
nxt = weekly.next_week_start(sales)
starts = [nxt] + [(pd.Timestamp(nxt) - pd.Timedelta(weeks=k)).date() for k in range(1, 5)]

c1, c2, c3 = st.columns(3)
week_start = c1.selectbox("Week starting (Monday)", starts, key="wk_start",
                          format_func=lambda d: f"{d} (next week)" if d == nxt else f"{d} (past week — backtest)")
buffer = c2.slider("Safety buffer %", 0, 30, weekly.DEFAULT_BUFFER_PCT, key="wk_buffer")
max_cut = c3.slider("Max waste trim %", 0, 30, weekly.DEFAULT_MAX_CUT_PCT, key="wk_max_cut",
                    help="Dishes that were over-prepped recently get their buffer trimmed by their waste rate, "
                         "but never more than this, and never below the forecast itself.")
dates = weekly.week_dates(week_start)

with st.expander("Events & extra covers", expanded=bool(st.session_state.weekly_events), icon=":material/celebration:"):
    e1, e2, e3, e4 = st.columns([2, 1, 1, 1])
    ev_day = e1.selectbox("Day", dates, key="ev_day", format_func=lambda d: f"{weekly.DAYS[d.weekday()]} {d}")
    ev_cov = e2.number_input("+ covers", 0, 1000, 0, step=5, key="ev_covers")
    ev_pct = e3.number_input("+ %", 0, 200, 0, step=5, key="ev_pct")
    if e4.button("Add event", key="ev_add", icon=":material/add:", disabled=not (ev_cov or ev_pct)):
        st.session_state.weekly_events.append({"date": ev_day, "extra_covers": int(ev_cov), "extra_pct": float(ev_pct)})
    for i, ev in enumerate(st.session_state.weekly_events):
        d = pd.Timestamp(ev["date"]).date()
        a, b = st.columns([4, 1])
        a.markdown(f"- **{weekly.DAYS[d.weekday()]} {d}**: +{ev.get('extra_covers', 0)} covers, +{ev.get('extra_pct', 0):g}%"
                   + ("" if d in dates else " _(outside this week — ignored)_"))
        if b.button("Remove", key=f"ev_rm_{i}"):
            st.session_state.weekly_events.pop(i)
            st.rerun()
    st.caption("+N covers ≈ N extra main courses; every dish that day scales by the same factor.")

res = weekly.build_week_order(sales, ui.recipes(), ui.suppliers(), week_start, batches=ui.batches(), stock=ui.stock(),
                              events=st.session_state.weekly_events, buffer_pct=buffer, max_cut_pct=max_cut)
lines, plan = res["lines"], res["plan"]

m1, m2, m3, m4 = st.columns(4)
m1.metric("Packs to order", int(lines["packs"].sum()))
m2.metric("Deliveries", lines["delivery_date"].nunique())
m3.metric("Est. cost (synthetic prices)", f"{int(lines['est_cost_nok'].sum()):,} NOK")
m4.metric("Stock expiring unused", f"{int(res['lost']['grams'].sum()):,} g", help="Not counted as available.")

st.subheader(f"Forecast per dish, {dates[0]} → {dates[-1]}")
dish = plan.groupby("item").agg(forecast=("forecast", "sum"), with_events=("forecast_adj", "sum"),
                                waste_rate_pct=("waste_rate_pct", "first"), buffer_trim_pct=("waste_cut_pct", "first"),
                                planned=("planned", "sum")).round(1).reset_index()
st.dataframe(dish, hide_index=True, width="stretch")
with st.expander("Per day", icon=":material/calendar_view_week:"):
    pivot = plan.pivot_table(index="item", columns="date", values="planned", aggfunc="sum").round(1)
    pivot.columns = [f"{weekly.DAYS[pd.Timestamp(c).weekday()]} {c}" for c in pivot.columns]
    st.dataframe(pivot, width="stretch")

st.subheader("Draft order by delivery")
st.caption("Stock used: " + ("**confirmed on the Stock page this session**" if ui.stock_is_confirmed() else "synthetic stock batches")
           + ". Fresh items arrive twice a week, long-life items weekly (synthetic `suppliers.csv`).")
edited = st.data_editor(lines[["delivery_date", "delivery_day", "order_by", "covers", "supplier", "ingredient", "storage",
                               "packs", "pack_size_g", "est_cost_nok", "reason"]],
                        hide_index=True, key="wk_table", width="stretch",
                        disabled=["delivery_date", "delivery_day", "order_by", "covers", "supplier", "ingredient",
                                  "storage", "pack_size_g", "est_cost_nok", "reason"],
                        column_config={"reason": st.column_config.TextColumn(width="large"),
                                       "packs": st.column_config.NumberColumn(min_value=0, step=1)})
edited = edited.assign(est_cost_nok=(edited["packs"] * lines["est_cost_nok"] / lines["packs"].where(lines["packs"] > 0)).fillna(0).round(0).astype(int),
                       order_g=edited["packs"] * edited["pack_size_g"])
covered = res["summary"]
if len(covered):
    with st.expander("Ingredients with enough stock", icon=":material/check_circle:"):
        st.dataframe(covered[covered["packs"] == 0][["ingredient", "reason"]], hide_index=True, width="stretch")

st.subheader("Approve or edit")
st.caption("Nothing is ordered until you approve. Approving saves the order in this app and gives you a CSV — it never contacts a supplier.")
who = st.text_input("Approved by (role, not full name)", key="wk_approver", placeholder="e.g. restaurant manager")
if st.button("Approve weekly order", disabled=not who, key="wk_approve", type="primary", icon=":material/check:"):
    oid = weekly.save_order(res, edited, who)
    st.session_state.weekly_approved = oid
    st.success(f"Weekly order {oid} approved by {who} and saved. Nothing was sent to suppliers — download the CSV and send it yourself.")
st.download_button("Download draft/approved CSV", edited.to_csv(index=False), f"weekly_order_{week_start}.csv",
                   key="wk_download", icon=":material/download:")

st.subheader("Order history")
history = weekly.list_orders()
if not history:
    st.caption("No approved weekly orders yet (saved under `data/orders/`; on Streamlit Cloud this resets when the app restarts).")
for o in history:
    with st.expander(f"Week {o['week_start']} — {o['packs']} packs, {o['est_cost_nok']:,} NOK — approved by {o['approved_by']} at {o['approved_at']}"):
        fva = weekly.forecast_vs_actual(o, sales)
        n = fva.attrs["days_with_actuals"]
        st.caption(f"Actual sales found for {n} of 7 days." if n else "No actual sales for this week in the data yet.")
        st.dataframe(fva, hide_index=True, width="stretch")
        st.dataframe(pd.DataFrame(o["lines"]).drop(columns=["reason"], errors="ignore"), hide_index=True, width="stretch")

with st.expander("Assumptions & limits", expanded=False, icon=":material/info:"):
    st.markdown(f"""
- Forecast = same-weekday average of the 4 weeks before the week starts (sold portions; sold-out days undercount demand).
- Waste trim uses the **synthetic** bin data (wasted ÷ prepared, last 28 days), capped at the slider and never below forecast. Plate-camera logs aren't used yet.
- Stock = batches with expiry; a batch counts only on days before its expiry date (oldest first). New deliveries are assumed fresh for the week.
- Delivery days and lead times are **synthetic**; "order by" = delivery − lead time and may already be past in this demo.
- Past weeks (backtest) use today's stock, so only the forecast-vs-actual comparison is meaningful there.
""")
