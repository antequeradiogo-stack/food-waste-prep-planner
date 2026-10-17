"""Weekly stock order for next Monday-Sunday (pure logic, no Streamlit).

Steps (each a small function, tested separately):
1. forecast_week     - portions per dish per day, same-weekday moving average (ordering.forecast_next_days).
2. apply_events      - manager adjustments: +N covers or +% on a day (scales every dish that day).
3. waste_rates/plan_dishes - add the safety buffer, then trim it for dishes that keep being over-prepped:
                       cut = min(recent waste rate, max cut); never below the (event-adjusted) forecast.
4. ingredient_daily_needs - portions x recipe grams per ingredient per day.
5. net_stock         - FIFO over stock batches by expiry: stock that expires before it's needed is NOT counted.
6. build_week_order  - shortfall per delivery window, rounded UP to supplier packs; fresh items twice a week,
                       long-life weekly (suppliers.csv delivery_days); a plain-language reason per line.
7. save_order/list_orders/forecast_vs_actual - approved orders saved as JSON + CSV under data/orders/.

Suggestions only: nothing counts as ordered until a person approves, and no supplier is ever contacted.
"""
import json
import os
import math
import pathlib
import re
from datetime import datetime

import pandas as pd

import ordering

ORDERS_DIR = pathlib.Path(__file__).resolve().parent.parent / "data" / "orders"   # git-ignored


def orders_dir() -> pathlib.Path:
    """data/orders/ (writable but ephemeral on Streamlit Cloud); override with LEFTOVER_ORDERS_DIR."""
    return pathlib.Path(os.environ.get("LEFTOVER_ORDERS_DIR") or ORDERS_DIR)
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
DEFAULT_BUFFER_PCT = 10
DEFAULT_MAX_CUT_PCT = 10


# ------------------------------------------------------------------ 1. forecast window
def next_week_start(sales: pd.DataFrame):
    """The Monday after the latest date in the sales data."""
    last = pd.Timestamp(sales["date"].max())
    return (last + pd.Timedelta(days=7 - last.weekday())).date()


def week_dates(week_start) -> list:
    s = pd.Timestamp(week_start)
    return [(s + pd.Timedelta(days=i)).date() for i in range(7)]


def forecast_week(sales: pd.DataFrame, week_start, weeks: int = 4) -> pd.DataFrame:
    """date, item, forecast for the 7 days from week_start (history strictly before week_start)."""
    return ordering.forecast_next_days(sales, week_start, days=7, weeks=weeks)


# ------------------------------------------------------------------ 2. events
def apply_events(fc: pd.DataFrame, events: list | None, sales: pd.DataFrame | None = None) -> pd.DataFrame:
    """events: [{"date": date, "extra_covers": int, "extra_pct": float, "note": str}].

    +N covers: one cover ~ one main course, so the day scales by N / forecast mains that day
    (all dishes if the data has no 'main' category). +%: the day scales by that percentage."""
    out = fc.copy()
    out["event_factor"] = 1.0
    mains = set()
    if sales is not None and "category" in sales:
        mains = set(sales.loc[sales["category"] == "main", "item"].unique())
    for ev in events or []:
        day = pd.Timestamp(ev["date"]).date()
        on_day = out["date"] == day
        if not on_day.any():
            continue
        base = out.loc[on_day & out["item"].isin(mains), "forecast"].sum() if mains else 0
        base = base or out.loc[on_day, "forecast"].sum()
        factor = 1 + float(ev.get("extra_pct", 0) or 0) / 100
        if base:
            factor += float(ev.get("extra_covers", 0) or 0) / base
        out.loc[on_day, "event_factor"] *= factor
    out["event_factor"] = out["event_factor"].round(3)
    out["forecast_adj"] = (out["forecast"] * out["event_factor"]).round(1)
    return out


# ------------------------------------------------------------------ 3. waste-aware buffer
def waste_rates(sales: pd.DataFrame, before, days: int = 28) -> pd.DataFrame:
    """item, waste_rate_pct = wasted / prepared portions in the `days` before `before` (bin data)."""
    before = pd.Timestamp(before)
    s = sales[(sales["date"] < before) & (sales["date"] >= before - pd.Timedelta(days=days))]
    if "wasted_units" not in s or "prepared_units" not in s or s.empty:
        return pd.DataFrame(columns=["item", "waste_rate_pct"])
    g = s.groupby("item")[["wasted_units", "prepared_units"]].sum()
    g["waste_rate_pct"] = (100 * g["wasted_units"] / g["prepared_units"].where(g["prepared_units"] > 0)).fillna(0).round(1)
    return g["waste_rate_pct"].reset_index()


def plan_dishes(fc_adj: pd.DataFrame, rates: pd.DataFrame, buffer_pct: float = DEFAULT_BUFFER_PCT,
                max_cut_pct: float = DEFAULT_MAX_CUT_PCT) -> pd.DataFrame:
    """planned = forecast_adj x (1 + buffer) x (1 - cut), cut = min(waste rate, max cut), floored at forecast_adj."""
    df = fc_adj.merge(rates, on="item", how="left")
    df["waste_rate_pct"] = df["waste_rate_pct"].fillna(0.0)
    df["waste_cut_pct"] = df["waste_rate_pct"].clip(upper=max(0.0, float(max_cut_pct))).round(1)
    raw = df["forecast_adj"] * (1 + buffer_pct / 100) * (1 - df["waste_cut_pct"] / 100)
    df["planned"] = raw.where(raw > df["forecast_adj"], df["forecast_adj"]).round(1)
    return df


# ------------------------------------------------------------------ 4. ingredients
def ingredient_daily_needs(plan: pd.DataFrame, recipes: pd.DataFrame) -> pd.DataFrame:
    m = plan.merge(recipes, left_on="item", right_on="dish")
    m["need_g"] = m["planned"] * m["grams_per_portion"]
    return m.groupby(["ingredient", "date"])["need_g"].sum().reset_index()


# ------------------------------------------------------------------ 5. stock netting with expiry
def stock_lots(batches: pd.DataFrame | None, stock: pd.DataFrame | None, suppliers: pd.DataFrame) -> pd.DataFrame:
    """ingredient, grams, expiry_date (NaT = no known expiry). Batches if given, else stock.csv totals."""
    if batches is not None and len(batches):
        pack = suppliers.set_index("ingredient")["pack_size_g"]
        b = batches[batches["quantity"] > 0]
        return pd.DataFrame({"ingredient": b["ingredient"].values,
                             "grams": [q * pack.get(i, 0) if u == "pack" else q
                                       for i, q, u in zip(b["ingredient"], b["quantity"], b["unit"])],
                             "expiry_date": pd.to_datetime(b["expiry_date"]).values})
    if stock is not None and len(stock):
        return pd.DataFrame({"ingredient": stock["ingredient"], "grams": stock["on_hand_g"].astype(float),
                             "expiry_date": pd.NaT})
    return pd.DataFrame(columns=["ingredient", "grams", "expiry_date"])


def net_stock(needs: pd.DataFrame, lots: pd.DataFrame, dates: list) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Use stock day by day, soonest expiry first; a lot is usable on days BEFORE its expiry date.

    Returns (daily: ingredient, date, need_g, from_stock_g, short_g) and
            (lost: ingredient, expiry_date, grams) = stock that expires within the week before it is used."""
    daily, lost = [], []
    last = pd.Timestamp(dates[-1])
    for ing in sorted(set(needs["ingredient"]) | set(lots["ingredient"])):
        mine = lots[lots["ingredient"] == ing].sort_values("expiry_date", na_position="last")
        left = [[g, e] for g, e in zip(mine["grams"], mine["expiry_date"])]
        need_by_day = needs[needs["ingredient"] == ing].set_index("date")["need_g"]
        for d in dates:
            need = float(need_by_day.get(d, 0.0))
            ts, got = pd.Timestamp(d), 0.0
            for lot in left:
                if need - got <= 0:
                    break
                if pd.notna(lot[1]) and lot[1] <= ts:
                    continue
                take = min(lot[0], need - got)
                lot[0] -= take
                got += take
            if ing in set(needs["ingredient"]):
                daily.append({"ingredient": ing, "date": d, "need_g": need, "from_stock_g": got, "short_g": need - got})
        for g, e in left:
            if g > 0 and pd.notna(e) and e <= last:
                lost.append({"ingredient": ing, "expiry_date": e.date(), "grams": g})
    return (pd.DataFrame(daily, columns=["ingredient", "date", "need_g", "from_stock_g", "short_g"]),
            pd.DataFrame(lost, columns=["ingredient", "expiry_date", "grams"]))


# ------------------------------------------------------------------ 6. packs + deliveries
def packs_for(grams: float, pack_size_g: float) -> int:
    return int(math.ceil(round(grams, 6) / pack_size_g)) if grams > 0 else 0


def delivery_dates(delivery_days, dates: list) -> list:
    """Dates in the week the supplier delivers. Missing column -> Monday only."""
    names = [d.strip()[:3].title() for d in str(delivery_days or "Mon").split(";") if d.strip()]
    out = [d for d in dates if DAYS[pd.Timestamp(d).weekday()] in names]
    return out or [dates[0]]


def build_week_order(sales, recipes, suppliers, week_start=None, batches=None, stock=None, events=None,
                     buffer_pct=DEFAULT_BUFFER_PCT, max_cut_pct=DEFAULT_MAX_CUT_PCT, weeks=4) -> dict:
    """Everything the page and the assistant need: dish plan, order lines (one per delivery), lost stock."""
    week_start = pd.Timestamp(week_start or next_week_start(sales)).date()
    dates = week_dates(week_start)
    fc = apply_events(forecast_week(sales, week_start, weeks), events, sales)
    rates = waste_rates(sales, week_start)
    plan = plan_dishes(fc, rates, buffer_pct, max_cut_pct)
    needs = ingredient_daily_needs(plan, recipes)
    daily, lost = net_stock(needs, stock_lots(batches, stock, suppliers), dates)
    sup = suppliers.set_index("ingredient")

    lines, summary = [], []
    for ing, d in daily.groupby("ingredient"):
        if ing not in sup.index:
            continue
        s = sup.loc[ing]
        pack = float(s["pack_size_g"])
        lead = int(s.get("lead_time_days", 1) or 1)
        drops = delivery_dates(s.get("delivery_days", "Mon"), dates)
        carry, per_drop = 0.0, []
        for k, drop in enumerate(drops):
            end = drops[k + 1] if k + 1 < len(drops) else None
            window = d[(d["date"] < end) if end else d["date"].notna()] if k == 0 else \
                d[(d["date"] >= drop) & ((d["date"] < end) if end else True)]
            short = float(window["short_g"].sum())
            n = packs_for(short - carry, pack)
            carry = carry + n * pack - short
            per_drop.append((drop, n, window["date"].min(), window["date"].max()))
        dishes = recipes[recipes["ingredient"] == ing]["dish"].tolist()
        dish_fc = plan[plan["item"].isin(dishes)].groupby("item").agg(
            portions=("forecast_adj", "sum"), waste_rate_pct=("waste_rate_pct", "first"),
            waste_cut_pct=("waste_cut_pct", "first"))
        my_lost = lost[lost["ingredient"] == ing]
        total_packs = sum(n for _, n, _, _ in per_drop)
        early = d[d["date"] < drops[0]]
        gap = early[early["short_g"] > 0.5]
        facts = {
            "ingredient": ing, "packs": total_packs, "pack_size_g": int(pack),
            "need_g": int(round(d["need_g"].sum())), "from_stock_g": int(round(d["from_stock_g"].sum())),
            "deliveries": [{"day": DAYS[pd.Timestamp(dr).weekday()], "packs": n} for dr, n, _, _ in per_drop if n],
            "dishes": [{"dish": i, "portions": int(round(r.portions)), "waste_rate_pct": float(r.waste_rate_pct),
                        "waste_cut_pct": float(r.waste_cut_pct)} for i, r in dish_fc.iterrows()],
            "expiring_unused": [{"day": DAYS[pd.Timestamp(e).weekday()], "grams": int(round(g)),
                                 "packs": round(g / pack, 1)} for e, g in zip(my_lost["expiry_date"], my_lost["grams"])],
            "short_before_first_delivery_g": int(round(gap["short_g"].sum())),
            "first_short_day": DAYS[pd.Timestamp(gap["date"].min()).weekday()] if len(gap) else None,
        }
        reason = make_reason(facts)
        summary.append({"ingredient": ing, "supplier": s["supplier"], "storage": s.get("storage", ""),
                        "packs": total_packs, "est_cost_nok": int(total_packs * s["pack_price_nok"]),
                        "need_g": facts["need_g"], "from_stock_g": facts["from_stock_g"], "reason": reason, "facts": facts})
        for drop, n, w0, w1 in per_drop:
            if n == 0:
                continue
            lines.append({"ingredient": ing, "supplier": s["supplier"], "storage": s.get("storage", ""),
                          "delivery_date": drop, "delivery_day": DAYS[pd.Timestamp(drop).weekday()],
                          "order_by": (pd.Timestamp(drop) - pd.Timedelta(days=lead)).date(),
                          "covers": f"{DAYS[pd.Timestamp(w0).weekday()]}-{DAYS[pd.Timestamp(w1).weekday()]}",
                          "packs": n, "pack_size_g": int(pack), "order_g": int(n * pack),
                          "est_cost_nok": int(n * s["pack_price_nok"]), "reason": reason})
    cols = ["ingredient", "supplier", "storage", "delivery_date", "delivery_day", "order_by", "covers",
            "packs", "pack_size_g", "order_g", "est_cost_nok", "reason"]
    lines_df = pd.DataFrame(lines, columns=cols).sort_values(["delivery_date", "supplier", "ingredient"]).reset_index(drop=True)
    return {"week_start": week_start, "dates": dates, "plan": plan, "lines": lines_df,
            "summary": pd.DataFrame(summary), "lost": lost, "buffer_pct": buffer_pct, "max_cut_pct": max_cut_pct,
            "events": list(events or [])}


def make_reason(f: dict) -> str:
    """Plain-language reason built ONLY from the computed facts dict."""
    name = f["ingredient"].replace("_", " ")
    if f["packs"]:
        drops = ", ".join(f"{x['day']} {x['packs']}" for x in f["deliveries"])
        head = f"{name}: {f['packs']} {'pack' if f['packs'] == 1 else 'packs'} ({drops})."
    else:
        head = f"{name}: no order, stock covers the week."
    dishes = "; ".join(f"forecast {d['portions']} {d['dish'].replace('_', ' ')}"
                       + (f", waste {d['waste_rate_pct']:g}% → buffer trimmed {d['waste_cut_pct']:g}%" if d["waste_cut_pct"] else "")
                       for d in f["dishes"])
    parts = [head, dishes + "." if dishes else "",
             f"Need {f['need_g']} g, usable stock {f['from_stock_g']} g."]
    for e in f["expiring_unused"]:
        qty = f"{e['packs']:g} packs ({e['grams']} g)" if e["packs"] >= 0.1 else f"{e['grams']} g"
        parts.append(f"{qty} expire {e['day']} before use (not counted).")
    if f.get("first_short_day"):
        parts.append(f"Runs short from {f['first_short_day']} ({f['short_before_first_delivery_g']} g) before the first delivery.")
    return " ".join(p for p in parts if p)


def reason_numbers_grounded(reason: str, facts: dict) -> list:
    """Numbers in a reason that are not in its facts (should always be empty)."""
    known = set(re.findall(r"\d+(?:\.\d+)?", json.dumps(facts, default=str)))
    known |= {f"{float(k):g}" for k in known}
    return [n for n in re.findall(r"\d+(?:\.\d+)?", reason) if n not in known]


# ------------------------------------------------------------------ 7. approve / save / history
def save_order(result: dict, lines: pd.DataFrame, approved_by: str, folder=None, now=None) -> str:
    """Save an APPROVED order (only called after a person clicks Approve). Returns the order id."""
    if not str(approved_by).strip():
        raise ValueError("an approver role is required")
    folder = pathlib.Path(folder or orders_dir())
    folder.mkdir(parents=True, exist_ok=True)
    now = now or datetime.now()
    oid = f"{result['week_start']}_{now:%Y%m%d%H%M%S}"
    dish_fc = result["plan"].groupby("item")["forecast_adj"].sum().round(1)
    meta = {"id": oid, "week_start": str(result["week_start"]), "approved_by": approved_by.strip(),
            "approved_at": now.isoformat(timespec="seconds"), "buffer_pct": result["buffer_pct"],
            "max_cut_pct": result["max_cut_pct"],
            "events": [{**e, "date": str(e["date"])} for e in result["events"]],
            "packs": int(lines["packs"].sum()) if len(lines) else 0,
            "est_cost_nok": int(lines["est_cost_nok"].sum()) if len(lines) else 0,
            "dish_forecast": {k: float(v) for k, v in dish_fc.items()},
            "lines": json.loads(lines.to_json(orient="records", date_format="iso")), "data_source": "SYNTHETIC"}
    (folder / f"order_{oid}.json").write_text(json.dumps(meta, indent=2))
    lines.to_csv(folder / f"order_{oid}.csv", index=False)
    return oid


def list_orders(folder=None) -> list:
    d = pathlib.Path(folder or orders_dir())
    if not d.exists():
        return []
    return sorted((json.loads(p.read_text()) for p in d.glob("order_*.json")), key=lambda m: m["approved_at"], reverse=True)


def forecast_vs_actual(order: dict, sales: pd.DataFrame) -> pd.DataFrame:
    """Per dish: forecast portions (as approved) vs actual sold that week, where the sales data has it."""
    start = pd.Timestamp(order["week_start"])
    week = sales[(sales["date"] >= start) & (sales["date"] < start + pd.Timedelta(days=7))]
    actual = week.groupby("item")["sold_units"].sum()
    rows = [{"dish": k, "forecast": v, "actual": (int(actual[k]) if k in actual else None)}
            for k, v in order["dish_forecast"].items()]
    df = pd.DataFrame(rows, columns=["dish", "forecast", "actual"])
    df["error_pct"] = [round(100 * (f - a) / a, 1) if a else None for f, a in zip(df["forecast"], df["actual"])]
    df.attrs["days_with_actuals"] = int(week["date"].nunique())
    return df


# ------------------------------------------------------------------ risks (for the assistant)
def risks(result: dict, sales: pd.DataFrame, batches=None, stock=None, suppliers=None) -> dict:
    """Stockout risk before the first delivery, stock expiring unused, recent sold-outs, rising waste."""
    ws = pd.Timestamp(result["week_start"])
    out = {"week_start": str(result["week_start"]), "stockout_before_delivery": [], "expiring_unused": [],
           "recent_sellouts": [], "rising_waste": []}
    for r in result["summary"].itertuples():
        f = r.facts
        if f.get("first_short_day"):
            out["stockout_before_delivery"].append({"ingredient": r.ingredient, "short_from": f["first_short_day"],
                                                    "short_g": f["short_before_first_delivery_g"],
                                                    "first_delivery": f["deliveries"][0]["day"] if f["deliveries"] else None})
        for e in f["expiring_unused"]:
            out["expiring_unused"].append({"ingredient": r.ingredient, **e})
    if "stockout_units" in sales:
        last14 = sales[(sales["date"] < ws) & (sales["date"] >= ws - pd.Timedelta(days=14))]
        so = last14[last14["stockout_units"] > 0].groupby("item")["stockout_units"].agg(["sum", "count"])
        out["recent_sellouts"] = [{"dish": i, "days": int(r["count"]), "portions_short": int(r["sum"])}
                                  for i, r in so.sort_values("sum", ascending=False).iterrows()]
    now = waste_rates(sales, ws, 14).set_index("item")["waste_rate_pct"]
    before = waste_rates(sales, ws - pd.Timedelta(days=14), 14).set_index("item")["waste_rate_pct"]
    for item in now.index:
        if item in before.index and now[item] - before[item] >= 3:
            out["rising_waste"].append({"dish": item, "waste_rate_pct_last_14d": float(now[item]),
                                        "waste_rate_pct_prior_14d": float(before[item])})
    return out
