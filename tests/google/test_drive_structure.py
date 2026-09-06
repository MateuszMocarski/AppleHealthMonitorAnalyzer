import pytest

from apple_health.google.drive import (
    DriveConflictError,
    DriveFileMetadata,
    DriveFilePage,
)
from apple_health.google.drive_structure import discover_ahm_root


# =====================================================================
# Verifies that AHM root discovery uses appProperties instead of the
# visible Drive folder name.
# =====================================================================
def test_discover_ahm_root_uses_app_properties_not_visible_name() -> None:
    root = DriveFileMetadata(
        file_id="root-123",
        name="Renamed by user",
        mime_type="application/vnd.google-apps.folder",
        size_bytes=None,
        trashed=False,
        app_properties={
            "ahm_type": "root",
            "ahm_version": "1",
        },
    )

    class FakeDriveClient:
        def search(
            self,
            query: str,
            page_token: str | None = None,
        ) -> DriveFilePage:
            assert page_token is None
            assert "appProperties has { key='ahm_type' and value='root' }" in query
            assert "appProperties has { key='ahm_version' and value='1' }" in query
            assert "trashed = false" in query
            assert "Apple Health Monitor" not in query
            assert root.name not in query

            return DriveFilePage(
                files=(root,),
                next_page_token=None,
            )

    assert discover_ahm_root(FakeDriveClient()) == root


# =====================================================================
# Verifies that multiple active AHM roots are reported as a controlled
# conflict instead of selecting or ignoring one automatically.
# =====================================================================
def test_discover_ahm_root_rejects_duplicate_active_roots() -> None:
    first_root = DriveFileMetadata(
        file_id="root-123",
        name="Apple Health Monitor",
        mime_type="application/vnd.google-apps.folder",
        size_bytes=None,
        trashed=False,
        app_properties={
            "ahm_type": "root",
            "ahm_version": "1",
        },
    )
    second_root = DriveFileMetadata(
        file_id="root-456",
        name="Renamed root",
        mime_type="application/vnd.google-apps.folder",
        size_bytes=None,
        trashed=False,
        app_properties={
            "ahm_type": "root",
            "ahm_version": "1",
        },
    )

    class FakeDriveClient:
        def search(
            self,
            query: str,
            page_token: str | None = None,
        ) -> DriveFilePage:
            return DriveFilePage(
                files=(first_root, second_root),
                next_page_token=None,
            )

    with pytest.raises(DriveConflictError):
        discover_ahm_root(FakeDriveClient())


# =====================================================================
# Verifies that AHM root discovery follows Drive pagination and detects
# a duplicate active root returned on a later page.
# =====================================================================
def test_discover_ahm_root_rejects_duplicate_root_on_later_page() -> None:
    first_root = DriveFileMetadata(
        file_id="root-123",
        name="Apple Health Monitor",
        mime_type="application/vnd.google-apps.folder",
        size_bytes=None,
        trashed=False,
        app_properties={
            "ahm_type": "root",
            "ahm_version": "1",
        },
    )
    second_root = DriveFileMetadata(
        file_id="root-456",
        name="Renamed root",
        mime_type="application/vnd.google-apps.folder",
        size_bytes=None,
        trashed=False,
        app_properties={
            "ahm_type": "root",
            "ahm_version": "1",
        },
    )

    class FakeDriveClient:
        def search(
            self,
            query: str,
            page_token: str | None = None,
        ) -> DriveFilePage:
            if page_token is None:
                return DriveFilePage(
                    files=(first_root,),
                    next_page_token="page-2",
                )

            assert page_token == "page-2"

            return DriveFilePage(
                files=(second_root,),
                next_page_token=None,
            )

    with pytest.raises(DriveConflictError):
        discover_ahm_root(FakeDriveClient())
