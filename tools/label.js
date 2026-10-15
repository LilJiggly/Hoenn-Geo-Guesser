// Labelling page for interiors that have no entrance data yet. See label.html.
const STORE = "hoenn-test-labels";
const $ = (id) => document.getElementById(id);
const MAP = [13024, 6864]; // unused; the overview is full.png at 1/8 scale (2048 x 1024)
const OVERVIEW = [2048, 1024];

let blocks = [];
let labels = {}; // block key -> [minimap x, minimap y]
let i = 0;
let guess = null;
let lastLabel = null;

const save = () => localStorage.setItem(STORE, JSON.stringify(labels));

async function init() {
  blocks = await (await fetch("../data/test_unlabeled.json")).json();
  try {
    labels = { ...(await (await fetch("../data/test_manual.json")).json()) };
  } catch (e) {
    labels = {};
  }
  try {
    labels = { ...labels, ...JSON.parse(localStorage.getItem(STORE) || "{}") };
  } catch (e) {}
  i = Math.max(0, blocks.findIndex((b) => !labels[b.key]));
  drawDone();
  show();
}

function show() {
  const b = blocks[i];
  if (!b) {
    $("progress").textContent = "· all blocks shown";
    $("block").removeAttribute("src");
    return;
  }
  const done = blocks.filter((x) => labels[x.key]).length;
  $("progress").textContent = `· block ${i + 1}/${blocks.length} · ${done} labelled`;
  $("block").src = `./label/blocks/${i}.png`;
  $("block").style.imageRendering = b.box[2] < 400 ? "pixelated" : "auto";
  $("info").textContent = `${b.box[2]} × ${b.box[3]} px (native) at ${b.box[0]}, ${b.box[1]}.`;
  const [x, y, w, h] = b.box;
  Object.assign($("here").style, {
    left: `${((x / 8) / OVERVIEW[0]) * 100}%`, top: `${((y / 8) / OVERVIEW[1]) * 100}%`,
    width: `${((w / 8) / OVERVIEW[0]) * 100}%`, height: `${((h / 8) / OVERVIEW[1]) * 100}%`,
  });
  setGuess(labels[b.key] || null);
}

function pin(cls, [u, v]) {
  const p = document.createElement("div");
  p.className = `pin ${cls}`;
  p.style.left = `${(u / 240) * 100}%`;
  p.style.top = `${(v / 160) * 100}%`;
  $("mini").appendChild(p);
}

function setGuess(g) {
  guess = g;
  document.querySelectorAll("#mini .pin").forEach((e) => e.remove());
  Object.values(labels).forEach((l) => pin("done", l));
  if (g) pin("guess", g);
  $("save").disabled = !g;
}

function drawDone() {
  document.querySelectorAll(".done-box").forEach((e) => e.remove());
  blocks.forEach((b) => {
    if (!labels[b.key]) return;
    const d = document.createElement("div");
    d.className = "done-box";
    const [x, y, w, h] = b.box;
    Object.assign(d.style, {
      left: `${((x / 8) / OVERVIEW[0]) * 100}%`, top: `${((y / 8) / OVERVIEW[1]) * 100}%`,
      width: `${((w / 8) / OVERVIEW[0]) * 100}%`, height: `${((h / 8) / OVERVIEW[1]) * 100}%`,
    });
    $("overview").appendChild(d);
  });
}

$("mini").addEventListener("click", (evt) => {
  const r = $("mini").querySelector("img").getBoundingClientRect();
  setGuess([Math.round(((evt.clientX - r.left) / r.width) * 2400) / 10, Math.round(((evt.clientY - r.top) / r.height) * 1600) / 10]);
});

function commit() {
  if (!guess || !blocks[i]) return;
  labels[blocks[i].key] = guess;
  lastLabel = guess;
  save();
  drawDone();
  go(1);
}
function go(d) {
  i = Math.min(blocks.length, Math.max(0, i + d));
  show();
}

$("save").onclick = commit;
$("skip").onclick = () => go(1);
$("back").onclick = () => go(-1);
$("same").onclick = () => {
  const prev = lastLabel || labels[Object.keys(labels).pop()];
  if (prev) setGuess(prev);
};
const json = () => JSON.stringify(labels, null, 1);
$("download").onclick = () => {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([json()], { type: "application/json" }));
  a.download = "test_manual.json";
  a.click();
};
$("copy").onclick = () => navigator.clipboard.writeText(json());
document.addEventListener("keydown", (e) => {
  if (e.key === "Enter") commit();
  else if (e.key === "s" || e.key === "S") go(1);
  else if (e.key === "b" || e.key === "B") go(-1);
});

init();
