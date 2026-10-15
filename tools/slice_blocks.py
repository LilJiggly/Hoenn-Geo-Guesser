"""Cuts every interior location out of images/full.png into its own transparent PNG, so a
screenshot can only ever show one location:
  images/blocks/L<n>_<k>.png      block k of location n of data/test_spots.json (the game)
  tools/label/blocks/<index>.png  blocks still unlabelled (tools/label.html), plus tools/label/overview.png

Run from the project root, after tools/build_test_spots.py:  python3 tools/slice_blocks.py
"""
import json, os
from PIL import Image
Image.MAX_IMAGE_PIXELS = None
S = 8

full = Image.open("images/full.png").convert("RGBA")
unit_mask = Image.open("tools/unit_mask.png")
unl_mask = Image.open("tools/unlabeled_mask.png")

def cut(box, mask, value, path):
    x, y, w, h = box
    m = mask.crop((x // S, y // S, (x + w) // S, (y + h) // S)).resize((w, h), Image.NEAREST)
    m = m.point(lambda v: 255 if v == value else 0)
    tile = full.crop((x, y, x + w, y + h))
    tile.putalpha(Image.composite(tile.getchannel("A"), Image.new("L", (w, h), 0), m))
    tile.save(path, optimize=True)

os.makedirs("images/blocks", exist_ok=True)
os.makedirs("tools/label/blocks", exist_ok=True)
for d in ("images/blocks", "tools/label/blocks"):
    for f in os.listdir(d):
        os.remove(os.path.join(d, f))
locs = json.load(open("data/test_spots.json"))["locations"]
pieces = 0
for i, l in enumerate(locs):
    for k, box in enumerate(l["pieces"]):
        cut(box, unit_mask, i + 1, f"images/blocks/L{i}_{k}.png")
        pieces += 1
unl = json.load(open("data/test_unlabeled.json"))
for i, b in enumerate(unl):
    cut(b["box"], unl_mask, i + 1, f"tools/label/blocks/{i}.png")
full.convert("RGB").resize((2048, 1024), Image.BOX).save("tools/label/overview.png", optimize=True)
print(pieces, "block images,", len(unl), "label images")
