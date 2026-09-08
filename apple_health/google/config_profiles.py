from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from apple_health.config.app_config import AppConfig
from apple_health.config.config_loader import ConfigLoader
from apple_health.google.drive import (
    DriveClient,
    DriveDownloadTooLargeError,
    DriveFileMetadata,
)
from apple_health.google.drive_structure import (
    discover_ahm_root,
    discover_config_container,
)

MAX_CONFIG_PROFILE_SIZE_BYTES = 1024 * 1024


@dataclass(frozen=True, slots=True)
class ConfigProfile:
    file_id: str
    name: str


def discover_config_profiles(
    files: tuple[DriveFileMetadata, ...],
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
    client: DriveClient,
    profile: ConfigProfile,
) -> AppConfig:
    metadata = client.get_metadata(profile.file_id)

    if metadata.size_bytes is not None and metadata.size_bytes > MAX_CONFIG_PROFILE_SIZE_BYTES:
        raise DriveDownloadTooLargeError("Drive config profile exceeds the maximum allowed size")

    with TemporaryDirectory() as temporary_directory:
        config_path = Path(temporary_directory) / "config.toml"

        client.download_file(
            profile.file_id,
            config_path,
            max_bytes=MAX_CONFIG_PROFILE_SIZE_BYTES,
        )

        return ConfigLoader.load(config_path)


def discover_drive_config_profiles(
    client: DriveClient,
) -> tuple[ConfigProfile, ...]:
    root = discover_ahm_root(client)

    if root is None:
        return ()

    config_container = discover_config_container(
        client,
        root_id=root.file_id,
    )

    if config_container is None:
        return ()

    files: list[DriveFileMetadata] = []
    page_token: str | None = None

    while True:
        page = client.list_children(
            config_container.file_id,
            page_token=page_token,
        )
        files.extend(page.files)

        page_token = page.next_page_token

        if page_token is None:
            break

    return discover_config_profiles(tuple(files))
