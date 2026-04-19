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

function filtersToQueryString(filters) {
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(filters)) {
    if (v === null || v === undefined || v === '') continue;
    if (Array.isArray(v)) {
      v.forEach(val => params.append(k, val));
    } else {
      params.append(k, String(v));
    }
  }
  return params.toString();
}
