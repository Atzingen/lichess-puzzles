import { Chessground } from 'chessground';
import { Chess } from 'chess.js';
import { randomPuzzle } from './api.js';

const RECENT_MAX = 10;

export function createTrainer() {
  const state = {
    board: null,
    chess: null,
    puzzle: null,
    moveIndex: 0,
    recentIds: [],
    currentFilters: {},
  };

  state.board = Chessground(document.getElementById('board'), {
    movable: { free: false, color: 'white', events: { after: onUserMove } },
    draggable: { showGhost: true },
  });

  async function loadRandom(filters) {
    state.currentFilters = filters;
    for (let attempt = 0; attempt < 4; attempt++) {
      const data = await randomPuzzle(filters);
      if (!data.puzzle) return showNoPuzzle(data.count);
      if (!state.recentIds.includes(data.puzzle.puzzle_id) || data.count <= state.recentIds.length) {
        return loadPuzzle(data.puzzle);
      }
    }
    const data = await randomPuzzle(filters);
    if (data.puzzle) loadPuzzle(data.puzzle);
  }

  function loadPuzzle(puzzle) {
    state.puzzle = puzzle;
    state.moveIndex = 0;
    state.chess = new Chess(puzzle.fen);
    state.recentIds.push(puzzle.puzzle_id);
    if (state.recentIds.length > RECENT_MAX) state.recentIds.shift();
    renderBoardFromChess();
    renderInfo(puzzle);
    setStatus(`Sua vez: ${puzzle.side_to_move === 'w' ? 'brancas' : 'pretas'}`);
    enableButtons(true);
  }

  function renderBoardFromChess() {
    const color = state.puzzle.side_to_move === 'w' ? 'white' : 'black';
    state.board.set({
      fen: state.chess.fen(),
      turnColor: color,
      orientation: color,
      movable: {
        color,
        free: false,
        dests: legalDests(state.chess),
        events: { after: onUserMove },
      },
      lastMove: undefined,
      drawable: { autoShapes: [] },
    });
  }

  function onUserMove(orig, dest) {
    const expectedUci = state.puzzle.moves.split(' ')[state.moveIndex];
    const promo = expectedUci.length === 5 ? expectedUci[4] : undefined;
    const move = state.chess.move({ from: orig, to: dest, promotion: promo });
    if (!move) {
      renderBoardFromChess();
      flash('Jogada ilegal', true);
      return;
    }
    if (move.from + move.to + (move.promotion || '') !== expectedUci) {
      state.chess.undo();
      renderBoardFromChess();
      flash('Tente de novo', true);
      return;
    }
    state.moveIndex += 1;
    flash('Correto!', false);

    const remaining = state.puzzle.moves.split(' ').length - state.moveIndex;
    if (remaining === 0) {
      setStatus('Resolvido ✓ — carregando próximo…', 'ok');
      setTimeout(() => loadRandom(state.currentFilters), 1500);
      return;
    }
    const reply = state.puzzle.moves.split(' ')[state.moveIndex];
    setTimeout(() => {
      state.chess.move({
        from: reply.slice(0,2), to: reply.slice(2,4),
        promotion: reply[4],
      });
      state.moveIndex += 1;
      renderBoardFromChess();
    }, 500);
  }

  function reveal() {
    if (!state.puzzle) return;
    state.chess = new Chess(state.puzzle.fen);
    state.moveIndex = 0;
    renderBoardFromChess();
    const moves = state.puzzle.moves.split(' ');
    const arrows = moves.map((uci, i) => ({
      orig: uci.slice(0,2), dest: uci.slice(2,4),
      brush: i % 2 === 0 ? 'green' : 'blue',
    }));
    state.board.set({ drawable: { autoShapes: arrows } });
    setStatus('Solução revelada', 'ok');
  }

  function reset() {
    if (!state.puzzle) return;
    state.chess = new Chess(state.puzzle.fen);
    state.moveIndex = 0;
    renderBoardFromChess();
    setStatus(`Sua vez: ${state.puzzle.side_to_move === 'w' ? 'brancas' : 'pretas'}`);
  }

  function showNoPuzzle(count) {
    state.puzzle = null;
    document.getElementById('puzzle-info').textContent =
      'Nenhum puzzle com esses filtros — afrouxe algum critério.';
    document.getElementById('puzzle-link').innerHTML = '';
    setStatus(`Total encontrado: ${count}`, 'err');
    enableButtons(false);
  }

  function renderInfo(p) {
    const themes = p.themes.map(t => `<span class="theme-chip">${t}</span>`).join(' ');
    const openings = p.opening_tags.length
      ? `<div>Abertura: ${p.opening_tags.join(', ')}</div>` : '';
    document.getElementById('puzzle-info').innerHTML = `
      <div><strong>ID:</strong> ${p.puzzle_id}</div>
      <div>Rating: ${p.rating} ±${p.rating_deviation}</div>
      <div>Popularidade: ${p.popularity}</div>
      <div>Plays: ${p.nb_plays.toLocaleString('pt-BR')}</div>
      <div>Peças: ${p.piece_count} — Lance: ${p.move_number} — Fase: ${p.phase}</div>
      <div>Material (B−P): ${p.material_balance}</div>
      <div>Themes: ${themes}</div>${openings}`;
    document.getElementById('puzzle-link').innerHTML = p.game_url
      ? `<a href="${p.game_url}" target="_blank" rel="noopener">ver no Lichess ↗</a>` : '';
    document.getElementById('puzzle-meta').textContent =
      `Rating ${p.rating} · Peças ${p.piece_count}`;
  }

  function legalDests(chess) {
    const dests = new Map();
    const squares = [];
    for (const f of 'abcdefgh') for (const r of '12345678') squares.push(f + r);
    for (const sq of squares) {
      const moves = chess.moves({ square: sq, verbose: true });
      if (moves.length) dests.set(sq, moves.map(m => m.to));
    }
    return dests;
  }

  function flash(msg, err) { setStatus(msg, err ? 'err' : 'ok'); }
  function setStatus(text, kind) {
    const el = document.getElementById('status');
    el.textContent = text;
    el.className = kind === 'ok' ? 'status-ok' : kind === 'err' ? 'status-err' : '';
  }
  function enableButtons(v) {
    for (const id of ['btn-reveal','btn-reset','btn-next']) {
      document.getElementById(id).disabled = !v;
    }
  }

  return { loadRandom, reveal, reset };
}
