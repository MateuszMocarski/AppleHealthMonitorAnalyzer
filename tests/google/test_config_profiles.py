from dataclasses import dataclass
from pathlib import Path

from apple_health.google.config_profiles import (
    ConfigProfile,
    discover_config_profiles,
    discover_drive_config_profiles,
    load_config_profile,
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
    def __init__(self, content: str) -> None:
        self.content = content
        self.downloaded_file_id: str | None = None
        self.max_bytes: int | None = None

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
# Verifies that Drive config profile discovery lists all pages from the
# config container and exposes only application-managed profiles.
# =====================================================================


def test_discover_drive_config_profiles_lists_config_container() -> None:
    pages = {
        None: _DrivePage(
            files=(
                _DriveFile(
                    file_id="config-1",
                    name="Cutting.toml",
                    trashed=False,
                    app_properties={
                        "ahm_type": "config_profile",
                    },
                ),
            ),
            next_page_token="page-2",
        ),
        "page-2": _DrivePage(
            files=(
                _DriveFile(
                    file_id="config-2",
                    name="Maintenance.toml",
                    trashed=False,
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
            ),
            next_page_token=None,
        ),
    }

    class FakeDriveClient:
        def list_children(
            self,
            parent_id: str,
            *,
            page_token: str | None = None,
        ) -> _DrivePage:
            assert parent_id == "config-container-1"
            return pages[page_token]

    assert discover_drive_config_profiles(
        FakeDriveClient(),
        config_container_id="config-container-1",
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
