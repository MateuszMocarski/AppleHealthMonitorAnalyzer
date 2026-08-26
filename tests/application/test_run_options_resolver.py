from datetime import date
from pathlib import Path

import pytest

from apple_health.application.run_options_resolver import (
    RunOptionsResolver,
)
from apple_health.application.run_profile import RunProfile


def test_resolves_run_options_from_defaults() -> None:
    today = date.today()

    options = RunOptionsResolver.resolve(
        archive_path=Path("export.zip"),
    )

    assert options.archive_path == Path("export.zip")
    assert options.year == today.year
    assert options.month == today.month
    assert options.month_summary is False
    assert options.output_format == "text"
    assert options.config_path is None


def test_run_profile_overrides_defaults() -> None:
    profile = RunProfile(
        archive_path=Path("profile-export.zip"),
        year=2025,
        month=7,
        month_summary=True,
        output_format="json",
        config_path=Path("profile-config.toml"),
    )

    options = RunOptionsResolver.resolve(
        profile=profile,
    )

    assert options.archive_path == Path("profile-export.zip")
    assert options.year == 2025
    assert options.month == 7
    assert options.month_summary is True
    assert options.output_format == "json"
    assert options.config_path == Path("profile-config.toml")


def test_cli_values_override_run_profile() -> None:
    profile = RunProfile(
        archive_path=Path("profile-export.zip"),
        year=2025,
        month=7,
        month_summary=True,
        output_format="json",
        config_path=Path("profile-config.toml"),
    )

    options = RunOptionsResolver.resolve(
        archive_path=Path("cli-export.zip"),
        year=2026,
        month=8,
        month_summary=False,
        output_format="text",
        config_path=Path("cli-config.toml"),
        profile=profile,
    )

    assert options.archive_path == Path("cli-export.zip")
    assert options.year == 2026
    assert options.month == 8
    assert options.month_summary is False
    assert options.output_format == "text"
    assert options.config_path == Path("cli-config.toml")


def test_missing_archive_path_is_rejected() -> None:
    with pytest.raises(
        ValueError,
        match="Archive path is required",
    ):
        RunOptionsResolver.resolve()
