from dataclasses import dataclass
from pathlib import Path

import pytest

from apple_health.config.exceptions import ConfigurationError
from apple_health.google.config_profiles import (
    ConfigProfile,
    discover_config_profiles,
    discover_drive_config_profiles,
    load_config_profile,
)
from apple_health.google.drive import (
    DriveDownloadTooLargeError,
    DriveFileMetadata,
    DriveFilePage,
)


@dataclass(frozen=True)
class _DriveFile:
    file_id: str
    name: str
    trashed: bool
    app_properties: dict[str, str]


@dataclass(frozen=True)
class _DrivePage:
    files: tuple[_DriveFile, ...]
    next_page_token: str | None


class _DriveDownloader:
    def __init__(
        self,
        content: str,
        *,
        size_bytes: int | None = None,
    ) -> None:
        self.content = content
        self.size_bytes = size_bytes
        self.downloaded_file_id: str | None = None
        self.max_bytes: int | None = None

    def get_metadata(
        self,
        file_id: str,
    ) -> DriveFileMetadata:
        return DriveFileMetadata(
            file_id=file_id,
            name="Cutting.toml",
            mime_type="application/toml",
            size_bytes=self.size_bytes,
            trashed=False,
            app_properties={
                "ahm_type": "config_profile",
            },
        )

    def download_file(
        self,
        file_id: str,
        destination_path: Path,
        *,
        max_bytes: int,
    ) -> None:
        self.downloaded_file_id = file_id
        self.max_bytes = max_bytes
        destination_path.write_text(
            self.content,
            encoding="utf-8",
        )


# =====================================================================
# Verifies that config profile discovery exposes application-managed
# Drive config files as named profiles without loading their content.
# =====================================================================


def test_discover_config_profiles_returns_named_profile() -> None:
    files = (
        _DriveFile(
            file_id="config-1",
            name="Cutting.toml",
            trashed=False,
            app_properties={
                "ahm_type": "config_profile",
            },
        ),
    )

    assert discover_config_profiles(files) == (
        ConfigProfile(
            file_id="config-1",
            name="Cutting.toml",
        ),
    )


# =====================================================================
# Verifies that config profile discovery ignores trashed files and
# Drive files that are not classified as config profiles.
# =====================================================================


def test_discover_config_profiles_ignores_unrelated_files() -> None:
    files = (
        _DriveFile(
            file_id="config-1",
            name="Cutting.toml",
            trashed=False,
            app_properties={
                "ahm_type": "config_profile",
            },
        ),
        _DriveFile(
            file_id="config-2",
            name="Old.toml",
            trashed=True,
            app_properties={
                "ahm_type": "config_profile",
            },
        ),
        _DriveFile(
            file_id="notes-1",
            name="notes.txt",
            trashed=False,
            app_properties={},
        ),
    )

    assert discover_config_profiles(files) == (
        ConfigProfile(
            file_id="config-1",
            name="Cutting.toml",
        ),
    )


# =====================================================================
# Verifies that a Drive config profile is downloaded with a hard size
# limit and validated through ConfigLoader before being returned.
# =====================================================================


def test_load_config_profile_downloads_and_validates_config() -> None:
    client = _DriveDownloader("[sleep]\n" "session_gap_threshold_minutes = 45\n")
    profile = ConfigProfile(
        file_id="config-1",
        name="Cutting.toml",
    )

    config = load_config_profile(
        client,
        profile,
    )

    assert config.sleep.session_gap_threshold_minutes == 45
    assert client.downloaded_file_id == "config-1"
    assert client.max_bytes == 1024 * 1024


# =====================================================================
# Verifies that Drive config profile discovery resolves the AHM root and
# config container before listing all saved configuration profiles.
# =====================================================================


def test_discover_drive_config_profiles_lists_config_container() -> None:
    root = DriveFileMetadata(
        file_id="root-1",
        name="Apple Health Monitor",
        mime_type="application/vnd.google-apps.folder",
        size_bytes=None,
        trashed=False,
        app_properties={
            "ahm_type": "root",
            "ahm_version": "1",
        },
    )
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

    profile_pages = {
        None: DriveFilePage(
            files=(
                DriveFileMetadata(
                    file_id="config-1",
                    name="Cutting.toml",
                    mime_type="application/toml",
                    size_bytes=100,
                    trashed=False,
                    app_properties={
                        "ahm_type": "config_profile",
                    },
                ),
            ),
            next_page_token="page-2",
        ),
        "page-2": DriveFilePage(
            files=(
                DriveFileMetadata(
                    file_id="config-2",
                    name="Maintenance.toml",
                    mime_type="application/toml",
                    size_bytes=100,
                    trashed=False,
                    app_properties={
                        "ahm_type": "config_profile",
                    },
                ),
                DriveFileMetadata(
                    file_id="notes-1",
                    name="notes.txt",
                    mime_type="text/plain",
                    size_bytes=100,
                    trashed=False,
                    app_properties={},
                ),
            ),
            next_page_token=None,
        ),
    }

    class FakeDriveClient:
        def search(
            self,
            query: str,
            page_token: str | None = None,
        ) -> DriveFilePage:
            if "value='root'" in query:
                return DriveFilePage(
                    files=(root,),
                    next_page_token=None,
                )

            if "value='config_container'" in query:
                assert "'root-1' in parents" in query
                return DriveFilePage(
                    files=(config_container,),
                    next_page_token=None,
                )

            raise AssertionError(f"Unexpected query: {query}")

        def list_children(
            self,
            parent_id: str,
            page_token: str | None = None,
        ) -> DriveFilePage:
            assert parent_id == "config-container-1"
            return profile_pages[page_token]

    assert discover_drive_config_profiles(
        FakeDriveClient(),
    ) == (
        ConfigProfile(
            file_id="config-1",
            name="Cutting.toml",
        ),
        ConfigProfile(
            file_id="config-2",
            name="Maintenance.toml",
        ),
    )


# =====================================================================
# Verifies that an oversized Drive config profile is rejected from
# metadata before any file content is downloaded.
# =====================================================================


def test_load_config_profile_rejects_oversized_metadata_before_download() -> None:
    client = _DriveDownloader(
        "[sleep]\n" "session_gap_threshold_minutes = 45\n",
        size_bytes=1024 * 1024 + 1,
    )
    profile = ConfigProfile(
        file_id="config-1",
        name="Cutting.toml",
    )

    with pytest.raises(DriveDownloadTooLargeError):
        load_config_profile(
            client,
            profile,
        )

    assert client.downloaded_file_id is None


# =====================================================================
# Verifies that an invalid Drive config profile fails validation instead
# of silently falling back to the application defaults.
# =====================================================================


def test_load_config_profile_rejects_invalid_configuration() -> None:
    client = _DriveDownloader("[sleep]\n" "unknown_field = 123\n")
    profile = ConfigProfile(
        file_id="config-1",
        name="Broken.toml",
    )

    with pytest.raises(
        ConfigurationError,
        match="Unknown configuration field",
    ):
        load_config_profile(
            client,
            profile,
        )


# =====================================================================
# Verifies that Drive config profile discovery returns no profiles when
# the Apple Health Monitor root folder does not exist.
# =====================================================================


def test_discover_drive_config_profiles_returns_empty_when_root_missing() -> None:
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

    assert (
        discover_drive_config_profiles(
            FakeDriveClient(),
        )
        == ()
    )


# =====================================================================
# Verifies that Drive config profile discovery returns no profiles when
# the application config container does not exist.
# =====================================================================


def test_discover_drive_config_profiles_returns_empty_when_config_container_missing() -> None:
    root = DriveFileMetadata(
        file_id="root-1",
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
            if "value='root'" in query:
                return DriveFilePage(
                    files=(root,),
                    next_page_token=None,
                )

            if "value='config_container'" in query:
                return DriveFilePage(
                    files=(),
                    next_page_token=None,
                )

            raise AssertionError(f"Unexpected query: {query}")

    assert (
        discover_drive_config_profiles(
            FakeDriveClient(),
        )
        == ()
    )
