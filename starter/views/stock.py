"""Stock: shelf camera counts, scale readings, expiry & use-first. Staff confirm every change."""
import json
import pathlib
import sys

import pandas as pd
import streamlit as st
from PIL import Image

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import cameras  # noqa: E402
import scales  # noqa: E402
import shelf  # noqa: E402
import stock as stock_mod  # noqa: E402
import ui  # noqa: E402

ui.page_header(":material/inventory_2: Stock",
               "What's on the shelves, what expires soon, and what to use first. Shelf cameras count packs; scales weigh the rest.",
               "Pick a location and check the shelf count, or read the scales. Correct anything wrong, tick the box and click **Confirm** — only then does stock change (and Ordering uses it).")

suppliers, recipes = ui.suppliers(), ui.recipes()
batches = ui.batches()
st.caption("Stock source: " + ("**confirmed in this session**" if ui.stock_is_confirmed()
                               else "synthetic stock file (nothing confirmed yet this session)"))


def save(new_batches, changes):
    st.session_state.stock_batches = new_batches
    st.session_state.stock_changes.extend(changes)


tab_over, tab_shelf, tab_scales, tab_expiry, tab_devices = st.tabs([
    ":material/view_list: Overview", ":material/photo_camera: Shelf camera", ":material/scale: Scales",
    ":material/event_busy: Expiry & use first", ":material/hub: How devices connect"])

# ---------------- Overview ----------------
with tab_over:
    loc_table = stock_mod.by_location(batches, suppliers)
    loc_table["next_expiry"] = loc_table["next_expiry"].dt.date
    for loc in stock_mod.LOCATIONS:
        rows = loc_table[loc_table.location == loc].drop(columns="location")
        with st.expander(f"{loc.title()} — {len(rows)} items", expanded=(loc == stock_mod.LOCATIONS[0])):
            st.dataframe(rows, hide_index=True, width="stretch")
    if st.session_state.stock_changes:
        st.markdown("**Changes confirmed this session**")
        st.dataframe(pd.DataFrame(st.session_state.stock_changes), hide_index=True, width="stretch")

# ---------------- Shelf camera ----------------
with tab_shelf:
    st.caption("Point the camera at shelves only — no staff faces. Photos are not stored.")
    location = st.selectbox("Location", stock_mod.LOCATIONS, key="shelf_location")
    items = shelf.pack_items_at(batches, location)
    col1, col2 = st.columns(2)
    with col1:
        source = st.radio("Image source", ["Sample shelf (illustration)", "Upload photo", "This device's camera",
                                           "IP camera snapshot (RTSP)"], key="shelf_source", horizontal=True)
        image, image_id = None, None
        if source == "Sample shelf (illustration)":
            image_id = f"sample-{location}"
            image = Image.open(ui.DATA / "shelf_samples" / f"{location.replace(' ', '_')}.png")
        elif source == "Upload photo":
            f = st.file_uploader("Shelf photo", type=["png", "jpg", "jpeg"], key="shelf_photo")
            image, image_id = (Image.open(f), f.name) if f else (None, None)
        elif source == "This device's camera":
            shot = st.camera_input("Take a picture of the shelf", key="shelf_cam")
            image, image_id = (Image.open(shot), f"cam-{shot.size}") if shot else (None, None)
        else:
            url = st.text_input("Camera URL (rtsp://…) — don't paste passwords on a shared/public deployment", key="shelf_rtsp")
            if st.button("Grab one frame", key="shelf_grab"):
                img, msg = cameras.grab_rtsp_frame(url)
                st.session_state.shelf_frame = img
                (st.success if img else st.info)(msg)
            image = st.session_state.get("shelf_frame")
            image_id = f"rtsp-{id(image)}" if image else None
        if image is not None:
            st.image(image, caption="SYNTHETIC illustration" if image_id.startswith("sample") else "Shelf image", width="stretch")
    with col2:
        if not items:
            st.info("No packed items are recorded at this location (weighed items are updated via Scales).")
        elif image is None:
            st.info("Choose or capture a shelf image.")
        else:
            est = shelf.estimate_counts(image, location, items)
            counted = {c["item"]: c for c in est["counts"]}
            recorded = batches[(batches.location == location) & (batches.unit == "pack")].groupby("ingredient")["quantity"].sum()
            table = pd.DataFrame([{"item": i, "recorded_packs": int(recorded.get(i, 0)),
                                   "counted_packs": int(counted[i]["count"]) if i in counted else int(recorded.get(i, 0)),
                                   "estimate": "camera" if i in counted else "not seen → recorded value",
                                   "confidence": counted.get(i, {}).get("confidence", "-")} for i in items])
            st.write(f"Estimate source: **{est['source']}**")
            edited = st.data_editor(table, hide_index=True, width="stretch", key=f"shelf_table_{location}_{image_id}",
                                    disabled=["item", "recorded_packs", "estimate", "confidence"],
                                    column_config={"counted_packs": st.column_config.NumberColumn(min_value=0, max_value=200, step=1)})
            diffs = edited[edited.counted_packs != edited.recorded_packs]
            st.caption(f"{len(diffs)} item(s) differ from the records." if len(diffs) else "Counts match the records.")
            checked = st.checkbox("I checked these counts against the shelf", key="shelf_checked")
            if st.button("Confirm counts → update stock", key="shelf_confirm", disabled=not checked, type="primary",
                         icon=":material/check:"):
                new, changes = batches, []
                for r in edited.itertuples():
                    if r.counted_packs != r.recorded_packs:
                        new, text = stock_mod.set_total(new, r.item, location, r.counted_packs)
                        changes.append({"source": "shelf camera", "change": text})
                save(new, changes)
                st.success(f"Stock updated for {location}: {len(changes)} change(s). Ordering now uses these counts.")
    st.warning("Cameras count **packs**, not how full a sack or carton is — use scales for weight. "
               "They can't read expiry dates on the back of packs; staff record those on delivery.", icon=":material/info:")

# ---------------- Scales ----------------
with tab_scales:
    st.caption("Weighed items (fish, veg, bread…) are updated from scale readings. Review every reading before applying.")
    src = st.radio("Reading source", ["Simulated scales (demo)", "HTTP/JSON pull", "CSV import (gateway export)",
                                      "Serial/ASCII lines (paste)"], key="scale_source", horizontal=True)
    max_g = st.number_input("Max plausible reading (g)", 1000, 200000, 50000, step=1000, key="scale_max")
    grams_now = stock_mod.with_grams(batches, suppliers).groupby(["ingredient", "location"])["grams"].sum()
    readings = None
    if src == "Simulated scales (demo)":
        weighed = {k: v for k, v in grams_now.items()
                   if batches[(batches.ingredient == k[0]) & (batches.location == k[1])]["unit"].iloc[0] == "g"}
        if st.button("Read simulated scales", key="scale_read", icon=":material/scale:"):
            readings = scales.SimulatedScale(weighed).read()
    elif src == "HTTP/JSON pull":
        st.info("Streamlit Cloud can't reach devices on the restaurant network — this only works for a URL the app "
                "server can reach (e.g. a gateway API). Expected JSON: see *How devices connect*.")
        url = st.text_input("Readings URL", key="scale_url", placeholder="https://gateway.example/readings")
        if st.button("Fetch readings", key="scale_fetch"):
            try:
                readings = scales.HttpJsonScale(url, timeout=5).read()
            except Exception as e:
                st.error(f"Could not read: {e}")
    elif src == "CSV import (gateway export)":
        f = st.file_uploader("CSV: " + ",".join(scales.CSV_COLUMNS), type="csv", key="scale_csv")
        if f:
            try:
                readings = scales.parse_csv(f)
            except Exception as e:
                st.error(f"Could not read CSV: {e}")
    else:
        c1, c2 = st.columns(2)
        ing = c1.selectbox("Ingredient on the scale", sorted(batches.ingredient.unique()), key="serial_ingredient")
        loc = c2.selectbox("Location", stock_mod.LOCATIONS, key="serial_location")
        lines = st.text_area("Lines from the scale (one per line)", "ST,GS,+  2.850kg", key="serial_lines")
        if st.button("Parse lines", key="serial_parse"):
            readings = []
            for ln in lines.splitlines():
                if not ln.strip():
                    continue
                try:
                    p = scales.parse_ascii_line(ln)
                    readings.append(scales.Reading("serial-1", loc, ing, p["grams"], "", "serial" + ("" if p["stable"] else " (UNSTABLE)")))
                except ValueError as e:
                    st.error(str(e))
    if readings is not None:
        st.session_state.scale_readings = [r.to_dict() for r in readings]

    if st.session_state.get("scale_readings"):
        rows = []
        for r in st.session_state.scale_readings:
            reading = scales.Reading(**r)
            prev = grams_now.get((reading.ingredient, reading.location))
            flags = scales.check_plausibility(reading, prev, max_grams=max_g)
            if prev is None:
                flags.append("no matching stock batch")
            if "UNSTABLE" in reading.source:
                flags.append("scale not stable")
            rows.append({**r, "recorded_g": None if prev is None else float(prev), "flags": "; ".join(flags),
                         "apply": not flags})
        edited = st.data_editor(pd.DataFrame(rows), hide_index=True, width="stretch", key="scale_table",
                                disabled=[c for c in rows[0] if c != "apply"])
        st.caption("Flagged readings start unticked. Tick *apply* only after checking them.")
        if st.button("Apply ticked readings → update stock", key="scale_apply", type="primary", icon=":material/check:"):
            new, changes = batches, []
            for r in edited[edited["apply"]].itertuples():
                if r.recorded_g is None or pd.isna(r.recorded_g):
                    continue
                qty = stock_mod.grams_to_quantity(new, suppliers, r.ingredient, r.location, r.grams)
                new, text = stock_mod.set_total(new, r.ingredient, r.location, qty)
                changes.append({"source": f"scale {r.scale_id}", "change": text})
            save(new, changes)
            st.session_state.scale_readings = []
            st.success(f"Applied {len(changes)} reading(s). Ordering now uses the updated stock.")

# ---------------- Expiry ----------------
with tab_expiry:
    days = st.slider("Show batches expiring within (days)", 0, 14, 2, key="expiry_days")
    exp = stock_mod.use_first(stock_mod.expiring(batches, ui.plan_date(), days), recipes)
    st.metric(f"Batches expiring within {days} day(s) of {ui.plan_date()}", len(exp))
    if exp.empty:
        st.success("Nothing expiring in that window.")
    else:
        show = exp[["ingredient", "location", "batch_id", "quantity", "unit", "expiry_date", "days_left", "use_in_dishes"]].copy()
        show["expiry_date"] = show["expiry_date"].dt.date
        st.dataframe(show, hide_index=True, width="stretch")
        st.markdown("**Use first:** " + "; ".join(f"{r.ingredient} → {r.use_in_dishes}" for r in exp.drop_duplicates("ingredient").itertuples()))
    st.info("FIFO — first in, first out: use the oldest batch first, put new deliveries behind old ones. "
            "Expiry dates here are synthetic; always check the label.", icon=":material/info:")

# ---------------- Devices ----------------
with tab_devices:
    st.markdown("**How real cameras and scales would connect.** This demo runs in the cloud (or your laptop) and "
                "**can't reach devices on the restaurant network**. A small local gateway does that and pushes readings out.")
    st.graphviz_chart("""
digraph G { rankdir=LR; node [shape=box, style="rounded,filled", fillcolor="#F2F6F4", color="#2E7D5B", fontname="sans-serif"];
  scales [label="Scales\\n(USB/serial, Wi-Fi)"]; cams [label="Cameras\\n(shelf, plate, bin)"];
  gw [label="Local gateway PC\\n(pyserial, snapshots)"]; api [label="API + database\\n(cloud)"]; app [label="Leftover Lab\\n(staff confirm)"];
  scales -> gw; cams -> gw; gw -> api [label="HTTPS push (JSON)"]; api -> app [label="pull"]; }
""")
    st.markdown("**Push / pull JSON format** (HTTP pull URL must return this; a gateway can POST it to your API):")
    st.code(json.dumps(scales.PUSH_PAYLOAD_EXAMPLE, indent=2), language="json")
    st.markdown(f"**CSV import columns:** `{','.join(scales.CSV_COLUMNS)}` (units: g, kg, lb, oz).")
    st.markdown("**Serial/USB scales:** many send ASCII lines like `ST,GS,+  1.234kg` (ST stable / US unstable / OL overload; "
                "GS gross / NT net). Read them with `pyserial` on the gateway (optional, not needed for this app) and "
                "parse with `scales.parse_ascii_line()`.")
    st.markdown("**Safety:** every reading is reviewed before it changes stock; negative, over-max and sudden-jump readings are flagged. "
                "Keep device passwords in the gateway / secrets, never in this app or git.")
