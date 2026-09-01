import pytest

from apple_health.config.sleep_score_config import SleepScoreConfig


def _set_config_value(
    config: SleepScoreConfig,
    attribute_path: str,
    value,
) -> None:
    target = config

    path_parts = attribute_path.split(".")

    for attribute in path_parts[:-1]:
        target = getattr(
            target,
            attribute,
        )

    setattr(
        target,
        path_parts[-1],
        value,
    )


# =====================================================================
# Verifies that the default sleep score configuration satisfies all
# validation rules and can be used without raising an exception.
# =====================================================================


def test_default_sleep_score_config_is_valid() -> None:
    config = SleepScoreConfig()

    config.validate()


# =====================================================================
# Verifies that negative daily Sleep Score component weights are
# rejected.
# =====================================================================


@pytest.mark.parametrize(
    "attribute_path",
    [
        "weights.bedtime",
        "weights.duration",
        "weights.wake_up",
    ],
)
def test_negative_score_component_weight_is_rejected(
    attribute_path: str,
) -> None:
    config = SleepScoreConfig()

    _set_config_value(
        config,
        attribute_path,
        -1.0,
    )

    with pytest.raises(
        ValueError,
        match="Sleep score component weights cannot be negative",
    ):
        config.validate()


# =====================================================================
# Verifies that at least one daily Sleep Score component must have a
# positive weight so the final weighted score can be calculated.
# =====================================================================


def test_all_zero_score_component_weights_are_rejected() -> None:
    config = SleepScoreConfig()

    config.weights.bedtime = 0.0
    config.weights.duration = 0.0
    config.weights.wake_up = 0.0

    with pytest.raises(
        ValueError,
        match="At least one sleep score component weight",
    ):
        config.validate()


# =====================================================================
# Verifies that zero or negative Sleep Score penalty intervals are
# rejected.
# =====================================================================


@pytest.mark.parametrize(
    ("attribute_path", "invalid_value"),
    [
        ("bedtime.penalty_interval_minutes", 0),
        ("bedtime.penalty_interval_minutes", -1),
        ("duration.penalty_interval_minutes", 0),
        ("duration.penalty_interval_minutes", -1),
        ("wake_up.penalty_interval_minutes", 0),
        ("wake_up.penalty_interval_minutes", -1),
    ],
)
def test_non_positive_penalty_interval_is_rejected(
    attribute_path: str,
    invalid_value: int,
) -> None:
    config = SleepScoreConfig()

    _set_config_value(
        config,
        attribute_path,
        invalid_value,
    )

    with pytest.raises(
        ValueError,
        match="Sleep score penalty intervals must be greater than zero",
    ):
        config.validate()


# =====================================================================
# Verifies that negative Sleep Score penalty-point values are rejected.
# =====================================================================


@pytest.mark.parametrize(
    "attribute_path",
    [
        "bedtime.penalty_points",
        "duration.penalty_points",
        "wake_up.penalty_points",
    ],
)
def test_negative_penalty_points_are_rejected(
    attribute_path: str,
) -> None:
    config = SleepScoreConfig()

    _set_config_value(
        config,
        attribute_path,
        -1.0,
    )

    with pytest.raises(
        ValueError,
        match="Sleep score penalty points cannot be negative",
    ):
        config.validate()


# =====================================================================
# Verifies that zero or negative sleep-duration targets are rejected.
# =====================================================================


@pytest.mark.parametrize(
    "invalid_target",
    [
        0,
        -1,
    ],
)
def test_non_positive_sleep_duration_target_is_rejected(
    invalid_target: int,
) -> None:
    config = SleepScoreConfig()

    config.duration.target_minutes = invalid_target

    with pytest.raises(
        ValueError,
        match="Sleep duration target must be greater than zero",
    ):
        config.validate()


# =====================================================================
# Verifies that sleep duration tolerance cannot be negative.
# =====================================================================


def test_negative_sleep_duration_tolerance_is_rejected() -> None:
    config = SleepScoreConfig()

    config.duration.tolerance_minutes = -1

    with pytest.raises(
        ValueError,
        match="Sleep duration tolerance cannot be negative",
    ):
        config.validate()


# =====================================================================
# Verifies that sleep-duration tolerance must remain strictly lower
# than the target duration.
# =====================================================================


@pytest.mark.parametrize(
    "tolerance_offset",
    [
        0,
        1,
    ],
)
def test_sleep_duration_tolerance_not_lower_than_target_is_rejected(
    tolerance_offset: int,
) -> None:
    config = SleepScoreConfig()

    config.duration.tolerance_minutes = config.duration.target_minutes + tolerance_offset

    with pytest.raises(
        ValueError,
        match="Sleep duration tolerance must be lower",
    ):
        config.validate()


# =====================================================================
# Verifies that negative oversleep and undersleep penalty weights are
# rejected.
# =====================================================================


@pytest.mark.parametrize(
    "attribute_path",
    [
        "duration.oversleep_weight",
        "duration.undersleep_weight",
    ],
)
def test_negative_duration_penalty_weight_is_rejected(
    attribute_path: str,
) -> None:
    config = SleepScoreConfig()

    _set_config_value(
        config,
        attribute_path,
        -1.0,
    )

    with pytest.raises(
        ValueError,
        match="Sleep duration penalty weights cannot be negative",
    ):
        config.validate()


# =====================================================================
# Verifies that monthly average bonus thresholds outside the 0-100
# score range are rejected.
# =====================================================================


@pytest.mark.parametrize(
    "invalid_threshold",
    [
        -1,
        101,
    ],
)
def test_average_bonus_threshold_outside_score_range_is_rejected(
    invalid_threshold: int,
) -> None:
    config = SleepScoreConfig()

    config.monthly_bonus.average_thresholds = (
        (invalid_threshold, 15),
        (80, 10),
        (70, 5),
    )

    with pytest.raises(
        ValueError,
        match="Sleep average bonus thresholds must be between 0 and 100",
    ):
        config.validate()


# =====================================================================
# Verifies that monthly average bonus points cannot be negative.
# =====================================================================


def test_negative_average_bonus_points_are_rejected() -> None:
    config = SleepScoreConfig()

    config.monthly_bonus.average_thresholds = (
        (90, -1),
        (80, 0),
        (70, 0),
    )

    with pytest.raises(
        ValueError,
        match="Sleep average bonus points cannot be negative",
    ):
        config.validate()


# =====================================================================
# Verifies that average bonus score thresholds must be ordered from
# highest to lowest without duplicate or increasing thresholds.
# =====================================================================


def test_average_bonus_thresholds_must_be_strictly_decreasing() -> None:
    config = SleepScoreConfig()

    config.monthly_bonus.average_thresholds = (
        (90, 15),
        (90, 10),
        (70, 5),
    )

    with pytest.raises(
        ValueError,
        match="Sleep average bonus thresholds must be strictly decreasing",
    ):
        config.validate()


# =====================================================================
# Verifies that lowering the required average Sleep Score cannot grant
# a larger bonus than a higher score threshold.
# =====================================================================


def test_average_bonus_points_cannot_increase_as_threshold_decreases() -> None:
    config = SleepScoreConfig()

    config.monthly_bonus.average_thresholds = (
        (90, 10),
        (80, 15),
        (70, 5),
    )

    with pytest.raises(
        ValueError,
        match="Sleep average bonus points cannot increase",
    ):
        config.validate()


# =====================================================================
# Verifies that zero or negative monthly consistency thresholds are
# rejected.
# =====================================================================


@pytest.mark.parametrize(
    "invalid_threshold",
    [
        0,
        -1,
    ],
)
def test_non_positive_consistency_threshold_is_rejected(
    invalid_threshold: int,
) -> None:
    config = SleepScoreConfig()

    config.monthly_bonus.consistency_thresholds = (
        (invalid_threshold, 5),
        (6, 4),
        (9, 3),
    )

    with pytest.raises(
        ValueError,
        match="Sleep consistency thresholds must be greater than zero",
    ):
        config.validate()


# =====================================================================
# Verifies that consistency bonus points cannot be negative.
# =====================================================================


def test_negative_consistency_bonus_points_are_rejected() -> None:
    config = SleepScoreConfig()

    config.monthly_bonus.consistency_thresholds = (
        (3, -1),
        (6, 0),
        (9, 0),
    )

    with pytest.raises(
        ValueError,
        match="Sleep consistency bonus points cannot be negative",
    ):
        config.validate()


# =====================================================================
# Verifies that consistency deviation thresholds must be ordered from
# lowest to highest without duplicate or decreasing values.
# =====================================================================


def test_consistency_thresholds_must_be_strictly_increasing() -> None:
    config = SleepScoreConfig()

    config.monthly_bonus.consistency_thresholds = (
        (3, 5),
        (3, 4),
        (9, 3),
    )

    with pytest.raises(
        ValueError,
        match="Sleep consistency thresholds must be strictly increasing",
    ):
        config.validate()


# =====================================================================
# Verifies that allowing greater Sleep Score deviation cannot grant a
# larger consistency bonus than a stricter deviation threshold.
# =====================================================================


def test_consistency_bonus_points_cannot_increase_as_deviation_increases() -> None:
    config = SleepScoreConfig()

    config.monthly_bonus.consistency_thresholds = (
        (3, 4),
        (6, 5),
        (9, 3),
    )

    with pytest.raises(
        ValueError,
        match="Sleep consistency bonus points cannot increase",
    ):
        config.validate()


# =====================================================================
# Verifies that the maximum possible average and consistency bonuses
# cannot exceed the configured monthly bonus cap.
# =====================================================================


def test_combined_monthly_bonus_cannot_exceed_configured_maximum() -> None:
    config = SleepScoreConfig()

    config.monthly_bonus.max_points = 19

    with pytest.raises(
        ValueError,
        match="Maximum configured monthly sleep bonuses exceed",
    ):
        config.validate()


# =====================================================================
# Verifies that negative wake-up component weights are rejected because
# they cannot represent a valid weighted maximum score.
# =====================================================================


@pytest.mark.parametrize(
    "attribute_path",
    [
        "wake_up.bedtime_weight",
        "wake_up.duration_weight",
    ],
)
def test_negative_wake_up_component_weight_is_rejected(
    attribute_path: str,
) -> None:
    config = SleepScoreConfig()

    _set_config_value(
        config,
        attribute_path,
        -1.0,
    )

    with pytest.raises(
        ValueError,
        match="Wake-up score component weights cannot be negative",
    ):
        config.validate()


# =====================================================================
# Verifies that at least one wake-up component weight must be positive
# so the weighted maximum score cannot divide by zero.
# =====================================================================


def test_all_zero_wake_up_component_weights_are_rejected() -> None:
    config = SleepScoreConfig()

    config.wake_up.bedtime_weight = 0.0
    config.wake_up.duration_weight = 0.0

    with pytest.raises(
        ValueError,
        match="At least one wake-up score component weight",
    ):
        config.validate()


# =====================================================================
# Verifies that programmatically constructed Sleep Score configuration
# also rejects non-finite numeric values.
# =====================================================================


@pytest.mark.parametrize(
    ("attribute_path", "value"),
    [
        ("bedtime.penalty_points", float("nan")),
        ("duration.oversleep_weight", float("inf")),
        ("weights.wake_up", float("-inf")),
    ],
)
def test_non_finite_sleep_score_value_is_rejected(
    attribute_path: str,
    value: float,
) -> None:
    config = SleepScoreConfig()

    _set_config_value(
        config,
        attribute_path,
        value,
    )

    with pytest.raises(
        ValueError,
        match="Sleep score numeric values must be finite",
    ):
        config.validate()


# =====================================================================
# Verifies that non-finite monthly bonus threshold values are rejected
# by the same finite-number validation rule.
# =====================================================================


def test_non_finite_monthly_bonus_threshold_is_rejected() -> None:
    config = SleepScoreConfig()
    config.monthly_bonus.average_thresholds = ((float("nan"), 15.0),)

    with pytest.raises(
        ValueError,
        match="Sleep score numeric values must be finite",
    ):
        config.validate()
