from enum import Enum, auto


class WorkoutType(Enum):
    WALKING = "walking"
    HIKING = "hiking"
    OUTDOOR_CYCLING = "outdoor cycling"
    INDOOR_CYCLING = "indoor cycling"
    STRENGTH_TRAINING = "strength training"
    OTHER = "other"


class SleepStage(Enum):
    IN_BED = auto()

    CORE = auto()
    REM = auto()
    DEEP = auto()

    AWAKE = auto()

    UNSPECIFIED = auto()

    OTHER = auto()


APPLE_WORKOUT_TYPES = {
    "HKWorkoutActivityTypeWalking": WorkoutType.WALKING,
    "HKWorkoutActivityTypeHiking": WorkoutType.HIKING,
    "HKWorkoutActivityTypeCycling": WorkoutType.OUTDOOR_CYCLING,
    "HKWorkoutActivityTypeTraditionalStrengthTraining": WorkoutType.STRENGTH_TRAINING,
}
