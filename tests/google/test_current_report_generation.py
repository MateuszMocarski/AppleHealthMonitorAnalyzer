from connected_health.google.current_report_generation import (
    CurrentReportGeneration,
    discover_current_generation,
    discover_current_generation_artifacts,
    resolve_current_generation,
    select_current_generation_artifacts,
)
from connected_health.google.drive import DriveFileMetadata, DriveFilePage

# =====================================================================
# Verifies that only artifacts matching the month current-generation
# pointer are treated as active report artifacts.
# =====================================================================


def test_select_current_generation_artifacts_uses_month_pointer() -> None:
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

    artifacts = (
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
        DriveFileMetadata(
            file_id="new-full-json",
            name="full.json",
            mime_type="application/json",
            size_bytes=120,
            trashed=False,
            app_properties={
                "ahm_type": "report_artifact",
                "ahm_period": "2026-08",
                "ahm_generation_id": "generation-new",
            },
        ),
    )

    selected = select_current_generation_artifacts(
        month=month,
        artifacts=artifacts,
    )

    assert tuple(artifact.file_id for artifact in selected) == (
        "new-summary-text",
        "new-full-json",
    )


# =====================================================================
# Verifies that report artifacts are not treated as current when the
# report month has no current-generation pointer.
# =====================================================================


def test_select_current_generation_artifacts_requires_month_pointer() -> None:
    month = DriveFileMetadata(
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

    artifacts = (
        DriveFileMetadata(
            file_id="artifact-1",
            name="full.json",
            mime_type="application/json",
            size_bytes=100,
            trashed=False,
            app_properties={
                "ahm_type": "report_artifact",
                "ahm_period": "2026-08",
                "ahm_generation_id": "generation-123",
            },
        ),
    )

    selected = select_current_generation_artifacts(
        month=month,
        artifacts=artifacts,
    )

    assert selected == ()


# =====================================================================
# Verifies that trashed artifacts are ignored even when they belong to
# the current generation.
# =====================================================================


def test_select_current_generation_artifacts_ignores_trashed_files() -> None:
    month = DriveFileMetadata(
        file_id="month-id",
        name="2026-08",
        mime_type="application/vnd.google-apps.folder",
        size_bytes=None,
        trashed=False,
        app_properties={
            "ahm_type": "report_month",
            "ahm_period": "2026-08",
            "ahm_current_generation_id": "generation-123",
        },
    )

    artifacts = (
        DriveFileMetadata(
            file_id="active",
            name="summary.txt",
            mime_type="text/plain",
            size_bytes=10,
            trashed=False,
            app_properties={
                "ahm_type": "report_artifact",
                "ahm_period": "2026-08",
                "ahm_generation_id": "generation-123",
            },
        ),
        DriveFileMetadata(
            file_id="trashed",
            name="full.json",
            mime_type="application/json",
            size_bytes=100,
            trashed=True,
            app_properties={
                "ahm_type": "report_artifact",
                "ahm_period": "2026-08",
                "ahm_generation_id": "generation-123",
            },
        ),
    )

    selected = select_current_generation_artifacts(
        month=month,
        artifacts=artifacts,
    )

    assert tuple(artifact.file_id for artifact in selected) == ("active",)


# =====================================================================
# Verifies that current report discovery reads all month children and
# returns only artifacts belonging to the current generation.
# =====================================================================


def test_discover_current_generation_artifacts_filters_month_children() -> None:
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

    old_artifact = DriveFileMetadata(
        file_id="old-id",
        name="full.json",
        mime_type="application/json",
        size_bytes=100,
        trashed=False,
        app_properties={
            "ahm_type": "report_artifact",
            "ahm_period": "2026-08",
            "ahm_generation_id": "generation-old",
        },
    )
    current_artifact = DriveFileMetadata(
        file_id="current-id",
        name="summary.txt",
        mime_type="text/plain",
        size_bytes=50,
        trashed=False,
        app_properties={
            "ahm_type": "report_artifact",
            "ahm_period": "2026-08",
            "ahm_generation_id": "generation-new",
        },
    )

    calls = []

    class FakeDriveClient:
        def list_children(
            self,
            parent_id: str,
            page_token: str | None = None,
        ) -> DriveFilePage:
            calls.append(
                (
                    parent_id,
                    page_token,
                )
            )

            if page_token is None:
                return DriveFilePage(
                    files=(old_artifact,),
                    next_page_token="page-2",
                )

            return DriveFilePage(
                files=(current_artifact,),
                next_page_token=None,
            )

    artifacts = discover_current_generation_artifacts(
        FakeDriveClient(),
        month=month,
    )

    assert calls == [
        ("month-id", None),
        ("month-id", "page-2"),
    ]
    assert tuple(artifact.file_id for artifact in artifacts) == ("current-id",)


# =====================================================================
# Verifies that an artifact with the current generation id is ignored
# when its report period does not match the report month.
# =====================================================================


def test_select_current_generation_artifacts_requires_matching_period() -> None:
    month = DriveFileMetadata(
        file_id="month-id",
        name="2026-08",
        mime_type="application/vnd.google-apps.folder",
        size_bytes=None,
        trashed=False,
        app_properties={
            "ahm_type": "report_month",
            "ahm_period": "2026-08",
            "ahm_current_generation_id": "generation-123",
        },
    )

    artifacts = (
        DriveFileMetadata(
            file_id="wrong-period",
            name="full.json",
            mime_type="application/json",
            size_bytes=100,
            trashed=False,
            app_properties={
                "ahm_type": "report_artifact",
                "ahm_period": "2026-07",
                "ahm_generation_id": "generation-123",
            },
        ),
        DriveFileMetadata(
            file_id="correct-period",
            name="summary.txt",
            mime_type="text/plain",
            size_bytes=50,
            trashed=False,
            app_properties={
                "ahm_type": "report_artifact",
                "ahm_period": "2026-08",
                "ahm_generation_id": "generation-123",
            },
        ),
    )

    selected = select_current_generation_artifacts(
        month=month,
        artifacts=artifacts,
    )

    assert tuple(artifact.file_id for artifact in selected) == ("correct-period",)


# =====================================================================
# Verifies that the current-generation model is derived exclusively
# from the month pointer and contains only matching active artifacts.
# =====================================================================


def test_resolve_current_generation_uses_month_pointer_as_source_of_truth() -> None:
    month = DriveFileMetadata(
        file_id="month-id",
        name="2026-08",
        mime_type="application/vnd.google-apps.folder",
        size_bytes=None,
        trashed=False,
        app_properties={
            "ahm_type": "report_month",
            "ahm_period": "2026-08",
            "ahm_current_generation_id": "generation-current",
        },
    )

    artifacts = (
        DriveFileMetadata(
            file_id="current-json",
            name="full.json",
            mime_type="application/json",
            size_bytes=100,
            trashed=False,
            app_properties={
                "ahm_type": "report_artifact",
                "ahm_period": "2026-08",
                "ahm_generation_id": "generation-current",
            },
        ),
        DriveFileMetadata(
            file_id="orphan-json",
            name="summary.json",
            mime_type="application/json",
            size_bytes=50,
            trashed=False,
            app_properties={
                "ahm_type": "report_artifact",
                "ahm_period": "2026-08",
                "ahm_generation_id": "generation-orphan",
            },
        ),
        DriveFileMetadata(
            file_id="staging-folder",
            name="staging",
            mime_type="application/vnd.google-apps.folder",
            size_bytes=None,
            trashed=False,
            app_properties={
                "ahm_type": "report_staging",
                "ahm_period": "2026-08",
                "ahm_generation_id": "generation-current",
            },
        ),
    )

    current = resolve_current_generation(
        month=month,
        artifacts=artifacts,
    )

    assert current == CurrentReportGeneration(
        period="2026-08",
        generation_id="generation-current",
        artifacts=(artifacts[0],),
    )


# =====================================================================
# Verifies that current-generation discovery returns one coherent model
# derived from the month pointer and matching Drive artifacts.
# =====================================================================


def test_discover_current_generation_returns_resolved_model() -> None:
    month = DriveFileMetadata(
        file_id="month-id",
        name="2026-08",
        mime_type="application/vnd.google-apps.folder",
        size_bytes=None,
        trashed=False,
        app_properties={
            "ahm_type": "report_month",
            "ahm_period": "2026-08",
            "ahm_current_generation_id": "generation-current",
        },
    )

    current_artifact = DriveFileMetadata(
        file_id="current-json",
        name="full.json",
        mime_type="application/json",
        size_bytes=100,
        trashed=False,
        app_properties={
            "ahm_type": "report_artifact",
            "ahm_period": "2026-08",
            "ahm_generation_id": "generation-current",
        },
    )

    orphan_artifact = DriveFileMetadata(
        file_id="orphan-json",
        name="summary.json",
        mime_type="application/json",
        size_bytes=50,
        trashed=False,
        app_properties={
            "ahm_type": "report_artifact",
            "ahm_period": "2026-08",
            "ahm_generation_id": "generation-orphan",
        },
    )

    class FakeDriveClient:
        def list_children(
            self,
            parent_id: str,
            page_token: str | None = None,
        ) -> DriveFilePage:
            assert parent_id == "month-id"
            assert page_token is None

            return DriveFilePage(
                files=(
                    current_artifact,
                    orphan_artifact,
                ),
                next_page_token=None,
            )

    current = discover_current_generation(
        FakeDriveClient(),
        month=month,
    )

    assert current == CurrentReportGeneration(
        period="2026-08",
        generation_id="generation-current",
        artifacts=(current_artifact,),
    )


# =====================================================================
# Verifies that current-generation discovery returns None without
# reading month children when no current-generation pointer exists.
# =====================================================================


def test_discover_current_generation_skips_children_without_pointer() -> None:
    month = DriveFileMetadata(
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

    class FakeDriveClient:
        def list_children(
            self,
            parent_id: str,
            page_token: str | None = None,
        ) -> DriveFilePage:
            raise AssertionError("Month children must not be read without a current pointer")

    current = discover_current_generation(
        FakeDriveClient(),
        month=month,
    )

    assert current is None


# =====================================================================
# Verifies that replacing a report with a different output set does not
# merge artifacts from the previous generation into the current one.
# =====================================================================


def test_current_generation_does_not_merge_previous_output_set() -> None:
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

    artifacts = (
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
            file_id="new-summary-text",
            name="summary.txt",
            mime_type="text/plain",
            size_bytes=50,
            trashed=False,
            app_properties={
                "ahm_type": "report_artifact",
                "ahm_period": "2026-08",
                "ahm_generation_id": "generation-new",
                "ahm_generated_at": "2026-09-12T18:00:00Z",
            },
        ),
    )

    current = resolve_current_generation(
        month=month,
        artifacts=artifacts,
    )

    assert current is not None
    assert current.generation_id == "generation-new"
    assert tuple(artifact.name for artifact in current.artifacts) == ("summary.txt",)
