from datetime import datetime, timezone

import pytest

from apple_health.application.monthly_reports import MonthlyReports
from apple_health.application.report_generation_metadata import (
    ReportGenerationMetadata,
)
from apple_health.application.report_period import ReportPeriod
from apple_health.google.current_report_generation import CurrentReportGeneration
from apple_health.google.drive import DriveConflictError, DriveFileMetadata, DriveFilePage
from apple_health.google.report_persistence import (
    archive_previous_generation,
    cleanup_staging_generation,
    commit_staged_generation,
    create_report_staging_folder,
    ensure_report_archive_container,
    mark_generation_current,
    prepare_staged_generation_activation,
    replace_report_month,
    save_new_report_month,
    stage_report_generation,
    upload_report_artifacts,
    verify_report_artifacts,
    verify_staged_generation,
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


# =====================================================================
# Verifies that report replacement creates an isolated staging folder
# for the new generation inside the existing report month.
# =====================================================================


def test_create_report_staging_folder_uses_generation_identity() -> None:
    created = []

    class FakeDriveClient:
        def create_folder(
            self,
            name: str,
            parent_id: str | None = None,
            app_properties=None,
        ) -> DriveFileMetadata:
            created.append(
                {
                    "name": name,
                    "parent_id": parent_id,
                    "app_properties": app_properties,
                }
            )

            return DriveFileMetadata(
                file_id="staging-id",
                name=name,
                mime_type="application/vnd.google-apps.folder",
                size_bytes=None,
                trashed=False,
                app_properties=app_properties or {},
            )

    staging = create_report_staging_folder(
        FakeDriveClient(),
        month_id="month-id",
        period="2026-08",
        generation_id="generation-new",
    )

    assert staging.file_id == "staging-id"
    assert created == [
        {
            "name": "staging-generation-new",
            "parent_id": "month-id",
            "app_properties": {
                "ahm_type": "report_staging",
                "ahm_period": "2026-08",
                "ahm_generation_id": "generation-new",
            },
        }
    ]


# =====================================================================
# Verifies that replacement artifacts are uploaded into an isolated
# staging folder rather than directly into the report month.
# =====================================================================


def test_stage_report_generation_uploads_artifacts_into_staging(
    monkeypatch,
) -> None:
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
                17,
                30,
                tzinfo=timezone.utc,
            ),
        ),
    )

    staging = DriveFileMetadata(
        file_id="staging-id",
        name="staging-generation-new",
        mime_type="application/vnd.google-apps.folder",
        size_bytes=None,
        trashed=False,
        app_properties={
            "ahm_type": "report_staging",
            "ahm_period": "2026-08",
            "ahm_generation_id": "generation-new",
        },
    )

    uploaded = (
        DriveFileMetadata(
            file_id="new-full-json",
            name="full.json",
            mime_type="application/json",
            size_bytes=len(b'{"status":"new"}'),
            trashed=False,
            app_properties=report.metadata.artifact_app_properties(),
        ),
    )

    calls = []

    monkeypatch.setattr(
        "apple_health.google.report_persistence.create_report_staging_folder",
        lambda drive_client, *, month_id, period, generation_id: (
            calls.append(
                (
                    "create_staging",
                    month_id,
                    period,
                    generation_id,
                )
            ),
            staging,
        )[1],
    )

    monkeypatch.setattr(
        "apple_health.google.report_persistence.upload_report_artifacts",
        lambda drive_client, *, month_id, report: (
            calls.append(
                (
                    "upload",
                    month_id,
                )
            ),
            uploaded,
        )[1],
    )

    staged_folder, staged_artifacts = stage_report_generation(
        object(),
        month_id="month-id",
        report=report,
    )

    assert staged_folder == staging
    assert staged_artifacts == uploaded

    assert calls == [
        (
            "create_staging",
            "month-id",
            "2026-08",
            "generation-new",
        ),
        (
            "upload",
            "staging-id",
        ),
    ]


# =====================================================================
# Verifies that a staged report generation is fully verified before
# any activation step can proceed.
# =====================================================================


def test_verify_staged_generation_validates_uploaded_artifacts(
    monkeypatch,
) -> None:
    period = ReportPeriod(
        year=2026,
        month=8,
    )

    report = MonthlyReports(
        period=period,
        full_text=None,
        full_json='{"status":"new"}',
        summary_text="summary",
        summary_json=None,
        metadata=ReportGenerationMetadata(
            period=period,
            generation_id="generation-new",
            generated_at=datetime(
                2026,
                9,
                12,
                17,
                30,
                tzinfo=timezone.utc,
            ),
        ),
    )

    uploaded = (
        DriveFileMetadata(
            file_id="new-full-json",
            name="full.json",
            mime_type="application/json",
            size_bytes=len(b'{"status":"new"}'),
            trashed=False,
            app_properties=report.metadata.artifact_app_properties(),
        ),
        DriveFileMetadata(
            file_id="new-summary-text",
            name="summary.txt",
            mime_type="text/plain",
            size_bytes=len(b"summary"),
            trashed=False,
            app_properties=report.metadata.artifact_app_properties(),
        ),
    )

    calls = []

    def fake_verify(
        drive_client,
        *,
        report,
        uploaded,
    ) -> None:
        calls.append(tuple(file.file_id for file in uploaded))

    monkeypatch.setattr(
        "apple_health.google.report_persistence.verify_report_artifacts",
        fake_verify,
    )

    verify_staged_generation(
        object(),
        report=report,
        uploaded=uploaded,
    )

    assert calls == [
        (
            "new-full-json",
            "new-summary-text",
        ),
    ]


# =====================================================================
# Verifies that a verified staged generation is prepared for activation
# by moving its artifacts into the report month without changing current.
# =====================================================================


def test_prepare_staged_generation_activation_moves_artifacts_to_month() -> None:
    staged = (
        DriveFileMetadata(
            file_id="new-full-json",
            name="full.json",
            mime_type="application/json",
            size_bytes=100,
            trashed=False,
            app_properties={
                "ahm_type": "report_artifact",
                "ahm_period": "2026-08",
                "ahm_generation_id": "generation-new",
            },
        ),
        DriveFileMetadata(
            file_id="new-summary-text",
            name="summary.txt",
            mime_type="text/plain",
            size_bytes=50,
            trashed=False,
            app_properties={
                "ahm_type": "report_artifact",
                "ahm_period": "2026-08",
                "ahm_generation_id": "generation-new",
            },
        ),
    )

    moves = []

    class FakeDriveClient:
        def move(
            self,
            file_id: str,
            *,
            add_parent_id: str,
            remove_parent_id: str,
        ) -> DriveFileMetadata:
            moves.append(
                (
                    file_id,
                    add_parent_id,
                    remove_parent_id,
                )
            )

            return next(artifact for artifact in staged if artifact.file_id == file_id)

    moved = prepare_staged_generation_activation(
        FakeDriveClient(),
        month_id="month-id",
        staging_id="staging-id",
        artifacts=staged,
    )

    assert moved == staged
    assert moves == [
        (
            "new-full-json",
            "month-id",
            "staging-id",
        ),
        (
            "new-summary-text",
            "month-id",
            "staging-id",
        ),
    ]


# =====================================================================
# Verifies that committing a prepared generation performs the single
# current-generation pointer switch to the new generation.
# =====================================================================


def test_commit_staged_generation_switches_current_pointer(
    monkeypatch,
) -> None:
    calls = []

    month = DriveFileMetadata(
        file_id="month-id",
        name="2026-08",
        mime_type="application/vnd.google-apps.folder",
        size_bytes=None,
        trashed=False,
        app_properties={
            "ahm_type": "report_month",
            "ahm_period": "2026-08",
            "ahm_current_generation_id": "generation-new",
        },
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

    committed = commit_staged_generation(
        object(),
        month_id="month-id",
        period="2026-08",
        generation_id="generation-new",
    )

    assert committed == month
    assert calls == [
        (
            "month-id",
            "2026-08",
            "generation-new",
        ),
    ]


# =====================================================================
# Verifies that report replacement reuses or creates the archive
# container directly under the report month.
# =====================================================================


def test_ensure_report_archive_container_creates_missing_archive() -> None:
    calls = []

    class FakeDriveClient:
        def list_children(
            self,
            parent_id: str,
            page_token: str | None = None,
        ) -> DriveFilePage:
            calls.append(
                (
                    "list",
                    parent_id,
                    page_token,
                )
            )

            return DriveFilePage(
                files=(),
                next_page_token=None,
            )

        def create_folder(
            self,
            name: str,
            parent_id: str | None = None,
            app_properties=None,
        ) -> DriveFileMetadata:
            calls.append(
                (
                    "create",
                    name,
                    parent_id,
                )
            )

            return DriveFileMetadata(
                file_id="archive-id",
                name=name,
                mime_type="application/vnd.google-apps.folder",
                size_bytes=None,
                trashed=False,
                app_properties={},
            )

    archive = ensure_report_archive_container(
        FakeDriveClient(),
        month_id="month-id",
    )

    assert archive.file_id == "archive-id"
    assert calls == [
        (
            "list",
            "month-id",
            None,
        ),
        (
            "create",
            "archive",
            "month-id",
        ),
    ]


# =====================================================================
# Verifies that the previous generation is moved into one timestamped
# archive folder derived from its original generation timestamp.
# =====================================================================


def test_archive_previous_generation_moves_old_artifacts_into_timestamp_folder(
    monkeypatch,
) -> None:
    old_artifacts = (
        DriveFileMetadata(
            file_id="old-full-json",
            name="full.json",
            mime_type="application/json",
            size_bytes=100,
            trashed=False,
            app_properties={
                "ahm_type": "report_artifact",
                "ahm_period": "2026-08",
                "ahm_generation_id": "generation-old",
                "ahm_generated_at": "2026-09-01T18:42:15Z",
            },
        ),
        DriveFileMetadata(
            file_id="old-full-text",
            name="full.txt",
            mime_type="text/plain",
            size_bytes=50,
            trashed=False,
            app_properties={
                "ahm_type": "report_artifact",
                "ahm_period": "2026-08",
                "ahm_generation_id": "generation-old",
                "ahm_generated_at": "2026-09-01T18:42:15Z",
            },
        ),
    )

    archive = DriveFileMetadata(
        file_id="archive-id",
        name="archive",
        mime_type="application/vnd.google-apps.folder",
        size_bytes=None,
        trashed=False,
        app_properties={},
    )

    archive_generation = DriveFileMetadata(
        file_id="archive-generation-id",
        name="2026-09-01T18-42-15Z",
        mime_type="application/vnd.google-apps.folder",
        size_bytes=None,
        trashed=False,
        app_properties={},
    )

    calls = []

    monkeypatch.setattr(
        "apple_health.google.report_persistence.ensure_report_archive_container",
        lambda drive_client, *, month_id: archive,
    )

    class FakeDriveClient:
        def create_folder(
            self,
            name: str,
            parent_id: str | None = None,
            app_properties=None,
        ) -> DriveFileMetadata:
            calls.append(
                (
                    "create_folder",
                    name,
                    parent_id,
                )
            )

            return archive_generation

        def move(
            self,
            file_id: str,
            *,
            add_parent_id: str,
            remove_parent_id: str,
        ) -> DriveFileMetadata:
            calls.append(
                (
                    "move",
                    file_id,
                    add_parent_id,
                    remove_parent_id,
                )
            )

            return next(artifact for artifact in old_artifacts if artifact.file_id == file_id)

    archived = archive_previous_generation(
        FakeDriveClient(),
        month_id="month-id",
        artifacts=old_artifacts,
    )

    assert archived == old_artifacts
    assert calls == [
        (
            "create_folder",
            "2026-09-01T18-42-15Z",
            "archive-id",
        ),
        (
            "move",
            "old-full-json",
            "archive-generation-id",
            "month-id",
        ),
        (
            "move",
            "old-full-text",
            "archive-generation-id",
            "month-id",
        ),
    ]


# =====================================================================
# Verifies that replacing an existing report month stages and verifies
# the new generation before switching current and archiving the old one.
# =====================================================================


def test_replace_report_month_uses_safe_commit_order(
    monkeypatch,
) -> None:
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
                17,
                30,
                tzinfo=timezone.utc,
            ),
        ),
    )

    month = DriveFileMetadata(
        file_id="month-id",
        name="2026-08",
        mime_type="application/vnd.google-apps.folder",
        size_bytes=None,
        trashed=False,
        app_properties={
            "ahm_type": "report_month",
            "ahm_period": "2026-08",
            "ahm_current_generation_id": "generation-old",
        },
    )

    old_artifacts = (
        DriveFileMetadata(
            file_id="old-full-json",
            name="full.json",
            mime_type="application/json",
            size_bytes=100,
            trashed=False,
            app_properties={
                "ahm_type": "report_artifact",
                "ahm_period": "2026-08",
                "ahm_generation_id": "generation-old",
                "ahm_generated_at": "2026-09-01T18:42:15Z",
            },
        ),
    )

    staging = DriveFileMetadata(
        file_id="staging-id",
        name="staging-generation-new",
        mime_type="application/vnd.google-apps.folder",
        size_bytes=None,
        trashed=False,
        app_properties={
            "ahm_type": "report_staging",
            "ahm_period": "2026-08",
            "ahm_generation_id": "generation-new",
        },
    )

    uploaded = (
        DriveFileMetadata(
            file_id="new-full-json",
            name="full.json",
            mime_type="application/json",
            size_bytes=len(b'{"status":"new"}'),
            trashed=False,
            app_properties=report.metadata.artifact_app_properties(),
        ),
    )

    calls = []

    monkeypatch.setattr(
        "apple_health.google.report_persistence.discover_current_generation",
        lambda drive_client, *, month: (
            calls.append("discover_old"),
            CurrentReportGeneration(
                period="2026-08",
                generation_id="generation-old",
                artifacts=old_artifacts,
            ),
        )[1],
    )

    monkeypatch.setattr(
        "apple_health.google.report_persistence.stage_report_generation",
        lambda drive_client, *, month_id, report: (
            calls.append("stage"),
            (staging, uploaded),
        )[1],
    )

    monkeypatch.setattr(
        "apple_health.google.report_persistence.verify_staged_generation",
        lambda drive_client, *, report, uploaded: calls.append("verify"),
    )

    monkeypatch.setattr(
        "apple_health.google.report_persistence.prepare_staged_generation_activation",
        lambda drive_client, *, month_id, staging_id, artifacts: (
            calls.append("prepare"),
            artifacts,
        )[1],
    )

    monkeypatch.setattr(
        "apple_health.google.report_persistence.commit_staged_generation",
        lambda drive_client, *, month_id, period, generation_id: (
            calls.append("commit"),
            month,
        )[1],
    )

    monkeypatch.setattr(
        "apple_health.google.report_persistence.archive_previous_generation",
        lambda drive_client, *, month_id, artifacts: (
            calls.append("archive_old"),
            artifacts,
        )[1],
    )

    replace_report_month(
        object(),
        month=month,
        report=report,
    )

    assert calls == [
        "discover_old",
        "stage",
        "verify",
        "prepare",
        "commit",
        "archive_old",
    ]


# =====================================================================
# Verifies that verification failure aborts replacement before the
# current-generation pointer switch and before archiving the old one.
# =====================================================================


def test_replace_report_month_does_not_commit_or_archive_when_verify_fails(
    monkeypatch,
) -> None:
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
                17,
                30,
                tzinfo=timezone.utc,
            ),
        ),
    )

    month = DriveFileMetadata(
        file_id="month-id",
        name="2026-08",
        mime_type="application/vnd.google-apps.folder",
        size_bytes=None,
        trashed=False,
        app_properties={
            "ahm_type": "report_month",
            "ahm_period": "2026-08",
            "ahm_current_generation_id": "generation-old",
        },
    )

    current = CurrentReportGeneration(
        period="2026-08",
        generation_id="generation-old",
        artifacts=(),
    )

    staging = DriveFileMetadata(
        file_id="staging-id",
        name="staging-generation-new",
        mime_type="application/vnd.google-apps.folder",
        size_bytes=None,
        trashed=False,
        app_properties={
            "ahm_type": "report_staging",
            "ahm_period": "2026-08",
            "ahm_generation_id": "generation-new",
        },
    )

    uploaded = (
        DriveFileMetadata(
            file_id="new-full-json",
            name="full.json",
            mime_type="application/json",
            size_bytes=len(b'{"status":"new"}'),
            trashed=False,
            app_properties=report.metadata.artifact_app_properties(),
        ),
    )

    calls = []

    monkeypatch.setattr(
        "apple_health.google.report_persistence.discover_current_generation",
        lambda drive_client, *, month: current,
    )

    monkeypatch.setattr(
        "apple_health.google.report_persistence.stage_report_generation",
        lambda drive_client, *, month_id, report: (
            staging,
            uploaded,
        ),
    )

    def fail_verify(
        drive_client,
        *,
        report,
        uploaded,
    ) -> None:
        calls.append("verify")
        raise ValueError("verification failed")

    monkeypatch.setattr(
        "apple_health.google.report_persistence.verify_staged_generation",
        fail_verify,
    )

    monkeypatch.setattr(
        "apple_health.google.report_persistence.commit_staged_generation",
        lambda *args, **kwargs: calls.append("commit"),
    )

    monkeypatch.setattr(
        "apple_health.google.report_persistence.archive_previous_generation",
        lambda *args, **kwargs: calls.append("archive"),
    )

    with pytest.raises(
        ValueError,
        match="verification failed",
    ):
        replace_report_month(
            object(),
            month=month,
            report=report,
        )

    assert calls == [
        "verify",
    ]


# =====================================================================
# Verifies that orphan staging data is cleaned up by trashing the
# staging folder after a replacement fails before commit.
# =====================================================================


def test_cleanup_staging_generation_trashes_staging_folder() -> None:
    calls = []

    class FakeDriveClient:
        def trash(
            self,
            file_id: str,
        ) -> DriveFileMetadata:
            calls.append(file_id)

            return DriveFileMetadata(
                file_id=file_id,
                name="staging-generation-new",
                mime_type="application/vnd.google-apps.folder",
                size_bytes=None,
                trashed=True,
                app_properties={
                    "ahm_type": "report_staging",
                    "ahm_period": "2026-08",
                    "ahm_generation_id": "generation-new",
                },
            )

    cleaned = cleanup_staging_generation(
        FakeDriveClient(),
        staging_id="staging-id",
    )

    assert cleaned.trashed is True
    assert calls == [
        "staging-id",
    ]


# =====================================================================
# Verifies that prepare failure keeps the old generation current and
# cleans staging without committing or archiving the old generation.
# =====================================================================


def test_replace_report_month_cleans_staging_when_prepare_fails(
    monkeypatch,
) -> None:
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
                17,
                30,
                tzinfo=timezone.utc,
            ),
        ),
    )

    month = DriveFileMetadata(
        file_id="month-id",
        name="2026-08",
        mime_type="application/vnd.google-apps.folder",
        size_bytes=None,
        trashed=False,
        app_properties={
            "ahm_type": "report_month",
            "ahm_period": "2026-08",
            "ahm_current_generation_id": "generation-old",
        },
    )

    current = CurrentReportGeneration(
        period="2026-08",
        generation_id="generation-old",
        artifacts=(),
    )

    staging = DriveFileMetadata(
        file_id="staging-id",
        name="staging-generation-new",
        mime_type="application/vnd.google-apps.folder",
        size_bytes=None,
        trashed=False,
        app_properties={
            "ahm_type": "report_staging",
            "ahm_period": "2026-08",
            "ahm_generation_id": "generation-new",
        },
    )

    uploaded = (
        DriveFileMetadata(
            file_id="new-full-json",
            name="full.json",
            mime_type="application/json",
            size_bytes=len(b'{"status":"new"}'),
            trashed=False,
            app_properties=report.metadata.artifact_app_properties(),
        ),
    )

    calls = []

    monkeypatch.setattr(
        "apple_health.google.report_persistence.discover_current_generation",
        lambda drive_client, *, month: current,
    )

    monkeypatch.setattr(
        "apple_health.google.report_persistence.stage_report_generation",
        lambda drive_client, *, month_id, report: (
            staging,
            uploaded,
        ),
    )

    monkeypatch.setattr(
        "apple_health.google.report_persistence.verify_staged_generation",
        lambda drive_client, *, report, uploaded: None,
    )

    def fail_prepare(
        drive_client,
        *,
        month_id,
        staging_id,
        artifacts,
    ):
        calls.append("prepare")
        raise RuntimeError("prepare failed")

    monkeypatch.setattr(
        "apple_health.google.report_persistence.prepare_staged_generation_activation",
        fail_prepare,
    )

    monkeypatch.setattr(
        "apple_health.google.report_persistence.cleanup_staging_generation",
        lambda drive_client, *, staging_id: calls.append("cleanup"),
    )

    monkeypatch.setattr(
        "apple_health.google.report_persistence.commit_staged_generation",
        lambda *args, **kwargs: calls.append("commit"),
    )

    monkeypatch.setattr(
        "apple_health.google.report_persistence.archive_previous_generation",
        lambda *args, **kwargs: calls.append("archive"),
    )

    with pytest.raises(
        RuntimeError,
        match="prepare failed",
    ):
        replace_report_month(
            object(),
            month=month,
            report=report,
        )

    assert calls == [
        "prepare",
        "cleanup",
    ]


# =====================================================================
# Verifies that archive failure after commit does not turn a successful
# replacement into a failed operation or roll back the new generation.
# =====================================================================


def test_replace_report_month_ignores_archive_failure_after_commit(
    monkeypatch,
) -> None:
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
                17,
                30,
                tzinfo=timezone.utc,
            ),
        ),
    )

    month = DriveFileMetadata(
        file_id="month-id",
        name="2026-08",
        mime_type="application/vnd.google-apps.folder",
        size_bytes=None,
        trashed=False,
        app_properties={
            "ahm_type": "report_month",
            "ahm_period": "2026-08",
            "ahm_current_generation_id": "generation-old",
        },
    )

    current = CurrentReportGeneration(
        period="2026-08",
        generation_id="generation-old",
        artifacts=(),
    )

    staging = DriveFileMetadata(
        file_id="staging-id",
        name="staging-generation-new",
        mime_type="application/vnd.google-apps.folder",
        size_bytes=None,
        trashed=False,
        app_properties={
            "ahm_type": "report_staging",
            "ahm_period": "2026-08",
            "ahm_generation_id": "generation-new",
        },
    )

    uploaded = (
        DriveFileMetadata(
            file_id="new-full-json",
            name="full.json",
            mime_type="application/json",
            size_bytes=len(b'{"status":"new"}'),
            trashed=False,
            app_properties=report.metadata.artifact_app_properties(),
        ),
    )

    calls = []

    monkeypatch.setattr(
        "apple_health.google.report_persistence.discover_current_generation",
        lambda drive_client, *, month: current,
    )

    monkeypatch.setattr(
        "apple_health.google.report_persistence.stage_report_generation",
        lambda drive_client, *, month_id, report: (
            staging,
            uploaded,
        ),
    )

    monkeypatch.setattr(
        "apple_health.google.report_persistence.verify_staged_generation",
        lambda drive_client, *, report, uploaded: calls.append("verify"),
    )

    monkeypatch.setattr(
        "apple_health.google.report_persistence.prepare_staged_generation_activation",
        lambda drive_client, *, month_id, staging_id, artifacts: (
            calls.append("prepare"),
            artifacts,
        )[1],
    )

    monkeypatch.setattr(
        "apple_health.google.report_persistence.commit_staged_generation",
        lambda drive_client, *, month_id, period, generation_id: (
            calls.append("commit"),
            month,
        )[1],
    )

    def fail_archive(
        drive_client,
        *,
        month_id,
        artifacts,
    ):
        calls.append("archive")
        raise RuntimeError("archive failed")

    monkeypatch.setattr(
        "apple_health.google.report_persistence.archive_previous_generation",
        fail_archive,
    )

    replace_report_month(
        object(),
        month=month,
        report=report,
    )

    assert calls == [
        "verify",
        "prepare",
        "commit",
        "archive",
    ]


# =====================================================================
# Verifies that successful replacement cleans the now-empty staging
# folder after committing and archiving the previous generation.
# =====================================================================


def test_replace_report_month_cleans_staging_after_success(
    monkeypatch,
) -> None:
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
                17,
                30,
                tzinfo=timezone.utc,
            ),
        ),
    )

    month = DriveFileMetadata(
        file_id="month-id",
        name="2026-08",
        mime_type="application/vnd.google-apps.folder",
        size_bytes=None,
        trashed=False,
        app_properties={
            "ahm_type": "report_month",
            "ahm_period": "2026-08",
            "ahm_current_generation_id": "generation-old",
        },
    )

    current = CurrentReportGeneration(
        period="2026-08",
        generation_id="generation-old",
        artifacts=(),
    )

    staging = DriveFileMetadata(
        file_id="staging-id",
        name="staging-generation-new",
        mime_type="application/vnd.google-apps.folder",
        size_bytes=None,
        trashed=False,
        app_properties={
            "ahm_type": "report_staging",
            "ahm_period": "2026-08",
            "ahm_generation_id": "generation-new",
        },
    )

    uploaded = (
        DriveFileMetadata(
            file_id="new-full-json",
            name="full.json",
            mime_type="application/json",
            size_bytes=len(b'{"status":"new"}'),
            trashed=False,
            app_properties=report.metadata.artifact_app_properties(),
        ),
    )

    calls = []

    monkeypatch.setattr(
        "apple_health.google.report_persistence.discover_current_generation",
        lambda drive_client, *, month: current,
    )

    monkeypatch.setattr(
        "apple_health.google.report_persistence.stage_report_generation",
        lambda drive_client, *, month_id, report: (
            staging,
            uploaded,
        ),
    )

    monkeypatch.setattr(
        "apple_health.google.report_persistence.verify_staged_generation",
        lambda drive_client, *, report, uploaded: calls.append("verify"),
    )

    monkeypatch.setattr(
        "apple_health.google.report_persistence.prepare_staged_generation_activation",
        lambda drive_client, *, month_id, staging_id, artifacts: (
            calls.append("prepare"),
            artifacts,
        )[1],
    )

    monkeypatch.setattr(
        "apple_health.google.report_persistence.commit_staged_generation",
        lambda drive_client, *, month_id, period, generation_id: (
            calls.append("commit"),
            month,
        )[1],
    )

    monkeypatch.setattr(
        "apple_health.google.report_persistence.archive_previous_generation",
        lambda drive_client, *, month_id, artifacts: (
            calls.append("archive"),
            artifacts,
        )[1],
    )

    monkeypatch.setattr(
        "apple_health.google.report_persistence.cleanup_staging_generation",
        lambda drive_client, *, staging_id: calls.append("cleanup"),
    )

    replace_report_month(
        object(),
        month=month,
        report=report,
    )

    assert calls == [
        "verify",
        "prepare",
        "commit",
        "archive",
        "cleanup",
    ]


# =====================================================================
# Verifies that staging cleanup failure after commit does not turn a
# successful replacement into a failed operation.
# =====================================================================


def test_replace_report_month_ignores_staging_cleanup_failure_after_commit(
    monkeypatch,
) -> None:
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
                17,
                30,
                tzinfo=timezone.utc,
            ),
        ),
    )

    month = DriveFileMetadata(
        file_id="month-id",
        name="2026-08",
        mime_type="application/vnd.google-apps.folder",
        size_bytes=None,
        trashed=False,
        app_properties={
            "ahm_type": "report_month",
            "ahm_period": "2026-08",
            "ahm_current_generation_id": "generation-old",
        },
    )

    current = CurrentReportGeneration(
        period="2026-08",
        generation_id="generation-old",
        artifacts=(),
    )

    staging = DriveFileMetadata(
        file_id="staging-id",
        name="staging-generation-new",
        mime_type="application/vnd.google-apps.folder",
        size_bytes=None,
        trashed=False,
        app_properties={
            "ahm_type": "report_staging",
            "ahm_period": "2026-08",
            "ahm_generation_id": "generation-new",
        },
    )

    uploaded = (
        DriveFileMetadata(
            file_id="new-full-json",
            name="full.json",
            mime_type="application/json",
            size_bytes=len(b'{"status":"new"}'),
            trashed=False,
            app_properties=report.metadata.artifact_app_properties(),
        ),
    )

    calls = []

    monkeypatch.setattr(
        "apple_health.google.report_persistence.discover_current_generation",
        lambda drive_client, *, month: current,
    )

    monkeypatch.setattr(
        "apple_health.google.report_persistence.stage_report_generation",
        lambda drive_client, *, month_id, report: (
            staging,
            uploaded,
        ),
    )

    monkeypatch.setattr(
        "apple_health.google.report_persistence.verify_staged_generation",
        lambda drive_client, *, report, uploaded: calls.append("verify"),
    )

    monkeypatch.setattr(
        "apple_health.google.report_persistence.prepare_staged_generation_activation",
        lambda drive_client, *, month_id, staging_id, artifacts: (
            calls.append("prepare"),
            artifacts,
        )[1],
    )

    monkeypatch.setattr(
        "apple_health.google.report_persistence.commit_staged_generation",
        lambda drive_client, *, month_id, period, generation_id: (
            calls.append("commit"),
            month,
        )[1],
    )

    monkeypatch.setattr(
        "apple_health.google.report_persistence.archive_previous_generation",
        lambda drive_client, *, month_id, artifacts: (
            calls.append("archive"),
            artifacts,
        )[1],
    )

    def fail_cleanup(
        drive_client,
        *,
        staging_id,
    ):
        calls.append("cleanup")
        raise RuntimeError("cleanup failed")

    monkeypatch.setattr(
        "apple_health.google.report_persistence.cleanup_staging_generation",
        fail_cleanup,
    )

    replace_report_month(
        object(),
        month=month,
        report=report,
    )

    assert calls == [
        "verify",
        "prepare",
        "commit",
        "archive",
        "cleanup",
    ]
