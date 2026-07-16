from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime
from typing import BinaryIO

from apple_health.models import Workout
from apple_health.enums import APPLE_WORKOUT_TYPES
from apple_health.enums import WorkoutType


APPLE_DATE_FORMAT = "%Y-%m-%d %H:%M:%S %z"


class AppleHealthParser:
    def __init__(self, xml_stream: BinaryIO) -> None:
        self.xml_stream = xml_stream

    def parse(self) -> list[Workout]:
        workouts: list[Workout] = []

        for _, element in ET.iterparse(self.xml_stream, events=("end",)):
            if element.tag != "Workout":
                continue

            workouts.append(self._parse_workout(element))

            element.clear()

        return workouts

    def _parse_workout_type(self, activity_type: str) -> WorkoutType:
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
                element.attrib["workoutActivityType"]
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