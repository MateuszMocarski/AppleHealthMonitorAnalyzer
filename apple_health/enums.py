from enum import Enum


class WorkoutType(Enum):
    WALKING = "walking"
    CYCLING = "cycling"
    STRENGTH_TRAINING = "strength_training"

    OTHER = "other"


APPLE_WORKOUT_TYPES: dict[str, WorkoutType] = {
    "HKWorkoutActivityTypeWalking": WorkoutType.WALKING,
    "HKWorkoutActivityTypeCycling": WorkoutType.CYCLING,
    "HKWorkoutActivityTypeTraditionalStrengthTraining": WorkoutType.STRENGTH_TRAINING,
}