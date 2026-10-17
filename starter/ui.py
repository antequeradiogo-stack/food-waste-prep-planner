"""Shared helpers for all pages: data loading, session state, banner, explainer."""
import pathlib
import sys

import pandas as pd
import streamlit as st

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))   # so pages can import our modules
import assistant  # noqa: E402
import core  # noqa: E402
import plate_waste as pw  # noqa: E402
import stock as stock_mod  # noqa: E402

APP_NAME = "Leftover Lab"
DATA = pathlib.Path(__file__).resolve().parent.parent / "data"      # works from any folder

HOW_IT_WORKS = [
    (":material/trending_up:", "1. Forecast", "Past sales for the same weekday predict tomorrow's portions."),
    (":material/checklist:", "2. Approve prep", "The app suggests prep amounts with a reason; the manager edits and approves."),
    (":material/inventory_2:", "3. Check stock", "Shelf cameras count packs, scales weigh the rest; staff confirm. Use what expires first."),
    (":material/local_shipping:", "4. Order what's missing", "Recipe grams × forecast − confirmed stock, rounded to supplier packs. Export only."),
    (":material/photo_camera:", "5. Log waste", "Plate and bin entries (confirmed by staff) show what's thrown away, to tune the next forecast."),
]


# ---------- data (cached so pages load fast) ----------
@st.cache_data
def _csv(name: str) -> pd.DataFrame:
    return pd.read_csv(DATA / name)


@st.cache_data
def _default_sales() -> pd.DataFrame:
    return core.load_data(DATA / "synthetic_restaurant_daily.csv")


def sales() -> pd.DataFrame:
    """Uploaded sales CSV if the user gave one (Prep plan page), else the synthetic demo data."""
    up = st.session_state.get("uploaded_sales")
    return up if up is not None else _default_sales()


def recipes() -> pd.DataFrame:
    return _csv("recipes.csv")


@st.cache_data
def _default_batches() -> pd.DataFrame:
    return stock_mod.load_batches(DATA / "stock_batches.csv")


def batches() -> pd.DataFrame:
    """Stock batches confirmed in this session (Stock page), else the synthetic CSV."""
    b = st.session_state.get("stock_batches")
    return b if b is not None else _default_batches()


def stock_is_confirmed() -> bool:
    return st.session_state.get("stock_batches") is not None


def stock() -> pd.DataFrame:
    """ingredient, on_hand_g. From session-confirmed batches if any, else data/stock.csv."""
    if stock_is_confirmed():
        return stock_mod.on_hand(st.session_state.stock_batches, suppliers())
    return _csv("stock.csv")


def suppliers() -> pd.DataFrame:
    return _csv("suppliers.csv")


def plan_date():
    """Demo 'tomorrow' = the day after the last day in the sales history."""
    return (sales()["date"].max() + pd.Timedelta(days=1)).date()


def app_data() -> assistant.AppData:
    return assistant.AppData(sales(), recipes(), stock(), suppliers(), plan_date(), st.session_state.waste_log, batches())


# ---------- session + layout ----------
def init_state():
    for key, default in {"waste_log": [], "chat": [], "onboarded": False, "stock_changes": []}.items():
        if key not in st.session_state:
            st.session_state[key] = default


def page_header(title: str, what: str, todo: str):
    """Every page starts the same way: title, plain-language helper, what to do, demo banner."""
    init_state()
    st.title(title)
    st.caption(what)
    st.info(f"**What to do here:** {todo}", icon=":material/touch_app:")
    st.warning("SYNTHETIC DEMO DATA — numbers show how the app works, not real results.",
               icon=":material/science:")


def how_it_works():
    cols = st.columns(len(HOW_IT_WORKS))
    for col, (icon, title, text) in zip(cols, HOW_IT_WORKS):
        with col.container(border=True):
            st.markdown(f"#### {icon} {title}")
            st.caption(text)


def waste_log_df() -> pd.DataFrame:
    cols = ["time", "stream", "dish", "ingredient", "estimated_bucket", "confirmed_bucket", "grams_wasted", "reason"]
    return pd.DataFrame(st.session_state.get("waste_log", []), columns=cols)
