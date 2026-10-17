import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import pandas as pd
import core
import ordering

DATA = pathlib.Path(__file__).resolve().parents[2] / "data"


def test_order_math_rounds_up_to_packs():
    needs = pd.DataFrame({"ingredient": ["fish", "rice"], "needed_g": [4500.0, 1000.0]})
    stock = pd.DataFrame({"ingredient": ["fish", "rice"], "on_hand_g": [1000, 3000]})
    sup = pd.DataFrame({"ingredient": ["fish", "rice"], "supplier": ["A", "B"], "pack_size_g": [2000, 5000],
                        "pack_price_nok": [100, 50], "lead_time_days": [1, 3]})
    o = ordering.suggest_order(needs, stock, sup).set_index("ingredient")
    assert o.loc["fish", "shortfall_g"] == 3500 and o.loc["fish", "packs"] == 2      # 3500 g -> 2 x 2000 g
    assert o.loc["fish", "order_g"] == 4000 and o.loc["fish", "est_cost_nok"] == 200
    assert o.loc["rice", "packs"] == 0 and "enough stock" in o.loc["rice", "why"]


def test_ingredient_needs_uses_recipe_grams_and_buffer():
    fc = pd.DataFrame({"date": ["d1", "d2"], "item": ["fries", "fries"], "forecast": [10.0, 10.0]})
    rec = pd.DataFrame({"dish": ["fries"], "ingredient": ["potato"], "grams_per_portion": [180]})
    n = ordering.ingredient_needs(fc, rec, buffer_pct=10)
    assert n.loc[0, "needed_g"] == round(20 * 180 * 1.1)


def test_forecast_next_days_no_peeking():
    sales = core.load_data(DATA / "synthetic_restaurant_daily.csv")
    start = sales["date"].max() - pd.Timedelta(days=13)     # pretend we're two weeks back
    fc = ordering.forecast_next_days(sales, start, days=3, weeks=4)
    assert fc["date"].nunique() == 3 and fc["item"].nunique() == 8
    # first day's forecast for one item equals the mean of the last 4 same weekdays before start
    day = pd.Timestamp(start); item = "burger"
    hist = sales[(sales.date < day) & (sales.date.dt.weekday == day.weekday()) & (sales.item == item)].tail(4)
    got = fc[(fc.date == day.date()) & (fc.item == item)]["forecast"].iloc[0]
    assert got == round(hist.sold_units.mean(), 1)


def test_synthetic_inventory_files_cover_all_recipe_ingredients():
    rec = pd.read_csv(DATA / "recipes.csv"); stock = pd.read_csv(DATA / "stock.csv"); sup = pd.read_csv(DATA / "suppliers.csv")
    assert set(rec.ingredient) <= set(stock.ingredient) and set(rec.ingredient) <= set(sup.ingredient)
    assert sup.supplier.str.contains("fictional").all()
