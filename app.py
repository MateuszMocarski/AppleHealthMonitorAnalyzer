from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from apple_health.application import AppleHealthApplication, RunOptions


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="AppleHealthMonitorAnalyzer",
    )

    parser.add_argument(
        "command",
        choices=["import"],
    )

    parser.add_argument(
        "file",
        type=Path,
    )

    parser.add_argument(
        "-y",
        "--year",
        type=int,
    )

    parser.add_argument(
        "-m",
        "--month",
        type=int,
        choices=range(1, 13),
    )

    parser.add_argument(
        "--month-summary",
        action="store_true",
        help="Show only the monthly summary",
    )

    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text).",
    )

    parser.add_argument(
        "--config",
        type=Path,
        help="Path to an optional TOML configuration file.",
    )

    args = parser.parse_args()

    if args.year is not None and args.month is None:
        parser.error("--year requires --month.")

    today = date.today()

    options = RunOptions(
        archive_path=args.file,
        year=args.year if args.year is not None else today.year,
        month=args.month if args.month is not None else today.month,
        month_summary=args.month_summary,
        output_format=args.format,
        config_path=args.config,
    )

    output = AppleHealthApplication().run(
        options,
    )

    print(
        output,
        end="",
    )


if __name__ == "__main__":
    main()