from health_analyzer.config.app_config import AppConfig
from health_analyzer.config.sleep_config import SleepConfig
from health_analyzer.config.source_config import SourceConfig

# =====================================================================
# Verifies that AppConfig composes the default source and sleep
# configuration objects used by the application.
# =====================================================================


def test_app_config_uses_default_configuration() -> None:
    config = AppConfig()

    assert isinstance(
        config.source,
        SourceConfig,
    )

    assert isinstance(
        config.sleep,
        SleepConfig,
    )

    assert config.source.apple_watch_source == "Apple\xa0Watch"

    assert config.source.health_analyzer_app_source == "Zdrowie"

    assert config.sleep.session_gap_threshold_minutes == 30
