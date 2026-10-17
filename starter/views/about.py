"""About & responsible AI."""
import pathlib
import sys

import streamlit as st

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import ui  # noqa: E402

ui.page_header(":material/verified_user: About & responsible AI",
               f"What {ui.APP_NAME} is built on, what it can't do, and who stays in control.",
               "Read this before showing the app to anyone, and before using real data.")

st.subheader("How it works")
ui.how_it_works()

st.subheader("Data sources")
st.markdown("""
| File | What | Source |
|---|---|---|
| `synthetic_restaurant_daily.csv` | daily prepared / sold / wasted portions | **Synthetic**, seeded generator |
| `recipes.csv` | grams per ingredient per portion | **Synthetic** |
| `stock.csv`, `suppliers.csv` | stock on hand, pack sizes, prices | **Synthetic**, fictional suppliers |
| `sample_plates/*.png` | plate images | **Drawn illustrations**, not photos |
No real restaurant, guest or supplier data is included.
""")

st.subheader("Human oversight")
st.markdown("""
- Prep plans and supplier orders are **suggestions**; a manager must approve. Orders are only exported as CSV.
- Plate estimates must be **confirmed or corrected** by staff before they are logged; both values are kept.
- The assistant **advises only** and cannot approve or order.
""")

st.subheader("Limits")
st.markdown("""
- Forecast = same-weekday average; ignores weather, holidays, events and menu changes. Sold-out days undercount demand.
- Plate-waste estimates are **unvalidated** (rough heuristic / untested LLM); a pilot must calibrate them against weighed plates.
- Optional LLM answers are checked: numbers not found in the app's data are flagged.
- The waste log lives in the browser session only (lost on refresh) in this demo.
""")

st.subheader("Privacy")
st.markdown("""
- Cameras point at plates and bins only — no guests or staff faces. No photos are stored by this demo.
- GDPR: if photos are stored in a real deployment, inform people, keep them briefly, and check LLM provider terms.
- Approvals record a **role**, not a person's name. API keys go in environment variables / Streamlit secrets, never in git.
""")
st.caption("Prepared before the AI for Good Hackathon (19 Oct 2026) as a disclosed starter; built with AI assistance. MIT licence.")
