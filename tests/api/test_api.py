import json
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from apple_health.api.app import app
from apple_health.application.application import AppleHealthApplication
from apple_health.application.monthly_reports import MonthlyReports
from apple_health.application.report_period import ReportPeriod
from apple_health.config.app_config import AppConfig

client = TestClient(app)


def _create_export_archive(
    tmp_path: Path,
) -> Path:
    config = AppConfig()
    source_config = config.source
    archive_path = tmp_path / "export.zip"

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
                type="HKQuantityTypeIdentifierSleepAnalysis"
                sourceName="{source_config.apple_watch_source}"
                value="HKCategoryValueSleepAnalysisAsleepCore"
                startDate="2026-08-01 00:00:00 +0200"
                endDate="2026-08-01 08:00:00 +0200"
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


# =====================================================================
# Verifies that the health endpoint confirms that the API is running.
# =====================================================================


def test_health_endpoint_returns_ok() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# =====================================================================
# Verifies that report generation rejects an invalid reporting month.
# =====================================================================


def test_report_generation_rejects_invalid_month() -> None:
    response = client.post(
        "/reports/generate",
        data={
            "year": "2026",
            "month": "13",
        },
        files={
            "archive": (
                "export.zip",
                b"not-a-real-zip",
                "application/zip",
            ),
        },
    )

    assert response.status_code == 422


# =====================================================================
# Verifies that report generation processes a synthetic Apple Health
# archive through the complete application pipeline.
# =====================================================================


def test_report_generation_returns_generated_report(
    tmp_path: Path,
) -> None:
    archive_path = _create_export_archive(tmp_path)

    with archive_path.open("rb") as archive:
        response = client.post(
            "/reports/generate",
            data={
                "periods": "2026-08",
            },
            files={
                "archive": (
                    "export.zip",
                    archive,
                    "application/zip",
                ),
            },
        )

    assert response.status_code == 200

    response_json = response.json()

    assert response.status_code == 200
    assert len(response_json["reports"]) == 1

    report = response_json["reports"][0]

    assert report["year"] == 2026
    assert report["month"] == 8

    full_json = json.loads(
        report["full_json"],
    )

    assert full_json["schema_version"] == "1.0"


# =====================================================================
# Verifies that report generation accepts multiple periods and returns
# all report variants for every requested month.
# =====================================================================


def test_generate_reports_for_multiple_months(
    monkeypatch,
) -> None:
    def fake_generate_reports(
        self,
        options,
    ):
        assert options.periods == (
            ReportPeriod(
                year=2026,
                month=8,
            ),
            ReportPeriod(
                year=2026,
                month=9,
            ),
        )

        return [
            MonthlyReports(
                period=ReportPeriod(
                    year=2026,
                    month=8,
                ),
                full_text="august-full-text",
                full_json="august-full-json",
                summary_text="august-summary-text",
                summary_json="august-summary-json",
            ),
            MonthlyReports(
                period=ReportPeriod(
                    year=2026,
                    month=9,
                ),
                full_text="september-full-text",
                full_json="september-full-json",
                summary_text="september-summary-text",
                summary_json="september-summary-json",
            ),
        ]

    monkeypatch.setattr(
        AppleHealthApplication,
        "generate_reports",
        fake_generate_reports,
    )

    response = client.post(
        "/reports/generate",
        files={
            "archive": (
                "export.zip",
                b"fake-archive",
                "application/zip",
            ),
        },
        data={
            "periods": "2026-08,2026-09",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "reports": [
            {
                "year": 2026,
                "month": 8,
                "full_text": "august-full-text",
                "full_json": "august-full-json",
                "summary_text": "august-summary-text",
                "summary_json": "august-summary-json",
            },
            {
                "year": 2026,
                "month": 9,
                "full_text": "september-full-text",
                "full_json": "september-full-json",
                "summary_text": "september-summary-text",
                "summary_json": "september-summary-json",
            },
        ]
    }
