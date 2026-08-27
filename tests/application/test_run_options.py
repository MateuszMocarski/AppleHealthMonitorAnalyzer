from pathlib import Path

from apple_health.application.run_options import RunOptions

# =====================================================================
# Verifies that RunOptions preserves the complete resolved parameter
# set passed to the application execution boundary.
# =====================================================================


def test_run_options_stores_resolved_application_parameters() -> None:
    options = RunOptions(
        archive_path=Path("export.zip"),
        year=2026,
        month=8,
        month_summary=True,
        output_format="json",
        config_path=Path("config.toml"),
    )

    assert options.archive_path == Path("export.zip")
    assert options.year == 2026
    assert options.month == 8
    assert options.month_summary is True
    assert options.output_format == "json"
    assert options.config_path == Path("config.toml")
