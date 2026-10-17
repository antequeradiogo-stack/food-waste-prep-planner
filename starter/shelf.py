"""Shelf camera: estimate how many PACKS of each item are on a shelf.

Backends:
  1. Vision LLM (optional, LLM_API_KEY): strict JSON list of {item, count, confidence}; validated.
  2. Demo heuristic (offline): counts coloured rectangles in the bundled SYNTHETIC shelf illustrations.
     It only works on those drawings — on real photos it finds nothing and staff count by hand.
Cameras count packs. They can't tell how full a sack or carton is (use a scale) and can't read expiry dates.
"""
import base64
import io
import json
import os

import numpy as np
from PIL import Image

# Must match data/make_stock_data.py
PALETTE = {
    "bun": (240, 170, 40), "chickpeas": (120, 200, 80), "rice": (80, 140, 230),
    "coconut_sauce": (180, 90, 200), "croutons": (230, 90, 60),
    "cream": (100, 200, 220), "cheese": (250, 210, 0), "dressing": (60, 160, 120), "butter": (250, 240, 140),
    "lettuce_tomato": (220, 40, 90), "romaine": (40, 120, 40),
    "cake": (200, 100, 160), "beef_patty": (170, 30, 30),
}
CONFIDENCES = {"low", "medium", "high"}
MAX_COUNT = 200


def pack_items_at(batches, location: str) -> list:
    b = batches[(batches.location == location) & (batches.unit == "pack")]
    return sorted(b.ingredient.unique())


def _count_blobs(mask: np.ndarray, min_pixels: int) -> int:
    """Count connected regions in a True/False mask (simple flood fill, 4-neighbours)."""
    seen = np.zeros_like(mask, dtype=bool)
    h, w = mask.shape
    blobs = 0
    for y, x in zip(*np.nonzero(mask)):
        if seen[y, x]:
            continue
        stack, size = [(y, x)], 0
        seen[y, x] = True
        while stack:
            cy, cx = stack.pop()
            size += 1
            for ny, nx in ((cy + 1, cx), (cy - 1, cx), (cy, cx + 1), (cy, cx - 1)):
                if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not seen[ny, nx]:
                    seen[ny, nx] = True
                    stack.append((ny, nx))
        if size >= min_pixels:
            blobs += 1
    return blobs


def heuristic_count(image: Image.Image, items: list) -> list:
    """DEMO HEURISTIC: count rectangles of each item's colour. Only meaningful on the synthetic shelves."""
    px = np.asarray(image.convert("RGB")).astype(int)[::2, ::2]       # half resolution is enough
    out = []
    for item in items:
        if item not in PALETTE:
            continue
        mask = (np.abs(px - np.array(PALETTE[item])).max(axis=2) <= 12)
        out.append({"item": item, "count": _count_blobs(mask, min_pixels=50), "confidence": "low"})
    return out


def validate_counts(raw, known_items) -> list:
    """Accept only a JSON list (or {"items": [...]}) of {item, count, confidence} with known items."""
    if isinstance(raw, str):
        text = raw.strip()
        if text.startswith("```"):
            text = text.strip("`").removeprefix("json").strip()
        try:
            raw = json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f"not valid JSON: {e}")
    if isinstance(raw, dict):
        raw = raw.get("items")
    if not isinstance(raw, list):
        raise ValueError("expected a list of {item, count, confidence}")
    out, seen = [], set()
    for row in raw:
        if not isinstance(row, dict):
            raise ValueError("each entry must be an object")
        item, count, conf = row.get("item"), row.get("count"), row.get("confidence")
        if item not in known_items:
            raise ValueError(f"unknown item: {item!r}")
        if item in seen:
            raise ValueError(f"duplicate item: {item}")
        if isinstance(count, bool) or not isinstance(count, int) or not 0 <= count <= MAX_COUNT:
            raise ValueError(f"count for {item} must be a whole number 0-{MAX_COUNT}, got {count!r}")
        if conf not in CONFIDENCES:
            raise ValueError(f"confidence for {item} must be low/medium/high, got {conf!r}")
        seen.add(item)
        out.append({"item": item, "count": count, "confidence": conf})
    return out


def llm_count(image: Image.Image, location: str, items: list, client=None) -> list:
    if client is None:
        from openai import OpenAI
        client = OpenAI(api_key=os.environ["LLM_API_KEY"], base_url=os.environ.get("LLM_BASE_URL"))
    buf = io.BytesIO()
    image.convert("RGB").save(buf, format="JPEG")
    prompt = (f"Photo of the {location} shelf in a restaurant. Count whole PACKS of these items only: {items}. "
              "Reply with JSON only: a list of {\"item\": <one of the names>, \"count\": <integer>, "
              "\"confidence\": \"low\"|\"medium\"|\"high\"}. Leave out items you cannot see.")
    resp = client.chat.completions.create(
        model=os.environ.get("VISION_MODEL", "gpt-4o-mini"), max_tokens=300, temperature=0,
        messages=[{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()}}]}])
    return validate_counts(resp.choices[0].message.content, set(items))


def estimate_counts(image: Image.Image, location: str, items: list, client=None) -> dict:
    """LLM if configured (or a client is passed), else the demo heuristic. Never raises."""
    if client is not None or os.environ.get("LLM_API_KEY"):
        try:
            return {"counts": llm_count(image, location, items, client), "source": "vision LLM (unvalidated)"}
        except Exception as e:
            return {"counts": heuristic_count(image, items), "source": f"demo heuristic (LLM failed: {type(e).__name__})"}
    return {"counts": heuristic_count(image, items), "source": "demo heuristic (offline)"}
