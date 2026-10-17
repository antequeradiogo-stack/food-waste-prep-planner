"""Ordering: suggested supplier order per ingredient. Export only — nothing is sent."""
import pathlib
import sys

import streamlit as st

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import ordering  # noqa: E402
import ui  # noqa: E402

ui.page_header(":material/local_shipping: Ordering",
               "Works out what to order: forecast portions × recipe grams for the next days, minus what's in stock, rounded up to supplier packs.",
               "Pick how many days to cover, check the *why* column, adjust packs if needed, then approve and download the CSV.")

c1, c2 = st.columns(2)
days = c1.slider("Days to cover", 1, 7, 3, key="order_days")
buffer = c2.slider("Safety buffer %", 0, 30, 10, key="order_buffer")

sug = ordering.order_suggestions(ui.sales(), ui.recipes(), ui.stock(), ui.suppliers(), ui.plan_date(), days=days, buffer_pct=buffer)
to_order = sug[sug["packs"] > 0]
m1, m2, m3 = st.columns(3)
m1.metric("Ingredients to order", len(to_order))
m2.metric("Packs", int(to_order["packs"].sum()))
m3.metric("Est. cost (synthetic prices)", f"{int(to_order['est_cost_nok'].sum()):,} NOK")

st.subheader(f"Suggested order from {ui.plan_date()} for {days} day(s)")
show_all = st.toggle("Show ingredients with enough stock too", value=False)
table = sug if show_all else to_order
edited = st.data_editor(table[["ingredient", "supplier", "packs", "pack_size_g", "needed_g", "on_hand_g", "why"]],
                        hide_index=True, disabled=["ingredient", "supplier", "pack_size_g", "needed_g", "on_hand_g", "why"],
                        key="order_table", width="stretch")

st.subheader("Manager approval")
who = st.text_input("Approved by (role, not full name)", key="order_approver", placeholder="e.g. kitchen manager")
if st.button("Approve order", disabled=not who, key="order_approve", type="primary", icon=":material/check:"):
    st.session_state.approved_order = edited
    st.success(f"Order approved by {who}. Nothing was sent to suppliers — download the CSV and send it yourself.")
    st.download_button("Download order CSV", edited.to_csv(index=False), "supplier_order.csv")

with st.expander("Assumptions & limits", expanded=True, icon=":material/info:"):
    st.markdown("""
- Stock levels, suppliers, pack sizes and prices are **synthetic** (`data/stock.csv`, `data/suppliers.csv`).
- Uses standard recipe grams; trim loss, spoilage and lead times are not modelled yet (lead time is shown for info).
- Forecast for each day = same-weekday average before the plan date, + buffer.
- The app never contacts suppliers.
""")
