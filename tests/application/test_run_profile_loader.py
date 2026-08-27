from pathlib import Path

import pytest

from apple_health.application.run_profile_loader import RunProfileLoader
from apple_health.config.exceptions import ConfigurationError

# =====================================================================
# Verifies that a complete [run] TOML section is converted into a fully
# populated RunProfile using the supported run-profile fields.
# =====================================================================


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


# =====================================================================
# Verifies that omitted run-profile fields remain unresolved rather than
# being replaced with built-in defaults during TOML loading.
# =====================================================================


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


# =====================================================================
# Verifies that unknown fields inside the [run] section fail fast rather
# than being silently ignored by run-profile loading.
# =====================================================================


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


# =====================================================================
# Verifies that unsupported run-profile output formats are rejected at
# the TOML loading boundary.
# =====================================================================


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


# =====================================================================
# Verifies that unknown top-level TOML sections are rejected instead of
# being silently ignored outside the supported [run] section.
# =====================================================================


def test_unknown_top_level_section_raises_configuration_error(
    tmp_path: Path,
) -> None:
    profile_path = tmp_path / "run.toml"

    profile_path.write_text(
        """
        [run]
        month = 8

        [garbage]
        value = true
        """,
        encoding="utf-8",
    )

    with pytest.raises(
        ConfigurationError,
        match="Unknown run profile section: garbage",
    ):
        RunProfileLoader.load(
            profile_path,
        )


# =====================================================================
# Verifies that all committed example run profiles remain compatible
# with the current RunProfileLoader contract.
# =====================================================================


@pytest.mark.parametrize(
    "profile_path",
    [
        Path("apple_health/application/examples/run.example.toml"),
        Path("apple_health/application/examples/run.month-summary.toml"),
        Path("apple_health/application/examples/run.partial.toml"),
    ],
)
def test_example_run_profile_is_loadable(
    profile_path: Path,
) -> None:
    profile = RunProfileLoader.load(
        profile_path,
    )

    assert profile is not None
