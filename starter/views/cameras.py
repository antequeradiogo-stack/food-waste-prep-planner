"""Waste cameras: plate-return camera (estimate + confirm) and kitchen-bin camera (scale grams)."""
import pathlib
import sys
from datetime import datetime

import streamlit as st
from PIL import Image

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import cameras  # noqa: E402
import plate_waste as pw  # noqa: E402
import ui  # noqa: E402

ui.page_header(":material/photo_camera: Waste cameras",
               "Log what comes back on plates and what goes in the kitchen bin. Staff always confirm before anything is saved.",
               "Pick a camera tab, choose an image source, check the estimate, correct it if needed, then click **Confirm**.")

recipes = ui.recipes()
SAMPLES = sorted((ui.DATA / "sample_plates").glob("*.png"))
SOURCES = ["Sample plate (illustration)", "Upload photo", "This device's camera", "IP camera snapshot (RTSP)"]


def get_image(prefix: str, allow_none: bool = False, sample_key: str | None = None):
    """Let staff choose where the image comes from. Returns (image or None, id, caption)."""
    options = (["No photo"] if allow_none else []) + SOURCES
    source = st.radio("Image source", options, key=f"{prefix}source", horizontal=True)  # e.g. plate_source
    if source == "Sample plate (illustration)":
        name = st.selectbox("Sample (synthetic illustration)", [p.stem for p in SAMPLES], key=sample_key or f"{prefix}sample")
        return Image.open(ui.DATA / "sample_plates" / f"{name}.png"), name, "SYNTHETIC illustration, not a photo"
    if source == "Upload photo":
        f = st.file_uploader("Photo", type=["png", "jpg", "jpeg"], key=f"{prefix}photo")
        return (Image.open(f), f.name, "Uploaded photo") if f else (None, None, "")
    if source == "This device's camera":
        shot = st.camera_input("Take a picture of the plate only", key=f"{prefix}cam")
        return (Image.open(shot), f"cam-{shot.size}", "Device camera") if shot else (None, None, "")
    if source == "IP camera snapshot (RTSP)":
        url = st.text_input("Camera URL (rtsp://…) — don't paste passwords on a shared/public deployment",
                            key=f"{prefix}rtsp")
        if st.button("Grab one frame", key=f"{prefix}grab"):
            img, msg = cameras.grab_rtsp_frame(url)
            st.session_state[f"{prefix}frame"] = img
            (st.success if img else st.info)(msg)
        img = st.session_state.get(f"{prefix}frame")
        return (img, f"rtsp-{id(img)}", "IP camera frame (not stored)") if img else (None, None, "")
    return None, None, ""


def log_rows(rows):
    st.session_state.waste_log.extend(rows)


plate_tab, bin_tab, connect_tab = st.tabs([":material/restaurant: Plate return camera",
                                           ":material/delete: Kitchen bin camera",
                                           ":material/settings_input_antenna: Connecting real cameras"])

# ---------------- Plate return ----------------
with plate_tab:
    st.caption("Use at the plate-return / dish station only. No guests or faces in the frame.")
    col1, col2 = st.columns(2)
    with col1:
        dish = st.selectbox("Dish ordered", sorted(recipes["dish"].unique()), key="dish")
        image, image_id, caption = get_image("plate_", sample_key="sample")
        if image is not None:
            st.image(image, caption=caption, width=260)

    with col2:
        if image is None:
            st.info("Choose or capture a plate image to get an estimate.")
        else:
            est = pw.estimate(image, dish, recipes)
            st.metric("Estimated leftover", f"{est['bucket']} (~{pw.BUCKETS[est['bucket']]:.0%})")
            st.write(f"Confidence: **{est['confidence']}** · Source: {est['source']}")
            st.caption(est["reasoning"])
            # When a new plate/dish is chosen, reset the slider to the new estimate
            plate_id = (dish, image_id)
            if st.session_state.get("plate_id") != plate_id:
                st.session_state.plate_id = plate_id
                st.session_state.confirmed_bucket = est["bucket"]
            # Human in the loop: staff confirm or correct before anything is logged
            confirmed = st.select_slider("Confirm or correct leftover", options=list(pw.BUCKETS), key="confirmed_bucket")
            grams = pw.grams_wasted(recipes, dish, confirmed)
            st.dataframe(grams, hide_index=True)
            if st.button("Confirm and add to log", key="confirm", type="primary", icon=":material/check:"):
                now = datetime.now().isoformat(timespec="seconds")
                log_rows([{"time": now, "stream": "plate_return", "dish": dish, "ingredient": r.ingredient,
                           "estimated_bucket": est["bucket"], "confirmed_bucket": confirmed,
                           "grams_wasted": r.grams_wasted, "reason": "plate leftover"} for r in grams.itertuples()])
                st.success(f"Logged {dish}: {confirmed}.")

# ---------------- Kitchen bin ----------------
with bin_tab:
    st.caption("Kitchen bin station: weigh the waste on a scale and type the grams. The photo is optional and not stored.")
    col1, col2 = st.columns(2)
    with col1:
        img, _, cap = get_image("bin_", allow_none=True)
        if img is not None:
            st.image(img, caption=cap, width=260)
    with col2:
        ingredients = sorted(recipes["ingredient"].unique()) + ["mixed / other"]
        ingredient = st.selectbox("What was thrown away?", ingredients, key="bin_ingredient")
        reason = st.selectbox("Reason", ["over-prepped", "spoiled / expired", "trim / peel", "dropped / mistake", "other"],
                              key="bin_reason")
        grams_in = st.number_input("Weight from scale (g)", min_value=0, max_value=50000, step=10, key="bin_grams")
        if st.button("Confirm and add to log", key="bin_confirm", disabled=grams_in <= 0, type="primary", icon=":material/check:"):
            log_rows([{"time": datetime.now().isoformat(timespec="seconds"), "stream": "kitchen_bin", "dish": "-",
                       "ingredient": ingredient, "estimated_bucket": "", "confirmed_bucket": "",
                       "grams_wasted": float(grams_in), "reason": reason}])
            st.success(f"Logged {grams_in} g of {ingredient} ({reason}).")

# ---------------- Connecting real cameras ----------------
with connect_tab:
    st.markdown("""
**This demo does not connect to real CCTV.** In a real kitchen you could:
1. **IP camera (RTSP)** above the plate-return belt or bin scale, pointed down at plates only. The app grabs one snapshot when staff press a button (needs `opencv-python-headless`).
2. **A phone or tablet** mounted at the plate return, using *This device's camera* in this page — simplest pilot.
3. **Smart scale + camera** at the kitchen bin: the scale gives grams (measured), the photo only helps label the item.

**Privacy (GDPR):** frame only plates/bins — no guests or staff faces; don't store photos unless needed (this demo stores none);
if you do, inform people, set short retention, and check your LLM provider's data terms before sending images.
Keep camera passwords out of the app and out of git (use Streamlit secrets).
""")

# ---------------- Log ----------------
st.subheader("Waste log (this session)")
log = ui.waste_log_df()
if log.empty:
    st.write("No entries yet.")
else:
    c1, c2, c3 = st.columns(3)
    c1.write("By source (g)"); c1.dataframe(log.groupby("stream")["grams_wasted"].sum().reset_index(), hide_index=True)
    c2.write("By dish (g)"); c2.dataframe(log.groupby("dish")["grams_wasted"].sum().reset_index(), hide_index=True)
    c3.write("By ingredient (g)"); c3.dataframe(log.groupby("ingredient")["grams_wasted"].sum().reset_index(), hide_index=True)
    st.download_button("Download waste log CSV", log.to_csv(index=False), "waste_log.csv")
    st.caption("This log is meant to feed the prep forecast (e.g. lower buffers for dishes often returned half-eaten).")

with st.expander("Accuracy & limits", expanded=True, icon=":material/info:"):
    st.markdown("""
- **Plate estimates are unvalidated.** The offline method is a rough heuristic, demo only; the LLM option is untested.
- A real pilot needs calibration: weigh a sample of returned plates on a scale and compare with the estimates.
- Buckets are coarse (25% steps); grams assume the standard recipe portion was served.
- Kitchen-bin grams come from a scale (measured) — more reliable than photo estimates.
- Camera at the plate-return station only, pointed at plates; no guests or staff faces in frame (GDPR).
""")
