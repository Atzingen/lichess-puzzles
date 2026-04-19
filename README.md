# lichess-puzzles

Self-hosted Lichess puzzle trainer with richer filtering than lichess.org —
including filters by piece count (derived from FEN) and by move number of the
source game.

Ingests the full official Lichess puzzle dump (~5M puzzles) into SQLite and
serves a FastAPI + chessground web UI to pick filters/presets and rotate
through matching puzzles.

Status: **Design phase.** See `docs/superpowers/specs/2026-04-18-lichess-puzzles-design.md`.
