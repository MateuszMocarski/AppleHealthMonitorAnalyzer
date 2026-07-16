from __future__ import annotations

import argparse
from pathlib import Path

from apple_health.importer import AppleHealthImporter
from apple_health.parser import AppleHealthParser


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
            importer = AppleHealthImporter(args.file)

            archive, xml_stream = importer.open_export()

            try:
                parser = AppleHealthParser(xml_stream)
                workouts = parser.parse()

                print(f"Loaded {len(workouts)} workouts.")

                if workouts:
                    print()
                    print("First workout:")
                    print(workouts[0])

            finally:
                xml_stream.close()
                archive.close()


if __name__ == "__main__":
    main()