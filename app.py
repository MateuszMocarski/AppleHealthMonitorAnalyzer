from __future__ import annotations

import argparse
from pathlib import Path
from datetime import date

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

    args = parser.parse_args()
    
    if args.year is not None and args.month is None:
        parser.error("--year requires --month.")

    match args.command:
        case "import":
            importer = AppleHealthImporter(args.file)

            archive, xml_stream = importer.open_export()

            try:
                parser = AppleHealthParser(xml_stream)
                workouts = parser.parse()

                analyzer = WorkoutAnalyzer(workouts)
                renderer = ConsoleRenderer()
                
                today = date.today()
                year = args.year if args.year is not None else today.year
                month = args.month if args.month is not None else today.month
                
                monthly_summary = analyzer.summarize_month(year, month)

                if args.month_summary:
                    renderer.render_month_summary(monthly_summary)
                else:
                    renderer.render_month(monthly_summary)

            finally:
                xml_stream.close()
                archive.close()


if __name__ == "__main__":
    main()