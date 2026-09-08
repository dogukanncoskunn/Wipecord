"""Entry point.

`python -m wipecord` opens the GUI. `python -m wipecord --headless` runs a
preview from the terminal, which is how the engine gets verified against the
real API without any UI in the way.

The token is deliberately not a command-line flag: arguments end up in shell
history and in the process list, where other users on the machine can read
them. It comes from the WIPECORD_TOKEN environment variable or a hidden prompt.
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import sys
from datetime import datetime
from getpass import getpass
from pathlib import Path

from .engine import DeletionEngine, Job
from .events import DoneEvent, LogEvent, PreviewEvent
from .scanner import Mode, ScanCriteria


def _parse_date(value: str):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected YYYY-MM-DD, got {value!r}") from None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wipecord",
        description="Delete your own Discord messages, locally.",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="run a preview in the terminal instead of opening the GUI",
    )
    parser.add_argument("--channel", help="channel or DM id to preview")
    parser.add_argument(
        "--mode", choices=[m.value for m in Mode], default=Mode.ALL.value
    )
    parser.add_argument("--last", type=int, help="how many recent messages (mode last_n)")
    parser.add_argument("--since", type=_parse_date, help="start date (mode date_range)")
    parser.add_argument("--until", type=_parse_date, help="end date (mode date_range)")
    parser.add_argument(
        "--include-pinned",
        action="store_true",
        help="do not skip pinned messages",
    )
    parser.add_argument("--json", dest="json_out", help="write the preview to this file")
    return parser


def read_token() -> str:
    token = os.environ.get("WIPECORD_TOKEN")
    if token:
        return token.strip()
    return getpass("Discord user token (input hidden): ").strip()


def run_headless(args) -> int:
    if not args.channel:
        print("--channel is required with --headless", file=sys.stderr)
        return 2

    token = read_token()
    if not token:
        print("No token supplied.", file=sys.stderr)
        return 2

    criteria = ScanCriteria(
        mode=Mode(args.mode),
        limit=args.last,
        start_date=args.since,
        end_date=args.until,
        skip_pinned=not args.include_pinned,
    )
    if criteria.mode is Mode.LAST_N and not criteria.limit:
        print("--last is required with --mode last_n", file=sys.stderr)
        return 2

    events: queue.Queue = queue.Queue()
    engine = DeletionEngine(events)
    # Headless is preview-only. Deleting is a destructive action that belongs
    # behind the GUI's confirmation flow, not behind a shell flag.
    engine.start(Job(token=token, channel_id=args.channel, criteria=criteria, dry_run=True))

    preview = None
    summary = None
    while True:
        event = events.get()
        if isinstance(event, LogEvent):
            print(f"[{event.level.value}] {event.text}")
        elif isinstance(event, PreviewEvent):
            preview = event
        elif isinstance(event, DoneEvent):
            summary = event.summary
            break
    engine.join(5)

    if preview is not None:
        print()
        for ref in preview.messages:
            print(f"  {ref.timestamp}  {ref.id}  {ref.summary}")

    if args.json_out and preview is not None:
        path = Path(args.json_out)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(
                    {
                        "channel": preview.channel_label,
                        "generated_at": datetime.now().astimezone().isoformat(),
                        "messages": [ref.__dict__ for ref in preview.messages],
                    },
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        except OSError as exc:
            print(f"\nCould not write {path}: {exc}", file=sys.stderr)
            return 1
        print(f"\nWrote {len(preview.messages)} entries to {path}")

    if summary is not None:
        print(
            f"\nPreview: {summary.scanned} message(s) matched in "
            f"{summary.duration:.1f}s. Nothing was deleted."
        )
        if summary.error:
            print(f"Error: {summary.error}", file=sys.stderr)
            return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.headless:
        return run_headless(args)

    from .ui.app import launch

    launch()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
