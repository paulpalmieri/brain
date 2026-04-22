"""LLM-backed retrieval: search and reflect."""

from __future__ import annotations

import os

from anthropic import Anthropic

from .store import Entry


MODEL = "claude-haiku-4-5-20251001"


def _client() -> Anthropic:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Export it before using search/reflect."
        )
    return Anthropic()


def _format_entries(entries: list[Entry]) -> str:
    if not entries:
        return "(no entries)"
    chunks = []
    for e in entries:
        header = e.created.strftime("%Y-%m-%d %H:%M")
        chunks.append(f"--- {header} (id: {e.id}) ---\n{e.text.strip()}")
    return "\n\n".join(chunks)


def search(query: str, entries: list[Entry]) -> str:
    system = (
        "You are reading someone's personal journal to answer their question. "
        "Use only the entries provided. Cite specific entries by their date when "
        "you reference them. If the entries don't contain an answer, say so plainly."
    )
    user = (
        f"Question: {query}\n\n"
        f"Journal entries (oldest first):\n\n{_format_entries(entries)}"
    )
    resp = _client().messages.create(
        model=MODEL,
        max_tokens=1024,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return "".join(b.text for b in resp.content if b.type == "text").strip()


def reflect(entries: list[Entry], days: int) -> str:
    system = (
        "You are reviewing someone's personal journal. Surface recurring themes, "
        "mood patterns, unresolved threads, and anything they mentioned wanting to "
        "do but haven't mentioned since. Be specific, warm, and concise. Cite dates "
        "when helpful. If there's very little to work with, say so honestly."
    )
    user = (
        f"Entries from the past {days} day(s), oldest first:\n\n"
        f"{_format_entries(entries)}"
    )
    resp = _client().messages.create(
        model=MODEL,
        max_tokens=1500,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return "".join(b.text for b in resp.content if b.type == "text").strip()
