"""Dining-room plate-waste logging: estimate leftover fraction, then grams wasted per ingredient.

Backends:
  1. Vision LLM (optional): only if env var LLM_API_KEY is set. Output is strictly validated.
  2. Offline heuristic: counts non-plate pixels on the plate. ROUGH HEURISTIC, DEMO ONLY.
A person always confirms or corrects the bucket before anything is logged.
"""
import base64
import io
import json
import os

import numpy as np
import pandas as pd
from PIL import Image

# Allowed answers: bucket name -> leftover fraction of the portion
BUCKETS = {"none": 0.0, "small": 0.25, "half": 0.5, "most": 0.75, "untouched": 1.0}
CONFIDENCES = {"low", "medium", "high"}

# In the sample illustrations, food fills a circle of 0.8 x plate radius => 0.64 of the plate area.
# Real photos will differ: this constant must be calibrated against weighed plates in a pilot.
FULL_PLATE_FOOD_COVERAGE = 0.64


# ---------- recipe math ----------
def load_recipes(path) -> pd.DataFrame:
    return pd.read_csv(path)


def grams_wasted(recipes: pd.DataFrame, dish: str, bucket: str) -> pd.DataFrame:
    """Grams wasted per ingredient = leftover fraction x grams per portion."""
    if bucket not in BUCKETS:
        raise ValueError(f"unknown bucket: {bucket}")
    rows = recipes[recipes["dish"] == dish].copy()
    if rows.empty:
        raise ValueError(f"dish not in recipes: {dish}")
    rows["grams_wasted"] = (rows["grams_per_portion"] * BUCKETS[bucket]).round(1)
    return rows[["dish", "ingredient", "grams_per_portion", "grams_wasted"]].reset_index(drop=True)


# ---------- validation of model output ----------
def validate_estimate(raw) -> dict:
    """Accept only {"bucket": one of BUCKETS, "confidence": low|medium|high, "reasoning": short text}.
    Anything else raises ValueError (we never trust model output blindly)."""
    if isinstance(raw, str):
        text = raw.strip()
        if text.startswith("```"):  # tolerate a fenced JSON block
            text = text.strip("`").removeprefix("json").strip()
        try:
            raw = json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f"not valid JSON: {e}")
    if not isinstance(raw, dict):
        raise ValueError("estimate must be a JSON object")
    bucket = raw.get("bucket")
    conf = raw.get("confidence")
    reason = raw.get("reasoning", "")
    if bucket not in BUCKETS:
        raise ValueError(f"bucket must be one of {list(BUCKETS)}, got {bucket!r}")
    if conf not in CONFIDENCES:
        raise ValueError(f"confidence must be one of {sorted(CONFIDENCES)}, got {conf!r}")
    if not isinstance(reason, str) or len(reason) > 500:
        raise ValueError("reasoning must be a string under 500 chars")
    return {"bucket": bucket, "confidence": conf, "reasoning": reason}


# ---------- offline heuristic ----------
def nearest_bucket(fraction: float) -> str:
    return min(BUCKETS, key=lambda b: abs(BUCKETS[b] - fraction))


def heuristic_estimate(image: Image.Image) -> dict:
    """ROUGH HEURISTIC, DEMO ONLY: share of non-white pixels inside the central plate circle."""
    img = image.convert("RGB").resize((200, 200))
    px = np.asarray(img).astype(int)
    yy, xx = np.mgrid[0:200, 0:200]
    plate_mask = (xx - 100) ** 2 + (yy - 100) ** 2 <= (200 * 0.43) ** 2   # assume plate is centred
    is_plate_white = (px.min(axis=2) > 200) & (px.max(axis=2) - px.min(axis=2) < 30)
    food_share = float((~is_plate_white & plate_mask).sum() / plate_mask.sum())
    leftover = min(1.0, food_share / FULL_PLATE_FOOD_COVERAGE)
    bucket = nearest_bucket(leftover)
    return {"bucket": bucket, "confidence": "low", "leftover_estimate": round(leftover, 2),
            "reasoning": f"Rough heuristic, demo only: {food_share:.0%} of the plate area is not "
                         f"plate-coloured -> ~{leftover:.0%} of a full portion -> '{bucket}'."}


# ---------- optional vision LLM ----------
def llm_estimate(image: Image.Image, dish: str, recipe: pd.DataFrame) -> dict:
    """Ask an OpenAI-compatible vision model for a bucket. Requires LLM_API_KEY and `pip install openai`."""
    from openai import OpenAI
    buf = io.BytesIO()
    image.convert("RGB").save(buf, format="JPEG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    portion = ", ".join(f"{r.ingredient} {r.grams_per_portion} g" for r in recipe.itertuples())
    prompt = (f"This is a plate returned to the dish station. Dish ordered: {dish}. Full portion: {portion}. "
              f"Estimate how much of the portion is LEFT on the plate. Reply with JSON only: "
              f'{{"bucket": one of {list(BUCKETS)}, "confidence": "low"|"medium"|"high", "reasoning": "<1 sentence>"}}')
    client = OpenAI(api_key=os.environ["LLM_API_KEY"], base_url=os.environ.get("LLM_BASE_URL"))
    resp = client.chat.completions.create(
        model=os.environ.get("VISION_MODEL", "gpt-4o-mini"), max_tokens=150, temperature=0,
        messages=[{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}]}])
    return validate_estimate(resp.choices[0].message.content)


def estimate(image: Image.Image, dish: str, recipes: pd.DataFrame) -> dict:
    """Use the LLM if configured; on any error (or no key) fall back to the heuristic."""
    if os.environ.get("LLM_API_KEY"):
        try:
            out = llm_estimate(image, dish, recipes[recipes["dish"] == dish])
            out["source"] = "vision LLM (unvalidated)"
            return out
        except Exception as e:
            fallback = heuristic_estimate(image)
            fallback["source"] = f"heuristic (LLM failed: {type(e).__name__})"
            return fallback
    out = heuristic_estimate(image)
    out["source"] = "heuristic (offline)"
    return out
