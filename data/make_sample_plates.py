"""Draw simple SYNTHETIC plate illustrations (not photos) for the plate-waste demo.

Each image: dark table, white plate, and a brown "food" pie slice covering
0%, 25%, 50%, 75% or 100% of the food area. Run: python data/make_sample_plates.py
"""
import pathlib
from PIL import Image, ImageDraw

OUT = pathlib.Path(__file__).resolve().parent / "sample_plates"
SIZE = 400
SAMPLES = {"empty": 0.0, "small_leftover": 0.25, "half_left": 0.5, "most_left": 0.75, "untouched": 1.0}


def draw_plate(fraction: float) -> Image.Image:
    img = Image.new("RGB", (SIZE, SIZE), (60, 45, 35))           # table
    d = ImageDraw.Draw(img)
    c, plate_r = SIZE // 2, int(SIZE * 0.45)
    d.ellipse([c - plate_r, c - plate_r, c + plate_r, c + plate_r], fill=(245, 245, 245))  # plate
    food_r = int(plate_r * 0.8)
    if fraction > 0:
        d.pieslice([c - food_r, c - food_r, c + food_r, c + food_r], start=-90,
                   end=-90 + 360 * fraction, fill=(150, 90, 40))  # food
    d.text((8, SIZE - 16), "SYNTHETIC ILLUSTRATION - not a photo", fill=(255, 255, 0))
    return img


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    for name, f in SAMPLES.items():
        draw_plate(f).save(OUT / f"{name}.png")
        print("wrote", OUT / f"{name}.png")
