from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
MAINTENANCE_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>lichess-puzzles — maintenance</title>
<style>body{font-family:sans-serif;max-width:640px;margin:4rem auto;padding:1rem}
code{background:#eee;padding:.1rem .3rem;border-radius:.2rem}</style></head>
<body>
<h1>Banco ainda n&atilde;o populado</h1>
<p>O arquivo SQLite n&atilde;o existe. Rode <code>make ingest</code> para
baixar e importar o dump oficial do Lichess (~5-10 min).</p>
</body></html>
"""


def _db_exists() -> bool:
    return settings.db_path.exists()


app = FastAPI(title="lichess-puzzles", version="0.1.0")


@app.get("/", response_class=HTMLResponse)
def root() -> HTMLResponse:
    if not _db_exists():
        return HTMLResponse(MAINTENANCE_HTML)
    return HTMLResponse((STATIC_DIR / "index.html").read_text(encoding="utf-8"))


@app.get("/healthz")
def healthz() -> dict[str, bool]:
    return {"ok": True, "db": _db_exists()}


if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
