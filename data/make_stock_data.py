"""Generate SYNTHETIC stock batches + shelf illustrations. Not real data.

Writes:
- stock_batches.csv : batch_id, ingredient, location, quantity, unit, received_date, expiry_date, data_source
  unit is "pack" (counted by shelf camera; grams = packs x supplier pack size) or "g" (weighed on a scale).
- stock.csv         : on_hand_g per ingredient = sum of batches (kept in sync for the CSV fallback)
- shelf_samples/<location>.png + manifest.json : drawn shelves with coloured packs and the drawn counts

Assumptions (invented): demo "today" = 2026-07-06 (day after the synthetic sales end); shelf lives below;
target grams per ingredient come from the original stock.csv values in TARGET_G.
Run: python data/make_stock_data.py
"""
import json
import pathlib
from datetime import date, timedelta

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw

HERE = pathlib.Path(__file__).resolve().parent
TODAY = date(2026, 7, 6)
SEED = 7

# ingredient: (location, unit, shelf_life_days, target_grams)
ITEMS = {
    "white_fish": ("walk-in fridge", "g", 3, 3000), "potato": ("dry store", "g", 21, 12000),
    "cream": ("walk-in fridge", "pack", 7, 5000), "leek": ("back fridge", "g", 7, 800),
    "beef_patty": ("freezer", "pack", 90, 9000), "bun": ("dry store", "pack", 4, 6400),
    "cheese": ("walk-in fridge", "pack", 21, 3000), "lettuce_tomato": ("back fridge", "pack", 3, 4000),
    "chickpeas": ("dry store", "pack", 365, 7500), "rice": ("dry store", "pack", 365, 10000),
    "vegetables": ("back fridge", "g", 5, 1200), "coconut_sauce": ("dry store", "pack", 180, 4000),
    "romaine": ("back fridge", "pack", 4, 3000), "chicken": ("walk-in fridge", "g", 4, 1500),
    "croutons": ("dry store", "pack", 60, 3000), "dressing": ("walk-in fridge", "pack", 30, 3000),
    "bread": ("dry store", "g", 2, 3000), "butter": ("walk-in fridge", "pack", 30, 2000),
    "cake": ("freezer", "pack", 60, 4400), "mixed_fruit": ("back fridge", "g", 3, 1500),
}
LOCATIONS = ["dry store", "walk-in fridge", "back fridge", "freezer"]

# Pack colours for the drawn shelves (only need to be distinct within one location)
PALETTE = {
    "bun": (240, 170, 40), "chickpeas": (120, 200, 80), "rice": (80, 140, 230),
    "coconut_sauce": (180, 90, 200), "croutons": (230, 90, 60),
    "cream": (100, 200, 220), "cheese": (250, 210, 0), "dressing": (60, 160, 120), "butter": (250, 240, 140),
    "lettuce_tomato": (220, 40, 90), "romaine": (40, 120, 40),
    "cake": (200, 100, 160), "beef_patty": (170, 30, 30),
}


def make_batches(suppliers: pd.DataFrame) -> pd.DataFrame:
    rng = np.random.default_rng(SEED)
    pack = suppliers.set_index("ingredient")["pack_size_g"]
    rows, n = [], 1
    for ing, (loc, unit, life, target) in ITEMS.items():
        total = max(1, round(target / pack[ing])) if unit == "pack" else target
        older = total // 3 if unit == "pack" else round(total * 0.4)
        parts = [p for p in (older, total - older) if p > 0]
        for i, qty in enumerate(parts):
            age = int(rng.integers(max(1, life // 2), life)) if i == 0 and len(parts) > 1 else int(rng.integers(0, 2))
            received = TODAY - timedelta(days=min(age, life - 1))
            rows.append({"batch_id": f"B{n:03d}", "ingredient": ing, "location": loc, "quantity": qty, "unit": unit,
                         "received_date": received.isoformat(), "expiry_date": (received + timedelta(days=life)).isoformat(),
                         "data_source": "SYNTHETIC"})
            n += 1
    return pd.DataFrame(rows)


def draw_shelf(location: str, counts: dict) -> Image.Image:
    W, H = 640, 420
    img = Image.new("RGB", (W, H), (235, 235, 235))
    d = ImageDraw.Draw(img)
    shelf_y = [130, 260, 390]
    for y in shelf_y:
        d.rectangle([20, y, W - 20, y + 8], fill=(110, 80, 50))          # shelf boards
    x, row = 30, 0
    for item, count in counts.items():
        if x + 60 * max(count, 1) > W - 20:
            x, row = 30, row + 1
        y_bottom = shelf_y[row]
        d.text((x, y_bottom - 82), item, fill=(0, 0, 0))
        for _ in range(count):
            d.rectangle([x, y_bottom - 62, x + 44, y_bottom - 4], fill=PALETTE[item])  # one pack
            x += 54
        x += 30
    d.text((20, 8), f"SYNTHETIC ILLUSTRATION - {location} shelf, not a photo", fill=(0, 0, 0))
    return img


if __name__ == "__main__":
    suppliers = pd.read_csv(HERE / "suppliers.csv")
    batches = make_batches(suppliers)
    batches.to_csv(HERE / "stock_batches.csv", index=False)
    pack = suppliers.set_index("ingredient")["pack_size_g"]
    grams = batches.apply(lambda r: r.quantity * (pack[r.ingredient] if r.unit == "pack" else 1), axis=1)
    stock = batches.assign(on_hand_g=grams).groupby("ingredient", sort=False)["on_hand_g"].sum().reset_index()
    stock.to_csv(HERE / "stock.csv", index=False)

    out = HERE / "shelf_samples"
    out.mkdir(exist_ok=True)
    manifest = {}
    for loc in LOCATIONS:
        recorded = batches[(batches.location == loc) & (batches.unit == "pack")].groupby("ingredient")["quantity"].sum()
        # the drawn shelf differs a little from the records so the demo shows a correction
        drawn = {ing: int(q) for ing, q in recorded.items()}
        first = next(iter(drawn), None)
        if first and drawn[first] > 1:
            drawn[first] -= 1
        draw_shelf(loc, drawn).save(out / f"{loc.replace(' ', '_')}.png")
        manifest[loc] = drawn
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"wrote {len(batches)} batches, stock.csv, {len(LOCATIONS)} shelf images")
