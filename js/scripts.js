// ===============================
// SETTINGS
// ===============================
const ROUNDS = 5;
const MAX_POINTS = 5000;
const SCORE_FALLOFF = 30; // minimap pixels; bigger = more forgiving
const VIEW_W = 384; // screenshot size in native big-map pixels (24x16 tiles); keep in sync with tools/build_spots.py
const VIEW_H = 256;
const MAX_PAN_TILES = 8; // drag limit baked into the chunks (PAN in tools/slice_map.py)
// how far the player may drag the screenshot, in game tiles (16 px each); ?pan=N overrides, 0 = no dragging
const PAN_TILES = Math.min(MAX_PAN_TILES, Number(new URLSearchParams(location.search).get("pan") ?? 4));
const TILE = 16;
const CHUNK = 1024; // map chunk size in images/map/ (tools/slice_map.py). The full map image is too big for iOS Safari
const ZONE = 512; // native px; spots are grouped into zones this big for even coverage
const MIN_SEPARATION = 25; // minimap px between rounds in one game, so shots differ
const DEBUG = new URLSearchParams(location.search).has("debug");

// ===============================
// STATE
// ===============================
let data;
let toMini; // function: big-map native px -> minimap px
let spots = []; // [bigX, bigY] native px centres inside the reachable area (data/spots.json)
let round = 0;
let total = 0;
let current = null; // { name, bigX, bigY, mini: [x, y] }
let guess = null; // [x, y] in minimap px
let answered = false;
let pan = { x: 0, y: 0 }; // drag offset of the screenshot, native px
let hasDragged = false; // the "drag to look around" hint stops showing once the player has tried it
let snapFrame = null;

const $ = (id) => document.getElementById(id);

// ===============================
// BIG MAP -> MINIMAP MAPPING
// The big map is a stitched, stretched version of the region, so a
// straight scale is off by tens of pixels. A thin-plate spline through
// the town anchors in data.json bends it into place.
// ===============================
function buildMapper(points) {
  const n = points.length;
  const U = (r2) => (r2 === 0 ? 0 : r2 * Math.log(r2) * 0.5);
  const A = [];
  for (let i = 0; i < n + 3; i++) A.push(new Array(n + 3).fill(0));
  for (let i = 0; i < n; i++) {
    for (let j = 0; j < n; j++) {
      const dx = points[i].x - points[j].x;
      const dy = points[i].y - points[j].y;
      A[i][j] = U(dx * dx + dy * dy);
    }
    A[i][i] += 0.001; // tiny smoothing
    A[i][n] = 1;
    A[i][n + 1] = points[i].x;
    A[i][n + 2] = points[i].y;
    A[n][i] = 1;
    A[n + 1][i] = points[i].x;
    A[n + 2][i] = points[i].y;
  }
  const solve = (rhs) => {
    const M = A.map((row, i) => [...row, rhs[i]]);
    const N = n + 3;
    for (let c = 0; c < N; c++) {
      let p = c;
      for (let r = c + 1; r < N; r++) if (Math.abs(M[r][c]) > Math.abs(M[p][c])) p = r;
      [M[c], M[p]] = [M[p], M[c]];
      for (let r = c + 1; r < N; r++) {
        const f = M[r][c] / M[c][c];
        for (let k = c; k <= N; k++) M[r][k] -= f * M[c][k];
      }
    }
    const x = new Array(N).fill(0);
    for (let r = N - 1; r >= 0; r--) {
      let s = M[r][N];
      for (let k = r + 1; k < N; k++) s -= M[r][k] * x[k];
      x[r] = s / M[r][r];
    }
    return x;
  };
  const wx = solve([...points.map((p) => p.u), 0, 0, 0]);
  const wy = solve([...points.map((p) => p.v), 0, 0, 0]);
  return (x, y) => {
    const f = (w) => {
      let s = w[n] + w[n + 1] * x + w[n + 2] * y;
      for (let i = 0; i < n; i++) {
        const dx = x - points[i].x;
        const dy = y - points[i].y;
        s += w[i] * U(dx * dx + dy * dy);
      }
      return s;
    };
    return [f(wx), f(wy)];
  };
}

// ===============================
// LOAD DATA
// ===============================
Promise.all([fetch("data/data.json"), fetch("data/spots.json")])
  .then(([a, b]) => Promise.all([a.json(), b.json()]))
  .then(([d, s]) => {
    data = d;
    spots = s;
    const k = data.bigMapSize[0] / data.displaySize[0]; // display coords -> native px
    toMini = buildMapper(
      data.anchors.map((a) => ({ x: a.big[0] * k, y: a.big[1] * k, u: a.mini[0], v: a.mini[1] }))
    );
    if (DEBUG) drawDebug();
    startGame();
  })
  .catch((error) => console.error("Error loading JSON:", error));

// ===============================
// GAME FLOW
// ===============================
function startGame() {
  round = 0;
  total = 0;
  $("rounds").textContent = ROUNDS;
  $("score").textContent = 0;
  $("final").hidden = true;
  deck = pickSpots();
  nextRound();
}

let deck = [];
let zones = null; // zone key -> spots in that zone
const seenZones = new Set(); // zones already shown this session, so repeat games feel fresh

// Picking a random spot would favour wide open areas (they hold thousands of spots) over narrow
// routes and towns. Instead pick a random zone first, then a random spot inside it.
function pickSpots() {
  if (!zones) {
    zones = new Map();
    for (const sp of spots) {
      const key = `${Math.floor(sp[0] / ZONE)},${Math.floor(sp[1] / ZONE)}`;
      if (!zones.has(key)) zones.set(key, []);
      zones.get(key).push(sp);
    }
  }
  let fresh = [...zones.keys()].filter((k) => !seenZones.has(k));
  if (fresh.length < ROUNDS * 3) {
    seenZones.clear(); // seen (nearly) everything: start over
    fresh = [...zones.keys()];
  }
  const picked = [];
  let tries = 0;
  while (picked.length < ROUNDS && tries++ < 5000) {
    const key = fresh[Math.floor(Math.random() * fresh.length)];
    const list = zones.get(key);
    const [x, y] = list[Math.floor(Math.random() * list.length)];
    const mini = toMini(x, y);
    const apart = picked.every((p) => Math.hypot(p.mini[0] - mini[0], p.mini[1] - mini[1]) >= MIN_SEPARATION);
    if (apart) {
      picked.push({ cx: x, cy: y, mini });
      seenZones.add(key);
    }
  }
  return picked;
}

function nextRound() {
  round++;
  answered = false;
  guess = null;
  clearMarkers();
  $("round").textContent = round;
  $("result").textContent = "";
  $("hint").textContent = "Click the minimap to place your guess.";
  $("guess-btn").textContent = "Guess";
  $("guess-btn").disabled = true;

  current = deck[round - 1];
  cancelAnimationFrame(snapFrame);
  pan = { x: 0, y: 0 };
  loadShotChunks();
  showShot();
  showDragHint();
}

// the screenshot is a window onto the map, built from the small chunks that overlap the view
function loadShotChunks() {
  const el = $("shot");
  el.replaceChildren();
  const lim = PAN_TILES * TILE;
  const x0 = Math.floor((current.cx - VIEW_W / 2 - lim) / CHUNK);
  const x1 = Math.floor((current.cx + VIEW_W / 2 + lim) / CHUNK);
  const y0 = Math.floor((current.cy - VIEW_H / 2 - lim) / CHUNK);
  const y1 = Math.floor((current.cy + VIEW_H / 2 + lim) / CHUNK);
  for (let cx = x0; cx <= x1; cx++) {
    for (let cy = y0; cy <= y1; cy++) {
      const img = document.createElement("img");
      img.src = `./images/map/${cx}_${cy}.png`;
      img.draggable = false;
      img.dataset.cx = cx;
      img.dataset.cy = cy;
      el.appendChild(img);
    }
  }
}

// subtle prompt that stays until the player drags once, then never returns
function showDragHint() {
  if (!PAN_TILES || hasDragged) return;
  const hint = document.createElement("div");
  hint.className = "drag-hint";
  hint.textContent = "Drag to look around";
  $("shot").appendChild(hint);
  requestAnimationFrame(() => hint.classList.add("visible"));
}

function hideDragHint() {
  document.querySelectorAll("#shot .drag-hint").forEach((h) => h.classList.remove("visible"));
}

function showShot() {
  const el = $("shot");
  const scale = el.clientWidth / VIEW_W;
  const left = current.cx + pan.x - VIEW_W / 2;
  const top = current.cy + pan.y - VIEW_H / 2;
  el.querySelectorAll("img").forEach((img) => {
    // +1px size so neighbouring chunks overlap instead of leaving hairline gaps
    img.style.left = `${Math.floor((img.dataset.cx * CHUNK - left) * scale)}px`;
    img.style.top = `${Math.floor((img.dataset.cy * CHUNK - top) * scale)}px`;
    img.style.width = `${Math.ceil(CHUNK * scale) + 1}px`;
    img.style.height = `${Math.ceil(CHUNK * scale) + 1}px`;
  });
}

window.addEventListener("resize", () => {
  if (current && data) showShot();
});

// drag the screenshot to look around (limited to PAN_TILES in each direction)
let drag = null;
$("shot").addEventListener("pointerdown", (evt) => {
  if (!PAN_TILES) return;
  cancelAnimationFrame(snapFrame);
  hasDragged = true;
  hideDragHint();
  drag = { x: evt.clientX, y: evt.clientY, panX: pan.x, panY: pan.y };
  $("shot").setPointerCapture(evt.pointerId);
  $("shot").classList.add("dragging");
});
$("shot").addEventListener("pointermove", (evt) => {
  if (!drag) return;
  const scale = $("shot").clientWidth / VIEW_W;
  const lim = PAN_TILES * TILE;
  // dragging right moves the view left, like grabbing the map
  pan.x = clamp(drag.panX - (evt.clientX - drag.x) / scale, -lim, lim);
  pan.y = clamp(drag.panY - (evt.clientY - drag.y) / scale, -lim, lim);
  showShot();
});
const endDrag = () => {
  if (!drag) return;
  drag = null;
  $("shot").classList.remove("dragging");
  snapBack();
};

// letting go glides the view back to the original spot
function snapBack() {
  const from = { ...pan };
  const start = performance.now();
  const DURATION = 250;
  const step = (now) => {
    const t = Math.min(1, (now - start) / DURATION);
    const k = 1 - Math.pow(1 - t, 3); // ease-out
    pan.x = from.x * (1 - k);
    pan.y = from.y * (1 - k);
    showShot();
    if (t < 1) snapFrame = requestAnimationFrame(step);
  };
  snapFrame = requestAnimationFrame(step);
}
$("shot").addEventListener("pointerup", endDrag);
$("shot").addEventListener("pointercancel", endDrag);

function clamp(v, a, b) {
  return Math.min(b, Math.max(a, v));
}

// ===============================
// MINIMAP INTERACTION
// ===============================
function miniPoint(evt) {
  const r = $("mini-img").getBoundingClientRect(); // excludes the screen border
  return [((evt.clientX - r.left) / r.width) * data.miniSize[0], ((evt.clientY - r.top) / r.height) * data.miniSize[1]];
}

function addPin(cls, [x, y]) {
  const p = document.createElement("div");
  p.className = `pin ${cls}`;
  p.style.left = `${(x / data.miniSize[0]) * 100}%`;
  p.style.top = `${(y / data.miniSize[1]) * 100}%`;
  $("mini").appendChild(p);
  return p;
}

function clearMarkers() {
  document.querySelectorAll("#mini .pin:not(.debug), #mini svg").forEach((e) => e.remove());
}

$("mini").addEventListener("click", (evt) => {
  if (answered || !data) return;
  guess = miniPoint(evt);
  document.querySelectorAll("#mini .pin.guess").forEach((e) => e.remove());
  addPin("guess", guess);
  $("guess-btn").disabled = false;
});

$("guess-btn").addEventListener("click", () => {
  if (answered) {
    if (round >= ROUNDS) return endGame();
    return nextRound();
  }
  if (!guess) return;
  answered = true;

  const dist = Math.hypot(guess[0] - current.mini[0], guess[1] - current.mini[1]);
  const points = Math.round(MAX_POINTS * Math.exp(-dist / SCORE_FALLOFF));
  total += points;
  $("score").textContent = total;

  addPin("answer", current.mini);
  drawLine(guess, current.mini);
  $("result").innerHTML = `<b>${points}</b> points: ${Math.round(dist)} minimap px away.`;
  $("hint").textContent = "";
  $("guess-btn").textContent = round >= ROUNDS ? "See final score" : "Next round";
});

function drawLine(a, b) {
  const [w, h] = data.miniSize;
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", `0 0 ${w} ${h}`);
  svg.innerHTML = `<line x1="${a[0]}" y1="${a[1]}" x2="${b[0]}" y2="${b[1]}" stroke="#fff" stroke-width="1" stroke-dasharray="3 2" />`;
  $("mini").appendChild(svg);
}

function endGame() {
  $("final-score").textContent = total;
  $("final-max").textContent = MAX_POINTS * ROUNDS;
  $("final").hidden = false;
}
$("again-btn").addEventListener("click", startGame);

// ===============================
// DEBUG: add ?debug to the URL to see where every spot lands
// ===============================
function drawDebug() {
  const k = data.bigMapSize[0] / data.displaySize[0];
  data.anchors.forEach((s) => {
    const p = addPin("debug", toMini(s.big[0] * k, s.big[1] * k));
    p.title = s.name;
  });
  // every 40th candidate spot, to see how the reachable area lands on the minimap
  spots.forEach(([x, y], i) => {
    if (i % 40 === 0) addPin("debug", toMini(x, y)).style.background = "#4da6ff";
  });
}
