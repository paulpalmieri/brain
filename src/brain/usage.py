"""LLM usage and cost tracking."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

from .store import BRAIN_DIR


# USD per million tokens. Cache write is 1.25x input; cache read is 0.1x input.
# Source: Anthropic public pricing.
PRICING: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5-20251001": (1.0, 5.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-opus-4-7": (15.0, 75.0),
}


def _log_path() -> Path:
    return BRAIN_DIR / "usage.jsonl"


@dataclass(frozen=True)
class Usage:
    ts: str
    command: str
    model: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_creation_tokens: int
    cost_usd: float


def cost_for(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_creation_tokens: int = 0,
) -> float:
    price_in, price_out = PRICING.get(model, (0.0, 0.0))
    return (
        input_tokens * price_in
        + cache_creation_tokens * price_in * 1.25
        + cache_read_tokens * price_in * 0.1
        + output_tokens * price_out
    ) / 1_000_000


def record(command: str, model: str, response: Any) -> Usage:
    """Extract token counts from an Anthropic Message response and persist."""
    u = response.usage
    input_tokens = getattr(u, "input_tokens", 0) or 0
    output_tokens = getattr(u, "output_tokens", 0) or 0
    cache_read = getattr(u, "cache_read_input_tokens", 0) or 0
    cache_creation = getattr(u, "cache_creation_input_tokens", 0) or 0
    usage = Usage(
        ts=datetime.now().isoformat(timespec="seconds"),
        command=command,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_tokens=cache_read,
        cache_creation_tokens=cache_creation,
        cost_usd=cost_for(
            model, input_tokens, output_tokens, cache_read, cache_creation
        ),
    )
    _append(usage)
    return usage


def _append(usage: Usage) -> None:
    BRAIN_DIR.mkdir(parents=True, exist_ok=True)
    with _log_path().open("a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(usage)) + "\n")


def all_records() -> list[Usage]:
    path = _log_path()
    if not path.exists():
        return []
    out: list[Usage] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
            out.append(Usage(**data))
        except (json.JSONDecodeError, TypeError):
            continue
    return out


def since(days: int) -> list[Usage]:
    cutoff = datetime.now() - timedelta(days=days)
    return [r for r in all_records() if datetime.fromisoformat(r.ts) >= cutoff]


@dataclass(frozen=True)
class Totals:
    calls: int
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_creation_tokens: int
    cost_usd: float


def totals(records: Iterable[Usage]) -> Totals:
    calls = 0
    tin = tout = tcr = tcc = 0
    cost = 0.0
    for r in records:
        calls += 1
        tin += r.input_tokens
        tout += r.output_tokens
        tcr += r.cache_read_tokens
        tcc += r.cache_creation_tokens
        cost += r.cost_usd
    return Totals(calls, tin, tout, tcr, tcc, cost)


def by_key(records: Iterable[Usage], key: str) -> dict[str, Totals]:
    grouped: dict[str, list[Usage]] = {}
    for r in records:
        grouped.setdefault(getattr(r, key), []).append(r)
    return {k: totals(v) for k, v in grouped.items()}
