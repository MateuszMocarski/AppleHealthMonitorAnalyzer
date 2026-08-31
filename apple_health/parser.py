from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import date, datetime
from typing import BinaryIO

from apple_health.config.app_config import AppConfig
from apple_health.constants import (
    APPLE_DATE_FORMAT,
    APPLE_HEALTH_DAILY_METRIC_TYPES,
    APPLE_WATCH_DAILY_METRIC_TYPES,
    NUTRITION_RECORD_TYPES,
    WORKOUT_ACTIVE_ENERGY_TYPE,
    WORKOUT_CYCLING_DISTANCE_TYPE,
    WORKOUT_INDOOR_METADATA_KEY,
    WORKOUT_WALKING_RUNNING_DISTANCE_TYPE,
)
from apple_health.enums import APPLE_WORKOUT_TYPES, SleepStage, WorkoutType
from apple_health.models import (
    AppleHealthData,
    DailyMetrics,
    NutritionData,
    SleepRecord,
    WeightMeasurement,
    Workout,
)


class AppleHealthParser:
    def __init__(self, xml_stream: BinaryIO, config: AppConfig | None = None) -> None:
        self.xml_stream = xml_stream
        self.config = config or AppConfig()

    def parse(self) -> AppleHealthData:
        workouts: list[Workout] = []
        daily_metrics: dict[date, DailyMetrics] = {}
        sleep_records: list[SleepRecord] = []

        root_checked = False

        for event, element in ET.iterparse(
            self.xml_stream,
            events=("start", "end"),
        ):
            if event == "start":
                if not root_checked:
                    root_checked = True

                    if element.tag != "HealthData":
                        raise ValueError("Expected Apple HealthData root element.")

                continue

            if element.tag == "Workout":
                workouts.append(self._parse_workout(element))
                element.clear()

            elif element.tag == "Record":
                record_type = element.attrib.get("type")

                if record_type == "HKCategoryTypeIdentifierSleepAnalysis":
                    sleep_records.append(self._parse_sleep_record(element))

                else:
                    self._parse_daily_metrics(
                        element,
                        daily_metrics,
                    )

                element.clear()

        return AppleHealthData(
            workouts=workouts,
            daily_metrics=sorted(
                daily_metrics.values(),
                key=lambda metrics: metrics.date,
            ),
            sleep_records=sleep_records,
        )

    def _parse_workout_type(
        self,
        activity_type: str,
        element: ET.Element,
    ) -> WorkoutType:
        if activity_type != "HKWorkoutActivityTypeCycling":
            return APPLE_WORKOUT_TYPES.get(
                activity_type,
                WorkoutType.OTHER,
            )

        is_indoor = any(
            child.tag == "MetadataEntry"
            and child.attrib.get("key") == WORKOUT_INDOOR_METADATA_KEY
            and child.attrib.get("value") == "1"
            for child in element
        )

        return WorkoutType.INDOOR_CYCLING if is_indoor else WorkoutType.OUTDOOR_CYCLING

    def _parse_workout(
        self,
        element: ET.Element,
    ) -> Workout:
        active_energy, distance = self._parse_workout_statistics(element)

        return Workout(
            apple_activity_type=element.attrib["workoutActivityType"],
            activity_type=self._parse_workout_type(
                element.attrib["workoutActivityType"],
                element,
            ),
            source_name=element.attrib["sourceName"],
            source_version=element.attrib.get("sourceVersion"),
            start=datetime.strptime(
                element.attrib["startDate"],
                APPLE_DATE_FORMAT,
            ),
            end=datetime.strptime(
                element.attrib["endDate"],
                APPLE_DATE_FORMAT,
            ),
            duration_minutes=float(element.attrib["duration"]),
            active_energy_kcal=active_energy,
            distance_km=distance,
        )

    def _parse_daily_metrics(
        self,
        element: ET.Element,
        daily_metrics: dict[date, DailyMetrics],
    ) -> None:
        record_type = element.attrib.get("type")

        record_source = self._expected_source_for_record_type(record_type)

        if record_source is None:
            return

        source_name = element.attrib.get(
            "sourceName",
            "",
        )

        if record_type in APPLE_WATCH_DAILY_METRIC_TYPES:
            if not self.config.source.matches_apple_watch_source(
                source_name,
            ):
                return

        elif source_name != record_source:
            return

        recorded_at = datetime.strptime(
            element.attrib["startDate"],
            APPLE_DATE_FORMAT,
        )

        day = recorded_at.date()

        metrics = daily_metrics.setdefault(
            day,
            DailyMetrics(date=day),
        )

        if record_type == "HKQuantityTypeIdentifierBodyMass":
            measurement = WeightMeasurement(
                value=float(element.attrib["value"]),
                timestamp=recorded_at,
                is_user_entered=self._is_user_entered(element),
            )

            if metrics.weight is None or self._should_replace_weight(
                current=metrics.weight,
                candidate=measurement,
            ):
                metrics.weight = measurement

            return

        if record_type in NUTRITION_RECORD_TYPES:
            if metrics.nutrition is None:
                metrics.nutrition = NutritionData()

            self._update_nutrition_data(
                metrics.nutrition,
                record_type,
                element.attrib["value"],
            )

            return

        self._update_daily_metrics(
            metrics,
            record_type,
            element.attrib["value"],
        )

    def _update_daily_metrics(
        self,
        metrics: DailyMetrics,
        record_type: str,
        value: str,
    ) -> None:
        if record_type == "HKQuantityTypeIdentifierStepCount":
            metrics.steps += int(value)

        elif record_type == "HKQuantityTypeIdentifierDistanceWalkingRunning":
            metrics.distance_km += float(value)

        elif record_type == "HKQuantityTypeIdentifierActiveEnergyBurned":
            metrics.active_energy = self._add_optional_value(
                metrics.active_energy,
                float(value),
            )

        elif record_type == "HKQuantityTypeIdentifierBasalEnergyBurned":
            metrics.basal_energy = self._add_optional_value(
                metrics.basal_energy,
                float(value),
            )

    def _parse_sleep_record(
        self,
        element: ET.Element,
    ) -> SleepRecord:
        start = datetime.strptime(
            element.attrib["startDate"],
            APPLE_DATE_FORMAT,
        )

        end = datetime.strptime(
            element.attrib["endDate"],
            APPLE_DATE_FORMAT,
        )

        return SleepRecord(
            stage=self._parse_sleep_stage(element.attrib["value"]),
            source_name=element.attrib["sourceName"],
            source_version=element.attrib.get("sourceVersion"),
            start=start,
            end=end,
            duration_minutes=(end - start).total_seconds() / 60,
        )

    def _parse_sleep_stage(
        self,
        value: str,
    ) -> SleepStage:
        match value:
            case "HKCategoryValueSleepAnalysisInBed":
                return SleepStage.IN_BED

            case "HKCategoryValueSleepAnalysisAsleepUnspecified":
                return SleepStage.UNSPECIFIED

            case "HKCategoryValueSleepAnalysisAsleepCore":
                return SleepStage.CORE

            case "HKCategoryValueSleepAnalysisAsleepDeep":
                return SleepStage.DEEP

            case "HKCategoryValueSleepAnalysisAsleepREM":
                return SleepStage.REM

            case "HKCategoryValueSleepAnalysisAwake":
                return SleepStage.AWAKE

            case _:
                return SleepStage.OTHER

    def _is_user_entered(
        self,
        element: ET.Element,
    ) -> bool:
        return any(
            child.tag == "MetadataEntry"
            and child.attrib.get("key") == "HKWasUserEntered"
            and child.attrib.get("value") == "1"
            for child in element
        )

    def _should_replace_weight(
        self,
        current: WeightMeasurement,
        candidate: WeightMeasurement,
    ) -> bool:
        if candidate.is_user_entered != current.is_user_entered:
            return candidate.is_user_entered

        return candidate.timestamp > current.timestamp

    def _update_nutrition_data(
        self,
        nutrition: NutritionData,
        record_type: str,
        value: str,
    ) -> None:
        parsed_value = float(value)

        if record_type == "HKQuantityTypeIdentifierDietaryEnergyConsumed":
            nutrition.calories_kcal = self._add_optional_value(
                nutrition.calories_kcal,
                parsed_value,
            )

        elif record_type == "HKQuantityTypeIdentifierDietaryProtein":
            nutrition.protein_g = self._add_optional_value(
                nutrition.protein_g,
                parsed_value,
            )

        elif record_type == "HKQuantityTypeIdentifierDietaryCarbohydrates":
            nutrition.carbohydrates_g = self._add_optional_value(
                nutrition.carbohydrates_g,
                parsed_value,
            )

        elif record_type == "HKQuantityTypeIdentifierDietaryFatTotal":
            nutrition.fat_g = self._add_optional_value(
                nutrition.fat_g,
                parsed_value,
            )

    def _expected_source_for_record_type(
        self,
        record_type: str | None,
    ) -> str | None:
        source_config = self.config.source
        if record_type in APPLE_WATCH_DAILY_METRIC_TYPES:
            return source_config.apple_watch_source

        if record_type in APPLE_HEALTH_DAILY_METRIC_TYPES:
            return source_config.apple_health_app_source

        return None

    def _parse_workout_statistics(
        self,
        element: ET.Element,
    ) -> tuple[float | None, float | None]:
        active_energy: float | None = None
        distance: float | None = None

        for child in element:
            if child.tag != "WorkoutStatistics":
                continue

            statistic_type = child.attrib.get("type")

            if statistic_type == WORKOUT_ACTIVE_ENERGY_TYPE:
                active_energy = float(child.attrib["sum"])

            elif statistic_type in (
                WORKOUT_WALKING_RUNNING_DISTANCE_TYPE,
                WORKOUT_CYCLING_DISTANCE_TYPE,
            ):
                distance = float(child.attrib["sum"])

        return active_energy, distance

    @staticmethod
    def _add_optional_value(
        current_value: float | None,
        value: float,
    ) -> float:
        if current_value is None:
            return value

        return current_value + value
