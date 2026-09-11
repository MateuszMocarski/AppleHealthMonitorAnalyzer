from datetime import datetime, timezone

import pytest

from apple_health.application.monthly_reports import MonthlyReports
from apple_health.application.report_generation_metadata import (
    ReportGenerationMetadata,
)
from apple_health.application.report_period import ReportPeriod
from apple_health.google.drive import DriveConflictError, DriveFileMetadata
from apple_health.google.report_persistence import (
    mark_generation_current,
    save_new_report_month,
    upload_report_artifacts,
    verify_report_artifacts,
)

# =====================================================================
# Verifies that report persistence uploads only generated artifacts
# with canonical generation metadata into the report month folder.
# =====================================================================


def test_upload_report_artifacts_uploads_only_generated_outputs() -> None:
    uploads = []

    period = ReportPeriod(
        year=2026,
        month=8,
    )

    report = MonthlyReports(
        period=period,
        full_text=None,
        full_json='{"status":"ok"}',
        summary_text="summary",
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
                tzinfo=timezone.utc,
            ),
        ),
    )

    class FakeDriveClient:
        def upload_file(
            self,
            name,
            content,
            mime_type,
            parent_id=None,
            app_properties=None,
        ):
            uploads.append(
                {
                    "name": name,
                    "content": content,
                    "mime_type": mime_type,
                    "parent_id": parent_id,
                    "app_properties": app_properties,
                }
            )

            return DriveFileMetadata(
                file_id=f"file-{name}",
                name=name,
                mime_type=mime_type,
                size_bytes=len(content),
                trashed=False,
                app_properties=app_properties or {},
            )

    uploaded = upload_report_artifacts(
        FakeDriveClient(),
        month_id="month-2026-08",
        report=report,
    )

    assert tuple(file.name for file in uploaded) == (
        "full.json",
        "summary.txt",
    )

    assert uploads == [
        {
            "name": "full.json",
            "content": b'{"status":"ok"}',
            "mime_type": "application/json",
            "parent_id": "month-2026-08",
            "app_properties": {
                "ahm_type": "report_artifact",
                "ahm_period": "2026-08",
                "ahm_generation_id": "generation-123",
                "ahm_generated_at": "2026-09-11T16:30:00Z",
            },
        },
        {
            "name": "summary.txt",
            "content": b"summary",
            "mime_type": "text/plain",
            "parent_id": "month-2026-08",
            "app_properties": {
                "ahm_type": "report_artifact",
                "ahm_period": "2026-08",
                "ahm_generation_id": "generation-123",
                "ahm_generated_at": "2026-09-11T16:30:00Z",
            },
        },
    ]


# =====================================================================
# Verifies that uploaded report artifacts are re-read from Drive and
# validated against the expected generation metadata and content size.
# =====================================================================


def test_verify_report_artifacts_accepts_complete_uploaded_generation() -> None:
    period = ReportPeriod(
        year=2026,
        month=8,
    )

    report = MonthlyReports(
        period=period,
        full_text=None,
        full_json='{"status":"ok"}',
        summary_text="summary",
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
                tzinfo=timezone.utc,
            ),
        ),
    )

    uploaded = (
        DriveFileMetadata(
            file_id="full-json-id",
            name="full.json",
            mime_type="application/json",
            size_bytes=len(b'{"status":"ok"}'),
            trashed=False,
            app_properties=report.metadata.artifact_app_properties(),
        ),
        DriveFileMetadata(
            file_id="summary-text-id",
            name="summary.txt",
            mime_type="text/plain",
            size_bytes=len(b"summary"),
            trashed=False,
            app_properties=report.metadata.artifact_app_properties(),
        ),
    )

    metadata_by_id = {file.file_id: file for file in uploaded}

    class FakeDriveClient:
        def get_metadata(
            self,
            file_id: str,
        ) -> DriveFileMetadata:
            return metadata_by_id[file_id]

    verify_report_artifacts(
        FakeDriveClient(),
        report=report,
        uploaded=uploaded,
    )


# =====================================================================
# Verifies that a verified monthly generation becomes current by
# storing its generation id on the report month metadata.
# =====================================================================


def test_mark_generation_current_updates_month_pointer() -> None:
    updates = []

    class FakeDriveClient:
        def update_metadata(
            self,
            file_id: str,
            *,
            name: str | None = None,
            app_properties=None,
        ) -> DriveFileMetadata:
            updates.append(
                {
                    "file_id": file_id,
                    "name": name,
                    "app_properties": app_properties,
                }
            )

            return DriveFileMetadata(
                file_id=file_id,
                name="2026-08",
                mime_type="application/vnd.google-apps.folder",
                size_bytes=None,
                trashed=False,
                app_properties=app_properties or {},
            )

    mark_generation_current(
        FakeDriveClient(),
        month_id="month-2026-08",
        period="2026-08",
        generation_id="generation-123",
    )

    assert updates == [
        {
            "file_id": "month-2026-08",
            "name": None,
            "app_properties": {
                "ahm_type": "report_month",
                "ahm_period": "2026-08",
                "ahm_current_generation_id": "generation-123",
            },
        }
    ]


# =====================================================================
# Verifies that saving a new report month creates the required Drive
# structure, uploads and verifies artifacts, then marks them current.
# =====================================================================


def test_save_new_report_month_commits_only_after_verification(
    monkeypatch,
) -> None:
    period = ReportPeriod(
        year=2026,
        month=8,
    )

    report = MonthlyReports(
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
                tzinfo=timezone.utc,
            ),
        ),
    )

    calls = []

    root = DriveFileMetadata(
        file_id="root-id",
        name="Apple Health Monitor",
        mime_type="application/vnd.google-apps.folder",
        size_bytes=None,
        trashed=False,
        app_properties={},
    )
    reports = DriveFileMetadata(
        file_id="reports-id",
        name="reports",
        mime_type="application/vnd.google-apps.folder",
        size_bytes=None,
        trashed=False,
        app_properties={},
    )
    year_folder = DriveFileMetadata(
        file_id="year-id",
        name="2026",
        mime_type="application/vnd.google-apps.folder",
        size_bytes=None,
        trashed=False,
        app_properties={},
    )
    month = DriveFileMetadata(
        file_id="month-id",
        name="2026-08",
        mime_type="application/vnd.google-apps.folder",
        size_bytes=None,
        trashed=False,
        app_properties={},
    )
    uploaded = (
        DriveFileMetadata(
            file_id="full-json-id",
            name="full.json",
            mime_type="application/json",
            size_bytes=len(b'{"status":"ok"}'),
            trashed=False,
            app_properties=report.metadata.artifact_app_properties(),
        ),
    )
    monkeypatch.setattr(
        "apple_health.google.report_persistence.ensure_ahm_root",
        lambda drive_client: (
            calls.append("ensure_root"),
            root,
        )[1],
    )

    monkeypatch.setattr(
        "apple_health.google.report_persistence.ensure_reports_container",
        lambda drive_client, *, root_id: (
            calls.append(("ensure_reports", root_id)),
            reports,
        )[1],
    )
    monkeypatch.setattr(
        "apple_health.google.report_persistence.ensure_year_container",
        lambda drive_client, *, reports_id, year: (
            calls.append(("ensure_year", reports_id, year)),
            year_folder,
        )[1],
    )
    monkeypatch.setattr(
        "apple_health.google.report_persistence.discover_report_month",
        lambda drive_client, *, year_id, period: None,
    )
    monkeypatch.setattr(
        "apple_health.google.report_persistence.ensure_report_month",
        lambda drive_client, *, year_id, period: (
            calls.append(("ensure_month", year_id, period)),
            month,
        )[1],
    )
    monkeypatch.setattr(
        "apple_health.google.report_persistence.upload_report_artifacts",
        lambda drive_client, *, month_id, report: (
            calls.append(("upload", month_id)),
            uploaded,
        )[1],
    )

    def fake_verify(
        drive_client,
        *,
        report,
        uploaded,
    ) -> None:
        calls.append(
            (
                "verify",
                tuple(file.file_id for file in uploaded),
            )
        )

    monkeypatch.setattr(
        "apple_health.google.report_persistence.verify_report_artifacts",
        fake_verify,
    )

    def fake_mark_current(
        drive_client,
        *,
        month_id,
        period,
        generation_id,
    ) -> DriveFileMetadata:
        calls.append(
            (
                "mark_current",
                month_id,
                period,
                generation_id,
            )
        )

        return month

    monkeypatch.setattr(
        "apple_health.google.report_persistence.mark_generation_current",
        fake_mark_current,
    )

    saved = save_new_report_month(
        object(),
        report=report,
    )

    assert saved == month
    assert calls == [
        "ensure_root",
        ("ensure_reports", "root-id"),
        ("ensure_year", "reports-id", 2026),
        ("ensure_month", "year-id", "2026-08"),
        ("upload", "month-id"),
        ("verify", ("full-json-id",)),
        (
            "mark_current",
            "month-id",
            "2026-08",
            "generation-123",
        ),
    ]


# =====================================================================
# Verifies that saving a new report month refuses to overwrite an
# already existing managed report month.
# =====================================================================


def test_save_new_report_month_rejects_existing_month(
    monkeypatch,
) -> None:
    period = ReportPeriod(
        year=2026,
        month=8,
    )

    report = MonthlyReports(
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
                tzinfo=timezone.utc,
            ),
        ),
    )

    root = DriveFileMetadata(
        file_id="root-id",
        name="Apple Health Monitor",
        mime_type="application/vnd.google-apps.folder",
        size_bytes=None,
        trashed=False,
        app_properties={},
    )
    reports = DriveFileMetadata(
        file_id="reports-id",
        name="reports",
        mime_type="application/vnd.google-apps.folder",
        size_bytes=None,
        trashed=False,
        app_properties={},
    )
    year_folder = DriveFileMetadata(
        file_id="year-id",
        name="2026",
        mime_type="application/vnd.google-apps.folder",
        size_bytes=None,
        trashed=False,
        app_properties={},
    )
    existing_month = DriveFileMetadata(
        file_id="month-id",
        name="2026-08",
        mime_type="application/vnd.google-apps.folder",
        size_bytes=None,
        trashed=False,
        app_properties={
            "ahm_type": "report_month",
            "ahm_period": "2026-08",
        },
    )

    monkeypatch.setattr(
        "apple_health.google.report_persistence.ensure_ahm_root",
        lambda drive_client: root,
    )
    monkeypatch.setattr(
        "apple_health.google.report_persistence.ensure_reports_container",
        lambda drive_client, *, root_id: reports,
    )
    monkeypatch.setattr(
        "apple_health.google.report_persistence.ensure_year_container",
        lambda drive_client, *, reports_id, year: year_folder,
    )
    monkeypatch.setattr(
        "apple_health.google.report_persistence.discover_report_month",
        lambda drive_client, *, year_id, period: existing_month,
    )

    with pytest.raises(
        DriveConflictError,
        match="Report month already exists",
    ):
        save_new_report_month(
            object(),
            report=report,
        )


# =====================================================================
# Verifies that a failed artifact verification prevents the new
# generation from being marked as current.
# =====================================================================


def test_save_new_report_month_does_not_commit_when_verification_fails(
    monkeypatch,
) -> None:
    period = ReportPeriod(
        year=2026,
        month=8,
    )

    report = MonthlyReports(
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
                tzinfo=timezone.utc,
            ),
        ),
    )

    root = DriveFileMetadata(
        file_id="root-id",
        name="Apple Health Monitor",
        mime_type="application/vnd.google-apps.folder",
        size_bytes=None,
        trashed=False,
        app_properties={},
    )
    reports = DriveFileMetadata(
        file_id="reports-id",
        name="reports",
        mime_type="application/vnd.google-apps.folder",
        size_bytes=None,
        trashed=False,
        app_properties={},
    )
    year_folder = DriveFileMetadata(
        file_id="year-id",
        name="2026",
        mime_type="application/vnd.google-apps.folder",
        size_bytes=None,
        trashed=False,
        app_properties={},
    )
    month = DriveFileMetadata(
        file_id="month-id",
        name="2026-08",
        mime_type="application/vnd.google-apps.folder",
        size_bytes=None,
        trashed=False,
        app_properties={},
    )
    uploaded = (
        DriveFileMetadata(
            file_id="full-json-id",
            name="full.json",
            mime_type="application/json",
            size_bytes=len(b'{"status":"ok"}'),
            trashed=False,
            app_properties=report.metadata.artifact_app_properties(),
        ),
    )

    monkeypatch.setattr(
        "apple_health.google.report_persistence.ensure_ahm_root",
        lambda drive_client: root,
    )
    monkeypatch.setattr(
        "apple_health.google.report_persistence.ensure_reports_container",
        lambda drive_client, *, root_id: reports,
    )
    monkeypatch.setattr(
        "apple_health.google.report_persistence.ensure_year_container",
        lambda drive_client, *, reports_id, year: year_folder,
    )
    monkeypatch.setattr(
        "apple_health.google.report_persistence.discover_report_month",
        lambda drive_client, *, year_id, period: None,
    )
    monkeypatch.setattr(
        "apple_health.google.report_persistence.ensure_report_month",
        lambda drive_client, *, year_id, period: month,
    )
    monkeypatch.setattr(
        "apple_health.google.report_persistence.upload_report_artifacts",
        lambda drive_client, *, month_id, report: uploaded,
    )

    def fail_verification(
        drive_client,
        *,
        report,
        uploaded,
    ) -> None:
        raise ValueError("Uploaded report artifact metadata does not match.")

    monkeypatch.setattr(
        "apple_health.google.report_persistence.verify_report_artifacts",
        fail_verification,
    )

    commit_calls = []

    monkeypatch.setattr(
        "apple_health.google.report_persistence.mark_generation_current",
        lambda *args, **kwargs: commit_calls.append(
            (
                args,
                kwargs,
            )
        ),
    )

    with pytest.raises(
        ValueError,
        match="metadata does not match",
    ):
        save_new_report_month(
            object(),
            report=report,
        )

    assert commit_calls == []
