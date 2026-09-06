import pytest

from apple_health.google.drive import (
    DriveConflictError,
    DriveFileMetadata,
    DriveFilePage,
)
from apple_health.google.drive_structure import (
    discover_ahm_root,
    discover_report_month,
    ensure_ahm_root,
    ensure_config_container,
    ensure_reports_container,
    ensure_year_container,
)

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


# =====================================================================
# Verifies that the AHM root is created lazily when a write requires it.
# =====================================================================


def test_ensure_ahm_root_creates_missing_root() -> None:
    created_root = DriveFileMetadata(
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

    class FakeDriveClient:
        def search(
            self,
            query: str,
            page_token: str | None = None,
        ) -> DriveFilePage:
            return DriveFilePage(
                files=(),
                next_page_token=None,
            )

        def create_folder(
            self,
            name: str,
            parent_id: str | None = None,
            app_properties: dict[str, str] | None = None,
        ) -> DriveFileMetadata:
            assert name == "Apple Health Monitor"
            assert parent_id is None
            assert app_properties == {
                "ahm_type": "root",
                "ahm_version": "1",
            }

            return created_root

    assert ensure_ahm_root(FakeDriveClient()) == created_root


# =====================================================================
# Verifies that a missing config container is created lazily under the
# AHM root and identified by appProperties instead of its visible name.
# =====================================================================


def test_ensure_config_container_creates_missing_container() -> None:
    created_config = DriveFileMetadata(
        file_id="config-123",
        name="config",
        mime_type="application/vnd.google-apps.folder",
        size_bytes=None,
        trashed=False,
        app_properties={
            "ahm_type": "config_container",
        },
    )

    class FakeDriveClient:
        def search(
            self,
            query: str,
            page_token: str | None = None,
        ) -> DriveFilePage:
            assert page_token is None
            assert "'root-123' in parents" in query
            assert "appProperties has " "{ key='ahm_type' and value='config_container' }" in query
            assert "trashed = false" in query
            assert "name =" not in query

            return DriveFilePage(
                files=(),
                next_page_token=None,
            )

        def create_folder(
            self,
            name: str,
            parent_id: str | None = None,
            app_properties: dict[str, str] | None = None,
        ) -> DriveFileMetadata:
            assert name == "config"
            assert parent_id == "root-123"
            assert app_properties == {
                "ahm_type": "config_container",
            }

            return created_config

    assert (
        ensure_config_container(
            FakeDriveClient(),
            root_id="root-123",
        )
        == created_config
    )


# =====================================================================
# Verifies that config container discovery follows Drive pagination
# before deciding that the container is missing and creating a new one.
# =====================================================================


def test_ensure_config_container_finds_existing_container_on_later_page() -> None:
    existing_config = DriveFileMetadata(
        file_id="config-123",
        name="Renamed config",
        mime_type="application/vnd.google-apps.folder",
        size_bytes=None,
        trashed=False,
        app_properties={
            "ahm_type": "config_container",
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
                    files=(),
                    next_page_token="page-2",
                )

            assert page_token == "page-2"

            return DriveFilePage(
                files=(existing_config,),
                next_page_token=None,
            )

        def create_folder(
            self,
            name: str,
            parent_id: str | None = None,
            app_properties: dict[str, str] | None = None,
        ) -> DriveFileMetadata:
            raise AssertionError("Existing config container must be reused")

    assert (
        ensure_config_container(
            FakeDriveClient(),
            root_id="root-123",
        )
        == existing_config
    )


# =====================================================================
# Verifies that a missing reports container is created lazily under the
# AHM root when report persistence requires it.
# =====================================================================


def test_ensure_reports_container_creates_missing_container() -> None:
    created_reports = DriveFileMetadata(
        file_id="reports-123",
        name="reports",
        mime_type="application/vnd.google-apps.folder",
        size_bytes=None,
        trashed=False,
        app_properties={
            "ahm_type": "reports_container",
        },
    )

    class FakeDriveClient:
        def search(
            self,
            query: str,
            page_token: str | None = None,
        ) -> DriveFilePage:
            assert page_token is None
            assert "'root-123' in parents" in query
            assert "appProperties has " "{ key='ahm_type' and value='reports_container' }" in query
            assert "trashed = false" in query
            assert "name =" not in query

            return DriveFilePage(
                files=(),
                next_page_token=None,
            )

        def create_folder(
            self,
            name: str,
            parent_id: str | None = None,
            app_properties: dict[str, str] | None = None,
        ) -> DriveFileMetadata:
            assert name == "reports"
            assert parent_id == "root-123"
            assert app_properties == {
                "ahm_type": "reports_container",
            }

            return created_reports

    assert (
        ensure_reports_container(
            FakeDriveClient(),
            root_id="root-123",
        )
        == created_reports
    )


# =====================================================================
# Verifies that a missing report year container is created lazily under
# the reports container when persistence for that year requires it.
# =====================================================================


def test_ensure_year_container_creates_missing_container() -> None:
    created_year = DriveFileMetadata(
        file_id="year-2026",
        name="2026",
        mime_type="application/vnd.google-apps.folder",
        size_bytes=None,
        trashed=False,
        app_properties={
            "ahm_type": "year_container",
            "ahm_year": "2026",
        },
    )

    class FakeDriveClient:
        def search(
            self,
            query: str,
            page_token: str | None = None,
        ) -> DriveFilePage:
            assert page_token is None
            assert "'reports-123' in parents" in query
            assert "appProperties has " "{ key='ahm_type' and value='year_container' }" in query
            assert "appProperties has " "{ key='ahm_year' and value='2026' }" in query
            assert "trashed = false" in query
            assert "name =" not in query

            return DriveFilePage(
                files=(),
                next_page_token=None,
            )

        def create_folder(
            self,
            name: str,
            parent_id: str | None = None,
            app_properties: dict[str, str] | None = None,
        ) -> DriveFileMetadata:
            assert name == "2026"
            assert parent_id == "reports-123"
            assert app_properties == {
                "ahm_type": "year_container",
                "ahm_year": "2026",
            }

            return created_year

    assert (
        ensure_year_container(
            FakeDriveClient(),
            reports_id="reports-123",
            year=2026,
        )
        == created_year
    )


# =====================================================================
# Verifies that year container discovery follows Drive pagination before
# deciding that the requested year container is missing.
# =====================================================================


def test_ensure_year_container_finds_existing_container_on_later_page() -> None:
    existing_year = DriveFileMetadata(
        file_id="year-2026",
        name="Renamed year",
        mime_type="application/vnd.google-apps.folder",
        size_bytes=None,
        trashed=False,
        app_properties={
            "ahm_type": "year_container",
            "ahm_year": "2026",
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
                    files=(),
                    next_page_token="page-2",
                )

            assert page_token == "page-2"

            return DriveFilePage(
                files=(existing_year,),
                next_page_token=None,
            )

        def create_folder(
            self,
            name: str,
            parent_id: str | None = None,
            app_properties: dict[str, str] | None = None,
        ) -> DriveFileMetadata:
            raise AssertionError("Existing year container must be reused")

    assert (
        ensure_year_container(
            FakeDriveClient(),
            reports_id="reports-123",
            year=2026,
        )
        == existing_year
    )


# =====================================================================
# Verifies that report month discovery uses appProperties instead of
# the visible Drive folder name.
# =====================================================================


def test_discover_report_month_uses_app_properties_not_visible_name() -> None:
    report_month = DriveFileMetadata(
        file_id="month-2026-08",
        name="Renamed by user",
        mime_type="application/vnd.google-apps.folder",
        size_bytes=None,
        trashed=False,
        app_properties={
            "ahm_type": "report_month",
            "ahm_period": "2026-08",
        },
    )

    class FakeDriveClient:
        def search(
            self,
            query: str,
            page_token: str | None = None,
        ) -> DriveFilePage:
            assert page_token is None
            assert "'year-2026' in parents" in query
            assert "appProperties has " "{ key='ahm_type' and value='report_month' }" in query
            assert "appProperties has " "{ key='ahm_period' and value='2026-08' }" in query
            assert "trashed = false" in query
            assert "name =" not in query
            assert report_month.name not in query

            return DriveFilePage(
                files=(report_month,),
                next_page_token=None,
            )

    assert (
        discover_report_month(
            FakeDriveClient(),
            year_id="year-2026",
            period="2026-08",
        )
        == report_month
    )


# =====================================================================
# Verifies that duplicate active report month containers are reported
# as a controlled conflict instead of selecting one automatically.
# =====================================================================


def test_discover_report_month_rejects_duplicate_active_months() -> None:
    first_month = DriveFileMetadata(
        file_id="month-1",
        name="2026-08",
        mime_type="application/vnd.google-apps.folder",
        size_bytes=None,
        trashed=False,
        app_properties={
            "ahm_type": "report_month",
            "ahm_period": "2026-08",
        },
    )
    second_month = DriveFileMetadata(
        file_id="month-2",
        name="Renamed month",
        mime_type="application/vnd.google-apps.folder",
        size_bytes=None,
        trashed=False,
        app_properties={
            "ahm_type": "report_month",
            "ahm_period": "2026-08",
        },
    )

    class FakeDriveClient:
        def search(
            self,
            query: str,
            page_token: str | None = None,
        ) -> DriveFilePage:
            return DriveFilePage(
                files=(first_month, second_month),
                next_page_token=None,
            )

    with pytest.raises(DriveConflictError):
        discover_report_month(
            FakeDriveClient(),
            year_id="year-2026",
            period="2026-08",
        )


# =====================================================================
# Verifies that report month discovery follows Drive pagination and
# detects a duplicate active month returned on a later page.
# =====================================================================


def test_discover_report_month_rejects_duplicate_on_later_page() -> None:
    first_month = DriveFileMetadata(
        file_id="month-1",
        name="2026-08",
        mime_type="application/vnd.google-apps.folder",
        size_bytes=None,
        trashed=False,
        app_properties={
            "ahm_type": "report_month",
            "ahm_period": "2026-08",
        },
    )
    second_month = DriveFileMetadata(
        file_id="month-2",
        name="Renamed month",
        mime_type="application/vnd.google-apps.folder",
        size_bytes=None,
        trashed=False,
        app_properties={
            "ahm_type": "report_month",
            "ahm_period": "2026-08",
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
                    files=(first_month,),
                    next_page_token="page-2",
                )

            assert page_token == "page-2"

            return DriveFilePage(
                files=(second_month,),
                next_page_token=None,
            )

    with pytest.raises(DriveConflictError):
        discover_report_month(
            FakeDriveClient(),
            year_id="year-2026",
            period="2026-08",
        )
