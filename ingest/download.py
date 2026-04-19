from __future__ import annotations

import time
from pathlib import Path

import httpx

MAX_AGE_SECONDS = 30 * 24 * 3600  # 30 days


def ensure_dump(url: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        age = time.time() - path.stat().st_mtime
        if age < MAX_AGE_SECONDS:
            return

    with httpx.Client(follow_redirects=True, timeout=None) as client:
        with client.stream("GET", url) as resp:
            resp.raise_for_status()
            with path.open("wb") as fh:
                for chunk in resp.iter_bytes(chunk_size=1 << 16):
                    fh.write(chunk)
