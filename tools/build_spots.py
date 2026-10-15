"""Builds data/spots.json (candidate screenshot centres) and tools/reachable_mask.png.

A spot's view must be mostly inside the reachable area (the imgi_*.webp tiles, transparent =
unreachable) and not mostly water. Unreachable pixels are blacked out by tools/slice_map.py, so
dragging never reveals them and spots may sit right at the edge of a route.

Run from the project root:  python3 tools/build_spots.py
Tile positions (1/8-scale map, 1628 px wide) come from tools/tile_positions.json.
"""
import json, glob, re
from PIL import Image

SCALE = 8                 # tile map is 1/8 of images/hoenn.png
W, H = 1628, 858
VIEW_W, VIEW_H = 384 // SCALE, 256 // SCALE   # screenshot window in tile-map px
STEP = 4
MIN_REACHABLE = 0.9       # share of the view that must be reachable (the rest shows as black)
MAX_WATER = 0.7           # skip shots that are mostly water

pos = json.load(open("tools/tile_positions.json"))
canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
for f, (score, (ox, oy, c, r)) in pos.items():
    canvas.alpha_composite(Image.open(f"images/{f}").convert("RGBA"), (ox, oy))
canvas.save("tools/reachable_preview.png")
canvas.getchannel("A").point(lambda a: 255 if a == 255 else 0).save("tools/reachable_mask.png")

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
for y in range(0, H - VIEW_H, STEP):
    for x in range(0, W - VIEW_W, STEP):
        if box(reach, x, y, x + VIEW_W, y + VIEW_H) / area < MIN_REACHABLE: continue
        if 1 - box(land, x, y, x + VIEW_W, y + VIEW_H) / area > MAX_WATER: continue
        spots.append([(x + VIEW_W // 2) * SCALE, (y + VIEW_H // 2) * SCALE])  # native px centre

json.dump(spots, open("data/spots.json", "w"), separators=(",", ":"))
print(len(spots), "spots")
