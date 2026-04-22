"""Basic tests for the store layer. No LLM calls."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from brain import store


@pytest.fixture(autouse=True)
def tmp_brain(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    entries = tmp_path / "entries"
    monkeypatch.setattr(store, "BRAIN_DIR", tmp_path)
    monkeypatch.setattr(store, "ENTRIES_DIR", entries)
    return tmp_path


def test_save_writes_file_and_roundtrips() -> None:
    entry = store.save("hello world")
    assert entry.path.exists()
    assert entry.path.read_text().strip() == "hello world"


def test_save_collision_adds_seconds() -> None:
    ts = datetime(2026, 4, 22, 12, 0, 0)
    first = store.save("one", now=ts)
    second = store.save("two", now=ts.replace(second=30))
    assert first.path != second.path
    assert first.path.exists() and second.path.exists()


def test_list_is_chronological() -> None:
    store.save("first", now=datetime(2026, 4, 20, 9, 0))
    store.save("second", now=datetime(2026, 4, 21, 9, 0))
    store.save("third", now=datetime(2026, 4, 22, 9, 0))
    entries = store.all_entries()
    assert [e.text.strip() for e in entries] == ["first", "second", "third"]


def test_recent_returns_tail() -> None:
    for i in range(5):
        store.save(f"entry {i}", now=datetime(2026, 4, 20 + i, 9, 0))
    recent = store.recent(2)
    assert [e.text.strip() for e in recent] == ["entry 3", "entry 4"]


def test_since_filters_by_window() -> None:
    now = datetime.now()
    store.save("old", now=now - timedelta(days=30))
    store.save("new", now=now - timedelta(days=1))
    window = store.since(7)
    assert [e.text.strip() for e in window] == ["new"]


def test_find_by_prefix() -> None:
    entry = store.save("findable", now=datetime(2026, 4, 22, 15, 30))
    full = store.find(entry.id)
    assert full is not None and full.id == entry.id
    prefix = store.find("2026-04-22")
    assert prefix is not None and prefix.id == entry.id
    assert store.find("nope") is None
