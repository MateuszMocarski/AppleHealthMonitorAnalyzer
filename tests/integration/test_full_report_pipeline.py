import json
import zipfile
from pathlib import Path

import pytest

from apple_health.analyzers.health_analyzer import HealthAnalyzer
from apple_health.application.application import AppleHealthApplication
from apple_health.application.multi_month_run_options import MultiMonthRunOptions
from apple_health.application.report_period import ReportPeriod
from apple_health.config.app_config import AppConfig
from apple_health.config.config_loader import ConfigLoader
from apple_health.enums import WorkoutType
from apple_health.importer import AppleHealthImporter
from apple_health.parser import AppleHealthParser
from apple_health.renderers.json_renderer import JsonRenderer
from apple_health.renderers.text_renderer import TextRenderer


def _create_export_archive(
    tmp_path: Path,
    config: AppConfig,
) -> Path:
    archive_path = tmp_path / "export.zip"
    source_config = config.source
    xml = f"""
        <HealthData>
            <Record
                type="HKQuantityTypeIdentifierStepCount"
                sourceName="{source_config.apple_watch_source}"
                value="8000"
                startDate="2026-08-01 10:00:00 +0200"
                endDate="2026-08-01 10:00:00 +0200"
            />

            <Record
                type="HKQuantityTypeIdentifierStepCount"
                sourceName="{source_config.apple_watch_source}"
                value="9000"
                startDate="2026-08-02 10:00:00 +0200"
                endDate="2026-08-02 10:00:00 +0200"
            />

            <Record
                type="HKQuantityTypeIdentifierStepCount"
                sourceName="{source_config.apple_watch_source}"
                value="10000"
                startDate="2026-08-03 10:00:00 +0200"
                endDate="2026-08-03 10:00:00 +0200"
            />

            <Record
                type="HKQuantityTypeIdentifierDistanceWalkingRunning"
                sourceName="{source_config.apple_watch_source}"
                value="6.4"
                startDate="2026-08-01 10:00:00 +0200"
                endDate="2026-08-01 10:00:00 +0200"
            />

            <Record
                type="HKQuantityTypeIdentifierActiveEnergyBurned"
                sourceName="{source_config.apple_watch_source}"
                value="700"
                startDate="2026-08-01 10:00:00 +0200"
                endDate="2026-08-01 10:00:00 +0200"
            />

            <Record
                type="HKQuantityTypeIdentifierBasalEnergyBurned"
                sourceName="{source_config.apple_watch_source}"
                value="1900"
                startDate="2026-08-01 10:00:00 +0200"
                endDate="2026-08-01 10:00:00 +0200"
            />

            <Record
                type="HKQuantityTypeIdentifierBodyMass"
                sourceName="{source_config.apple_health_app_source}"
                value="80.0"
                startDate="2026-08-01 08:00:00 +0200"
                endDate="2026-08-01 08:00:00 +0200">
                <MetadataEntry
                    key="HKWasUserEntered"
                    value="1"
                />
            </Record>

            <Record
                type="HKQuantityTypeIdentifierDietaryEnergyConsumed"
                sourceName="{source_config.apple_health_app_source}"
                value="2000"
                startDate="2026-08-01 20:00:00 +0200"
                endDate="2026-08-01 20:00:00 +0200"
            />

            <Record
                type="HKQuantityTypeIdentifierDietaryProtein"
                sourceName="{source_config.apple_health_app_source}"
                value="150"
                startDate="2026-08-01 20:00:00 +0200"
                endDate="2026-08-01 20:00:00 +0200"
            />

            <Workout
                workoutActivityType="HKWorkoutActivityTypeWalking"
                sourceName="{source_config.apple_watch_source}"
                sourceVersion="1"
                startDate="2026-08-01 18:00:00 +0200"
                endDate="2026-08-01 19:00:00 +0200"
                duration="60">
                <WorkoutStatistics
                    type="HKQuantityTypeIdentifierActiveEnergyBurned"
                    sum="400"
                />
                <WorkoutStatistics
                    type="HKQuantityTypeIdentifierDistanceWalkingRunning"
                    sum="5.0"
                />
            </Workout>

            <Record
                type="HKCategoryTypeIdentifierSleepAnalysis"
                sourceName="{source_config.apple_watch_source}"
                value="HKCategoryValueSleepAnalysisAsleepCore"
                startDate="2026-08-01 00:00:00 +0200"
                endDate="2026-08-01 08:00:00 +0200"
            />

            <Record
                type="HKCategoryTypeIdentifierSleepAnalysis"
                sourceName="{source_config.apple_watch_source}"
                value="HKCategoryValueSleepAnalysisAsleepCore"
                startDate="2026-08-02 00:00:00 +0200"
                endDate="2026-08-02 08:00:00 +0200"
            />
        </HealthData>
        """

    with zipfile.ZipFile(
        archive_path,
        "w",
    ) as archive:
        archive.writestr(
            "apple_health_export/export.xml",
            xml,
        )

        return archive_path


def _create_multi_month_export_archive(
    tmp_path: Path,
    config: AppConfig,
) -> Path:
    archive_path = tmp_path / "multi_month_export.zip"
    source_config = config.source

    xml = f"""
        <HealthData>
            <Record
                type="HKQuantityTypeIdentifierStepCount"
                sourceName="{source_config.apple_watch_source}"
                value="8000"
                startDate="2026-08-01 10:00:00 +0200"
                endDate="2026-08-01 10:00:00 +0200"
            />

            <Record
                type="HKQuantityTypeIdentifierActiveEnergyBurned"
                sourceName="{source_config.apple_watch_source}"
                value="700"
                startDate="2026-08-01 10:00:00 +0200"
                endDate="2026-08-01 10:00:00 +0200"
            />

            <Record
                type="HKQuantityTypeIdentifierBasalEnergyBurned"
                sourceName="{source_config.apple_watch_source}"
                value="1900"
                startDate="2026-08-01 10:00:00 +0200"
                endDate="2026-08-01 10:00:00 +0200"
            />

            <Record
                type="HKQuantityTypeIdentifierStepCount"
                sourceName="{source_config.apple_watch_source}"
                value="9000"
                startDate="2026-09-01 10:00:00 +0200"
                endDate="2026-09-01 10:00:00 +0200"
            />

            <Record
                type="HKQuantityTypeIdentifierActiveEnergyBurned"
                sourceName="{source_config.apple_watch_source}"
                value="750"
                startDate="2026-09-01 10:00:00 +0200"
                endDate="2026-09-01 10:00:00 +0200"
            />

            <Record
                type="HKQuantityTypeIdentifierBasalEnergyBurned"
                sourceName="{source_config.apple_watch_source}"
                value="1900"
                startDate="2026-09-01 10:00:00 +0200"
                endDate="2026-09-01 10:00:00 +0200"
            />
            
            <Record
                type="HKQuantityTypeIdentifierStepCount"
                sourceName="{source_config.apple_watch_source}"
                value="10000"
                startDate="2026-09-02 10:00:00 +0200"
                endDate="2026-09-02 10:00:00 +0200"
            />
        </HealthData>
        """

    with zipfile.ZipFile(
        archive_path,
        "w",
    ) as archive:
        archive.writestr(
            "apple_health_export/export.xml",
            xml,
        )

    return archive_path


def _run_pipeline(
    archive_path: Path,
    config: AppConfig,
):
    importer = AppleHealthImporter(archive_path)

    with importer.open_export() as xml_file:
        health_data = AppleHealthParser(
            xml_file,
            config=config,
        ).parse()

    analyzer = HealthAnalyzer(
        health_data,
        config=config,
    )

    return analyzer.summarize_month(
        year=2026,
        month=8,
    )


# =====================================================================
# Verifies that the complete Apple Health report pipeline runs from ZIP
# import through rendering.
# =====================================================================


def test_full_report_pipeline(
    tmp_path: Path,
) -> None:
    config = AppConfig()
    archive_path = _create_export_archive(
        tmp_path,
        config,
    )

    summary = _run_pipeline(
        archive_path,
        config,
    )

    output = TextRenderer(
        config=config,
    ).render_month(summary)

    assert summary.reporting_days == 2
    assert len(summary.days) == 2

    assert "Apple Health Monthly Report" in output
    assert "August 2026" in output
    assert "Data available through: 2026-08-02" in output

    assert "General activity" in output
    assert "Sleep" in output
    assert "Sleep score" in output
    assert "Sleep configuration" in output
    assert "Workouts" in output
    assert "Walking" in output
    assert "Body weight:" in output
    assert "Average energy expenditure" in output
    assert "Average nutrition" in output

    assert "2026-08-01" in output
    assert "2026-08-02" in output


# =====================================================================
# Verifies that values imported from the Apple Health XML remain
# correct after parsing, aggregation and construction of the monthly
# report.
# =====================================================================


def test_full_pipeline_preserves_report_values(
    tmp_path: Path,
) -> None:
    config = AppConfig()
    archive_path = _create_export_archive(
        tmp_path,
        config,
    )

    summary = _run_pipeline(
        archive_path,
        config,
    )

    assert summary.reporting_days == 2

    assert summary.activity_metrics.total_steps == 17000

    assert summary.activity_metrics.total_distance_km == pytest.approx(6.4)

    assert summary.activity_metrics.average_daily_steps == 8500.0

    assert len(summary.activities) == 1

    walking = summary.activities[0]

    assert walking.activity_type == WorkoutType.WALKING
    assert walking.sessions == 1
    assert walking.duration_minutes == 60
    assert walking.active_energy_kcal == 400
    assert walking.distance_km == 5.0

    assert summary.sleep_summary.total_sessions == 2


# =====================================================================
# Verifies that the complete import and analysis pipeline can produce a
# monthly-only report without rendering individual daily report
# sections.
# =====================================================================


def test_month_summary_only_pipeline(
    tmp_path: Path,
) -> None:
    config = AppConfig()
    archive_path = _create_export_archive(
        tmp_path,
        config,
    )

    summary = _run_pipeline(
        archive_path,
        config,
    )

    output = TextRenderer(
        config=config,
    ).render_month_summary(summary)

    assert "Apple Health Monthly Report" in output
    assert "General activity" in output
    assert "Sleep score" in output
    assert "Sleep configuration" in output
    assert "Average nutrition" in output

    assert "\n2026-08-01\n" not in output
    assert "\n2026-08-02\n" not in output


# =====================================================================
# Verifies that the complete application pipeline produces exactly the
# approved deterministic text report for a known Apple Health export.
# =====================================================================


def test_full_pipeline_matches_golden_report(
    tmp_path: Path,
) -> None:
    config = AppConfig()
    archive_path = _create_export_archive(
        tmp_path,
        config,
    )

    summary = _run_pipeline(
        archive_path,
        config,
    )

    output = TextRenderer(
        config=config,
    ).render_month(summary)

    expected_report_path = Path(__file__).parent / "fixtures" / "expected_report.txt"

    expected_output = expected_report_path.read_text(encoding="utf-8")

    assert output == expected_output


# =====================================================================
# Verifies that the complete Apple Health pipeline can produce a valid
# JSON report containing both monthly summary data and daily reports.
# =====================================================================


def test_full_pipeline_renders_json_report(
    tmp_path: Path,
) -> None:
    config = AppConfig()
    archive_path = _create_export_archive(
        tmp_path,
        config,
    )

    summary = _run_pipeline(
        archive_path,
        config,
    )

    output = JsonRenderer(
        config=config,
    ).render_month(summary)

    payload = json.loads(output)

    assert payload["schema_version"] == "1.0"

    assert payload["report"] == {
        "type": "monthly",
        "year": 2026,
        "month": 8,
        "reporting_days": 2,
        "data_through": "2026-08-02",
    }

    assert payload["general_activity"] is not None
    assert payload["sleep"] is not None
    assert payload["sleep"]["configuration"]["duration"]["target_minutes"] == (
        config.sleep.score.duration.target_minutes
    )
    assert payload["workouts"]

    assert "days" in payload
    assert len(payload["days"]) == 2

    assert payload["days"][0]["date"] == "2026-08-01"
    assert payload["days"][1]["date"] == "2026-08-02"


# =====================================================================
# Verifies that the complete Apple Health pipeline can produce a valid
# JSON monthly summary without including detailed daily report entries.
# =====================================================================


def test_full_pipeline_renders_json_month_summary(
    tmp_path: Path,
) -> None:
    config = AppConfig()
    archive_path = _create_export_archive(
        tmp_path,
        config,
    )

    summary = _run_pipeline(
        archive_path,
        config,
    )

    output = JsonRenderer(
        config=config,
    ).render_month_summary(summary)

    payload = json.loads(output)

    assert payload["schema_version"] == "1.0"

    assert payload["report"] == {
        "type": "monthly",
        "year": 2026,
        "month": 8,
        "reporting_days": 2,
        "data_through": "2026-08-02",
    }

    assert payload["general_activity"] is not None
    assert payload["sleep"] is not None
    assert payload["sleep"]["configuration"]["duration"]["target_minutes"] == (
        config.sleep.score.duration.target_minutes
    )
    assert payload["workouts"]

    assert "body_weight" in payload
    assert "energy_expenditure" in payload
    assert "nutrition" in payload
    assert "average_calories_balance_kcal" in payload

    assert "days" not in payload


# =====================================================================
# Verifies that the committed example application configuration is
# loadable by ConfigLoader.
# =====================================================================


def test_example_config_file_is_loadable() -> None:
    config_path = Path("apple_health/config/examples/config.example.toml")

    config = ConfigLoader.load(config_path)

    assert config.sleep.session_gap_threshold_minutes == 30
    assert config.sleep.score.duration.target_minutes == 480
    assert config.sleep.score.wake_up.target.hour == 8


# =====================================================================
# Verifies that TOML configuration overrides change the effective
# sleep-scoring settings.
# =====================================================================


def test_toml_configuration_changes_sleep_scoring(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.toml"

    config_path.write_text(
        """
        [sleep.score.duration]
        target_minutes = 420
        tolerance_minutes = 10
        undersleep_weight = 2.0

        [sleep.score.weights]
        bedtime = 1.0
        duration = 5.0
        wake_up = 1.0
        """,
        encoding="utf-8",
    )

    config = ConfigLoader.load(config_path)

    archive_path = _create_export_archive(
        tmp_path,
        config,
    )

    summary = _run_pipeline(
        archive_path,
        config,
    )

    assert summary.sleep_summary is not None
    assert summary.sleep_summary.average_sleep_score != 100.0


# =====================================================================
# Verifies that TOML sleep-scoring overrides produce an observable
# change in the pipeline result.
# =====================================================================


def test_toml_configuration_changes_pipeline_result(
    tmp_path: Path,
) -> None:
    default_config = AppConfig()

    archive_path = _create_export_archive(
        tmp_path,
        default_config,
    )

    default_summary = _run_pipeline(
        archive_path,
        default_config,
    )

    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
        [sleep.score.duration]
        target_minutes = 540
        tolerance_minutes = 0
        penalty_interval_minutes = 15
        penalty_points = 5.0
        """,
        encoding="utf-8",
    )

    custom_config = ConfigLoader.load(config_path)

    custom_summary = _run_pipeline(
        archive_path,
        custom_config,
    )

    assert default_summary.sleep_summary.average_sleep_score == 100.0
    assert custom_summary.sleep_summary.average_sleep_score < 100.0


# =====================================================================
# Verifies that the pipeline uses default application configuration
# when no TOML file is supplied.
# =====================================================================


def test_pipeline_without_config_uses_default_configuration(
    tmp_path: Path,
) -> None:
    config = ConfigLoader.load(None)

    assert config == AppConfig()

    archive_path = _create_export_archive(
        tmp_path,
        config,
    )

    summary = _run_pipeline(
        archive_path,
        config,
    )

    assert summary.sleep_summary is not None


# =====================================================================
# Verifies that multi-month report generation processes one Apple
# Health archive and returns all report variants for each requested month.
# =====================================================================


def test_multi_month_report_generation_pipeline(
    tmp_path: Path,
) -> None:
    config = AppConfig()
    archive_path = _create_multi_month_export_archive(
        tmp_path,
        config,
    )

    options = MultiMonthRunOptions(
        archive_path=archive_path,
        periods=(
            ReportPeriod(
                year=2026,
                month=8,
            ),
            ReportPeriod(
                year=2026,
                month=9,
            ),
        ),
        config_path=None,
    )

    reports = AppleHealthApplication().generate_reports(
        options,
    )

    assert len(reports) == 2

    august_report = reports[0]
    september_report = reports[1]

    assert august_report.period == ReportPeriod(
        year=2026,
        month=8,
    )
    assert september_report.period == ReportPeriod(
        year=2026,
        month=9,
    )

    assert august_report.full_text
    assert august_report.full_json
    assert august_report.summary_text
    assert august_report.summary_json

    assert september_report.full_text
    assert september_report.full_json
    assert september_report.summary_text
    assert september_report.summary_json

    august_json = json.loads(
        august_report.full_json,
    )
    september_json = json.loads(
        september_report.full_json,
    )

    assert august_json["report"]["year"] == 2026
    assert august_json["report"]["month"] == 8

    assert september_json["report"]["year"] == 2026
    assert september_json["report"]["month"] == 9

    assert august_json["schema_version"] == "1.0"
    assert september_json["schema_version"] == "1.0"

    assert august_json["general_activity"]["total_steps"] == 8000

    assert september_json["general_activity"]["total_steps"] == 9000

    assert all(day["date"].startswith("2026-08") for day in august_json["days"])

    assert all(day["date"].startswith("2026-09") for day in september_json["days"])
