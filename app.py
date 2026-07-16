from __future__ import annotations

import argparse
from pathlib import Path

from apple_health.importer import AppleHealthImporter


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

    args = parser.parse_args()

    match args.command:
        case "import":
            AppleHealthImporter(args.file).run()


if __name__ == "__main__":
    main()