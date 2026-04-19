# lichess-puzzles

Self-hosted Lichess puzzle trainer with richer filtering than lichess.org —
including filters by piece count (derived from FEN) and by move number of the
source game.

Ingests the full official Lichess puzzle dump (~5M puzzles) into SQLite and
serves a FastAPI + chessground web UI to pick filters/presets and rotate
through matching puzzles.

Status: **Deployed.**

## Deployed at

`hostinger-02` · `deployer@72.61.43.231:/var/local/apps/lichess-puzzles`
Open: <http://72.61.43.231:8004/>

DB has 5.882.680 puzzles (Lichess dump, 2026-04).

## Docs

- Design: `docs/superpowers/specs/2026-04-18-lichess-puzzles-design.md`
- Implementation plan: `docs/superpowers/plans/2026-04-18-lichess-puzzles.md`
