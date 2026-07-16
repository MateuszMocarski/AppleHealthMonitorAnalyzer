from enum import Enum


class WorkoutType(Enum):
    WALKING = "walking"
    HIKING = "hiking"
    CYCLING = "cycling"
    STRENGTH_TRAINING = "strength_training"

    OTHER = "other"


APPLE_WORKOUT_TYPES: dict[str, WorkoutType] = {
    "HKWorkoutActivityTypeWalking": WorkoutType.WALKING,
    "HKWorkoutActivityTypeHiking": WorkoutType.HIKING,
    "HKWorkoutActivityTypeCycling": WorkoutType.CYCLING,
    "HKWorkoutActivityTypeTraditionalStrengthTraining": WorkoutType.STRENGTH_TRAINING,
}