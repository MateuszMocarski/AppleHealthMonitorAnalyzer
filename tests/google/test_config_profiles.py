from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

from connected_health.config.app_config import AppConfig
from connected_health.config.exceptions import ConfigurationError
from connected_health.config.source_config import SourceConfig
from connected_health.config.toml_renderer import TomlRenderer
from connected_health.google.config_profiles import (
    ConfigProfile,
    autosave_config_profile,
    discover_config_profiles,
    discover_drive_config_profiles,
    has_semantic_duplicate,
    load_config_profile,
    render_config_profile,
    resolve_config_profile_name,
    save_config_profile,
)
from connected_health.google.drive import (
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


# =====================================================================
# Verifies that semantically identical effective configurations are
# detected as duplicates regardless of their object identity.
# =====================================================================


def test_semantically_identical_config_is_detected_as_duplicate() -> None:
    effective_config = AppConfig(
        source=SourceConfig(
            apple_watch_source="Custom Watch",
            apple_health_app_source="Custom Health",
        ),
    )
    existing_config = AppConfig(
        source=SourceConfig(
            apple_watch_source="Custom Watch",
            apple_health_app_source="Custom Health",
        ),
    )

    assert has_semantic_duplicate(
        effective_config,
        existing_configs=(existing_config,),
    )


# =====================================================================
# Verifies that genuinely different effective configurations are not
# treated as semantic duplicates.
# =====================================================================


def test_different_config_is_not_detected_as_duplicate() -> None:
    effective_config = AppConfig(
        source=SourceConfig(
            apple_watch_source="Custom Watch",
            apple_health_app_source="Custom Health",
        ),
    )
    existing_config = AppConfig(
        source=SourceConfig(
            apple_watch_source="Different Watch",
            apple_health_app_source="Custom Health",
        ),
    )

    assert not has_semantic_duplicate(
        effective_config,
        existing_configs=(existing_config,),
    )


# =====================================================================
# Verifies that config profile collision suffixes are inserted before
# the TOML extension.
# =====================================================================


def test_resolve_config_profile_name_preserves_toml_extension() -> None:
    existing_profiles = (
        ConfigProfile(
            file_id="config-1",
            name="Cutting.toml",
        ),
    )

    result = resolve_config_profile_name(
        "Cutting.toml",
        existing_profiles=existing_profiles,
    )

    assert result == "Cutting_2.toml"


# =====================================================================
# Verifies that a non-colliding configuration profile name is preserved
# unchanged.
# =====================================================================


def test_config_profile_name_without_collision_is_preserved() -> None:
    existing_profiles = (
        ConfigProfile(
            file_id="config-1",
            name="Cutting",
        ),
    )

    resolved_name = resolve_config_profile_name(
        "Maintenance",
        existing_profiles=existing_profiles,
    )

    assert resolved_name == "Maintenance"


# =====================================================================
# Verifies that a configuration profile is serialized using the
# canonical TOML representation of the effective AppConfig.
# =====================================================================


def test_config_profile_is_rendered_as_canonical_toml() -> None:
    config = AppConfig(
        source=SourceConfig(
            apple_watch_source="Custom Watch",
            apple_health_app_source="Custom Health",
        ),
    )

    rendered = render_config_profile(config)

    assert rendered == TomlRenderer.render(config)


# =====================================================================
# Verifies that saving a configuration profile uploads its canonical
# TOML content into the config container with profile metadata.
# =====================================================================


def test_save_config_profile_uploads_canonical_toml() -> None:
    calls = {}

    class FakeDriveClient:
        def upload_file(
            self,
            name,
            content,
            mime_type,
            parent_id=None,
            app_properties=None,
        ):
            calls["name"] = name
            calls["content"] = content
            calls["mime_type"] = mime_type
            calls["parent_id"] = parent_id
            calls["app_properties"] = app_properties

    config = AppConfig(
        source=SourceConfig(
            apple_watch_source="Custom Watch",
            apple_health_app_source="Custom Health",
        ),
    )

    save_config_profile(
        FakeDriveClient(),
        config_container_id="config-container",
        name="Cutting",
        config=config,
    )

    assert calls == {
        "name": "Cutting.toml",
        "content": TomlRenderer.render(config).encode("utf-8"),
        "mime_type": "application/toml",
        "parent_id": "config-container",
        "app_properties": {
            "ahm_type": "config_profile",
        },
    }


# =====================================================================
# Verifies that saving a semantically duplicate configuration profile
# does not create another Drive file.
# =====================================================================


def test_save_config_profile_skips_semantic_duplicate(tmp_path) -> None:
    config = AppConfig(
        source=SourceConfig(
            apple_watch_source="Custom Watch",
            apple_health_app_source="Custom Health",
        ),
    )

    existing_profile = ConfigProfile(
        file_id="existing-config",
        name="Existing",
    )

    class FakeDriveClient:
        def download_file(
            self,
            file_id,
            destination_path,
            *,
            max_bytes,
        ):
            assert file_id == "existing-config"
            destination_path.write_text(
                TomlRenderer.render(config),
                encoding="utf-8",
            )

        def upload_file(self, *args, **kwargs):
            raise AssertionError("Duplicate config must not be uploaded")

        def get_metadata(
            self,
            file_id: str,
        ):
            assert file_id == "existing-config"

            rendered_config = TomlRenderer.render(config)

            return DriveFileMetadata(
                file_id=file_id,
                name="Existing",
                mime_type="application/toml",
                size_bytes=len(
                    rendered_config.encode("utf-8"),
                ),
                trashed=False,
                app_properties={
                    "ahm_type": "config_profile",
                },
            )

    save_config_profile(
        FakeDriveClient(),
        config_container_id="config-container",
        name="Cutting",
        config=config,
        existing_profiles=(existing_profile,),
    )


# =====================================================================
# Verifies that saving a different configuration with a colliding
# profile name uses the next deterministic numeric suffix.
# =====================================================================


def test_save_config_profile_resolves_name_collision() -> None:
    existing_config = AppConfig(
        source=SourceConfig(
            apple_watch_source="Existing Watch",
            apple_health_app_source="Existing Health",
        ),
    )
    new_config = AppConfig(
        source=SourceConfig(
            apple_watch_source="New Watch",
            apple_health_app_source="New Health",
        ),
    )

    existing_profile = ConfigProfile(
        file_id="existing-config",
        name="Cutting.toml",
    )

    uploaded_name = None

    class FakeDriveClient:
        def get_metadata(self, file_id):
            assert file_id == "existing-config"

            return SimpleNamespace(
                size_bytes=len(TomlRenderer.render(existing_config).encode("utf-8")),
            )

        def download_file(
            self,
            file_id,
            destination_path,
            *,
            max_bytes,
        ):
            assert file_id == "existing-config"

            destination_path.write_text(
                TomlRenderer.render(existing_config),
                encoding="utf-8",
            )

        def upload_file(
            self,
            name,
            content,
            mime_type,
            parent_id=None,
            app_properties=None,
        ):
            nonlocal uploaded_name
            uploaded_name = name

    save_config_profile(
        FakeDriveClient(),
        config_container_id="config-container",
        name="Cutting",
        config=new_config,
        existing_profiles=(existing_profile,),
    )

    assert uploaded_name == "Cutting_2.toml"


# =====================================================================
# Verifies that configuration autosave performs no Drive operations when
# the session autosave preference is disabled.
# =====================================================================


def test_config_autosave_does_nothing_when_disabled() -> None:
    class FakeDriveClient:
        def __getattr__(self, name):
            raise AssertionError(
                f"Drive must not be accessed when config autosave is disabled: {name}"
            )

    autosave_config_profile(
        FakeDriveClient(),
        enabled=False,
        config_container_id="config-container",
        name="Autosaved config",
        config=AppConfig(),
        existing_profiles=(),
    )


# =====================================================================
# Verifies that enabled configuration autosave delegates to the normal
# configuration profile save flow.
# =====================================================================


def test_config_autosave_saves_when_enabled(monkeypatch) -> None:
    calls = []

    def fake_save_config_profile(
        client,
        *,
        config_container_id,
        name,
        config,
        existing_profiles=(),
    ):
        calls.append(
            (
                client,
                config_container_id,
                name,
                config,
                existing_profiles,
            )
        )

    monkeypatch.setattr(
        "connected_health.google.config_profiles.save_config_profile",
        fake_save_config_profile,
    )

    client = object()
    config = AppConfig()
    existing_profiles = (
        ConfigProfile(
            file_id="existing-config",
            name="Existing",
        ),
    )

    autosave_config_profile(
        client,
        enabled=True,
        config_container_id="config-container",
        name="Autosaved config",
        config=config,
        existing_profiles=existing_profiles,
    )

    assert calls == [
        (
            client,
            "config-container",
            "Autosaved config",
            config,
            existing_profiles,
        )
    ]
