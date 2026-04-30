# Phase 4 — Free mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Habilitar `mode=free` no fluxo: sem término automático, com checkbox "Avanço manual" controlando `auto_advance`. Quando `mode=free && auto_advance=false`, exibir painel lateral pós-outcome com `[Próximo]`, `[Tentar de novo]` (se errou), navegação de variante (`[Início][Anterior][Próximo▶][Fim]`) e checkbox **Sandbox**. Atalhos: `←/→` variant nav, `n` próximo, `r` retry.

**Architecture:** Backend já aceita `mode=free` e `auto_advance=false` (forçado a `true` em `time/count`). Trabalho é frontend puro: configurações, máquina de estados em `play.js` e UI lateral em `play.html`. Variante navegada via array de FENs gerados a partir de `puzzle.moves`.

**Tech Stack:** chessground + chess.js (já vendored via esm.sh).

**Baseline:** Phase 3 verde (testes 86/86), commit anterior `chore: Phase 3 (stats screen) backend smoke passed`.

---

### Task 1: Habilitar radio "Modo livre" em `index.html`

**Files:**
- Modify: `static/index.html`

- [ ] **Step 1: Replace the disabled radio**

Find:

```html
      <label><input type="radio" name="mode" value="free" disabled> Modo livre <em>(Fase 4)</em></label>
```

Replace with:

```html
      <label><input type="radio" name="mode" value="free"> Modo livre</label>
      <div class="mode-options" id="opts-free">
        <label><input type="checkbox" id="free-manual-advance"> Avanço manual (próximo lance e explorar livremente)</label>
      </div>
```

- [ ] **Step 2: Commit**

```bash
git add static/index.html
git commit -m "feat(config): enable free mode radio with manual-advance toggle"
```

---

### Task 2: `config.js` — usar `mode=free` + `auto_advance` na criação

**Files:**
- Modify: `static/js/config.js`

- [ ] **Step 1: In `onStart`, derive `auto_advance` for free mode**

Find the `createSession({...})` call inside `onStart`. Replace the `auto_advance: true,` line so the value depends on mode:

Before:
```javascript
    const created = await createSession({
      mode,
      target: effectiveTarget,
      auto_advance: true,
      dedupe_solved: dedupe,
```

After:
```javascript
    const manualAdvance = !!document.getElementById('free-manual-advance')?.checked;
    const autoAdvance = mode === 'free' ? !manualAdvance : true;
    const created = await createSession({
      mode,
      target: effectiveTarget,
      auto_advance: autoAdvance,
      dedupe_solved: dedupe,
```

- [ ] **Step 2: Show/hide `#opts-free` block based on mode**

In `boot()`, after the existing `document.querySelectorAll('input[name=mode]')...` listener, add:

```javascript
  syncModeOptionsVisibility();
  document.querySelectorAll('input[name=mode]').forEach(r =>
    r.addEventListener('change', syncModeOptionsVisibility));
```

Add helper near the bottom (before `boot().catch`):

```javascript
function syncModeOptionsVisibility() {
  const mode = readMode();
  const ids = { time: 'opts-time', count: 'opts-count', free: 'opts-free' };
  for (const [m, id] of Object.entries(ids)) {
    const el = document.getElementById(id);
    if (el) el.style.display = (m === mode) ? '' : 'none';
  }
}
```

- [ ] **Step 3: Allow free mode in `refreshStartEnabled` (already handles `targetOk` with `mode === 'free'`; verify and tweak only if buggy)**

Reconfirme reading `refreshStartEnabled`: `targetOk = mode === 'free' || (target !== null && target > 0);` — já está correto. Sem mudanças.

- [ ] **Step 4: Commit**

```bash
git add static/js/config.js
git commit -m "feat(config): wire free mode + manual-advance toggle into session creation"
```

---

### Task 3: `play.js` — construir `variantHistory` ao carregar puzzle

**Files:**
- Modify: `static/js/play.js`

- [ ] **Step 1: Add `variantHistory` and `variantCursor` to `ui` state**

Find the `const ui = { ... }` block near the top and add fields:

```javascript
const ui = {
  board: null,
  chess: null,
  puzzle: null,
  moveIndex: 0,
  exerciseStartedAt: 0,
  state: 'IDLE',
  variantHistory: [],   // [{fen, lastMove}], full solution path snapshots
  variantCursor: 0,
  postOpponentFen: null, // FEN right after OPPONENT_MOVE (for retry rollback)
  postOpponentLastMove: null,
  sandboxOn: false,
};
```

- [ ] **Step 2: Populate `variantHistory` in `loadNextPuzzle`**

Inside `loadNextPuzzle`, after `ui.chess = new Chess(ui.puzzle.fen);`, build the variant from the official solution moves. Replace:

```javascript
      ui.puzzle = await loadPuzzleById(id);
      ui.chess = new Chess(ui.puzzle.fen);
      ui.moveIndex = 0;
      startPreview();
      return;
```

With:

```javascript
      ui.puzzle = await loadPuzzleById(id);
      ui.chess = new Chess(ui.puzzle.fen);
      ui.moveIndex = 0;
      ui.variantHistory = buildVariantHistory(ui.puzzle.fen, ui.puzzle.moves);
      ui.variantCursor = 0;
      ui.postOpponentFen = null;
      ui.postOpponentLastMove = null;
      ui.sandboxOn = false;
      startPreview();
      return;
```

Add the helper after `loadPuzzleById`:

```javascript
function buildVariantHistory(startFen, movesStr) {
  const tmp = new Chess(startFen);
  const out = [{ fen: tmp.fen(), lastMove: null }];
  for (const uci of movesStr.split(' ').filter(Boolean)) {
    const move = tmp.move({ from: uci.slice(0, 2), to: uci.slice(2, 4), promotion: uci[4] });
    if (!move) break;
    out.push({ fen: tmp.fen(), lastMove: [uci.slice(0, 2), uci.slice(2, 4)] });
  }
  return out;
}
```

- [ ] **Step 3: Capture `postOpponentFen` after the opponent's move**

In `startOpponentMove`, after `ui.chess.move(...)` and before `ui.board.set(...)`, add:

```javascript
  ui.postOpponentFen = ui.chess.fen();
  ui.postOpponentLastMove = [uci.slice(0,2), uci.slice(2,4)];
```

- [ ] **Step 4: Commit**

```bash
git add static/js/play.js
git commit -m "feat(play): build variant history and capture post-opponent state for free mode"
```

---

### Task 4: `play.html` + `play.css` — painel lateral

**Files:**
- Modify: `static/play.html`
- Modify: `static/css/play.css`

- [ ] **Step 1: Add side panel HTML**

In `static/play.html`, inside `<main class="play-board-wrap">`, after `<div id="flash" .../>`, add:

```html
    <aside class="play-side" id="side-panel" hidden>
      <button class="primary" id="btn-next-free">Próximo exercício</button>
      <button class="secondary" id="btn-retry" hidden>Tentar de novo</button>
      <div class="play-side-block">
        <strong>Variante</strong>
        <div class="variant-nav">
          <button data-variant="start" title="Início">⏮</button>
          <button data-variant="prev"  title="Anterior">◀</button>
          <button data-variant="next"  title="Próximo">▶</button>
          <button data-variant="end"   title="Fim">⏭</button>
        </div>
        <div class="variant-pos" id="variant-pos">0 / 0</div>
      </div>
      <label class="play-side-block">
        <input type="checkbox" id="sandbox"> Sandbox (mover livremente)
      </label>
    </aside>
```

- [ ] **Step 2: Append CSS**

Append to `static/css/play.css`:

```css
.play-board-wrap { position: relative; display: grid; grid-template-columns: 1fr; }
@media (min-width: 900px) {
  .play-board-wrap.with-side { grid-template-columns: 1fr 220px; gap: 1rem; }
}
.play-side {
  background: rgba(255,255,255,0.04); color: #ddd;
  border-radius: 6px; padding: 1rem; display: grid; gap: 0.75rem;
  align-self: start; min-width: 200px;
}
.play-side button {
  width: 100%; padding: 0.5rem 0.75rem; border-radius: 4px;
  border: 1px solid #555; background: #2b2b2b; color: #eee; cursor: pointer;
}
.play-side button.primary   { background: #2c5282; border-color: #2c5282; }
.play-side button.secondary { background: #4a4a4a; }
.play-side-block { display: grid; gap: 0.4rem; font-size: 0.85rem; }
.variant-nav { display: grid; grid-template-columns: repeat(4, 1fr); gap: 0.25rem; }
.variant-nav button { padding: 0.35rem; }
.variant-pos { font-family: ui-monospace, monospace; color: #aaa; font-size: 0.8rem; }
```

- [ ] **Step 3: Commit**

```bash
git add static/play.html static/css/play.css
git commit -m "ui(play): side panel scaffold (next/retry/variant/sandbox)"
```

---

### Task 5: `play.js` — gating do painel + estado `OUTCOME_FREE`

**Files:**
- Modify: `static/js/play.js`

- [ ] **Step 1: Add helper to detect free-manual mode**

Near the top of `play.js`, add:

```javascript
function isFreeManual() {
  return session.meta && session.meta.mode === 'free' && !session.meta.auto_advance;
}
```

- [ ] **Step 2: Add helper to show/hide the panel**

Add:

```javascript
function setSidePanel(visible, opts = {}) {
  const panel = document.getElementById('side-panel');
  const wrap  = document.querySelector('.play-board-wrap');
  panel.hidden = !visible;
  wrap.classList.toggle('with-side', visible);
  document.getElementById('btn-retry').hidden = !visible || !opts.canRetry;
  document.getElementById('variant-pos').textContent =
    `${ui.variantCursor} / ${Math.max(0, ui.variantHistory.length - 1)}`;
}
```

- [ ] **Step 3: Replace the auto-advance scheduling in `registerCorrectAndAdvance` and `registerWrongAndAdvance`**

Replace:

```javascript
function registerCorrectAndAdvance() {
  recordAttempt(true);
  setFlash('✓', 'ok');
  ui.state = 'OUTCOME';
  setTimeout(loadNextPuzzle, 350);
}

function registerWrongAndAdvance() {
  recordAttempt(false);
  setFlash('✗', 'err');
  const wrap = document.querySelector('.play-board-wrap');
  wrap.classList.add('shake');
  setTimeout(() => wrap.classList.remove('shake'), 250);
  ui.state = 'OUTCOME';
  setTimeout(loadNextPuzzle, 600);
}
```

With:

```javascript
function registerCorrectAndAdvance() {
  recordAttempt(true);
  setFlash('✓', 'ok');
  if (isFreeManual()) {
    ui.state = 'OUTCOME_FREE';
    ui.variantCursor = ui.variantHistory.length - 1;
    setSidePanel(true, { canRetry: false });
    return;
  }
  ui.state = 'OUTCOME';
  setTimeout(loadNextPuzzle, 350);
}

function registerWrongAndAdvance() {
  recordAttempt(false);
  setFlash('✗', 'err');
  const wrap = document.querySelector('.play-board-wrap');
  wrap.classList.add('shake');
  setTimeout(() => wrap.classList.remove('shake'), 250);
  if (isFreeManual()) {
    ui.state = 'OUTCOME_FREE';
    ui.variantCursor = 1; // post-OPPONENT_MOVE position in variantHistory
    setSidePanel(true, { canRetry: true });
    return;
  }
  ui.state = 'OUTCOME';
  setTimeout(loadNextPuzzle, 600);
}
```

- [ ] **Step 4: In `loadNextPuzzle`, hide side panel and reset sandbox**

Insert at the top of `loadNextPuzzle`, before the `while` loop:

```javascript
  setSidePanel(false);
  const sb = document.getElementById('sandbox');
  if (sb) sb.checked = false;
```

- [ ] **Step 5: Free mode never auto-terminates by count or time**

Find the `if (session.meta.mode === 'count' && ...)` block in `recordAttempt`. Wrap so it only fires for non-free modes — replace:

```javascript
  if (session.meta.mode === 'count') {
```

With:

```javascript
  if (session.meta.mode === 'count' && !isFreeManual()) {
```

(`session.meta.mode === 'count'` already excludes `free`, so the change is mostly defensive — but for free mode the count termination shouldn't fire anyway. Skip the change if `mode==='count'` is already the only guard. Verify.)

In `startClockLoop`, keep the time check guarded by `session.meta.mode === 'time'` (already in the code). Free mode counts up forever, fine as-is.

- [ ] **Step 6: Commit**

```bash
git add static/js/play.js
git commit -m "feat(play): OUTCOME_FREE state and side-panel gating"
```

---

### Task 6: `play.js` — handlers `[Próximo]` e `[Tentar de novo]`

- [ ] **Step 1: Wire buttons in `boot()`**

In `boot()`, after `document.getElementById('btn-quit').addEventListener(...)`, add:

```javascript
  document.getElementById('btn-next-free').addEventListener('click', onNextFree);
  document.getElementById('btn-retry').addEventListener('click', onRetry);
  document.getElementById('sandbox').addEventListener('change', onSandboxToggle);
  document.querySelectorAll('.variant-nav button').forEach(b =>
    b.addEventListener('click', () => onVariantNav(b.dataset.variant)));
  document.addEventListener('keydown', onKeydown);
```

- [ ] **Step 2: Add handlers**

Add near the bottom of the file, before `boot().catch`:

```javascript
function onNextFree() {
  if (ui.state !== 'OUTCOME_FREE') return;
  setSidePanel(false);
  loadNextPuzzle();
}

function onRetry() {
  if (ui.state !== 'OUTCOME_FREE' || ui.postOpponentFen == null) return;
  // rebuild the chess engine to the post-opponent state and re-arm USER_TURN.
  ui.chess = new Chess(ui.postOpponentFen);
  ui.moveIndex = 1; // moves[0] was the opponent move
  ui.board.set({
    fen: ui.postOpponentFen,
    lastMove: ui.postOpponentLastMove || undefined,
    drawable: { autoShapes: [] },
  });
  setSidePanel(false);
  setFlash('');
  armUserTurn();
}
```

- [ ] **Step 3: Commit**

```bash
git add static/js/play.js
git commit -m "feat(play): free-mode next/retry without re-recording attempt"
```

---

### Task 7: `play.js` — navegação de variante

- [ ] **Step 1: Add `onVariantNav`**

```javascript
function onVariantNav(action) {
  if (ui.state !== 'OUTCOME_FREE') return;
  const last = ui.variantHistory.length - 1;
  if (last < 0) return;
  if (action === 'start') ui.variantCursor = 0;
  else if (action === 'end')  ui.variantCursor = last;
  else if (action === 'prev') ui.variantCursor = Math.max(0, ui.variantCursor - 1);
  else if (action === 'next') ui.variantCursor = Math.min(last, ui.variantCursor + 1);
  paintVariantCursor();
}

function paintVariantCursor() {
  const snap = ui.variantHistory[ui.variantCursor];
  if (!snap) return;
  ui.board.set({
    fen: snap.fen,
    lastMove: snap.lastMove || undefined,
    movable: ui.sandboxOn
      ? { color: 'both', free: true, dests: new Map() }
      : { color: null, dests: new Map() },
  });
  document.getElementById('variant-pos').textContent =
    `${ui.variantCursor} / ${Math.max(0, ui.variantHistory.length - 1)}`;
}
```

- [ ] **Step 2: Commit**

```bash
git add static/js/play.js
git commit -m "feat(play): variant navigation buttons (start/prev/next/end)"
```

---

### Task 8: `play.js` — Sandbox toggle

- [ ] **Step 1: Add `onSandboxToggle`**

```javascript
function onSandboxToggle(ev) {
  if (ui.state !== 'OUTCOME_FREE') {
    ev.target.checked = false;
    return;
  }
  ui.sandboxOn = !!ev.target.checked;
  if (ui.sandboxOn) {
    ui.board.set({
      movable: { color: 'both', free: true, dests: new Map() },
      draggable: { showGhost: true },
    });
  } else {
    paintVariantCursor(); // restores the variant snapshot at cursor
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add static/js/play.js
git commit -m "feat(play): sandbox checkbox (free-form moves, restores on uncheck)"
```

---

### Task 9: `play.js` — atalhos de teclado

- [ ] **Step 1: Add `onKeydown`**

```javascript
function onKeydown(ev) {
  if (ui.state !== 'OUTCOME_FREE') {
    if (ev.key === 'Escape') onQuit();
    return;
  }
  if (ev.key === 'ArrowLeft')  { ev.preventDefault(); onVariantNav('prev'); return; }
  if (ev.key === 'ArrowRight') { ev.preventDefault(); onVariantNav('next'); return; }
  if (ev.key === 'n' || ev.key === 'N') { ev.preventDefault(); onNextFree(); return; }
  if (ev.key === 'r' || ev.key === 'R') {
    ev.preventDefault();
    if (!document.getElementById('btn-retry').hidden) onRetry();
    return;
  }
  if (ev.key === 'Escape') onQuit();
}
```

- [ ] **Step 2: Commit**

```bash
git add static/js/play.js
git commit -m "feat(play): keyboard shortcuts (←/→ variant, n next, r retry, Esc quit)"
```

---

### Task 10: Smoke E2E + chore commit final

- [ ] **Step 1: Run full test suite**

```bash
python -m pytest -q
```
Expected: 86/86 still passing (Phase 4 is pure frontend; no test churn).

- [ ] **Step 2: Backend smoke for free mode session creation**

```bash
python - <<'PY'
from fastapi.testclient import TestClient
from app.main import app
c = TestClient(app)

# free + manual advance
r = c.post('/api/sessions', json={
    'mode':'free','target':None,'auto_advance':False,'filters':{},'label':'free manual'
})
assert r.status_code == 201, r.text
sid = r.json()['session_id']
det = c.get(f'/api/sessions/{sid}').json()['session']
assert det['mode'] == 'free'
assert det['auto_advance'] is False, det
assert det['target'] is None
print('free+manual OK', sid)

# free + auto advance
r = c.post('/api/sessions', json={
    'mode':'free','target':None,'auto_advance':True,'filters':{}
})
assert r.status_code == 201
det = c.get(f'/api/sessions/{r.json()["session_id"]}').json()['session']
assert det['mode'] == 'free' and det['auto_advance'] is True
print('free+auto OK')

# time mode forces auto_advance=True even if client tries to disable
r = c.post('/api/sessions', json={
    'mode':'time','target':3,'auto_advance':False,'filters':{}
})
det = c.get(f'/api/sessions/{r.json()["session_id"]}').json()['session']
assert det['auto_advance'] is True, det
print('time forces auto_advance=True OK')
PY
```

Expected: 3 OK lines, no AssertionError.

- [ ] **Step 3: Final chore commit**

```bash
git add -A
git commit -m "chore: Phase 3+4 backend smoke passed

Phase 3 (stats screen) — validated via TestClient:
- AttemptDetail now exposes game_url (regression test added)
- /play/{id}/stats route serves stats.html (test added)
- 86/86 backend tests green

Phase 4 (free mode) — validated via TestClient:
- POST /api/sessions accepts mode=free + auto_advance=false
- POST /api/sessions with mode=time/count still forces auto_advance=true
- GET /api/sessions/{id} round-trips the auto_advance flag

Frontend pieces requiring browser walkthrough:
- /play/:id/stats: cards, histogram (1s bins, click filters), scatter
  rating×time, failed list, [Refazer errados], [Nova sessão], [Voltar]
- / (config): [→] routes to /stats vs /play based on ended_at; [↻]
  clones session params; ?prefill=:id restores filters/mode/target
- /play/:id (free + manual): side panel with [Próximo], [Tentar de novo]
  (only after wrong), variant nav [⏮ ◀ ▶ ⏭], Sandbox checkbox
- Keyboard: ←/→ variant, n next, r retry, Esc quit" --allow-empty
```
