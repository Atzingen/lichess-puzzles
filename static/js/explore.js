import { initFilterUI, readFilters, updateCounter, applyPreset } from './filters.js';
import { createTrainer } from './trainer.js';

async function boot() {
  const trainer = createTrainer();
  await initFilterUI(updateCounter);

  const presets = await fetch('/static/presets.json').then(r => r.json());
  const row = document.getElementById('presets');
  presets.forEach(p => {
    const b = document.createElement('button');
    b.textContent = p.name;
    b.addEventListener('click', async () => {
      applyPreset(p.filters);
      await updateCounter(readFilters());
      await trainer.loadRandom(readFilters());
    });
    row.append(b);
  });

  document.getElementById('btn-search').addEventListener('click', () =>
    trainer.loadRandom(readFilters()));
  document.getElementById('btn-next').addEventListener('click', () =>
    trainer.loadRandom(readFilters()));
  document.getElementById('btn-reveal').addEventListener('click', () => trainer.reveal());
  document.getElementById('btn-reset').addEventListener('click', () => trainer.reset());
}

boot().catch(e => {
  document.getElementById('puzzle-info').textContent = 'Erro ao iniciar: ' + e.message;
});
