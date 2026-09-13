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
# Verifies that omitted run-profile fields remain unresolved rather
# than being replaced with built-in defaults during TOML loading.
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
# Verifies that unknown fields inside the [run] section fail fast
# rather than being silently ignored by run-profile loading.
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
# Verifies that every committed example run profile remains loadable by
# RunProfileLoader.
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


# =====================================================================
# Verifies that a run profile must contain the required [run] section.
# =====================================================================


def test_missing_run_section_raises_configuration_error(
    tmp_path: Path,
) -> None:
    profile_path = tmp_path / "run.toml"
    profile_path.write_text("", encoding="utf-8")

    with pytest.raises(
        ConfigurationError,
        match="Missing required configuration section: run",
    ):
        RunProfileLoader.load(profile_path)


# =====================================================================
# Verifies that run must be a TOML section rather than a scalar value.
# =====================================================================


def test_non_section_run_value_raises_configuration_error(
    tmp_path: Path,
) -> None:
    profile_path = tmp_path / "run.toml"
    profile_path.write_text('run = "invalid"', encoding="utf-8")

    with pytest.raises(
        ConfigurationError,
        match="Expected a TOML section",
    ):
        RunProfileLoader.load(profile_path)


# =====================================================================
# Verifies that string integer values are accepted for year and month.
# =====================================================================


def test_integer_strings_are_coerced(
    tmp_path: Path,
) -> None:
    profile_path = tmp_path / "run.toml"
    profile_path.write_text(
        '[run]\nyear = "2026"\nmonth = "8"\n',
        encoding="utf-8",
    )

    profile = RunProfileLoader.load(profile_path)

    assert profile.year == 2026
    assert profile.month == 8


# =====================================================================
# Verifies that booleans are not silently accepted as integer fields.
# =====================================================================


def test_boolean_integer_field_raises_configuration_error(
    tmp_path: Path,
) -> None:
    profile_path = tmp_path / "run.toml"
    profile_path.write_text("[run]\nmonth = true\n", encoding="utf-8")

    with pytest.raises(
        ConfigurationError,
        match="run.month",
    ):
        RunProfileLoader.load(profile_path)


# =====================================================================
# Verifies that invalid string integers fail with a controlled error.
# =====================================================================


def test_invalid_integer_string_raises_configuration_error(
    tmp_path: Path,
) -> None:
    profile_path = tmp_path / "run.toml"
    profile_path.write_text('[run]\nyear = "later"\n', encoding="utf-8")

    with pytest.raises(
        ConfigurationError,
        match="run.year",
    ):
        RunProfileLoader.load(profile_path)


# =====================================================================
# Verifies that typed run-profile values reject incompatible TOML types.
# =====================================================================


@pytest.mark.parametrize(
    ("field", "value", "expected_path"),
    [
        ("archive", "123", "run.archive"),
        ("config", "false", "run.config"),
        ("month_summary", '"yes"', "run.month_summary"),
    ],
)
def test_invalid_typed_run_fields_raise_configuration_error(
    tmp_path: Path,
    field: str,
    value: str,
    expected_path: str,
) -> None:
    profile_path = tmp_path / "run.toml"
    profile_path.write_text(
        f"[run]\n{field} = {value}\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ConfigurationError,
        match=expected_path,
    ):
        RunProfileLoader.load(profile_path)


# =====================================================================
# Verifies that missing and malformed profile files are surfaced as
# domain configuration errors instead of raw I/O/TOML exceptions.
# =====================================================================


def test_missing_run_profile_file_raises_configuration_error(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        ConfigurationError,
        match="Run profile file not found",
    ):
        RunProfileLoader.load(tmp_path / "missing.toml")


def test_malformed_run_profile_toml_raises_configuration_error(
    tmp_path: Path,
) -> None:
    profile_path = tmp_path / "run.toml"
    profile_path.write_text("[run", encoding="utf-8")

    with pytest.raises(
        ConfigurationError,
        match="Invalid TOML run profile",
    ):
        RunProfileLoader.load(profile_path)


# =====================================================================
# Verifies recursive key normalization for nested dictionaries and lists.
# =====================================================================


def test_normalize_keys_recurses_through_lists() -> None:
    normalized = RunProfileLoader._normalize_keys(
        {
            "RUN": [
                {"MONTH": 8},
            ],
        }
    )

    assert normalized == {
        "run": [
            {"month": 8},
        ],
    }
