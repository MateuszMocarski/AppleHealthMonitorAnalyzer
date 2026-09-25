import pytest

from connected_health.google.drive import DriveConflictError, DriveFileMetadata, DriveFilePage
from connected_health.google.drive_structure import discover_viewer_report_index


def _metadata(
    file_id: str,
    *,
    name: str,
    app_properties: dict[str, str],
    mime_type: str = "application/vnd.google-apps.folder",
    trashed: bool = False,
) -> DriveFileMetadata:
    return DriveFileMetadata(
        file_id=file_id,
        name=name,
        mime_type=mime_type,
        size_bytes=None,
        trashed=trashed,
        app_properties=app_properties,
    )


def _artifact(
    file_id: str,
    *,
    name: str,
    period: str,
    generation_id: str,
    mime_type: str = "application/json",
) -> DriveFileMetadata:
    return _metadata(
        file_id,
        name=name,
        mime_type=mime_type,
        app_properties={
            "ahm_type": "report_artifact",
            "ahm_period": period,
            "ahm_generation_id": generation_id,
            "ahm_generated_at": "2026-09-12T18:00:00Z",
        },
    )


def _drive_client(
    *,
    months: tuple[DriveFileMetadata, ...] = (),
    children: dict[str, tuple[DriveFileMetadata, ...]] | None = None,
    root_exists: bool = True,
    reports_exists: bool = True,
):
    root = _metadata(
        "root",
        name="Connected Health Analyzer",
        app_properties={"ahm_type": "root", "ahm_version": "1"},
    )
    reports = _metadata(
        "reports",
        name="reports",
        app_properties={"ahm_type": "reports_container"},
    )
    year = _metadata(
        "year",
        name="2026",
        app_properties={"ahm_type": "year_container", "ahm_year": "2026"},
    )

    class FakeDriveClient:
        def search(self, query: str, page_token: str | None = None) -> DriveFilePage:
            assert page_token is None
            if "value='root'" in query:
                return DriveFilePage(files=(root,) if root_exists else (), next_page_token=None)
            if "value='reports_container'" in query:
                return DriveFilePage(
                    files=(reports,) if reports_exists else (), next_page_token=None
                )
            if "value='year_container'" in query:
                return DriveFilePage(files=(year,) if months else (), next_page_token=None)
            if "'year' in parents" in query:
                return DriveFilePage(files=months, next_page_token=None)
            raise AssertionError(f"Unexpected search query: {query}")

        def list_children(self, parent_id: str, page_token: str | None = None) -> DriveFilePage:
            assert page_token is None
            return DriveFilePage(files=(children or {}).get(parent_id, ()), next_page_token=None)

        def download_file(self, *args: object, **kwargs: object) -> None:
            raise AssertionError("Viewer index discovery must not download report bodies")

    return FakeDriveClient()


def _month(period: str, generation_id: str) -> DriveFileMetadata:
    return _metadata(
        f"month-{period}",
        name=period,
        app_properties={
            "ahm_type": "report_month",
            "ahm_period": period,
            "ahm_current_generation_id": generation_id,
        },
    )


def test_discover_viewer_report_index_is_empty_without_managed_root() -> None:
    assert discover_viewer_report_index(_drive_client(root_exists=False)) == ()


def test_discover_viewer_report_index_is_empty_without_report_json() -> None:
    month = _month("2026-08", "generation-current")
    client = _drive_client(months=(month,), children={month.file_id: ()})

    assert discover_viewer_report_index(client) == ()


@pytest.mark.parametrize(
    ("names", "expected_kinds"),
    [
        (("full.json",), ("full",)),
        (("summary.json",), ("summary",)),
        (("full.json", "summary.json", "full.txt", "summary.txt"), ("full", "summary")),
    ],
)
def test_discover_viewer_report_index_includes_only_active_json_kinds(
    names: tuple[str, ...], expected_kinds: tuple[str, ...]
) -> None:
    month = _month("2026-08", "generation-current")
    artifacts = tuple(
        _artifact(
            f"artifact-{name}",
            name=name,
            period="2026-08",
            generation_id="generation-current",
            mime_type="application/json" if name.endswith(".json") else "text/plain",
        )
        for name in names
    )
    client = _drive_client(months=(month,), children={month.file_id: artifacts})

    index = discover_viewer_report_index(client)

    assert tuple(artifact.kind for artifact in index) == expected_kinds
    assert all(artifact.period == "2026-08" for artifact in index)
    assert all(artifact.generation_id == "generation-current" for artifact in index)
    assert all(artifact.generated_at == "2026-09-12T18:00:00Z" for artifact in index)


def test_discover_viewer_report_index_excludes_archived_staging_orphan_and_old_artifacts() -> None:
    month = _month("2026-08", "generation-current")
    current = _artifact(
        "current-full",
        name="full.json",
        period="2026-08",
        generation_id="generation-current",
    )
    old = _artifact(
        "old-summary",
        name="summary.json",
        period="2026-08",
        generation_id="generation-old",
    )
    orphan = _artifact(
        "orphan-summary",
        name="summary.json",
        period="2026-08",
        generation_id="generation-orphan",
    )
    staging = _metadata(
        "staging",
        name="staging-generation-current",
        app_properties={
            "ahm_type": "report_staging",
            "ahm_period": "2026-08",
            "ahm_generation_id": "generation-current",
        },
    )
    archived = _artifact(
        "archived-full",
        name="full.json",
        period="2026-08",
        generation_id="generation-old",
    )
    client = _drive_client(
        months=(month,),
        children={month.file_id: (current, old, orphan, staging, archived)},
    )

    index = discover_viewer_report_index(client)

    assert tuple(artifact.file_id for artifact in index) == ("current-full",)


def test_discover_viewer_report_index_follows_replacement_current_generation_pointer() -> None:
    old_month = _month("2026-08", "generation-old")
    new_month = _month("2026-08", "generation-new")
    old_full = _artifact(
        "old-full",
        name="full.json",
        period="2026-08",
        generation_id="generation-old",
    )
    new_full = _artifact(
        "new-full",
        name="full.json",
        period="2026-08",
        generation_id="generation-new",
    )
    children = {
        old_month.file_id: (old_full, new_full),
        new_month.file_id: (old_full, new_full),
    }

    before_replacement = discover_viewer_report_index(
        _drive_client(months=(old_month,), children=children)
    )
    after_replacement = discover_viewer_report_index(
        _drive_client(months=(new_month,), children=children)
    )

    assert tuple(artifact.file_id for artifact in before_replacement) == ("old-full",)
    assert tuple(artifact.file_id for artifact in after_replacement) == ("new-full",)


def test_discover_viewer_report_index_orders_newest_period_then_full_before_summary() -> None:
    august = _month("2026-08", "generation-august")
    september = _month("2026-09", "generation-september")
    client = _drive_client(
        months=(august, september),
        children={
            august.file_id: (
                _artifact(
                    "august-summary",
                    name="summary.json",
                    period="2026-08",
                    generation_id="generation-august",
                ),
            ),
            september.file_id: (
                _artifact(
                    "september-summary",
                    name="summary.json",
                    period="2026-09",
                    generation_id="generation-september",
                ),
                _artifact(
                    "september-full",
                    name="full.json",
                    period="2026-09",
                    generation_id="generation-september",
                ),
            ),
        },
    )

    index = discover_viewer_report_index(client)

    assert [(artifact.period, artifact.kind) for artifact in index] == [
        ("2026-09", "full"),
        ("2026-09", "summary"),
        ("2026-08", "summary"),
    ]


def test_discover_viewer_report_index_rejects_duplicate_active_artifact_kind() -> None:
    month = _month("2026-08", "generation-current")
    artifacts = (
        _artifact(
            "first-full",
            name="full.json",
            period="2026-08",
            generation_id="generation-current",
        ),
        _artifact(
            "second-full",
            name="full.json",
            period="2026-08",
            generation_id="generation-current",
        ),
    )
    client = _drive_client(months=(month,), children={month.file_id: artifacts})

    with pytest.raises(DriveConflictError, match="Multiple active full.json"):
        discover_viewer_report_index(client)
