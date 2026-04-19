import { fetchThemes, fetchOpenings, search } from './api.js';

const NUMBER_FIELDS = [
  'rating_min','rating_max','piece_count_min','piece_count_max',
  'move_number_min','move_number_max','popularity_min','nb_plays_min',
  'material_balance_min','material_balance_max',
];
const SELECT_FIELDS = ['side_to_move','phase'];
const BOOL_SELECT_FIELDS = ['has_promoted','has_en_passant','has_castling'];

export async function initFilterUI(onChange) {
  const [themes, openings] = await Promise.all([fetchThemes(), fetchOpenings()]);
  renderCheckboxList('themes_any', themes);
  renderCheckboxList('themes_all', themes);
  renderCheckboxList('opening_tags_any', openings);

  const debounced = debounce(() => onChange(readFilters()), 300);
  for (const id of [...NUMBER_FIELDS, ...SELECT_FIELDS, ...BOOL_SELECT_FIELDS]) {
    document.getElementById(id)?.addEventListener('input', debounced);
  }
  document.querySelectorAll('.checkbox-list input').forEach(cb =>
    cb.addEventListener('change', debounced));
  onChange(readFilters());
}

export function readFilters() {
  const f = {};
  for (const id of NUMBER_FIELDS) {
    const v = document.getElementById(id)?.value;
    if (v !== '' && v !== undefined) f[id] = Number(v);
  }
  for (const id of SELECT_FIELDS) {
    const v = document.getElementById(id)?.value;
    if (v) f[id] = v;
  }
  for (const id of BOOL_SELECT_FIELDS) {
    const v = document.getElementById(id)?.value;
    if (v === 'true') f[id] = true;
    else if (v === 'false') f[id] = false;
  }
  f.themes_any       = collectChecked('themes_any');
  f.themes_all       = collectChecked('themes_all');
  f.opening_tags_any = collectChecked('opening_tags_any');
  return f;
}

export function applyPreset(preset) {
  clearAll();
  for (const [k, v] of Object.entries(preset)) {
    if (Array.isArray(v)) {
      setCheckboxList(k, v);
    } else if (typeof v === 'boolean') {
      const el = document.getElementById(k);
      if (el) el.value = v ? 'true' : 'false';
    } else {
      const el = document.getElementById(k);
      if (el) el.value = v ?? '';
    }
  }
}

export async function updateCounter(filters) {
  try {
    const { count } = await search(filters);
    document.getElementById('counter').textContent = count.toLocaleString('pt-BR');
  } catch {
    document.getElementById('counter').textContent = '—';
  }
}

function clearAll() {
  for (const id of [...NUMBER_FIELDS, ...SELECT_FIELDS, ...BOOL_SELECT_FIELDS]) {
    const el = document.getElementById(id);
    if (el) el.value = '';
  }
  document.querySelectorAll('.checkbox-list input').forEach(cb => cb.checked = false);
}

function renderCheckboxList(containerId, items) {
  const box = document.getElementById(containerId);
  box.innerHTML = '';
  items.forEach(item => {
    const label = document.createElement('label');
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.value = item;
    cb.dataset.group = containerId;
    label.append(cb, ' ', item);
    box.append(label);
  });
}

function collectChecked(containerId) {
  return [...document.querySelectorAll(`#${containerId} input:checked`)].map(cb => cb.value);
}

function setCheckboxList(containerId, values) {
  const set = new Set(values);
  document.querySelectorAll(`#${containerId} input`).forEach(cb => {
    cb.checked = set.has(cb.value);
  });
}

function debounce(fn, ms) {
  let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
}
