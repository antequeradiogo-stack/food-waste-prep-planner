"""Generate a SYNTHETIC restaurant daily sales / stock / waste dataset.

THIS DATA IS FAKE. It is not from any real restaurant and must not be presented as real
measurements. Assumptions (all invented, chosen only to make a realistic-looking demo):
- One fictional restaurant, 8 menu items, 182 days starting 2026-01-05 (a Monday).
- Base daily demand per item is a made-up number; weekday multipliers make Fri/Sat busier
  and Mon quieter; a few random "events" days boost demand; noise is Poisson.
- Kitchen preps each item each morning using a naive rule (last week's same-day sales + 15%),
  so there is visible over/under-prep for a forecast to improve on.
- Wasted = prepared - sold when positive (unsold perishable portions). Sold is capped by prepared;
  the gap is recorded as `stockout_units` (estimated missed demand).
- Unit cost is a made-up per-portion cost in NOK.
Usage: python generate_synthetic_restaurant_data.py [--seed 42] [--days 182] [--out synthetic_restaurant_daily.csv]
"""
import argparse
import numpy as np
import pandas as pd

ITEMS = {  # item: (base_daily_demand, unit_cost_nok, category)
    "fish_soup": (18, 45, "main"), "burger": (30, 38, "main"), "veg_curry": (14, 30, "main"),
    "caesar_salad": (16, 28, "starter"), "bread_basket": (40, 6, "side"),
    "fries": (35, 8, "side"), "chocolate_cake": (12, 22, "dessert"), "fruit_salad": (9, 18, "dessert"),
}
WEEKDAY_MULT = [0.7, 0.8, 0.9, 1.0, 1.35, 1.5, 1.1]  # Mon..Sun (invented)


def generate(seed=42, days=182, start="2026-01-05"):
    rng = np.random.default_rng(seed)
    dates = pd.date_range(start, periods=days, freq="D")
    event_days = set(rng.choice(days, size=max(1, days // 20), replace=False))
    rows, history = [], {}
    for d_i, date in enumerate(dates):
        boost = 1.4 if d_i in event_days else 1.0
        for item, (base, cost, cat) in ITEMS.items():
            demand = int(rng.poisson(base * WEEKDAY_MULT[date.weekday()] * boost))
            last_week = history.get((item, d_i - 7))
            prepared = int(round((last_week if last_week is not None else base) * 1.15))
            sold = min(demand, prepared)
            history[(item, d_i)] = sold
            rows.append({"date": date.date().isoformat(), "weekday": date.day_name(), "item": item,
                         "category": cat, "prepared_units": prepared, "sold_units": sold,
                         "wasted_units": prepared - sold, "stockout_units": demand - sold,
                         "unit_cost_nok": cost, "special_event": d_i in event_days,
                         "data_source": "SYNTHETIC"})
    return pd.DataFrame(rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--days", type=int, default=182)
    ap.add_argument("--out", default="synthetic_restaurant_daily.csv")
    a = ap.parse_args()
    df = generate(a.seed, a.days)
    df.to_csv(a.out, index=False)
    print(f"wrote {len(df)} rows -> {a.out} (SYNTHETIC, seed={a.seed})")
