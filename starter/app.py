"""Food waste prep planner. Run: streamlit run starter/app.py"""
import pathlib
from datetime import datetime

import pandas as pd
import streamlit as st
from PIL import Image

import core
import plate_waste as pw

DATA = pathlib.Path(__file__).resolve().parent.parent / "data"   # works from any folder
DEFAULT_CSV = DATA / "synthetic_restaurant_daily.csv"
SAMPLES = sorted((DATA / "sample_plates").glob("*.png"))

st.set_page_config(page_title="Food waste prep planner", layout="wide")
st.title("Food waste prep planner")
st.warning("Demo uses SYNTHETIC data and illustrations. Suggestions are not orders; a person must approve.")

up = st.sidebar.file_uploader("Sales CSV (date, item, sold_units)", type="csv")
df = core.load_data(up if up else DEFAULT_CSV)
recipes = pw.load_recipes(DATA / "recipes.csv")
if "waste_log" not in st.session_state:
    st.session_state.waste_log = []          # in-session only; lost when the browser tab closes

tab_plan, tab_waste = st.tabs(["Prep plan", "Log plate waste"])

# ---------------- Tab 1: prep plan ----------------
with tab_plan:
    target = st.date_input("Plan for date", value=(df["date"].max() + pd.Timedelta(days=1)).date())
    weeks = st.slider("Weeks of history", 1, 8, 4)
    buffer = st.slider("Safety buffer %", 0, 30, 10)
    st.subheader("History")
    st.line_chart(df.pivot_table(index="date", columns="item", values="sold_units"))

    rec = core.recommend(core.weekday_moving_average(df, target, weeks), buffer)
    st.subheader(f"Suggested prep for {target}")
    edited = st.data_editor(rec[["item", "forecast", "suggested_prep", "reason"]],
                            disabled=["item", "forecast", "reason"], key="rec")
    st.markdown(core.explain(rec))
    if st.session_state.waste_log:
        st.info(f"{len(st.session_state.waste_log)} plate-waste entries logged this session. "
                "Next step: use them to adjust the buffer per dish (not automated yet).")

    st.subheader("Human approval")
    who = st.text_input("Approved by (role, not full name)", key="approver")
    if st.button("Approve plan", disabled=not who, key="approve"):
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

# ---------------- Tab 2: log plate waste ----------------
with tab_waste:
    st.caption("Use at the plate-return / dish station only. No guests or faces in the frame.")
    col1, col2 = st.columns(2)
    with col1:
        dish = st.selectbox("Dish ordered", sorted(recipes["dish"].unique()), key="dish")
        photo = st.file_uploader("Plate photo", type=["png", "jpg", "jpeg"], key="photo")
        sample = st.selectbox("...or a sample (synthetic illustration)", [p.stem for p in SAMPLES], key="sample")
        image = Image.open(photo) if photo else Image.open(DATA / "sample_plates" / f"{sample}.png")
        st.image(image, caption="Uploaded photo" if photo else "SYNTHETIC illustration, not a photo", width=260)

    with col2:
        est = pw.estimate(image, dish, recipes)
        st.metric("Estimated leftover", f"{est['bucket']} (~{pw.BUCKETS[est['bucket']]:.0%})")
        st.write(f"Confidence: **{est['confidence']}** · Source: {est['source']}")
        st.caption(est["reasoning"])
        # When a new plate/dish is chosen, reset the slider to the new estimate
        plate_id = (dish, photo.name if photo else sample)
        if st.session_state.get("plate_id") != plate_id:
            st.session_state.plate_id = plate_id
            st.session_state.confirmed_bucket = est["bucket"]
        # Human in the loop: staff confirm or correct before anything is logged
        confirmed = st.select_slider("Confirm or correct leftover", options=list(pw.BUCKETS),
                                     key="confirmed_bucket")
        grams = pw.grams_wasted(recipes, dish, confirmed)
        st.dataframe(grams, hide_index=True)
        if st.button("Confirm and add to log", key="confirm"):
            for r in grams.itertuples():
                st.session_state.waste_log.append({
                    "time": datetime.now().isoformat(timespec="seconds"), "dish": dish,
                    "estimated_bucket": est["bucket"], "confirmed_bucket": confirmed,
                    "ingredient": r.ingredient, "grams_wasted": r.grams_wasted})
            st.success(f"Logged {dish}: {confirmed}.")

    st.subheader("Waste log (this session)")
    if st.session_state.waste_log:
        log = pd.DataFrame(st.session_state.waste_log)
        c1, c2 = st.columns(2)
        c1.write("By dish (g)"); c1.dataframe(log.groupby("dish")["grams_wasted"].sum().reset_index(), hide_index=True)
        c2.write("By ingredient (g)"); c2.dataframe(log.groupby("ingredient")["grams_wasted"].sum().reset_index(), hide_index=True)
        st.download_button("Download waste log CSV", log.to_csv(index=False), "plate_waste_log.csv")
        st.caption("This log is meant to feed the prep forecast (e.g. lower buffers for dishes often returned half-eaten).")
    else:
        st.write("No entries yet.")

    with st.expander("Accuracy & limits", expanded=True):
        st.markdown("""
- **Estimates are unvalidated.** The offline method is a rough heuristic, demo only; the LLM option is untested.
- A real pilot needs calibration: weigh a sample of returned plates on a scale and compare with the estimates.
- Buckets are coarse (25% steps); grams assume the standard recipe portion was served.
- Camera at the plate-return station only, pointed at plates; no guests or staff faces in frame.
- GDPR: don't store photos unless needed; if you do, tell guests/staff, set a short retention period, and keep them out of LLM prompts unless the provider terms allow it.
""")
