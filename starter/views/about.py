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
| `stock_batches.csv`, `stock.csv` | batches by location with received/expiry dates; totals | **Synthetic** |
| `suppliers.csv` | pack sizes, prices, lead times, storage, delivery days | **Synthetic**, fictional suppliers |
| `data/orders/` | approved weekly orders (JSON + CSV), created by the app | Your approvals; ephemeral on Streamlit Cloud |
| `shelf_samples/*.png` | shelf images | **Drawn illustrations**, not photos |
| `sample_plates/*.png` | plate images | **Drawn illustrations**, not photos |

No real restaurant, guest or supplier data is included.
""")

st.subheader("Human oversight")
st.markdown("""
- Prep plans, supplier orders and weekly orders are **suggestions**; a manager must approve. Approved weekly orders are saved in the app and exported as CSV — no supplier is ever contacted.
- Plate estimates must be **confirmed or corrected** by staff before they are logged; both values are kept.
- The assistant **advises only**: it can prepare a draft weekly order or add an event to the draft, but only a person can approve.
- Shelf counts and scale readings change stock **only after staff confirm**; odd readings (negative, over max, sudden jumps) are flagged and start unticked.
""")

st.subheader("Limits")
st.markdown("""
- Forecast = same-weekday average; ignores weather, holidays and menu changes; events only count if a manager adds them (Weekly order). Sold-out days undercount demand.
- Plate-waste estimates are **unvalidated** (rough heuristic / untested LLM); a pilot must calibrate them against weighed plates.
- Optional LLM answers are checked: numbers not found in the app's data are flagged.
- Shelf cameras count packs only — not how full a sack is, and they can't read expiry dates. The shelf heuristic only works on the bundled drawings.
- Real cameras/scales need a local gateway; the cloud app can't reach the restaurant network.
- The waste log lives in the browser session only (lost on refresh) in this demo.
""")

st.subheader("Privacy")
st.markdown("""
- Cameras point at plates, bins and shelves only — no guests or staff faces. No photos are stored by this demo.
- Data minimisation: keep counts, grams and timestamps — not images — and only what's needed to plan.
- GDPR: if photos are stored in a real deployment, inform people, keep them briefly, and check LLM provider terms.
- Approvals record a **role**, not a person's name. API keys go in environment variables / Streamlit secrets, never in git.
""")
st.caption("Prepared before the AI for Good Hackathon (19 Oct 2026) as a disclosed starter; built with AI assistance. MIT licence.")
