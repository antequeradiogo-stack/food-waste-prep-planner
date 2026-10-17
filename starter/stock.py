"""Stock batches: on-hand grams, expiry, 'use first', and applying confirmed counts/readings.

A batch has a quantity in a unit: "pack" (grams = packs x supplier pack size) or "g".
When stock goes DOWN we take it from the oldest batch first (FIFO); when it goes UP we add to the newest.
"""
import pandas as pd

LOCATIONS = ["dry store", "walk-in fridge", "back fridge", "freezer"]


def load_batches(path) -> pd.DataFrame:
    b = pd.read_csv(path, parse_dates=["received_date", "expiry_date"])
    b["quantity"] = b["quantity"].astype(float)   # allow partial updates
    return b


def with_grams(batches: pd.DataFrame, suppliers: pd.DataFrame) -> pd.DataFrame:
    pack = suppliers.set_index("ingredient")["pack_size_g"]
    b = batches.copy()
    b["grams"] = [q * pack.get(i, 0) if u == "pack" else q for i, q, u in zip(b.ingredient, b.quantity, b.unit)]
    return b


def on_hand(batches: pd.DataFrame, suppliers: pd.DataFrame) -> pd.DataFrame:
    """Same shape as stock.csv: ingredient, on_hand_g."""
    b = with_grams(batches, suppliers)
    return b.groupby("ingredient", sort=False)["grams"].sum().rename("on_hand_g").reset_index()


def by_location(batches: pd.DataFrame, suppliers: pd.DataFrame) -> pd.DataFrame:
    b = with_grams(batches, suppliers)
    return (b.groupby(["location", "ingredient", "unit"])
             .agg(quantity=("quantity", "sum"), grams=("grams", "sum"), next_expiry=("expiry_date", "min"))
             .reset_index())


def expiring(batches: pd.DataFrame, today, days: int = 2) -> pd.DataFrame:
    """Batches whose expiry date is within `days` days of `today` (incl. already expired), soonest first."""
    today = pd.Timestamp(today)
    b = batches[batches["quantity"] > 0].copy()
    b["days_left"] = (b["expiry_date"] - today).dt.days
    return b[b["days_left"] <= days].sort_values(["days_left", "ingredient"]).reset_index(drop=True)


def use_first(expiring_batches: pd.DataFrame, recipes: pd.DataFrame) -> pd.DataFrame:
    """For each expiring ingredient, the dishes that use it (so the kitchen can push those dishes)."""
    dishes = recipes.groupby("ingredient")["dish"].apply(lambda d: ", ".join(sorted(d))).rename("use_in_dishes")
    out = expiring_batches.merge(dishes, left_on="ingredient", right_index=True, how="left")
    out["use_in_dishes"] = out["use_in_dishes"].fillna("(not on the menu)")
    return out


def set_total(batches: pd.DataFrame, ingredient: str, location: str, new_qty: float):
    """Set the total quantity (in the batch unit) for one ingredient at one location.

    Returns (new_batches, change_text). Decreases come out of the oldest batches first (FIFO)."""
    b = batches.copy()
    mask = (b.ingredient == ingredient) & (b.location == location)
    if not mask.any():
        raise ValueError(f"no {ingredient} batches recorded in {location}")
    idx = b[mask].sort_values("received_date").index.tolist()   # oldest first
    old = float(b.loc[idx, "quantity"].sum())
    diff = float(new_qty) - old
    if diff >= 0:
        b.loc[idx[-1], "quantity"] += diff                        # add to the newest batch
    else:
        remove = -diff
        for i in idx:                                             # FIFO: take from the oldest
            take = min(remove, b.loc[i, "quantity"])
            b.loc[i, "quantity"] -= take
            remove -= take
            if remove <= 0:
                break
    unit = b.loc[idx[0], "unit"]
    return b, f"{ingredient} @ {location}: {old:g} → {float(new_qty):g} {unit}"


def grams_to_quantity(batches, suppliers, ingredient, location, grams: float) -> float:
    """Convert a scale reading in grams into the batch unit (packs are rounded to the nearest whole pack)."""
    unit = batches[(batches.ingredient == ingredient) & (batches.location == location)]["unit"].iloc[0]
    if unit == "g":
        return round(float(grams))
    pack = float(suppliers.set_index("ingredient").loc[ingredient, "pack_size_g"])
    return round(float(grams) / pack)
