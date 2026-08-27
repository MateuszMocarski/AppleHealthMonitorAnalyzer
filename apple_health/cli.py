from __future__ import annotations

import argparse
from pathlib import Path

from apple_health.application import (
    AppleHealthApplication,
    RunOptionsResolver,
    RunProfileLoader,
)


def run_cli() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    _validate_arguments(
        parser,
        args,
    )

    profile = RunProfileLoader.load(args.profile) if args.profile is not None else None

    try:
        options = RunOptionsResolver.resolve(
            archive_path=args.file,
            year=args.year,
            month=args.month,
            month_summary=args.month_summary,
            output_format=args.format,
            config_path=args.config,
            profile=profile,
        )
    except ValueError as exc:
        parser.error(str(exc))

    output = AppleHealthApplication().run(
        options,
    )

    print(
        output,
        end="",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="AppleHealthMonitorAnalyzer",
    )

    parser.add_argument(
        "command",
        nargs="?",
        choices=["import"],
    )

    parser.add_argument(
        "file",
        nargs="?",
        type=Path,
    )

    parser.add_argument(
        "--profile",
        type=Path,
        help="Path to an optional TOML run profile.",
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

    month_summary_group = parser.add_mutually_exclusive_group()

    month_summary_group.add_argument(
        "--month-summary",
        dest="month_summary",
        action="store_true",
        help="Show only the monthly summary.",
    )

    month_summary_group.add_argument(
        "--enforce-daily",
        dest="month_summary",
        action="store_false",
        help="Show the full report including daily details.",
    )

    parser.set_defaults(
        month_summary=None,
    )

    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default=None,
        help="Output format.",
    )

    parser.add_argument(
        "--config",
        type=Path,
        help="Path to an optional TOML configuration file.",
    )

    return parser


def _validate_arguments(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
) -> None:
    if args.command == "import" and args.file is None:
        parser.error("import requires an archive path.")

    if args.file is not None and args.command is None:
        parser.error("Archive path requires the import command.")
