"""Brain CLI."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta

import click
from prompt_toolkit import PromptSession
from prompt_toolkit.key_binding import KeyBindings
from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table

from . import llm, store, usage
from .usage import Totals, Usage


console = Console()


def _compose() -> str:
    kb = KeyBindings()

    @kb.add("c-d")
    def _submit(event) -> None:
        event.current_buffer.validate_and_handle()

    console.print(
        "[dim]Write your entry. "
        "[bold]Esc↵[/bold] or [bold]^D[/bold] to save · "
        "[bold]^C[/bold] to cancel.[/dim]"
    )
    session: PromptSession[str] = PromptSession(multiline=True, key_bindings=kb)
    try:
        return session.prompt("› ")
    except (KeyboardInterrupt, EOFError):
        return ""


def _short_model(m: str) -> str:
    s = m.removeprefix("claude-")
    parts = s.rsplit("-", 1)
    if len(parts) == 2 and parts[1].isdigit() and len(parts[1]) == 8:
        s = parts[0]
    return s


def _fmt_tokens(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


def _fmt_cost(c: float) -> str:
    if c == 0:
        return "$0"
    if c < 0.01:
        return f"${c:.4f}"
    return f"${c:.2f}"


def _print_usage(u: Usage) -> None:
    console.print(
        f"[dim]↳ {_short_model(u.model)} · "
        f"{_fmt_tokens(u.input_tokens)} in / "
        f"{_fmt_tokens(u.output_tokens)} out · "
        f"{_fmt_cost(u.cost_usd)}[/dim]"
    )


@click.group()
@click.version_option()
def cli() -> None:
    """A local CLI journal with LLM-powered search and reflection."""


@cli.command("add")
@click.argument("text", required=False)
def cmd_add(text: str | None) -> None:
    """Save an entry. With no argument, opens an inline multi-line editor."""
    body = text if text else _compose()
    if not body.strip():
        console.print("[yellow]Empty entry, nothing saved.[/yellow]")
        sys.exit(1)
    entry = store.save(body)
    console.print(f"[green]Saved.[/green] [dim]{entry.id}[/dim]")


@cli.command("search")
@click.argument("query")
@click.option("--limit", default=50, show_default=True, help="Entries to consider.")
def cmd_search(query: str, limit: int) -> None:
    """Ask a question; the LLM answers from your recent entries."""
    entries = store.recent(limit)
    if not entries:
        console.print("[yellow]No entries yet.[/yellow]")
        return
    try:
        with console.status("[dim]thinking...[/dim]", spinner="dots"):
            answer, u = llm.search(query, entries)
    except RuntimeError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)
    console.print(Markdown(answer))
    _print_usage(u)


@cli.command("reflect")
@click.option("--days", default=7, show_default=True, help="Window in days.")
def cmd_reflect(days: int) -> None:
    """Weekly reflection: themes, patterns, open threads."""
    entries = store.since(days)
    if not entries:
        console.print(f"[yellow]No entries in the last {days} day(s).[/yellow]")
        return
    try:
        with console.status("[dim]reflecting...[/dim]", spinner="dots"):
            answer, u = llm.reflect(entries, days)
    except RuntimeError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)
    console.print(Markdown(answer))
    _print_usage(u)


@cli.command("list")
@click.option("--limit", default=20, show_default=True, help="How many to show.")
def cmd_list(limit: int) -> None:
    """List recent entries."""
    entries = store.recent(limit)
    if not entries:
        console.print("[yellow]No entries yet. Try `brain add`.[/yellow]")
        return
    table = Table(show_header=True, header_style="bold")
    table.add_column("id", style="dim")
    table.add_column("when")
    table.add_column("preview")
    for e in reversed(entries):
        preview = e.text.strip().splitlines()[0][:70] if e.text.strip() else ""
        table.add_row(e.id, e.created.strftime("%Y-%m-%d %H:%M"), preview)
    console.print(table)


@cli.command("show")
@click.argument("entry_id")
def cmd_show(entry_id: str) -> None:
    """Show a full entry by id (or id prefix)."""
    entry = store.find(entry_id)
    if entry is None:
        console.print(f"[red]No entry matching {entry_id!r}.[/red]")
        sys.exit(1)
    header = entry.created.strftime("%Y-%m-%d %H:%M")
    console.rule(f"[bold]{header}[/bold]  [dim]{entry.id}[/dim]")
    console.print(entry.text.rstrip())


def _row(scope: str, t: Totals) -> tuple[str, str, str, str, str]:
    return (
        scope,
        str(t.calls),
        _fmt_tokens(t.input_tokens),
        _fmt_tokens(t.output_tokens),
        _fmt_cost(t.cost_usd),
    )


@cli.command("usage")
def cmd_usage() -> None:
    """Show LLM token + cost metrics."""
    records = usage.all_records()
    if not records:
        console.print("[yellow]No LLM usage recorded yet.[/yellow]")
        return

    now = datetime.now()
    start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today = [r for r in records if datetime.fromisoformat(r.ts) >= start_of_today]
    last_7 = [
        r for r in records if datetime.fromisoformat(r.ts) >= now - timedelta(days=7)
    ]
    last_30 = [
        r for r in records if datetime.fromisoformat(r.ts) >= now - timedelta(days=30)
    ]

    summary = Table(title="Usage", header_style="bold", title_style="bold")
    summary.add_column("scope")
    summary.add_column("calls", justify="right")
    summary.add_column("in", justify="right")
    summary.add_column("out", justify="right")
    summary.add_column("cost", justify="right")
    summary.add_row(*_row("today", usage.totals(today)))
    summary.add_row(*_row("7 days", usage.totals(last_7)))
    summary.add_row(*_row("30 days", usage.totals(last_30)))
    summary.add_row(*_row("all time", usage.totals(records)))
    console.print(summary)

    by_cmd = usage.by_key(records, "command")
    cmd_table = Table(title="By command", header_style="bold", title_style="bold")
    cmd_table.add_column("command")
    cmd_table.add_column("calls", justify="right")
    cmd_table.add_column("in", justify="right")
    cmd_table.add_column("out", justify="right")
    cmd_table.add_column("cost", justify="right")
    for name, t in sorted(by_cmd.items(), key=lambda kv: -kv[1].cost_usd):
        cmd_table.add_row(*_row(name, t))
    console.print(cmd_table)

    by_model = usage.by_key(records, "model")
    if len(by_model) > 1:
        model_table = Table(title="By model", header_style="bold", title_style="bold")
        model_table.add_column("model")
        model_table.add_column("calls", justify="right")
        model_table.add_column("in", justify="right")
        model_table.add_column("out", justify="right")
        model_table.add_column("cost", justify="right")
        for name, t in sorted(by_model.items(), key=lambda kv: -kv[1].cost_usd):
            model_table.add_row(*_row(_short_model(name), t))
        console.print(model_table)
