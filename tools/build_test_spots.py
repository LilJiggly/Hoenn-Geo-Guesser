"""Builds data/test_spots.json for test mode, which uses images/full.png.

full.png holds the overworld plus everything the normal map leaves out: caves, gyms, hideouts,
the Safari Zone and so on. Interior blocks have no obvious place on the minimap, so each one is
tied to a named location (tools/test_labels.csv: name + page coordinates, from the interactive map
on pokemoncompletion.com) and each location is tied to an overworld "host" (the entrance), whose
position the game then maps to the minimap exactly like the normal mode does.

Interiors are shown one location at a time (images/blocks/L<n>.png holds only that location's
pixels), so a screenshot never contains a second location, even when the player drags the view.

Blocks without a line or name can be labelled by hand with tools/label.html; its export goes into
data/test_manual.json and is picked up here (answer = minimap position, keyed by block corner).

Run from the project root, after tools/build_spots.py:
    python3 tools/build_test_spots.py && python3 tools/slice_blocks.py
"""
import csv, json, collections, os
from PIL import Image, ImageFilter
Image.MAX_IMAGE_PIXELS = None

S = 8                          # occupancy grids are 1/8 scale (2048 x 1024)
OFFSET = (538, 1580)           # where images/hoenn.png sits inside images/full.png (native px, pixel exact)
# page coordinates -> full.png native px (fitted on the 13 towns; good to about +-100 px)
AX, BX, AY, BY = 16.179, 177.6, -16.413, 72.4
VIEW_W, VIEW_H = 384 // S, 256 // S
DILATE = 24                    # blocks closer than this (1/8 px) count as one cluster
STEP = 8                       # spot spacing (1/8 px)
MIN_COVER = 0.3                # share of the view that must show map (interiors are small rooms)

# interior location -> overworld location whose position stands in for its entrance
HOST = {
    "Island Cave": "Route 105", "Granite Cave": "Route 106", "Abandoned Ship": "Route 108",
    "Oceanic Museum": "Slateport City", "Trick House": "Route 110", "New Mauville": "Route 110",
    "Trainer Hill": "Route 111", "Desert Ruins": "Route 111", "Mirage Tower": "Route 111",
    "Fiery Path": "Route 112", "Jagged Pass": "Route 112", "Mt. Chimney": "Route 112",
    "Team Magma Hideout": "Route 112", "Desert Underpass": "Route 114", "Meteor Falls": "Route 114",
    "Rusturf Tunnel": "Verdanturf Town", "Weather Institute": "Route 119", "Scorched Slab": "Route 120",
    "Ancient Tomb": "Route 120", "Safari Zone": "Route 121", "Mt. Pyre": "Route 122",
    "Lilycove Museum": "Lilycove City", "Team Aqua Hideout": "Lilycove City", "Shoal Cave": "Route 125",
    "Mossdeep Space Center": "Mossdeep City", "Seafloor Cavern": "Route 128", "Mirage Island": "Route 130",
    "Sky Pillar": "Route 131", "Victory Road": "Ever Grande City", "Pokémon League": "Ever Grande City",
    "Sealed Chamber": "Route 134", "Altering Cave": "Route 103",
    "Sootopolis City": "@crater", "Cave of Origin": "@crater",
}
# no spot on the minimap (or not sure where it belongs): left out of test mode
SKIP = {"Battle Frontier", "Southern Island", "Birth Island", "Faraway Island", "Navel Rock", "S.S. Tidal",
        "Artisan Cave", "Marine Cave", "Terra Cave", "Mirage Island"}  # Mirage Island: label sits on the wrong block
CRATER = (1500, 510)           # Sootopolis crater on the 2000 px wide overview of hoenn.png (data.json anchor)

labels = {}
for r in csv.DictReader(open("tools/test_labels.csv")):
    labels[r["name"]] = ((AX * float(r["lng"]) + BX), (AY * float(r["lat"]) + BY))   # full.png native px

# --- occupancy of full.png at 1/8 scale -------------------------------------------------------------
full = Image.open("images/full.png")
W8, H8 = full.width // S, full.height // S
occ = full.getchannel("A").resize((W8, H8), Image.BOX).point(lambda a: 255 if a >= 128 else 0)
del full

# remove the part that belongs to the normal overworld (the reachable tiles)
ow = Image.open("tools/reachable_mask.png").convert("L")
ox, oy = round(OFFSET[0] / S), round(OFFSET[1] / S)
ow_big = Image.new("L", (W8, H8), 0)
ow_big.paste(ow, (ox, oy))
op, wp = occ.load(), ow_big.load()
interior = Image.new("L", (W8, H8), 0)
ip = interior.load()
for y in range(H8):
    for x in range(W8):
        if op[x, y] and not wp[x, y]:
            ip[x, y] = 255

# --- blocks: touching rooms/floors form one block ------------------------------------------------------
grown = interior  # rooms are separate rectangles; touching ones form one block
gp = grown.load()
bid = [[0] * W8 for _ in range(H8)]
nb = 0
for y0 in range(H8):
    for x0 in range(W8):
        if gp[x0, y0] and not bid[y0][x0]:
            nb += 1
            bid[y0][x0] = nb
            stack = [(x0, y0)]
            while stack:
                x, y = stack.pop()
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    a, b = x + dx, y + dy
                    if 0 <= a < W8 and 0 <= b < H8 and gp[a, b] and not bid[b][a]:
                        bid[b][a] = nb
                        stack.append((a, b))
print(nb, "interior blocks")

def near_overworld(px, py, rad=4):
    x, y = int(px / S), int(py / S)
    return any(0 <= x + dx < W8 and 0 <= y + dy < H8 and wp[x + dx, y + dy] for dx in range(-rad, rad + 1) for dy in range(-rad, rad + 1))

def block_near(px, py, rad=32):
    x, y = int(px / S), int(py / S)
    best = None
    for dy in range(-rad, rad + 1):
        for dx in range(-rad, rad + 1):
            a, b = x + dx, y + dy
            if 0 <= a < W8 and 0 <= b < H8 and ip[a, b]:
                d = dx * dx + dy * dy
                if best is None or d < best[0]:
                    best = (d, bid[b][a])
    return best[1] if best else None

# union blocks that are linked to each other by an "area connection line" (floors of one cave, etc.)
parent = list(range(nb + 1))
def find(i):
    while parent[i] != i:
        parent[i] = parent[parent[i]]
        i = parent[i]
    return i

def to_px(lat, lng):
    return AX * lng + BX, AY * lat + BY

entrances = collections.defaultdict(list)     # block -> overworld entrances (hoenn native px)
pending = []
for r in csv.DictReader(open("tools/test_lines.csv")):
    ends = []
    for lat, lng in ((float(r["lat1"]), float(r["lng1"])), (float(r["lat2"]), float(r["lng2"]))):
        px, py = to_px(lat, lng)
        if near_overworld(px, py):
            ends.append(("ow", (px - OFFSET[0], py - OFFSET[1])))
        else:
            bl = block_near(px, py)
            ends.append(("in", bl) if bl else ("none", None))
    kinds = [e[0] for e in ends]
    if kinds == ["in", "in"]:
        parent[find(ends[0][1])] = find(ends[1][1])
    elif sorted(kinds) == ["in", "ow"]:
        pending.append((ends[kinds.index("in")][1], ends[kinds.index("ow")][1]))
for blk, pos in pending:
    entrances[find(blk)].append(pos)

# names and fallback entrances from the labelled locations
names = collections.defaultdict(list)
fallback = {}
for name, (px, py) in labels.items():
    if name in SKIP or name not in HOST:
        continue
    bl = block_near(px, py)
    if bl is None:
        print("label not on any interior block:", name)
        continue
    root = find(bl)
    names[root].append(name)
    host = HOST[name]
    fallback.setdefault(root, (CRATER[0] * 6.512, CRATER[1] * 6.512) if host == "@crater" else (labels[host][0] - OFFSET[0], labels[host][1] - OFFSET[1]))

# --- units: one per location; its pixels get their own image --------------------------------------------
def corner(root):
    """bounding box of a block group in 1/8 cells"""
    return boxes[root]
boxes = {}
for y in range(H8):
    for x in range(W8):
        if ip[x, y]:
            r = find(bid[y][x])
            b = boxes.setdefault(r, [x, y, x, y])
            b[0] = min(b[0], x); b[1] = min(b[1], y); b[2] = max(b[2], x); b[3] = max(b[3], y)

manual = json.load(open("data/test_manual.json")) if os.path.exists("data/test_manual.json") else {}
loc, unit_of, unlabeled = [], {}, []
for root in sorted(boxes):
    x0, y0, x1, y1 = boxes[root]
    key = f"{x0},{y0}"
    ent = entrances.get(root) or ([fallback[root]] if root in fallback else None)
    entry = None
    if ent:
        hx, hy = ent[0]        # several entrances: the first listed line wins
        entry = {"name": " / ".join(dict.fromkeys(names.get(root, []))) or "", "host": [round(hx), round(hy)],
                 "via": "line" if entrances.get(root) else "label"}
    elif key in manual:
        entry = {"name": "", "mini": manual[key], "via": "manual"}
    if entry:
        entry["box"] = [x0 * S, y0 * S, (x1 - x0 + 1) * S, (y1 - y0 + 1) * S]
        unit_of[root] = len(loc)
        loc.append(entry)
    elif (x1 - x0 + 1) >= 16 and (y1 - y0 + 1) >= 12:   # ignore slivers and tiny fragments
        unlabeled.append({"root": root, "key": key, "box": [x0 * S, y0 * S, (x1 - x0 + 1) * S, (y1 - y0 + 1) * S]})
via = collections.Counter(l["via"] for l in loc)
print(len(loc), "interior locations:", dict(via), "|", len(unlabeled), "blocks still unlabelled")

# masks for tools/slice_blocks.py (cell value = unit id + 1)
unit_mask = Image.new("L", (W8, H8), 0); um = unit_mask.load()
uid = [[-1] * W8 for _ in range(H8)]
for y in range(H8):
    for x in range(W8):
        if ip[x, y]:
            r = find(bid[y][x])
            u = unit_of.get(r)
            if u is not None:
                um[x, y] = u + 1
                uid[y][x] = u
# a location may be several blocks far apart (floors linked by lines): one small image per block,
# because a single bounding box over all of them would be far too big for phones to decode
piece_box = {}
for y in range(H8):
    for x in range(W8):
        if uid[y][x] >= 0:
            b = piece_box.setdefault(bid[y][x], [x, y, x, y, uid[y][x]])
            b[0] = min(b[0], x); b[1] = min(b[1], y); b[2] = max(b[2], x); b[3] = max(b[3], y)
for l in loc:
    l["pieces"] = []
for b in sorted(piece_box.values()):
    x0, y0, x1, y1, u = b
    loc[u]["pieces"].append([x0 * S, y0 * S, (x1 - x0 + 1) * S, (y1 - y0 + 1) * S])
unit_mask.save("tools/unit_mask.png")

# --- spots: the view must show mostly its own location -------------------------------------------------
spots = []
for y in range(0, H8, STEP):
    for x in range(0, W8, STEP):
        u = uid[y][x]
        if u < 0:
            continue
        hit = tot = 0
        for yy in range(y - VIEW_H // 2, y + VIEW_H // 2, 4):
            for xx in range(x - VIEW_W // 2, x + VIEW_W // 2, 4):
                tot += 1
                if 0 <= xx < W8 and 0 <= yy < H8 and uid[yy][xx] == u:
                    hit += 1
        if hit < MIN_COVER * tot:
            continue
        spots.append([x * S + S // 2, y * S + S // 2, u])
print(len(spots), "interior spots")
per = collections.Counter(sp[2] for sp in spots)
print("spots per location: min", min(per.values()), "max", max(per.values()), "| locations without a spot:", len(loc) - len(per))

# overworld spots are the normal-mode ones (hoenn.png coordinates, drawn from images/map)
overworld = json.load(open("data/spots.json"))

json.dump({
    "locations": [{k: v for k, v in l.items() if k not in ("via", "box")} for l in loc],
    "spots": spots,
    "overworld": overworld,
}, open("data/test_spots.json", "w"), separators=(",", ":"), ensure_ascii=False)

# blocks the labelling page should show, in reading order so neighbours (same town) come together
unlabeled.sort(key=lambda b: (b["box"][1] // 320, b["box"][0]))
root_idx = {b["root"]: i + 1 for i, b in enumerate(unlabeled)}
unl_mask = Image.new("L", (W8, H8), 0); ulm = unl_mask.load()
for y in range(H8):
    for x in range(W8):
        if ip[x, y]:
            ulm[x, y] = root_idx.get(find(bid[y][x]), 0)
unl_mask.save("tools/unlabeled_mask.png")
for b in unlabeled:
    del b["root"]
json.dump(unlabeled, open("data/test_unlabeled.json", "w"), separators=(",", ":"))
print("wrote data/test_spots.json and data/test_unlabeled.json")
