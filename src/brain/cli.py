"""Brain CLI."""

from __future__ import annotations

import sys

import click
from prompt_toolkit import PromptSession
from prompt_toolkit.key_binding import KeyBindings
from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table

from . import llm, store


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


@click.group()
@click.version_option()
def cli() -> None:
    """A local CLI journal with LLM-powered search and reflection."""


@cli.command("add")
@click.argument("text", required=False)
def cmd_add(text: str | None) -> None:
    """Save an entry. With no argument, opens $EDITOR."""
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
            answer = llm.search(query, entries)
    except RuntimeError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)
    console.print(Markdown(answer))


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
            answer = llm.reflect(entries, days)
    except RuntimeError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)
    console.print(Markdown(answer))


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
