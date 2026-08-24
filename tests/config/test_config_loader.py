from pathlib import Path

import pytest

from apple_health.config.app_config import AppConfig
from apple_health.config.config_loader import ConfigLoader
from apple_health.config.exceptions import ConfigurationError

def test_load_without_path_returns_default_app_config() -> None:
    config = ConfigLoader.load(None)

    assert config == AppConfig()
    
def test_loads_source_config_from_toml(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.toml"

    config_path.write_text(
        """
        [source]
        apple_watch_source = "Custom Watch"
        apple_health_app_source = "Custom Health"
        """,
        encoding="utf-8",
    )

    config = ConfigLoader.load(config_path)

    assert config.source.apple_watch_source == "Custom Watch"
    assert config.source.apple_health_app_source == "Custom Health"
    
def test_partial_source_config_preserves_defaults(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.toml"

    config_path.write_text(
        """
        [source]
        apple_watch_source = "Custom Watch"
        """,
        encoding="utf-8",
    )

    config = ConfigLoader.load(config_path)

    assert config.source.apple_watch_source == "Custom Watch"
    assert config.source.apple_health_app_source == "Zdrowie"
    
def test_source_config_keys_are_case_insensitive(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.toml"

    config_path.write_text(
        """
        [SoUrCe]
        ApPlE_WaTcH_SoUrCe = "Custom Watch"
        ApPlE_HeAlTh_ApP_SoUrCe = "Custom Health"
        """,
        encoding="utf-8",
    )

    config = ConfigLoader.load(config_path)

    assert config.source.apple_watch_source == "Custom Watch"
    assert config.source.apple_health_app_source == "Custom Health"
    
def test_unknown_source_field_raises_configuration_error(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.toml"

    config_path.write_text(
        """
        [source]
        apple_watch_soruce = "Custom Watch"
        """,
        encoding="utf-8",
    )

    with pytest.raises(
        ConfigurationError,
        match="source.apple_watch_soruce",
    ):
        ConfigLoader.load(config_path)
        
def test_unknown_top_level_section_raises_configuration_error(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.toml"

    config_path.write_text(
        """
        [magic]
        unicorn_factor = 2137
        """,
        encoding="utf-8",
    )

    with pytest.raises(
        ConfigurationError,
        match="magic",
    ):
        ConfigLoader.load(config_path)
        
def test_missing_config_file_raises_configuration_error(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "missing.toml"

    with pytest.raises(
        ConfigurationError,
        match="Configuration file not found",
    ):
        ConfigLoader.load(config_path)
        
def test_malformed_toml_raises_configuration_error(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.toml"

    config_path.write_text(
        """
        [source
        apple_watch_source = "Custom Watch"
        """,
        encoding="utf-8",
    )

    with pytest.raises(
        ConfigurationError,
        match="Invalid TOML configuration",
    ):
        ConfigLoader.load(config_path)