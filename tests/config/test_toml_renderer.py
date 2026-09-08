from datetime import time

from apple_health.config.app_config import AppConfig
from apple_health.config.config_loader import ConfigLoader
from apple_health.config.source_config import SourceConfig
from apple_health.config.toml_renderer import (
    TomlRenderer,
    semantic_fingerprint,
)

# =====================================================================
# Verifies that the canonical TOML contains the effective source
# configuration values.
# =====================================================================


def test_toml_renderer_renders_effective_source_config() -> None:
    config = AppConfig(
        source=SourceConfig(
            apple_watch_source="Watch",
            apple_health_app_source="Health",
        ),
    )

    rendered = TomlRenderer.render(config)

    assert rendered.startswith(
        "[source]\n" 'apple_watch_source = "Watch"\n' 'apple_health_app_source = "Health"\n'
    )


# =====================================================================
# Verifies that TomlRenderer serializes the effective top-level sleep
# configuration after the source section.
# =====================================================================


def test_toml_renderer_renders_effective_sleep_config() -> None:
    config = AppConfig()
    config.sleep.session_gap_threshold_minutes = 45

    rendered = TomlRenderer.render(config)

    assert "[sleep]\n" in rendered
    assert "session_gap_threshold_minutes = 45\n" in rendered


# =====================================================================
# Verifies that TomlRenderer serializes the effective sleep score mode
# using canonical TOML boolean syntax.
# =====================================================================


def test_toml_renderer_renders_sleep_score_linear_penalties() -> None:
    config = AppConfig()
    config.sleep.score.linear_penalties = True

    rendered = TomlRenderer.render(config)

    assert "[sleep.score]\n" in rendered
    assert "linear_penalties = true\n" in rendered


# =====================================================================
# Verifies that TomlRenderer serializes bedtime target using the
# canonical HH:MM format accepted by ConfigLoader.
# =====================================================================


def test_toml_renderer_renders_bedtime_target_as_hh_mm() -> None:
    config = AppConfig()
    config.sleep.score.bedtime.target = time(23, 30)

    rendered = TomlRenderer.render(config)

    assert "[sleep.score.bedtime]\n" in rendered
    assert 'target = "23:30"\n' in rendered


# =====================================================================
# Verifies that TomlRenderer serializes the complete bedtime score
# configuration using stable numeric TOML values.
# =====================================================================


def test_toml_renderer_renders_complete_bedtime_config() -> None:
    config = AppConfig()
    config.sleep.score.bedtime.penalty_interval_minutes = 10
    config.sleep.score.bedtime.penalty_points = 4.5

    rendered = TomlRenderer.render(config)

    assert "penalty_interval_minutes = 10\n" in rendered
    assert "penalty_points = 4.5\n" in rendered


# =====================================================================
# Verifies that TomlRenderer serializes the complete sleep duration
# score configuration in deterministic field order.
# =====================================================================


def test_toml_renderer_renders_complete_duration_config() -> None:
    config = AppConfig()
    config.sleep.score.duration.target_minutes = 450
    config.sleep.score.duration.tolerance_minutes = 20
    config.sleep.score.duration.penalty_interval_minutes = 10
    config.sleep.score.duration.penalty_points = 4.0
    config.sleep.score.duration.oversleep_weight = 0.5
    config.sleep.score.duration.undersleep_weight = 1.5

    rendered = TomlRenderer.render(config)

    assert (
        "[sleep.score.duration]\n"
        "target_minutes = 450\n"
        "tolerance_minutes = 20\n"
        "penalty_interval_minutes = 10\n"
        "penalty_points = 4.0\n"
        "oversleep_weight = 0.5\n"
        "undersleep_weight = 1.5\n"
    ) in rendered


# =====================================================================
# Verifies that TomlRenderer serializes the complete wake-up score
# configuration using canonical time and numeric TOML values.
# =====================================================================


def test_toml_renderer_renders_complete_wake_up_config() -> None:
    config = AppConfig()
    config.sleep.score.wake_up.target = time(7, 45)
    config.sleep.score.wake_up.bedtime_weight = 1.5
    config.sleep.score.wake_up.duration_weight = 2.5
    config.sleep.score.wake_up.penalty_interval_minutes = 10
    config.sleep.score.wake_up.penalty_points = 2.0

    rendered = TomlRenderer.render(config)

    assert (
        "[sleep.score.wake_up]\n"
        'target = "07:45"\n'
        "bedtime_weight = 1.5\n"
        "duration_weight = 2.5\n"
        "penalty_interval_minutes = 10\n"
        "penalty_points = 2.0\n"
    ) in rendered


# =====================================================================
# Verifies that TomlRenderer serializes the complete sleep score
# component weights in deterministic field order.
# =====================================================================


def test_toml_renderer_renders_complete_score_weights() -> None:
    config = AppConfig()
    config.sleep.score.weights.bedtime = 1.5
    config.sleep.score.weights.duration = 2.0
    config.sleep.score.weights.wake_up = 0.5

    rendered = TomlRenderer.render(config)

    assert (
        "[sleep.score.weights]\n" "bedtime = 1.5\n" "duration = 2.0\n" "wake_up = 0.5\n"
    ) in rendered


# =====================================================================
# Verifies that TomlRenderer serializes monthly bonus scalar settings
# using canonical TOML boolean and integer values.
# =====================================================================


def test_toml_renderer_renders_monthly_bonus_scalars() -> None:
    config = AppConfig()
    config.sleep.score.monthly_bonus.enabled = False
    config.sleep.score.monthly_bonus.max_points = 25

    rendered = TomlRenderer.render(config)

    assert ("[sleep.score.monthly_bonus]\n" "enabled = false\n" "max_points = 25\n") in rendered


# =====================================================================
# Verifies that TomlRenderer serializes average monthly bonus
# thresholds as canonical arrays of numeric pairs.
# =====================================================================


def test_toml_renderer_renders_average_bonus_thresholds() -> None:
    config = AppConfig()
    config.sleep.score.monthly_bonus.average_thresholds = (
        (92, 12),
        (81.5, 7.5),
    )

    rendered = TomlRenderer.render(config)

    assert ("average_thresholds = " "[[92.0, 12.0], [81.5, 7.5]]\n") in rendered


# =====================================================================
# Verifies that TomlRenderer serializes consistency monthly bonus
# thresholds as canonical arrays of numeric pairs.
# =====================================================================


def test_toml_renderer_renders_consistency_bonus_thresholds() -> None:
    config = AppConfig()
    config.sleep.score.monthly_bonus.consistency_thresholds = (
        (2, 6),
        (7.5, 3.5),
    )

    rendered = TomlRenderer.render(config)

    assert ("consistency_thresholds = " "[[2.0, 6.0], [7.5, 3.5]]\n") in rendered


# =====================================================================
# Verifies that canonical TOML can be loaded back into the same
# effective AppConfig even when string values require escaping.
# =====================================================================


def test_toml_renderer_round_trips_effective_config(tmp_path) -> None:
    config = AppConfig()
    config.source.apple_watch_source = 'Watch "Series" \\ Test'
    config.sleep.session_gap_threshold_minutes = 45
    config.sleep.score.linear_penalties = True
    config.sleep.score.bedtime.target = time(23, 30)
    config.sleep.score.duration.target_minutes = 450

    path = tmp_path / "config.toml"
    path.write_text(
        TomlRenderer.render(config),
        encoding="utf-8",
    )

    assert ConfigLoader.load(path) == config


# =====================================================================
# Verifies that semantic config fingerprint is derived deterministically
# from the canonical effective configuration.
# =====================================================================


def test_semantic_fingerprint_is_stable_for_same_config() -> None:
    config = AppConfig()
    config.sleep.score.duration.target_minutes = 450

    assert semantic_fingerprint(config) == semantic_fingerprint(config)


# =====================================================================
# Verifies that semantic config fingerprint normalizes equivalent
# integer and floating-point representations of float settings.
# =====================================================================


def test_semantic_fingerprint_normalizes_float_values() -> None:
    integer_config = AppConfig()
    integer_config.sleep.score.bedtime.penalty_points = 5
    integer_config.sleep.score.duration.penalty_points = 5
    integer_config.sleep.score.duration.oversleep_weight = 1
    integer_config.sleep.score.duration.undersleep_weight = 1
    integer_config.sleep.score.wake_up.bedtime_weight = 1
    integer_config.sleep.score.wake_up.duration_weight = 2
    integer_config.sleep.score.wake_up.penalty_points = 3
    integer_config.sleep.score.weights.bedtime = 1
    integer_config.sleep.score.weights.duration = 1
    integer_config.sleep.score.weights.wake_up = 1

    float_config = AppConfig()
    float_config.sleep.score.bedtime.penalty_points = 5.0
    float_config.sleep.score.duration.penalty_points = 5.0
    float_config.sleep.score.duration.oversleep_weight = 1.0
    float_config.sleep.score.duration.undersleep_weight = 1.0
    float_config.sleep.score.wake_up.bedtime_weight = 1.0
    float_config.sleep.score.wake_up.duration_weight = 2.0
    float_config.sleep.score.wake_up.penalty_points = 3.0
    float_config.sleep.score.weights.bedtime = 1.0
    float_config.sleep.score.weights.duration = 1.0
    float_config.sleep.score.weights.wake_up = 1.0

    assert semantic_fingerprint(integer_config) == semantic_fingerprint(float_config)


# =====================================================================
# Verifies that changing effective configuration semantics changes the
# semantic fingerprint.
# =====================================================================


def test_semantic_fingerprint_changes_when_config_changes() -> None:
    first = AppConfig()
    second = AppConfig()

    second.sleep.score.duration.target_minutes = 450

    assert semantic_fingerprint(first) != semantic_fingerprint(second)


# =====================================================================
# Verifies that TomlRenderer produces the complete canonical TOML
# representation of the default effective AppConfig.
# =====================================================================


def test_toml_renderer_renders_default_config_canonically() -> None:
    assert TomlRenderer.render(AppConfig()) == (
        "[source]\n"
        'apple_watch_source = "Apple\u00a0Watch"\n'
        'apple_health_app_source = "Zdrowie"\n'
        "\n"
        "[sleep]\n"
        "session_gap_threshold_minutes = 30\n"
        "\n"
        "[sleep.score]\n"
        "linear_penalties = false\n"
        "\n"
        "[sleep.score.bedtime]\n"
        'target = "00:00"\n'
        "penalty_interval_minutes = 15\n"
        "penalty_points = 5.0\n"
        "\n"
        "[sleep.score.duration]\n"
        "target_minutes = 480\n"
        "tolerance_minutes = 30\n"
        "penalty_interval_minutes = 15\n"
        "penalty_points = 5.0\n"
        "oversleep_weight = 1.0\n"
        "undersleep_weight = 1.0\n"
        "\n"
        "[sleep.score.wake_up]\n"
        'target = "08:00"\n'
        "bedtime_weight = 1.0\n"
        "duration_weight = 2.0\n"
        "penalty_interval_minutes = 15\n"
        "penalty_points = 3.0\n"
        "\n"
        "[sleep.score.weights]\n"
        "bedtime = 1.0\n"
        "duration = 1.0\n"
        "wake_up = 1.0\n"
        "\n"
        "[sleep.score.monthly_bonus]\n"
        "enabled = true\n"
        "max_points = 20\n"
        "average_thresholds = "
        "[[90.0, 15.0], [80.0, 10.0], [70.0, 5.0]]\n"
        "consistency_thresholds = "
        "[[3.0, 5.0], [6.0, 4.0], [9.0, 3.0], "
        "[12.0, 2.0], [15.0, 1.0]]\n"
    )
