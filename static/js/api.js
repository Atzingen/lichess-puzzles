function filtersToQueryString(filtersForBatch) {
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(filtersForBatch)) {
    if (v === null || v === undefined || v === '') continue;
    if (Array.isArray(v)) v.forEach(val => params.append(k, val));
    else params.append(k, String(v));
  }
  return params.toString();
}

export async function fetchStats() {
  const r = await fetch('/api/stats');
  if (!r.ok) throw new Error('stats');
  return r.json();
}

export async function fetchThemes() {
  const r = await fetch('/api/themes');
  return r.ok ? r.json() : [];
}

export async function fetchOpenings() {
  const r = await fetch('/api/openings');
  return r.ok ? r.json() : [];
}

export async function search(filters) {
  const r = await fetch('/api/puzzles/search', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(filters),
  });
  if (!r.ok) throw new Error('search');
  return r.json();
}

export async function randomPuzzle(filters) {
  const qs = filtersToQueryString(filters);
  const r = await fetch(`/api/puzzles/random${qs ? '?' + qs : ''}`);
  if (!r.ok) throw new Error('random');
  return r.json();
}

export async function fetchBatch(filters, limit = 500) {
  const qs = filtersToQueryString({ ...filters, limit });
  const r = await fetch(`/api/puzzles/batch${qs ? '?' + qs : ''}`);
  if (!r.ok) throw new Error('batch ' + r.status);
  return r.json();
}

export async function createSession(payload) {
  const r = await fetch('/api/sessions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!r.ok) throw new Error('createSession ' + r.status);
  return r.json();
}

export async function listSessions(limit = 20) {
  const r = await fetch(`/api/sessions?limit=${limit}`);
  if (!r.ok) throw new Error('listSessions ' + r.status);
  return r.json();
}

export async function getSession(sessionId) {
  const r = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}`);
  if (!r.ok) throw new Error('getSession ' + r.status);
  return r.json();
}
