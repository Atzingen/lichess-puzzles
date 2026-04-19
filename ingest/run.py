from __future__ import annotations

import argparse
import csv
import io
import sqlite3
from pathlib import Path

import zstandard
from tqdm import tqdm

from app.config import settings
from app.db import init_db
from ingest.download import ensure_dump
from ingest.writer import insert_batch, row_from_csv


def _stream_csv(path: Path):
    if path.suffix == ".zst":
        with path.open("rb") as raw:
            dctx = zstandard.ZstdDecompressor()
            with dctx.stream_reader(raw) as decoded:
                text = io.TextIOWrapper(decoded, encoding="utf-8", newline="")
                yield from csv.DictReader(text)
    else:
        with path.open("r", encoding="utf-8", newline="") as fh:
            yield from csv.DictReader(fh)


def ingest_csv_file(csv_path: Path, db_path: Path, batch_size: int = 10_000) -> int:
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA synchronous=OFF")
        conn.execute("PRAGMA journal_mode=MEMORY")
        conn.execute("BEGIN")
        batch: list = []
        total = 0
        for csv_row in tqdm(_stream_csv(csv_path), desc="ingest"):
            batch.append(row_from_csv(csv_row))
            if len(batch) >= batch_size:
                insert_batch(conn, batch)
                total += len(batch)
                batch.clear()
        if batch:
            insert_batch(conn, batch)
            total += len(batch)
        conn.commit()
        conn.execute("VACUUM")
        conn.execute("ANALYZE")
        return total
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest Lichess puzzle dump.")
    parser.add_argument("--csv", type=Path, default=None,
                        help="local CSV (uncompressed) to ingest; skips download")
    args = parser.parse_args()

    if args.csv is not None:
        ingest_csv_file(args.csv, settings.db_path)
        return
    ensure_dump(settings.dump_url, settings.dump_path)
    ingest_csv_file(settings.dump_path, settings.db_path)


if __name__ == "__main__":
    main()
