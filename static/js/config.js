async function loadSessions() {
  const ul = document.getElementById('sessions-list');
  try {
    const r = await fetch('/api/sessions?limit=20');
    if (!r.ok) throw new Error('http ' + r.status);
    const list = await r.json();
    if (list.length === 0) {
      ul.innerHTML = '<li class="empty">Nenhuma sessão ainda.</li>';
      return;
    }
    ul.innerHTML = '';
    for (const s of list) {
      const li = document.createElement('li');
      const when = formatStarted(s.started_at);
      const target = formatTarget(s.mode, s.target);
      const score = `${s.correct}/${s.total}`;
      li.innerHTML = `
        <span class="when">${when}</span>
        <span class="target">${target}</span>
        <span class="label">${escapeHtml(s.label || '')}</span>
        <span class="score">${score}</span>
      `;
      ul.append(li);
    }
  } catch (e) {
    ul.innerHTML = `<li class="empty">Erro ao carregar: ${e.message}</li>`;
  }
}

function formatStarted(iso) {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleString('pt-BR', {
    day: '2-digit', month: '2-digit',
    hour: '2-digit', minute: '2-digit',
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

loadSessions();
