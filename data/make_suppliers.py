"""Write SYNTHETIC data/suppliers.csv (fictional suppliers). Not real data.

Columns: ingredient, supplier, pack_size_g, pack_price_nok, lead_time_days, storage, delivery_days
- storage: "fresh" (chilled, short life) or "dry"/"frozen" (long life). Invented per ingredient.
- delivery_days: weekdays the fictional supplier delivers, ";"-separated. Fresh items arrive twice a week
  (Mon;Thu), long-life items once a week (Mon). Lead time = days between ordering and delivery.
All values are invented for the demo. Run: python data/make_suppliers.py
"""
import pathlib

import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
FRESH, WEEKLY = "Mon;Thu", "Mon"

# ingredient: (supplier, pack_size_g, pack_price_nok, lead_time_days, storage)
ROWS = {
    "white_fish": ("Fish supplier (fictional)", 2000, 420, 1, "fresh"),
    "potato": ("Produce supplier (fictional)", 10000, 180, 1, "dry"),
    "cream": ("Dairy supplier (fictional)", 1000, 55, 1, "fresh"),
    "leek": ("Produce supplier (fictional)", 1000, 45, 1, "fresh"),
    "beef_patty": ("Butcher (fictional)", 3000, 390, 2, "frozen"),
    "bun": ("Bakery (fictional)", 1600, 60, 1, "fresh"),
    "cheese": ("Dairy supplier (fictional)", 1000, 120, 1, "fresh"),
    "lettuce_tomato": ("Produce supplier (fictional)", 2000, 70, 1, "fresh"),
    "chickpeas": ("Dry goods (fictional)", 2500, 60, 3, "dry"),
    "rice": ("Dry goods (fictional)", 5000, 95, 3, "dry"),
    "vegetables": ("Produce supplier (fictional)", 5000, 150, 1, "fresh"),
    "coconut_sauce": ("Dry goods (fictional)", 2000, 80, 3, "dry"),
    "romaine": ("Produce supplier (fictional)", 1500, 65, 1, "fresh"),
    "chicken": ("Butcher (fictional)", 2500, 260, 2, "fresh"),
    "croutons": ("Bakery (fictional)", 1000, 50, 2, "dry"),
    "dressing": ("Dry goods (fictional)", 1000, 70, 3, "dry"),
    "bread": ("Bakery (fictional)", 2000, 70, 1, "fresh"),
    "butter": ("Dairy supplier (fictional)", 500, 45, 1, "fresh"),
    "cake": ("Bakery (fictional)", 2200, 240, 2, "frozen"),
    "mixed_fruit": ("Produce supplier (fictional)", 3000, 150, 1, "fresh"),
}


def build() -> pd.DataFrame:
    rows = [{"ingredient": i, "supplier": s, "pack_size_g": p, "pack_price_nok": c, "lead_time_days": l,
             "storage": st, "delivery_days": FRESH if st == "fresh" else WEEKLY}
            for i, (s, p, c, l, st) in ROWS.items()]
    return pd.DataFrame(rows)


if __name__ == "__main__":
    build().to_csv(HERE / "suppliers.csv", index=False)
    print(f"wrote {len(ROWS)} suppliers rows")
