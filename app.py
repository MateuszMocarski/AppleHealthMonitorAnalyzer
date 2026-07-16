from pathlib import Path
import argparse


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="AppleHealthMonitorAnalyzer",
        description="Apple Health export analyzer",
    )

    parser.add_argument(
        "command",
        choices=["import"],
        help="Command to execute",
    )

    parser.add_argument(
        "file",
        type=Path,
        help="Path to export.zip",
    )

    args = parser.parse_args()

    print(f"Command : {args.command}")
    print(f"File    : {args.file.resolve()}")


if __name__ == "__main__":
    main()