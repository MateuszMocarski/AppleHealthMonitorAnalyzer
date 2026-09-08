from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Protocol

from apple_health.config.app_config import AppConfig
from apple_health.config.config_loader import ConfigLoader

MAX_CONFIG_PROFILE_SIZE_BYTES = 1024 * 1024


class _DriveFileMetadataLike(Protocol):
    file_id: str
    name: str
    trashed: bool
    app_properties: dict[str, str]


class _DriveConfigDownloader(Protocol):
    def download_file(
        self,
        file_id: str,
        destination_path: Path,
        *,
        max_bytes: int,
    ) -> None: ...


class _DriveFilePageLike(Protocol):
    files: tuple[_DriveFileMetadataLike, ...]
    next_page_token: str | None


class _DriveProfileLister(Protocol):
    def list_children(
        self,
        parent_id: str,
        *,
        page_token: str | None = None,
    ) -> _DriveFilePageLike: ...


@dataclass(frozen=True, slots=True)
class ConfigProfile:
    file_id: str
    name: str


def discover_config_profiles(
    files: tuple[_DriveFileMetadataLike, ...],
) -> tuple[ConfigProfile, ...]:
    return tuple(
        ConfigProfile(
            file_id=file.file_id,
            name=file.name,
        )
        for file in files
        if not file.trashed and file.app_properties.get("ahm_type") == "config_profile"
    )


def load_config_profile(
    client: _DriveConfigDownloader,
    profile: ConfigProfile,
) -> AppConfig:
    with TemporaryDirectory() as temporary_directory:
        config_path = Path(temporary_directory) / "config.toml"

        client.download_file(
            profile.file_id,
            config_path,
            max_bytes=MAX_CONFIG_PROFILE_SIZE_BYTES,
        )

        return ConfigLoader.load(config_path)


def discover_drive_config_profiles(
    client: _DriveProfileLister,
    *,
    config_container_id: str,
) -> tuple[ConfigProfile, ...]:
    files: list[_DriveFileMetadataLike] = []
    page_token: str | None = None

    while True:
        page = client.list_children(
            config_container_id,
            page_token=page_token,
        )
        files.extend(page.files)

        page_token = page.next_page_token

        if page_token is None:
            break

    return discover_config_profiles(tuple(files))
