// uPlot is loaded as IIFE -> window.uPlot
const $ = (id) => document.getElementById(id);

const state = {
  sessionId: null,
  detail: null,
  histBarPickedMs: null,
};

async function boot() {
  const parts = location.pathname.split('/');
  state.sessionId = parts[parts.length - 2]; // /play/<id>/stats
  try {
    const r = await fetch(`/api/sessions/${state.sessionId}`);
    if (!r.ok) throw new Error('http ' + r.status);
    state.detail = await r.json();
  } catch (e) {
    document.body.innerHTML =
      `<main style="padding:2rem">Erro ao carregar sessão: ${e.message} <a href="/">voltar</a></main>`;
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

function renderFailedList() {
  const failed = state.detail.attempts.filter(x => !x.correct);
  $('failed-count').textContent = `(${failed.length})`;
  $('btn-redo-failed').disabled = failed.length === 0;
  $('failed-list').innerHTML = failed.length
    ? failed.map(attemptRow).join('')
    : '<li>Sem erros nesta sessão.</li>';
}

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
  const xs = bins.map((_, i) => i + 0.5);
  const ys = bins;

  const opts = {
    width: el.clientWidth || 600,
    height: 220,
    scales: { x: { time: false }, y: { range: (_u, _mn, mx) => [0, Math.max(1, mx + 1)] } },
    axes: [{ label: 'segundos' }, { label: 'qtd' }],
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

function renderScatter() {
  const el = $('scatter');
  el.innerHTML = '';
  const a = state.detail.attempts;
  if (a.length === 0) { el.textContent = 'Sem dados.'; return; }

  const xs = a.map(x => x.rating || 0);
  const okY = a.map(x => x.correct ? x.time_ms / 1000 : null);
  const wrY = a.map(x => x.correct ? null : x.time_ms / 1000);

  const opts = {
    width: el.clientWidth || 600,
    height: 240,
    axes: [{ label: 'rating' }, { label: 'tempo (s)' }],
    scales: {
      x: { time: false },
      y: { range: (_u, _mn, mx) => [0, Math.max(1, (mx || 0) + 0.5)] },
    },
    series: [
      { label: 'rating' },
      { label: 'corretos', stroke: '#2f855a', fill: '#2f855a',
        paths: () => null, points: { show: true, size: 6, fill: '#2f855a' } },
      { label: 'errados', stroke: '#b53030', fill: '#b53030',
        paths: () => null, points: { show: true, size: 6, fill: '#b53030' } },
    ],
  };
  new uPlot(opts, [xs, okY, wrY], el);
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
          filters: {},
          parent_session: s.session_id,
          label: (s.label ? s.label + ' (refazer)' : 'refazer errados'),
        }),
      });
      if (!r.ok) throw new Error('http ' + r.status);
      const out = await r.json();
      const failedIds = state.detail.attempts.filter(x => !x.correct).map(x => x.puzzle_id);
      sessionStorage.setItem(`pool:${out.session_id}`, JSON.stringify({ puzzle_ids: failedIds }));
      location.href = `/play/${out.session_id}`;
    } catch (e) {
      alert('Falha ao criar sessão filha: ' + e.message);
      btn.disabled = false;
    }
  });

  $('btn-new-session').addEventListener('click', () => {
    location.href = `/?prefill=${encodeURIComponent(state.sessionId)}`;
  });

  $('btn-back-config').addEventListener('click', () => {
    location.href = `/?prefill=${encodeURIComponent(state.sessionId)}`;
  });
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

boot();
