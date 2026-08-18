from datetime import time

# ============================================
# Penalty calculation mode
# ============================================

SLEEP_SCORE_LINEAR_PENALTIES = False


# ============================================
# Bedtime score configuration
# ============================================

BEDTIME_TARGET = time(0, 0)

BEDTIME_PENALTY_INTERVAL_MINUTES = 15
BEDTIME_PENALTY_POINTS = 5


# ============================================
# Sleep duration score configuration
# ============================================

SLEEP_DURATION_TARGET_MINUTES = 480
SLEEP_DURATION_TOLERANCE_MINUTES = 30

SLEEP_DURATION_PENALTY_INTERVAL_MINUTES = 15
SLEEP_DURATION_PENALTY_POINTS = 5

SLEEP_DURATION_OVERSLEEP_WEIGHT = 1.0
SLEEP_DURATION_UNDERSLEEP_WEIGHT = 1.0


# ============================================
# Wake-up score configuration
# ============================================

WAKE_UP_TARGET = time(8, 0)

WAKE_UP_BEDTIME_WEIGHT = 1.0
WAKE_UP_DURATION_WEIGHT = 2.0

WAKE_UP_PENALTY_INTERVAL_MINUTES = 15
WAKE_UP_PENALTY_POINTS = 3


# ============================================
# Daily score component weights
# ============================================

BEDTIME_SCORE_WEIGHT = 1.0
SLEEP_DURATION_SCORE_WEIGHT = 1.0
WAKE_UP_SCORE_WEIGHT = 1.0


# ============================================
# Configuration validation
# ============================================


def validate_sleep_score_config() -> None:
    score_weights = (
        BEDTIME_SCORE_WEIGHT,
        SLEEP_DURATION_SCORE_WEIGHT,
        WAKE_UP_SCORE_WEIGHT,
    )

    penalty_intervals = (
        BEDTIME_PENALTY_INTERVAL_MINUTES,
        SLEEP_DURATION_PENALTY_INTERVAL_MINUTES,
        WAKE_UP_PENALTY_INTERVAL_MINUTES,
    )

    penalty_points = (
        BEDTIME_PENALTY_POINTS,
        SLEEP_DURATION_PENALTY_POINTS,
        WAKE_UP_PENALTY_POINTS,
    )

    duration_penalty_weights = (
        SLEEP_DURATION_OVERSLEEP_WEIGHT,
        SLEEP_DURATION_UNDERSLEEP_WEIGHT,
    )

    if any(weight < 0 for weight in score_weights):
        raise ValueError("Sleep score component weights cannot be negative.")

    if sum(score_weights) == 0:
        raise ValueError("At least one sleep score component weight " "must be greater than zero.")

    if any(interval <= 0 for interval in penalty_intervals):
        raise ValueError("Sleep score penalty intervals must be greater than zero.")

    if any(points < 0 for points in penalty_points):
        raise ValueError("Sleep score penalty points cannot be negative.")

    if SLEEP_DURATION_TARGET_MINUTES <= 0:
        raise ValueError("Sleep duration target must be greater than zero.")

    if SLEEP_DURATION_TOLERANCE_MINUTES < 0:
        raise ValueError("Sleep duration tolerance cannot be negative.")

    if SLEEP_DURATION_TOLERANCE_MINUTES >= SLEEP_DURATION_TARGET_MINUTES:
        raise ValueError(
            "Sleep duration tolerance must be lower " "than the sleep duration target."
        )

    if any(weight < 0 for weight in duration_penalty_weights):
        raise ValueError("Sleep duration penalty weights cannot be negative.")
