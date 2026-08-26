from pathlib import Path

import pytest

from apple_health.application.run_profile_loader import RunProfileLoader
from apple_health.config.exceptions import ConfigurationError


def test_loads_run_profile_from_toml(
    tmp_path: Path,
) -> None:
    profile_path = tmp_path / "run.toml"

    profile_path.write_text(
        """
        [run]
        archive = "private/export.zip"
        year = 2026
        month = 8
        month_summary = true
        format = "json"
        config = "private/config.toml"
        """,
        encoding="utf-8",
    )

    profile = RunProfileLoader.load(
        profile_path,
    )

    assert profile.archive_path == Path("private/export.zip")
    assert profile.year == 2026
    assert profile.month == 8
    assert profile.month_summary is True
    assert profile.output_format == "json"
    assert profile.config_path == Path("private/config.toml")


def test_loads_partial_run_profile_from_toml(
    tmp_path: Path,
) -> None:
    profile_path = tmp_path / "run.toml"

    profile_path.write_text(
        """
        [run]
        month = 8
        format = "json"
        """,
        encoding="utf-8",
    )

    profile = RunProfileLoader.load(
        profile_path,
    )

    assert profile.archive_path is None
    assert profile.year is None
    assert profile.month == 8
    assert profile.month_summary is None
    assert profile.output_format == "json"
    assert profile.config_path is None


def test_unknown_run_profile_field_raises_configuration_error(
    tmp_path: Path,
) -> None:
    profile_path = tmp_path / "run.toml"

    profile_path.write_text(
        """
        [run]
        month = 8
        output = "json"
        """,
        encoding="utf-8",
    )

    with pytest.raises(
        ConfigurationError,
        match="run.output",
    ):
        RunProfileLoader.load(
            profile_path,
        )


def test_invalid_run_profile_format_raises_configuration_error(
    tmp_path: Path,
) -> None:
    profile_path = tmp_path / "run.toml"

    profile_path.write_text(
        """
        [run]
        format = "xml"
        """,
        encoding="utf-8",
    )

    with pytest.raises(
        ConfigurationError,
        match="run.format",
    ):
        RunProfileLoader.load(
            profile_path,
        )
