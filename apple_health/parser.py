from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime, date
from typing import BinaryIO

from apple_health.models import Workout
from apple_health.models import AppleHealthData
from apple_health.models import DailyMetrics
from apple_health.models import SleepRecord

from apple_health.constants import APPLE_WATCH_SOURCE
from apple_health.enums import APPLE_WORKOUT_TYPES
from apple_health.enums import SleepStage
from apple_health.enums import WorkoutType


APPLE_DATE_FORMAT = "%Y-%m-%d %H:%M:%S %z"


class AppleHealthParser:
    def __init__(self, xml_stream: BinaryIO) -> None:
        self.xml_stream = xml_stream

    def parse(self) -> AppleHealthData:
        workouts: list[Workout] = []
        daily_metrics: dict[date, DailyMetrics] = {}
        sleep_records: list[SleepRecord] = []

        for _, element in ET.iterparse(self.xml_stream, events=("end",)):
            if element.tag == "Workout":
                workouts.append(self._parse_workout(element))
                element.clear()

            elif element.tag == "Record":
                record_type = element.attrib.get("type")

                if record_type == "HKCategoryTypeIdentifierSleepAnalysis":
                    sleep_records.append(
                        self._parse_sleep_record(element)
                    )

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
        if activity_type == "HKWorkoutActivityTypeCycling":
            for child in element:
                if (
                    child.tag == "MetadataEntry"
                    and child.attrib.get("key") == "HKIndoorWorkout"
                ):
                    if child.attrib.get("value") == "1":
                        return WorkoutType.INDOOR_CYCLING

                    return WorkoutType.OUTDOOR_CYCLING

            return WorkoutType.OUTDOOR_CYCLING

        return APPLE_WORKOUT_TYPES.get(
            activity_type,
            WorkoutType.OTHER,
        )
    
    def _parse_workout(self, element: ET.Element) -> Workout:
        active_energy: float | None = None
        distance: float | None = None

        for child in element:
            if child.tag != "WorkoutStatistics":
                continue

            statistic_type = child.attrib.get("type")

            if statistic_type == "HKQuantityTypeIdentifierActiveEnergyBurned":
                active_energy = float(child.attrib["sum"])

            elif statistic_type == "HKQuantityTypeIdentifierDistanceWalkingRunning":
                distance = float(child.attrib["sum"])

            elif statistic_type == "HKQuantityTypeIdentifierDistanceCycling":
                distance = float(child.attrib["sum"])

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

        if record_type not in (
            "HKQuantityTypeIdentifierStepCount",
            "HKQuantityTypeIdentifierDistanceWalkingRunning",
        ):
            return
        
        source_name = element.attrib.get("sourceName", "")
        
        if APPLE_WATCH_SOURCE not in source_name:
            return

        day = datetime.strptime(
            element.attrib["startDate"],
            APPLE_DATE_FORMAT,
        ).date()

        metrics = daily_metrics.setdefault(
            day,
            DailyMetrics(date=day),
        )
        
        value = (element.attrib["value"])

        self._update_daily_metrics(
            metrics,
            record_type,
            value,
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