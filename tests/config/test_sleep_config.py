import pytest

from apple_health.config.sleep_config import SleepConfig

# =====================================================================
# Verifies that the default sleep configuration satisfies all
# validation rules and can be used without raising an exception.
# =====================================================================


def test_default_sleep_config_is_valid() -> None:
    config = SleepConfig()

    config.validate()


# =====================================================================
# Verifies that the sleep-session gap threshold cannot be negative.
# Negative values would make session reconstruction semantics invalid.
# =====================================================================


def test_negative_session_gap_threshold_is_rejected() -> None:
    config = SleepConfig(
        session_gap_threshold_minutes=-1,
    )

    with pytest.raises(
        ValueError,
        match="Sleep session gap threshold cannot be negative",
    ):
        config.validate()


# =====================================================================
# Verifies that a zero-minute session gap threshold is valid and means
# only directly adjacent sleep records may be merged into one session.
# =====================================================================


def test_zero_session_gap_threshold_is_valid() -> None:
    config = SleepConfig(
        session_gap_threshold_minutes=0,
    )

    config.validate()
