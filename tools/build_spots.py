"""Builds data/spots.json: candidate screenshot centres that lie fully inside the
reachable area (the imgi_*.webp tiles, transparent = unreachable) and are not mostly water.

Run from the project root:  python3 tools/build_spots.py
Tile positions (1/8-scale map, 1628 px wide) come from tools/tile_positions.json.
"""
import json, glob, re
from PIL import Image

SCALE = 8                 # tile map is 1/8 of images/hoenn.png
W, H = 1628, 858
VIEW_W, VIEW_H = 384 // SCALE, 256 // SCALE   # screenshot window in tile-map px
STEP = 4
MIN_REACHABLE = 1.0       # whole window must be reachable
MAX_PAN_TILES = 8         # extra reachable margin around the window so players can drag the view
                          # (keep in sync with MAX_PAN_TILES in js/scripts.js; 1 tile = 2 px here)
M = MAX_PAN_TILES * 2
MAX_WATER = 0.5          # skip mostly-water shots

pos = json.load(open("tools/tile_positions.json"))
canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
for f, (score, (ox, oy, c, r)) in pos.items():
    canvas.alpha_composite(Image.open(f"images/{f}").convert("RGBA"), (ox, oy))
canvas.save("tools/reachable_preview.png")

px = canvas.load()
def is_water(r, g, b): return b > 150 and r < 130 and g < 150

# integral images of "reachable" and "land"
reach = [[0] * (W + 1) for _ in range(H + 1)]
land = [[0] * (W + 1) for _ in range(H + 1)]
for y in range(H):
    rs = ls = 0
    for x in range(W):
        r, g, b, a = px[x, y]
        rs += 1 if a == 255 else 0
        ls += 1 if (a == 255 and not is_water(r, g, b)) else 0
        reach[y + 1][x + 1] = reach[y][x + 1] + rs
        land[y + 1][x + 1] = land[y][x + 1] + ls

def box(I, x0, y0, x1, y1):
    return I[y1][x1] - I[y0][x1] - I[y1][x0] + I[y0][x0]

area = VIEW_W * VIEW_H
spots = []
big_area = (VIEW_W + 2 * M) * (VIEW_H + 2 * M)
for y in range(M, H - VIEW_H - M, STEP):
    for x in range(M, W - VIEW_W - M, STEP):
        if box(reach, x - M, y - M, x + VIEW_W + M, y + VIEW_H + M) / big_area < MIN_REACHABLE: continue
        if 1 - box(land, x, y, x + VIEW_W, y + VIEW_H) / area > MAX_WATER: continue
        spots.append([(x + VIEW_W // 2) * SCALE, (y + VIEW_H // 2) * SCALE])  # native px centre

json.dump(spots, open("data/spots.json", "w"), separators=(",", ":"))
print(len(spots), "spots")
