"""CLI entry point for appmon."""

from __future__ import annotations

import argparse
import sys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="appmon",
        description="Terminal monitor that aggregates RAM and CPU usage per application.",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=1.0,
        metavar="SEC",
        help="Refresh interval in seconds (default: 1.0)",
    )
    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s 0.3.2",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    from appmon.tui.app import run_tui

    args = build_parser().parse_args(argv)
    if args.interval <= 0:
        print("error: --interval must be positive", file=sys.stderr)
        return 2
    run_tui(interval=args.interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
