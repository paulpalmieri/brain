"""Tests for usage tracking and aggregation."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from brain import store, usage


@pytest.fixture(autouse=True)
def tmp_brain(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(store, "BRAIN_DIR", tmp_path)
    monkeypatch.setattr(store, "ENTRIES_DIR", tmp_path / "entries")
    monkeypatch.setattr(usage, "BRAIN_DIR", tmp_path)
    return tmp_path


@dataclass
class _RespUsage:
    input_tokens: int
    output_tokens: int
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


@dataclass
class _Resp:
    usage: Any


def test_cost_for_haiku_basic() -> None:
    # 1M input @ $1 + 1M output @ $5 = $6
    cost = usage.cost_for("claude-haiku-4-5-20251001", 1_000_000, 1_000_000)
    assert cost == pytest.approx(6.0)


def test_cost_for_cache_pricing() -> None:
    # Cache write = 1.25x input; cache read = 0.1x input.
    # 1M cache_write haiku = $1.25; 1M cache_read haiku = $0.10
    cost = usage.cost_for(
        "claude-haiku-4-5-20251001",
        input_tokens=0,
        output_tokens=0,
        cache_read_tokens=1_000_000,
        cache_creation_tokens=1_000_000,
    )
    assert cost == pytest.approx(1.35)


def test_cost_for_unknown_model_is_zero() -> None:
    assert usage.cost_for("unknown-model", 1000, 1000) == 0.0


def test_record_writes_jsonl_and_computes_cost(tmp_brain: Path) -> None:
    resp = _Resp(usage=_RespUsage(input_tokens=1000, output_tokens=500))
    u = usage.record("search", "claude-haiku-4-5-20251001", resp)
    assert u.input_tokens == 1000
    assert u.output_tokens == 500
    # 1000 * $1/M + 500 * $5/M = $0.001 + $0.0025 = $0.0035
    assert u.cost_usd == pytest.approx(0.0035)

    log = tmp_brain / "usage.jsonl"
    assert log.exists()
    records = usage.all_records()
    assert len(records) == 1
    assert records[0].command == "search"


def test_all_records_roundtrip_multiple(tmp_brain: Path) -> None:
    for _ in range(3):
        usage.record(
            "search",
            "claude-haiku-4-5-20251001",
            _Resp(usage=_RespUsage(input_tokens=100, output_tokens=50)),
        )
    records = usage.all_records()
    assert len(records) == 3
    assert all(r.command == "search" for r in records)


def test_totals_sums_correctly() -> None:
    records = [
        usage.Usage("2026-04-22T10:00:00", "search", "m", 100, 50, 0, 0, 0.001),
        usage.Usage("2026-04-22T11:00:00", "reflect", "m", 200, 80, 10, 5, 0.002),
    ]
    t = usage.totals(records)
    assert t.calls == 2
    assert t.input_tokens == 300
    assert t.output_tokens == 130
    assert t.cache_read_tokens == 10
    assert t.cache_creation_tokens == 5
    assert t.cost_usd == pytest.approx(0.003)


def test_by_key_groups() -> None:
    records = [
        usage.Usage("2026-04-22T10:00:00", "search", "m", 100, 50, 0, 0, 0.001),
        usage.Usage("2026-04-22T11:00:00", "search", "m", 200, 80, 0, 0, 0.002),
        usage.Usage("2026-04-22T12:00:00", "reflect", "m", 300, 90, 0, 0, 0.003),
    ]
    grouped = usage.by_key(records, "command")
    assert set(grouped) == {"search", "reflect"}
    assert grouped["search"].calls == 2
    assert grouped["search"].input_tokens == 300
    assert grouped["reflect"].calls == 1


def _write_records(path: Path, records: list[usage.Usage]) -> None:
    path.write_text(
        "\n".join(json.dumps(asdict(r)) for r in records) + "\n", encoding="utf-8"
    )


def test_since_filters_by_window(tmp_brain: Path) -> None:
    old_ts = (datetime.now() - timedelta(days=30)).isoformat(timespec="seconds")
    new_ts = (datetime.now() - timedelta(hours=1)).isoformat(timespec="seconds")
    _write_records(
        tmp_brain / "usage.jsonl",
        [
            usage.Usage(old_ts, "search", "m", 1, 1, 0, 0, 0.0),
            usage.Usage(new_ts, "search", "m", 2, 2, 0, 0, 0.0),
        ],
    )
    window = usage.since(7)
    assert len(window) == 1
    assert window[0].input_tokens == 2


def test_all_records_skips_malformed_lines(tmp_brain: Path) -> None:
    log = tmp_brain / "usage.jsonl"
    good = json.dumps(
        asdict(usage.Usage("2026-04-22T10:00:00", "search", "m", 1, 1, 0, 0, 0.0))
    )
    log.write_text(f"{good}\nnot json\n{{}}\n{good}\n", encoding="utf-8")
    records = usage.all_records()
    assert len(records) == 2
