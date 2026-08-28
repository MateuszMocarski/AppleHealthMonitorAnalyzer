import json
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from apple_health.api.app import app
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
                "year": "2026",
                "month": "8",
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

    body = response.json()

    assert body["year"] == 2026
    assert body["month"] == 8
    assert body["content"]

    report = json.loads(body["content"])

    assert report["schema_version"] == "1.0"
