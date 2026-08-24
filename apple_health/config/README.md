# Configuration

The `apple_health.config` package defines the application's strongly typed configuration model.

Configuration is represented by Python `dataclass` objects rather than module-level globals. The root `AppConfig` object groups configuration by responsibility and can be injected into the components that depend on configurable behavior.

At the current development stage, configuration values are defined by defaults in the dataclasses. Loading configuration from external runtime sources is intentionally not implemented yet.

## Overview

The configuration hierarchy is:

```text
AppConfig
├── source: SourceConfig
└── sleep: SleepConfig
    ├── session_gap_threshold_minutes
    └── score: SleepScoreConfig
        ├── linear_penalties
        ├── bedtime: BedtimeScoreConfig
        ├── duration: SleepDurationScoreConfig
        ├── wake_up: WakeUpScoreConfig
        ├── weights: SleepScoreWeightsConfig
        └── monthly_bonus: MonthlySleepBonusConfig
```

Each nested configuration object owns settings for one clearly defined responsibility.

This structure replaces the previous approach based on module-level configuration constants and provides a stable foundation for future runtime configuration loading.

## Design Goals

The configuration model is designed around several principles:

- **Strong typing** – configuration is represented by typed dataclasses.
- **Clear ownership** – settings are grouped by the subsystem that consumes them.
- **Dependency injection** – configurable components receive `AppConfig` instead of importing mutable configuration globals.
- **Safe defaults** – the application can run without supplying an explicit configuration object.
- **Validation** – relationships between values are checked before invalid settings are used by sleep scoring.
- **Extensibility** – future configuration sources can populate the same object model without changing consumers.
- **Isolation** – configuration storage and loading are kept separate from parsing, analysis and rendering logic.

## Dependency Injection

The application entry point creates one `AppConfig` instance for a processing run and passes it to components that require configurable behavior.

The intended application-level flow is:

```text
                    AppConfig
                       │
          ┌────────────┼──────────────┐
          │            │              │
          ▼            ▼              ▼
AppleHealthParser  HealthAnalyzer   Renderer
                       │
                       ▼
                  SleepAnalyzer
```

In application code this follows the pattern:

```python
config = AppConfig()

health_data = AppleHealthParser(
    xml_stream,
    config=config,
).parse()

analyzer = HealthAnalyzer(
    health_data,
    config=config,
)

renderer = TextRenderer(
    config=config,
)
```

The same configuration instance can therefore control parsing, analysis and presentation consistently during one application run.

Components also support independent construction with default configuration:

```python
parser = AppleHealthParser(xml_stream)
analyzer = HealthAnalyzer(health_data)
renderer = TextRenderer()
```

When no configuration is injected, the component creates a default `AppConfig`.

This fallback is primarily useful for standalone use and tests. The application entry point should prefer one shared configuration instance.

## `AppConfig`

Defined in:

```text
apple_health/config/app_config.py
```

`AppConfig` is the root configuration object.

```python
@dataclass(slots=True)
class AppConfig:
    source: SourceConfig = field(default_factory=SourceConfig)
    sleep: SleepConfig = field(default_factory=SleepConfig)
```

It currently contains two configuration areas:

| Field | Type | Responsibility |
|---|---|---|
| `source` | `SourceConfig` | Identifies supported Apple Health data sources |
| `sleep` | `SleepConfig` | Controls sleep-session reconstruction and Sleep Score behavior |

Nested objects use `default_factory`, so each `AppConfig` instance receives independent configuration objects.

Example:

```python
config = AppConfig()

config.source.apple_watch_source = "Custom Watch"
config.sleep.session_gap_threshold_minutes = 45
config.sleep.score.linear_penalties = True
```

## `SourceConfig`

Defined in:

```text
apple_health/config/source_config.py
```

`SourceConfig` identifies source names expected in Apple Health XML records.

### Defaults

| Setting | Default | Purpose |
|---|---:|---|
| `apple_watch_source` | `"Apple Watch"` | Source used for Apple Watch activity and sleep records |
| `apple_health_app_source` | `"Zdrowie"` | Source used for Apple Health application records such as nutrition and body weight |

> **Important:** the default Apple Watch value contains a non-breaking space between `Apple` and `Watch`, matching the source name expected in the exported data.

### Consumers

`SourceConfig` is currently used by:

- `AppleHealthParser` when selecting supported daily metric sources;
- `SleepAnalyzer` when selecting Apple Watch sleep records.

Example override:

```python
config = AppConfig()
config.source.apple_watch_source = "My Apple Watch"
```

The same `config` must then be passed to the parser and analyzer if both should use the custom source.

## `SleepConfig`

Defined in:

```text
apple_health/config/sleep_config.py
```

`SleepConfig` owns configuration for sleep-session reconstruction and contains the nested Sleep Score configuration.

```text
SleepConfig
├── session_gap_threshold_minutes
└── score
```

### Defaults

| Setting | Default | Purpose |
|---|---:|---|
| `session_gap_threshold_minutes` | `30` | Maximum gap between sleep records that may still belong to one reconstructed sleep session |
| `score` | `SleepScoreConfig()` | Daily and monthly Sleep Score configuration |

A gap equal to the configured threshold is valid for joining records into the same session. A larger gap starts a new session.

### Validation

`SleepConfig.validate()` rejects negative session-gap thresholds and delegates Sleep Score validation to `SleepScoreConfig`.

A threshold of `0` is valid. In that case, only directly adjacent records can be joined without a positive gap.

Example:

```python
config = AppConfig()
config.sleep.session_gap_threshold_minutes = 60

config.sleep.validate()
```

## Sleep Score Configuration

Defined in:

```text
apple_health/config/sleep_score_config.py
```

`SleepScoreConfig` controls the complete daily Sleep Score model and optional monthly bonus system.

The daily score consists of:

```text
Bedtime Score
      +
Sleep Duration Score
      +
Wake-up Score
      │
      ▼
weighted Total Sleep Score
```

Each component is scored on a `0–100` scale before the configured component weights are applied.

## `SleepScoreConfig`

### Defaults

| Setting | Default | Purpose |
|---|---:|---|
| `linear_penalties` | `False` | Selects step-based or proportional penalties |
| `bedtime` | `BedtimeScoreConfig()` | Bedtime scoring |
| `duration` | `SleepDurationScoreConfig()` | Sleep-duration scoring |
| `wake_up` | `WakeUpScoreConfig()` | Wake-up scoring |
| `weights` | `SleepScoreWeightsConfig()` | Final daily score weighting |
| `monthly_bonus` | `MonthlySleepBonusConfig()` | Optional monthly bonuses |

### Penalty Modes

With:

```python
config.sleep.score.linear_penalties = False
```

penalties are applied in complete configured intervals.

With:

```python
config.sleep.score.linear_penalties = True
```

partial intervals produce proportional penalties.

For example, with a `15` minute interval and `5` penalty points, a `12` minute deviation produces:

```text
12 / 15 × 5 = 4 penalty points
```

in linear mode.

## `BedtimeScoreConfig`

Controls the Bedtime Score.

### Defaults

| Setting | Default | Purpose |
|---|---:|---|
| `target` | `00:00` | Target bedtime |
| `penalty_interval_minutes` | `15` | Size of one bedtime penalty interval |
| `penalty_points` | `5.0` | Penalty per interval |

Going to bed at or before the target receives the maximum Bedtime Score.

Later bedtimes are penalized according to the selected penalty mode.

Example:

```python
from datetime import time

config = AppConfig()

config.sleep.score.bedtime.target = time(23, 30)
config.sleep.score.bedtime.penalty_interval_minutes = 10
config.sleep.score.bedtime.penalty_points = 4.0
```

## `SleepDurationScoreConfig`

Controls the Sleep Duration Score.

### Defaults

| Setting | Default | Purpose |
|---|---:|---|
| `target_minutes` | `480` | Target sleep duration: 8 hours |
| `tolerance_minutes` | `30` | Allowed deviation around the target without penalty |
| `penalty_interval_minutes` | `15` | Size of one duration penalty interval |
| `penalty_points` | `5.0` | Base penalty per interval |
| `oversleep_weight` | `1.0` | Multiplier applied to oversleep penalties |
| `undersleep_weight` | `1.0` | Multiplier applied to undersleep penalties |

With the defaults, the maximum-score range is:

```text
450–510 minutes
7 h 30 min – 8 h 30 min
```

Duration outside that range is penalized.

The two penalty weights allow oversleeping and undersleeping to have different impacts:

```python
config.sleep.score.duration.oversleep_weight = 0.5
config.sleep.score.duration.undersleep_weight = 1.5
```

## `WakeUpScoreConfig`

Controls the Wake-up Score.

### Defaults

| Setting | Default | Purpose |
|---|---:|---|
| `target` | `08:00` | Target wake-up time |
| `bedtime_weight` | `1.0` | Bedtime Score contribution to the maximum available Wake-up Score |
| `duration_weight` | `2.0` | Duration Score contribution to the maximum available Wake-up Score |
| `penalty_interval_minutes` | `15` | Size of one late wake-up penalty interval |
| `penalty_points` | `3.0` | Penalty per interval |

The maximum available Wake-up Score is derived from Bedtime Score and Duration Score:

```text
Bedtime Score × bedtime_weight
+
Duration Score × duration_weight
─────────────────────────────────
bedtime_weight + duration_weight
```

With the defaults, sleep duration has twice the influence of bedtime on the maximum available Wake-up Score.

Waking later than the configured target then applies additional penalties.

## `SleepScoreWeightsConfig`

Controls how the three daily score components are combined into the final Total Sleep Score.

### Defaults

| Component | Weight |
|---|---:|
| Bedtime | `1.0` |
| Duration | `1.0` |
| Wake-up | `1.0` |

The total score is calculated as:

```text
Bedtime Score × bedtime
+
Duration Score × duration
+
Wake-up Score × wake_up
──────────────────────────
bedtime + duration + wake_up
```

The weights do not need to add up to `1`. They are normalized by their total.

Example:

```python
config.sleep.score.weights.bedtime = 1.0
config.sleep.score.weights.duration = 2.0
config.sleep.score.weights.wake_up = 1.0
```

This makes sleep duration twice as influential as each of the other components.

## `MonthlySleepBonusConfig`

Controls the optional monthly Sleep Score bonus system.

### Defaults

| Setting | Default |
|---|---:|
| `enabled` | `True` |
| `max_points` | `20` |

Default Average Bonus thresholds:

| Minimum monthly average Sleep Score | Bonus |
|---:|---:|
| `90` | `+15` |
| `80` | `+10` |
| `70` | `+5` |

Default Consistency Bonus thresholds:

| Population standard deviation below | Bonus |
|---:|---:|
| `3` | `+5` |
| `6` | `+4` |
| `9` | `+3` |
| `12` | `+2` |
| `15` | `+1` |

The monthly result is:

```text
Average Daily Sleep Score
+ Average Bonus
+ Consistency Bonus
= Monthly Sleep Score
```

With the default `max_points = 20`, the documented maximum monthly score is:

```text
120
```

### Average Bonus

`average_thresholds` is a tuple of:

```python
(score_threshold, bonus_points)
```

Example:

```python
config.sleep.score.monthly_bonus.average_thresholds = (
    (95, 12),
    (85, 8),
    (75, 4),
)
```

Thresholds are evaluated from highest to lowest.

### Consistency Bonus

`consistency_thresholds` is a tuple of:

```python
(standard_deviation_threshold, bonus_points)
```

Example:

```python
config.sleep.score.monthly_bonus.consistency_thresholds = (
    (2, 5),
    (5, 3),
    (10, 1),
)
```

Lower standard deviation represents greater consistency.

### Disabling Monthly Bonuses

```python
config.sleep.score.monthly_bonus.enabled = False
```

When disabled:

- Average Bonus is not applied.
- Consistency Bonus is not applied.
- Monthly Sleep Score remains the average daily Sleep Score.
- Text output reports the monthly bonus system as disabled.

## Validation Rules

Configuration validation protects calculations from invalid or contradictory values.

### Sleep Session Validation

`SleepConfig` requires:

- `session_gap_threshold_minutes >= 0`

### Daily Score Weights

`SleepScoreWeightsConfig` values must satisfy:

- every component weight is non-negative;
- at least one component weight is greater than zero.

Invalid:

```python
config.sleep.score.weights.bedtime = 0
config.sleep.score.weights.duration = 0
config.sleep.score.weights.wake_up = 0
```

### Penalty Intervals

All configured penalty intervals must be greater than zero:

- bedtime penalty interval;
- duration penalty interval;
- wake-up penalty interval.

### Penalty Points

Penalty points for bedtime, duration and wake-up scoring cannot be negative.

A value of `0` is valid and effectively disables that individual penalty while preserving the scoring structure.

### Sleep Duration

Sleep duration configuration requires:

- `target_minutes > 0`;
- `tolerance_minutes >= 0`;
- `tolerance_minutes < target_minutes`.

### Duration Penalty Weights

Both:

```text
oversleep_weight
undersleep_weight
```

must be non-negative.

### Average Bonus Thresholds

Every `(threshold, bonus)` pair must satisfy:

- score threshold is between `0` and `100`;
- bonus points are non-negative;
- score thresholds are strictly decreasing;
- bonus points cannot increase as the required score decreases.

Valid ordering:

```python
(
    (90, 15),
    (80, 10),
    (70, 5),
)
```

Invalid ordering:

```python
(
    (90, 10),
    (80, 15),
)
```

because the lower score requirement grants a larger bonus.

### Consistency Bonus Thresholds

Every `(threshold, bonus)` pair must satisfy:

- deviation threshold is greater than zero;
- bonus points are non-negative;
- deviation thresholds are strictly increasing;
- bonus points cannot increase as greater deviation is allowed.

Valid ordering:

```python
(
    (3, 5),
    (6, 4),
    (9, 3),
)
```

### Maximum Monthly Bonus

The largest possible Average Bonus plus the largest possible Consistency Bonus cannot exceed `monthly_bonus.max_points`.

With the defaults:

```text
15 + 5 = 20
```

which matches:

```python
max_points = 20
```

## Complete Default Configuration

The current default configuration is equivalent to:

```python
from datetime import time

from apple_health.config.app_config import AppConfig


config = AppConfig()

config.source.apple_watch_source = "Apple\xa0Watch"
config.source.apple_health_app_source = "Zdrowie"

config.sleep.session_gap_threshold_minutes = 30

config.sleep.score.linear_penalties = False

config.sleep.score.bedtime.target = time(0, 0)
config.sleep.score.bedtime.penalty_interval_minutes = 15
config.sleep.score.bedtime.penalty_points = 5.0

config.sleep.score.duration.target_minutes = 480
config.sleep.score.duration.tolerance_minutes = 30
config.sleep.score.duration.penalty_interval_minutes = 15
config.sleep.score.duration.penalty_points = 5.0
config.sleep.score.duration.oversleep_weight = 1.0
config.sleep.score.duration.undersleep_weight = 1.0

config.sleep.score.wake_up.target = time(8, 0)
config.sleep.score.wake_up.bedtime_weight = 1.0
config.sleep.score.wake_up.duration_weight = 2.0
config.sleep.score.wake_up.penalty_interval_minutes = 15
config.sleep.score.wake_up.penalty_points = 3.0

config.sleep.score.weights.bedtime = 1.0
config.sleep.score.weights.duration = 1.0
config.sleep.score.weights.wake_up = 1.0

config.sleep.score.monthly_bonus.enabled = True
config.sleep.score.monthly_bonus.max_points = 20

config.sleep.score.monthly_bonus.average_thresholds = (
    (90, 15),
    (80, 10),
    (70, 5),
)

config.sleep.score.monthly_bonus.consistency_thresholds = (
    (3, 5),
    (6, 4),
    (9, 3),
    (12, 2),
    (15, 1),
)
```

Normally these values do not need to be assigned manually because they are already defined as dataclass defaults.

## Example: Custom Sleep Configuration

```python
from datetime import time

from apple_health.config.app_config import AppConfig


config = AppConfig()

config.sleep.session_gap_threshold_minutes = 45

config.sleep.score.linear_penalties = True

config.sleep.score.bedtime.target = time(23, 30)
config.sleep.score.bedtime.penalty_interval_minutes = 10
config.sleep.score.bedtime.penalty_points = 4.0

config.sleep.score.duration.target_minutes = 450
config.sleep.score.duration.tolerance_minutes = 20
config.sleep.score.duration.undersleep_weight = 1.5
config.sleep.score.duration.oversleep_weight = 0.5

config.sleep.score.wake_up.target = time(7, 30)

config.sleep.score.weights.bedtime = 1.0
config.sleep.score.weights.duration = 2.0
config.sleep.score.weights.wake_up = 1.0

config.sleep.validate()
```

The configured instance can then be injected into the processing pipeline:

```python
health_data = AppleHealthParser(
    xml_stream,
    config=config,
).parse()

analyzer = HealthAnalyzer(
    health_data,
    config=config,
)

renderer = JsonRenderer(
    config=config,
)
```

## Why Configuration Is Injected

Previously, configurable values were represented as module-level constants.

That approach works for a fixed application but makes runtime configuration increasingly difficult because consumers become directly coupled to specific modules and global values.

The current model changes that dependency direction:

```text
Before

SleepAnalyzer
    │
    └── imports configuration globals


Now

AppConfig
    │
    ▼
SleepAnalyzer
```

The consuming component no longer needs to know where the configuration came from.

This distinction is important for future configuration sources.

A future loader may construct the same `AppConfig` from:

- a JSON file;
- a YAML file;
- command-line arguments;
- environment variables;
- a database;
- a remote configuration service.

The parser, analyzers and renderers do not need to change when the source of configuration changes.

## Current Limitations

The configuration model and dependency-injection infrastructure are implemented, but external configuration loading is not.

Currently:

- configuration defaults are defined in Python dataclasses;
- the application creates an `AppConfig` at startup;
- configurable components consume that object;
- custom values can be assigned programmatically;
- configuration is not yet loaded from files, environment variables, databases or CLI configuration flags.

In other words, the application currently supports **configuration injection**, but does not yet provide a user-facing **configuration source**.

That distinction is intentional and defines the boundary of the current implementation.

## Future Runtime Configuration

A future configuration-loading feature can populate `AppConfig` before the processing pipeline starts.

Conceptually:

```text
External Configuration Source
          │
          ▼
     Config Loader
          │
          ▼
       AppConfig
          │
     ┌────┼─────────────┐
     ▼    ▼             ▼
  Parser Analyzer    Renderer
```

The exact supported sources, file formats and precedence rules should be defined by that feature rather than by the configuration model itself.

This package should remain responsible for:

- representing configuration;
- providing defaults;
- validating configuration;
- exposing a stable object hierarchy.

Loading and merging external values should remain a separate responsibility.

## Testing

Configuration behavior is covered at several levels:

- `test_app_config.py` verifies root configuration composition and defaults;
- `test_sleep_config.py` verifies sleep-level validation;
- `test_sleep_score_config.py` verifies detailed Sleep Score validation rules;
- analyzer tests verify that injected values affect scoring and session reconstruction;
- parser tests verify custom source injection;
- renderer tests verify configuration-dependent presentation behavior;
- full pipeline tests verify that one shared configuration instance can flow through the application.

Run the complete test suite with:

```bash
pytest
```

Code quality checks:

```bash
ruff check .
black --check .
```

## Package Files

```text
apple_health/config/
├── __init__.py
├── app_config.py
├── source_config.py
├── sleep_config.py
├── sleep_score_config.py
└── README.md
```

## Related Documentation

- [Project README](../../README.md)
- [Test Suite Documentation](../../tests/README.md)
