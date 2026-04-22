"""Filesystem store for journal entries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path


BRAIN_DIR = Path.home() / ".brain"
ENTRIES_DIR = BRAIN_DIR / "entries"


@dataclass(frozen=True)
class Entry:
    path: Path
    created: datetime
    text: str

    @property
    def id(self) -> str:
        return self.path.stem

    @property
    def short_id(self) -> str:
        return self.path.stem[:10]


def ensure_dirs() -> None:
    ENTRIES_DIR.mkdir(parents=True, exist_ok=True)


def save(text: str, now: datetime | None = None) -> Entry:
    ensure_dirs()
    ts = now or datetime.now()
    # Collision-safe: add seconds if the minute-level name already exists.
    base = ts.strftime("%Y-%m-%d-%H%M")
    path = ENTRIES_DIR / f"{base}.md"
    if path.exists():
        path = ENTRIES_DIR / f"{base}{ts.strftime('%S')}.md"
    path.write_text(text.rstrip() + "\n", encoding="utf-8")
    return Entry(path=path, created=ts, text=text)


def _parse_ts(path: Path) -> datetime | None:
    stem = path.stem
    for fmt in ("%Y-%m-%d-%H%M%S", "%Y-%m-%d-%H%M"):
        try:
            return datetime.strptime(stem, fmt)
        except ValueError:
            continue
    return None


def all_entries() -> list[Entry]:
    ensure_dirs()
    out: list[Entry] = []
    for p in sorted(ENTRIES_DIR.glob("*.md")):
        ts = _parse_ts(p)
        if ts is None:
            continue
        out.append(Entry(path=p, created=ts, text=p.read_text(encoding="utf-8")))
    return out


def recent(limit: int) -> list[Entry]:
    entries = all_entries()
    return entries[-limit:]


def since(days: int) -> list[Entry]:
    cutoff = datetime.now() - timedelta(days=days)
    return [e for e in all_entries() if e.created >= cutoff]


def find(short_id: str) -> Entry | None:
    for e in all_entries():
        if e.id == short_id or e.short_id == short_id or e.id.startswith(short_id):
            return e
    return None
