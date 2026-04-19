import os
import time
from pathlib import Path

from ingest.download import ensure_dump, MAX_AGE_SECONDS


class FakeResponse:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def raise_for_status(self) -> None: ...

    def iter_bytes(self, chunk_size: int = 65536):
        for i in range(0, len(self._data), chunk_size):
            yield self._data[i:i + chunk_size]


class FakeStream:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def __enter__(self) -> FakeResponse:
        return FakeResponse(self._data)

    def __exit__(self, *exc) -> None: ...


class FakeClient:
    def __init__(self, data: bytes) -> None:
        self._data = data
        self.called = 0

    def stream(self, method: str, url: str):
        self.called += 1
        return FakeStream(self._data)

    def __enter__(self):
        return self

    def __exit__(self, *exc): ...


def test_ensure_dump_downloads_when_missing(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "dump.zst"
    client = FakeClient(b"hello-world")
    monkeypatch.setattr("ingest.download.httpx.Client", lambda **kw: client)
    ensure_dump(url="http://x", path=target)
    assert target.read_bytes() == b"hello-world"
    assert client.called == 1


def test_ensure_dump_reuses_recent_file(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "dump.zst"
    target.write_bytes(b"old")
    client = FakeClient(b"NEW")
    monkeypatch.setattr("ingest.download.httpx.Client", lambda **kw: client)
    ensure_dump(url="http://x", path=target)
    assert target.read_bytes() == b"old"
    assert client.called == 0


def test_ensure_dump_redownloads_when_stale(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "dump.zst"
    target.write_bytes(b"old")
    old_mtime = time.time() - (MAX_AGE_SECONDS + 1000)
    os.utime(target, (old_mtime, old_mtime))

    client = FakeClient(b"NEW")
    monkeypatch.setattr("ingest.download.httpx.Client", lambda **kw: client)
    ensure_dump(url="http://x", path=target)
    assert target.read_bytes() == b"NEW"
