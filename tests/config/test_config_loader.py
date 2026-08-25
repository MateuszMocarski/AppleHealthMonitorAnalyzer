from datetime import time
from pathlib import Path

import pytest

from apple_health.config.app_config import AppConfig
from apple_health.config.config_loader import ConfigLoader
from apple_health.config.exceptions import ConfigurationError


def _write_config(
    tmp_path: Path,
    content: str,
) -> Path:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        content,
        encoding="utf-8",
    )
    return config_path


# =====================================================================
# Defaults and source configuration
# =====================================================================


def test_load_without_path_returns_default_app_config() -> None:
    config = ConfigLoader.load(None)

    assert config == AppConfig()


def test_loads_source_config_from_toml(
    tmp_path: Path,
) -> None:
    config_path = _write_config(
        tmp_path,
        """
        [source]
        apple_watch_source = "Custom Watch"
        apple_health_app_source = "Custom Health"
        """,
    )

    config = ConfigLoader.load(config_path)

    assert config.source.apple_watch_source == "Custom Watch"
    assert config.source.apple_health_app_source == "Custom Health"


def test_partial_source_config_preserves_defaults(
    tmp_path: Path,
) -> None:
    config_path = _write_config(
        tmp_path,
        """
        [source]
        apple_watch_source = "Custom Watch"
        """,
    )

    config = ConfigLoader.load(config_path)

    assert config.source.apple_watch_source == "Custom Watch"
    assert config.source.apple_health_app_source == "Zdrowie"


def test_config_keys_are_case_insensitive(
    tmp_path: Path,
) -> None:
    config_path = _write_config(
        tmp_path,
        """
        [SlEeP.ScOrE.DuRaTiOn]
        TaRgEt_MiNuTeS = 450
        """,
    )

    config = ConfigLoader.load(config_path)

    assert config.sleep.score.duration.target_minutes == 450


# =====================================================================
# File and schema errors
# =====================================================================


def test_unknown_source_field_raises_configuration_error(
    tmp_path: Path,
) -> None:
    config_path = _write_config(
        tmp_path,
        """
        [source]
        apple_watch_soruce = "Custom Watch"
        """,
    )

    with pytest.raises(
        ConfigurationError,
        match="source.apple_watch_soruce",
    ):
        ConfigLoader.load(config_path)


def test_unknown_nested_field_raises_configuration_error(
    tmp_path: Path,
) -> None:
    config_path = _write_config(
        tmp_path,
        """
        [sleep.score.duration]
        target_minuts = 450
        """,
    )

    with pytest.raises(
        ConfigurationError,
        match="sleep.score.duration.target_minuts",
    ):
        ConfigLoader.load(config_path)


def test_unknown_top_level_section_raises_configuration_error(
    tmp_path: Path,
) -> None:
    config_path = _write_config(
        tmp_path,
        """
        [magic]
        unicorn_factor = 2137
        """,
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
    config_path = _write_config(
        tmp_path,
        """
        [source
        apple_watch_source = "Custom Watch"
        """,
    )

    with pytest.raises(
        ConfigurationError,
        match="Invalid TOML configuration",
    ):
        ConfigLoader.load(config_path)


# =====================================================================
# Sleep configuration
# =====================================================================


def test_loads_sleep_config_from_toml(
    tmp_path: Path,
) -> None:
    config_path = _write_config(
        tmp_path,
        """
        [sleep]
        session_gap_threshold_minutes = 60
        """,
    )

    config = ConfigLoader.load(config_path)

    assert config.sleep.session_gap_threshold_minutes == 60


def test_sleep_config_preserves_default_score_config(
    tmp_path: Path,
) -> None:
    config_path = _write_config(
        tmp_path,
        """
        [sleep]
        session_gap_threshold_minutes = 60
        """,
    )

    config = ConfigLoader.load(config_path)

    assert config.sleep.score == AppConfig().sleep.score


def test_loads_sleep_score_config_from_toml(
    tmp_path: Path,
) -> None:
    config_path = _write_config(
        tmp_path,
        """
        [sleep.score]
        linear_penalties = true
        """,
    )

    config = ConfigLoader.load(config_path)

    assert config.sleep.score.linear_penalties is True


# =====================================================================
# Bedtime configuration
# =====================================================================


def test_loads_bedtime_score_config_from_toml(
    tmp_path: Path,
) -> None:
    config_path = _write_config(
        tmp_path,
        """
        [sleep.score.bedtime]
        target = "23:30"
        penalty_interval_minutes = 10
        penalty_points = 4.0
        """,
    )

    config = ConfigLoader.load(config_path)
    bedtime = config.sleep.score.bedtime

    assert bedtime.target == time(23, 30)
    assert bedtime.penalty_interval_minutes == 10
    assert bedtime.penalty_points == 4.0


@pytest.mark.parametrize(
    "invalid_time",
    [
        "23:30:00",
        "not-a-time",
        "24:00",
    ],
)
def test_invalid_bedtime_target_raises_configuration_error(
    tmp_path: Path,
    invalid_time: str,
) -> None:
    config_path = _write_config(
        tmp_path,
        f"""
        [sleep.score.bedtime]
        target = "{invalid_time}"
        """,
    )

    with pytest.raises(
        ConfigurationError,
        match="sleep.score.bedtime.target",
    ):
        ConfigLoader.load(config_path)


# =====================================================================
# Duration and wake-up configuration
# =====================================================================


def test_loads_duration_score_config_from_toml(
    tmp_path: Path,
) -> None:
    config_path = _write_config(
        tmp_path,
        """
        [sleep.score.duration]
        target_minutes = 450
        tolerance_minutes = 20
        penalty_interval_minutes = 10
        penalty_points = 4
        oversleep_weight = 0.5
        undersleep_weight = 1.5
        """,
    )

    config = ConfigLoader.load(config_path)
    duration = config.sleep.score.duration

    assert duration.target_minutes == 450
    assert duration.tolerance_minutes == 20
    assert duration.penalty_interval_minutes == 10
    assert duration.penalty_points == 4.0
    assert duration.oversleep_weight == 0.5
    assert duration.undersleep_weight == 1.5


def test_loads_wake_up_score_config_from_toml(
    tmp_path: Path,
) -> None:
    config_path = _write_config(
        tmp_path,
        """
        [sleep.score.wake_up]
        target = "07:30"
        bedtime_weight = 2
        duration_weight = 3.5
        penalty_interval_minutes = 10
        penalty_points = 2
        """,
    )

    config = ConfigLoader.load(config_path)
    wake_up = config.sleep.score.wake_up

    assert wake_up.target == time(7, 30)
    assert wake_up.bedtime_weight == 2.0
    assert wake_up.duration_weight == 3.5
    assert wake_up.penalty_interval_minutes == 10
    assert wake_up.penalty_points == 2.0


# =====================================================================
# Daily score weights and monthly bonuses
# =====================================================================


def test_loads_sleep_score_weights_from_toml(
    tmp_path: Path,
) -> None:
    config_path = _write_config(
        tmp_path,
        """
        [sleep.score.weights]
        bedtime = 1
        duration = 2.5
        wake_up = 3
        """,
    )

    config = ConfigLoader.load(config_path)
    weights = config.sleep.score.weights

    assert weights.bedtime == 1.0
    assert weights.duration == 2.5
    assert weights.wake_up == 3.0


def test_loads_monthly_bonus_config_from_toml(
    tmp_path: Path,
) -> None:
    config_path = _write_config(
        tmp_path,
        """
        [sleep.score.monthly_bonus]
        enabled = true
        max_points = 20

        average_thresholds = [
            [95, 12],
            [85, 8],
            [75, 4],
        ]

        consistency_thresholds = [
            [2, 5],
            [5, 3],
            [10, 1],
        ]
        """,
    )

    config = ConfigLoader.load(config_path)
    bonus = config.sleep.score.monthly_bonus

    assert bonus.enabled is True
    assert bonus.max_points == 20
    assert bonus.average_thresholds == (
        (95.0, 12.0),
        (85.0, 8.0),
        (75.0, 4.0),
    )
    assert bonus.consistency_thresholds == (
        (2.0, 5.0),
        (5.0, 3.0),
        (10.0, 1.0),
    )


# =====================================================================
# Type conversion and validation
# =====================================================================


def test_numeric_strings_are_coerced_for_numeric_fields(
    tmp_path: Path,
) -> None:
    config_path = _write_config(
        tmp_path,
        """
        [sleep]
        session_gap_threshold_minutes = "45"

        [sleep.score.duration]
        target_minutes = "450"
        penalty_points = "3.5"
        """,
    )

    config = ConfigLoader.load(config_path)

    assert config.sleep.session_gap_threshold_minutes == 45
    assert config.sleep.score.duration.target_minutes == 450
    assert config.sleep.score.duration.penalty_points == 3.5


@pytest.mark.parametrize(
    ("toml", "expected_path"),
    [
        (
            """
            [sleep]
            session_gap_threshold_minutes = "abc"
            """,
            "sleep.session_gap_threshold_minutes",
        ),
        (
            """
            [sleep.score]
            linear_penalties = "true"
            """,
            "sleep.score.linear_penalties",
        ),
        (
            """
            [source]
            apple_watch_source = 123
            """,
            "source.apple_watch_source",
        ),
    ],
)
def test_invalid_value_types_raise_configuration_error(
    tmp_path: Path,
    toml: str,
    expected_path: str,
) -> None:
    config_path = _write_config(
        tmp_path,
        toml,
    )

    with pytest.raises(
        ConfigurationError,
        match=expected_path,
    ):
        ConfigLoader.load(config_path)


def test_invalid_threshold_shape_raises_configuration_error(
    tmp_path: Path,
) -> None:
    config_path = _write_config(
        tmp_path,
        """
        [sleep.score.monthly_bonus]
        average_thresholds = [
            [90, 15, 5],
        ]
        """,
    )

    with pytest.raises(
        ConfigurationError,
        match=r"average_thresholds\[0\]",
    ):
        ConfigLoader.load(config_path)


def test_invalid_sleep_configuration_is_wrapped_as_configuration_error(
    tmp_path: Path,
) -> None:
    config_path = _write_config(
        tmp_path,
        """
        [sleep.score.duration]
        target_minutes = -1
        """,
    )

    with pytest.raises(
        ConfigurationError,
        match="Sleep duration target must be greater than zero",
    ):
        ConfigLoader.load(config_path)


def test_partial_nested_config_preserves_unset_defaults(
    tmp_path: Path,
) -> None:
    config_path = _write_config(
        tmp_path,
        """
        [sleep.score.duration]
        target_minutes = 450
        """,
    )

    config = ConfigLoader.load(config_path)
    defaults = AppConfig()

    assert config.sleep.score.duration.target_minutes == 450
    assert (
        config.sleep.score.duration.tolerance_minutes
        == defaults.sleep.score.duration.tolerance_minutes
    )
    assert config.sleep.score.bedtime == defaults.sleep.score.bedtime
    assert config.source == defaults.source
