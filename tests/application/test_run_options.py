from pathlib import Path

from connected_health.application.multi_month_run_options import MultiMonthRunOptions
from connected_health.application.report_period import ReportPeriod
from connected_health.application.run_options import RunOptions
from connected_health.config.app_config import AppConfig

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


# =====================================================================
# Verifies that multi-month generation options can carry an already
# validated selected Drive configuration into the application layer.
# =====================================================================


def test_multi_month_run_options_preserve_selected_drive_config() -> None:
    selected_drive_config = AppConfig()

    options = MultiMonthRunOptions(
        archive_path=Path("export.zip"),
        periods=(
            ReportPeriod(
                year=2026,
                month=8,
            ),
        ),
        config_path=None,
        selected_drive_config=selected_drive_config,
    )

    assert options.selected_drive_config is selected_drive_config
