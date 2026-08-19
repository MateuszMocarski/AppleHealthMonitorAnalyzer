import pytest

import apple_health.sleep_score_config as config
from apple_health.sleep_score_config import validate_sleep_score_config

# =====================================================================
# Verifies that the default sleep score configuration satisfies all
# validation rules and can be used without raising an exception.
# =====================================================================


def test_default_sleep_score_config_is_valid() -> None:
    validate_sleep_score_config()


# =====================================================================
# Verifies that every daily Sleep Score component weight must be
# non-negative.
# =====================================================================


@pytest.mark.parametrize(
    "setting_name",
    [
        "BEDTIME_SCORE_WEIGHT",
        "SLEEP_DURATION_SCORE_WEIGHT",
        "WAKE_UP_SCORE_WEIGHT",
    ],
)
def test_negative_score_component_weight_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    setting_name: str,
) -> None:
    monkeypatch.setattr(
        config,
        setting_name,
        -1.0,
    )

    with pytest.raises(
        ValueError,
        match="Sleep score component weights cannot be negative",
    ):
        validate_sleep_score_config()


# =====================================================================
# Verifies that at least one daily Sleep Score component must have a
# positive weight so the final weighted score can be calculated.
# =====================================================================


def test_all_zero_score_component_weights_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        config,
        "BEDTIME_SCORE_WEIGHT",
        0.0,
    )
    monkeypatch.setattr(
        config,
        "SLEEP_DURATION_SCORE_WEIGHT",
        0.0,
    )
    monkeypatch.setattr(
        config,
        "WAKE_UP_SCORE_WEIGHT",
        0.0,
    )

    with pytest.raises(
        ValueError,
        match="At least one sleep score component weight",
    ):
        validate_sleep_score_config()


# =====================================================================
# Verifies that every configured penalty interval must be greater than
# zero to avoid invalid penalty calculations.
# =====================================================================


@pytest.mark.parametrize(
    ("setting_name", "invalid_value"),
    [
        ("BEDTIME_PENALTY_INTERVAL_MINUTES", 0),
        ("BEDTIME_PENALTY_INTERVAL_MINUTES", -1),
        ("SLEEP_DURATION_PENALTY_INTERVAL_MINUTES", 0),
        ("SLEEP_DURATION_PENALTY_INTERVAL_MINUTES", -1),
        ("WAKE_UP_PENALTY_INTERVAL_MINUTES", 0),
        ("WAKE_UP_PENALTY_INTERVAL_MINUTES", -1),
    ],
)
def test_non_positive_penalty_interval_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    setting_name: str,
    invalid_value: int,
) -> None:
    monkeypatch.setattr(
        config,
        setting_name,
        invalid_value,
    )

    with pytest.raises(
        ValueError,
        match="Sleep score penalty intervals must be greater than zero",
    ):
        validate_sleep_score_config()


# =====================================================================
# Verifies that penalty points cannot be negative for any Sleep Score
# component.
# =====================================================================


@pytest.mark.parametrize(
    "setting_name",
    [
        "BEDTIME_PENALTY_POINTS",
        "SLEEP_DURATION_PENALTY_POINTS",
        "WAKE_UP_PENALTY_POINTS",
    ],
)
def test_negative_penalty_points_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
    setting_name: str,
) -> None:
    monkeypatch.setattr(
        config,
        setting_name,
        -1,
    )

    with pytest.raises(
        ValueError,
        match="Sleep score penalty points cannot be negative",
    ):
        validate_sleep_score_config()


# =====================================================================
# Verifies that the configured sleep duration target must be greater
# than zero.
# =====================================================================


@pytest.mark.parametrize(
    "invalid_target",
    [
        0,
        -1,
    ],
)
def test_non_positive_sleep_duration_target_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    invalid_target: int,
) -> None:
    monkeypatch.setattr(
        config,
        "SLEEP_DURATION_TARGET_MINUTES",
        invalid_target,
    )

    with pytest.raises(
        ValueError,
        match="Sleep duration target must be greater than zero",
    ):
        validate_sleep_score_config()


# =====================================================================
# Verifies that sleep duration tolerance cannot be negative.
# =====================================================================


def test_negative_sleep_duration_tolerance_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        config,
        "SLEEP_DURATION_TOLERANCE_MINUTES",
        -1,
    )

    with pytest.raises(
        ValueError,
        match="Sleep duration tolerance cannot be negative",
    ):
        validate_sleep_score_config()


# =====================================================================
# Verifies that sleep duration tolerance must remain lower than the
# configured target duration.
# =====================================================================


@pytest.mark.parametrize(
    "tolerance_offset",
    [
        0,
        1,
    ],
)
def test_sleep_duration_tolerance_not_lower_than_target_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    tolerance_offset: int,
) -> None:
    monkeypatch.setattr(
        config,
        "SLEEP_DURATION_TOLERANCE_MINUTES",
        config.SLEEP_DURATION_TARGET_MINUTES + tolerance_offset,
    )

    with pytest.raises(
        ValueError,
        match="Sleep duration tolerance must be lower",
    ):
        validate_sleep_score_config()


# =====================================================================
# Verifies that oversleep and undersleep penalty weights cannot be
# negative.
# =====================================================================


@pytest.mark.parametrize(
    "setting_name",
    [
        "SLEEP_DURATION_OVERSLEEP_WEIGHT",
        "SLEEP_DURATION_UNDERSLEEP_WEIGHT",
    ],
)
def test_negative_duration_penalty_weight_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    setting_name: str,
) -> None:
    monkeypatch.setattr(
        config,
        setting_name,
        -1.0,
    )

    with pytest.raises(
        ValueError,
        match="Sleep duration penalty weights cannot be negative",
    ):
        validate_sleep_score_config()


# =====================================================================
# Verifies that monthly average bonus score thresholds must stay within
# the valid Daily Sleep Score range of 0-100.
# =====================================================================


@pytest.mark.parametrize(
    "invalid_threshold",
    [
        -1,
        101,
    ],
)
def test_average_bonus_threshold_outside_score_range_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    invalid_threshold: int,
) -> None:
    monkeypatch.setattr(
        config,
        "SLEEP_AVERAGE_BONUS_THRESHOLDS",
        (
            (invalid_threshold, 15),
            (80, 10),
            (70, 5),
        ),
    )

    with pytest.raises(
        ValueError,
        match="Sleep average bonus thresholds must be between 0 and 100",
    ):
        validate_sleep_score_config()


# =====================================================================
# Verifies that monthly average bonus points cannot be negative.
# =====================================================================


def test_negative_average_bonus_points_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        config,
        "SLEEP_AVERAGE_BONUS_THRESHOLDS",
        (
            (90, -1),
            (80, 0),
            (70, 0),
        ),
    )

    with pytest.raises(
        ValueError,
        match="Sleep average bonus points cannot be negative",
    ):
        validate_sleep_score_config()


# =====================================================================
# Verifies that average bonus score thresholds must be ordered from
# highest to lowest without duplicate or increasing thresholds.
# =====================================================================


def test_average_bonus_thresholds_must_be_strictly_decreasing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        config,
        "SLEEP_AVERAGE_BONUS_THRESHOLDS",
        (
            (90, 15),
            (90, 10),
            (70, 5),
        ),
    )

    with pytest.raises(
        ValueError,
        match="Sleep average bonus thresholds must be strictly decreasing",
    ):
        validate_sleep_score_config()


# =====================================================================
# Verifies that lowering the required average Sleep Score cannot grant
# a larger bonus than a higher score threshold.
# =====================================================================


def test_average_bonus_points_cannot_increase_as_threshold_decreases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        config,
        "SLEEP_AVERAGE_BONUS_THRESHOLDS",
        (
            (90, 10),
            (80, 15),
            (70, 5),
        ),
    )

    with pytest.raises(
        ValueError,
        match="Sleep average bonus points cannot increase",
    ):
        validate_sleep_score_config()


# =====================================================================
# Verifies that consistency bonus deviation thresholds must always be
# greater than zero.
# =====================================================================


@pytest.mark.parametrize(
    "invalid_threshold",
    [
        0,
        -1,
    ],
)
def test_non_positive_consistency_threshold_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    invalid_threshold: int,
) -> None:
    monkeypatch.setattr(
        config,
        "SLEEP_CONSISTENCY_BONUS_THRESHOLDS",
        (
            (invalid_threshold, 5),
            (6, 4),
            (9, 3),
        ),
    )

    with pytest.raises(
        ValueError,
        match="Sleep consistency thresholds must be greater than zero",
    ):
        validate_sleep_score_config()


# =====================================================================
# Verifies that consistency bonus points cannot be negative.
# =====================================================================


def test_negative_consistency_bonus_points_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        config,
        "SLEEP_CONSISTENCY_BONUS_THRESHOLDS",
        (
            (3, -1),
            (6, 0),
            (9, 0),
        ),
    )

    with pytest.raises(
        ValueError,
        match="Sleep consistency bonus points cannot be negative",
    ):
        validate_sleep_score_config()


# =====================================================================
# Verifies that consistency deviation thresholds must be ordered from
# lowest to highest without duplicate or decreasing values.
# =====================================================================


def test_consistency_thresholds_must_be_strictly_increasing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        config,
        "SLEEP_CONSISTENCY_BONUS_THRESHOLDS",
        (
            (3, 5),
            (3, 4),
            (9, 3),
        ),
    )

    with pytest.raises(
        ValueError,
        match="Sleep consistency thresholds must be strictly increasing",
    ):
        validate_sleep_score_config()


# =====================================================================
# Verifies that allowing greater Sleep Score deviation cannot grant a
# larger consistency bonus than a stricter deviation threshold.
# =====================================================================


def test_consistency_bonus_points_cannot_increase_as_deviation_increases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        config,
        "SLEEP_CONSISTENCY_BONUS_THRESHOLDS",
        (
            (3, 4),
            (6, 5),
            (9, 3),
        ),
    )

    with pytest.raises(
        ValueError,
        match="Sleep consistency bonus points cannot increase",
    ):
        validate_sleep_score_config()


# =====================================================================
# Verifies that the maximum possible average and consistency bonuses
# cannot exceed the configured monthly bonus cap.
# =====================================================================


def test_combined_monthly_bonus_cannot_exceed_configured_maximum(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        config,
        "SLEEP_MONTHLY_BONUS_MAX_POINTS",
        19,
    )

    with pytest.raises(
        ValueError,
        match="Maximum configured monthly sleep bonuses exceed",
    ):
        validate_sleep_score_config()
