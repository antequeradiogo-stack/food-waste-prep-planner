import json, pathlib, sys
from types import SimpleNamespace as NS
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import pandas as pd
import pytest
from PIL import Image
import assistant, core, scales, shelf
import stock as stock_mod

DATA = pathlib.Path(__file__).resolve().parents[2] / "data"
SUP = pd.read_csv(DATA / "suppliers.csv")
REC = pd.read_csv(DATA / "recipes.csv")
TODAY = "2026-07-06"


@pytest.fixture
def batches():
    return stock_mod.load_batches(DATA / "stock_batches.csv")


# ---------- stock ----------
def test_stock_csv_matches_batches(batches):
    csv = pd.read_csv(DATA / "stock.csv").set_index("ingredient")["on_hand_g"]
    agg = stock_mod.on_hand(batches, SUP).set_index("ingredient")["on_hand_g"]
    assert (csv.sort_index() == agg.sort_index()).all()
    assert (batches.data_source == "SYNTHETIC").all() and set(batches.location) <= set(stock_mod.LOCATIONS)


def test_expiring_and_use_first(batches):
    e = stock_mod.expiring(batches, TODAY, 2)
    assert (e.days_left <= 2).all() and list(e.days_left) == sorted(e.days_left)
    u = stock_mod.use_first(e, REC).set_index("ingredient")
    assert "fish_soup" in u.loc[["white_fish"], "use_in_dishes"].iloc[0]


def test_set_total_takes_from_oldest_first(batches):
    fish = batches[batches.ingredient == "white_fish"].sort_values("received_date")
    old_id, new_id = fish.batch_id.iloc[0], fish.batch_id.iloc[-1]
    new, text = stock_mod.set_total(batches, "white_fish", "walk-in fridge", 2000)    # 3000 -> 2000
    q = new.set_index("batch_id")["quantity"]
    assert q[old_id] == 200 and q[new_id] == 1800 and "3000 → 2000" in text
    up, _ = stock_mod.set_total(batches, "white_fish", "walk-in fridge", 3500)
    assert up.set_index("batch_id")["quantity"][new_id] == 2300                       # added to newest
    with pytest.raises(ValueError):
        stock_mod.set_total(batches, "white_fish", "freezer", 1)


def test_grams_to_quantity(batches):
    assert stock_mod.grams_to_quantity(batches, SUP, "cream", "walk-in fridge", 2600) == 3    # 1000 g packs
    assert stock_mod.grams_to_quantity(batches, SUP, "leek", "back fridge", 812.4) == 812


# ---------- shelf ----------
def test_shelf_heuristic_matches_drawn_counts(batches):
    manifest = json.loads((DATA / "shelf_samples" / "manifest.json").read_text())
    for loc, drawn in manifest.items():
        img = Image.open(DATA / "shelf_samples" / f"{loc.replace(' ', '_')}.png")
        got = {c["item"]: c["count"] for c in shelf.heuristic_count(img, shelf.pack_items_at(batches, loc))}
        assert got == drawn, loc


def test_validate_counts_accepts_good():
    out = shelf.validate_counts('```json\n{"items": [{"item": "rice", "count": 2, "confidence": "high"}]}\n```', {"rice"})
    assert out == [{"item": "rice", "count": 2, "confidence": "high"}]


@pytest.mark.parametrize("bad", [
    "nope", '{"x": 1}', '[{"item": "caviar", "count": 1, "confidence": "low"}]',
    '[{"item": "rice", "count": -1, "confidence": "low"}]', '[{"item": "rice", "count": 2.5, "confidence": "low"}]',
    '[{"item": "rice", "count": true, "confidence": "low"}]', '[{"item": "rice", "count": 999, "confidence": "low"}]',
    '[{"item": "rice", "count": 1, "confidence": "sure"}]',
    '[{"item": "rice", "count": 1, "confidence": "low"}, {"item": "rice", "count": 2, "confidence": "low"}]',
])
def test_validate_counts_rejects_bad(bad):
    with pytest.raises(ValueError):
        shelf.validate_counts(bad, {"rice", "bun"})


def fake_vision(text):
    return NS(chat=NS(completions=NS(create=lambda **kw: NS(choices=[NS(message=NS(content=text))]))))


def test_estimate_counts_llm_and_fallback(batches):
    img = Image.open(DATA / "shelf_samples" / "freezer.png")
    items = shelf.pack_items_at(batches, "freezer")
    ok = shelf.estimate_counts(img, "freezer", items, client=fake_vision('[{"item": "cake", "count": 2, "confidence": "medium"}]'))
    assert ok["source"].startswith("vision LLM") and ok["counts"][0]["count"] == 2
    bad = shelf.estimate_counts(img, "freezer", items, client=fake_vision('[{"item": "pizza", "count": 9, "confidence": "high"}]'))
    assert "heuristic" in bad["source"] and {c["item"] for c in bad["counts"]} == set(items)


# ---------- scales ----------
def test_unit_conversion():
    assert scales.to_grams(1.5, "kg") == 1500 and scales.to_grams(1, "lb") == 453.6 and scales.to_grams(250, "G") == 250
    with pytest.raises(ValueError):
        scales.to_grams(1, "stone")
    with pytest.raises(ValueError):
        scales.to_grams("heavy", "kg")


@pytest.mark.parametrize("line,grams,stable", [
    ("ST,GS,+  1.234kg", 1234.0, True), ("US,NT,-  0.500kg", -500.0, False),
    ("ST,GS,+   850g", 850.0, True), ("ST,NT,+ 2.00lb", 907.2, True),
])
def test_parse_ascii_line(line, grams, stable):
    r = scales.parse_ascii_line(line)
    assert r["grams"] == grams and r["stable"] is stable


@pytest.mark.parametrize("line", ["OL,GS,+ 9.999kg", "hello", "", "ST,GS,+ 1.2 tons"])
def test_parse_ascii_line_rejects(line):
    with pytest.raises(ValueError):
        scales.parse_ascii_line(line)


def test_http_pull_with_fake_fetch_and_validation():
    payload = json.dumps(scales.PUSH_PAYLOAD_EXAMPLE).encode()
    r = scales.HttpJsonScale("https://gw.example/readings", fetch=lambda url, timeout: payload).read()
    assert r[0].grams == 2850 and r[0].ingredient == "white_fish" and r[0].source.startswith("http:")
    with pytest.raises(ValueError):
        scales.HttpJsonScale("ftp://x")
    with pytest.raises(ValueError):
        scales.HttpJsonScale("https://gw", fetch=lambda u, t: b'{"readings": [{"scale_id": "a"}]}').read()


def test_csv_import():
    text = "scale_id,location,ingredient,value,unit,timestamp\ns1,back fridge,leek,0.75,kg,2026-07-06T10:00\n"
    r = scales.parse_csv(text)
    assert r[0].grams == 750 and r[0].source == "csv import"
    with pytest.raises(ValueError):
        scales.parse_csv("a,b\n1,2\n")


def test_plausibility_flags():
    R = lambda g: scales.Reading("s", "back fridge", "leek", g, "", "t")
    assert scales.check_plausibility(R(800), 790) == []
    assert "negative weight" in scales.check_plausibility(R(-5), 800)
    assert any("above max" in f for f in scales.check_plausibility(R(60000), None, max_grams=50000))
    assert any("sudden change" in f for f in scales.check_plausibility(R(200), 800))


def test_simulated_scale_is_deterministic_and_includes_one_odd_reading():
    rec = {("leek", "back fridge"): 800.0, ("bread", "dry store"): 3000.0, ("rice", "dry store"): 5000.0}
    a, b = scales.SimulatedScale(rec).read(), scales.SimulatedScale(rec).read()
    assert a == b
    flagged = [r for r in a if scales.check_plausibility(r, rec[(r.ingredient, r.location)])]
    assert len(flagged) == 1


# ---------- assistant ----------
@pytest.fixture
def data(batches):
    sales = core.load_data(DATA / "synthetic_restaurant_daily.csv")
    return assistant.AppData(sales, REC, stock_mod.on_hand(batches, SUP), SUP,
                             (sales.date.max() + pd.Timedelta(days=1)).date(), [], batches)


@pytest.mark.parametrize("q,tool", [
    ("What expires in the next 2 days?", "get_expiring_items"),
    ("What should we use first?", "get_use_first_advice"),
    ("What's in stock in the walk-in fridge?", "get_stock_levels"),
    ("How much is in the back fridge?", "get_stock_levels"),
    ("What should I order for the next 3 days?", "get_order_suggestions"),
])
def test_stock_intents_grounded(q, tool, data):
    r = assistant.answer_offline(q, data)
    assert r["tools"][0]["name"] == tool and "Why:" in r["text"]
    assert assistant.ungrounded_numbers(r["text"], [t["result"] for t in r["tools"]], q) == []


def test_stock_levels_location_filter(data):
    r = assistant.tool_stock_levels(data, "back fridge")
    assert r["items"] and {i["location"] for i in r["items"]} == {"back fridge"}
    assert assistant.answer_offline("How much is in the back fridge?", data)["tools"][0]["args"]["location"] == "back fridge"


def test_llm_can_call_expiry_tool(data):
    class Fake:
        def __init__(self):
            self.n = 0
            self.chat = NS(completions=NS(create=self.create))
        def create(self, **kw):
            self.n += 1
            if self.n == 1:
                c = NS(id="c1", function=NS(name="get_expiring_items", arguments='{"days": 2}'))
                return NS(choices=[NS(message=NS(content="", tool_calls=[c]))])
            return NS(choices=[NS(message=NS(content="White fish expires 2026-07-07. Why: get_expiring_items", tool_calls=None))])
    r = assistant.answer("expiring?", data, client=Fake())
    assert r["mode"] == "llm" and r["tools"][0]["name"] == "get_expiring_items" and "⚠️" not in r["text"]
