from enum import Enum


class WorkoutType(Enum):
    WALKING = "walking"
    HIKING = "hiking"
    OUTDOOR_CYCLING = "outdoor cycling"
    INDOOR_CYCLING = "indoor cycling"
    STRENGTH_TRAINING = "strength training"
    OTHER = "other"

APPLE_WORKOUT_TYPES = {
    "HKWorkoutActivityTypeWalking": WorkoutType.WALKING,
    "HKWorkoutActivityTypeHiking": WorkoutType.HIKING,
    "HKWorkoutActivityTypeCycling": WorkoutType.OUTDOOR_CYCLING,  # tymczasowo
    "HKWorkoutActivityTypeTraditionalStrengthTraining": WorkoutType.STRENGTH_TRAINING,
}