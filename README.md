# brain

A local CLI journal. Capture thoughts quickly from the terminal, then use an LLM to search them, ask questions, and surface weekly patterns.

Entries are plain markdown files in `~/.brain/entries/`.

## Install

```sh
git clone https://github.com/<you>/brain.git
cd brain
uv sync
export ANTHROPIC_API_KEY=sk-ant-...
```

Then either `uv run brain ...` or activate the venv (`source .venv/bin/activate`) to use `brain` directly.

## Usage

```sh
brain add                    # opens $EDITOR, save+quit to store
brain add "quick thought"    # inline
brain search "what have I been worried about lately?"
brain reflect                # past 7 days
brain reflect --days 30
brain list                   # recent entries
brain show 2026-04-22-1530   # full entry (id prefix works too)
```

## How it works

Entries are stored as `YYYY-MM-DD-HHMM.md` files in `~/.brain/entries/`. `search` and `reflect` read the relevant files off disk and send them to Claude Haiku, which answers with citations. At journal scale, reading every file at query time is fast enough — no index or database needed.

## Roadmap

- [ ] Tags and summaries on write
- [ ] `triage` command for open threads
- [ ] Telegram bot for capture on the go
- [ ] Web UI for browsing
- [ ] Voice input
- [ ] Export (JSON, Markdown bundle)

## License

MIT.
