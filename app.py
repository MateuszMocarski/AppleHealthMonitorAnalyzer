from __future__ import annotations

import argparse
from pathlib import Path

from apple_health.importer import AppleHealthImporter
from apple_health.parser import AppleHealthParser
from apple_health.analyzer import WorkoutAnalyzer
from apple_health.renderer import ConsoleRenderer


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

                analyzer = WorkoutAnalyzer(workouts)
                renderer = ConsoleRenderer()

                print(f"Loaded {len(workouts)} workouts.")
                print()

                summaries = analyzer.summarize_month(2026, 5)
                renderer.render_month(summaries)

            finally:
                xml_stream.close()
                archive.close()


if __name__ == "__main__":
    main()