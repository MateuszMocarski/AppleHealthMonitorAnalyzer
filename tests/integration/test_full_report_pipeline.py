import json
import zipfile
from pathlib import Path

import pytest

from apple_health.analyzers.health_analyzer import HealthAnalyzer
from apple_health.enums import WorkoutType
from apple_health.importer import AppleHealthImporter
from apple_health.parser import AppleHealthParser
from apple_health.renderers.json_renderer import JsonRenderer
from apple_health.renderers.text_renderer import TextRenderer
from apple_health.config.app_config import AppConfig


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


def _run_pipeline(
    archive_path: Path,
    config: AppConfig,
):
    importer = AppleHealthImporter(archive_path)

    archive, xml_file = importer.open_export()

    try:
        health_data = AppleHealthParser(
            xml_file,
            config=config,
        ).parse()
    finally:
        xml_file.close()
        archive.close()

    analyzer = HealthAnalyzer(
        health_data,
        config=config,
    )

    return analyzer.summarize_month(
        year=2026,
        month=8,
    )


# =====================================================================
# Verifies the complete Apple Health report pipeline from a ZIP archive
# through importing, parsing and analysis to the final rendered report.
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
    assert "Workouts" in output
    assert "Walking" in output
    assert "Body weight:" in output
    assert "Average energy expenditure" in output
    assert "Average nutrition" in output

    assert "2026-08-01" in output
    assert "2026-08-02" in output


# =====================================================================
# Verifies that values imported from the Apple Health XML remain correct
# after parsing, aggregation and construction of the monthly report.
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
# monthly-only report without rendering individual daily report sections.
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
    assert payload["workouts"]

    assert "body_weight" in payload
    assert "energy_expenditure" in payload
    assert "nutrition" in payload
    assert "average_calories_balance_kcal" in payload

    assert "days" not in payload