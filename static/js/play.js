import { Chessground } from 'chessground';
import { Chess } from 'chess.js';

const STORAGE_KEY = (sessionId) => `pool:${sessionId}`;

const session = {
  id: null,
  meta: null,
  pool: [],
  poolIdx: 0,
  attempts: [],
  ended: false,
};

const ui = {
  board: null,
  chess: null,
  puzzle: null,
  moveIndex: 0,
  exerciseStartedAt: 0,
  state: 'IDLE',
  variantHistory: [],
  variantCursor: 0,
  postOpponentFen: null,
  postOpponentLastMove: null,
  sandboxOn: false,
};

const clock = { startedAt: 0, raf: 0 };
const solvedThisSession = new Set();

async function boot() {
  session.id = location.pathname.split('/').pop();

  const meta = await fetchSession(session.id);
  const stored = JSON.parse(sessionStorage.getItem(STORAGE_KEY(session.id)) || 'null');

  session.meta = meta.session;
  if (session.meta.ended_at) {
    return showOverlay('Esta sessão já está encerrada.', 'Voltar', goStats);
  }
  if (!stored || !Array.isArray(stored.puzzle_ids) || stored.puzzle_ids.length === 0) {
    return showOverlay(
      'Pool não encontrada para esta sessão. Volte e clique em "Buscar pool" novamente.',
      'Voltar', () => location.href = '/'
    );
  }
  session.pool = stored.puzzle_ids;

  ui.board = Chessground(document.getElementById('board'), {
    movable: { free: false, color: null, events: { after: onUserMove } },
    draggable: { showGhost: true },
  });

  document.getElementById('btn-quit').addEventListener('click', onQuit);
  document.getElementById('btn-next-free')?.addEventListener('click', onNextFree);
  document.getElementById('btn-retry')?.addEventListener('click', onRetry);
  document.getElementById('sandbox')?.addEventListener('change', onSandboxToggle);
  document.querySelectorAll('.variant-nav button').forEach(b =>
    b.addEventListener('click', () => onVariantNav(b.dataset.variant)));
  document.addEventListener('keydown', onKeydown);
  renderCounter();
  startClockLoop();
  await loadNextPuzzle();
}

function startClockLoop() {
  clock.startedAt = performance.now();
  const tick = () => {
    if (session.ended) return;
    const elapsed = performance.now() - clock.startedAt;
    renderClock(elapsed);
    if (session.meta.mode === 'time' &&
        elapsed >= session.meta.target * 60_000) {
      endSession('time');
      return;
    }
    clock.raf = requestAnimationFrame(tick);
  };
  clock.raf = requestAnimationFrame(tick);
}

async function fetchSession(id) {
  const r = await fetch(`/api/sessions/${id}`);
  if (!r.ok) throw new Error('session ' + r.status);
  return r.json();
}

async function loadPuzzleById(id) {
  const r = await fetch(`/api/puzzles/${id}`);
  if (!r.ok) throw new Error('puzzle ' + r.status);
  return r.json();
}

async function loadNextPuzzle() {
  setSidePanel(false);
  const sb = document.getElementById('sandbox');
  if (sb) sb.checked = false;
  while (session.poolIdx < session.pool.length) {
    const id = session.pool[session.poolIdx++];
    if (session.meta.dedupe_solved && solvedThisSession.has(id)) continue;
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
  }
  if (session.meta.mode !== 'free') endSession('count');
}

function setSidePanel(visible, opts = {}) {
  const panel = document.getElementById('side-panel');
  const wrap  = document.querySelector('.play-board-wrap');
  if (!panel || !wrap) return;
  panel.hidden = !visible;
  wrap.classList.toggle('with-side', visible);
  const retryBtn = document.getElementById('btn-retry');
  if (retryBtn) retryBtn.hidden = !visible || !opts.canRetry;
  const pos = document.getElementById('variant-pos');
  if (pos) pos.textContent = `${ui.variantCursor} / ${Math.max(0, ui.variantHistory.length - 1)}`;
}

function isFreeManual() {
  return session.meta && session.meta.mode === 'free' && !session.meta.auto_advance;
}

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

function startPreview() {
  const oppColor = ui.puzzle.side_to_move === 'w' ? 'white' : 'black';
  const userColor = oppColor === 'white' ? 'black' : 'white';
  ui.board.set({
    fen: ui.chess.fen(),
    turnColor: oppColor,
    orientation: userColor,
    movable: { color: null, dests: new Map() },
    lastMove: undefined,
    drawable: { autoShapes: [] },
  });
  ui.state = 'PREVIEW';
  setFlash('');
  setTimeout(startOpponentMove, 400);
}

function startOpponentMove() {
  const moves = ui.puzzle.moves.split(' ');
  const uci = moves[0];
  ui.chess.move({ from: uci.slice(0,2), to: uci.slice(2,4), promotion: uci[4] });
  ui.moveIndex = 1;
  ui.postOpponentFen = ui.chess.fen();
  ui.postOpponentLastMove = [uci.slice(0,2), uci.slice(2,4)];
  ui.board.set({
    fen: ui.chess.fen(),
    lastMove: [uci.slice(0,2), uci.slice(2,4)],
    movable: { color: null, dests: new Map() },
  });
  ui.state = 'OPPONENT_MOVE';
  setTimeout(armUserTurn, 250);
}

function armUserTurn() {
  const userColor = ui.puzzle.side_to_move === 'w' ? 'black' : 'white';
  ui.board.set({
    turnColor: userColor,
    movable: {
      color: userColor,
      free: false,
      dests: legalDests(ui.chess),
      events: { after: onUserMove },
    },
  });
  ui.state = 'USER_TURN';
  ui.exerciseStartedAt = performance.now();
}

function onUserMove(orig, dest) {
  if (ui.state !== 'USER_TURN') return;

  const moves = ui.puzzle.moves.split(' ');
  const expectedUci = moves[ui.moveIndex];
  const isLastMove = ui.moveIndex === moves.length - 1;
  const isMatePuzzle = (ui.puzzle.themes || []).some(t => t.startsWith('mate'));
  const expectedPromo = expectedUci.length === 5 ? expectedUci[4] : undefined;

  const played = ui.chess.move({ from: orig, to: dest, promotion: expectedPromo });
  if (!played) {
    return registerWrongAndAdvance();
  }
  const userUci = played.from + played.to + (played.promotion || '');

  if (userUci === expectedUci) {
    return continueAfterCorrect(moves);
  }
  if (isLastMove && isMatePuzzle && ui.chess.isCheckmate()) {
    return continueAfterCorrect(moves);
  }

  ui.chess.undo();
  registerWrongAndAdvance();
}

function continueAfterCorrect(moves) {
  ui.moveIndex += 1;
  ui.board.set({
    fen: ui.chess.fen(),
    movable: { color: null, dests: new Map() },
    turnColor: ui.chess.turn() === 'w' ? 'white' : 'black',
  });
  ui.state = 'OPPONENT_REPLY';

  if (ui.moveIndex >= moves.length) {
    return registerCorrectAndAdvance();
  }

  setTimeout(() => {
    const reply = moves[ui.moveIndex];
    ui.chess.move({ from: reply.slice(0,2), to: reply.slice(2,4), promotion: reply[4] });
    ui.moveIndex += 1;
    ui.board.set({
      fen: ui.chess.fen(),
      lastMove: [reply.slice(0,2), reply.slice(2,4)],
    });
    if (ui.moveIndex >= moves.length) {
      registerCorrectAndAdvance();
    } else {
      const userColor = ui.puzzle.side_to_move === 'w' ? 'black' : 'white';
      ui.board.set({
        turnColor: userColor,
        movable: {
          color: userColor, free: false,
          dests: legalDests(ui.chess), events: { after: onUserMove },
        },
      });
      ui.state = 'USER_TURN';
    }
  }, 250);
}

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
    ui.variantCursor = 1;
    setSidePanel(true, { canRetry: true });
    return;
  }
  ui.state = 'OUTCOME';
  setTimeout(loadNextPuzzle, 600);
}

function recordAttempt(correct) {
  const attempt = {
    order_idx: session.attempts.length,
    puzzle_id: ui.puzzle.puzzle_id,
    correct,
    time_ms: Math.round(performance.now() - ui.exerciseStartedAt),
  };
  session.attempts.push(attempt);
  if (correct) solvedThisSession.add(attempt.puzzle_id);
  postAttempt(attempt);
  renderCounter();
  if (session.meta.mode === 'count') {
    const correctCount = session.attempts.filter(a => a.correct).length;
    if (session.meta.target !== null && correctCount >= session.meta.target) {
      setTimeout(() => endSession('count'), 400);
    }
  }
}

function postAttempt(attempt, retriesLeft = 3) {
  fetch(`/api/sessions/${session.id}/attempts`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(attempt),
  }).then(r => {
    if (!r.ok && r.status !== 409 && retriesLeft > 0) {
      setTimeout(() => postAttempt(attempt, retriesLeft - 1), 1500);
    }
  }).catch(() => {
    if (retriesLeft > 0) setTimeout(() => postAttempt(attempt, retriesLeft - 1), 1500);
  });
}

function legalDests(chess) {
  const dests = new Map();
  for (const f of 'abcdefgh') for (const r of '12345678') {
    const sq = f + r;
    const moves = chess.moves({ square: sq, verbose: true });
    if (moves.length) dests.set(sq, moves.map(m => m.to));
  }
  return dests;
}

function setFlash(msg, kind) {
  const el = document.getElementById('flash');
  el.textContent = msg;
  el.className = 'play-flash ' + (kind || '');
}

function renderCounter() {
  const total = session.attempts.length;
  const correct = session.attempts.filter(a => a.correct).length;
  let text;
  if (session.meta.mode === 'count') {
    text = `${correct} / ${session.meta.target ?? '?'}`;
  } else {
    const wrong = total - correct;
    text = `✓ ${correct}  ✗ ${wrong}`;
  }
  document.getElementById('counter').textContent = text;
}

function renderClock(elapsedMs) {
  const el = document.getElementById('clock');
  let secs;
  if (session.meta.mode === 'time') {
    const remaining = Math.max(0, (session.meta.target * 60_000) - elapsedMs);
    secs = Math.ceil(remaining / 1000);
    el.classList.toggle('warning', secs <= 30 && secs > 10);
    el.classList.toggle('urgent', secs <= 10);
  } else {
    secs = Math.floor(elapsedMs / 1000);
  }
  const m = Math.floor(secs / 60).toString().padStart(2, '0');
  const s = (secs % 60).toString().padStart(2, '0');
  el.textContent = `${m}:${s}`;
}

function showOverlay(msg, actionLabel, onAction) {
  document.getElementById('overlay-msg').textContent = msg;
  const btn = document.getElementById('overlay-action');
  btn.textContent = actionLabel;
  btn.onclick = onAction;
  document.getElementById('overlay').hidden = false;
}

function goStats() {
  location.href = `/play/${encodeURIComponent(session.id)}/stats`;
}

async function onQuit() {
  if (!confirm('Encerrar a sessão agora?')) return;
  await endSession('manual');
}

async function endSession(reason) {
  if (session.ended) return;
  session.ended = true;
  if (clock.raf) cancelAnimationFrame(clock.raf);
  try {
    await fetch(`/api/sessions/${session.id}/end`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ end_reason: reason }),
    });
  } catch { /* server-side guarantee not critical for redirect */ }
  goStats();
}

function onNextFree() {
  if (ui.state !== 'OUTCOME_FREE') return;
  setSidePanel(false);
  loadNextPuzzle();
}

function onRetry() {
  if (ui.state !== 'OUTCOME_FREE' || ui.postOpponentFen == null) return;
  ui.chess = new Chess(ui.postOpponentFen);
  ui.moveIndex = 1;
  ui.board.set({
    fen: ui.postOpponentFen,
    lastMove: ui.postOpponentLastMove || undefined,
    drawable: { autoShapes: [] },
  });
  setSidePanel(false);
  setFlash('');
  armUserTurn();
}

function onVariantNav(action) {
  if (ui.state !== 'OUTCOME_FREE') return;
  const last = ui.variantHistory.length - 1;
  if (last < 0) return;
  if (action === 'start')      ui.variantCursor = 0;
  else if (action === 'end')   ui.variantCursor = last;
  else if (action === 'prev')  ui.variantCursor = Math.max(0, ui.variantCursor - 1);
  else if (action === 'next')  ui.variantCursor = Math.min(last, ui.variantCursor + 1);
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
  const pos = document.getElementById('variant-pos');
  if (pos) pos.textContent = `${ui.variantCursor} / ${Math.max(0, ui.variantHistory.length - 1)}`;
}

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
    paintVariantCursor();
  }
}

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
    const retryBtn = document.getElementById('btn-retry');
    if (retryBtn && !retryBtn.hidden) onRetry();
    return;
  }
  if (ev.key === 'Escape') onQuit();
}

boot().catch(e => {
  showOverlay('Erro ao iniciar a sessão: ' + (e.message || e), 'Voltar', goStats);
});
