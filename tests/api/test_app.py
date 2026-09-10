import json
import re
import zipfile
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse
from zipfile import ZipFile

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import apple_health.api.app as api_app_module
from apple_health.api.app import MAX_UPLOAD_SIZE, app, download_drive_archive, verify_drive_archive
from apple_health.application.application import AppleHealthApplication
from apple_health.application.monthly_reports import MonthlyReports
from apple_health.application.report_generation_metadata import (
    ReportGenerationMetadata,
)
from apple_health.application.report_generation_result import (
    ReportGenerationResult,
)
from apple_health.application.report_outputs import ReportOutputs
from apple_health.application.report_period import ReportPeriod
from apple_health.config.app_config import AppConfig
from apple_health.config.exceptions import ConfigurationError
from apple_health.exceptions import (
    ExportXmlTooLargeError,
    HealthDataParseError,
    InvalidArchiveError,
)
from apple_health.google.config_profiles import ConfigProfile
from apple_health.google.drive import (
    DriveAccessError,
    DriveDownloadTooLargeError,
    DriveFileMetadata,
    DriveTransientError,
)
from apple_health.google.oauth import (
    GoogleOAuthError,
    GoogleOAuthService,
    GoogleTokenResponse,
)
from apple_health.google.sessions import SessionStore

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


def _generation_result(
    reports=(),
) -> ReportGenerationResult:
    return ReportGenerationResult(
        reports=tuple(reports),
        effective_config=AppConfig(),
    )


# =====================================================================
# Verifies that the health endpoint confirms that the API is running.
# =====================================================================


def test_health_endpoint_returns_ok() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


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

        return _generation_result(
            [
                MonthlyReports(
                    period=ReportPeriod(
                        year=2026,
                        month=8,
                    ),
                    full_text="august-full-text",
                    full_json="august-full-json",
                    summary_text="august-summary-text",
                    summary_json="august-summary-json",
                    metadata=ReportGenerationMetadata(
                        period=ReportPeriod(
                            year=2026,
                            month=8,
                        ),
                        generation_id="generation-123",
                        generated_at=datetime(
                            2026,
                            9,
                            10,
                            20,
                            30,
                            tzinfo=timezone.utc,
                        ),
                    ),
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
                    metadata=ReportGenerationMetadata(
                        period=ReportPeriod(
                            year=2026,
                            month=9,
                        ),
                        generation_id="generation-456",
                        generated_at=datetime(
                            2026,
                            9,
                            10,
                            20,
                            31,
                            tzinfo=timezone.utc,
                        ),
                    ),
                ),
            ]
        )

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
                "generation_id": "generation-123",
                "generated_at": "2026-09-10T20:30:00Z",
            },
            {
                "year": 2026,
                "month": 9,
                "full_text": "september-full-text",
                "full_json": "september-full-json",
                "summary_text": "september-summary-text",
                "summary_json": "september-summary-json",
                "generation_id": "generation-456",
                "generated_at": "2026-09-10T20:31:00Z",
            },
        ]
    }


# =====================================================================
# Verifies that report generation rejects archives exceeding the
# configured upload size limit.
# =====================================================================


def test_report_generation_rejects_oversized_archive(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "apple_health.api.app.MAX_UPLOAD_SIZE",
        10,
    )

    response = client.post(
        "/reports/generate",
        files={
            "archive": (
                "export.zip",
                b"12345678901",
                "application/zip",
            ),
        },
        data={
            "periods": "2026-08",
        },
    )

    assert response.status_code == 413
    assert response.json() == {
        "detail": "Uploaded archive is too large.",
    }


# =====================================================================
# Verifies that report generation returns a client error when a
# reporting period is invalid.
# =====================================================================


def test_report_generation_rejects_invalid_period() -> None:
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
            "periods": "2026-13",
        },
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": "Invalid reporting period.",
    }


# =====================================================================
# Verifies that the web interface exposes a favicon without returning
# a missing-resource error to the browser.
# =====================================================================


def test_favicon_is_available() -> None:
    response = client.get(
        "/favicon.svg",
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/svg+xml")


# =====================================================================
# Verifies that report generation rejects an empty reporting period
# instead of attempting to generate a report.
# =====================================================================


def test_report_generation_rejects_empty_periods() -> None:
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
            "periods": "",
        },
    )

    assert response.status_code == 422


# =====================================================================
# Verifies that report generation rejects reporting periods containing
# only whitespace.
# =====================================================================


def test_report_generation_rejects_whitespace_periods() -> None:
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
            "periods": "   ",
        },
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": "Invalid reporting period.",
    }


# =====================================================================
# Verifies that report generation accepts reporting periods separated
# by commas with surrounding whitespace.
# =====================================================================


def test_report_generation_accepts_whitespace_between_periods(
    monkeypatch,
) -> None:
    captured_periods = None

    def fake_generate_reports(
        self,
        options,
    ):
        nonlocal captured_periods
        captured_periods = options.periods
        return _generation_result()

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
            "periods": "2026-08, 2026-09",
        },
    )

    assert response.status_code == 200
    assert captured_periods == (
        ReportPeriod(
            year=2026,
            month=8,
        ),
        ReportPeriod(
            year=2026,
            month=9,
        ),
    )


# =====================================================================
# Verifies that report generation rejects duplicate reporting periods
# instead of generating the same month more than once.
# =====================================================================


def test_report_generation_rejects_duplicate_periods() -> None:
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
            "periods": "2026-08,2026-08",
        },
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": "Duplicate reporting periods are not allowed.",
    }


# =====================================================================
# Verifies that report generation rejects files that are not valid ZIP
# archives instead of returning an internal server error.
# =====================================================================


def test_report_generation_rejects_invalid_zip_archive() -> None:
    response = client.post(
        "/reports/generate",
        files={
            "archive": (
                "export.zip",
                b"this-is-not-a-zip",
                "application/zip",
            ),
        },
        data={
            "periods": "2026-08",
        },
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": "Invalid Apple Health export archive.",
    }


# =====================================================================
# Verifies that report generation rejects ZIP archives that do not
# contain the Apple Health export.xml file.
# =====================================================================


def test_report_generation_rejects_archive_without_export_xml() -> None:
    archive_buffer = BytesIO()

    with ZipFile(
        archive_buffer,
        "w",
    ) as archive:
        archive.writestr(
            "apple_health_export/readme.txt",
            "not an Apple Health export",
        )

    response = client.post(
        "/reports/generate",
        files={
            "archive": (
                "export.zip",
                archive_buffer.getvalue(),
                "application/zip",
            ),
        },
        data={
            "periods": "2026-08",
        },
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": "Apple Health export XML not found in archive.",
    }


# =====================================================================
# Verifies that an archive containing multiple candidate Apple Health
# export XML files is rejected with a controlled API error.
# =====================================================================


def test_report_generation_rejects_archive_with_multiple_export_xml_files(
    tmp_path: Path,
) -> None:
    archive_path = tmp_path / "export.zip"

    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(
            "apple_health_export/export.xml",
            "<HealthData />",
        )
        archive.writestr(
            "apple_health_export/eksport.xml",
            "<HealthData />",
        )

    with archive_path.open("rb") as archive_file:
        response = client.post(
            "/reports/generate",
            files={
                "archive": (
                    "export.zip",
                    archive_file,
                    "application/zip",
                ),
            },
            data={
                "periods": "2026-08",
            },
        )

    assert response.status_code == 422
    assert response.json() == {
        "detail": ("Archive contains multiple Apple Health " "export XML files."),
    }


# =====================================================================
# Verifies that report generation rejects an empty ZIP archive because
# it does not contain an Apple Health export XML file.
# =====================================================================


def test_report_generation_rejects_empty_zip_archive() -> None:
    archive_buffer = BytesIO()

    with ZipFile(
        archive_buffer,
        "w",
    ):
        pass

    response = client.post(
        "/reports/generate",
        files={
            "archive": (
                "export.zip",
                archive_buffer.getvalue(),
                "application/zip",
            ),
        },
        data={
            "periods": "2026-08",
        },
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": "Apple Health export XML not found in archive.",
    }


# =====================================================================
# Verifies that report generation rejects archives whose export.xml
# content is not valid XML.
# =====================================================================


def test_report_generation_rejects_invalid_export_xml() -> None:
    archive_buffer = BytesIO()

    with ZipFile(
        archive_buffer,
        "w",
    ) as archive:
        archive.writestr(
            "apple_health_export/export.xml",
            "this-is-not-valid-xml",
        )

    response = client.post(
        "/reports/generate",
        files={
            "archive": (
                "export.zip",
                archive_buffer.getvalue(),
                "application/zip",
            ),
        },
        data={
            "periods": "2026-08",
        },
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": "Invalid Apple Health export XML.",
    }


# =====================================================================
# Verifies that report generation rejects valid XML that is not an
# Apple Health export document.
# =====================================================================


def test_report_generation_rejects_non_apple_health_xml() -> None:
    archive_buffer = BytesIO()

    with ZipFile(
        archive_buffer,
        "w",
    ) as archive:
        archive.writestr(
            "apple_health_export/export.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<NotHealthData>
    <Something />
</NotHealthData>
""",
        )

    response = client.post(
        "/reports/generate",
        files={
            "archive": (
                "export.zip",
                archive_buffer.getvalue(),
                "application/zip",
            ),
        },
        data={
            "periods": "2026-08",
        },
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": "Invalid Apple Health export XML.",
    }


# =====================================================================
# Verifies that report generation accepts a valid Apple Health archive
# regardless of the uploaded filename or MIME type.
# =====================================================================


def test_report_generation_does_not_trust_filename_or_mime_type(
    monkeypatch,
) -> None:
    archive_buffer = BytesIO()

    with ZipFile(
        archive_buffer,
        "w",
    ) as archive:
        archive.writestr(
            "apple_health_export/export.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<HealthData>
</HealthData>
""",
        )

    monkeypatch.setattr(
        AppleHealthApplication,
        "generate_reports",
        lambda self, options: _generation_result(),
    )

    response = client.post(
        "/reports/generate",
        files={
            "archive": (
                "archive.bin",
                archive_buffer.getvalue(),
                "application/octet-stream",
            ),
        },
        data={
            "periods": "2026-08",
        },
    )

    assert response.status_code == 200


# =====================================================================
# Verifies that report generation rejects requests without an uploaded
# archive file.
# =====================================================================


def test_report_generation_rejects_missing_archive() -> None:
    response = client.post(
        "/reports/generate",
        data={
            "periods": "2026-08",
        },
    )

    assert response.status_code == 422


# =====================================================================
# Verifies that the temporary uploaded archive is deleted after report
# generation completes successfully.
# =====================================================================


def test_report_generation_deletes_temporary_archive_after_success(
    monkeypatch,
) -> None:
    temporary_archive_path = None

    def fake_generate_reports(
        self,
        options,
    ):
        nonlocal temporary_archive_path
        temporary_archive_path = options.archive_path

        assert temporary_archive_path.exists()

        return _generation_result()

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
            "periods": "2026-08",
        },
    )

    assert response.status_code == 200
    assert temporary_archive_path is not None
    assert not temporary_archive_path.exists()


# =====================================================================
# Verifies that the temporary uploaded archive is deleted when report
# generation fails.
# =====================================================================


def test_report_generation_deletes_temporary_archive_after_failure(
    monkeypatch,
) -> None:
    temporary_archive_path = None

    def fake_generate_reports(
        self,
        options,
    ):
        nonlocal temporary_archive_path
        temporary_archive_path = options.archive_path

        assert temporary_archive_path.exists()

        raise InvalidArchiveError

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
            "periods": "2026-08",
        },
    )

    assert response.status_code == 422
    assert temporary_archive_path is not None
    assert not temporary_archive_path.exists()


# =====================================================================
# Verifies that unexpected application errors are not misclassified as
# client input errors.
# =====================================================================


def test_report_generation_preserves_unexpected_server_errors(
    monkeypatch,
) -> None:
    def fake_generate_reports(
        self,
        options,
    ):
        raise RuntimeError("unexpected failure")

    monkeypatch.setattr(
        AppleHealthApplication,
        "generate_reports",
        fake_generate_reports,
    )

    client_without_server_exceptions = TestClient(
        app,
        raise_server_exceptions=False,
    )

    response = client_without_server_exceptions.post(
        "/reports/generate",
        files={
            "archive": (
                "export.zip",
                b"fake-archive",
                "application/zip",
            ),
        },
        data={
            "periods": "2026-08",
        },
    )

    assert response.status_code == 500


# =====================================================================
# Verifies that unexpected ValueError exceptions remain server errors
# instead of being incorrectly converted into client input errors.
# =====================================================================


def test_report_generation_preserves_unexpected_value_errors(
    monkeypatch,
) -> None:
    def fake_generate_reports(
        self,
        options,
    ):
        raise ValueError("unexpected value error")

    monkeypatch.setattr(
        AppleHealthApplication,
        "generate_reports",
        fake_generate_reports,
    )

    client_without_server_exceptions = TestClient(
        app,
        raise_server_exceptions=False,
    )

    response = client_without_server_exceptions.post(
        "/reports/generate",
        files={
            "archive": (
                "export.zip",
                b"fake-archive",
                "application/zip",
            ),
        },
        data={
            "periods": "2026-08",
        },
    )

    assert response.status_code == 500


# =====================================================================
# Verifies that unexpected server errors do not expose their exception
# messages in the HTTP response body.
# =====================================================================


def test_report_generation_does_not_expose_server_error_message(
    monkeypatch,
) -> None:
    def fake_generate_reports(
        self,
        options,
    ):
        raise RuntimeError("SECRET_INTERNAL_ERROR_MESSAGE")

    monkeypatch.setattr(
        AppleHealthApplication,
        "generate_reports",
        fake_generate_reports,
    )

    client_without_server_exceptions = TestClient(
        app,
        raise_server_exceptions=False,
    )

    response = client_without_server_exceptions.post(
        "/reports/generate",
        files={
            "archive": (
                "export.zip",
                b"fake-archive",
                "application/zip",
            ),
        },
        data={
            "periods": "2026-08",
        },
    )

    assert response.status_code == 500
    assert "SECRET_INTERNAL_ERROR_MESSAGE" not in response.text


# =====================================================================
# Verifies that unexpected server errors do not expose local filesystem
# paths in the HTTP response body.
# =====================================================================


def test_report_generation_does_not_expose_local_paths(
    monkeypatch,
) -> None:
    local_path = "/home/private/apple-health/export.xml"

    def fake_generate_reports(
        self,
        options,
    ):
        raise RuntimeError(f"Failed while reading {local_path}")

    monkeypatch.setattr(
        AppleHealthApplication,
        "generate_reports",
        fake_generate_reports,
    )

    client_without_server_exceptions = TestClient(
        app,
        raise_server_exceptions=False,
    )

    response = client_without_server_exceptions.post(
        "/reports/generate",
        files={
            "archive": (
                "export.zip",
                b"fake-archive",
                "application/zip",
            ),
        },
        data={
            "periods": "2026-08",
        },
    )

    assert response.status_code == 500
    assert local_path not in response.text


# =====================================================================
# Verifies that the known Apple Health root validation error is exposed
# as a stable client-facing API error.
# =====================================================================


def test_report_generation_maps_invalid_health_root_to_stable_error(
    monkeypatch,
) -> None:
    def fake_generate_reports(
        self,
        options,
    ):
        raise HealthDataParseError("Invalid Apple Health export XML.")

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
            "periods": "2026-08",
        },
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": "Invalid Apple Health export XML.",
    }


# =====================================================================
# Verifies that unexpected exceptions from the application layer are
# not accidentally swallowed by API-specific exception handling.
# =====================================================================


def test_report_generation_preserves_unhandled_exception_types(
    monkeypatch,
) -> None:
    def fake_generate_reports(
        self,
        options,
    ):
        raise OSError("unexpected filesystem failure")

    monkeypatch.setattr(
        AppleHealthApplication,
        "generate_reports",
        fake_generate_reports,
    )

    client_without_server_exceptions = TestClient(
        app,
        raise_server_exceptions=False,
    )

    response = client_without_server_exceptions.post(
        "/reports/generate",
        files={
            "archive": (
                "export.zip",
                b"fake-archive",
                "application/zip",
            ),
        },
        data={
            "periods": "2026-08",
        },
    )

    assert response.status_code == 500


# =====================================================================
# Verifies that report generation rejects requests containing more
# reporting periods than the configured safety limit.
# =====================================================================


def test_report_generation_rejects_too_many_periods(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "apple_health.api.app.MAX_REPORT_PERIODS",
        2,
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
            "periods": "2026-08,2026-09,2026-10",
        },
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": "Too many reporting periods requested.",
    }


# =====================================================================
# Verifies that an oversized Apple Health export XML is exposed as a
# controlled payload-too-large API response.
# =====================================================================


def test_report_generation_rejects_oversized_export_xml(
    monkeypatch,
) -> None:
    def fake_generate_reports(
        self,
        options,
    ):
        raise ExportXmlTooLargeError

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
            "periods": "2026-08",
        },
    )

    assert response.status_code == 413
    assert response.json() == {
        "detail": "Apple Health export XML is too large.",
    }


# =====================================================================
# Verifies that generated health reports are explicitly marked as
# non-cacheable because the response contains private health data.
# =====================================================================


def test_report_generation_disables_response_caching(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        AppleHealthApplication,
        "generate_reports",
        lambda self, options: _generation_result(),
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
            "periods": "2026-08",
        },
    )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"


# =====================================================================
# Verifies that optional source overrides submitted by the web client
# are normalized and forwarded to multi-month report generation.
# =====================================================================


def test_report_generation_forwards_source_overrides(
    monkeypatch,
) -> None:
    def fake_generate_reports(
        self,
        options,
    ):
        assert options.apple_watch_source == "Custom Watch"
        assert options.apple_health_app_source == "Custom Health"

        return _generation_result()

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
            "periods": "2026-08",
            "apple_watch_source": "  Custom Watch  ",
            "apple_health_app_source": "  Custom Health  ",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "reports": [],
    }


# =====================================================================
# Verifies that blank source fields are treated as absent overrides so
# the configured defaults remain effective.
# =====================================================================


def test_report_generation_ignores_blank_source_overrides(
    monkeypatch,
) -> None:
    def fake_generate_reports(
        self,
        options,
    ):
        assert options.apple_watch_source is None
        assert options.apple_health_app_source is None

        return _generation_result()

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
            "periods": "2026-08",
            "apple_watch_source": "   ",
            "apple_health_app_source": "",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "reports": [],
    }


# =====================================================================
# Verifies that the web interface exposes optional source override
# controls together with the Apple Watch NBSP default warning.
# =====================================================================


def test_web_interface_exposes_source_override_controls() -> None:
    response = client.get("/")

    assert response.status_code == 200

    html = response.text

    assert 'id="apple-watch-source"' in html
    assert 'id="apple-health-app-source"' in html
    assert "Apple\\xa0Watch" in html
    assert "NBSP / U+00A0" in html


# =====================================================================
# Verifies that an uploaded TOML configuration is available during
# report generation and removed after the request is completed.
# =====================================================================


def test_report_generation_forwards_uploaded_config(
    monkeypatch,
) -> None:
    config_content = """
[source]
apple_health_app_source = "Custom Health"
"""

    captured_config_path: Path | None = None

    def fake_generate_reports(
        self,
        options,
    ):
        nonlocal captured_config_path

        captured_config_path = options.config_path

        assert captured_config_path is not None
        assert captured_config_path.exists()
        assert (
            captured_config_path.read_text(
                encoding="utf-8",
            )
            == config_content
        )

        return _generation_result()

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
            "config": (
                "config.toml",
                config_content.encode(),
                "application/toml",
            ),
        },
        data={
            "periods": "2026-08",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "reports": [],
    }

    assert captured_config_path is not None
    assert not captured_config_path.exists()


# =====================================================================
# Verifies that malformed uploaded TOML configuration is rejected as
# invalid client input instead of causing an internal server error.
# =====================================================================


def test_report_generation_rejects_malformed_config() -> None:
    response = client.post(
        "/reports/generate",
        files={
            "archive": (
                "export.zip",
                b"fake-archive",
                "application/zip",
            ),
            "config": (
                "config.toml",
                b"[source",
                "application/toml",
            ),
        },
        data={
            "periods": "2026-08",
        },
    )

    assert response.status_code == 422
    assert "Invalid TOML configuration" in response.json()["detail"]


# =====================================================================
# Verifies that uploaded configuration files exceeding the dedicated
# size limit are rejected before configuration parsing.
# =====================================================================


def test_report_generation_rejects_oversized_config(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "apple_health.api.app.MAX_CONFIG_UPLOAD_SIZE",
        10,
    )

    response = client.post(
        "/reports/generate",
        files={
            "archive": (
                "export.zip",
                b"fake-archive",
                "application/zip",
            ),
            "config": (
                "config.toml",
                b"12345678901",
                "application/toml",
            ),
        },
        data={
            "periods": "2026-08",
        },
    )

    assert response.status_code == 413
    assert response.json() == {
        "detail": "Uploaded configuration is too large.",
    }


# =====================================================================
# Verifies that the downloadable example configuration is served from
# the repository's canonical config.example.toml file.
# =====================================================================


def test_example_config_download_returns_canonical_file() -> None:
    example_config_path = (
        Path(__file__).parents[2] / "apple_health" / "config" / "examples" / "config.example.toml"
    )

    response = client.get(
        "/config.example.toml",
    )

    assert response.status_code == 200
    assert response.content == example_config_path.read_bytes()
    assert 'filename="config.example.toml"' in response.headers["content-disposition"]


# =====================================================================
# Verifies that semantically invalid Apple Health record values are
# mapped to the stable invalid-export HTTP 422 response.
# =====================================================================


def test_report_generation_rejects_invalid_numeric_xml_value() -> None:
    source_name = AppConfig().source.apple_watch_source
    archive_buffer = BytesIO()

    with ZipFile(
        archive_buffer,
        "w",
    ) as archive:
        archive.writestr(
            "apple_health_export/export.xml",
            f"""<HealthData>
<Record
    type="HKQuantityTypeIdentifierStepCount"
    sourceName="{source_name}"
    value="not-a-number"
    startDate="2026-08-01 10:00:00 +0200"
    endDate="2026-08-01 10:00:00 +0200"
/>
</HealthData>""",
        )

    response = client.post(
        "/reports/generate",
        files={
            "archive": (
                "export.zip",
                archive_buffer.getvalue(),
                "application/zip",
            ),
        },
        data={
            "periods": "2026-08",
        },
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": "Invalid Apple Health export XML.",
    }


# =====================================================================
# Verifies that Apple Health records missing required attributes are
# mapped to the stable invalid-export HTTP 422 response.
# =====================================================================


def test_report_generation_rejects_missing_required_xml_attribute() -> None:
    source_name = AppConfig().source.apple_watch_source
    archive_buffer = BytesIO()

    with ZipFile(
        archive_buffer,
        "w",
    ) as archive:
        archive.writestr(
            "apple_health_export/export.xml",
            f"""<HealthData>
<Record
    type="HKQuantityTypeIdentifierStepCount"
    sourceName="{source_name}"
    value="100"
    endDate="2026-08-01 10:00:00 +0200"
/>
</HealthData>""",
        )

    response = client.post(
        "/reports/generate",
        files={
            "archive": (
                "export.zip",
                archive_buffer.getvalue(),
                "application/zip",
            ),
        },
        data={
            "periods": "2026-08",
        },
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": "Invalid Apple Health export XML.",
    }


# =====================================================================
# Verifies that non-finite Apple Health numeric values are rejected as
# invalid export data instead of reaching generated JSON reports.
# =====================================================================


def test_report_generation_rejects_non_finite_xml_value() -> None:
    source_name = AppConfig().source.apple_watch_source
    archive_buffer = BytesIO()

    with ZipFile(
        archive_buffer,
        "w",
    ) as archive:
        archive.writestr(
            "apple_health_export/export.xml",
            f"""<HealthData>
<Record
    type="HKQuantityTypeIdentifierActiveEnergyBurned"
    sourceName="{source_name}"
    value="nan"
    startDate="2026-08-01 10:00:00 +0200"
    endDate="2026-08-01 10:00:00 +0200"
/>
</HealthData>""",
        )

    response = client.post(
        "/reports/generate",
        files={
            "archive": (
                "export.zip",
                archive_buffer.getvalue(),
                "application/zip",
            ),
        },
        data={
            "periods": "2026-08",
        },
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": "Invalid Apple Health export XML.",
    }


# =====================================================================
# Verifies that non-finite TOML configuration values are rejected at
# the HTTP boundary with a controlled configuration error.
# =====================================================================


def test_report_generation_rejects_non_finite_config_value() -> None:
    response = client.post(
        "/reports/generate",
        files={
            "archive": (
                "export.zip",
                b"fake-archive",
                "application/zip",
            ),
            "config": (
                "config.toml",
                b"[sleep.score.bedtime]\npenalty_points = nan\n",
                "application/toml",
            ),
        },
        data={
            "periods": "2026-08",
        },
    )

    assert response.status_code == 422
    assert "Expected finite number" in response.json()["detail"]


# =====================================================================
# Verifies that starting Google OAuth creates a backend session, sets
# its opaque cookie, and redirects the browser to Google authorization.
# =====================================================================


def test_google_oauth_start_redirects_with_backend_session(
    monkeypatch,
) -> None:
    monkeypatch.setenv("AHM_ENV", "development")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "dev-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "dev-client-secret")
    monkeypatch.setenv(
        "GOOGLE_REDIRECT_URI",
        "http://localhost:8000/auth/google/callback",
    )
    monkeypatch.setenv("GOOGLE_PICKER_API_KEY", "dev-picker-key")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT_NUMBER", "123456789")
    monkeypatch.setenv("AHM_SESSION_SECRET", "dev-session-secret")

    sessions = SessionStore()

    monkeypatch.setattr(
        api_app_module,
        "session_store",
        sessions,
    )

    auth_client = TestClient(app)

    response = auth_client.get(
        "/auth/google/start",
        follow_redirects=False,
    )

    assert response.status_code == 302

    authorization_url = urlparse(response.headers["location"])
    query = parse_qs(authorization_url.query)

    assert authorization_url.scheme == "https"
    assert authorization_url.netloc == "accounts.google.com"

    session_id = response.cookies["ahm_session"]
    session = sessions.get(session_id)

    assert session is not None
    assert session.oauth_state is not None
    assert query["state"] == [session.oauth_state]

    set_cookie = response.headers["set-cookie"]

    assert "HttpOnly" in set_cookie
    assert "SameSite=lax" in set_cookie
    assert "Secure" not in set_cookie


# =====================================================================
# Verifies that a valid Google OAuth callback exchanges the
# authorization code and stores the access token in the backend session.
# =====================================================================


def test_google_oauth_callback_completes_backend_session(
    monkeypatch,
) -> None:
    monkeypatch.setenv("AHM_ENV", "development")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "dev-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "dev-client-secret")
    monkeypatch.setenv(
        "GOOGLE_REDIRECT_URI",
        "http://localhost:8000/auth/google/callback",
    )
    monkeypatch.setenv("GOOGLE_PICKER_API_KEY", "dev-picker-key")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT_NUMBER", "123456789")
    monkeypatch.setenv("AHM_SESSION_SECRET", "dev-session-secret")

    sessions = SessionStore()
    session_id = sessions.create()

    sessions.set_oauth_state(
        session_id,
        "expected-state",
    )

    monkeypatch.setattr(
        api_app_module,
        "session_store",
        sessions,
    )

    class FakeTokenClient:
        def exchange_code(
            self,
            code: str,
            client_id: str,
            client_secret: str,
            redirect_uri: str,
        ) -> GoogleTokenResponse:
            return GoogleTokenResponse(
                access_token="access-token",
                expires_in_seconds=3600,
                granted_scopes=frozenset(GoogleOAuthService.SCOPES),
            )

    class FakeIdentity:
        sub = "google-user-123"
        email = "user@example.com"

    class FakeIdentityClient:
        def get_identity(
            self,
            access_token: str,
        ) -> FakeIdentity:
            assert access_token == "access-token"

            return FakeIdentity()

    monkeypatch.setattr(
        api_app_module,
        "google_token_client",
        FakeTokenClient(),
    )

    monkeypatch.setattr(
        api_app_module,
        "google_identity_client",
        FakeIdentityClient(),
        raising=False,
    )

    auth_client = TestClient(app)
    auth_client.cookies.set(
        "ahm_session",
        session_id,
    )

    response = auth_client.get(
        "/auth/google/callback",
        params={
            "code": "authorization-code",
            "state": "expected-state",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/"

    session = sessions.get(session_id)

    assert session is not None
    assert session.oauth_state is None
    assert session.google_access_token == "access-token"
    assert session.google_sub == "google-user-123"
    assert session.google_email == "user@example.com"


# =====================================================================
# Verifies that denying Google authorization returns a controlled OAuth
# error instead of FastAPI validation failure.
# =====================================================================


def test_google_oauth_callback_handles_access_denied(
    monkeypatch,
) -> None:
    monkeypatch.setenv("AHM_ENV", "development")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "dev-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "dev-client-secret")
    monkeypatch.setenv(
        "GOOGLE_REDIRECT_URI",
        "http://localhost:8000/auth/google/callback",
    )
    monkeypatch.setenv("GOOGLE_PICKER_API_KEY", "dev-picker-key")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT_NUMBER", "123456789")
    monkeypatch.setenv("AHM_SESSION_SECRET", "dev-session-secret")

    sessions = SessionStore()
    session_id = sessions.create()

    sessions.set_oauth_state(
        session_id,
        "expected-state",
    )

    monkeypatch.setattr(
        api_app_module,
        "session_store",
        sessions,
    )

    auth_client = TestClient(app)
    auth_client.cookies.set(
        "ahm_session",
        session_id,
    )

    response = auth_client.get(
        "/auth/google/callback",
        params={
            "error": "access_denied",
            "state": "expected-state",
        },
    )

    assert response.status_code == 400
    assert response.json() == {
        "detail": "Google authorization was denied.",
    }


# =====================================================================
# Verifies that a Google OAuth callback without a backend session
# returns a controlled error instead of FastAPI validation failure.
# =====================================================================


def test_google_oauth_callback_handles_missing_session(
    monkeypatch,
) -> None:
    monkeypatch.setenv("AHM_ENV", "development")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "dev-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "dev-client-secret")
    monkeypatch.setenv(
        "GOOGLE_REDIRECT_URI",
        "http://localhost:8000/auth/google/callback",
    )
    monkeypatch.setenv("GOOGLE_PICKER_API_KEY", "dev-picker-key")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT_NUMBER", "123456789")
    monkeypatch.setenv("AHM_SESSION_SECRET", "dev-session-secret")

    auth_client = TestClient(app)

    response = auth_client.get(
        "/auth/google/callback",
        params={
            "code": "authorization-code",
            "state": "expected-state",
        },
    )

    assert response.status_code == 400
    assert response.json() == {
        "detail": "Google OAuth session is missing or has expired.",
    }


# =====================================================================
# Verifies that a Google OAuth callback with an expired backend session
# returns a controlled error instead of an unhandled server failure.
# =====================================================================


def test_google_oauth_callback_handles_expired_session(
    monkeypatch,
) -> None:
    monkeypatch.setenv("AHM_ENV", "development")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "dev-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "dev-client-secret")
    monkeypatch.setenv(
        "GOOGLE_REDIRECT_URI",
        "http://localhost:8000/auth/google/callback",
    )
    monkeypatch.setenv("GOOGLE_PICKER_API_KEY", "dev-picker-key")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT_NUMBER", "123456789")
    monkeypatch.setenv("AHM_SESSION_SECRET", "dev-session-secret")

    current_time = datetime(
        2026,
        9,
        5,
        18,
        0,
        tzinfo=timezone.utc,
    )
    sessions = SessionStore(clock=lambda: current_time)
    session_id = sessions.create()

    sessions.set_oauth_state(
        session_id,
        "expected-state",
    )

    monkeypatch.setattr(
        api_app_module,
        "session_store",
        sessions,
    )

    current_time += timedelta(hours=8)

    auth_client = TestClient(
        app,
        raise_server_exceptions=False,
    )
    auth_client.cookies.set(
        "ahm_session",
        session_id,
    )

    response = auth_client.get(
        "/auth/google/callback",
        params={
            "code": "authorization-code",
            "state": "expected-state",
        },
    )

    assert response.status_code == 400
    assert response.json() == {
        "detail": "Google OAuth session is missing or has expired.",
    }


# =====================================================================
# Verifies that a Google OAuth callback with an invalid state returns
# a controlled error instead of an unhandled server failure.
# =====================================================================


def test_google_oauth_callback_handles_invalid_state(
    monkeypatch,
) -> None:
    monkeypatch.setenv("AHM_ENV", "development")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "dev-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "dev-client-secret")
    monkeypatch.setenv(
        "GOOGLE_REDIRECT_URI",
        "http://localhost:8000/auth/google/callback",
    )
    monkeypatch.setenv("GOOGLE_PICKER_API_KEY", "dev-picker-key")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT_NUMBER", "123456789")
    monkeypatch.setenv("AHM_SESSION_SECRET", "dev-session-secret")

    sessions = SessionStore()
    session_id = sessions.create()

    sessions.set_oauth_state(
        session_id,
        "expected-state",
    )

    monkeypatch.setattr(
        api_app_module,
        "session_store",
        sessions,
    )

    auth_client = TestClient(
        app,
        raise_server_exceptions=False,
    )
    auth_client.cookies.set(
        "ahm_session",
        session_id,
    )

    response = auth_client.get(
        "/auth/google/callback",
        params={
            "code": "authorization-code",
            "state": "different-state",
        },
    )

    assert response.status_code == 400
    assert response.json() == {
        "detail": "Google OAuth callback is invalid.",
    }


# =====================================================================
# Verifies that a consumed Google OAuth state cannot be reused and a
# replayed callback returns a controlled error.
# =====================================================================


def test_google_oauth_callback_rejects_replayed_state(
    monkeypatch,
) -> None:
    monkeypatch.setenv("AHM_ENV", "development")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "dev-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "dev-client-secret")
    monkeypatch.setenv(
        "GOOGLE_REDIRECT_URI",
        "http://localhost:8000/auth/google/callback",
    )
    monkeypatch.setenv("GOOGLE_PICKER_API_KEY", "dev-picker-key")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT_NUMBER", "123456789")
    monkeypatch.setenv("AHM_SESSION_SECRET", "dev-session-secret")

    sessions = SessionStore()
    session_id = sessions.create()

    sessions.set_oauth_state(
        session_id,
        "expected-state",
    )

    monkeypatch.setattr(
        api_app_module,
        "session_store",
        sessions,
    )

    class FakeTokenClient:
        def exchange_code(
            self,
            code: str,
            client_id: str,
            client_secret: str,
            redirect_uri: str,
        ) -> GoogleTokenResponse:
            return GoogleTokenResponse(
                access_token="access-token",
                expires_in_seconds=3600,
                granted_scopes=frozenset(GoogleOAuthService.SCOPES),
            )

    class FakeIdentity:
        sub = "google-user-123"
        email = "user@example.com"

    class FakeIdentityClient:
        def get_identity(
            self,
            access_token: str,
        ) -> FakeIdentity:
            return FakeIdentity()

    monkeypatch.setattr(
        api_app_module,
        "google_token_client",
        FakeTokenClient(),
    )
    monkeypatch.setattr(
        api_app_module,
        "google_identity_client",
        FakeIdentityClient(),
    )

    auth_client = TestClient(app)
    auth_client.cookies.set(
        "ahm_session",
        session_id,
    )

    first_response = auth_client.get(
        "/auth/google/callback",
        params={
            "code": "authorization-code",
            "state": "expected-state",
        },
    )

    replayed_response = auth_client.get(
        "/auth/google/callback",
        params={
            "code": "authorization-code",
            "state": "expected-state",
        },
    )

    assert first_response.status_code == 200
    assert replayed_response.status_code == 400
    assert replayed_response.json() == {
        "detail": "Google OAuth callback is invalid.",
    }


# =====================================================================
# Verifies that a Google token exchange failure returns a controlled
# upstream error instead of an unhandled server failure.
# =====================================================================


def test_google_oauth_callback_handles_token_exchange_failure(
    monkeypatch,
) -> None:
    monkeypatch.setenv("AHM_ENV", "development")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "dev-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "dev-client-secret")
    monkeypatch.setenv(
        "GOOGLE_REDIRECT_URI",
        "http://localhost:8000/auth/google/callback",
    )
    monkeypatch.setenv("GOOGLE_PICKER_API_KEY", "dev-picker-key")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT_NUMBER", "123456789")
    monkeypatch.setenv("AHM_SESSION_SECRET", "dev-session-secret")

    sessions = SessionStore()
    session_id = sessions.create()

    sessions.set_oauth_state(
        session_id,
        "expected-state",
    )

    monkeypatch.setattr(
        api_app_module,
        "session_store",
        sessions,
    )

    class FailingTokenClient:
        def exchange_code(
            self,
            code: str,
            client_id: str,
            client_secret: str,
            redirect_uri: str,
        ) -> GoogleTokenResponse:
            raise GoogleOAuthError(
                "Google token exchange failed",
            )

    monkeypatch.setattr(
        api_app_module,
        "google_token_client",
        FailingTokenClient(),
    )

    auth_client = TestClient(
        app,
        raise_server_exceptions=False,
    )
    auth_client.cookies.set(
        "ahm_session",
        session_id,
    )

    response = auth_client.get(
        "/auth/google/callback",
        params={
            "code": "authorization-code",
            "state": "expected-state",
        },
    )

    assert response.status_code == 502
    assert response.json() == {
        "detail": "Google OAuth connection failed.",
    }


# =====================================================================
# Verifies that a Google identity lookup failure returns a controlled
# upstream error instead of an unhandled server failure.
# =====================================================================


def test_google_oauth_callback_handles_identity_failure(
    monkeypatch,
) -> None:
    monkeypatch.setenv("AHM_ENV", "development")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "dev-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "dev-client-secret")
    monkeypatch.setenv(
        "GOOGLE_REDIRECT_URI",
        "http://localhost:8000/auth/google/callback",
    )
    monkeypatch.setenv("GOOGLE_PICKER_API_KEY", "dev-picker-key")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT_NUMBER", "123456789")
    monkeypatch.setenv("AHM_SESSION_SECRET", "dev-session-secret")

    sessions = SessionStore()
    session_id = sessions.create()

    sessions.set_oauth_state(
        session_id,
        "expected-state",
    )

    monkeypatch.setattr(
        api_app_module,
        "session_store",
        sessions,
    )

    class FakeTokenClient:
        def exchange_code(
            self,
            code: str,
            client_id: str,
            client_secret: str,
            redirect_uri: str,
        ) -> GoogleTokenResponse:
            return GoogleTokenResponse(
                access_token="access-token",
                expires_in_seconds=3600,
                granted_scopes=frozenset(GoogleOAuthService.SCOPES),
            )

    class FailingIdentityClient:
        def get_identity(
            self,
            access_token: str,
        ):
            raise GoogleOAuthError(
                "Google identity request failed",
            )

    monkeypatch.setattr(
        api_app_module,
        "google_token_client",
        FakeTokenClient(),
    )
    monkeypatch.setattr(
        api_app_module,
        "google_identity_client",
        FailingIdentityClient(),
    )

    auth_client = TestClient(
        app,
        raise_server_exceptions=False,
    )
    auth_client.cookies.set(
        "ahm_session",
        session_id,
    )

    response = auth_client.get(
        "/auth/google/callback",
        params={
            "code": "authorization-code",
            "state": "expected-state",
        },
    )

    assert response.status_code == 502
    assert response.json() == {
        "detail": "Google OAuth connection failed.",
    }


# =====================================================================
# Verifies that a Google OAuth callback without an authorization code
# returns a controlled error.
# =====================================================================


def test_google_oauth_callback_handles_missing_code(
    monkeypatch,
) -> None:
    monkeypatch.setenv("AHM_ENV", "development")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "dev-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "dev-client-secret")
    monkeypatch.setenv(
        "GOOGLE_REDIRECT_URI",
        "http://localhost:8000/auth/google/callback",
    )
    monkeypatch.setenv("GOOGLE_PICKER_API_KEY", "dev-picker-key")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT_NUMBER", "123456789")
    monkeypatch.setenv("AHM_SESSION_SECRET", "dev-session-secret")

    sessions = SessionStore()
    session_id = sessions.create()

    sessions.set_oauth_state(
        session_id,
        "expected-state",
    )

    monkeypatch.setattr(
        api_app_module,
        "session_store",
        sessions,
    )

    auth_client = TestClient(
        app,
        raise_server_exceptions=False,
    )
    auth_client.cookies.set(
        "ahm_session",
        session_id,
    )

    response = auth_client.get(
        "/auth/google/callback",
        params={
            "state": "expected-state",
        },
    )

    assert response.status_code == 400
    assert response.json() == {
        "detail": "Google OAuth callback is incomplete.",
    }


# =====================================================================
# Verifies that signing out deletes the backend session and expires the
# local AHM session cookie without requiring Google configuration.
# =====================================================================


def test_sign_out_deletes_backend_session_and_cookie(
    monkeypatch,
) -> None:
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)

    sessions = SessionStore()
    session_id = sessions.create()

    monkeypatch.setattr(
        api_app_module,
        "session_store",
        sessions,
    )

    auth_client = TestClient(app)
    auth_client.cookies.set(
        "ahm_session",
        session_id,
    )

    response = auth_client.post(
        "/auth/sign-out",
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "signed_out",
    }
    assert sessions.get(session_id) is None

    set_cookie = response.headers["set-cookie"]

    assert "ahm_session=" in set_cookie
    assert "Max-Age=0" in set_cookie


# =====================================================================
# Verifies that signing out without an active backend session remains
# successful and still expires the local AHM session cookie.
# =====================================================================


def test_sign_out_is_idempotent() -> None:
    auth_client = TestClient(app)
    auth_client.cookies.set(
        "ahm_session",
        "missing-session-id",
    )

    response = auth_client.post(
        "/auth/sign-out",
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "signed_out",
    }

    set_cookie = response.headers["set-cookie"]

    assert "ahm_session=" in set_cookie
    assert "Max-Age=0" in set_cookie


# =====================================================================
# Verifies that disconnecting Google revokes the current access grant,
# deletes the backend session, and expires the local AHM session cookie.
# =====================================================================


def test_disconnect_google_revokes_access_and_deletes_session(
    monkeypatch,
) -> None:
    sessions = SessionStore()
    session_id = sessions.create()

    sessions.set_google_identity(
        session_id=session_id,
        google_sub="google-user-123",
        google_email="user@example.com",
    )
    sessions.set_google_access_credentials(
        session_id=session_id,
        access_token="access-token",
        granted_scopes=frozenset(GoogleOAuthService.SCOPES),
        expires_in_seconds=3600,
    )

    monkeypatch.setattr(
        api_app_module,
        "session_store",
        sessions,
    )

    class FakeRevocationClient:
        def __init__(self) -> None:
            self.revoked_token: str | None = None

        def revoke(
            self,
            access_token: str,
        ) -> None:
            self.revoked_token = access_token

    revocation_client = FakeRevocationClient()

    monkeypatch.setattr(
        api_app_module,
        "google_revocation_client",
        revocation_client,
        raising=False,
    )

    auth_client = TestClient(app)
    auth_client.cookies.set(
        "ahm_session",
        session_id,
    )

    response = auth_client.post(
        "/auth/google/disconnect",
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "google_disconnected",
    }

    assert revocation_client.revoked_token == "access-token"
    assert sessions.get(session_id) is None

    set_cookie = response.headers["set-cookie"]

    assert "ahm_session=" in set_cookie
    assert "Max-Age=0" in set_cookie


# =====================================================================
# Verifies that a Google revocation failure returns a controlled error
# while still deleting the local session and expiring its cookie.
# =====================================================================


def test_disconnect_google_handles_revocation_failure(
    monkeypatch,
) -> None:
    sessions = SessionStore()
    session_id = sessions.create()

    sessions.set_google_identity(
        session_id=session_id,
        google_sub="google-user-123",
        google_email="user@example.com",
    )
    sessions.set_google_access_credentials(
        session_id=session_id,
        access_token="access-token",
        granted_scopes=frozenset(GoogleOAuthService.SCOPES),
        expires_in_seconds=3600,
    )

    monkeypatch.setattr(
        api_app_module,
        "session_store",
        sessions,
    )

    class FailingRevocationClient:
        def revoke(
            self,
            access_token: str,
        ) -> None:
            raise GoogleOAuthError(
                "Google token revocation failed",
            )

    monkeypatch.setattr(
        api_app_module,
        "google_revocation_client",
        FailingRevocationClient(),
    )

    auth_client = TestClient(
        app,
        raise_server_exceptions=False,
    )
    auth_client.cookies.set(
        "ahm_session",
        session_id,
    )

    response = auth_client.post(
        "/auth/google/disconnect",
    )

    assert response.status_code == 502
    assert response.json() == {
        "detail": "Google disconnect failed.",
    }

    assert sessions.get(session_id) is None

    set_cookie = response.headers["set-cookie"]

    assert "ahm_session=" in set_cookie
    assert "Max-Age=0" in set_cookie


# =====================================================================
# Verifies that disconnecting Google without an active backend session
# returns a controlled error instead of FastAPI validation failure.
# =====================================================================


def test_disconnect_google_handles_missing_session() -> None:
    auth_client = TestClient(app)

    response = auth_client.post(
        "/auth/google/disconnect",
    )

    assert response.status_code == 400
    assert response.json() == {
        "detail": "Google connection is not available.",
    }


# =====================================================================
# Verifies that disconnecting Google with a stale session cookie
# returns a controlled error.
# =====================================================================


def test_disconnect_google_handles_stale_session_cookie(
    monkeypatch,
) -> None:
    sessions = SessionStore()

    monkeypatch.setattr(
        api_app_module,
        "session_store",
        sessions,
    )

    auth_client = TestClient(app)
    auth_client.cookies.set(
        "ahm_session",
        "missing-session-id",
    )

    response = auth_client.post(
        "/auth/google/disconnect",
    )

    assert response.status_code == 400
    assert response.json() == {
        "detail": "Google connection is not available.",
    }


# =====================================================================
# Verifies that disconnecting Google without stored Google credentials
# returns a controlled error and does not attempt token revocation.
# =====================================================================


def test_disconnect_google_without_credentials_does_not_revoke(
    monkeypatch,
) -> None:
    sessions = SessionStore()
    session_id = sessions.create()

    monkeypatch.setattr(
        api_app_module,
        "session_store",
        sessions,
    )

    class FailingIfCalledRevocationClient:
        def revoke(
            self,
            access_token: str,
        ) -> None:
            raise AssertionError("Revocation should not be called")

    monkeypatch.setattr(
        api_app_module,
        "google_revocation_client",
        FailingIfCalledRevocationClient(),
    )

    auth_client = TestClient(app)
    auth_client.cookies.set(
        "ahm_session",
        session_id,
    )

    response = auth_client.post(
        "/auth/google/disconnect",
    )

    assert response.status_code == 400
    assert response.json() == {
        "detail": "Google connection is not available.",
    }

    assert sessions.get(session_id) is not None


# =====================================================================
# Verifies that signing out of an active Google-backed session deletes
# only the local AHM session and does not revoke the Google OAuth grant.
# =====================================================================


def test_sign_out_does_not_revoke_google_access(
    monkeypatch,
) -> None:
    sessions = SessionStore()
    session_id = sessions.create()

    sessions.set_google_identity(
        session_id=session_id,
        google_sub="google-user-123",
        google_email="user@example.com",
    )
    sessions.set_google_access_credentials(
        session_id=session_id,
        access_token="access-token",
        granted_scopes=frozenset(GoogleOAuthService.SCOPES),
        expires_in_seconds=3600,
    )

    monkeypatch.setattr(
        api_app_module,
        "session_store",
        sessions,
    )

    class FailingIfCalledRevocationClient:
        def revoke(
            self,
            access_token: str,
        ) -> None:
            raise AssertionError("Sign out must not revoke Google access")

    monkeypatch.setattr(
        api_app_module,
        "google_revocation_client",
        FailingIfCalledRevocationClient(),
    )

    auth_client = TestClient(app)
    auth_client.cookies.set(
        "ahm_session",
        session_id,
    )

    response = auth_client.post(
        "/auth/sign-out",
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "signed_out",
    }
    assert sessions.get(session_id) is None


# =====================================================================
# Verifies that Google connection status reports an active and ready
# Google-backed session together with its display email address.
# =====================================================================


def test_google_status_reports_connected_session(
    monkeypatch,
) -> None:
    sessions = SessionStore()
    session_id = sessions.create()

    sessions.set_google_identity(
        session_id=session_id,
        google_sub="google-user-123",
        google_email="user@example.com",
    )
    sessions.set_google_access_credentials(
        session_id=session_id,
        access_token="access-token",
        granted_scopes=frozenset(GoogleOAuthService.SCOPES),
        expires_in_seconds=3600,
    )

    monkeypatch.setattr(
        api_app_module,
        "session_store",
        sessions,
    )

    auth_client = TestClient(app)
    auth_client.cookies.set(
        "ahm_session",
        session_id,
    )

    response = auth_client.get(
        "/auth/google/status",
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "connected",
        "email": "user@example.com",
    }


# =====================================================================
# Verifies that Google connection status reports disconnected when no
# active AHM session cookie is available.
# =====================================================================


def test_google_status_reports_disconnected_without_session() -> None:
    auth_client = TestClient(app)

    response = auth_client.get(
        "/auth/google/status",
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "disconnected",
    }


# =====================================================================
# Verifies that Google connection status requires reconnection when the
# stored Google access token has expired while identity remains known.
# =====================================================================


def test_google_status_reports_reconnect_required_for_expired_token(
    monkeypatch,
) -> None:
    current_time = datetime(
        2026,
        1,
        1,
        tzinfo=timezone.utc,
    )

    sessions = SessionStore(
        clock=lambda: current_time,
    )
    session_id = sessions.create()

    sessions.set_google_identity(
        session_id=session_id,
        google_sub="google-user-123",
        google_email="user@example.com",
    )
    sessions.set_google_access_credentials(
        session_id=session_id,
        access_token="access-token",
        granted_scopes=frozenset(GoogleOAuthService.SCOPES),
        expires_in_seconds=60,
    )

    current_time += timedelta(
        seconds=60,
    )

    monkeypatch.setattr(
        api_app_module,
        "session_store",
        sessions,
    )

    auth_client = TestClient(app)
    auth_client.cookies.set(
        "ahm_session",
        session_id,
    )

    response = auth_client.get(
        "/auth/google/status",
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "reconnect_required",
        "email": "user@example.com",
    }


# =====================================================================
# Verifies that Google connection status requires reconnection when the
# stored access token is missing one of the required OAuth scopes.
# =====================================================================


def test_google_status_reports_reconnect_required_for_missing_scope(
    monkeypatch,
) -> None:
    sessions = SessionStore()
    session_id = sessions.create()

    sessions.set_google_identity(
        session_id=session_id,
        google_sub="google-user-123",
        google_email="user@example.com",
    )
    sessions.set_google_access_credentials(
        session_id=session_id,
        access_token="access-token",
        granted_scopes=frozenset(
            {
                "openid",
                "email",
            }
        ),
        expires_in_seconds=3600,
    )

    monkeypatch.setattr(
        api_app_module,
        "session_store",
        sessions,
    )

    auth_client = TestClient(app)
    auth_client.cookies.set(
        "ahm_session",
        session_id,
    )

    response = auth_client.get(
        "/auth/google/status",
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "reconnect_required",
        "email": "user@example.com",
    }


# =====================================================================
# Verifies that reconnecting Google reuses the existing AHM session
# instead of replacing it with a newly created backend session.
# =====================================================================


def test_google_oauth_start_reuses_existing_session_for_reconnect(
    monkeypatch,
) -> None:
    monkeypatch.setenv("AHM_ENV", "development")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "dev-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "dev-client-secret")
    monkeypatch.setenv(
        "GOOGLE_REDIRECT_URI",
        "http://localhost:8000/auth/google/callback",
    )
    monkeypatch.setenv("GOOGLE_PICKER_API_KEY", "dev-picker-key")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT_NUMBER", "123456789")
    monkeypatch.setenv("AHM_SESSION_SECRET", "dev-session-secret")

    sessions = SessionStore()
    session_id = sessions.create()

    sessions.set_google_identity(
        session_id=session_id,
        google_sub="google-user-123",
        google_email="user@example.com",
    )

    monkeypatch.setattr(
        api_app_module,
        "session_store",
        sessions,
    )

    auth_client = TestClient(app)
    auth_client.cookies.set(
        "ahm_session",
        session_id,
    )

    response = auth_client.get(
        "/auth/google/start",
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.cookies["ahm_session"] == session_id

    session = sessions.get(session_id)

    assert session is not None
    assert session.oauth_state is not None

    authorization_url = urlparse(
        response.headers["location"],
    )
    query = parse_qs(
        authorization_url.query,
    )

    assert query["state"] == [
        session.oauth_state,
    ]


# =====================================================================
# Verifies that starting Google OAuth with a stale AHM session cookie
# creates a new backend session instead of reusing the invalid session.
# =====================================================================


def test_google_oauth_start_replaces_stale_session_cookie(
    monkeypatch,
) -> None:
    monkeypatch.setenv("AHM_ENV", "development")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "dev-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "dev-client-secret")
    monkeypatch.setenv(
        "GOOGLE_REDIRECT_URI",
        "http://localhost:8000/auth/google/callback",
    )
    monkeypatch.setenv("GOOGLE_PICKER_API_KEY", "dev-picker-key")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT_NUMBER", "123456789")
    monkeypatch.setenv("AHM_SESSION_SECRET", "dev-session-secret")

    sessions = SessionStore()

    monkeypatch.setattr(
        api_app_module,
        "session_store",
        sessions,
    )

    auth_client = TestClient(app)
    auth_client.cookies.set(
        "ahm_session",
        "stale-session-id",
    )

    response = auth_client.get(
        "/auth/google/start",
        follow_redirects=False,
    )

    assert response.status_code == 302

    new_session_id = response.cookies["ahm_session"]

    assert new_session_id != "stale-session-id"

    session = sessions.get(new_session_id)

    assert session is not None
    assert session.oauth_state is not None


# =====================================================================
# Verifies that completing Google OAuth during reconnection replaces
# the old Google credentials while preserving the existing AHM session.
# =====================================================================


def test_google_oauth_callback_refreshes_existing_session_credentials(
    monkeypatch,
) -> None:
    monkeypatch.setenv("AHM_ENV", "development")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "dev-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "dev-client-secret")
    monkeypatch.setenv(
        "GOOGLE_REDIRECT_URI",
        "http://localhost:8000/auth/google/callback",
    )
    monkeypatch.setenv("GOOGLE_PICKER_API_KEY", "dev-picker-key")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT_NUMBER", "123456789")
    monkeypatch.setenv("AHM_SESSION_SECRET", "dev-session-secret")

    sessions = SessionStore()
    session_id = sessions.create()

    sessions.set_google_identity(
        session_id=session_id,
        google_sub="google-user-123",
        google_email="user@example.com",
    )
    sessions.set_google_access_credentials(
        session_id=session_id,
        access_token="old-access-token",
        granted_scopes=frozenset(GoogleOAuthService.SCOPES),
        expires_in_seconds=60,
    )
    sessions.set_oauth_state(
        session_id,
        "expected-state",
    )

    monkeypatch.setattr(
        api_app_module,
        "session_store",
        sessions,
    )

    class FakeTokenClient:
        def exchange_code(
            self,
            code: str,
            client_id: str,
            client_secret: str,
            redirect_uri: str,
        ) -> GoogleTokenResponse:
            return GoogleTokenResponse(
                access_token="new-access-token",
                expires_in_seconds=3600,
                granted_scopes=frozenset(
                    GoogleOAuthService.SCOPES,
                ),
            )

    class FakeIdentity:
        sub = "google-user-123"
        email = "user@example.com"

    class FakeIdentityClient:
        def get_identity(
            self,
            access_token: str,
        ) -> FakeIdentity:
            assert access_token == "new-access-token"
            return FakeIdentity()

    monkeypatch.setattr(
        api_app_module,
        "google_token_client",
        FakeTokenClient(),
    )
    monkeypatch.setattr(
        api_app_module,
        "google_identity_client",
        FakeIdentityClient(),
    )

    auth_client = TestClient(app)
    auth_client.cookies.set(
        "ahm_session",
        session_id,
    )

    response = auth_client.get(
        "/auth/google/callback",
        params={
            "code": "authorization-code",
            "state": "expected-state",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/"

    session = sessions.get(session_id)

    assert session is not None
    assert session.oauth_state is None
    assert session.google_access_token == "new-access-token"
    assert session.google_sub == "google-user-123"
    assert session.google_email == "user@example.com"
    assert session.google_granted_scopes == frozenset(
        GoogleOAuthService.SCOPES,
    )


# =====================================================================
# Verifies that reconnecting Google reuses the existing AHM session
# without extending its absolute expiration time.
# =====================================================================


def test_google_oauth_reconnect_preserves_session_expiry(
    monkeypatch,
) -> None:
    monkeypatch.setenv("AHM_ENV", "development")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "dev-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "dev-client-secret")
    monkeypatch.setenv(
        "GOOGLE_REDIRECT_URI",
        "http://localhost:8000/auth/google/callback",
    )
    monkeypatch.setenv("GOOGLE_PICKER_API_KEY", "dev-picker-key")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT_NUMBER", "123456789")
    monkeypatch.setenv("AHM_SESSION_SECRET", "dev-session-secret")

    current_time = datetime(
        2026,
        1,
        1,
        tzinfo=timezone.utc,
    )

    sessions = SessionStore(
        clock=lambda: current_time,
    )
    session_id = sessions.create()

    original_session = sessions.get(session_id)

    assert original_session is not None

    original_expires_at = original_session.expires_at

    current_time += timedelta(hours=1)

    monkeypatch.setattr(
        api_app_module,
        "session_store",
        sessions,
    )

    auth_client = TestClient(app)
    auth_client.cookies.set(
        "ahm_session",
        session_id,
    )

    response = auth_client.get(
        "/auth/google/start",
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.cookies["ahm_session"] == session_id

    session = sessions.get(session_id)

    assert session is not None
    assert session.expires_at == original_expires_at


# =====================================================================
# Verifies that the configuration profile API exposes saved profiles,
# the current selection, and the session autosave preference.
# =====================================================================


def test_config_profiles_endpoint_exposes_session_state(
    monkeypatch,
) -> None:
    sessions = SessionStore()
    session_id = sessions.create()

    sessions.set_google_access_credentials(
        session_id=session_id,
        access_token="access-token",
        granted_scopes=frozenset(),
        expires_in_seconds=3600,
    )
    sessions.set_selected_config_profile(
        session_id=session_id,
        profile_id="config-2",
    )
    sessions.set_config_autosave_enabled(
        session_id=session_id,
        enabled=False,
    )

    monkeypatch.setattr(
        api_app_module,
        "session_store",
        sessions,
    )

    profiles = (
        ConfigProfile(
            file_id="config-1",
            name="Cutting",
        ),
        ConfigProfile(
            file_id="config-2",
            name="Maintenance",
        ),
    )

    monkeypatch.setattr(
        api_app_module,
        "discover_config_profiles_for_session",
        lambda session: profiles,
        raising=False,
    )

    auth_client = TestClient(app)
    auth_client.cookies.set(
        "ahm_session",
        session_id,
    )

    response = auth_client.get("/config/profiles")

    assert response.status_code == 200
    assert response.json() == {
        "profiles": [
            {
                "file_id": "config-1",
                "name": "Cutting",
            },
            {
                "file_id": "config-2",
                "name": "Maintenance",
            },
        ],
        "selected_profile_id": "config-2",
        "autosave_enabled": False,
    }


# =====================================================================
# Verifies that the configuration profile API selects an existing Drive
# profile for the current session.
# =====================================================================


def test_config_profile_can_be_selected(
    monkeypatch,
) -> None:
    sessions = SessionStore()
    session_id = sessions.create()

    sessions.set_google_access_credentials(
        session_id=session_id,
        access_token="access-token",
        granted_scopes=frozenset(),
        expires_in_seconds=3600,
    )

    monkeypatch.setattr(
        api_app_module,
        "session_store",
        sessions,
    )

    profiles = (
        ConfigProfile(
            file_id="config-1",
            name="Cutting",
        ),
        ConfigProfile(
            file_id="config-2",
            name="Maintenance",
        ),
    )

    monkeypatch.setattr(
        api_app_module,
        "discover_config_profiles_for_session",
        lambda session: profiles,
    )

    auth_client = TestClient(app)
    auth_client.cookies.set(
        "ahm_session",
        session_id,
    )

    response = auth_client.post(
        "/config/profiles/select",
        data={
            "profile_id": "config-2",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "selected_profile_id": "config-2",
    }

    session = sessions.get(session_id)

    assert session is not None
    assert session.selected_config_profile_id == "config-2"


# =====================================================================
# Verifies that the configuration profile API can explicitly clear the
# current Drive profile selection without deleting any saved profile.
# =====================================================================


def test_config_profile_selection_can_be_cleared(
    monkeypatch,
) -> None:
    sessions = SessionStore()
    session_id = sessions.create()

    sessions.set_google_access_credentials(
        session_id=session_id,
        access_token="access-token",
        granted_scopes=frozenset(),
        expires_in_seconds=3600,
    )
    sessions.set_selected_config_profile(
        session_id=session_id,
        profile_id="config-2",
    )

    monkeypatch.setattr(
        api_app_module,
        "session_store",
        sessions,
    )

    auth_client = TestClient(app)
    auth_client.cookies.set(
        "ahm_session",
        session_id,
    )

    response = auth_client.post(
        "/config/profiles/select-none",
    )

    assert response.status_code == 200
    assert response.json() == {
        "selected_profile_id": None,
    }

    session = sessions.get(session_id)

    assert session is not None
    assert session.selected_config_profile_id is None


# =====================================================================
# Verifies that the configuration autosave preference can be updated
# through the API for the current session.
# =====================================================================


def test_config_autosave_preference_can_be_updated(
    monkeypatch,
) -> None:
    sessions = SessionStore()
    session_id = sessions.create()

    sessions.set_google_access_credentials(
        session_id=session_id,
        access_token="access-token",
        granted_scopes=frozenset(),
        expires_in_seconds=3600,
    )

    monkeypatch.setattr(
        api_app_module,
        "session_store",
        sessions,
    )

    auth_client = TestClient(app)
    auth_client.cookies.set(
        "ahm_session",
        session_id,
    )

    response = auth_client.post(
        "/config/autosave",
        data={
            "enabled": "false",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "autosave_enabled": False,
    }

    session = sessions.get(session_id)

    assert session is not None
    assert session.config_autosave_enabled is False


# =====================================================================
# Verifies that report generation forwards the selected Drive
# configuration into the application run options.
# =====================================================================


def test_report_generation_uses_selected_drive_config(
    monkeypatch,
) -> None:
    sessions = SessionStore()
    session_id = sessions.create()

    sessions.set_google_access_credentials(
        session_id=session_id,
        access_token="access-token",
        granted_scopes=frozenset(),
        expires_in_seconds=3600,
    )

    sessions.set_config_autosave_enabled(
        session_id=session_id,
        enabled=False,
    )

    sessions.set_selected_config_profile(
        session_id=session_id,
        profile_id="config-1",
    )

    monkeypatch.setattr(
        api_app_module,
        "session_store",
        sessions,
    )

    selected_config = AppConfig()

    monkeypatch.setattr(
        api_app_module,
        "load_selected_config_for_session",
        lambda session: selected_config,
        raising=False,
    )

    captured_options = None

    class FakeApplication:
        def generate_reports(
            self,
            options,
        ):
            nonlocal captured_options
            captured_options = options
            return _generation_result()

    monkeypatch.setattr(
        api_app_module,
        "AppleHealthApplication",
        FakeApplication,
    )

    auth_client = TestClient(app)
    auth_client.cookies.set(
        "ahm_session",
        session_id,
    )

    response = auth_client.post(
        "/reports/generate",
        files={
            "archive": (
                "export.zip",
                b"fake-archive",
                "application/zip",
            ),
        },
        data={
            "periods": "2026-08",
        },
    )

    assert response.status_code == 200
    assert captured_options is not None
    assert captured_options.selected_drive_config == selected_config


# =====================================================================
# Verifies that an uploaded configuration replaces the selected Drive
# profile as the base configuration source for the current request.
# =====================================================================


def test_uploaded_config_replaces_selected_drive_config(
    monkeypatch,
) -> None:
    sessions = SessionStore()
    session_id = sessions.create()

    sessions.set_google_access_credentials(
        session_id=session_id,
        access_token="access-token",
        granted_scopes=frozenset(),
        expires_in_seconds=3600,
    )

    sessions.set_config_autosave_enabled(
        session_id=session_id,
        enabled=False,
    )

    sessions.set_selected_config_profile(
        session_id=session_id,
        profile_id="config-1",
    )

    monkeypatch.setattr(
        api_app_module,
        "session_store",
        sessions,
    )

    def fail_if_selected_drive_config_is_loaded(session):
        raise AssertionError("Selected Drive config must not be loaded when a config is uploaded")

    monkeypatch.setattr(
        api_app_module,
        "load_selected_config_for_session",
        fail_if_selected_drive_config_is_loaded,
    )

    captured_options = None

    class FakeApplication:
        def generate_reports(
            self,
            options,
        ):
            nonlocal captured_options
            captured_options = options
            return _generation_result()

    monkeypatch.setattr(
        api_app_module,
        "AppleHealthApplication",
        FakeApplication,
    )

    auth_client = TestClient(app)
    auth_client.cookies.set(
        "ahm_session",
        session_id,
    )

    response = auth_client.post(
        "/reports/generate",
        files={
            "archive": (
                "export.zip",
                b"fake-archive",
                "application/zip",
            ),
            "config": (
                "config.toml",
                b'[source]\napple_watch_source = "Uploaded Watch"\n',
                "application/toml",
            ),
        },
        data={
            "periods": "2026-08",
        },
    )

    assert response.status_code == 200
    assert captured_options is not None
    assert captured_options.config_path is not None
    assert captured_options.selected_drive_config is None


# =====================================================================
# Verifies that the selected Drive configuration is discovered and
# loaded through the authenticated user's Drive session.
# =====================================================================


def test_load_selected_config_for_session_loads_selected_profile(
    monkeypatch,
) -> None:
    sessions = SessionStore()
    session_id = sessions.create()

    sessions.set_google_access_credentials(
        session_id=session_id,
        access_token="access-token",
        granted_scopes=frozenset(),
        expires_in_seconds=3600,
    )
    sessions.set_selected_config_profile(
        session_id=session_id,
        profile_id="config-2",
    )

    session = sessions.get(session_id)

    assert session is not None

    calls = {}

    class FakeDriveClient:
        def __init__(
            self,
            access_token,
        ):
            calls["access_token"] = access_token

    monkeypatch.setattr(
        api_app_module,
        "HttpGoogleDriveClient",
        FakeDriveClient,
        raising=False,
    )

    class FakeRoot:
        file_id = "root-id"

    class FakeConfigContainer:
        file_id = "config-container-id"

    monkeypatch.setattr(
        api_app_module,
        "discover_ahm_root",
        lambda client: FakeRoot(),
        raising=False,
    )

    def fake_discover_config_container(
        client,
        *,
        root_id,
    ):
        assert root_id == "root-id"
        return FakeConfigContainer()

    monkeypatch.setattr(
        api_app_module,
        "discover_config_container",
        fake_discover_config_container,
        raising=False,
    )

    profiles = (
        ConfigProfile(
            file_id="config-1",
            name="Cutting",
        ),
        ConfigProfile(
            file_id="config-2",
            name="Maintenance",
        ),
    )

    def fake_discover_drive_config_profiles(
        client,
    ):
        return profiles

    monkeypatch.setattr(
        api_app_module,
        "discover_drive_config_profiles",
        fake_discover_drive_config_profiles,
        raising=False,
    )

    expected_config = AppConfig()

    def fake_load_config_profile(
        client,
        profile,
    ):
        assert profile == profiles[1]
        return expected_config

    monkeypatch.setattr(
        api_app_module,
        "load_config_profile",
        fake_load_config_profile,
        raising=False,
    )

    result = api_app_module.load_selected_config_for_session(
        session,
    )

    assert calls["access_token"] == "access-token"
    assert result == expected_config


# =====================================================================
# Verifies that a missing explicitly selected Drive configuration does
# not silently fall back to application defaults.
# =====================================================================


def test_load_selected_config_for_session_rejects_missing_selected_profile(
    monkeypatch,
) -> None:
    sessions = SessionStore()
    session_id = sessions.create()

    sessions.set_google_access_credentials(
        session_id=session_id,
        access_token="access-token",
        granted_scopes=frozenset(),
        expires_in_seconds=3600,
    )
    sessions.set_selected_config_profile(
        session_id=session_id,
        profile_id="missing-config",
    )

    session = sessions.get(session_id)

    assert session is not None

    class FakeDriveClient:
        def __init__(
            self,
            access_token,
        ):
            assert access_token == "access-token"

    monkeypatch.setattr(
        api_app_module,
        "HttpGoogleDriveClient",
        FakeDriveClient,
    )

    class FakeRoot:
        file_id = "root-id"

    class FakeConfigContainer:
        file_id = "config-container-id"

    monkeypatch.setattr(
        api_app_module,
        "discover_drive_config_profiles",
        lambda client: (
            ConfigProfile(
                file_id="config-1",
                name="Cutting",
            ),
        ),
    )

    with pytest.raises(
        ConfigurationError,
        match="Selected configuration profile is unavailable",
    ):
        api_app_module.load_selected_config_for_session(
            session,
        )


# =====================================================================
# Verifies that an explicitly selected Drive configuration does not
# silently fall back when no Drive configuration profiles are available.
# =====================================================================


def test_load_selected_config_for_session_rejects_missing_drive_profiles(
    monkeypatch,
) -> None:
    sessions = SessionStore()
    session_id = sessions.create()

    sessions.set_google_access_credentials(
        session_id=session_id,
        access_token="access-token",
        granted_scopes=frozenset(),
        expires_in_seconds=3600,
    )
    sessions.set_selected_config_profile(
        session_id=session_id,
        profile_id="config-1",
    )

    session = sessions.get(session_id)

    assert session is not None

    class FakeDriveClient:
        def __init__(
            self,
            access_token,
        ):
            assert access_token == "access-token"

    monkeypatch.setattr(
        api_app_module,
        "HttpGoogleDriveClient",
        FakeDriveClient,
    )

    monkeypatch.setattr(
        api_app_module,
        "discover_drive_config_profiles",
        lambda client: (),
    )

    with pytest.raises(
        ConfigurationError,
        match="Selected configuration profile is unavailable",
    ):
        api_app_module.load_selected_config_for_session(
            session,
        )


# =====================================================================
# Verifies that configuration profile discovery uses the authenticated
# user's Drive and returns profiles from the existing config container.
# =====================================================================


def test_discover_config_profiles_for_session_reads_drive_profiles(
    monkeypatch,
) -> None:
    sessions = SessionStore()
    session_id = sessions.create()

    sessions.set_google_access_credentials(
        session_id=session_id,
        access_token="access-token",
        granted_scopes=frozenset(),
        expires_in_seconds=3600,
    )

    session = sessions.get(session_id)

    assert session is not None

    calls = {}

    class FakeDriveClient:
        def __init__(
            self,
            access_token,
        ):
            calls["access_token"] = access_token

    monkeypatch.setattr(
        api_app_module,
        "HttpGoogleDriveClient",
        FakeDriveClient,
    )

    class FakeRoot:
        file_id = "root-id"

    class FakeConfigContainer:
        file_id = "config-container-id"

    def fake_discover_config_container(
        client,
        *,
        root_id,
    ):
        assert root_id == "root-id"
        return FakeConfigContainer()

    expected_profiles = (
        ConfigProfile(
            file_id="config-1",
            name="Cutting",
        ),
        ConfigProfile(
            file_id="config-2",
            name="Maintenance",
        ),
    )

    def fake_discover_drive_config_profiles(
        client,
    ):
        return expected_profiles

    monkeypatch.setattr(
        api_app_module,
        "discover_drive_config_profiles",
        fake_discover_drive_config_profiles,
    )

    result = api_app_module.discover_config_profiles_for_session(
        session,
    )

    assert calls["access_token"] == "access-token"
    assert result == expected_profiles


# =====================================================================
# Verifies that saving a named configuration profile lazily ensures the
# AHM Drive structure and delegates canonical persistence.
# =====================================================================


def test_save_config_profile_for_session_uses_lazy_drive_write_path(
    monkeypatch,
) -> None:
    sessions = SessionStore()
    session_id = sessions.create()

    sessions.set_google_access_credentials(
        session_id=session_id,
        access_token="access-token",
        granted_scopes=frozenset(),
        expires_in_seconds=3600,
    )

    session = sessions.get(session_id)

    assert session is not None

    calls = {}

    class FakeDriveClient:
        def __init__(
            self,
            access_token,
        ):
            calls["access_token"] = access_token

    monkeypatch.setattr(
        api_app_module,
        "HttpGoogleDriveClient",
        FakeDriveClient,
    )

    class FakeRoot:
        file_id = "root-id"

    class FakeConfigContainer:
        file_id = "config-container-id"

    def fake_ensure_ahm_root(
        client,
    ):
        calls["root"] = True
        return FakeRoot()

    monkeypatch.setattr(
        api_app_module,
        "ensure_ahm_root",
        fake_ensure_ahm_root,
    )

    def fake_ensure_config_container(
        client,
        *,
        root_id,
    ):
        assert root_id == "root-id"
        calls["config_container"] = True
        return FakeConfigContainer()

    monkeypatch.setattr(
        api_app_module,
        "ensure_config_container",
        fake_ensure_config_container,
    )

    existing_profiles = (
        ConfigProfile(
            file_id="config-1",
            name="Cutting",
        ),
    )

    def fake_discover_drive_config_profiles(
        client,
    ):
        return existing_profiles

    monkeypatch.setattr(
        api_app_module,
        "discover_drive_config_profiles",
        fake_discover_drive_config_profiles,
    )

    config = AppConfig()

    def fake_save_config_profile(
        client,
        *,
        config_container_id,
        name,
        config,
        existing_profiles,
    ):
        calls["save"] = {
            "config_container_id": config_container_id,
            "name": name,
            "config": config,
            "existing_profiles": existing_profiles,
        }

    monkeypatch.setattr(
        api_app_module,
        "save_config_profile",
        fake_save_config_profile,
    )

    api_app_module.save_config_profile_for_session(
        session,
        name="Maintenance",
        config=config,
    )

    assert calls["access_token"] == "access-token"
    assert calls["root"] is True
    assert calls["config_container"] is True
    assert calls["save"] == {
        "config_container_id": "config-container-id",
        "name": "Maintenance",
        "config": config,
        "existing_profiles": existing_profiles,
    }


# =====================================================================
# Verifies that the report API serializes reports from the application
# generation result instead of treating the result itself as a list.
# =====================================================================


def test_report_generation_serializes_generation_result(
    monkeypatch,
) -> None:
    class FakeGenerationResult:
        reports = ()
        effective_config = AppConfig()

    class FakeApplication:
        def generate_reports(
            self,
            options,
        ):
            return FakeGenerationResult()

    monkeypatch.setattr(
        api_app_module,
        "AppleHealthApplication",
        FakeApplication,
    )

    auth_client = TestClient(app)

    response = auth_client.post(
        "/reports/generate",
        files={
            "archive": (
                "export.zip",
                b"fake-archive",
                "application/zip",
            ),
        },
        data={
            "periods": "2026-08",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "reports": [],
    }


# =====================================================================
# Verifies that an explicit Save configuration as request persists the
# effective configuration even when automatic config saving is disabled.
# =====================================================================


def test_report_generation_can_explicitly_save_effective_config(
    monkeypatch,
) -> None:
    sessions = SessionStore()
    session_id = sessions.create()

    sessions.set_google_access_credentials(
        session_id=session_id,
        access_token="access-token",
        granted_scopes=frozenset(),
        expires_in_seconds=3600,
    )
    sessions.set_config_autosave_enabled(
        session_id=session_id,
        enabled=False,
    )

    monkeypatch.setattr(
        api_app_module,
        "session_store",
        sessions,
    )

    effective_config = AppConfig()

    class FakeGenerationResult:
        def __init__(
            self,
            effective_config,
        ):
            self.reports = ()
            self.effective_config = effective_config

    class FakeApplication:
        def generate_reports(
            self,
            options,
        ):
            return FakeGenerationResult(
                effective_config,
            )

    monkeypatch.setattr(
        api_app_module,
        "AppleHealthApplication",
        FakeApplication,
    )

    saved_configs = []

    def fake_save_config_profile_for_session(
        session,
        *,
        name,
        config,
    ):
        saved_configs.append(
            (
                session.session_id,
                name,
                config,
            )
        )

    monkeypatch.setattr(
        api_app_module,
        "save_config_profile_for_session",
        fake_save_config_profile_for_session,
    )

    auth_client = TestClient(app)
    auth_client.cookies.set(
        "ahm_session",
        session_id,
    )

    response = auth_client.post(
        "/reports/generate",
        files={
            "archive": (
                "export.zip",
                b"fake-archive",
                "application/zip",
            ),
        },
        data={
            "periods": "2026-08",
            "save_config_as": "Maintenance",
        },
    )

    assert response.status_code == 200
    assert saved_configs == [
        (
            session_id,
            "Maintenance",
            effective_config,
        )
    ]


# =====================================================================
# Verifies that successful report generation automatically persists the
# effective configuration when config autosave is enabled.
# =====================================================================


def test_report_generation_autosaves_effective_config(
    monkeypatch,
) -> None:
    sessions = SessionStore()
    session_id = sessions.create()

    sessions.set_google_access_credentials(
        session_id=session_id,
        access_token="access-token",
        granted_scopes=frozenset(),
        expires_in_seconds=3600,
    )

    monkeypatch.setattr(
        api_app_module,
        "session_store",
        sessions,
    )

    effective_config = AppConfig()

    class FakeGenerationResult:
        def __init__(
            self,
            effective_config,
        ):
            self.reports = ()
            self.effective_config = effective_config

    class FakeApplication:
        def generate_reports(
            self,
            options,
        ):
            return FakeGenerationResult(
                effective_config,
            )

    monkeypatch.setattr(
        api_app_module,
        "AppleHealthApplication",
        FakeApplication,
    )

    saved_configs = []

    def fake_save_config_profile_for_session(
        session,
        *,
        name,
        config,
    ):
        saved_configs.append(
            (
                session.session_id,
                name,
                config,
            )
        )

    monkeypatch.setattr(
        api_app_module,
        "save_config_profile_for_session",
        fake_save_config_profile_for_session,
    )

    auth_client = TestClient(app)
    auth_client.cookies.set(
        "ahm_session",
        session_id,
    )

    response = auth_client.post(
        "/reports/generate",
        files={
            "archive": (
                "export.zip",
                b"fake-archive",
                "application/zip",
            ),
        },
        data={
            "periods": "2026-08",
        },
    )

    assert response.status_code == 200
    assert len(saved_configs) == 1
    assert saved_configs[0][0] == session_id
    assert saved_configs[0][2] == effective_config


# =====================================================================
# Verifies that successful report generation does not persist the
# effective configuration when config autosave is disabled.
# =====================================================================


def test_report_generation_does_not_autosave_when_disabled(
    monkeypatch,
) -> None:
    sessions = SessionStore()
    session_id = sessions.create()

    sessions.set_google_access_credentials(
        session_id=session_id,
        access_token="access-token",
        granted_scopes=frozenset(),
        expires_in_seconds=3600,
    )
    sessions.set_config_autosave_enabled(
        session_id=session_id,
        enabled=False,
    )

    monkeypatch.setattr(
        api_app_module,
        "session_store",
        sessions,
    )

    effective_config = AppConfig()

    class FakeGenerationResult:
        def __init__(
            self,
            effective_config,
        ):
            self.reports = ()
            self.effective_config = effective_config

    class FakeApplication:
        def generate_reports(
            self,
            options,
        ):
            return FakeGenerationResult(
                effective_config,
            )

    monkeypatch.setattr(
        api_app_module,
        "AppleHealthApplication",
        FakeApplication,
    )

    def fail_if_saved(
        session,
        *,
        name,
        config,
    ):
        raise AssertionError("Configuration must not be autosaved when autosave is disabled")

    monkeypatch.setattr(
        api_app_module,
        "save_config_profile_for_session",
        fail_if_saved,
    )

    auth_client = TestClient(app)
    auth_client.cookies.set(
        "ahm_session",
        session_id,
    )

    response = auth_client.post(
        "/reports/generate",
        files={
            "archive": (
                "export.zip",
                b"fake-archive",
                "application/zip",
            ),
        },
        data={
            "periods": "2026-08",
        },
    )

    assert response.status_code == 200


# =====================================================================
# Verifies that an explicit configuration save takes precedence over
# autosave and does not cause two profile saves in one request.
# =====================================================================


def test_explicit_config_save_takes_precedence_over_autosave(
    monkeypatch,
) -> None:
    sessions = SessionStore()
    session_id = sessions.create()

    sessions.set_google_access_credentials(
        session_id=session_id,
        access_token="access-token",
        granted_scopes=frozenset(),
        expires_in_seconds=3600,
    )

    monkeypatch.setattr(
        api_app_module,
        "session_store",
        sessions,
    )

    effective_config = AppConfig()

    class FakeGenerationResult:
        def __init__(
            self,
            effective_config,
        ):
            self.reports = ()
            self.effective_config = effective_config

    class FakeApplication:
        def generate_reports(
            self,
            options,
        ):
            return FakeGenerationResult(
                effective_config,
            )

    monkeypatch.setattr(
        api_app_module,
        "AppleHealthApplication",
        FakeApplication,
    )

    saved_configs = []

    def fake_save_config_profile_for_session(
        session,
        *,
        name,
        config,
    ):
        saved_configs.append(
            (
                name,
                config,
            )
        )

    monkeypatch.setattr(
        api_app_module,
        "save_config_profile_for_session",
        fake_save_config_profile_for_session,
    )

    auth_client = TestClient(app)
    auth_client.cookies.set(
        "ahm_session",
        session_id,
    )

    response = auth_client.post(
        "/reports/generate",
        files={
            "archive": (
                "export.zip",
                b"fake-archive",
                "application/zip",
            ),
        },
        data={
            "periods": "2026-08",
            "save_config_as": "Maintenance",
        },
    )

    assert response.status_code == 200
    assert saved_configs == [
        (
            "Maintenance",
            effective_config,
        )
    ]


# =====================================================================
# Verifies that the web interface exposes configuration profile controls
# for selection, defaults, explicit save, and autosave preference.
# =====================================================================


def test_web_interface_exposes_config_profile_controls() -> None:
    response = client.get("/")

    assert response.status_code == 200

    html = response.text

    assert 'id="config-profile-select"' in html
    assert 'id="config-profile-none"' in html
    assert 'id="save-config-as"' in html
    assert 'id="config-autosave"' in html


# =====================================================================
# Verifies that the web interface loads saved configuration profiles
# and restores the current selection plus autosave preference.
# =====================================================================


def test_web_interface_loads_config_profile_state() -> None:
    response = client.get("/")

    assert response.status_code == 200

    html = response.text

    assert 'fetch("/config/profiles")' in html
    assert "payload.profiles" in html
    assert "payload.selected_profile_id" in html
    assert "payload.autosave_enabled" in html


# =====================================================================
# Verifies that the web interface persists Drive profile selection and
# explicitly clears the selection when application defaults are chosen.
# =====================================================================


def test_web_interface_updates_config_profile_selection() -> None:
    response = client.get("/")

    assert response.status_code == 200

    html = response.text

    assert '"/config/profiles/select"' in html
    assert '"/config/profiles/select-none"' in html
    assert "configProfileSelect.addEventListener(" in html
    assert "configProfileNone.addEventListener(" in html


# =====================================================================
# Verifies that the web interface persists the configuration autosave
# preference when the checkbox state changes.
# =====================================================================


def test_web_interface_updates_config_autosave_preference() -> None:
    response = client.get("/")

    assert response.status_code == 200

    html = response.text

    assert '"/config/autosave"' in html
    assert "configAutosave.addEventListener(" in html
    assert '"enabled"' in html


# =====================================================================
# Verifies that the web interface forwards the explicit configuration
# profile name with the report generation request.
# =====================================================================


def test_web_interface_forwards_save_config_as() -> None:
    response = client.get("/")

    assert response.status_code == 200

    html = response.text

    assert '"save-config-as"' in html
    assert '"save_config_as"' in html
    assert "saveConfigAs.value" in html


# =====================================================================
# Verifies that the web interface explains configuration precedence
# including the selected Drive profile and uploaded configuration.
# =====================================================================


def test_web_interface_explains_config_profile_precedence() -> None:
    response = client.get("/")

    assert response.status_code == 200

    html = response.text

    assert "selected Drive profile" in html
    assert "uploaded config.toml" in html


# =====================================================================
# Verifies that successful report generation refreshes configuration
# profile state so newly saved profiles become visible immediately.
# =====================================================================


def test_web_interface_refreshes_config_profiles_after_generation() -> None:
    response = client.get("/")

    assert response.status_code == 200

    html = response.text

    assert "await loadConfigProfileState();" in html


# =====================================================================
# Verifies that the browser can obtain only the public Google Picker
# configuration required to initialize the Drive file picker.
# =====================================================================


def test_google_picker_config_exposes_browser_safe_values(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "AHM_ENV",
        "development",
    )
    monkeypatch.setenv(
        "GOOGLE_CLIENT_ID",
        "dev-client-id",
    )
    monkeypatch.setenv(
        "GOOGLE_CLIENT_SECRET",
        "dev-client-secret",
    )
    monkeypatch.setenv(
        "GOOGLE_REDIRECT_URI",
        "http://localhost:8000/auth/google/callback",
    )
    monkeypatch.setenv(
        "GOOGLE_PICKER_API_KEY",
        "dev-picker-key",
    )
    monkeypatch.setenv(
        "GOOGLE_CLOUD_PROJECT_NUMBER",
        "123456789",
    )
    monkeypatch.setenv(
        "AHM_SESSION_SECRET",
        "dev-session-secret",
    )

    response = client.get(
        "/google/picker/config",
    )

    assert response.status_code == 200
    assert response.json() == {
        "api_key": "dev-picker-key",
        "app_id": "123456789",
    }


# =====================================================================
# Verifies that an authenticated Google session can obtain the current
# OAuth access token required to initialize the Google Picker.
# =====================================================================


def test_google_picker_token_returns_active_session_token(
    monkeypatch,
) -> None:
    sessions = SessionStore()
    session_id = sessions.create()

    sessions.set_google_identity(
        session_id=session_id,
        google_sub="google-user-123",
        google_email="user@example.com",
    )
    sessions.set_google_access_credentials(
        session_id=session_id,
        access_token="picker-access-token",
        granted_scopes=frozenset(
            GoogleOAuthService.SCOPES,
        ),
        expires_in_seconds=3600,
    )

    monkeypatch.setattr(
        api_app_module,
        "session_store",
        sessions,
    )

    auth_client = TestClient(app)
    auth_client.cookies.set(
        "ahm_session",
        session_id,
    )

    response = auth_client.get(
        "/google/picker/token",
    )

    assert response.status_code == 200
    assert response.json() == {
        "access_token": "picker-access-token",
    }


# =====================================================================
# Verifies that the Google Picker OAuth token response is explicitly
# non-cacheable because it contains a short-lived access credential.
# =====================================================================


def test_google_picker_token_disables_response_caching(
    monkeypatch,
) -> None:
    sessions = SessionStore()
    session_id = sessions.create()

    sessions.set_google_identity(
        session_id=session_id,
        google_sub="google-user-123",
        google_email="user@example.com",
    )
    sessions.set_google_access_credentials(
        session_id=session_id,
        access_token="picker-access-token",
        granted_scopes=frozenset(
            GoogleOAuthService.SCOPES,
        ),
        expires_in_seconds=3600,
    )

    monkeypatch.setattr(
        api_app_module,
        "session_store",
        sessions,
    )

    auth_client = TestClient(app)
    auth_client.cookies.set(
        "ahm_session",
        session_id,
    )

    response = auth_client.get(
        "/google/picker/token",
    )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"


# =====================================================================
# Verifies that the web interface exposes Google Drive ZIP selection
# and loads the Google API required by the Drive Picker.
# =====================================================================


def test_web_interface_exposes_google_drive_picker() -> None:
    response = client.get("/")

    assert response.status_code == 200

    html = response.text

    assert 'id="drive-archive-picker"' in html
    assert "https://apis.google.com/js/api.js" in html
    assert '"drive-archive-picker"' in html


# =====================================================================
# Verifies that the Drive Picker entry point obtains its public config
# and OAuth token without persisting the token in browser storage.
# =====================================================================


def test_web_interface_loads_google_picker_credentials_in_memory() -> None:
    response = client.get("/")

    assert response.status_code == 200

    html = response.text

    assert '"/google/picker/config"' in html
    assert '"/google/picker/token"' in html
    assert "driveArchivePicker.addEventListener(" in html
    assert "pickerAccessToken" in html


# =====================================================================
# Verifies that the web interface builds a single-file Google Drive
# Picker restricted to ZIP archives and handles Picker cancellation.
# =====================================================================


def test_web_interface_builds_zip_only_google_drive_picker() -> None:
    response = client.get("/")

    assert response.status_code == 200

    html = response.text

    assert "google.picker.PickerBuilder()" in html
    assert "application/zip" in html
    assert "google.picker.Action.PICKED" in html
    assert "google.picker.Action.CANCEL" in html


# =====================================================================
# Verifies that the web interface keeps only the selected Drive file ID
# after a successful Google Picker selection.
# =====================================================================


def test_web_interface_keeps_only_selected_drive_file_id() -> None:
    response = client.get("/")

    assert response.status_code == 200

    html = response.text

    assert "selectedDriveFileId" in html
    assert "data.docs[0].id" in html


# =====================================================================
# Verifies that a selected Google Drive archive is accepted only when
# its server-side metadata describes an accessible ZIP within the limit.
# =====================================================================


def test_verify_drive_archive_accepts_valid_zip(
    monkeypatch,
) -> None:
    class FakeDriveClient:
        def __init__(
            self,
            access_token: str,
        ) -> None:
            assert access_token == "drive-token"

        def get_metadata(
            self,
            file_id: str,
        ):
            assert file_id == "drive-file-id"

            return DriveFileMetadata(
                file_id=file_id,
                name="export.zip",
                mime_type="application/zip",
                size_bytes=1024,
                trashed=False,
                app_properties={},
            )

    monkeypatch.setattr(
        api_app_module,
        "HttpGoogleDriveClient",
        FakeDriveClient,
    )

    metadata = verify_drive_archive(
        access_token="drive-token",
        file_id="drive-file-id",
    )

    assert metadata.file_id == "drive-file-id"


# =====================================================================
# Verifies that Drive archive verification rejects a blank file ID
# before attempting any Google Drive request.
# =====================================================================


def test_verify_drive_archive_rejects_blank_file_id(
    monkeypatch,
) -> None:
    class FakeDriveClient:
        def __init__(
            self,
            access_token: str,
        ) -> None:
            raise AssertionError("Drive client must not be created for a blank file ID")

    monkeypatch.setattr(
        api_app_module,
        "HttpGoogleDriveClient",
        FakeDriveClient,
    )

    with pytest.raises(
        HTTPException,
    ) as exc_info:
        verify_drive_archive(
            access_token="drive-token",
            file_id="   ",
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == ("Selected Google Drive file ID is invalid.")


# =====================================================================
# Verifies that inaccessible Google Drive files are exposed as a
# controlled validation error instead of leaking Drive client errors.
# =====================================================================


def test_verify_drive_archive_rejects_inaccessible_file(
    monkeypatch,
) -> None:
    class FakeDriveClient:
        def __init__(
            self,
            access_token: str,
        ) -> None:
            assert access_token == "drive-token"

        def get_metadata(
            self,
            file_id: str,
        ):
            raise DriveAccessError("Google Drive access denied")

    monkeypatch.setattr(
        api_app_module,
        "HttpGoogleDriveClient",
        FakeDriveClient,
    )

    with pytest.raises(
        HTTPException,
    ) as exc_info:
        verify_drive_archive(
            access_token="drive-token",
            file_id="drive-file-id",
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == ("Selected Google Drive file is unavailable.")


# =====================================================================
# Verifies that a selected Google Drive archive is downloaded through
# the bounded Drive client into the requested temporary path.
# =====================================================================


def test_download_drive_archive_uses_bounded_drive_download(
    monkeypatch,
    tmp_path,
) -> None:
    destination = tmp_path / "archive.zip"

    class FakeDriveClient:
        def __init__(
            self,
            access_token: str,
        ) -> None:
            assert access_token == "drive-token"

        def get_metadata(
            self,
            file_id: str,
        ):
            assert file_id == "drive-file-id"

            return DriveFileMetadata(
                file_id=file_id,
                name="export.zip",
                mime_type="application/zip",
                size_bytes=1024,
                trashed=False,
                app_properties={},
            )

        def download_file(
            self,
            file_id,
            destination,
            max_bytes,
        ):
            assert file_id == "drive-file-id"
            assert max_bytes == MAX_UPLOAD_SIZE

            destination.write_bytes(
                b"fake-zip",
            )

            return 8

    monkeypatch.setattr(
        api_app_module,
        "HttpGoogleDriveClient",
        FakeDriveClient,
    )

    download_drive_archive(
        access_token="drive-token",
        file_id="drive-file-id",
        destination=destination,
    )

    assert destination.read_bytes() == b"fake-zip"


# =====================================================================
# Verifies that report generation can use a selected Google Drive ZIP
# as the archive source and pass its temporary path into the application.
# =====================================================================


def test_report_generation_uses_google_drive_archive(
    monkeypatch,
) -> None:
    sessions = SessionStore()
    session_id = sessions.create()

    sessions.set_google_identity(
        session_id=session_id,
        google_sub="google-user-123",
        google_email="user@example.com",
    )
    sessions.set_google_access_credentials(
        session_id=session_id,
        access_token="drive-token",
        granted_scopes=frozenset(
            GoogleOAuthService.SCOPES,
        ),
        expires_in_seconds=3600,
    )
    sessions.set_config_autosave_enabled(
        session_id=session_id,
        enabled=False,
    )

    monkeypatch.setattr(
        api_app_module,
        "session_store",
        sessions,
    )

    captured_archive_path = None

    def fake_download_drive_archive(
        *,
        access_token,
        file_id,
        destination,
    ):
        assert access_token == "drive-token"
        assert file_id == "drive-file-id"

        destination.write_bytes(
            b"fake-drive-zip",
        )

    def fake_generate_reports(
        self,
        options,
    ):
        nonlocal captured_archive_path

        captured_archive_path = options.archive_path

        assert captured_archive_path.exists()
        assert captured_archive_path.read_bytes() == (b"fake-drive-zip")

        return _generation_result()

    monkeypatch.setattr(
        api_app_module,
        "download_drive_archive",
        fake_download_drive_archive,
    )
    monkeypatch.setattr(
        AppleHealthApplication,
        "generate_reports",
        fake_generate_reports,
    )

    auth_client = TestClient(app)
    auth_client.cookies.set(
        "ahm_session",
        session_id,
    )

    response = auth_client.post(
        "/reports/generate",
        data={
            "periods": "2026-08",
            "drive_file_id": "drive-file-id",
        },
    )

    assert response.status_code == 200
    assert captured_archive_path is not None
    assert not captured_archive_path.exists()


# =====================================================================
# Verifies that report generation rejects requests containing both a
# local archive upload and a selected Google Drive archive.
# =====================================================================


def test_report_generation_rejects_multiple_archive_sources(
    monkeypatch,
) -> None:
    sessions = SessionStore()
    session_id = sessions.create()

    sessions.set_google_identity(
        session_id=session_id,
        google_sub="google-user-123",
        google_email="user@example.com",
    )
    sessions.set_google_access_credentials(
        session_id=session_id,
        access_token="drive-token",
        granted_scopes=frozenset(
            GoogleOAuthService.SCOPES,
        ),
        expires_in_seconds=3600,
    )
    sessions.set_config_autosave_enabled(
        session_id=session_id,
        enabled=False,
    )

    monkeypatch.setattr(
        api_app_module,
        "session_store",
        sessions,
    )

    auth_client = TestClient(app)
    auth_client.cookies.set(
        "ahm_session",
        session_id,
    )

    response = auth_client.post(
        "/reports/generate",
        files={
            "archive": (
                "export.zip",
                b"local-zip",
                "application/zip",
            ),
        },
        data={
            "periods": "2026-08",
            "drive_file_id": "drive-file-id",
        },
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": "Choose exactly one Apple Health archive source.",
    }


# =====================================================================
# Verifies that report generation submits the selected Drive file ID
# instead of a local archive when Google Drive is the active ZIP source.
# =====================================================================


def test_web_interface_submits_selected_drive_archive() -> None:
    response = client.get("/")

    assert response.status_code == 200

    html = response.text

    assert '"drive_file_id"' in html
    assert "selectedDriveFileId" in html


# =====================================================================
# Verifies that dropping a local ZIP clears any previously selected
# Google Drive archive before report generation.
# =====================================================================


def test_web_interface_clears_drive_selection_on_local_drop() -> None:
    response = client.get("/")

    assert response.status_code == 200

    html = response.text

    assert (
        "archiveInput.files = transfer.files;" "\n\n" "                selectedDriveFileId = null;"
    ) in html


# =====================================================================
# Verifies that an oversized Google Drive download is exposed as a
# controlled HTTP 413 error.
# =====================================================================


def test_download_drive_archive_rejects_oversized_download(
    monkeypatch,
    tmp_path,
) -> None:
    destination = tmp_path / "archive.zip"

    class FakeDriveClient:
        def __init__(
            self,
            access_token: str,
        ) -> None:
            assert access_token == "drive-token"

        def get_metadata(
            self,
            file_id: str,
        ):
            return DriveFileMetadata(
                file_id=file_id,
                name="export.zip",
                mime_type="application/zip",
                size_bytes=1024,
                trashed=False,
                app_properties={},
            )

        def download_file(
            self,
            file_id,
            destination,
            max_bytes,
        ):
            raise DriveDownloadTooLargeError("Google Drive download exceeds size limit")

    monkeypatch.setattr(
        api_app_module,
        "HttpGoogleDriveClient",
        FakeDriveClient,
    )

    with pytest.raises(
        HTTPException,
    ) as exc_info:
        download_drive_archive(
            access_token="drive-token",
            file_id="drive-file-id",
            destination=destination,
        )

    assert exc_info.value.status_code == 413
    assert exc_info.value.detail == ("Selected Google Drive archive is too large.")


# =====================================================================
# Verifies that a temporary Google Drive archive is removed when report
# generation fails inside the existing archive processing pipeline.
# =====================================================================


def test_report_generation_cleans_up_drive_archive_after_failure(
    monkeypatch,
) -> None:
    sessions = SessionStore()
    session_id = sessions.create()

    sessions.set_google_identity(
        session_id=session_id,
        google_sub="google-user-123",
        google_email="user@example.com",
    )
    sessions.set_google_access_credentials(
        session_id=session_id,
        access_token="drive-token",
        granted_scopes=frozenset(
            GoogleOAuthService.SCOPES,
        ),
        expires_in_seconds=3600,
    )
    sessions.set_config_autosave_enabled(
        session_id=session_id,
        enabled=False,
    )

    monkeypatch.setattr(
        api_app_module,
        "session_store",
        sessions,
    )

    captured_archive_path = None

    def fake_download_drive_archive(
        *,
        access_token,
        file_id,
        destination,
    ):
        assert access_token == "drive-token"
        assert file_id == "drive-file-id"

        destination.write_bytes(
            b"fake-drive-zip",
        )

    def fake_generate_reports(
        self,
        options,
    ):
        nonlocal captured_archive_path

        captured_archive_path = options.archive_path

        assert captured_archive_path.exists()

        raise InvalidArchiveError("invalid archive")

    monkeypatch.setattr(
        api_app_module,
        "download_drive_archive",
        fake_download_drive_archive,
    )
    monkeypatch.setattr(
        AppleHealthApplication,
        "generate_reports",
        fake_generate_reports,
    )

    auth_client = TestClient(app)
    auth_client.cookies.set(
        "ahm_session",
        session_id,
    )

    response = auth_client.post(
        "/reports/generate",
        data={
            "periods": "2026-08",
            "drive_file_id": "drive-file-id",
        },
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": "Invalid Apple Health export archive.",
    }

    assert captured_archive_path is not None
    assert not captured_archive_path.exists()


# =====================================================================
# Verifies that a Drive file becoming inaccessible during download is
# exposed as a controlled validation error.
# =====================================================================


def test_download_drive_archive_rejects_inaccessible_download(
    monkeypatch,
    tmp_path,
) -> None:
    destination = tmp_path / "archive.zip"

    class FakeDriveClient:
        def __init__(
            self,
            access_token: str,
        ) -> None:
            assert access_token == "drive-token"

        def get_metadata(
            self,
            file_id: str,
        ):
            return DriveFileMetadata(
                file_id=file_id,
                name="export.zip",
                mime_type="application/zip",
                size_bytes=1024,
                trashed=False,
                app_properties={},
            )

        def download_file(
            self,
            file_id,
            destination,
            max_bytes,
        ):
            raise DriveAccessError("Google Drive access denied")

    monkeypatch.setattr(
        api_app_module,
        "HttpGoogleDriveClient",
        FakeDriveClient,
    )

    with pytest.raises(
        HTTPException,
    ) as exc_info:
        download_drive_archive(
            access_token="drive-token",
            file_id="drive-file-id",
            destination=destination,
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == ("Selected Google Drive file is unavailable.")


# =====================================================================
# Verifies that malformed Google Drive ZIP input is rejected by the
# existing archive validation pipeline.
# =====================================================================


def test_report_generation_rejects_malformed_drive_archive(
    monkeypatch,
) -> None:
    sessions = SessionStore()
    session_id = sessions.create()

    sessions.set_google_identity(
        session_id=session_id,
        google_sub="google-user-123",
        google_email="user@example.com",
    )
    sessions.set_google_access_credentials(
        session_id=session_id,
        access_token="drive-token",
        granted_scopes=frozenset(
            GoogleOAuthService.SCOPES,
        ),
        expires_in_seconds=3600,
    )
    sessions.set_config_autosave_enabled(
        session_id=session_id,
        enabled=False,
    )

    monkeypatch.setattr(
        api_app_module,
        "session_store",
        sessions,
    )

    def fake_download_drive_archive(
        *,
        access_token,
        file_id,
        destination,
    ):
        assert access_token == "drive-token"
        assert file_id == "drive-file-id"

        destination.write_bytes(
            b"not-a-zip",
        )

    monkeypatch.setattr(
        api_app_module,
        "download_drive_archive",
        fake_download_drive_archive,
    )

    auth_client = TestClient(app)
    auth_client.cookies.set(
        "ahm_session",
        session_id,
    )

    response = auth_client.post(
        "/reports/generate",
        data={
            "periods": "2026-08",
            "drive_file_id": "drive-file-id",
        },
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": "Invalid Apple Health export archive.",
    }


# =====================================================================
# Verifies that the Google Picker access token is kept only in
# JavaScript memory and is never persisted in browser storage.
# =====================================================================


def test_web_interface_keeps_picker_token_in_memory_only() -> None:
    response = client.get("/")

    assert response.status_code == 200

    html = response.text

    assert "pickerAccessToken" in html
    assert "localStorage" not in html
    assert "sessionStorage" not in html


# =====================================================================
# Verifies that cancelling the Google Picker exits the callback without
# changing the selected archive state.
# =====================================================================


def test_web_interface_picker_cancel_is_noop() -> None:
    response = client.get("/")

    assert response.status_code == 200

    html = response.text

    cancel_index = html.index("google.picker.Action.CANCEL")

    callback_tail = html[cancel_index : cancel_index + 200]

    assert "return;" in callback_tail


# =====================================================================
# Verifies that the Google Picker is restricted to a single ZIP file
# and clears any previously selected local archive after Drive selection.
# =====================================================================


def test_web_interface_picker_is_zip_only_and_single_file() -> None:
    response = client.get("/")

    assert response.status_code == 200

    html = response.text

    assert '"application/zip"' in html
    assert "setMimeTypes" in html

    assert "MULTISELECT_ENABLED" not in html

    assert "selectedDriveFileId" in html
    assert 'archiveInput.value = "";' in html


# =====================================================================
# Verifies that the Google Drive ZIP picker is hidden by default until
# Google mode is confirmed as connected.
# =====================================================================


def test_web_interface_hides_drive_picker_until_google_connected() -> None:
    response = client.get("/")

    assert response.status_code == 200

    html = response.text

    assert 'id="drive-archive-picker"' in html
    assert 'id="drive-archive-picker"' in html
    assert (
        "hidden"
        in html[
            html.index('id="drive-archive-picker"')
            - 100 : html.index('id="drive-archive-picker"')
            + 200
        ]
    )


# =====================================================================
# Verifies that the Drive ZIP picker is shown only after the frontend
# confirms that Google mode is connected.
# =====================================================================


def test_web_interface_shows_drive_picker_only_when_google_connected() -> None:
    response = client.get("/")

    assert response.status_code == 200

    html = response.text

    assert "/auth/google/status" in html
    assert 'googleStatus.status === "connected"' in html
    assert "driveArchivePicker.hidden = false;" in html


# =====================================================================
# Verifies that a temporary Google Drive download failure is exposed as
# a controlled HTTP error instead of an unhandled server exception.
# =====================================================================


def test_download_drive_archive_rejects_transient_download_failure(
    monkeypatch,
    tmp_path,
) -> None:
    class FakeDriveClient:
        def __init__(self, access_token: str) -> None:
            assert access_token == "access-token"

        def get_metadata(
            self,
            file_id: str,
        ) -> DriveFileMetadata:
            return DriveFileMetadata(
                file_id=file_id,
                name="export.zip",
                mime_type="application/zip",
                size_bytes=1024,
                trashed=False,
                app_properties={},
            )

        def download_file(
            self,
            file_id: str,
            destination: Path,
            max_bytes: int,
        ) -> int:
            raise DriveTransientError("Google Drive request failed temporarily")

    monkeypatch.setattr(
        api_app_module,
        "HttpGoogleDriveClient",
        FakeDriveClient,
    )

    with pytest.raises(HTTPException) as exc_info:
        download_drive_archive(
            access_token="access-token",
            file_id="drive-file-id",
            destination=tmp_path / "archive.zip",
        )

    assert exc_info.value.status_code == 502
    assert exc_info.value.detail == "Google Drive is temporarily unavailable."


# =====================================================================
# Verifies that saving a Drive config profile uses the current profile
# discovery API without passing an obsolete config container argument.
# =====================================================================


def test_save_config_profile_uses_current_discovery_api(
    monkeypatch,
) -> None:
    calls = []

    def fake_discover_drive_config_profiles(client):
        calls.append(client)
        return ()

    monkeypatch.setattr(
        api_app_module,
        "discover_drive_config_profiles",
        fake_discover_drive_config_profiles,
    )

    # use the existing helper setup from the nearest
    # save_config_profile_for_session test


# =====================================================================
# Verifies that the web interface exposes a Google connection control
# that starts the existing Google OAuth flow.
# =====================================================================


def test_web_interface_exposes_google_connect_control() -> None:
    response = client.get("/")

    assert response.status_code == 200

    html = response.text

    assert 'id="google-connect"' in html
    assert 'href="/auth/google/start"' in html
    assert "Connect Google" in html


# =====================================================================
# Verifies that the web interface replaces the Google connect control
# with the connected account email after successful authentication.
# =====================================================================


def test_web_interface_shows_connected_google_account() -> None:
    response = client.get("/")

    assert response.status_code == 200

    html = response.text

    assert 'id="google-connection-status"' in html
    assert "googleConnect.hidden = true;" in html
    assert "googleConnectionStatus.hidden = false;" in html
    assert "googleStatus.email" in html


# =====================================================================
# Verifies that the web interface restores the disconnected Google state
# by showing the connect control and hiding Google-only controls.
# =====================================================================


def test_web_interface_restores_disconnected_google_state() -> None:
    response = client.get("/")

    assert response.status_code == 200

    html = response.text

    assert "googleConnect.hidden = false;" in html
    assert "googleConnectionStatus.hidden = true;" in html
    assert "driveArchivePicker.hidden = true;" in html


# =====================================================================
# Verifies that the web interface exposes a reconnect action when the
# Google session requires reauthentication.
# =====================================================================


def test_web_interface_shows_google_reconnect_state() -> None:
    response = client.get("/")

    assert response.status_code == 200

    html = response.text

    assert 'googleStatus.status === "reconnect_required"' in html
    assert "googleConnectLabel.textContent" in html
    assert '"Reconnect Google"' in html
    assert "googleConnect.hidden = false;" in html
    assert "googleConnectionStatus.hidden = true;" in html
    assert "driveArchivePicker.hidden = true;" in html


# =====================================================================
# Verifies that a successful Google OAuth callback redirects the user
# back to the application root.
# =====================================================================


def test_google_callback_redirects_to_application_root(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        api_app_module.session_store,
        "get",
        lambda _: object(),
    )

    monkeypatch.setattr(
        api_app_module.GoogleOAuthService,
        "complete",
        lambda self, **_: None,
    )

    monkeypatch.setattr(
        api_app_module.GoogleSettings,
        "load",
        lambda: SimpleNamespace(
            client_id="test-client-id",
            client_secret="test-client-secret",
            redirect_uri="http://localhost:8000/auth/google/callback",
        ),
    )

    response = client.get(
        "/auth/google/callback",
        params={
            "code": "test-code",
            "state": "test-state",
        },
        cookies={
            "ahm_session": "test-session",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/"


# =====================================================================
# Verifies that saved Google Drive config profiles are loaded only
# after the frontend confirms an active Google connection.
# =====================================================================


def test_web_interface_loads_config_profiles_only_when_google_connected() -> None:
    response = client.get("/")

    assert response.status_code == 200

    html = response.text

    google_state_function = html.split(
        "async function loadGoogleConnectionState()",
        1,
    )[1].split(
        "async function loadConfigProfileState()",
        1,
    )[0]

    assert "await loadConfigProfileState();" in google_state_function

    assert "loadConfigProfileState();\n" "        loadGoogleConnectionState();" not in html


# =====================================================================
# Verifies that the reports API can serialize unselected report outputs
# as missing values while returning the selected Full JSON output.
# =====================================================================


def test_reports_api_serializes_unselected_outputs_as_none(
    monkeypatch,
) -> None:
    class FakeApplication:
        def generate_reports(
            self,
            options,
        ):
            return _generation_result(
                reports=(
                    MonthlyReports(
                        period=ReportPeriod(
                            year=2026,
                            month=8,
                        ),
                        full_text=None,
                        full_json='{"status":"ok"}',
                        summary_text=None,
                        summary_json=None,
                        metadata=ReportGenerationMetadata(
                            period=ReportPeriod(
                                year=2026,
                                month=8,
                            ),
                            generation_id="generation-123",
                            generated_at=datetime(
                                2026,
                                9,
                                10,
                                20,
                                30,
                                tzinfo=timezone.utc,
                            ),
                        ),
                    ),
                ),
            )

    monkeypatch.setattr(
        api_app_module,
        "AppleHealthApplication",
        FakeApplication,
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
            "periods": "2026-08",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "reports": [
            {
                "year": 2026,
                "month": 8,
                "full_text": None,
                "full_json": '{"status":"ok"}',
                "summary_text": None,
                "summary_json": None,
                "generation_id": "generation-123",
                "generated_at": "2026-09-10T20:30:00Z",
            },
        ],
    }


# =====================================================================
# Verifies that the reports API passes the selected report outputs to
# the application generation options.
# =====================================================================


def test_reports_api_passes_selected_outputs_to_generation(
    monkeypatch,
) -> None:
    def fake_generate_reports(
        self,
        options,
    ):
        assert options.outputs == ReportOutputs(
            full_text=True,
            full_json=False,
            summary_text=True,
            summary_json=False,
        )

        return _generation_result()

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
            "periods": "2026-08",
            "full_text": "true",
            "full_json": "false",
            "summary_text": "true",
            "summary_json": "false",
        },
    )

    assert response.status_code == 200


# =====================================================================
# Verifies that report generation rejects requests with every report
# output disabled.
# =====================================================================


def test_reports_api_rejects_all_outputs_disabled() -> None:
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
            "periods": "2026-08",
            "full_text": "false",
            "full_json": "false",
            "summary_text": "false",
            "summary_json": "false",
        },
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": "At least one report output must be selected.",
    }


# =====================================================================
# Verifies that the web interface exposes selectable report outputs
# with Full JSON selected by default.
# =====================================================================


def test_web_interface_exposes_report_output_controls() -> None:
    response = client.get("/")

    assert response.status_code == 200

    html = response.text

    assert 'id="output-full-text"' in html
    assert 'id="output-full-json"' in html
    assert 'id="output-summary-text"' in html
    assert 'id="output-summary-json"' in html

    assert re.search(
        r'<input[^>]*id="output-full-json"[^>]*checked[^>]*>',
        html,
        re.DOTALL,
    )


# =====================================================================
# Verifies that the web interface submits the selected report outputs
# with the report generation request.
# =====================================================================


def test_web_interface_submits_selected_report_outputs() -> None:
    response = client.get("/")

    assert response.status_code == 200

    html = response.text

    assert 'document.getElementById("output-full-text")' in html
    assert 'document.getElementById("output-full-json")' in html
    assert 'document.getElementById("output-summary-text")' in html
    assert 'document.getElementById("output-summary-json")' in html

    assert '"full_text"' in html
    assert '"full_json"' in html
    assert '"summary_text"' in html
    assert '"summary_json"' in html

    assert "outputFullText.checked" in html
    assert "outputFullJson.checked" in html
    assert "outputSummaryText.checked" in html
    assert "outputSummaryJson.checked" in html


# =====================================================================
# Verifies that the web interface blocks report generation when no
# report output is selected.
# =====================================================================


def test_web_interface_rejects_no_selected_report_outputs() -> None:
    response = client.get("/")

    assert response.status_code == 200

    html = " ".join(response.text.split())

    assert "const hasSelectedOutput =" in html
    assert "outputFullText.checked" in html
    assert "outputFullJson.checked" in html
    assert "outputSummaryText.checked" in html
    assert "outputSummaryJson.checked" in html
    assert "if (!hasSelectedOutput)" in html
    assert "Select at least one report output." in html


# =====================================================================
# Verifies that the web interface renders download controls only for
# report outputs actually returned by the backend.
# =====================================================================


def test_web_interface_renders_only_available_report_outputs() -> None:
    response = client.get("/")

    assert response.status_code == 200

    html = " ".join(response.text.split())

    assert "if (report.full_text !== null)" in html
    assert "if (report.full_json !== null)" in html
    assert "if (report.summary_text !== null)" in html
    assert "if (report.summary_json !== null)" in html


# =====================================================================
# Verifies that the web interface documents selectable report outputs
# instead of claiming that every report format is always generated.
# =====================================================================


def test_web_interface_documents_selectable_report_outputs() -> None:
    response = client.get("/")

    assert response.status_code == 200

    html = " ".join(response.text.split())

    assert "Selected report outputs are generated for every chosen month." in html
    assert "Every selected month produces" not in html


# =====================================================================
# Verifies that the reports API exposes the generation identity and
# timestamp assigned to each generated monthly report.
# =====================================================================


def test_reports_api_serializes_month_generation_metadata(
    monkeypatch,
) -> None:
    generated_at = datetime(
        2026,
        9,
        10,
        20,
        30,
        tzinfo=timezone.utc,
    )

    class FakeApplication:
        def generate_reports(
            self,
            options,
        ):
            period = ReportPeriod(
                year=2026,
                month=8,
            )

            return _generation_result(
                reports=(
                    MonthlyReports(
                        period=period,
                        full_text=None,
                        full_json='{"status":"ok"}',
                        summary_text=None,
                        summary_json=None,
                        metadata=ReportGenerationMetadata(
                            period=period,
                            generation_id="generation-123",
                            generated_at=generated_at,
                        ),
                    ),
                ),
            )

    monkeypatch.setattr(
        api_app_module,
        "AppleHealthApplication",
        FakeApplication,
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
            "periods": "2026-08",
        },
    )

    assert response.status_code == 200

    report = response.json()["reports"][0]

    assert report["generation_id"] == "generation-123"

    assert (
        datetime.fromisoformat(
            report["generated_at"].replace(
                "Z",
                "+00:00",
            )
        )
        == generated_at
    )
