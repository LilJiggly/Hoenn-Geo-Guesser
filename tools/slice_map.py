"""Slices images/hoenn.png (13024x6864, too big for iOS Safari to decode) into 1024px chunks
in images/map/<col>_<row>.png. Only chunks any spot can show (view + pan margin) are written.

Run from the project root:  python3 tools/slice_map.py
"""
import json, os
from PIL import Image
Image.MAX_IMAGE_PIXELS = None

CHUNK = 1024                    # keep in sync with CHUNK in js/scripts.js
VIEW_W, VIEW_H = 384, 256
PAN = 8 * 16                    # MAX_PAN_TILES * 16 native px

spots = json.load(open("data/spots.json"))
need = set()
for x, y in spots:
    for cx in range(int(x - VIEW_W / 2 - PAN) // CHUNK, int(x + VIEW_W / 2 + PAN) // CHUNK + 1):
        for cy in range(int(y - VIEW_H / 2 - PAN) // CHUNK, int(y + VIEW_H / 2 + PAN) // CHUNK + 1):
            need.add((cx, cy))

big = Image.open("images/hoenn.png").convert("RGBA")
os.makedirs("images/map", exist_ok=True)
for cx, cy in sorted(need):
    tile = big.crop((cx * CHUNK, cy * CHUNK, (cx + 1) * CHUNK, (cy + 1) * CHUNK))
    tile.save(f"images/map/{cx}_{cy}.png", optimize=True)
print(len(need), "chunks")
