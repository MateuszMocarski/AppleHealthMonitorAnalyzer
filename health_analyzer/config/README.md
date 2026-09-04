# Configuration

The `health_analyzer.config` package defines the application's strongly typed configuration model.

Configuration is represented by Python `dataclass` objects rather than module-level globals. The root `AppConfig` object groups configuration by responsibility and can be injected into the components that depend on configurable behavior.

Configuration values are defined by defaults in the dataclasses, may be overridden by an optional TOML file loaded through `ConfigLoader`, and may receive per-request source-name overrides from the web/API workflow.

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

This structure replaces the previous approach based on module-level configuration constants and provides the stable object model used by runtime configuration loading.

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

The application layer creates one `AppConfig` instance for each processing run and passes it to components that require configurable behavior.

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

This fallback is primarily useful for standalone use and tests. Application execution should prefer one shared configuration instance for the complete processing run.

## Runtime TOML Configuration

The application supports optional TOML configuration plus narrow runtime overrides for the two `SourceConfig` fields.

For CLI execution, application configuration can be selected directly with:

```bash
python app.py import export.zip --config path/to/config.toml
```

or indirectly through a run profile:

```toml
[run]
config = "path/to/config.toml"
```

Run profiles configure *how the application is executed*; this package continues to define *how Apple Health data is interpreted and scored*. The two configuration concerns remain separate.

The browser/API workflow can upload the same TOML configuration as multipart field `config`. The uploaded file is temporary and exists only for the request.

`ConfigLoader.load()` also accepts optional runtime source overrides:

```python
config = ConfigLoader.load(
    config_path,
    apple_watch_source="Custom Watch",
    health_analyzer_app_source="Custom Health",
)
```

These are intentionally limited to source-name selection rather than exposing every configuration setting as a separate HTTP field.

The effective application configuration is resolved using:

```text
dataclass defaults
        ↓
TOML overrides
        ↓
runtime source overrides
```

Equivalently, when deciding which supplied value wins:

```text
runtime/UI source override
        >
TOML value
        >
dataclass default
```

A runtime source argument equal to `None` means “do not override”. At the FastAPI boundary, blank or whitespace-only source fields are normalized to `None`.

When no TOML path is supplied and no runtime source override is present, `ConfigLoader.load(None)` returns the default validated `AppConfig`.

When a TOML path is supplied, `ConfigLoader` reads and parses the file, normalizes keys to lowercase, rejects unknown fields, converts supported values, builds nested configuration dataclasses, preserves defaults for omitted values, applies any runtime source overrides, validates the final `AppConfig`, and returns it or raises `ConfigurationError`.

### Partial Configuration

TOML files do not need to contain every setting.

```toml
[sleep.score.duration]
target_minutes = 450
undersleep_weight = 1.5
```

Only the listed values override defaults. Runtime source overrides are then applied independently after TOML loading.

Example:

```toml
[source]
apple_watch_source = "Watch from TOML"
health_analyzer_app_source = "Health from TOML"
```

with:

```python
ConfigLoader.load(
    path,
    apple_watch_source="Watch from UI",
)
```

produces:

```text
apple_watch_source      = "Watch from UI"
health_analyzer_app_source = "Health from TOML"
```

### Key Matching

Configuration keys are case-insensitive. After normalization, names must match dataclass field names exactly. Unknown fields fail fast.

### Supported Value Conversion

The loader accepts normal finite TOML numeric values, simple numeric strings for numeric fields, strict TOML booleans, strings, `HH:MM` values for time fields, and arrays of two-item arrays for monthly bonus thresholds. Non-finite values such as `nan`, `inf`, and `-inf` are rejected before the final configuration object is returned.

### Errors

Configuration failures are exposed through `ConfigurationError`, including missing files, malformed TOML, unreadable files, unknown fields, invalid types, invalid/non-finite numeric values, invalid time values, malformed threshold arrays, and final validation failures.

The web/API adapter maps configuration errors caused by an uploaded TOML file to HTTP 422 instead of exposing them as internal server failures.

## `AppConfig`

Defined in:

```text
health_analyzer/config/app_config.py
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
health_analyzer/config/source_config.py
```

`SourceConfig` identifies source names expected in Apple Health XML records.

### Defaults

| Setting | Default | Purpose |
|---|---:|---|
| `apple_watch_source` | `"Apple Watch"` | Source used for Apple Watch activity and sleep records |
| `health_analyzer_app_source` | `"Zdrowie"` | Source used for Apple Health application records such as nutrition and body weight |

> **Important:** the default Apple Watch value contains a non-breaking space between `Apple` and `Watch`. In escaped form the value is `Apple\xa0Watch`; `Apple Watch` with a normal space is a different string. The built-in default is also a special family matcher: it accepts the bare default and standard device-named values such as `Apple\xa0Watch (Mateusz)`. Any explicit Watch value supplied through TOML or a runtime/UI override is matched exactly.

### Consumers

`SourceConfig` is currently used by:

- `AppleHealthParser` when selecting supported daily metric sources;
- `SleepAnalyzer` when selecting Apple Watch sleep records.

The same effective `AppConfig` is passed through parsing and analysis, so source selection remains consistent across components.

### Runtime overrides

The two source names are the only application settings currently exposed as dedicated per-request web/API overrides.

```python
config = ConfigLoader.load(
    path,
    apple_watch_source="My Apple Watch",
)
```

If an override is omitted, the corresponding TOML value remains effective. If TOML also omits it, the dataclass default remains effective. Explicit Watch overrides use exact matching; only the untouched built-in `Apple\xa0Watch` value enables the standard Apple Watch family matcher.

The browser intentionally leaves both source fields blank by default and documents both the family-matching behavior and the Apple Watch NBSP requirement to avoid silently replacing the built-in matcher with a visually similar normal-space string.

## `SleepConfig`

Defined in:

```text
health_analyzer/config/sleep_config.py
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
health_analyzer/config/sleep_score_config.py
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

When the monthly bonus system is enabled, the maximum monthly score is calculated dynamically as `100 + max_points`.

With the default `max_points = 20`, the maximum monthly score is:

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
- The effective maximum monthly score remains `100`.
- Text output reports the monthly bonus system as disabled.
- JSON output exposes `monthly_score_max` as `100`.

## Validation Rules

Configuration validation protects calculations from invalid or contradictory values.

### Sleep Session Validation

`SleepConfig` requires:

- `session_gap_threshold_minutes >= 0`

### Finite Numeric Values

All floating-point Sleep Score values must be finite. `NaN`, positive infinity, and negative infinity are rejected before scoring. This includes penalty points, duration/wake-up weights, daily component weights, and both values in monthly bonus threshold pairs.

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

### Wake-up Component Weights

`WakeUpScoreConfig.bedtime_weight` and `WakeUpScoreConfig.duration_weight` must both be non-negative, and at least one of them must be greater than zero. This prevents division by zero when calculating the maximum available Wake-up Score.

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

from health_analyzer.config.app_config import AppConfig


config = AppConfig()

config.source.apple_watch_source = "Apple\xa0Watch"
config.source.health_analyzer_app_source = "Zdrowie"

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

## Example TOML Files

The repository includes example configuration profiles in:

```text
health_analyzer/config/examples/
├── config.example.toml
├── config.undersleeping.toml
├── config.oversleeping.toml
├── config.strict-schedule.toml
└── config.lenient.toml
```

`config.example.toml` contains the complete current configuration using the application defaults and serves as the primary reference template. The other profiles demonstrate partial configuration.

CLI example:

```bash
python app.py import export.zip --config health_analyzer/config/examples/config.strict-schedule.toml
```

The browser interface can also download the complete `config.example.toml` directly from its advanced settings section and then re-upload a customized copy for one report-generation request.

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

Generic runtime configuration loading currently supports TOML only.

The web/API layer additionally exposes only two direct per-request override fields:

- `apple_watch_source`
- `health_analyzer_app_source`

Other sleep/scoring settings must currently be changed through TOML rather than individual UI controls.

The application does not currently load application configuration from JSON or YAML files, environment variables, databases, or remote configuration services. It also does not expose generic per-setting CLI override flags for the `AppConfig` hierarchy.

These limitations are deliberate: parser, analyzer, and renderer consumers depend only on the final `AppConfig`, so future configuration sources can be added without changing the configuration object hierarchy they consume.

## Future Configuration Sources

Future loaders may construct the same `AppConfig` from other sources while keeping the configuration model stable.

The planned Google identity/Drive phase does not require changing this configuration contract: uploaded TOML and runtime source overrides remain request-scoped inputs, while report persistence is a separate application concern.

## Testing

Configuration behavior is covered at several levels:

- `test_app_config.py` verifies root configuration composition and defaults;
- `test_sleep_config.py` verifies sleep-level validation;
- `test_sleep_score_config.py` verifies detailed Sleep Score validation rules;
- analyzer tests verify that injected values affect scoring and session reconstruction;
- parser tests verify custom source injection and missing-data preservation;
- renderer tests verify configuration-dependent presentation behavior;
- `test_config_loader.py` contains **40 collected cases** covering TOML loading, type conversion, finite-number rejection, blank-source rejection, partial overrides, error handling, final validation, committed example files, runtime source overrides, and `runtime override > TOML > default` precedence;
- application tests verify that `MultiMonthRunOptions` forwards runtime source overrides into `ConfigLoader`;
- FastAPI tests verify source-field normalization, optional TOML upload, temporary-file cleanup, malformed-config HTTP 422 behavior, and the dedicated 1 MiB config-upload limit;
- full pipeline tests verify that one shared effective configuration instance flows through parser, analyzer, and renderer layers;
- integration tests verify that TOML overrides produce observable report changes and that the reference example configuration remains loadable.

Run the complete project test suite with:

```bash
pytest
```

The current repository collects **386 tests**.

Code quality checks:

```bash
ruff check .
black --check .
```

## Package Files

The built wheel includes the TOML files under `health_analyzer/config/examples/` because the browser serves `config.example.toml` at runtime. This README is repository documentation and is not required by the runtime package.

```text
health_analyzer/config/
├── __init__.py
├── app_config.py
├── config_loader.py
├── examples/
│   ├── config.example.toml
│   ├── config.undersleeping.toml
│   ├── config.oversleeping.toml
│   ├── config.strict-schedule.toml
│   └── config.lenient.toml
├── exceptions.py
├── source_config.py
├── sleep_config.py
├── sleep_score_config.py
└── README.md
```

## Related Documentation

- [Project README](../../README.md)
- [Test Suite Documentation](../../tests/README.md)
