import json
import zipfile
from io import BytesIO
from pathlib import Path
from zipfile import BadZipFile, ZipFile

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

        raise BadZipFile("invalid archive")

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
        raise ValueError("Expected Apple HealthData root element.")

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
        raise RuntimeError("Apple Health export XML is too large.")

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
