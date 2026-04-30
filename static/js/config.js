import { initFilterUI, readFilters, updateCounter, applyPreset } from './filters.js';
import { fetchBatch, createSession, listSessions, getSession } from './api.js';

const POOL_LIMIT = 500;
const STORAGE_KEY = (sessionId) => `pool:${sessionId}`;

const state = {
  pool: null,
  poolFiltersSig: null,
};

async function boot() {
  await initFilterUI(onFiltersChanged);
  await maybePrefillFromQuery();

  const presets = await fetch('/static/presets.json').then(r => r.json());
  const row = document.getElementById('presets');
  presets.forEach(p => {
    const b = document.createElement('button');
    b.textContent = p.name;
    b.addEventListener('click', async () => {
      applyPreset(p.filters);
      await onFiltersChanged(readFilters());
    });
    row.append(b);
  });

  document.getElementById('btn-pool').addEventListener('click', onFetchPool);
  document.getElementById('btn-start').addEventListener('click', onStart);
  document.querySelectorAll('input[name=mode]').forEach(r =>
    r.addEventListener('change', refreshStartEnabled));
  document.querySelectorAll('.mode-options input').forEach(el =>
    el.addEventListener('input', refreshStartEnabled));

  await loadSessions();
  refreshStartEnabled();
}

function onFiltersChanged(filters) {
  state.pool = null;
  state.poolFiltersSig = null;
  setPoolInfo('—');
  updateCounter(filters);
  refreshStartEnabled();
}

function filtersSig(filters) {
  return JSON.stringify(filters, Object.keys(filters).sort());
}

async function onFetchPool() {
  const filters = readFilters();
  setPoolInfo('Buscando…');
  try {
    const data = await fetchBatch(filters, POOL_LIMIT);
    state.pool = data;
    state.poolFiltersSig = filtersSig(filters);
    if (data.count === 0) {
      setPoolInfo('Nenhum puzzle com esses filtros — afrouxe algum critério.');
    } else {
      setPoolInfo(`Pool pronta: ${data.count} puzzle${data.count === 1 ? '' : 's'}.`);
    }
  } catch (e) {
    setPoolInfo('Erro ao buscar: ' + e.message);
  }
  refreshStartEnabled();
}

function setPoolInfo(text) {
  document.getElementById('pool-info').textContent = text;
}

function readMode() {
  return document.querySelector('input[name=mode]:checked')?.value || 'time';
}

function readTarget(mode) {
  if (mode === 'free') return null;
  const groupName = mode === 'time' ? 'time-target' : 'count-target';
  const customId  = mode === 'time' ? 'time-custom' : 'count-custom';
  const sel = document.querySelector(`input[name=${groupName}]:checked`)?.value;
  if (sel === 'custom') {
    const v = Number(document.getElementById(customId).value);
    return Number.isFinite(v) && v > 0 ? v : null;
  }
  return sel ? Number(sel) : null;
}

function refreshStartEnabled() {
  const filters = readFilters();
  const mode = readMode();
  const target = readTarget(mode);
  const sigOk = state.poolFiltersSig === filtersSig(filters);
  const poolOk = sigOk && state.pool && state.pool.count > 0;
  const targetOk = mode === 'free' || (target !== null && target > 0);
  const ok = !!(poolOk && targetOk);
  const btn = document.getElementById('btn-start');
  btn.disabled = !ok;
  if (ok) {
    btn.title = '';
  } else if (!sigOk || !state.pool) {
    btn.title = 'Clique em "Buscar pool" para preparar o conjunto de puzzles.';
  } else if (!poolOk) {
    btn.title = 'Pool vazia — afrouxe os filtros.';
  } else if (!targetOk) {
    btn.title = 'Defina um alvo (preset ou outro com valor > 0).';
  }
}

async function onStart() {
  hideStartError();
  const filters = readFilters();
  const mode = readMode();
  const target = readTarget(mode);
  const dedupe = document.getElementById('dedupe_solved').checked;
  const labelEl = document.getElementById('label');
  const label = labelEl.value.trim() || null;

  if (state.poolFiltersSig !== filtersSig(filters)) {
    showStartError('Os filtros mudaram após o "Buscar pool". Clique de novo.');
    return;
  }
  if (!state.pool || state.pool.count === 0) {
    showStartError('Pool vazia.');
    return;
  }

  let effectiveTarget = target;
  if (mode === 'count' && target !== null && target > state.pool.count) {
    effectiveTarget = state.pool.count;
  }

  document.getElementById('btn-start').disabled = true;
  try {
    const created = await createSession({
      mode,
      target: effectiveTarget,
      auto_advance: true,
      dedupe_solved: dedupe,
      filters,
      parent_session: null,
      label,
    });
    sessionStorage.setItem(STORAGE_KEY(created.session_id), JSON.stringify({
      puzzle_ids: state.pool.puzzles.map(p => p.puzzle_id),
    }));
    location.href = `/play/${created.session_id}`;
  } catch (e) {
    showStartError('Falha ao criar sessão: ' + e.message);
    document.getElementById('btn-start').disabled = false;
  }
}

function showStartError(msg) {
  const el = document.getElementById('start-error');
  el.textContent = msg; el.hidden = false;
}
function hideStartError() { document.getElementById('start-error').hidden = true; }

async function loadSessions() {
  const ul = document.getElementById('sessions-list');
  try {
    const list = await listSessions(20);
    if (list.length === 0) {
      ul.innerHTML = '<li class="empty">Nenhuma sessão ainda.</li>';
      return;
    }
    ul.innerHTML = '';
    for (const s of list) {
      const li = document.createElement('li');
      const arrowHref = s.ended_at
        ? `/play/${s.session_id}/stats`
        : `/play/${s.session_id}`;
      const arrowTitle = s.ended_at ? 'Ver estatísticas' : 'Reabrir';
      li.innerHTML = `
        <span class="when">${formatStarted(s.started_at)}</span>
        <span class="target">${formatTarget(s.mode, s.target)}</span>
        <span class="label">${escapeHtml(s.label || '')}</span>
        <span class="score">${s.correct}/${s.total}</span>
        <span class="actions">
          <a href="${arrowHref}" title="${arrowTitle}">→</a>
          <button class="ghost" data-redo="${s.session_id}" title="Nova sessão com mesmos filtros">↻</button>
        </span>
      `;
      ul.append(li);
    }
    ul.querySelectorAll('button[data-redo]').forEach(btn =>
      btn.addEventListener('click', () => onRedoSession(btn.dataset.redo))
    );
  } catch (e) {
    ul.innerHTML = `<li class="empty">Erro ao carregar: ${e.message}</li>`;
  }
}

function formatStarted(iso) {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleString('pt-BR', {
    day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit',
  });
}
function formatTarget(mode, target) {
  if (mode === 'free') return 'livre';
  if (mode === 'time') return `${target} min`;
  if (mode === 'count') return `${target} puzzles`;
  return mode;
}
function escapeHtml(s) {
  return s.replace(/[&<>"']/g, ch => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[ch]));
}

async function maybePrefillFromQuery() {
  const params = new URLSearchParams(location.search);
  const sid = params.get('prefill');
  if (!sid) return;
  try {
    const det = await getSession(sid);
    const s = det.session;
    applyPreset(s.filters || {});
    const modeRadio = document.querySelector(`input[name=mode][value="${s.mode}"]`);
    if (modeRadio && !modeRadio.disabled) modeRadio.checked = true;
    if (s.mode === 'time' || s.mode === 'count') {
      const groupName = s.mode === 'time' ? 'time-target' : 'count-target';
      const customId  = s.mode === 'time' ? 'time-custom' : 'count-custom';
      const presetVals = s.mode === 'time' ? ['3','5','10'] : ['50','100','200','500'];
      const tgt = String(s.target ?? '');
      if (presetVals.includes(tgt)) {
        const r = document.querySelector(`input[name=${groupName}][value="${tgt}"]`);
        if (r) r.checked = true;
      } else if (s.target) {
        const r = document.querySelector(`input[name=${groupName}][value="custom"]`);
        if (r) r.checked = true;
        const inp = document.getElementById(customId);
        if (inp) inp.value = s.target;
      }
    }
    const dedupeEl = document.getElementById('dedupe_solved');
    if (dedupeEl) dedupeEl.checked = !!s.dedupe_solved;
    const labelEl = document.getElementById('label');
    if (labelEl && s.label) labelEl.value = s.label;
  } catch (e) {
    console.warn('prefill failed', e);
  }
}

async function onRedoSession(parentSessionId) {
  try {
    const det = await getSession(parentSessionId);
    const s = det.session;
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

boot().catch(e => {
  document.getElementById('pool-info').textContent = 'Erro ao iniciar: ' + e.message;
});
