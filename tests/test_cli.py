from pathlib import Path

import pytest

from health_analyzer.cli import _build_parser, _validate_arguments

# =====================================================================
# Verifies that optional CLI arguments remain unresolved when they are
# not explicitly supplied, allowing later profile/default resolution.
# =====================================================================


def test_parser_uses_none_for_unspecified_optional_arguments() -> None:
    parser = _build_parser()

    args = parser.parse_args([])

    assert args.command is None
    assert args.file is None
    assert args.profile is None
    assert args.year is None
    assert args.month is None
    assert args.month_summary is None
    assert args.format is None
    assert args.config is None


# =====================================================================
# Verifies that the CLI parser correctly converts a complete import
# command into typed argument values without applying application
# logic.
# =====================================================================


def test_parser_parses_import_arguments() -> None:
    parser = _build_parser()

    args = parser.parse_args(
        [
            "import",
            "export.zip",
            "--year",
            "2026",
            "--month",
            "8",
            "--month-summary",
            "--format",
            "json",
            "--config",
            "config.toml",
            "--profile",
            "run.toml",
        ]
    )

    assert args.command == "import"
    assert args.file == Path("export.zip")
    assert args.year == 2026
    assert args.month == 8
    assert args.month_summary is True
    assert args.format == "json"
    assert args.config == Path("config.toml")
    assert args.profile == Path("run.toml")


# =====================================================================
# Verifies that --enforce-daily explicitly resolves the tri-state
# monthly-summary CLI option to False for profile override purposes.
# =====================================================================


def test_parser_parses_enforce_daily() -> None:
    parser = _build_parser()

    args = parser.parse_args(
        [
            "--enforce-daily",
        ]
    )

    assert args.month_summary is False


# =====================================================================
# Verifies that the import command cannot be used without supplying the
# Apple Health export archive path required by the CLI import workflow.
# =====================================================================


def test_import_requires_archive_path() -> None:
    parser = _build_parser()

    args = parser.parse_args(
        [
            "import",
        ]
    )

    with pytest.raises(SystemExit):
        _validate_arguments(
            parser,
            args,
        )


# =====================================================================
# Verifies that an archive path cannot be supplied as a positional
# value without the supported import command preceding it.
# =====================================================================


def test_archive_path_without_import_command_is_rejected() -> None:
    parser = _build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "export.zip",
                "--year",
                "2026",
            ]
        )
