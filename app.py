from __future__ import annotations

import argparse
from pathlib import Path

from apple_health.importer import AppleHealthImporter
from apple_health.parser import AppleHealthParser
from apple_health.analyzer import WorkoutAnalyzer


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

                print(f"Loaded {len(workouts)} workouts.")
                # TODO: temporary debug output
                day = sorted(analyzer.workouts_by_day())[0]

                print()
                print(day)
                print()

                summary = analyzer.summarize_day(day)
                print(summary)
                
                for workout in analyzer.workouts_for_day(day):
                    print(workout.apple_activity_type, "->", workout.activity_type)

            finally:
                xml_stream.close()
                archive.close()


if __name__ == "__main__":
    main()