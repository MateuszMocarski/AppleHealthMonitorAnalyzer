import pytest

from connected_health.google.drive import (
    DriveConflictError,
    DriveFileMetadata,
    DriveFilePage,
)
from connected_health.google.drive_structure import (
    discover_ahm_root,
    discover_config_container,
    discover_report_index,
    discover_report_month,
    discover_report_months,
    discover_report_years,
    discover_reports_container,
    ensure_ahm_root,
    ensure_config_container,
    ensure_report_month,
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


# =====================================================================
# Verifies that lightweight report discovery returns active month
# containers from metadata without downloading report content.
# =====================================================================


def test_discover_report_months_uses_metadata_without_downloading_content() -> None:
    august = DriveFileMetadata(
        file_id="month-2026-08",
        name="Renamed August",
        mime_type="application/vnd.google-apps.folder",
        size_bytes=None,
        trashed=False,
        app_properties={
            "ahm_type": "report_month",
            "ahm_period": "2026-08",
        },
    )
    september = DriveFileMetadata(
        file_id="month-2026-09",
        name="Whatever user wants",
        mime_type="application/vnd.google-apps.folder",
        size_bytes=None,
        trashed=False,
        app_properties={
            "ahm_type": "report_month",
            "ahm_period": "2026-09",
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
            assert "trashed = false" in query
            assert "name =" not in query

            return DriveFilePage(
                files=(august, september),
                next_page_token=None,
            )

        def download_file(self, *args: object, **kwargs: object) -> None:
            raise AssertionError("Lightweight report discovery must not download content")

    assert discover_report_months(
        FakeDriveClient(),
        year_id="year-2026",
    ) == (august, september)


# =====================================================================
# Verifies that lightweight report discovery follows Drive pagination
# and returns active month containers from every result page.
# =====================================================================


def test_discover_report_months_follows_pagination() -> None:
    august = DriveFileMetadata(
        file_id="month-2026-08",
        name="2026-08",
        mime_type="application/vnd.google-apps.folder",
        size_bytes=None,
        trashed=False,
        app_properties={
            "ahm_type": "report_month",
            "ahm_period": "2026-08",
        },
    )
    september = DriveFileMetadata(
        file_id="month-2026-09",
        name="2026-09",
        mime_type="application/vnd.google-apps.folder",
        size_bytes=None,
        trashed=False,
        app_properties={
            "ahm_type": "report_month",
            "ahm_period": "2026-09",
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
                    files=(august,),
                    next_page_token="page-2",
                )

            assert page_token == "page-2"

            return DriveFilePage(
                files=(september,),
                next_page_token=None,
            )

    assert discover_report_months(
        FakeDriveClient(),
        year_id="year-2026",
    ) == (august, september)


# =====================================================================
# Verifies that lightweight report discovery rejects duplicate active
# month containers for the same report period.
# =====================================================================


def test_discover_report_months_rejects_duplicate_periods() -> None:
    first_august = DriveFileMetadata(
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
    second_august = DriveFileMetadata(
        file_id="month-2",
        name="Renamed duplicate",
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
                files=(first_august, second_august),
                next_page_token=None,
            )

    with pytest.raises(DriveConflictError):
        discover_report_months(
            FakeDriveClient(),
            year_id="year-2026",
        )


# =====================================================================
# Verifies that lightweight report discovery finds year containers by
# metadata even when their visible Drive names have been changed.
# =====================================================================


def test_discover_report_years_uses_metadata_not_visible_name() -> None:
    year_2025 = DriveFileMetadata(
        file_id="year-2025",
        name="Renamed old reports",
        mime_type="application/vnd.google-apps.folder",
        size_bytes=None,
        trashed=False,
        app_properties={
            "ahm_type": "year_container",
            "ahm_year": "2025",
        },
    )
    year_2026 = DriveFileMetadata(
        file_id="year-2026",
        name="Whatever",
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
            assert "trashed = false" in query
            assert "name =" not in query

            return DriveFilePage(
                files=(year_2025, year_2026),
                next_page_token=None,
            )

    assert discover_report_years(
        FakeDriveClient(),
        reports_id="reports-123",
    ) == (year_2025, year_2026)


# =====================================================================
# Verifies that lightweight report year discovery follows Drive
# pagination and returns year containers from every result page.
# =====================================================================


def test_discover_report_years_follows_pagination() -> None:
    year_2025 = DriveFileMetadata(
        file_id="year-2025",
        name="2025",
        mime_type="application/vnd.google-apps.folder",
        size_bytes=None,
        trashed=False,
        app_properties={
            "ahm_type": "year_container",
            "ahm_year": "2025",
        },
    )
    year_2026 = DriveFileMetadata(
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
            if page_token is None:
                return DriveFilePage(
                    files=(year_2025,),
                    next_page_token="page-2",
                )

            assert page_token == "page-2"

            return DriveFilePage(
                files=(year_2026,),
                next_page_token=None,
            )

    assert discover_report_years(
        FakeDriveClient(),
        reports_id="reports-123",
    ) == (year_2025, year_2026)


# =====================================================================
# Verifies that lightweight report year discovery rejects duplicate
# active year containers for the same canonical year.
# =====================================================================


def test_discover_report_years_rejects_duplicate_years() -> None:
    first_year = DriveFileMetadata(
        file_id="year-1",
        name="2026",
        mime_type="application/vnd.google-apps.folder",
        size_bytes=None,
        trashed=False,
        app_properties={
            "ahm_type": "year_container",
            "ahm_year": "2026",
        },
    )
    second_year = DriveFileMetadata(
        file_id="year-2",
        name="Renamed duplicate",
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
            return DriveFilePage(
                files=(first_year, second_year),
                next_page_token=None,
            )

    with pytest.raises(DriveConflictError):
        discover_report_years(
            FakeDriveClient(),
            reports_id="reports-123",
        )


# =====================================================================
# Verifies that read-only reports container discovery returns no result
# when the container is missing and never creates Drive structure.
# =====================================================================


def test_discover_reports_container_returns_none_when_missing() -> None:
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
            raise AssertionError("Read-only discovery must not create containers")

    assert (
        discover_reports_container(
            FakeDriveClient(),
            root_id="root-123",
        )
        is None
    )


# =====================================================================
# Verifies that read-only reports container discovery follows Drive
# pagination before deciding that the container is missing.
# =====================================================================


def test_discover_reports_container_finds_existing_container_on_later_page() -> None:
    reports = DriveFileMetadata(
        file_id="reports-123",
        name="Renamed reports",
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
            if page_token is None:
                return DriveFilePage(
                    files=(),
                    next_page_token="page-2",
                )

            assert page_token == "page-2"

            return DriveFilePage(
                files=(reports,),
                next_page_token=None,
            )

        def create_folder(
            self,
            name: str,
            parent_id: str | None = None,
            app_properties: dict[str, str] | None = None,
        ) -> DriveFileMetadata:
            raise AssertionError("Read-only discovery must not create containers")

    assert (
        discover_reports_container(
            FakeDriveClient(),
            root_id="root-123",
        )
        == reports
    )


# =====================================================================
# Verifies that read-only reports container discovery rejects duplicate
# active containers instead of selecting one arbitrarily.
# =====================================================================


def test_discover_reports_container_rejects_duplicate_active_containers() -> None:
    first_reports = DriveFileMetadata(
        file_id="reports-1",
        name="reports",
        mime_type="application/vnd.google-apps.folder",
        size_bytes=None,
        trashed=False,
        app_properties={
            "ahm_type": "reports_container",
        },
    )
    second_reports = DriveFileMetadata(
        file_id="reports-2",
        name="Renamed reports",
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
            return DriveFilePage(
                files=(first_reports, second_reports),
                next_page_token=None,
            )

    with pytest.raises(DriveConflictError):
        discover_reports_container(
            FakeDriveClient(),
            root_id="root-123",
        )


# =====================================================================
# Verifies that lightweight report index discovery returns an empty
# index when the AHM root is absent and performs no Drive writes.
# =====================================================================


def test_discover_report_index_is_empty_when_root_is_missing() -> None:
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
            raise AssertionError("Read-only discovery must not create Drive structure")

        def download_file(self, *args: object, **kwargs: object) -> None:
            raise AssertionError("Lightweight index must not download report content")

    assert discover_report_index(FakeDriveClient()) == {}


# =====================================================================
# Verifies that lightweight report index discovery combines existing
# Drive metadata into available years and active report periods.
# =====================================================================


def test_discover_report_index_returns_available_years_and_months() -> None:
    root = DriveFileMetadata(
        file_id="root-123",
        name="Renamed root",
        mime_type="application/vnd.google-apps.folder",
        size_bytes=None,
        trashed=False,
        app_properties={
            "ahm_type": "root",
            "ahm_version": "1",
        },
    )
    reports = DriveFileMetadata(
        file_id="reports-123",
        name="Renamed reports",
        mime_type="application/vnd.google-apps.folder",
        size_bytes=None,
        trashed=False,
        app_properties={
            "ahm_type": "reports_container",
        },
    )
    year_2025 = DriveFileMetadata(
        file_id="year-2025",
        name="Old stuff",
        mime_type="application/vnd.google-apps.folder",
        size_bytes=None,
        trashed=False,
        app_properties={
            "ahm_type": "year_container",
            "ahm_year": "2025",
        },
    )
    year_2026 = DriveFileMetadata(
        file_id="year-2026",
        name="Current stuff",
        mime_type="application/vnd.google-apps.folder",
        size_bytes=None,
        trashed=False,
        app_properties={
            "ahm_type": "year_container",
            "ahm_year": "2026",
        },
    )
    december_2025 = DriveFileMetadata(
        file_id="month-2025-12",
        name="Renamed December",
        mime_type="application/vnd.google-apps.folder",
        size_bytes=None,
        trashed=False,
        app_properties={
            "ahm_type": "report_month",
            "ahm_period": "2025-12",
        },
    )
    august_2026 = DriveFileMetadata(
        file_id="month-2026-08",
        name="Renamed August",
        mime_type="application/vnd.google-apps.folder",
        size_bytes=None,
        trashed=False,
        app_properties={
            "ahm_type": "report_month",
            "ahm_period": "2026-08",
        },
    )
    september_2026 = DriveFileMetadata(
        file_id="month-2026-09",
        name="Renamed September",
        mime_type="application/vnd.google-apps.folder",
        size_bytes=None,
        trashed=False,
        app_properties={
            "ahm_type": "report_month",
            "ahm_period": "2026-09",
        },
    )

    class FakeDriveClient:
        def search(
            self,
            query: str,
            page_token: str | None = None,
        ) -> DriveFilePage:
            assert page_token is None

            if "value='root'" in query:
                return DriveFilePage(
                    files=(root,),
                    next_page_token=None,
                )

            if "value='reports_container'" in query:
                return DriveFilePage(
                    files=(reports,),
                    next_page_token=None,
                )

            if "value='year_container'" in query:
                return DriveFilePage(
                    files=(year_2025, year_2026),
                    next_page_token=None,
                )

            if "'year-2025' in parents" in query:
                return DriveFilePage(
                    files=(december_2025,),
                    next_page_token=None,
                )

            if "'year-2026' in parents" in query:
                return DriveFilePage(
                    files=(august_2026, september_2026),
                    next_page_token=None,
                )

            raise AssertionError(f"Unexpected query: {query}")

        def create_folder(
            self,
            name: str,
            parent_id: str | None = None,
            app_properties: dict[str, str] | None = None,
        ) -> DriveFileMetadata:
            raise AssertionError("Read-only discovery must not create Drive structure")

        def download_file(self, *args: object, **kwargs: object) -> None:
            raise AssertionError("Lightweight index must not download report content")

    assert discover_report_index(FakeDriveClient()) == {
        "2025": ("2025-12",),
        "2026": ("2026-08", "2026-09"),
    }


# =====================================================================
# Verifies that config container discovery returns an existing
# application-managed config folder without creating Drive state.
# =====================================================================


def test_discover_config_container_returns_existing_container() -> None:
    config_container = DriveFileMetadata(
        file_id="config-container-1",
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
            *,
            page_token: str | None = None,
        ) -> DriveFilePage:
            return DriveFilePage(
                files=(config_container,),
                next_page_token=None,
            )

    assert (
        discover_config_container(
            FakeDriveClient(),
            root_id="root-1",
        )
        == config_container
    )


# =====================================================================
# Verifies that ensuring a report month creates the managed month
# folder with canonical period metadata when it does not exist.
# =====================================================================


def test_ensure_report_month_creates_missing_month() -> None:
    created = {}

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
            created["name"] = name
            created["parent_id"] = parent_id
            created["app_properties"] = app_properties

            return DriveFileMetadata(
                file_id="month-1",
                name=name,
                mime_type="application/vnd.google-apps.folder",
                size_bytes=None,
                trashed=False,
                app_properties=app_properties or {},
            )

    month = ensure_report_month(
        FakeDriveClient(),
        year_id="year-2026",
        period="2026-08",
    )

    assert month.file_id == "month-1"
    assert created == {
        "name": "2026-08",
        "parent_id": "year-2026",
        "app_properties": {
            "ahm_type": "report_month",
            "ahm_period": "2026-08",
        },
    }
