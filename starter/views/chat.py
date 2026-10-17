"""Assistant: chat grounded in the app's own data. Advises only."""
import os
import pathlib
import sys

import pandas as pd
import streamlit as st

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import assistant  # noqa: E402
import ui  # noqa: E402

ui.page_header(":material/smart_toy: Assistant",
               "Ask about prep, orders, waste or busy days. Answers come from this app's data, with a *Why* line.",
               "Click a suggested question or type your own. To act on advice, approve on the Prep plan or Ordering page.")

mode = "LLM with tools (numbers checked against app data)" if os.environ.get("LLM_API_KEY") else "Offline (rule-based, uses app data)"
st.caption(f"Mode: {mode}. The assistant never approves plans or places orders.")

data = ui.app_data()
st.markdown("**Suggested questions**")
cols = st.columns(3)
clicked = None
for i, q in enumerate(assistant.SUGGESTED_QUESTIONS):
    if cols[i % 3].button(q, key=f"chip_{i}", width="stretch"):
        clicked = q

typed = st.chat_input("Ask about prep, orders, waste…")
question = typed or clicked
if question:
    history = [{"role": m["role"], "content": m["content"]} for m in st.session_state.chat]
    res = assistant.answer(question, data, history=history)
    st.session_state.chat.append({"role": "user", "content": question})
    st.session_state.chat.append({"role": "assistant", "content": res["text"], "tools": res["tools"], "mode": res["mode"]})

for m in st.session_state.chat:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])
        for t in m.get("tools", []):
            with st.expander(f"Data used: {t['name']}", icon=":material/dataset:"):
                st.json(t["result"], expanded=False)

if st.session_state.chat and st.button("Clear chat", key="clear_chat", icon=":material/delete_sweep:"):
    st.session_state.chat = []
    st.rerun()

c1, c2 = st.columns(2)
c1.page_link("views/prep.py", label="Go to Prep plan to approve", icon=":material/checklist:")
c2.page_link("views/order.py", label="Go to Ordering to approve", icon=":material/local_shipping:")
