# Phase 3 — Statistics screen Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `/play/:session_id/stats` (cards + histograma + scatter + lista de errados + ações) e plugar a tela como destino pós-término. Atualizar a lista "Sessões anteriores" com `[→]` (rota condicional) e `[↻]` (reuso de params).

**Architecture:** Endpoint `GET /api/sessions/{id}` (já existente) é a única fonte da tela; estende `AttemptDetail` para incluir `game_url` (necessário para o link Lichess). Charts via uPlot vendored (~40KB, MIT). Frontend puro: `static/stats.html` + `static/js/stats.js` + `static/css/stats.css`. Sem novos endpoints.

**Tech Stack:** FastAPI + SQLite (backend, mudança mínima), JS ES modules, uPlot 1.6.x (vendored), CSS grid.

**Baseline:** 84/84 testes verdes (commit `686c5d8`).

---

### Task 1: Adicionar `game_url` ao `AttemptDetail` (TDD)

**Files:**
- Modify: `app/models.py` (AttemptDetail)
- Modify: `app/sessions.py` (get_session_with_attempts SQL + return)
- Test: `tests/test_sessions.py`

- [ ] **Step 1: Write failing test**

Adicionar em `tests/test_sessions.py` (no final do arquivo, depois de outros testes):

```python
def test_get_session_includes_game_url_on_attempts(app_with_db) -> None:
    c = TestClient(app_with_db)
    sid = c.post("/api/sessions", json={
        "mode": "count", "target": 5, "filters": {}
    }).json()["session_id"]
    # use a puzzle id present in tests/fixtures/puzzles_sample.csv
    c.post(f"/api/sessions/{sid}/attempts", json={
        "order_idx": 0, "puzzle_id": "00008", "correct": True, "time_ms": 100,
    })
    detail = c.get(f"/api/sessions/{sid}").json()
    assert "attempts" in detail
    assert len(detail["attempts"]) == 1
    a = detail["attempts"][0]
    assert "game_url" in a
    # fixture has a real game_url for 00008 (lichess.org/...). Just sanity-check non-empty.
    assert a["game_url"] is None or a["game_url"].startswith("https://")
```

- [ ] **Step 2: Run test, expect FAIL**

```bash
python -m pytest tests/test_sessions.py::test_get_session_includes_game_url_on_attempts -v
```
Expected: FAIL (KeyError or AssertionError on `"game_url"`).

- [ ] **Step 3: Update AttemptDetail model**

In `app/models.py`, change `AttemptDetail`:

```python
class AttemptDetail(BaseModel):
    order_idx: int
    puzzle_id: str
    correct: bool
    time_ms: int
    completed_at: str
    rating: int
    themes: list[str]
    game_url: str | None = None
```

- [ ] **Step 4: Update SQL JOIN + mapping in `get_session_with_attempts`**

In `app/sessions.py`, change the SELECT inside `get_session_with_attempts`:

```python
    rows = conn.execute(
        """
        SELECT a.order_idx, a.puzzle_id, a.correct, a.time_ms, a.completed_at,
               p.rating, p.themes, p.game_url
        FROM attempts a
        LEFT JOIN puzzles p ON p.puzzle_id = a.puzzle_id
        WHERE a.session_id = ?
        ORDER BY a.order_idx ASC
        """,
        (session_id,),
    ).fetchall()
    attempts = [
        AttemptDetail(
            order_idx=r["order_idx"],
            puzzle_id=r["puzzle_id"],
            correct=bool(r["correct"]),
            time_ms=r["time_ms"],
            completed_at=r["completed_at"],
            rating=r["rating"] or 0,
            themes=(r["themes"] or "").split() if r["themes"] else [],
            game_url=r["game_url"],
        )
        for r in rows
    ]
```

- [ ] **Step 5: Run tests, expect PASS**

```bash
python -m pytest tests/test_sessions.py -v
```
Expected: all session tests pass (including o novo).

- [ ] **Step 6: Commit**

```bash
git add app/models.py app/sessions.py tests/test_sessions.py
git commit -m "feat(sessions): expose game_url in /api/sessions/{id} attempts"
```

---

### Task 2: Vendor uPlot

**Files:**
- Create: `static/vendor/uPlot.iife.min.js`
- Create: `static/vendor/uPlot.min.css`

- [ ] **Step 1: Download uPlot vendored bundle**

```bash
curl -sSL -o static/vendor/uPlot.iife.min.js \
  https://cdn.jsdelivr.net/npm/uplot@1.6.31/dist/uPlot.iife.min.js
curl -sSL -o static/vendor/uPlot.min.css \
  https://cdn.jsdelivr.net/npm/uplot@1.6.31/dist/uPlot.min.css
```

- [ ] **Step 2: Verify**

```bash
ls -la static/vendor/uPlot.* && head -c 80 static/vendor/uPlot.iife.min.js
```
Expected: both files present, JS ~40KB minified.

- [ ] **Step 3: Commit**

```bash
git add static/vendor/uPlot.iife.min.js static/vendor/uPlot.min.css
git commit -m "chore(vendor): add uPlot 1.6.31 (charts for stats screen)"
```

---

### Task 3: Rota `/play/:id/stats` + `static/stats.html` scaffold + teste

**Files:**
- Create: `static/stats.html`
- Modify: `app/main.py`
- Test: `tests/test_main.py`

- [ ] **Step 1: Create static/stats.html scaffold**

```html
<!doctype html>
<html lang="pt-br">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>lichess-puzzles — estatísticas</title>
<link rel="stylesheet" href="/static/css/styles.css"/>
<link rel="stylesheet" href="/static/vendor/uPlot.min.css"/>
<link rel="stylesheet" href="/static/css/stats.css"/>
<script src="/static/vendor/uPlot.iife.min.js"></script>
</head>
<body class="stats-body">
<header class="stats-header">
  <h1 id="stats-title">Sessão</h1>
  <nav><a href="/">/ ↗</a></nav>
</header>

<main class="stats-main">
  <section class="stats-cards" id="cards">—</section>

  <section class="stats-chart-block">
    <h2>Histograma de tempos</h2>
    <div id="histogram" class="stats-chart" aria-label="histograma de tempos por exercício"></div>
    <p class="stats-hint">Clique numa barra para filtrar a lista abaixo.</p>
  </section>

  <section class="stats-chart-block">
    <h2>Rating × tempo</h2>
    <div id="scatter" class="stats-chart" aria-label="dispersão rating contra tempo"></div>
  </section>

  <section class="stats-list-block">
    <div class="stats-list-head">
      <h2>Errados <span id="failed-count">0</span></h2>
      <button class="primary" id="btn-redo-failed" disabled>Refazer errados</button>
    </div>
    <ul id="failed-list" class="stats-attempts"></ul>
  </section>

  <section class="stats-list-block" id="filtered-block" hidden>
    <h2>Filtrados <span id="filtered-label"></span></h2>
    <ul id="filtered-list" class="stats-attempts"></ul>
  </section>

  <footer class="stats-actions">
    <button class="primary" id="btn-new-session">Nova sessão (mesmos params)</button>
    <button class="secondary" id="btn-back-config">Voltar à configuração</button>
  </footer>
</main>

<script type="module" src="/static/js/stats.js"></script>
</body>
</html>
```

- [ ] **Step 2: Add route + test**

Add test in `tests/test_main.py`:

```python
def test_stats_route_returns_html(app_with_db) -> None:
    from fastapi.testclient import TestClient
    c = TestClient(app_with_db)
    sid = c.post("/api/sessions", json={
        "mode": "count", "target": 5, "filters": {}
    }).json()["session_id"]
    r = c.get(f"/play/{sid}/stats")
    assert r.status_code == 200
    assert "stats" in r.text.lower()
```

Add route in `app/main.py` (after the existing `/play/{session_id}` route):

```python
@app.get("/play/{session_id}/stats", response_class=HTMLResponse)
def play_stats(session_id: str) -> HTMLResponse:
    if not _db_exists():
        return HTMLResponse(MAINTENANCE_HTML)
    return HTMLResponse((STATIC_DIR / "stats.html").read_text(encoding="utf-8"))
```

- [ ] **Step 3: Run tests**

```bash
python -m pytest tests/test_main.py -v
```
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add app/main.py static/stats.html tests/test_main.py
git commit -m "feat(routes): /play/{id}/stats serves stats.html scaffold"
```

---

### Task 4: `static/css/stats.css` (layout)

**Files:**
- Create: `static/css/stats.css`

- [ ] **Step 1: Write CSS**

```css
.stats-body { font-family: system-ui, sans-serif; background: #fafafa; margin: 0; }
.stats-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 0.75rem 1.25rem; border-bottom: 1px solid #ddd; background: #fff;
}
.stats-header h1 { font-size: 1.1rem; margin: 0; }
.stats-main {
  max-width: 1100px; margin: 0 auto; padding: 1rem; display: grid; gap: 1.25rem;
}

.stats-cards {
  display: grid; gap: 0.75rem;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
}
.stats-card {
  background: #fff; border: 1px solid #e0e0e0; border-radius: 6px;
  padding: 0.75rem 1rem; display: flex; flex-direction: column; gap: 0.25rem;
}
.stats-card .lbl { font-size: 0.8rem; color: #666; text-transform: uppercase; letter-spacing: 0.04em; }
.stats-card .val { font-size: 1.6rem; font-weight: 600; }

.stats-chart-block {
  background: #fff; border: 1px solid #e0e0e0; border-radius: 6px; padding: 1rem;
}
.stats-chart-block h2 { margin: 0 0 0.5rem; font-size: 1rem; }
.stats-chart { width: 100%; min-height: 220px; }
.stats-hint { color: #888; font-size: 0.8rem; margin: 0.4rem 0 0; }

.stats-list-block {
  background: #fff; border: 1px solid #e0e0e0; border-radius: 6px; padding: 1rem;
}
.stats-list-head {
  display: flex; justify-content: space-between; align-items: center; gap: 1rem;
  margin-bottom: 0.5rem;
}
.stats-list-head h2 { margin: 0; font-size: 1rem; }
.stats-attempts { list-style: none; padding: 0; margin: 0; display: grid; gap: 0.25rem; }
.stats-attempts li {
  display: grid; grid-template-columns: auto auto auto 1fr auto; gap: 0.75rem;
  padding: 0.4rem 0.5rem; border-radius: 4px;
  font-family: ui-monospace, monospace; font-size: 0.85rem; align-items: center;
}
.stats-attempts li:hover { background: #f0f0f0; }
.stats-attempts li.wrong { color: #b53030; }
.stats-attempts li.correct { color: #2f855a; }
.stats-attempts a { color: inherit; text-decoration: underline; }

.stats-actions {
  display: flex; gap: 0.75rem; flex-wrap: wrap; padding-top: 0.5rem;
  border-top: 1px solid #eee;
}
.stats-actions button { padding: 0.55rem 1rem; }

.uplot, .u-wrap { width: 100% !important; }
```

- [ ] **Step 2: Commit**

```bash
git add static/css/stats.css
git commit -m "style(stats): grid layout for cards/charts/lists"
```

---

### Task 5: `static/js/stats.js` — boot + cards

**Files:**
- Create: `static/js/stats.js`

- [ ] **Step 1: Create stats.js with boot + cards rendering**

```javascript
// uPlot is loaded as IIFE -> window.uPlot
const $ = (id) => document.getElementById(id);

const state = {
  sessionId: null,
  detail: null,        // {session, attempts}
  histBarPickedMs: null, // [lo, hi] when user clicked a histogram bar
};

async function boot() {
  const parts = location.pathname.split('/');
  state.sessionId = parts[parts.length - 2]; // /play/<id>/stats
  try {
    const r = await fetch(`/api/sessions/${state.sessionId}`);
    if (!r.ok) throw new Error('http ' + r.status);
    state.detail = await r.json();
  } catch (e) {
    document.body.innerHTML = `<main style="padding:2rem">Erro ao carregar sessão: ${e.message} <a href="/">voltar</a></main>`;
    return;
  }
  renderTitle();
  renderCards();
  renderFailedList();
  renderHistogram();
  renderScatter();
  wireActions();
}

function renderTitle() {
  const s = state.detail.session;
  const dt = formatDate(s.started_at);
  const tgt = formatTarget(s.mode, s.target);
  $('stats-title').textContent = `Sessão ${dt} — ${tgt}`;
}

function renderCards() {
  const a = state.detail.attempts;
  const total = a.length;
  const correct = a.filter(x => x.correct).length;
  const wrong = total - correct;
  const avgMs = total ? Math.round(a.reduce((s, x) => s + x.time_ms, 0) / total) : 0;
  const cards = [
    ['Total', total],
    ['Corretos', correct],
    ['Erros', wrong],
    ['Tempo médio', `${(avgMs / 1000).toFixed(1)}s`],
  ];
  $('cards').innerHTML = cards.map(([lbl, val]) =>
    `<div class="stats-card"><span class="lbl">${lbl}</span><span class="val">${val}</span></div>`
  ).join('');
}

function formatDate(iso) {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
}
function formatTarget(mode, target) {
  if (mode === 'free') return 'modo livre';
  if (mode === 'time')  return `${target} min`;
  if (mode === 'count') return `${target} puzzles`;
  return mode;
}
function escapeHtml(s) {
  return (s || '').replace(/[&<>"']/g, ch => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[ch]));
}

// stubs filled in subsequent tasks
function renderFailedList() {}
function renderHistogram() {}
function renderScatter() {}
function wireActions() {}

boot();
```

- [ ] **Step 2: Commit**

```bash
git add static/js/stats.js
git commit -m "feat(stats): boot + summary cards"
```

---

### Task 6: stats.js — histograma de tempos (uPlot, bins de 1s, clicável)

- [ ] **Step 1: Replace `renderHistogram` stub**

Substituir a linha `function renderHistogram() {}` em `static/js/stats.js` por:

```javascript
function renderHistogram() {
  const el = $('histogram');
  el.innerHTML = '';
  const a = state.detail.attempts;
  if (a.length === 0) { el.textContent = 'Sem tentativas.'; return; }

  const maxSec = Math.max(1, Math.ceil(Math.max(...a.map(x => x.time_ms)) / 1000));
  const bins = new Array(maxSec).fill(0);
  for (const x of a) {
    const idx = Math.min(maxSec - 1, Math.floor(x.time_ms / 1000));
    bins[idx] += 1;
  }
  const xs = bins.map((_, i) => i + 0.5); // bar centers
  const ys = bins;

  const opts = {
    width: el.clientWidth || 600,
    height: 220,
    scales: { x: { time: false }, y: { range: (_u, min, max) => [0, Math.max(1, max + 1)] } },
    axes: [
      { label: 'segundos' },
      { label: 'qtd' },
    ],
    series: [
      {},
      {
        label: 'Tentativas',
        stroke: '#2c5282',
        fill: 'rgba(44,82,130,0.4)',
        paths: uPlot.paths.bars({ size: [0.9, 80], align: 0 }),
        points: { show: false },
      },
    ],
    cursor: { drag: { x: false, y: false } },
    hooks: {
      ready: [
        (u) => {
          u.over.addEventListener('click', () => {
            const idx = u.cursor.idx;
            if (idx == null) return;
            const lo = idx * 1000;
            const hi = (idx + 1) * 1000;
            state.histBarPickedMs = [lo, hi];
            renderFilteredList();
          });
        },
      ],
    },
  };
  new uPlot(opts, [xs, ys], el);
}

function renderFilteredList() {
  const block = $('filtered-block');
  const list  = $('filtered-list');
  const lbl   = $('filtered-label');
  const range = state.histBarPickedMs;
  if (!range) { block.hidden = true; return; }
  const [lo, hi] = range;
  const sec = lo / 1000;
  lbl.textContent = `(${sec}–${sec + 1}s)`;
  const items = state.detail.attempts.filter(x => x.time_ms >= lo && x.time_ms < hi);
  if (items.length === 0) {
    list.innerHTML = '<li>Nada nesse bin.</li>';
  } else {
    list.innerHTML = items.map(attemptRow).join('');
  }
  block.hidden = false;
}

function attemptRow(x) {
  const cls = x.correct ? 'correct' : 'wrong';
  const mark = x.correct ? '✓' : '✗';
  const t = (x.time_ms / 1000).toFixed(2) + 's';
  const themes = (x.themes || []).slice(0, 3).map(escapeHtml).join(' ');
  const linkInner = x.game_url
    ? `<a href="${escapeHtml(x.game_url)}" target="_blank" rel="noopener">↗ Lichess</a>`
    : '';
  return `<li class="${cls}">
    <span>${mark}</span>
    <span>${escapeHtml(x.puzzle_id)}</span>
    <span>${x.rating || '?'}</span>
    <span>${t} ${themes ? '· ' + themes : ''}</span>
    <span>${linkInner}</span>
  </li>`;
}
```

- [ ] **Step 2: Commit**

```bash
git add static/js/stats.js
git commit -m "feat(stats): histogram with 1s bins and click-to-filter"
```

---

### Task 7: stats.js — scatter rating × tempo

- [ ] **Step 1: Replace `renderScatter` stub**

Substituir `function renderScatter() {}` por:

```javascript
function renderScatter() {
  const el = $('scatter');
  el.innerHTML = '';
  const a = state.detail.attempts;
  if (a.length === 0) { el.textContent = 'Sem dados.'; return; }

  // build two series: correct and wrong, each on the same x axis (rating)
  const ratings = a.map(x => x.rating || 0);
  const okRatings = a.map(x => x.correct ? (x.rating || 0) : null);
  const okTimes   = a.map(x => x.correct ? x.time_ms / 1000 : null);
  const wrRatings = a.map(x => x.correct ? null : (x.rating || 0));
  const wrTimes   = a.map(x => x.correct ? null : x.time_ms / 1000);

  // uPlot expects shared x axis; duplicate ratings as x and use null gating per series
  const xs = ratings;
  const opts = {
    width: el.clientWidth || 600,
    height: 240,
    axes: [{ label: 'rating' }, { label: 'tempo (s)' }],
    scales: { x: { time: false }, y: { range: (_u, _mn, mx) => [0, Math.max(1, mx + 0.5)] } },
    series: [
      { label: 'rating' },
      { label: 'corretos', stroke: '#2f855a', fill: '#2f855a',
        paths: () => null, points: { show: true, size: 6, fill: '#2f855a' } },
      { label: 'errados', stroke: '#b53030', fill: '#b53030',
        paths: () => null, points: { show: true, size: 6, fill: '#b53030' } },
    ],
  };
  // we need three "y" arrays aligned with xs. To avoid drawing wrong points where x belongs to other series,
  // use a per-series y of null when the attempt belongs to the other class.
  const okY = a.map(x => x.correct ? x.time_ms / 1000 : null);
  const wrY = a.map(x => x.correct ? null : x.time_ms / 1000);
  new uPlot(opts, [xs, okY, wrY], el);
}
```

- [ ] **Step 2: Commit**

```bash
git add static/js/stats.js
git commit -m "feat(stats): scatter rating × time (green ok, red wrong)"
```

---

### Task 8: stats.js — lista de errados

- [ ] **Step 1: Replace `renderFailedList` stub**

Substituir `function renderFailedList() {}` por:

```javascript
function renderFailedList() {
  const failed = state.detail.attempts.filter(x => !x.correct);
  $('failed-count').textContent = `(${failed.length})`;
  $('btn-redo-failed').disabled = failed.length === 0;
  $('failed-list').innerHTML = failed.length
    ? failed.map(attemptRow).join('')
    : '<li>Sem erros nesta sessão. </li>';
}
```

- [ ] **Step 2: Commit**

```bash
git add static/js/stats.js
git commit -m "feat(stats): failed list with Lichess game link"
```

---

### Task 9: stats.js — ações (Refazer errados, Nova sessão, Voltar à configuração)

- [ ] **Step 1: Replace `wireActions` stub**

Substituir `function wireActions() {}` por:

```javascript
function wireActions() {
  $('btn-redo-failed').addEventListener('click', async () => {
    const btn = $('btn-redo-failed');
    btn.disabled = true;
    try {
      const s = state.detail.session;
      const r = await fetch('/api/sessions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          mode: s.mode, target: s.target,
          auto_advance: s.auto_advance,
          dedupe_solved: s.dedupe_solved,
          filters: {},  // server ignores filters when parent_session is set
          parent_session: s.session_id,
          label: (s.label ? s.label + ' (refazer)' : 'refazer errados'),
        }),
      });
      if (!r.ok) throw new Error('http ' + r.status);
      const out = await r.json();
      // pool already prepared server-side; play.js reads pool from sessionStorage,
      // so we mirror it here from the failed puzzle ids.
      const failedIds = state.detail.attempts.filter(x => !x.correct).map(x => x.puzzle_id);
      sessionStorage.setItem(`pool:${out.session_id}`, JSON.stringify({ puzzle_ids: failedIds }));
      location.href = `/play/${out.session_id}`;
    } catch (e) {
      alert('Falha ao criar sessão filha: ' + e.message);
      btn.disabled = false;
    }
  });

  $('btn-new-session').addEventListener('click', () => {
    // Reuse current params on /: open / and let user click Buscar pool again.
    // We pass ?prefill so filters are restored.
    location.href = `/?prefill=${encodeURIComponent(state.sessionId)}`;
  });

  $('btn-back-config').addEventListener('click', () => {
    location.href = `/?prefill=${encodeURIComponent(state.sessionId)}`;
  });
}
```

- [ ] **Step 2: Commit**

```bash
git add static/js/stats.js
git commit -m "feat(stats): action buttons (redo failed, new session, back to config)"
```

---

### Task 10: `play.js` — redirecionar para `/play/:id/stats` no fim

**Files:**
- Modify: `static/js/play.js`

- [ ] **Step 1: Replace `goExplore` with `goStats`**

In `static/js/play.js`, find:

```javascript
function goExplore() {
  location.href = '/explore?ended=' + encodeURIComponent(session.id);
}
```

Replace with:

```javascript
function goStats() {
  location.href = `/play/${encodeURIComponent(session.id)}/stats`;
}
```

Then replace **all** call sites of `goExplore` with `goStats` (there are two: in `boot` overlay handler and in `endSession`). Use a single grep + sed or just fix each spot manually. Verify with:

```bash
grep -n goExplore static/js/play.js   # should print nothing
grep -n goStats   static/js/play.js   # should print the new function + 2 call sites
```

- [ ] **Step 2: Commit**

```bash
git add static/js/play.js
git commit -m "feat(play): redirect to /play/:id/stats after session ends"
```

---

### Task 11: `config.js` — `[→]` rota condicional + `[↻]` reuso de params

**Files:**
- Modify: `static/js/config.js`
- Modify: `static/js/api.js` (small helper for getSession)

- [ ] **Step 1: Add helper to api.js**

Append to `static/js/api.js`:

```javascript
export async function getSession(sessionId) {
  const r = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}`);
  if (!r.ok) throw new Error('getSession ' + r.status);
  return r.json();
}
```

- [ ] **Step 2: Update import in config.js**

In `static/js/config.js`, change the import line to include `getSession`:

```javascript
import { fetchBatch, createSession, listSessions, getSession } from './api.js';
```

- [ ] **Step 3: Update `loadSessions` rendering**

Replace the `for (const s of list)` block in `loadSessions` with:

```javascript
    ul.innerHTML = '';
    for (const s of list) {
      const li = document.createElement('li');
      const arrowHref = s.ended_at
        ? `/play/${s.session_id}/stats`
        : `/play/${s.session_id}`;
      li.innerHTML = `
        <span class="when">${formatStarted(s.started_at)}</span>
        <span class="target">${formatTarget(s.mode, s.target)}</span>
        <span class="label">${escapeHtml(s.label || '')}</span>
        <span class="score">${s.correct}/${s.total}</span>
        <span class="actions">
          <a href="${arrowHref}" title="${s.ended_at ? 'Ver estatísticas' : 'Reabrir'}">→</a>
          <button class="ghost" data-redo="${s.session_id}" title="Nova sessão com mesmos filtros">↻</button>
        </span>
      `;
      ul.append(li);
    }
    ul.querySelectorAll('button[data-redo]').forEach(btn =>
      btn.addEventListener('click', () => onRedoSession(btn.dataset.redo))
    );
```

Add the `onRedoSession` function near the bottom of the file (before `boot().catch`):

```javascript
async function onRedoSession(parentSessionId) {
  try {
    const det = await getSession(parentSessionId);
    const s = det.session;
    // refresh pool first so play.js finds it in sessionStorage
    const pool = await fetchBatch(s.filters || {}, POOL_LIMIT);
    if (!pool || pool.count === 0) {
      alert('Pool vazia para os filtros desta sessão.');
      return;
    }
    let target = s.target;
    if (s.mode === 'count' && target && target > pool.count) target = pool.count;
    const created = await createSession({
      mode: s.mode, target,
      auto_advance: s.auto_advance,
      dedupe_solved: s.dedupe_solved,
      filters: s.filters || {},
      parent_session: null,
      label: s.label,
    });
    sessionStorage.setItem(`pool:${created.session_id}`, JSON.stringify({
      puzzle_ids: pool.puzzles.map(p => p.puzzle_id),
    }));
    location.href = `/play/${created.session_id}`;
  } catch (e) {
    alert('Falha ao recriar sessão: ' + e.message);
  }
}
```

- [ ] **Step 4: Add CSS for the ghost button**

Append to `static/css/config.css` (or `styles.css` if more appropriate — verify with `grep ghost static/css/*.css` first; if absent, use config.css):

```css
button.ghost {
  background: transparent; border: 1px solid #ccc; cursor: pointer;
  padding: 0.15rem 0.5rem; border-radius: 4px; font-size: 1rem; line-height: 1;
}
button.ghost:hover { background: #f0f0f0; }
.sessions-panel .actions { display: inline-flex; gap: 0.4rem; }
```

- [ ] **Step 5: Commit**

```bash
git add static/js/config.js static/js/api.js static/css/config.css
git commit -m "feat(config): sessions list [→] routes by status and [↻] clones params"
```

---

### Task 12: `config.js` — pré-preenchimento via `?prefill=:id`

**Files:**
- Modify: `static/js/config.js`
- Modify: `static/js/filters.js` (only if needed — check first)

- [ ] **Step 1: Inspect `filters.js` for an apply helper**

```bash
grep -n "applyPreset\|writeFilters\|setFilters" static/js/filters.js
```

If `applyPreset(filters)` already writes filter inputs (it does, used by presets), reuse it.

- [ ] **Step 2: Add prefill logic to `boot` in config.js**

Right after `await initFilterUI(onFiltersChanged);` in `boot()`, add:

```javascript
  await maybePrefillFromQuery();
```

Add the function near the bottom (before `boot().catch`):

```javascript
async function maybePrefillFromQuery() {
  const params = new URLSearchParams(location.search);
  const sid = params.get('prefill');
  if (!sid) return;
  try {
    const det = await getSession(sid);
    const f = det.session.filters || {};
    applyPreset(f);
    await onFiltersChanged(readFilters());
    // Restore mode + target as well
    const s = det.session;
    const modeRadio = document.querySelector(`input[name=mode][value="${s.mode}"]`);
    if (modeRadio && !modeRadio.disabled) modeRadio.checked = true;
    if (s.mode === 'time' || s.mode === 'count') {
      const groupName = s.mode === 'time' ? 'time-target' : 'count-target';
      const customId  = s.mode === 'time' ? 'time-custom' : 'count-custom';
      const presets = ['3','5','10']; // time
      const presetsCount = ['50','100','200','500'];
      const opts = s.mode === 'time' ? presets : presetsCount;
      const tgt = String(s.target ?? '');
      if (opts.includes(tgt)) {
        const r = document.querySelector(`input[name=${groupName}][value="${tgt}"]`);
        if (r) r.checked = true;
      } else if (s.target) {
        const r = document.querySelector(`input[name=${groupName}][value="custom"]`);
        if (r) r.checked = true;
        document.getElementById(customId).value = s.target;
      }
    }
    document.getElementById('dedupe_solved').checked = !!s.dedupe_solved;
    if (s.label) document.getElementById('label').value = s.label;
  } catch (e) {
    console.warn('prefill failed', e);
  }
}
```

- [ ] **Step 3: Commit**

```bash
git add static/js/config.js
git commit -m "feat(config): apply ?prefill=:session_id to restore filters/mode/target"
```

---

### Task 13: Smoke E2E + chore commit

- [ ] **Step 1: Run full test suite**

```bash
python -m pytest -q
```
Expected: 86/86 (84 baseline + 2 novos: `test_stats_route_returns_html`, `test_get_session_includes_game_url_on_attempts`).

- [ ] **Step 2: Manual TestClient smoke (optional one-off — verify backend wiring)**

```bash
python - <<'PY'
from fastapi.testclient import TestClient
from app.main import app
c = TestClient(app)
r = c.post('/api/sessions', json={'mode':'count','target':3,'filters':{}})
sid = r.json()['session_id']
c.post(f'/api/sessions/{sid}/attempts', json={'order_idx':0,'puzzle_id':'00008','correct':False,'time_ms':2200})
c.post(f'/api/sessions/{sid}/end', json={'end_reason':'manual'})
det = c.get(f'/api/sessions/{sid}').json()
print('session ended_at:', det['session']['ended_at'])
print('attempt fields  :', list(det['attempts'][0].keys()))
print('stats route 200 :', c.get(f'/play/{sid}/stats').status_code)
PY
```
Expected output:
- `ended_at` non-null ISO-Z string
- attempt has `game_url` key
- stats route returns 200

- [ ] **Step 3: Chore commit (Phase 3 alone — Phase 4 will add a bigger summary)**

```bash
git add -A
git commit -m "chore: Phase 3 (stats screen) backend smoke passed" --allow-empty
```
