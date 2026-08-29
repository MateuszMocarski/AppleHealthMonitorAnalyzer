from io import BytesIO

import pytest

from apple_health.config.app_config import AppConfig
from apple_health.constants import (
    WORKOUT_ACTIVE_ENERGY_TYPE,
    WORKOUT_CYCLING_DISTANCE_TYPE,
    WORKOUT_INDOOR_METADATA_KEY,
    WORKOUT_WALKING_RUNNING_DISTANCE_TYPE,
)
from apple_health.enums import SleepStage, WorkoutType
from apple_health.parser import AppleHealthParser

# =======
# Helpers
# =======


def _parse_xml(
    xml: str,
    config: AppConfig | None = None,
):
    return AppleHealthParser(
        BytesIO(xml.encode("utf-8")),
        config=config,
    ).parse()


def _wrap_xml(*elements: str) -> str:
    return "<HealthData>" + "".join(elements) + "</HealthData>"


def _record(
    *,
    record_type: str,
    source_name: str,
    value: str,
    start_date: str = "2026-08-01 10:00:00 +0200",
    end_date: str | None = None,
    metadata: str = "",
) -> str:
    end_date = end_date or start_date

    return f"""
        <Record
            type="{record_type}"
            sourceName="{source_name}"
            value="{value}"
            startDate="{start_date}"
            endDate="{end_date}">
            {metadata}
        </Record>
    """


def _workout(
    *,
    activity_type: str,
    metadata: str = "",
    statistics: str = "",
    source_name: str | None = None,
) -> str:
    if source_name is None:
        source_name = AppConfig().source.apple_watch_source

    return f"""
        <Workout
            workoutActivityType="{activity_type}"
            sourceName="{source_name}"
            sourceVersion="1"
            startDate="2026-08-01 10:00:00 +0200"
            endDate="2026-08-01 11:00:00 +0200"
            duration="60">
            {metadata}
            {statistics}
        </Workout>
    """


# =====================================================================
# Verifies that a standard Apple workout activity type is mapped to the
# corresponding internal WorkoutType.
# =====================================================================


def test_parses_standard_workout_type() -> None:
    data = _parse_xml(_wrap_xml(_workout(activity_type="HKWorkoutActivityTypeWalking")))

    assert len(data.workouts) == 1
    assert data.workouts[0].activity_type == WorkoutType.WALKING


# =====================================================================
# Verifies that cycling workouts containing the Apple indoor-workout
# metadata flag are classified as indoor cycling.
# =====================================================================


def test_parses_indoor_cycling_workout() -> None:
    metadata = f"""
        <MetadataEntry
            key="{WORKOUT_INDOOR_METADATA_KEY}"
            value="1"
        />
    """

    data = _parse_xml(
        _wrap_xml(
            _workout(
                activity_type="HKWorkoutActivityTypeCycling",
                metadata=metadata,
            )
        )
    )

    assert data.workouts[0].activity_type == WorkoutType.INDOOR_CYCLING


# =====================================================================
# Verifies that cycling workouts without the indoor metadata flag are
# classified as outdoor cycling.
# =====================================================================


def test_parses_outdoor_cycling_workout() -> None:
    data = _parse_xml(_wrap_xml(_workout(activity_type="HKWorkoutActivityTypeCycling")))

    assert data.workouts[0].activity_type == WorkoutType.OUTDOOR_CYCLING


# =====================================================================
# Verifies that unknown Apple workout activity types are preserved as
# generic OTHER workouts instead of causing parsing to fail.
# =====================================================================


def test_unknown_workout_type_maps_to_other() -> None:
    data = _parse_xml(_wrap_xml(_workout(activity_type="HKWorkoutActivityTypeSomethingUnknown")))

    assert data.workouts[0].activity_type == WorkoutType.OTHER


# =====================================================================
# Verifies that workout active energy and walking/running distance are
# extracted from WorkoutStatistics child elements.
# =====================================================================


def test_parses_workout_energy_and_distance_statistics() -> None:
    statistics = f"""
        <WorkoutStatistics
            type="{WORKOUT_ACTIVE_ENERGY_TYPE}"
            sum="456.7"
        />
        <WorkoutStatistics
            type="{WORKOUT_WALKING_RUNNING_DISTANCE_TYPE}"
            sum="8.25"
        />
    """

    data = _parse_xml(
        _wrap_xml(
            _workout(
                activity_type="HKWorkoutActivityTypeWalking",
                statistics=statistics,
            )
        )
    )

    workout = data.workouts[0]

    assert workout.active_energy_kcal == pytest.approx(456.7)
    assert workout.distance_km == pytest.approx(8.25)


# =====================================================================
# Verifies that cycling distance statistics are accepted as workout
# distance in the same way as walking/running distance.
# =====================================================================


def test_parses_cycling_distance_statistics() -> None:
    statistics = f"""
        <WorkoutStatistics
            type="{WORKOUT_CYCLING_DISTANCE_TYPE}"
            sum="21.5"
        />
    """

    data = _parse_xml(
        _wrap_xml(
            _workout(
                activity_type="HKWorkoutActivityTypeCycling",
                statistics=statistics,
            )
        )
    )

    assert data.workouts[0].distance_km == pytest.approx(21.5)


# =====================================================================
# Verifies that Apple Watch daily activity records are aggregated into
# DailyMetrics when they originate from the expected Apple Watch
# source.
# =====================================================================


def test_aggregates_apple_watch_daily_metrics() -> None:
    config = AppConfig()
    source_config = config.source
    xml = _wrap_xml(
        _record(
            record_type="HKQuantityTypeIdentifierStepCount",
            source_name=source_config.apple_watch_source,
            value="5000",
        ),
        _record(
            record_type="HKQuantityTypeIdentifierStepCount",
            source_name=source_config.apple_watch_source,
            value="3500",
        ),
        _record(
            record_type="HKQuantityTypeIdentifierDistanceWalkingRunning",
            source_name=source_config.apple_watch_source,
            value="7.25",
        ),
        _record(
            record_type="HKQuantityTypeIdentifierActiveEnergyBurned",
            source_name=source_config.apple_watch_source,
            value="650",
        ),
        _record(
            record_type="HKQuantityTypeIdentifierBasalEnergyBurned",
            source_name=source_config.apple_watch_source,
            value="1900",
        ),
    )

    data = _parse_xml(xml, config=config)

    assert len(data.daily_metrics) == 1

    metrics = data.daily_metrics[0]

    assert metrics.steps == 8500
    assert metrics.distance_km == pytest.approx(7.25)
    assert metrics.active_energy == pytest.approx(650)
    assert metrics.basal_energy == pytest.approx(1900)


# =====================================================================
# Verifies that Apple Watch metric types from an unexpected source are
# ignored instead of being included in daily activity totals.
# =====================================================================


def test_ignores_watch_metrics_from_wrong_source() -> None:
    data = _parse_xml(
        _wrap_xml(
            _record(
                record_type="HKQuantityTypeIdentifierStepCount",
                source_name="Some Other Device",
                value="10000",
            )
        )
    )

    assert data.daily_metrics == []


# =====================================================================
# Verifies that record types not supported by the daily-metrics parser
# are ignored without creating an empty DailyMetrics object.
# =====================================================================


def test_ignores_unknown_daily_metric_types() -> None:
    data = _parse_xml(
        _wrap_xml(
            _record(
                record_type="HKQuantityTypeIdentifierUnknownMetric",
                source_name=AppConfig().source.apple_watch_source,
                value="123",
            )
        )
    )

    assert data.daily_metrics == []


# =====================================================================
# Verifies that nutrition records from Apple Health are accumulated
# into one NutritionData object for the corresponding calendar day.
# =====================================================================


def test_aggregates_nutrition_records() -> None:
    config = AppConfig()
    source_config = config.source
    xml = _wrap_xml(
        _record(
            record_type="HKQuantityTypeIdentifierDietaryEnergyConsumed",
            source_name=source_config.apple_health_app_source,
            value="1000",
        ),
        _record(
            record_type="HKQuantityTypeIdentifierDietaryEnergyConsumed",
            source_name=source_config.apple_health_app_source,
            value="1050",
        ),
        _record(
            record_type="HKQuantityTypeIdentifierDietaryProtein",
            source_name=source_config.apple_health_app_source,
            value="155",
        ),
        _record(
            record_type="HKQuantityTypeIdentifierDietaryCarbohydrates",
            source_name=source_config.apple_health_app_source,
            value="194",
        ),
        _record(
            record_type="HKQuantityTypeIdentifierDietaryFatTotal",
            source_name=source_config.apple_health_app_source,
            value="73",
        ),
    )

    data = _parse_xml(xml, config=config)

    nutrition = data.daily_metrics[0].nutrition

    assert nutrition is not None
    assert nutrition.calories_kcal == pytest.approx(2050)
    assert nutrition.protein_g == pytest.approx(155)
    assert nutrition.carbohydrates_g == pytest.approx(194)
    assert nutrition.fat_g == pytest.approx(73)


# =====================================================================
# Verifies that Apple Health nutrition and body-mass records
# originating from an unexpected source are rejected.
# =====================================================================


def test_ignores_apple_health_metrics_from_wrong_source() -> None:
    data = _parse_xml(
        _wrap_xml(
            _record(
                record_type="HKQuantityTypeIdentifierDietaryProtein",
                source_name="Some Other Source",
                value="150",
            ),
            _record(
                record_type="HKQuantityTypeIdentifierBodyMass",
                source_name="Some Other Source",
                value="80",
            ),
        )
    )

    assert data.daily_metrics == []


# =====================================================================
# Verifies that a user-entered body-weight measurement takes precedence
# over an automatically recorded measurement from the same day.
# =====================================================================


def test_user_entered_weight_replaces_automatic_measurement() -> None:
    user_entered_metadata = """
        <MetadataEntry
            key="HKWasUserEntered"
            value="1"
        />
    """
    config = AppConfig()
    source_config = config.source
    xml = _wrap_xml(
        _record(
            record_type="HKQuantityTypeIdentifierBodyMass",
            source_name=source_config.apple_health_app_source,
            value="80.5",
            start_date="2026-08-01 12:00:00 +0200",
        ),
        _record(
            record_type="HKQuantityTypeIdentifierBodyMass",
            source_name=source_config.apple_health_app_source,
            value="79.8",
            start_date="2026-08-01 08:00:00 +0200",
            metadata=user_entered_metadata,
        ),
    )

    data = _parse_xml(xml, config=config)

    weight = data.daily_metrics[0].weight

    assert weight is not None
    assert weight.value == pytest.approx(79.8)
    assert weight.is_user_entered is True


# =====================================================================
# Verifies that when body-weight measurements have the same entry type,
# the most recent measurement is selected for the day.
# =====================================================================


def test_latest_weight_replaces_older_measurement() -> None:
    config = AppConfig()
    source_config = config.source

    xml = _wrap_xml(
        _record(
            record_type="HKQuantityTypeIdentifierBodyMass",
            source_name=source_config.apple_health_app_source,
            value="80.5",
            start_date="2026-08-01 08:00:00 +0200",
        ),
        _record(
            record_type="HKQuantityTypeIdentifierBodyMass",
            source_name=source_config.apple_health_app_source,
            value="79.9",
            start_date="2026-08-01 20:00:00 +0200",
        ),
    )

    data = _parse_xml(xml, config=config)

    weight = data.daily_metrics[0].weight

    assert weight is not None
    assert weight.value == pytest.approx(79.9)


# =====================================================================
# Verifies that parsed DailyMetrics objects are returned in
# chronological order even when XML records appear in a different
# order.
# =====================================================================


def test_daily_metrics_are_sorted_by_date() -> None:
    config = AppConfig()
    source_config = config.source
    xml = _wrap_xml(
        _record(
            record_type="HKQuantityTypeIdentifierStepCount",
            source_name=source_config.apple_watch_source,
            value="3000",
            start_date="2026-08-03 10:00:00 +0200",
        ),
        _record(
            record_type="HKQuantityTypeIdentifierStepCount",
            source_name=source_config.apple_watch_source,
            value="1000",
            start_date="2026-08-01 10:00:00 +0200",
        ),
        _record(
            record_type="HKQuantityTypeIdentifierStepCount",
            source_name=source_config.apple_watch_source,
            value="2000",
            start_date="2026-08-02 10:00:00 +0200",
        ),
    )

    data = _parse_xml(xml, config=config)

    assert [metrics.date.day for metrics in data.daily_metrics] == [
        1,
        2,
        3,
    ]


# =====================================================================
# Verifies that all supported Apple Health sleep-stage values map to
# the expected SleepStage enum.
# =====================================================================


@pytest.mark.parametrize(
    ("apple_value", "expected_stage"),
    [
        (
            "HKCategoryValueSleepAnalysisInBed",
            SleepStage.IN_BED,
        ),
        (
            "HKCategoryValueSleepAnalysisAsleepUnspecified",
            SleepStage.UNSPECIFIED,
        ),
        (
            "HKCategoryValueSleepAnalysisAsleepCore",
            SleepStage.CORE,
        ),
        (
            "HKCategoryValueSleepAnalysisAsleepDeep",
            SleepStage.DEEP,
        ),
        (
            "HKCategoryValueSleepAnalysisAsleepREM",
            SleepStage.REM,
        ),
        (
            "HKCategoryValueSleepAnalysisAwake",
            SleepStage.AWAKE,
        ),
    ],
)
def test_parses_known_sleep_stages(
    apple_value: str,
    expected_stage: SleepStage,
) -> None:
    data = _parse_xml(
        _wrap_xml(
            _record(
                record_type="HKCategoryTypeIdentifierSleepAnalysis",
                source_name=AppConfig().source.apple_watch_source,
                value=apple_value,
                start_date="2026-08-01 00:00:00 +0200",
                end_date="2026-08-01 01:00:00 +0200",
            )
        )
    )

    assert len(data.sleep_records) == 1
    assert data.sleep_records[0].stage == expected_stage


# =====================================================================
# Verifies that an unknown Apple sleep-analysis value is preserved as
# the generic OTHER sleep stage instead of failing parsing.
# =====================================================================


def test_unknown_sleep_stage_maps_to_other() -> None:
    data = _parse_xml(
        _wrap_xml(
            _record(
                record_type="HKCategoryTypeIdentifierSleepAnalysis",
                source_name=AppConfig().source.apple_watch_source,
                value="SomethingCompletelyUnknown",
                start_date="2026-08-01 00:00:00 +0200",
                end_date="2026-08-01 01:00:00 +0200",
            )
        )
    )

    assert data.sleep_records[0].stage == SleepStage.OTHER


# =====================================================================
# Verifies that SleepRecord duration is calculated from its start and
# end timestamps rather than relying on a separate XML duration value.
# =====================================================================


def test_sleep_record_duration_is_calculated_from_timestamps() -> None:
    data = _parse_xml(
        _wrap_xml(
            _record(
                record_type="HKCategoryTypeIdentifierSleepAnalysis",
                source_name=AppConfig().source.apple_watch_source,
                value="HKCategoryValueSleepAnalysisAsleepCore",
                start_date="2026-08-01 00:15:00 +0200",
                end_date="2026-08-01 02:45:00 +0200",
            )
        )
    )

    assert data.sleep_records[0].duration_minutes == 150


# =====================================================================
# Verifies that AppleHealthParser uses the injected Apple Watch source
# when selecting daily activity records.
# =====================================================================


def test_uses_configured_apple_watch_source() -> None:
    config = AppConfig()
    config.source.apple_watch_source = "Custom Watch"

    xml = _wrap_xml(
        _record(
            record_type="HKQuantityTypeIdentifierStepCount",
            source_name="Custom Watch",
            value="5000",
        )
    )

    data = _parse_xml(
        xml,
        config=config,
    )

    assert len(data.daily_metrics) == 1
    assert data.daily_metrics[0].steps == 5000


# =====================================================================
# Verifies that AppleHealthParser uses the injected Apple Health source
# when selecting nutrition and body-mass records.
# =====================================================================


def test_uses_configured_apple_health_source() -> None:
    config = AppConfig()
    config.source.apple_health_app_source = "Custom Health"

    xml = _wrap_xml(
        _record(
            record_type="HKQuantityTypeIdentifierDietaryProtein",
            source_name="Custom Health",
            value="150",
        )
    )

    data = _parse_xml(
        xml,
        config=config,
    )

    assert len(data.daily_metrics) == 1

    nutrition = data.daily_metrics[0].nutrition

    assert nutrition is not None
    assert nutrition.protein_g == pytest.approx(150)

# =====================================================================
# Verifies that the parser rejects XML documents whose root element is
# not the Apple HealthData element.
# =====================================================================


def test_parser_rejects_non_health_data_root() -> None:
    xml_stream = BytesIO(
        b"""<?xml version="1.0" encoding="UTF-8"?>
<NotHealthData>
    <Record />
</NotHealthData>
"""
    )

    parser = AppleHealthParser(
        xml_stream=xml_stream,
    )

    with pytest.raises(
        ValueError,
        match="Expected Apple HealthData root element.",
    ):
        parser.parse()