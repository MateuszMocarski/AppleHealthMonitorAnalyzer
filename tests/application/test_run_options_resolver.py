from datetime import date
from pathlib import Path

import pytest

from health_analyzer.application.run_options_resolver import (
    RunOptionsResolver,
)
from health_analyzer.application.run_profile import RunProfile

# =====================================================================
# Verifies that unresolved run parameters fall back to built-in
# defaults while the explicitly supplied archive path is preserved.
# =====================================================================


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


# =====================================================================
# Verifies that values supplied by a RunProfile override built-in run
# defaults when no explicit CLI-equivalent values are provided.
# =====================================================================


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


# =====================================================================
# Verifies that explicit CLI-equivalent values take precedence over all
# corresponding values loaded from a RunProfile.
# =====================================================================


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


# =====================================================================
# Verifies that final run-option resolution rejects execution when no
# archive path can be resolved from explicit values or a RunProfile.
# =====================================================================


def test_missing_archive_path_is_rejected() -> None:
    with pytest.raises(
        ValueError,
        match="Archive path is required",
    ):
        RunOptionsResolver.resolve()


# =====================================================================
# Verifies that resolved month values outside the calendar range are
# rejected.
# =====================================================================


@pytest.mark.parametrize(
    "month",
    [
        0,
        13,
    ],
)
def test_rejects_invalid_resolved_month(
    month: int,
) -> None:
    with pytest.raises(
        ValueError,
        match="Month must be between 1 and 12",
    ):
        RunOptionsResolver.resolve(
            archive_path=Path("export.zip"),
            month=month,
        )


# =====================================================================
# Verifies that a non-positive resolved year is rejected before report
# generation is delegated to the application layer.
# =====================================================================


def test_rejects_invalid_resolved_year() -> None:
    with pytest.raises(
        ValueError,
        match="Year must be a positive integer",
    ):
        RunOptionsResolver.resolve(
            archive_path=Path("export.zip"),
            year=0,
        )


# =====================================================================
# Verifies that unsupported output formats cannot silently fall back to
# the text renderer after final run-option resolution.
# =====================================================================


def test_rejects_invalid_resolved_output_format() -> None:
    with pytest.raises(
        ValueError,
        match="Output format must be 'text' or 'json'",
    ):
        RunOptionsResolver.resolve(
            archive_path=Path("export.zip"),
            output_format="pdf",
        )


# =====================================================================
# Verifies that the resolved monthly-summary option remains a strict
# boolean at the application execution boundary.
# =====================================================================


def test_rejects_non_boolean_month_summary() -> None:
    with pytest.raises(
        ValueError,
        match="Month summary must be a boolean",
    ):
        RunOptionsResolver.resolve(
            archive_path=Path("export.zip"),
            month_summary="yes",  # type: ignore[arg-type]
        )
