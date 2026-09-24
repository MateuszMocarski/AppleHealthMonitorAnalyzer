"""Apple raw-value mappings into the canonical health taxonomy."""

from apple_health.enums import WorkoutType

APPLE_WORKOUT_TYPES = {
    "HKWorkoutActivityTypeWalking": WorkoutType.WALKING,
    "HKWorkoutActivityTypeHiking": WorkoutType.HIKING,
    "HKWorkoutActivityTypeCycling": WorkoutType.OUTDOOR_CYCLING,
    "HKWorkoutActivityTypeTraditionalStrengthTraining": WorkoutType.STRENGTH_TRAINING,
}
