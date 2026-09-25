import json
import re
import zipfile
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse
from zipfile import ZipFile

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import connected_health.api.app as api_app_module
from connected_health.api.app import (
    MAX_UPLOAD_SIZE,
    app,
    download_drive_archive,
    verify_drive_archive,
)
from connected_health.application.application import AppleHealthApplication
from connected_health.application.monthly_reports import MonthlyReports
from connected_health.application.report_generation_metadata import (
    ReportGenerationMetadata,
)
from connected_health.application.report_generation_result import (
    ReportGenerationResult,
)
from connected_health.application.report_outputs import ReportOutputs
from connected_health.application.report_period import ReportPeriod
from connected_health.config.app_config import AppConfig
from connected_health.config.exceptions import ConfigurationError
from connected_health.google.config_profiles import ConfigProfile
from connected_health.google.drive import (
    DriveAccessError,
    DriveConflictError,
    DriveDownloadTooLargeError,
    DriveFileMetadata,
    DriveNotFoundError,
    DriveTransientError,
)
from connected_health.google.drive_structure import ViewerReportArtifact
from connected_health.google.oauth import (
    GoogleOAuthError,
    GoogleOAuthService,
    GoogleTokenResponse,
)
from connected_health.google.sessions import SessionStore
from connected_health.providers.apple.errors import (
    ExportXmlTooLargeError,
    HealthDataParseError,
    InvalidArchiveError,
)
from connected_health.viewer.report_contract import parse_persisted_report
from connected_health.viewer.report_loader import ViewerReportLoadError

client = TestClient(app)


def test_api_uses_connected_health_analyzer_title() -> None:
    assert app.title == "Connected Health Analyzer"


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
# Verifies that browser-facing responses include baseline security
# headers that reduce MIME sniffing, framing, and referrer leakage.
# =====================================================================


def test_browser_security_headers_are_applied() -> None:
    response = client.get("/health")

    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["content-security-policy"] == "frame-ancestors 'none'"


# =====================================================================
# Verifies that Google/session state endpoints are marked no-store so
# browsers and intermediaries do not cache private account state.
# =====================================================================


@pytest.mark.parametrize(
    "path",
    [
        "/auth/google/status",
        "/config/profiles",
        "/reports/autosave",
        "/viewer/reports",
    ],
)
def test_private_google_state_endpoints_are_not_cached(
    path: str,
) -> None:
    response = client.get(path)

    assert response.headers["cache-control"] == "no-store"


def test_viewer_report_index_returns_active_artifact_metadata_for_google_session(
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
    monkeypatch.setattr(api_app_module, "session_store", sessions)

    def discover_index(session):
        assert session.google_access_token == "access-token"
        return (
            ViewerReportArtifact(
                file_id="full-file-id",
                period="2026-08",
                kind="full",
                generation_id="generation-123",
                generated_at="2026-09-12T18:00:00Z",
            ),
        )

    monkeypatch.setattr(api_app_module, "discover_viewer_report_index_for_session", discover_index)

    auth_client = TestClient(app)
    auth_client.cookies.set("ahm_session", session_id)

    response = auth_client.get("/viewer/reports")

    assert response.status_code == 200
    assert response.json() == {
        "artifacts": [
            {
                "file_id": "full-file-id",
                "period": "2026-08",
                "kind": "full",
                "generation_id": "generation-123",
                "generated_at": "2026-09-12T18:00:00Z",
            }
        ]
    }
    assert response.headers["cache-control"] == "no-store"


def test_viewer_report_index_requires_connected_google_session(
    monkeypatch,
) -> None:
    sessions = SessionStore()
    session_id = sessions.create()
    monkeypatch.setattr(api_app_module, "session_store", sessions)

    auth_client = TestClient(app)
    auth_client.cookies.set("ahm_session", session_id)

    response = auth_client.get("/viewer/reports")

    assert response.status_code == 401
    assert response.json() == {"detail": "Google reconnect is required."}


def test_viewer_report_index_rejects_missing_google_session() -> None:
    response = TestClient(app).get("/viewer/reports")

    assert response.status_code == 401
    assert response.json() == {"detail": "Google session is unavailable."}


def test_viewer_report_index_uses_google_reconnect_recovery_for_drive_access_failure(
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
    monkeypatch.setattr(api_app_module, "session_store", sessions)

    def fail_discovery(_session):
        raise DriveAccessError("access denied")

    monkeypatch.setattr(api_app_module, "discover_viewer_report_index_for_session", fail_discovery)

    recovery_client = TestClient(app, raise_server_exceptions=False)
    recovery_client.cookies.set("ahm_session", session_id)

    response = recovery_client.get("/viewer/reports")

    assert response.status_code == 401
    assert response.json() == {"detail": "Google reconnect is required."}


def _connected_google_session() -> tuple[SessionStore, str]:
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
    return sessions, session_id


def test_open_viewer_report_verifies_file_id_before_loading_body(
    monkeypatch,
) -> None:
    selected = ViewerReportArtifact(
        file_id="selected-file-id",
        period="2026-08",
        kind="summary",
        generation_id="generation-123",
        generated_at="2026-09-12T18:00:00Z",
    )
    load_calls = []

    class FakeDriveClient:
        def __init__(self, access_token: str) -> None:
            assert access_token == "access-token"

    monkeypatch.setattr(api_app_module, "HttpGoogleDriveClient", FakeDriveClient)
    monkeypatch.setattr(api_app_module, "discover_viewer_report_index", lambda _client: (selected,))
    monkeypatch.setattr(
        api_app_module,
        "load_viewer_report",
        lambda _client, *, artifact: load_calls.append(artifact.file_id) or "validated-report",
    )

    session = SimpleNamespace(google_access_token="access-token")
    artifact, report = api_app_module.open_viewer_report_for_session(
        session,
        file_id="selected-file-id",
    )

    assert artifact == selected
    assert report == "validated-report"
    assert load_calls == ["selected-file-id"]

    with pytest.raises(api_app_module.ViewerReportArtifactUnavailableError):
        api_app_module.open_viewer_report_for_session(session, file_id="arbitrary-file-id")

    assert load_calls == ["selected-file-id"]


def test_viewer_replacement_lifecycle_exposes_only_new_current_artifacts(
    monkeypatch,
) -> None:
    sessions, session_id = _connected_google_session()
    monkeypatch.setattr(api_app_module, "session_store", sessions)

    old_full = ViewerReportArtifact(
        file_id="old-full-file-id",
        period="2026-08",
        kind="full",
        generation_id="generation-old",
        generated_at="2026-09-12T18:00:00Z",
    )
    new_full = ViewerReportArtifact(
        file_id="new-full-file-id",
        period="2026-08",
        kind="full",
        generation_id="generation-new",
        generated_at="2026-09-13T18:00:00Z",
    )
    active_artifacts = [old_full]
    load_calls: list[str] = []

    class FakeDriveClient:
        def __init__(self, access_token: str) -> None:
            assert access_token == "access-token"

    monkeypatch.setattr(api_app_module, "HttpGoogleDriveClient", FakeDriveClient)
    monkeypatch.setattr(
        api_app_module,
        "discover_viewer_report_index_for_session",
        lambda _session: tuple(active_artifacts),
    )
    monkeypatch.setattr(
        api_app_module,
        "discover_viewer_report_index",
        lambda _client: tuple(active_artifacts),
    )
    monkeypatch.setattr(
        api_app_module,
        "load_viewer_report",
        lambda _client, *, artifact: load_calls.append(artifact.file_id) or "validated-report",
    )

    auth_client = TestClient(app)
    auth_client.cookies.set("ahm_session", session_id)

    assert auth_client.get("/viewer/reports").json()["artifacts"] == [
        {
            "file_id": "old-full-file-id",
            "period": "2026-08",
            "kind": "full",
            "generation_id": "generation-old",
            "generated_at": "2026-09-12T18:00:00Z",
        }
    ]

    session = sessions.get(session_id)
    assert session is not None
    api_app_module.open_viewer_report_for_session(
        session,
        file_id="old-full-file-id",
    )

    # This models replacement committing a new current-generation pointer and
    # archiving the former generation: discovery now exposes only the new one.
    active_artifacts[:] = [new_full]

    assert auth_client.get("/viewer/reports").json()["artifacts"] == [
        {
            "file_id": "new-full-file-id",
            "period": "2026-08",
            "kind": "full",
            "generation_id": "generation-new",
            "generated_at": "2026-09-13T18:00:00Z",
        }
    ]

    with pytest.raises(api_app_module.ViewerReportArtifactUnavailableError):
        api_app_module.open_viewer_report_for_session(
            session,
            file_id="old-full-file-id",
        )

    api_app_module.open_viewer_report_for_session(
        session,
        file_id="new-full-file-id",
    )

    assert load_calls == ["old-full-file-id", "new-full-file-id"]


def test_open_viewer_report_endpoint_returns_validated_html_and_disables_caching(
    monkeypatch,
) -> None:
    sessions, session_id = _connected_google_session()
    monkeypatch.setattr(api_app_module, "session_store", sessions)
    artifact = ViewerReportArtifact(
        file_id="selected-file-id",
        period="2026-08",
        kind="summary",
        generation_id="generation-123",
        generated_at="2026-09-12T18:00:00Z",
    )
    report = parse_persisted_report(
        '{"schema_version":"1.0","report":{"type":"monthly","year":2026,'
        '"month":8,"reporting_days":0,"data_through":null},'
        '"general_activity":null,"sleep":null,"workouts":[],"body_weight":null,'
        '"energy_expenditure":null,"nutrition":null,"calories_balance":'
        '{"average_calories_balance_kcal":null,"total_calories_balance_kcal":null,'
        '"calories_balance_count_days":null}}'
    )
    monkeypatch.setattr(
        api_app_module,
        "open_viewer_report_for_session",
        lambda _session, *, file_id: (artifact, report),
    )

    auth_client = TestClient(app)
    auth_client.cookies.set("ahm_session", session_id)
    response = auth_client.get("/viewer/reports/selected-file-id")

    assert response.status_code == 200
    assert response.json()["artifact"]["file_id"] == "selected-file-id"
    assert "August 2026" in response.json()["html"]
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    ("error", "status_code", "detail"),
    [
        (DriveAccessError("access denied"), 401, "Google reconnect is required."),
        (DriveTransientError("temporary failure"), 502, "Google Drive is temporarily unavailable."),
        (DriveConflictError("conflict"), 409, "Managed Viewer reports are conflicted."),
        (DriveNotFoundError("missing"), 404, "Selected Viewer report is unavailable."),
        (DriveDownloadTooLargeError("too large"), 413, "Selected Viewer report is too large."),
        (ViewerReportLoadError("invalid"), 422, "Selected Viewer report is invalid."),
    ],
)
def test_open_viewer_report_endpoint_maps_controlled_load_errors(
    monkeypatch,
    error: Exception,
    status_code: int,
    detail: str,
) -> None:
    sessions, session_id = _connected_google_session()
    monkeypatch.setattr(api_app_module, "session_store", sessions)

    def fail_open(_session, *, file_id: str):
        assert file_id == "selected-file-id"
        raise error

    monkeypatch.setattr(api_app_module, "open_viewer_report_for_session", fail_open)

    recovery_client = TestClient(app, raise_server_exceptions=False)
    recovery_client.cookies.set("ahm_session", session_id)
    response = recovery_client.get("/viewer/reports/selected-file-id")

    assert response.status_code == status_code
    assert response.json() == {"detail": detail}


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
                            tzinfo=UTC,
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
                            tzinfo=UTC,
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
        "connected_health.api.app.MAX_UPLOAD_SIZE",
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
        "connected_health.api.app.MAX_REPORT_PERIODS",
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
        "connected_health.api.app.MAX_CONFIG_UPLOAD_SIZE",
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
        Path(__file__).parents[2]
        / "connected_health"
        / "config"
        / "examples"
        / "config.example.toml"
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

    current_time = datetime(
        2026,
        9,
        5,
        18,
        0,
        tzinfo=UTC,
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
        tzinfo=UTC,
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

    current_time = datetime(
        2026,
        1,
        1,
        tzinfo=UTC,
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

    sessions.set_report_autosave_enabled(
        session_id=session_id,
        enabled=False,
    )

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

    sessions.set_report_autosave_enabled(
        session_id=session_id,
        enabled=False,
    )

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

    sessions.set_report_autosave_enabled(
        session_id=session_id,
        enabled=False,
    )

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

    sessions.set_config_autosave_enabled(
        session_id=session_id,
        enabled=True,
    )

    sessions.set_report_autosave_enabled(
        session_id=session_id,
        enabled=False,
    )

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

    sessions.set_report_autosave_enabled(
        session_id=session_id,
        enabled=False,
    )

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

    sessions.set_report_autosave_enabled(
        session_id=session_id,
        enabled=False,
    )

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
# Verifies that Drive authorization failure during archive verification
# requests Google reconnection instead of treating the file as missing.
# =====================================================================


def test_verify_drive_archive_requires_reconnect_when_access_is_denied(
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

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == ("Google reconnect is required.")


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

    sessions.set_report_autosave_enabled(
        session_id=session_id,
        enabled=False,
    )

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
# Verifies that Drive authorization failure during archive download
# requests Google reconnection instead of treating the file as missing.
# =====================================================================


def test_download_drive_archive_requires_reconnect_when_access_is_denied(
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

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == ("Google reconnect is required.")


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
    assert "window.open(" in html
    assert '"/auth/google/start?popup=true"' in html
    assert '"google-oauth-complete"' in html
    assert "await loadGoogleConnectionState();" in html


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

    callback_client = TestClient(app)
    callback_client.cookies.set(
        "ahm_session",
        "test-session",
    )

    response = callback_client.get(
        "/auth/google/callback",
        params={
            "code": "test-code",
            "state": "test-state",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/"


# =====================================================================
# Verifies that saved Google Drive config profiles are loaded only
# after the frontend confirms an active Google connection.
# =====================================================================


# =====================================================================
# Verifies that popup OAuth start marks the flow without changing the
# normal backend session cookie contract.
# =====================================================================


def test_google_oauth_start_marks_popup_flow(
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

    sessions = SessionStore()

    monkeypatch.setattr(
        api_app_module,
        "session_store",
        sessions,
    )

    auth_client = TestClient(app)

    response = auth_client.get(
        "/auth/google/start?popup=true",
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.cookies["ahm_google_oauth_popup"] == "1"


# =====================================================================
# Verifies that a successful popup OAuth callback notifies the opener
# and closes itself instead of reloading the main application page.
# =====================================================================


def test_google_callback_completes_popup_without_root_redirect(
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

    callback_client = TestClient(app)
    callback_client.cookies.set(
        "ahm_session",
        "test-session",
    )
    callback_client.cookies.set(
        "ahm_google_oauth_popup",
        "1",
    )

    response = callback_client.get(
        "/auth/google/callback",
        params={
            "code": "test-code",
            "state": "test-state",
        },
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert "google-oauth-complete" in response.text
    assert "window.opener.postMessage(" in response.text
    assert "window.close();" in response.text
    assert "ahm_google_oauth_popup" in response.headers["set-cookie"]


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
# Verifies that the top-level Viewer shell is unavailable in the initial
# anonymous page state, while Generate remains the active module.
# =====================================================================


def test_web_interface_starts_in_anonymous_generate_only_mode() -> None:
    response = client.get("/")

    assert response.status_code == 200

    html = response.text

    module_switch = html[
        html.index('id="module-switch"') - 160 : html.index('id="module-switch"') + 220
    ]
    viewer_module = html[
        html.index('id="viewer-module"') - 160 : html.index('id="viewer-module"') + 260
    ]

    assert "hidden" in module_switch
    assert 'id="generate-module"' in html
    assert 'aria-selected="true"' in html
    assert "hidden" in viewer_module


# =====================================================================
# Verifies that a confirmed Google connection enables the accessible module
# switch, retains Generate as the default, and loads only report metadata.
# =====================================================================


def test_web_interface_enables_and_loads_viewer_index_after_google_connection() -> None:
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

    assert 'role="tablist"' in html
    assert 'id="generate-module-tab"' in html
    assert 'id="viewer-module-tab"' in html
    assert 'aria-controls="generate-module"' in html
    assert 'aria-controls="viewer-module"' in html
    assert 'googleStatus.status === "connected"' in google_state_function
    assert "enableViewer();" in google_state_function
    assert "const viewerIndexLoad =" in google_state_function
    assert "loadViewerReportIndex();" in google_state_function
    assert "await loadConfigProfileState();" in google_state_function
    assert "await loadReportAutosaveState();" in google_state_function
    assert "await viewerIndexLoad;" in google_state_function
    assert google_state_function.index("loadViewerReportIndex();") < google_state_function.index(
        "await loadConfigProfileState();"
    )
    assert 'fetch("/viewer/reports")' in html
    assert 'fetch("/viewer/reports/' not in html
    assert 'activeModule: "generate"' in html


# =====================================================================
# Verifies that module switching is independent from the Apple provider and
# simply hides or reveals the stable module regions, preserving form inputs.
# =====================================================================


def test_web_interface_switches_modules_without_resetting_generate_state() -> None:
    response = client.get("/")

    assert response.status_code == 200

    html = response.text
    module_switch_function = html.split(
        "function setActiveModule(moduleName)",
        1,
    )[1].split(
        "function clearViewerState()",
        1,
    )[0]

    assert "selectedProvider" not in module_switch_function
    assert "generateModule.hidden = viewerIsActive;" in module_switch_function
    assert "viewerModule.hidden = !viewerIsActive;" in module_switch_function
    assert "archiveInput.value" not in module_switch_function
    assert "selectedMonths.clear" not in module_switch_function
    assert 'setActiveModule("viewer")' in html
    assert 'setActiveModule("generate")' in html


# =====================================================================
# Verifies that Viewer index state handles loading, empty and controlled
# failure states without opening a report or adding report-selection UI.
# =====================================================================


def test_web_interface_keeps_viewer_index_metadata_only_and_failure_local() -> None:
    response = client.get("/")

    assert response.status_code == 200

    html = response.text

    assert "Loading saved report index" in html
    assert "No saved JSON reports are available." in html
    assert "Saved report discovery is temporarily unavailable." in html
    assert "viewerState.artifacts = payload.artifacts;" in html
    assert 'id="viewer-index-status"' in html
    assert 'id="output-viewer' not in html
    assert 'id="viewer-report-picker"' not in html


# =====================================================================
# Verifies that Viewer index requests use a monotonic generation so stale
# fetches cannot restore data or surface recovery after clear/newer loads.
# =====================================================================


def test_web_interface_invalidates_stale_viewer_index_requests() -> None:
    response = client.get("/")

    assert response.status_code == 200

    html = response.text
    clear_function = html.split(
        "function clearViewerState()",
        1,
    )[1].split(
        "function enableViewer()",
        1,
    )[0]
    load_function = html.split(
        "async function loadViewerReportIndex()",
        1,
    )[1].split(
        "generateModuleTab.addEventListener",
        1,
    )[0]

    assert "let viewerIndexRequestGeneration = 0;" in html
    assert "viewerIndexRequestGeneration += 1;" in clear_function
    assert "const requestGeneration =" in load_function
    assert "viewerIndexRequestGeneration = requestGeneration;" in load_function
    assert load_function.count("!== viewerIndexRequestGeneration") == 4
    assert load_function.rindex("!== viewerIndexRequestGeneration") < load_function.index(
        "viewerState.artifacts = payload.artifacts;"
    )
    assert load_function.index("!== viewerIndexRequestGeneration") < load_function.index(
        "showTransientDriveRecovery(loadViewerReportIndex);"
    )
    assert load_function.index("!== viewerIndexRequestGeneration") < load_function.index(
        "showReconnectRecovery();"
    )


# =====================================================================
# Verifies that connected Viewer state is loading before discovery resolves,
# and that the empty message requires a successful current index response.
# =====================================================================


def test_web_interface_shows_empty_viewer_state_only_after_current_index_load() -> None:
    response = client.get("/")

    assert response.status_code == 200

    html = response.text
    render_function = html.split(
        "function renderViewerIndexState()",
        1,
    )[1].split(
        "function setActiveModule",
        1,
    )[0]
    enable_function = html.split(
        "function enableViewer()",
        1,
    )[1].split(
        "async function loadViewerReportIndex()",
        1,
    )[0]
    load_function = html.split(
        "async function loadViewerReportIndex()",
        1,
    )[1].split(
        "generateModuleTab.addEventListener",
        1,
    )[0]

    assert "viewerState.indexLoading = true;" in enable_function
    assert "renderViewerIndexState();" in enable_function
    assert "if (viewerState.indexLoading)" in render_function
    assert "viewerState.indexLoaded" in render_function
    assert "viewerState.indexLoaded = true;" in load_function
    assert render_function.index("viewerState.indexLoaded") < render_function.index(
        "No saved JSON reports are available."
    )
    assert load_function.index("viewerState.indexLoaded = true;") < load_function.index(
        "viewerState.indexLoading = false;",
        load_function.index("viewerState.indexLoaded = true;"),
    )


# =====================================================================
# Verifies that the connected Viewer builds a compact selector from the
# discovered metadata with human-facing labels only.
# =====================================================================


def test_web_interface_builds_safe_grouped_viewer_report_selector() -> None:
    response = client.get("/")

    assert response.status_code == 200

    html = response.text
    selector_function = html.split(
        "function renderViewerSelector()",
        1,
    )[1].split(
        "function renderViewerReportState()",
        1,
    )[0]

    assert 'id="viewer-selector"' in html
    assert 'id="viewer-selector-toggle"' in html
    assert 'id="viewer-selector-menu"' in html
    assert 'aria-expanded="false"' in html
    assert "viewerState.artifacts.forEach" in selector_function
    assert "formatViewerPeriod(artifact.period)" in selector_function
    assert '"Full report"' in selector_function
    assert '"Summary report"' in selector_function
    assert "document.createElement" in selector_function
    assert ".textContent" in selector_function
    assert ".innerHTML" not in selector_function
    assert "generation_id" not in selector_function
    assert "generated_at" not in selector_function


# =====================================================================
# Verifies that backend discovery order is preserved for selector grouping,
# so newest periods and Full-before-Summary remain authoritative.
# =====================================================================


def test_web_interface_preserves_backend_viewer_artifact_order_for_selector() -> None:
    response = client.get("/")

    assert response.status_code == 200

    html = response.text
    selector_function = html.split(
        "function renderViewerSelector()",
        1,
    )[1].split(
        "function renderViewerReportState()",
        1,
    )[0]

    assert "viewerState.artifacts.forEach" in selector_function
    assert ".sort(" not in selector_function
    assert "previousYear" in selector_function
    assert "previousPeriod" in selector_function
    assert 'artifact.kind === "full"' in selector_function


# =====================================================================
# Verifies that opening Viewer, rather than login/index discovery, performs
# the one default lazy body load for the first Full artifact in backend order.
# =====================================================================


def test_web_interface_defaults_to_newest_full_only_after_viewer_is_opened() -> None:
    response = client.get("/")

    assert response.status_code == 200

    html = response.text
    default_function = html.split(
        "function applyViewerDefaultSelection()",
        1,
    )[1].split(
        "function viewerReportErrorMessage",
        1,
    )[0]
    module_function = html.split(
        "function setActiveModule(moduleName)",
        1,
    )[1].split(
        "function clearViewerState()",
        1,
    )[0]
    google_state_function = html.split(
        "async function loadGoogleConnectionState()",
        1,
    )[1].split(
        "async function loadConfigProfileState()",
        1,
    )[0]

    assert 'viewerState.activeModule !== "viewer"' in default_function
    assert "viewerState.defaultSelectionAttempted" in default_function
    assert 'artifact.kind === "full"' in default_function
    assert "selectViewerArtifact(defaultArtifact);" in default_function
    assert "No Full report available for default viewing." in default_function
    assert 'moduleName === "viewer"' in module_function
    assert "applyViewerDefaultSelection();" in module_function
    assert "selectViewerArtifact(" not in google_state_function
    assert 'fetch("/viewer/reports/' not in google_state_function


# =====================================================================
# Verifies that one manual Full or Summary selection uses its file identifier,
# consumes backend-rendered HTML, and leaves no client-side report rebuilding.
# =====================================================================


def test_web_interface_opens_selected_viewer_report_at_the_server_rendering_boundary() -> None:
    response = client.get("/")

    assert response.status_code == 200

    html = response.text
    selection_function = html.split(
        "async function selectViewerArtifact(artifact)",
        1,
    )[1].split(
        "function setActiveModule",
        1,
    )[0]
    report_render_function = html.split(
        "function renderViewerReportState()",
        1,
    )[1].split(
        "function closeViewerSelector()",
        1,
    )[0]

    assert "closeViewerSelector();" in selection_function
    assert "viewerState.selectedArtifact = artifact;" in selection_function
    assert "viewerState.reportLoading = true;" in selection_function
    assert "encodeURIComponent(artifact.file_id)" in selection_function
    assert "sameViewerArtifact(" in selection_function
    assert "viewerState.selectedArtifact = payload.artifact;" in selection_function
    assert "viewerState.reportHtml = payload.html;" in selection_function
    assert "viewerReportContent.innerHTML = viewerState.reportHtml;" in report_render_function
    assert "JSON.parse" not in selection_function
    assert "model_dump" not in selection_function


# =====================================================================
# Verifies that report-body loads have their own generation and cannot surface
# stale content or recovery after selection, index refresh, or Viewer clear.
# =====================================================================


def test_web_interface_invalidates_stale_viewer_report_body_loads() -> None:
    response = client.get("/")

    assert response.status_code == 200

    html = response.text
    reset_function = html.split(
        "function resetViewerReportState(",
        1,
    )[1].split(
        "function applyViewerDefaultSelection()",
        1,
    )[0]
    selection_function = html.split(
        "async function selectViewerArtifact(artifact)",
        1,
    )[1].split(
        "function setActiveModule",
        1,
    )[0]
    index_load_function = html.split(
        "async function loadViewerReportIndex()",
        1,
    )[1].split(
        "generateModuleTab.addEventListener",
        1,
    )[0]

    assert "let viewerReportRequestGeneration = 0;" in html
    assert "viewerReportRequestGeneration += 1;" in reset_function
    assert "const requestGeneration =" in selection_function
    assert "viewerReportRequestGeneration = requestGeneration;" in selection_function
    assert selection_function.count("!== viewerReportRequestGeneration") == 4
    assert selection_function.rindex(
        "!== viewerReportRequestGeneration"
    ) < selection_function.index("viewerState.reportHtml = payload.html;")
    assert selection_function.index("!== viewerReportRequestGeneration") < selection_function.index(
        "showReconnectRecovery();"
    )
    assert "viewerReportRequestGeneration += 1;" in index_load_function
    assert "resetViewerReportState(true);" not in index_load_function


# =====================================================================
# Verifies that a connected-state refresh after report generation keeps a
# still-current mounted report, but invalidates body work and clears a report
# whose active artifact was replaced.
# =====================================================================


def test_web_interface_reconciles_viewer_selection_after_persisted_report_refresh() -> None:
    response = client.get("/")

    assert response.status_code == 200

    html = response.text
    enable_function = html.split(
        "function enableViewer()",
        1,
    )[1].split(
        "async function loadViewerReportIndex()",
        1,
    )[0]
    index_load_function = html.split(
        "async function loadViewerReportIndex()",
        1,
    )[1].split(
        "generateModuleTab.addEventListener",
        1,
    )[0]
    report_render_function = html.split(
        "function renderViewerReportState()",
        1,
    )[1].split(
        "function initializeViewerDailyNavigation()",
        1,
    )[0]
    generation_function = html.split(
        "async function handleSuccessfulGeneration(",
        1,
    )[1].split(
        "async function handleGenerationRecovery",
        1,
    )[0]

    assert "if (viewerState.available)" in enable_function
    identity_function = html.split(
        "function sameViewerArtifact(",
        1,
    )[1].split(
        "function resetViewerReportState",
        1,
    )[0]

    assert "viewerReportRequestGeneration += 1;" in index_load_function
    assert "viewerState.reportLoading = false;" not in index_load_function
    assert "activeSelectedArtifact" in index_load_function
    assert "viewerState.artifacts.find" in index_load_function
    assert "resetViewerReportState(false);" in index_load_function
    assert "replaced or is no longer active" in index_load_function
    assert "viewerState.selectedArtifact =" in index_load_function
    assert "restartSelectedArtifact" in index_load_function
    assert "selectViewerArtifact(restartSelectedArtifact);" in index_load_function
    assert (
        "return;"
        in index_load_function.split(
            "selectViewerArtifact(restartSelectedArtifact);",
            1,
        )[1]
    )
    assert "mountedReportArtifact" in report_render_function
    assert "sameViewerArtifact(" in report_render_function
    assert "viewerReportContent.innerHTML = viewerState.reportHtml;" in report_render_function
    assert "initializeViewerDailyNavigation();" in report_render_function
    assert "firstArtifact.generation_id" in identity_function
    assert "firstArtifact.period" in identity_function
    assert "firstArtifact.kind" in identity_function
    assert "await loadGoogleConnectionState();" in generation_function


# =====================================================================
# Verifies that only an index-invalidated in-flight selected report is loaded
# again after the refreshed index confirms the complete artifact identity.
# =====================================================================


def test_web_interface_restarts_only_still_current_inflight_viewer_report_load() -> None:
    response = client.get("/")

    assert response.status_code == 200

    html = response.text
    index_load_function = html.split(
        "async function loadViewerReportIndex()",
        1,
    )[1].split(
        "generateModuleTab.addEventListener",
        1,
    )[0]

    assert "const reportWasLoading =" in index_load_function
    assert "if (activeSelectedArtifact === undefined)" in index_load_function
    assert "if (reportWasLoading)" in index_load_function
    assert "restartSelectedArtifact =" in index_load_function
    assert index_load_function.index("renderViewerIndexState();") < index_load_function.index(
        "selectViewerArtifact(restartSelectedArtifact);"
    )
    assert index_load_function.count("selectViewerArtifact(") == 1


# =====================================================================
# Verifies that an index refresh retains the synthetic pending-load state after
# invalidating the old body request, so either a manual retry or the newest of
# overlapping refreshes can restart the selected artifact exactly once.
# =====================================================================


def test_web_interface_retains_pending_load_across_index_refreshes() -> None:
    response = client.get("/")

    assert response.status_code == 200

    html = response.text
    index_load_function = html.split(
        "async function loadViewerReportIndex()",
        1,
    )[1].split(
        "generateModuleTab.addEventListener",
        1,
    )[0]

    assert "const reportWasLoading =" in index_load_function
    assert "viewerState.reportLoading = false;" not in index_load_function
    assert index_load_function.count("showTransientDriveRecovery(loadViewerReportIndex);") == 3
    assert index_load_function.count("!== viewerIndexRequestGeneration") == 4
    assert index_load_function.index(
        "!== viewerIndexRequestGeneration"
    ) < index_load_function.index("showTransientDriveRecovery(loadViewerReportIndex);")
    assert "if (activeSelectedArtifact === undefined)" in index_load_function
    assert "resetViewerReportState(false);" in index_load_function


# =====================================================================
# Verifies that matching file identifiers alone cannot preserve mounted Viewer
# HTML or accept a report-open response from a different generation.
# =====================================================================


def test_web_interface_uses_complete_viewer_artifact_identity() -> None:
    response = client.get("/")

    assert response.status_code == 200

    html = response.text
    identity_function = html.split(
        "function sameViewerArtifact(",
        1,
    )[1].split(
        "function resetViewerReportState",
        1,
    )[0]
    report_render_function = html.split(
        "function renderViewerReportState()",
        1,
    )[1].split(
        "function initializeViewerDailyNavigation()",
        1,
    )[0]
    selection_function = html.split(
        "async function selectViewerArtifact(artifact)",
        1,
    )[1].split(
        "function setActiveModule",
        1,
    )[0]

    for identity_field in ("file_id", "generation_id", "period", "kind"):
        assert f"firstArtifact.{identity_field}" in identity_function
        assert f"secondArtifact.{identity_field}" in identity_function

    assert "sameViewerArtifact(" in report_render_function
    assert "sameViewerArtifact(" in selection_function
    assert "payload.artifact?.file_id" not in selection_function


# =====================================================================
# Verifies that a selected saved report can hand its trusted reporting period
# to Generate without treating persisted JSON as a source or changing the
# explicit provider-selection contract.
# =====================================================================


def test_web_interface_exposes_regenerate_handoff_without_viewer_download() -> None:
    response = client.get("/")

    assert response.status_code == 200

    html = response.text
    regenerate_handler = html.split(
        "viewerRegenerateButton.addEventListener(",
        1,
    )[1].split(
        "function openGoogleOAuthPopup",
        1,
    )[0]
    report_render_function = html.split(
        "function renderViewerReportState()",
        1,
    )[1].split(
        "function initializeViewerDailyNavigation()",
        1,
    )[0]
    reports_function = html.split(
        "function renderReports(reports)",
        1,
    )[1].split(
        "function hideGoogleRecovery",
        1,
    )[0]

    assert 'id="viewer-report-actions"' in html
    assert 'id="viewer-regenerate-button"' in html
    assert "viewerReportActions.hidden" in report_render_function
    assert "selectedMonths.add(artifact.period);" in regenerate_handler
    assert "renderMonthChips();" in regenerate_handler
    assert 'setActiveModule("generate");' in regenerate_handler
    assert "Choose Apple Health and a ZIP source" in regenerate_handler
    assert "selectedProvider =" not in regenerate_handler
    assert "/viewer/reports/${encodeURIComponent(artifact.file_id)}/download" not in html

    for filename in ("full.txt", "full.json", "summary.txt", "summary.json"):
        assert filename in reports_function


# =====================================================================
# Verifies that report-open failures stay controlled and local, with only a
# current 401 following the established reconnect-and-clear behavior.
# =====================================================================


def test_web_interface_exposes_controlled_viewer_report_open_errors() -> None:
    response = client.get("/")

    assert response.status_code == 200

    html = response.text
    error_function = html.split(
        "function viewerReportErrorMessage(statusCode)",
        1,
    )[1].split(
        "async function selectViewerArtifact",
        1,
    )[0]
    selection_function = html.split(
        "async function selectViewerArtifact(artifact)",
        1,
    )[1].split(
        "function setActiveModule",
        1,
    )[0]

    for status_code in (404, 409, 413, 422, 502):
        assert f"{status_code}:" in error_function

    assert "response.status === 401" in selection_function
    assert "showReconnectRecovery();" in selection_function
    assert "viewerReportErrorMessage(response.status)" in selection_function
    assert "response.json" not in selection_function.split("if (!response.ok)", 1)[0]


# =====================================================================
# Verifies that the monthly dashboard styles target explicit server-rendered
# Viewer hooks without adding report calculations to the selector state code.
# =====================================================================


def test_web_interface_styles_server_rendered_monthly_viewer_content() -> None:
    response = client.get("/")

    assert response.status_code == 200

    html = response.text
    viewer_styles = html.split(
        ".viewer-report {",
        1,
    )[1].split(
        ".google-recovery {",
        1,
    )[0]
    viewer_state_code = html.split(
        "const viewerState = {",
        1,
    )[1].split(
        "function updateGenerationSummary()",
        1,
    )[0]

    for css_hook in (
        ".viewer-report-header",
        ".viewer-monthly-dashboard",
        ".viewer-monthly-section",
        ".viewer-metric-grid",
        ".viewer-metric-coverage",
        ".viewer-workout-card",
    ):
        assert css_hook in viewer_styles

    assert ".viewer-report-header h1" in viewer_styles
    for css_hook in (
        ".viewer-controls",
        ".viewer-chart-grid--wide",
        ".viewer-chart-grid--daily",
        ".viewer-monthly-section--activity",
        ".viewer-chart--line .viewer-chart-svg",
        ".viewer-chart-grid--wide .viewer-chart-svg",
        ".viewer-chart-gridline",
        ".viewer-chart-legend-value",
    ):
        assert css_hook in html
    assert ".viewer-chart-slice {\n            stroke: none;" in html
    assert ".viewer-chart-line {\n            fill: none;" in html
    assert "data-viewer-daily" in viewer_styles
    assert "viewerReportContent.innerHTML = viewerState.reportHtml;" in viewer_state_code
    assert "average_daily_steps" not in viewer_state_code
    assert "calories_balance" not in viewer_state_code


def test_web_interface_places_selector_and_regenerate_above_full_width_content() -> None:
    response = client.get("/")

    assert response.status_code == 200

    html = response.text
    layout = (
        html.split('id="viewer-layout"', 1)[1].split(
            'id="viewer-index-status"',
            1,
        )[0]
        + html.split('id="viewer-selector"', 1)[1].split(
            'id="viewer-report-content"',
            1,
        )[0]
        + html.split('id="viewer-report-content"', 1)[1].split(
            'id="viewer-module"',
            1,
        )[0]
    )

    assert layout.index('class="viewer-controls"') < layout.index('class="viewer-report-content"')
    assert layout.index('id="viewer-selector"') < layout.index('id="viewer-regenerate-button"')
    assert ".viewer-layout {\n            display: block;" in html
    assert ".viewer-report-content {\n            min-width: 0;\n            width: 100%;" in html


# =====================================================================
# Verifies that the browser only navigates already-rendered Full-report day
# articles. It neither fetches day data nor derives health values.
# =====================================================================


def test_web_interface_initializes_server_rendered_daily_navigation_without_fetches() -> None:
    response = client.get("/")

    assert response.status_code == 200

    html = response.text
    report_render_function = html.split(
        "function renderViewerReportState()",
        1,
    )[1].split(
        "function initializeViewerDailyNavigation()",
        1,
    )[0]
    navigation_function = html.split(
        "function initializeViewerDailyNavigation()",
        1,
    )[1].split(
        "function closeViewerSelector()",
        1,
    )[0]
    module_function = html.split(
        "function setActiveModule(moduleName)",
        1,
    )[1].split(
        "function clearViewerState()",
        1,
    )[0]
    clear_function = html.split(
        "function clearViewerState()",
        1,
    )[1].split(
        "function enableViewer()",
        1,
    )[0]
    reset_function = html.split(
        "function resetViewerReportState(",
        1,
    )[1].split(
        "function applyViewerDefaultSelection()",
        1,
    )[0]
    viewer_styles = html.split(
        ".viewer-report {",
        1,
    )[1].split(
        ".google-recovery {",
        1,
    )[0]

    assert "initializeViewerDailyNavigation();" in report_render_function
    assert "[data-viewer-daily='true']" in navigation_function
    assert 'querySelectorAll("[data-viewer-day]")' in navigation_function
    assert "days.findIndex" in navigation_function
    assert "days.length - 1" in navigation_function
    assert "day.hidden = dayIndex !== index;" in navigation_function
    assert "previousButton.disabled = index === 0;" in navigation_function
    assert "nextButton.disabled = index === days.length - 1;" in navigation_function
    assert "showDay(currentIndex - 1);" in navigation_function
    assert "showDay(currentIndex + 1);" in navigation_function
    assert "selectedDay.dataset.viewerDay" in navigation_function
    assert "fetch(" not in navigation_function
    assert "JSON.parse" not in navigation_function
    assert "average_daily_steps" not in navigation_function
    assert "calories_balance" not in navigation_function
    assert "renderViewerReportState" not in module_function
    assert "resetViewerReportState(true);" in clear_function
    assert "renderViewerReportState();" in reset_function
    assert "viewerReportContent.replaceChildren();" in report_render_function

    for css_hook in (
        ".viewer-daily-view",
        ".viewer-daily-navigation",
        ".viewer-daily-dashboard",
        ".viewer-daily-section",
        ".viewer-daily-workout-card",
    ):
        assert css_hook in viewer_styles


def test_web_interface_only_controls_the_server_rendered_sleep_config_dialog() -> None:
    response = client.get("/")

    assert response.status_code == 200

    html = response.text
    report_render_function = html.split(
        "function renderViewerReportState()",
        1,
    )[1].split(
        "function initializeViewerDailyNavigation()",
        1,
    )[0]
    config_function = html.split(
        "function initializeViewerSleepConfiguration()",
        1,
    )[1].split(
        "function closeViewerSelector()",
        1,
    )[0]
    viewer_state_code = html.split(
        "const viewerState = {",
        1,
    )[1].split(
        "function updateGenerationSummary()",
        1,
    )[0]

    assert "initializeViewerSleepConfiguration();" in report_render_function
    assert "[data-viewer-sleep-config]" in config_function
    assert "[data-viewer-config-open]" in config_function
    assert "[data-viewer-config-close]" in config_function
    assert "dialog.showModal();" in config_function
    assert "dialog.close();" in config_function
    assert "fetch(" not in config_function
    assert "JSON.parse" not in config_function
    assert "viewerReportContent.innerHTML = viewerState.reportHtml;" in viewer_state_code
    assert "chart.js" not in html.lower()
    assert "new Chart(" not in html

    for css_hook in (
        ".viewer-chart-grid",
        ".viewer-chart-svg",
        ".viewer-chart-zero-line",
        ".viewer-sleep-config-dialog",
    ):
        assert css_hook in html


# =====================================================================
# Verifies that local, anonymous and reconnect-required transitions clear the
# in-memory Viewer state and return the user to Generate.
# =====================================================================


def test_web_interface_clears_viewer_state_when_google_becomes_unavailable() -> None:
    response = client.get("/")

    assert response.status_code == 200

    html = response.text
    clear_function = html.split(
        "function clearViewerState()",
        1,
    )[1].split(
        "function enableViewer()",
        1,
    )[0]
    anonymous_function = html.split(
        "function applyAnonymousGoogleState()",
        1,
    )[1].split(
        "async function continueWithoutGoogle()",
        1,
    )[0]
    reconnect_function = html.split(
        "function showReconnectRecovery()",
        1,
    )[1].split(
        "function showTransientDriveRecovery",
        1,
    )[0]

    assert "viewerState.artifacts = [];" in clear_function
    assert "viewerState.available = false;" in clear_function
    assert "moduleSwitch.hidden = true;" in clear_function
    assert 'setActiveModule("generate");' in clear_function
    assert "clearViewerState();" in anonymous_function
    assert "clearViewerState();" in reconnect_function


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
                                tzinfo=UTC,
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
        tzinfo=UTC,
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


# =====================================================================
# Verifies that an authenticated Google session autosaves generated
# reports by default after local report generation succeeds.
# =====================================================================


def test_generate_reports_autosaves_reports_for_google_session(
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

    # Keep config autosave out of this test.
    sessions.set_config_autosave_enabled(
        session_id=session_id,
        enabled=False,
    )

    monkeypatch.setattr(
        api_app_module,
        "session_store",
        sessions,
    )

    period = ReportPeriod(
        year=2026,
        month=8,
    )

    monthly_report = MonthlyReports(
        period=period,
        full_text=None,
        full_json='{"status":"ok"}',
        summary_text=None,
        summary_json=None,
        metadata=ReportGenerationMetadata(
            period=period,
            generation_id="generation-123",
            generated_at=datetime(
                2026,
                9,
                11,
                16,
                30,
                tzinfo=UTC,
            ),
        ),
    )

    generation_result = _generation_result(
        reports=(monthly_report,),
    )

    class FakeApplication:
        def generate_reports(
            self,
            options,
        ):
            return generation_result

    monkeypatch.setattr(
        api_app_module,
        "AppleHealthApplication",
        FakeApplication,
    )

    drive_client = object()

    monkeypatch.setattr(
        api_app_module,
        "find_existing_report_periods",
        lambda drive_client, *, reports: set(),
    )

    monkeypatch.setattr(
        api_app_module,
        "HttpGoogleDriveClient",
        lambda access_token: drive_client,
    )

    saved = []

    def fake_save_new_report_month(
        received_drive_client,
        *,
        report,
    ):
        saved.append(
            (
                received_drive_client,
                report,
            )
        )

    monkeypatch.setattr(
        api_app_module,
        "save_new_report_month",
        fake_save_new_report_month,
        raising=False,
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
    assert saved == [
        (
            drive_client,
            generation_result.reports[0],
        ),
    ]


# =====================================================================
# Verifies that disabling report autosave prevents generated reports
# from being persisted to Drive.
# =====================================================================


def test_generate_reports_skips_report_persistence_when_autosave_disabled(
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
    sessions.set_report_autosave_enabled(
        session_id=session_id,
        enabled=False,
    )

    monkeypatch.setattr(
        api_app_module,
        "session_store",
        sessions,
    )

    period = ReportPeriod(
        year=2026,
        month=8,
    )

    monthly_report = MonthlyReports(
        period=period,
        full_text=None,
        full_json='{"status":"ok"}',
        summary_text=None,
        summary_json=None,
        metadata=ReportGenerationMetadata(
            period=period,
            generation_id="generation-123",
            generated_at=datetime(
                2026,
                9,
                11,
                16,
                30,
                tzinfo=UTC,
            ),
        ),
    )

    generation_result = _generation_result(
        reports=(monthly_report,),
    )

    class FakeApplication:
        def generate_reports(
            self,
            options,
        ):
            return generation_result

    monkeypatch.setattr(
        api_app_module,
        "AppleHealthApplication",
        FakeApplication,
    )

    save_calls = []

    monkeypatch.setattr(
        api_app_module,
        "save_new_report_month",
        lambda *args, **kwargs: save_calls.append(
            (
                args,
                kwargs,
            )
        ),
        raising=False,
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
    assert save_calls == []


# =====================================================================
# Verifies that the report autosave preference can be updated through
# the API for the current session.
# =====================================================================


def test_report_autosave_preference_can_be_updated(
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
        "/reports/autosave",
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
    assert session.report_autosave_enabled is False


# =====================================================================
# Verifies that the current report autosave preference can be read
# through the API for the active session.
# =====================================================================


def test_report_autosave_preference_can_be_read(
    monkeypatch,
) -> None:
    sessions = SessionStore()
    session_id = sessions.create()

    sessions.set_report_autosave_enabled(
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

    response = auth_client.get(
        "/reports/autosave",
    )

    assert response.status_code == 200
    assert response.json() == {
        "autosave_enabled": False,
    }


# =====================================================================
# Verifies that the web interface exposes report autosave controls and
# synchronizes them with the report autosave API for Google sessions.
# =====================================================================


def test_web_interface_exposes_report_autosave_control() -> None:
    response = client.get("/")

    assert response.status_code == 200

    html = response.text

    assert 'id="report-autosave-control"' in html
    assert 'id="report-autosave"' in html
    assert "Automatically save reports" in html

    assert 'fetch("/reports/autosave")' in html
    assert '"/reports/autosave"' in html
    assert "reportAutosave.checked" in html


# =====================================================================
# Verifies that explicit replacement permission replaces an existing
# saved month instead of returning a conflict.
# =====================================================================


def test_generate_reports_replaces_existing_month_when_explicitly_allowed(
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

    monthly_report = MonthlyReports(
        period=ReportPeriod(
            year=2026,
            month=8,
        ),
        full_text=None,
        full_json='{"status":"new"}',
        summary_text=None,
        summary_json=None,
        metadata=ReportGenerationMetadata(
            period=ReportPeriod(
                year=2026,
                month=8,
            ),
            generation_id="generation-new",
            generated_at=datetime(
                2026,
                9,
                12,
                18,
                0,
                tzinfo=UTC,
            ),
        ),
    )

    monkeypatch.setattr(
        AppleHealthApplication,
        "generate_reports",
        lambda self, options: _generation_result(
            reports=(monthly_report,),
        ),
    )

    drive_client = object()

    monkeypatch.setattr(
        api_app_module,
        "HttpGoogleDriveClient",
        lambda access_token: drive_client,
    )

    monkeypatch.setattr(
        api_app_module,
        "find_existing_report_periods",
        lambda received_drive_client, *, reports: {
            "2026-08",
        },
    )

    calls = []

    monkeypatch.setattr(
        api_app_module,
        "save_new_report_month",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("New-month save must not run for explicit replacement")
        ),
    )

    monkeypatch.setattr(
        api_app_module,
        "replace_existing_report_month",
        lambda received_drive_client, *, report: calls.append(
            (
                received_drive_client,
                report.metadata.generation_id,
            )
        ),
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
            "full_json": "true",
            "replace_periods": "2026-08",
        },
        files={
            "archive": (
                "export.zip",
                b"fake",
                "application/zip",
            ),
        },
    )

    assert response.status_code == 200
    assert calls == [
        (
            drive_client,
            "generation-new",
        ),
    ]


# =====================================================================
# Verifies that explicit replacement applies only to confirmed periods
# while other months still use the normal new-month save flow.
# =====================================================================


def test_generate_reports_replaces_only_explicitly_confirmed_periods(
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

    july_period = ReportPeriod(
        year=2026,
        month=7,
    )

    july = MonthlyReports(
        period=july_period,
        full_text=None,
        full_json='{"status":"july"}',
        summary_text=None,
        summary_json=None,
        metadata=ReportGenerationMetadata(
            period=july_period,
            generation_id="generation-july",
            generated_at=datetime(
                2026,
                9,
                12,
                18,
                0,
                tzinfo=UTC,
            ),
        ),
    )

    august_period = ReportPeriod(
        year=2026,
        month=8,
    )

    august = MonthlyReports(
        period=august_period,
        full_text=None,
        full_json='{"status":"august"}',
        summary_text=None,
        summary_json=None,
        metadata=ReportGenerationMetadata(
            period=august_period,
            generation_id="generation-august",
            generated_at=datetime(
                2026,
                9,
                12,
                18,
                1,
                tzinfo=UTC,
            ),
        ),
    )

    monkeypatch.setattr(
        AppleHealthApplication,
        "generate_reports",
        lambda self, options: _generation_result(
            reports=(july, august),
        ),
    )

    drive_client = object()

    monkeypatch.setattr(
        api_app_module,
        "HttpGoogleDriveClient",
        lambda access_token: drive_client,
    )

    monkeypatch.setattr(
        api_app_module,
        "find_existing_report_periods",
        lambda received_drive_client, *, reports: {
            "2026-08",
        },
    )

    calls = []

    monkeypatch.setattr(
        api_app_module,
        "save_new_report_month",
        lambda received_drive_client, *, report: calls.append(
            (
                "save",
                report.period.year,
                report.period.month,
            )
        ),
    )

    monkeypatch.setattr(
        api_app_module,
        "replace_existing_report_month",
        lambda received_drive_client, *, report: calls.append(
            (
                "replace",
                report.period.year,
                report.period.month,
            )
        ),
    )

    auth_client = TestClient(app)
    auth_client.cookies.set(
        "ahm_session",
        session_id,
    )

    response = auth_client.post(
        "/reports/generate",
        data={
            "periods": "2026-07,2026-08",
            "full_json": "true",
            "replace_periods": "2026-08",
        },
        files={
            "archive": (
                "export.zip",
                b"fake",
                "application/zip",
            ),
        },
    )

    assert response.status_code == 200
    assert calls == [
        ("save", 2026, 7),
        ("replace", 2026, 8),
    ]


# =====================================================================
# Verifies that existing unconfirmed report months are detected before
# any save or replacement mutates Drive state.
# =====================================================================


def test_generate_reports_preflights_existing_months_before_persistence(
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

    july_period = ReportPeriod(
        year=2026,
        month=7,
    )

    august_period = ReportPeriod(
        year=2026,
        month=8,
    )

    july = MonthlyReports(
        period=july_period,
        full_text=None,
        full_json='{"status":"july"}',
        summary_text=None,
        summary_json=None,
        metadata=ReportGenerationMetadata(
            period=july_period,
            generation_id="generation-july",
            generated_at=datetime(
                2026,
                9,
                12,
                18,
                0,
                tzinfo=UTC,
            ),
        ),
    )

    august = MonthlyReports(
        period=august_period,
        full_text=None,
        full_json='{"status":"august"}',
        summary_text=None,
        summary_json=None,
        metadata=ReportGenerationMetadata(
            period=august_period,
            generation_id="generation-august",
            generated_at=datetime(
                2026,
                9,
                12,
                18,
                1,
                tzinfo=UTC,
            ),
        ),
    )

    monkeypatch.setattr(
        AppleHealthApplication,
        "generate_reports",
        lambda self, options: _generation_result(
            reports=(july, august),
        ),
    )

    drive_client = object()

    monkeypatch.setattr(
        api_app_module,
        "HttpGoogleDriveClient",
        lambda access_token: drive_client,
    )

    monkeypatch.setattr(
        api_app_module,
        "find_existing_report_periods",
        lambda received_drive_client, *, reports: {
            "2026-08",
        },
    )

    persistence_calls = []

    monkeypatch.setattr(
        api_app_module,
        "save_new_report_month",
        lambda *args, **kwargs: persistence_calls.append("save"),
    )

    monkeypatch.setattr(
        api_app_module,
        "replace_existing_report_month",
        lambda *args, **kwargs: persistence_calls.append("replace"),
    )

    auth_client = TestClient(app)
    auth_client.cookies.set(
        "ahm_session",
        session_id,
    )

    response = auth_client.post(
        "/reports/generate",
        data={
            "periods": "2026-07,2026-08",
            "full_json": "true",
        },
        files={
            "archive": (
                "export.zip",
                b"fake",
                "application/zip",
            ),
        },
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Report months already exist: 2026-08",
    }
    assert persistence_calls == []


# =====================================================================
# Verifies that confirmed existing months are replaced while new months
# are saved normally within the same multi-month persistence batch.
# =====================================================================


def test_generate_reports_persists_confirmed_and_new_months_together(
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

    july_period = ReportPeriod(
        year=2026,
        month=7,
    )

    august_period = ReportPeriod(
        year=2026,
        month=8,
    )

    july = MonthlyReports(
        period=july_period,
        full_text=None,
        full_json='{"status":"july"}',
        summary_text=None,
        summary_json=None,
        metadata=ReportGenerationMetadata(
            period=july_period,
            generation_id="generation-july",
            generated_at=datetime(
                2026,
                9,
                12,
                18,
                0,
                tzinfo=UTC,
            ),
        ),
    )

    august = MonthlyReports(
        period=august_period,
        full_text=None,
        full_json='{"status":"august"}',
        summary_text=None,
        summary_json=None,
        metadata=ReportGenerationMetadata(
            period=august_period,
            generation_id="generation-august",
            generated_at=datetime(
                2026,
                9,
                12,
                18,
                1,
                tzinfo=UTC,
            ),
        ),
    )

    monkeypatch.setattr(
        AppleHealthApplication,
        "generate_reports",
        lambda self, options: _generation_result(
            reports=(july, august),
        ),
    )

    drive_client = object()

    monkeypatch.setattr(
        api_app_module,
        "HttpGoogleDriveClient",
        lambda access_token: drive_client,
    )

    monkeypatch.setattr(
        api_app_module,
        "find_existing_report_periods",
        lambda received_drive_client, *, reports: {
            "2026-08",
        },
    )

    calls = []

    monkeypatch.setattr(
        api_app_module,
        "save_new_report_month",
        lambda received_drive_client, *, report: calls.append(
            (
                "save",
                report.period.year,
                report.period.month,
            )
        ),
    )

    monkeypatch.setattr(
        api_app_module,
        "replace_existing_report_month",
        lambda received_drive_client, *, report: calls.append(
            (
                "replace",
                report.period.year,
                report.period.month,
            )
        ),
    )

    auth_client = TestClient(app)
    auth_client.cookies.set(
        "ahm_session",
        session_id,
    )

    response = auth_client.post(
        "/reports/generate",
        data={
            "periods": "2026-07,2026-08",
            "full_json": "true",
            "replace_periods": "2026-08",
        },
        files={
            "archive": (
                "export.zip",
                b"fake",
                "application/zip",
            ),
        },
    )

    assert response.status_code == 200
    assert calls == [
        ("save", 2026, 7),
        ("replace", 2026, 8),
    ]


# =====================================================================
# Verifies that report replacement uses the in-page confirmation flow
# and supports automatic replacement when enforcement is enabled.
# =====================================================================


def test_web_interface_confirms_report_replacement() -> None:
    response = client.get("/")

    assert response.status_code == 200

    html = response.text

    assert "window.confirm(" not in html

    assert 'id="replacement-modal"' in html
    assert 'id="replacement-modal-cancel"' in html
    assert 'id="replacement-modal-confirm"' in html
    assert 'class="replacement-cancel"' in html
    assert "OK" in html
    assert "color: var(--text-secondary);" in html
    assert "color: var(--error);" in html

    assert "function confirmReportReplacement(" in html

    assert "enforceReportReplacement.checked" in html

    assert "await confirmReportReplacement(" in html

    assert "await submitGenerationRequest(" in html

    assert '"replace_periods"' in html


# =====================================================================
# Verifies that disabled report autosave skips both persistence preflight
# and all report Drive mutations, even when target months already exist.
# =====================================================================


def test_generate_reports_skips_persistence_when_report_autosave_disabled(
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

    sessions.set_report_autosave_enabled(
        session_id=session_id,
        enabled=False,
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

    period = ReportPeriod(
        year=2026,
        month=8,
    )

    report = MonthlyReports(
        period=period,
        full_text=None,
        full_json='{"status":"new"}',
        summary_text=None,
        summary_json=None,
        metadata=ReportGenerationMetadata(
            period=period,
            generation_id="generation-new",
            generated_at=datetime(
                2026,
                9,
                12,
                18,
                0,
                tzinfo=UTC,
            ),
        ),
    )

    monkeypatch.setattr(
        AppleHealthApplication,
        "generate_reports",
        lambda self, options: _generation_result(
            reports=(report,),
        ),
    )

    calls = []

    monkeypatch.setattr(
        api_app_module,
        "HttpGoogleDriveClient",
        lambda access_token: calls.append("client"),
    )

    monkeypatch.setattr(
        api_app_module,
        "find_existing_report_periods",
        lambda *args, **kwargs: calls.append("preflight"),
    )

    monkeypatch.setattr(
        api_app_module,
        "save_new_report_month",
        lambda *args, **kwargs: calls.append("save"),
    )

    monkeypatch.setattr(
        api_app_module,
        "replace_existing_report_month",
        lambda *args, **kwargs: calls.append("replace"),
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
            "full_json": "true",
        },
        files={
            "archive": (
                "export.zip",
                b"fake",
                "application/zip",
            ),
        },
    )

    assert response.status_code == 200
    assert calls == []


# =====================================================================
# Verifies that report persistence is atomic per month rather than
# across the whole multi-month generation request.
# =====================================================================


def test_generate_reports_allows_partial_multi_month_persistence(
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

    july_period = ReportPeriod(
        year=2026,
        month=7,
    )

    august_period = ReportPeriod(
        year=2026,
        month=8,
    )

    july = MonthlyReports(
        period=july_period,
        full_text=None,
        full_json='{"status":"july"}',
        summary_text=None,
        summary_json=None,
        metadata=ReportGenerationMetadata(
            period=july_period,
            generation_id="generation-july",
            generated_at=datetime(
                2026,
                9,
                12,
                18,
                0,
                tzinfo=UTC,
            ),
        ),
    )

    august = MonthlyReports(
        period=august_period,
        full_text=None,
        full_json='{"status":"august"}',
        summary_text=None,
        summary_json=None,
        metadata=ReportGenerationMetadata(
            period=august_period,
            generation_id="generation-august",
            generated_at=datetime(
                2026,
                9,
                12,
                18,
                1,
                tzinfo=UTC,
            ),
        ),
    )

    monkeypatch.setattr(
        AppleHealthApplication,
        "generate_reports",
        lambda self, options: _generation_result(
            reports=(july, august),
        ),
    )

    drive_client = object()

    monkeypatch.setattr(
        api_app_module,
        "HttpGoogleDriveClient",
        lambda access_token: drive_client,
    )

    monkeypatch.setattr(
        api_app_module,
        "find_existing_report_periods",
        lambda received_drive_client, *, reports: set(),
    )

    calls = []

    def save_report(
        received_drive_client,
        *,
        report,
    ) -> None:
        period = (
            report.period.year,
            report.period.month,
        )

        calls.append(period)

        if period == (2026, 8):
            raise RuntimeError("second month persistence failed")

    monkeypatch.setattr(
        api_app_module,
        "save_new_report_month",
        save_report,
    )

    auth_client = TestClient(app)

    auth_client.cookies.set(
        "ahm_session",
        session_id,
    )

    with pytest.raises(
        RuntimeError,
        match="second month persistence failed",
    ):
        auth_client.post(
            "/reports/generate",
            data={
                "periods": "2026-07,2026-08",
                "full_json": "true",
            },
            files={
                "archive": (
                    "export.zip",
                    b"fake",
                    "application/zip",
                ),
            },
        )

    assert calls == [
        (2026, 7),
        (2026, 8),
    ]


# =====================================================================
# Verifies that the web interface exposes one visible archive-source
# status shared by local upload and Google Drive selection.
# =====================================================================


def test_web_interface_exposes_unified_archive_source_status() -> None:
    response = client.get("/")

    assert response.status_code == 200

    html = response.text

    assert 'id="archive-source-status"' in html
    assert "Local file:" in html
    assert "Google Drive:" in html


# =====================================================================
# Verifies that the web interface exposes one visible configuration
# source status for defaults, saved profiles and uploaded config files.
# =====================================================================


def test_web_interface_exposes_unified_config_source_status() -> None:
    response = client.get("/")

    assert response.status_code == 200

    html = response.text

    assert 'id="config-source-status"' in html
    assert "Application defaults" in html
    assert "Configuration from Google Drive:" in html
    assert "Configuration from this device:" in html
    assert 'id="config-source-clear"' in html
    assert "Select configuration from Google Drive" in html


# =====================================================================
# Verifies that the web interface exposes one generation summary with
# archive source, periods, config source, outputs and persistence state.
# =====================================================================


def test_web_interface_exposes_generation_summary() -> None:
    response = client.get("/")

    assert response.status_code == 200

    html = response.text

    assert 'id="generation-summary"' in html
    assert "Generation summary" in html
    assert "Persistence:" in html
    assert "Outputs:" in html


# =====================================================================
# Verifies that report generation uses one shared request-building and
# submission flow for normal generation and replacement retries.
# =====================================================================


def test_web_interface_uses_unified_generation_request_flow() -> None:
    response = client.get("/")

    assert response.status_code == 200

    html = response.text

    assert "function buildGenerationFormData(" in html
    assert "async function submitGenerationRequest(" in html
    assert "async function readResponseError(" in html
    assert "async function handleSuccessfulGeneration(" in html


# =====================================================================
# Verifies that Drive authorization failures become a controlled
# reconnect response instead of an internal server error.
# =====================================================================


def test_config_profiles_returns_reconnect_response_for_drive_access_failure(
    monkeypatch,
) -> None:
    sessions = SessionStore()
    session_id = sessions.create()

    sessions.set_google_access_credentials(
        session_id=session_id,
        access_token="access-token",
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

    def fail_profile_discovery(
        session,
    ):
        raise DriveAccessError("access denied")

    monkeypatch.setattr(
        api_app_module,
        "discover_config_profiles_for_session",
        fail_profile_discovery,
    )

    recovery_client = TestClient(
        app,
        raise_server_exceptions=False,
    )

    recovery_client.cookies.set(
        "ahm_session",
        session_id,
    )

    response = recovery_client.get(
        "/config/profiles",
    )

    assert response.status_code == 401
    assert response.json() == {
        "detail": "Google reconnect is required.",
    }


# =====================================================================
# Verifies that transient Drive failures become a controlled retryable
# response instead of an internal server error.
# =====================================================================


def test_config_profiles_returns_retryable_response_for_transient_drive_failure(
    monkeypatch,
) -> None:
    sessions = SessionStore()
    session_id = sessions.create()

    sessions.set_google_access_credentials(
        session_id=session_id,
        access_token="access-token",
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

    def fail_profile_discovery(
        session,
    ):
        raise DriveTransientError("temporary failure")

    monkeypatch.setattr(
        api_app_module,
        "discover_config_profiles_for_session",
        fail_profile_discovery,
    )

    recovery_client = TestClient(
        app,
        raise_server_exceptions=False,
    )

    recovery_client.cookies.set(
        "ahm_session",
        session_id,
    )

    response = recovery_client.get(
        "/config/profiles",
    )

    assert response.status_code == 502
    assert response.json() == {
        "detail": ("Google Drive is temporarily unavailable."),
    }


# =====================================================================
# Verifies that the web interface exposes explicit reconnect, retry,
# local ZIP and anonymous recovery actions for Google Drive failures.
# =====================================================================


def test_web_interface_exposes_google_drive_recovery_actions() -> None:
    response = client.get("/")

    assert response.status_code == 200

    html = response.text

    assert 'id="google-recovery"' in html
    assert 'id="google-recovery-reconnect"' in html
    assert 'id="google-recovery-retry"' in html
    assert 'id="google-recovery-local"' in html
    assert 'id="google-recovery-anonymous"' in html

    assert "Reconnect Google" in html
    assert "Retry Google Drive" in html
    assert "Choose local ZIP" in html
    assert "Continue without Google" in html


# =====================================================================
# Verifies that Google recovery copy is user-facing and avoids exposing
# Picker credential or access-token terminology to the user.
# =====================================================================


def test_web_interface_uses_friendly_google_drive_recovery_copy() -> None:
    response = client.get("/")

    assert response.status_code == 200

    html = response.text

    assert "Google needs to be reconnected before Drive " "features can be used." in html

    assert "Google Drive is temporarily unavailable. " "Retry or choose a local ZIP." in html

    assert "Google Picker credentials are unavailable." not in html


# =====================================================================
# Verifies that retry is initiated only by an explicit user action and
# does not create an automatic frontend retry loop.
# =====================================================================


def test_web_interface_uses_manual_google_drive_retry() -> None:
    response = client.get("/")

    assert response.status_code == 200

    html = response.text

    assert "let lastGoogleRetryAction = null;" in html

    assert "async function retryGoogleAction()" in html

    assert "googleRecoveryRetry.addEventListener(" in html

    assert "await retryAction();" in html
    assert "setInterval(" not in html


# =====================================================================
# Verifies that anonymous fallback signs out the local Google-backed
# session so local generation cannot silently keep Drive persistence.
# =====================================================================


def test_web_interface_anonymous_fallback_signs_out_google_session() -> None:
    response = client.get("/")

    assert response.status_code == 200

    html = response.text

    assert "async function continueWithoutGoogle()" in html

    assert '"/auth/sign-out"' in html
    assert 'method: "POST"' in html

    assert "applyAnonymousGoogleState();" in html

    assert "Continuing locally without Google Drive." in html


# =====================================================================
# Verifies that Drive-backed generation failures expose reconnect,
# retry or local-file recovery instead of only surfacing raw API errors.
# =====================================================================


def test_web_interface_recovers_from_drive_generation_failures() -> None:
    response = client.get("/")

    assert response.status_code == 200

    html = response.text

    assert "async function handleGenerationRecovery(" in html

    assert "response.status === 401" in html
    assert "response.status === 502" in html
    assert "response.status === 422" in html

    assert "The selected Google Drive ZIP is no longer " "available." in html


# =====================================================================
# Verifies that temporary uploaded configuration files are deleted after
# successful report generation together with the temporary archive.
# =====================================================================


def test_report_generation_deletes_temporary_config_after_success(
    monkeypatch,
) -> None:
    temporary_config_path = None

    def fake_generate_reports(
        self,
        options,
    ):
        nonlocal temporary_config_path

        temporary_config_path = options.config_path

        assert temporary_config_path is not None
        assert temporary_config_path.exists()

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
                b"[source]\n",
                "application/toml",
            ),
        },
        data={
            "periods": "2026-08",
        },
    )

    assert response.status_code == 200
    assert temporary_config_path is not None
    assert not temporary_config_path.exists()


# =====================================================================
# Verifies that temporary uploaded configuration files are deleted when
# report generation fails.
# =====================================================================


def test_report_generation_deletes_temporary_config_after_failure(
    monkeypatch,
) -> None:
    temporary_config_path = None

    def fake_generate_reports(
        self,
        options,
    ):
        nonlocal temporary_config_path

        temporary_config_path = options.config_path

        assert temporary_config_path is not None
        assert temporary_config_path.exists()

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
            "config": (
                "config.toml",
                b"[source]\n",
                "application/toml",
            ),
        },
        data={
            "periods": "2026-08",
        },
    )

    assert response.status_code == 422
    assert temporary_config_path is not None
    assert not temporary_config_path.exists()


# =====================================================================
# Verifies that user-controlled archive and configuration names are not
# interpolated into generation-summary HTML.
# =====================================================================


def test_web_interface_renders_generation_summary_without_inner_html() -> None:
    response = client.get("/")

    assert response.status_code == 200

    html = response.text

    assert "generationSummary.innerHTML" not in html
    assert "generationSummary.replaceChildren(" in html
    assert "document.createTextNode(line)" in html


# =====================================================================
# Verifies that successful report generation exposes phase timings via
# the standard Server-Timing response header without changing the body.
# =====================================================================


def test_report_generation_exposes_server_timing_header(
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

    server_timing = response.headers["Server-Timing"]

    assert "archive;dur=" in server_timing
    assert "parse;dur=" in server_timing
    assert "reports;dur=" in server_timing
    assert "total;dur=" in server_timing

    assert "drive_verify;dur=" not in server_timing
    assert "drive_wait;dur=" not in server_timing
    assert "drive_body;dur=" not in server_timing
    assert "write;dur=" not in server_timing


# =====================================================================
# Verifies that Drive-backed archive downloads expose measured transfer
# and temporary-file write timings to the report-generation response.
# =====================================================================


def test_download_drive_archive_returns_download_timings(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from connected_health.google.drive import DriveDownloadTimings

    client_timings = DriveDownloadTimings(
        downloaded_bytes=11,
        verification_seconds=0.0,
        response_wait_seconds=5.0,
        body_transfer_seconds=2.5,
        write_seconds=0.3,
    )

    class FakeDriveClient:
        def __init__(
            self,
            access_token: str,
        ) -> None:
            assert access_token == "drive-token"

            self.last_download_timings = client_timings

        def download_file(
            self,
            file_id: str,
            destination: Path,
            max_bytes: int,
        ) -> int:
            assert file_id == "drive-file-id"
            assert max_bytes == MAX_UPLOAD_SIZE

            destination.write_bytes(
                b"hello world",
            )

            return 11

    monkeypatch.setattr(
        api_app_module,
        "verify_drive_archive",
        lambda **kwargs: None,
    )

    monkeypatch.setattr(
        api_app_module,
        "HttpGoogleDriveClient",
        FakeDriveClient,
    )

    verification_clock = iter(
        (
            10.0,
            12.0,
        )
    )

    monkeypatch.setattr(
        api_app_module,
        "perf_counter",
        lambda: next(verification_clock),
    )

    timings = download_drive_archive(
        access_token="drive-token",
        file_id="drive-file-id",
        destination=(tmp_path / "archive.zip"),
    )

    assert timings == DriveDownloadTimings(
        downloaded_bytes=11,
        verification_seconds=2.0,
        response_wait_seconds=5.0,
        body_transfer_seconds=2.5,
        write_seconds=0.3,
    )


# =====================================================================
# Verifies that the web UI distinguishes Drive transfer from local
# parsing and renders backend performance diagnostics after generation.
# =====================================================================


def test_web_interface_exposes_drive_transfer_progress_and_timings() -> None:
    response = client.get("/")

    assert response.status_code == 200

    html = response.text

    assert 'id="technical-diagnostics"' in html

    assert "Technical diagnostics" in html

    assert "function formatPerformanceSummary(" in html

    assert 'response.headers.get("Server-Timing")' in html

    assert "Downloading the Apple Health ZIP " "from Google Drive" in html

    assert 'Drive verify ${timings.get("drive_verify").toFixed(1)}s' in html

    assert 'Drive wait ${timings.get("drive_wait").toFixed(1)}s' in html

    assert 'Drive body ${timings.get("drive_body").toFixed(1)}s' in html

    assert 'temp write ${timings.get("write").toFixed(1)}s' in html

    assert "other backend ${otherSeconds.toFixed(1)}s" in html

    assert "technicalDiagnostics.checked" in html


# =====================================================================
# Verifies that request diagnostics account for local archive copying
# and report persistence outside the core report-generation pipeline.
# =====================================================================


def test_report_generation_server_timing_accounts_for_persistence(
    monkeypatch,
    tmp_path: Path,
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

    monkeypatch.setattr(
        api_app_module,
        "_persist_generated_reports",
        lambda **kwargs: None,
    )

    clock = iter(
        (
            0.0,
            1.0,
            2.0,
            3.0,
            8.0,
            10.0,
        )
    )

    monkeypatch.setattr(
        api_app_module,
        "perf_counter",
        lambda: next(clock),
    )

    archive_path = _create_export_archive(tmp_path)

    auth_client = TestClient(app)
    auth_client.cookies.set(
        "ahm_session",
        session_id,
    )

    with archive_path.open("rb") as archive:
        response = auth_client.post(
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

    server_timing = response.headers["Server-Timing"]

    assert "local_copy;dur=1000.0" in server_timing
    assert "report_save;dur=5000.0" in server_timing
    assert "total;dur=10000.0" in server_timing


# =====================================================================
# Verifies that technical diagnostics are presented as a toggle switch
# below the GitHub link in the header utility controls.
# =====================================================================


def test_web_interface_places_diagnostics_toggle_below_github_link() -> None:
    response = client.get("/")

    assert response.status_code == 200

    html = response.text

    github_position = html.index("View on GitHub")
    diagnostics_position = html.index("Technical diagnostics")

    assert github_position < diagnostics_position
    assert 'class="diagnostics-switch"' in html
    assert 'id="technical-diagnostics"' in html
