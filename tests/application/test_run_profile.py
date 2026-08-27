from pathlib import Path

from apple_health.application.run_profile import RunProfile


# =====================================================================
# Verifies that RunProfile supports partial execution settings so that
# omitted values can be resolved later from CLI input or defaults.
# =====================================================================


def test_run_profile_supports_partial_application_parameters() -> None:
    profile = RunProfile(
        month=8,
        output_format="json",
        config_path=Path("config.toml"),
    )

    assert profile.archive_path is None
    assert profile.year is None
    assert profile.month == 8
    assert profile.month_summary is None
    assert profile.output_format == "json"
    assert profile.config_path == Path("config.toml")
