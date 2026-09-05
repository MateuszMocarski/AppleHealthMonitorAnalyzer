import json
import zipfile
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from zipfile import ZipFile

from fastapi.testclient import TestClient

import apple_health.api.app as api_app_module
from apple_health.api.app import app
from apple_health.application.application import AppleHealthApplication
from apple_health.application.monthly_reports import MonthlyReports
from apple_health.application.report_period import ReportPeriod
from apple_health.config.app_config import AppConfig
from apple_health.exceptions import (
    ExportXmlTooLargeError,
    HealthDataParseError,
    InvalidArchiveError,
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
        return []

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
        lambda self, options: [],
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

        return []

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
        lambda self, options: [],
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

        return []

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

        return []

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

        return []

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
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "google_connected",
    }

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
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "google_connected",
    }

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
