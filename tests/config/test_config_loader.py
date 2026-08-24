from pathlib import Path

from apple_health.config.app_config import AppConfig
from apple_health.config.config_loader import ConfigLoader

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