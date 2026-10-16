import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import pytest
from PIL import Image
import plate_waste as pw

DATA = pathlib.Path(__file__).resolve().parents[2] / "data"
RECIPES = pw.load_recipes(DATA / "recipes.csv")


def test_recipe_math_half_burger():
    g = pw.grams_wasted(RECIPES, "burger", "half")
    assert dict(zip(g.ingredient, g.grams_wasted))["beef_patty"] == 75.0
    assert g.grams_wasted.sum() == pytest.approx(0.5 * g.grams_per_portion.sum())


def test_recipe_math_none_and_unknown():
    assert pw.grams_wasted(RECIPES, "fries", "none").grams_wasted.sum() == 0
    with pytest.raises(ValueError):
        pw.grams_wasted(RECIPES, "pizza", "half")
    with pytest.raises(ValueError):
        pw.grams_wasted(RECIPES, "fries", "60%")


def test_validate_accepts_good_json():
    out = pw.validate_estimate('```json\n{"bucket": "small", "confidence": "medium", "reasoning": "a few fries"}\n```')
    assert out["bucket"] == "small"


@pytest.mark.parametrize("bad", [
    "not json", "[1,2]", '{"bucket": "40%", "confidence": "high"}',
    '{"bucket": "half", "confidence": "very"}', '{"confidence": "low"}',
    '{"bucket": "half", "confidence": "low", "reasoning": 5}',
])
def test_validate_rejects_bad_json(bad):
    with pytest.raises(ValueError):
        pw.validate_estimate(bad)


def test_heuristic_orders_sample_plates():
    order = ["empty", "small_leftover", "half_left", "most_left", "untouched"]
    est = [pw.heuristic_estimate(Image.open(DATA / "sample_plates" / f"{n}.png")) for n in order]
    values = [e["leftover_estimate"] for e in est]
    assert values == sorted(values) and values[0] < values[-1]
    assert est[0]["bucket"] == "none" and est[-1]["bucket"] == "untouched"
    assert all("demo only" in e["reasoning"] for e in est)
