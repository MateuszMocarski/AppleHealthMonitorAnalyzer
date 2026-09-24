from dataclasses import dataclass, field
from datetime import time
from math import isfinite


@dataclass(slots=True)
class BedtimeScoreConfig:
    target: time = time(0, 0)

    penalty_interval_minutes: int = 15
    penalty_points: float = 5.0


@dataclass(slots=True)
class SleepDurationScoreConfig:
    target_minutes: int = 480
    tolerance_minutes: int = 30

    penalty_interval_minutes: int = 15
    penalty_points: float = 5.0

    oversleep_weight: float = 1.0
    undersleep_weight: float = 1.0


@dataclass(slots=True)
class WakeUpScoreConfig:
    target: time = time(8, 0)

    bedtime_weight: float = 1.0
    duration_weight: float = 2.0

    penalty_interval_minutes: int = 15
    penalty_points: float = 3.0


@dataclass(slots=True)
class SleepScoreWeightsConfig:
    bedtime: float = 1.0
    duration: float = 1.0
    wake_up: float = 1.0


@dataclass(slots=True)
class MonthlySleepBonusConfig:
    enabled: bool = True
    max_points: int = 20

    average_thresholds: tuple[tuple[float, float], ...] = (
        (90, 15),
        (80, 10),
        (70, 5),
    )

    consistency_thresholds: tuple[tuple[float, float], ...] = (
        (3, 5),
        (6, 4),
        (9, 3),
        (12, 2),
        (15, 1),
    )


@dataclass(slots=True)
class SleepScoreConfig:
    linear_penalties: bool = False

    bedtime: BedtimeScoreConfig = field(default_factory=BedtimeScoreConfig)

    duration: SleepDurationScoreConfig = field(default_factory=SleepDurationScoreConfig)

    wake_up: WakeUpScoreConfig = field(default_factory=WakeUpScoreConfig)

    weights: SleepScoreWeightsConfig = field(default_factory=SleepScoreWeightsConfig)

    monthly_bonus: MonthlySleepBonusConfig = field(default_factory=MonthlySleepBonusConfig)

    def validate(self) -> None:
        self._validate_finite_numbers()
        self._validate_score_weights()
        self._validate_wake_up_weights()
        self._validate_penalty_intervals()
        self._validate_penalty_points()
        self._validate_duration()
        self._validate_duration_penalty_weights()
        self._validate_average_bonus_thresholds()
        self._validate_consistency_bonus_thresholds()
        self._validate_maximum_monthly_bonus()

    def _validate_finite_numbers(self) -> None:
        values = (
            self.bedtime.penalty_points,
            self.duration.penalty_points,
            self.duration.oversleep_weight,
            self.duration.undersleep_weight,
            self.wake_up.bedtime_weight,
            self.wake_up.duration_weight,
            self.wake_up.penalty_points,
            self.weights.bedtime,
            self.weights.duration,
            self.weights.wake_up,
            *(value for pair in self.monthly_bonus.average_thresholds for value in pair),
            *(value for pair in self.monthly_bonus.consistency_thresholds for value in pair),
        )

        if any(not isfinite(value) for value in values):
            raise ValueError("Sleep score numeric values must be finite.")

    def _validate_score_weights(self) -> None:
        score_weights = (
            self.weights.bedtime,
            self.weights.duration,
            self.weights.wake_up,
        )

        if any(weight < 0 for weight in score_weights):
            raise ValueError("Sleep score component weights cannot be negative.")

        if sum(score_weights) == 0:
            raise ValueError(
                "At least one sleep score component weight " "must be greater than zero."
            )

    def _validate_wake_up_weights(self) -> None:
        wake_up_weights = (
            self.wake_up.bedtime_weight,
            self.wake_up.duration_weight,
        )

        if any(weight < 0 for weight in wake_up_weights):
            raise ValueError("Wake-up score component weights cannot be negative.")

        if sum(wake_up_weights) == 0:
            raise ValueError(
                "At least one wake-up score component weight " "must be greater than zero."
            )

    def _validate_penalty_intervals(self) -> None:
        penalty_intervals = (
            self.bedtime.penalty_interval_minutes,
            self.duration.penalty_interval_minutes,
            self.wake_up.penalty_interval_minutes,
        )

        if any(interval <= 0 for interval in penalty_intervals):
            raise ValueError("Sleep score penalty intervals must be greater than zero.")

    def _validate_penalty_points(self) -> None:
        penalty_points = (
            self.bedtime.penalty_points,
            self.duration.penalty_points,
            self.wake_up.penalty_points,
        )

        if any(points < 0 for points in penalty_points):
            raise ValueError("Sleep score penalty points cannot be negative.")

    def _validate_duration(self) -> None:
        if self.duration.target_minutes <= 0:
            raise ValueError("Sleep duration target must be greater than zero.")

        if self.duration.tolerance_minutes < 0:
            raise ValueError("Sleep duration tolerance cannot be negative.")

        if self.duration.tolerance_minutes >= self.duration.target_minutes:
            raise ValueError(
                "Sleep duration tolerance must be lower " "than the sleep duration target."
            )

    def _validate_duration_penalty_weights(self) -> None:
        penalty_weights = (
            self.duration.oversleep_weight,
            self.duration.undersleep_weight,
        )

        if any(weight < 0 for weight in penalty_weights):
            raise ValueError("Sleep duration penalty weights cannot be negative.")

    def _validate_average_bonus_thresholds(self) -> None:
        previous_threshold = None
        previous_bonus = None

        for (
            threshold,
            bonus,
        ) in self.monthly_bonus.average_thresholds:
            if not 0 <= threshold <= 100:
                raise ValueError("Sleep average bonus thresholds " "must be between 0 and 100.")

            if bonus < 0:
                raise ValueError("Sleep average bonus points cannot be negative.")

            if previous_threshold is not None and threshold >= previous_threshold:
                raise ValueError("Sleep average bonus thresholds " "must be strictly decreasing.")

            if previous_bonus is not None and bonus > previous_bonus:
                raise ValueError(
                    "Sleep average bonus points cannot increase "
                    "as the score threshold decreases."
                )

            previous_threshold = threshold
            previous_bonus = bonus

    def _validate_consistency_bonus_thresholds(self) -> None:
        previous_threshold = None
        previous_bonus = None

        for (
            threshold,
            bonus,
        ) in self.monthly_bonus.consistency_thresholds:
            if threshold <= 0:
                raise ValueError("Sleep consistency thresholds " "must be greater than zero.")

            if bonus < 0:
                raise ValueError("Sleep consistency bonus points " "cannot be negative.")

            if previous_threshold is not None and threshold <= previous_threshold:
                raise ValueError("Sleep consistency thresholds " "must be strictly increasing.")

            if previous_bonus is not None and bonus > previous_bonus:
                raise ValueError(
                    "Sleep consistency bonus points cannot increase " "as deviation increases."
                )

            previous_threshold = threshold
            previous_bonus = bonus

    def _validate_maximum_monthly_bonus(self) -> None:
        max_average_bonus = max(
            (bonus for _, bonus in self.monthly_bonus.average_thresholds),
            default=0,
        )

        max_consistency_bonus = max(
            (bonus for _, bonus in self.monthly_bonus.consistency_thresholds),
            default=0,
        )

        if max_average_bonus + max_consistency_bonus > self.monthly_bonus.max_points:
            raise ValueError(
                "Maximum configured monthly sleep bonuses exceed "
                "the configured monthly bonus maximum."
            )
