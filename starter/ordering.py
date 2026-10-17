"""Supplier order suggestions (pure logic, no Streamlit).

Order per ingredient = forecast portions x recipe grams over the next N days (+ buffer)
                       - current stock, rounded UP to whole supplier packs.
Suggestions only: nothing is ever sent to a supplier.
"""
import math

import pandas as pd


def forecast_next_days(sales: pd.DataFrame, start, days: int = 3, weeks: int = 4) -> pd.DataFrame:
    """Forecast portions per item for each of the next `days` days.

    For each future date we average the same weekday over the last `weeks` weeks
    of history BEFORE `start` (we never peek at data we wouldn't have yet)."""
    start = pd.Timestamp(start)
    history = sales[sales["date"] < start]
    rows = []
    for i in range(days):
        day = start + pd.Timedelta(days=i)
        same_wd = history[history["date"].dt.weekday == day.weekday()]
        recent_dates = sorted(same_wd["date"].unique())[-weeks:]
        recent = same_wd[same_wd["date"].isin(recent_dates)]
        for item, mean in recent.groupby("item")["sold_units"].mean().items():
            rows.append({"date": day.date(), "item": item, "forecast": round(float(mean), 1)})
    return pd.DataFrame(rows, columns=["date", "item", "forecast"])


def ingredient_needs(forecast: pd.DataFrame, recipes: pd.DataFrame, buffer_pct: float = 10) -> pd.DataFrame:
    """Total grams needed per ingredient = sum(portions x grams per portion) x (1 + buffer)."""
    portions = forecast.groupby("item")["forecast"].sum().rename("portions").reset_index()
    merged = recipes.merge(portions, left_on="dish", right_on="item")
    merged["needed_g"] = merged["portions"] * merged["grams_per_portion"] * (1 + buffer_pct / 100)
    return merged.groupby("ingredient")["needed_g"].sum().round(0).reset_index()


def suggest_order(needs: pd.DataFrame, stock: pd.DataFrame, suppliers: pd.DataFrame) -> pd.DataFrame:
    """Compare needs with stock and round the shortfall up to supplier packs."""
    df = needs.merge(stock, on="ingredient", how="left").merge(suppliers, on="ingredient", how="left")
    df["on_hand_g"] = df["on_hand_g"].fillna(0)
    df["shortfall_g"] = (df["needed_g"] - df["on_hand_g"]).clip(lower=0)
    df["packs"] = [math.ceil(s / p) if s > 0 else 0 for s, p in zip(df["shortfall_g"], df["pack_size_g"])]
    df["order_g"] = df["packs"] * df["pack_size_g"]
    df["est_cost_nok"] = df["packs"] * df["pack_price_nok"]
    df["why"] = [
        f"need {n:,.0f} g, have {h:,.0f} g → short {s:,.0f} g → {k} × {p:,.0f} g pack(s)" if k
        else f"need {n:,.0f} g, have {h:,.0f} g → enough stock"
        for n, h, s, k, p in zip(df["needed_g"], df["on_hand_g"], df["shortfall_g"], df["packs"], df["pack_size_g"])
    ]
    cols = ["ingredient", "supplier", "needed_g", "on_hand_g", "shortfall_g", "pack_size_g",
            "packs", "order_g", "est_cost_nok", "lead_time_days", "why"]
    return df[cols].sort_values(["packs", "ingredient"], ascending=[False, True]).reset_index(drop=True)


def order_suggestions(sales, recipes, stock, suppliers, start, days=3, weeks=4, buffer_pct=10):
    """Convenience wrapper used by the Ordering page and the assistant."""
    fc = forecast_next_days(sales, start, days, weeks)
    return suggest_order(ingredient_needs(fc, recipes, buffer_pct), stock, suppliers)
