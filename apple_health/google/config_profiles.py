from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from apple_health.config.app_config import AppConfig
from apple_health.config.config_loader import ConfigLoader
from apple_health.config.toml_renderer import TomlRenderer, semantic_fingerprint
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


def has_semantic_duplicate(
    config: AppConfig,
    *,
    existing_configs: tuple[AppConfig, ...],
) -> bool:
    fingerprint = semantic_fingerprint(config)

    return any(
        semantic_fingerprint(existing_config) == fingerprint for existing_config in existing_configs
    )


def resolve_config_profile_name(
    name: str,
    *,
    existing_profiles: tuple[ConfigProfile, ...],
) -> str:
    existing_names = {profile.name for profile in existing_profiles}

    if name not in existing_names:
        return name

    if name.lower().endswith(".toml"):
        base_name = name[:-5]
        extension = name[-5:]
    else:
        base_name = name
        extension = ""

    suffix = 2

    while True:
        candidate = f"{base_name}_{suffix}{extension}"

        if candidate not in existing_names:
            return candidate

        suffix += 1


def render_config_profile(config: AppConfig) -> str:
    return TomlRenderer.render(config)


def save_config_profile(
    client: DriveClient,
    *,
    config_container_id: str,
    name: str,
    config: AppConfig,
    existing_profiles: tuple[ConfigProfile, ...] = (),
) -> None:
    existing_configs = tuple(load_config_profile(client, profile) for profile in existing_profiles)

    if has_semantic_duplicate(
        config,
        existing_configs=existing_configs,
    ):
        return

    normalized_name = name if name.lower().endswith(".toml") else f"{name}.toml"

    resolved_name = resolve_config_profile_name(
        normalized_name,
        existing_profiles=existing_profiles,
    )

    client.upload_file(
        name=resolved_name,
        content=render_config_profile(config).encode("utf-8"),
        mime_type="application/toml",
        parent_id=config_container_id,
        app_properties={
            "ahm_type": "config_profile",
        },
    )


def autosave_config_profile(
    client: DriveClient,
    *,
    enabled: bool,
    config_container_id: str,
    name: str,
    config: AppConfig,
    existing_profiles: tuple[ConfigProfile, ...] = (),
) -> None:
    if not enabled:
        return

    save_config_profile(
        client,
        config_container_id=config_container_id,
        name=name,
        config=config,
        existing_profiles=existing_profiles,
    )
