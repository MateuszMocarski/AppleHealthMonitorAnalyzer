# Test Suite

The Apple Health Monitor Analyzer test suite provides automated coverage of the application's core business logic, Apple Health data processing, report generation, configuration validation, and end-to-end component integration.

The suite currently contains **220 test cases**.

## Test structure

| Area | Test cases |
| --- | ---: |
| `SleepAnalyzer` | 39 |
| `ActivityAnalyzer` | 7 |
| `MetricsAnalyzer` | 11 |
| `HealthAnalyzer` | 10 |
| `AppleHealthParser` | 24 |
| `AppConfig` | 1 |
| `ConfigLoader` | 27 |
| `SleepConfig` | 3 |
| Sleep Score configuration | 32 |
| Report models | 17 |
| `TextRenderer` | 12 |
| `JsonRenderer` | 21 |
| `AppleHealthImporter` | 6 |
| Integration tests | 10 |
| **Total** | **220** |

## Analyzers

### SleepAnalyzer

`tests/analyzers/test_sleep_analyzer.py` contains **39 test cases** covering the complete sleep-analysis and scoring flow.

The suite verifies:

- reconstruction of sleep sessions from individual Apple Health sleep records
- session splitting based on the configured gap threshold
- the exact session-gap boundary condition
- selection of the longest primary sleep session for a reporting day
- filtering of sleep records by Apple Watch source
- reporting-date assignment, including the noon boundary
- bedtime scoring before, at, and after the configured target
- step-based and linear bedtime penalties
- sleep-duration target and tolerance boundaries
- undersleep and oversleep penalties
- wake-up score calculation and configured component weighting
- wake-up penalties and the zero-score floor
- daily weighted Sleep Score calculation
- monthly average component and total scores
- average-score monthly bonus selection
- consistency bonus calculation based on population standard deviation
- single-session consistency behavior
- final monthly Sleep Score calculation
- awake-time handling
- sleep efficiency
- `IN_BED` handling
- lookup behavior when no primary session exists
- average bedtime calculation across midnight
- score lower boundaries
- disabled monthly bonus behavior
- dependency injection of the configured sleep-session gap threshold

### ActivityAnalyzer

`tests/analyzers/test_activity_analyzer.py` contains **7 test cases**.

The suite verifies:

- grouping workouts by calendar day
- counting unique active days
- returning an empty list for days without workouts
- daily aggregation of workouts by activity type
- separation of different workout types
- preservation of `None` when activity distance is unavailable
- monthly aggregation limited by the completed reporting-day range

### MetricsAnalyzer

`tests/analyzers/test_metrics_analyzer.py` contains **11 test cases**.

The suite verifies:

- lookup of metrics for a specific day
- missing-day lookup behavior
- reporting-day filtering
- monthly step and distance totals
- daily step and distance averages
- basal and active energy averages
- average step length
- zero-step handling
- nutrition aggregation and averaging
- body-weight statistics
- behavior when no weight measurements are available

### HealthAnalyzer

`tests/analyzers/test_health_analyzer.py` contains **10 test cases**.

These tests focus on orchestration rather than repeating the business rules already covered by the specialized analyzers.

The suite verifies:

- construction of a complete `DailySummary`
- safe default values when daily metrics are unavailable
- attachment of sleep sessions and Sleep Scores to daily summaries
- exclusion of the final partially completed data day
- full reporting periods for historical months
- zero reporting days for months after the available data
- construction of a complete `MonthlySummary` from delegated analyzer results
- monthly summary generation when no sleep data is available
- monthly summary generation when no activity metrics are available for the reporting period
- propagation of injected `AppConfig` into `SleepAnalyzer`

## AppleHealthParser

`tests/test_parser.py` contains **24 test cases** using synthetic Apple Health XML.

The suite verifies:

- standard workout-type mapping
- indoor cycling detection through workout metadata
- outdoor cycling fallback
- unknown workout mapping to `OTHER`
- workout active-energy parsing
- walking/running distance parsing
- cycling distance parsing
- aggregation of Apple Watch daily metrics
- rejection of Apple Watch metrics from incorrect sources
- ignoring unsupported daily metric types
- nutrition aggregation
- rejection of Apple Health metrics from incorrect sources
- preference for user-entered body-weight measurements
- selection of the latest weight measurement when entry types are equivalent
- chronological sorting of parsed daily metrics
- all known Apple sleep-stage mappings
- fallback of unknown sleep stages to `OTHER`
- sleep-record duration calculation from timestamps
- injected custom Apple Watch source selection
- injected custom Apple Health application source selection

## Application configuration

### AppConfig

`tests/config/test_app_config.py` contains **1 test case** verifying root configuration composition.

The test verifies:

- creation of the default `SourceConfig`
- creation of the default `SleepConfig`
- default source values
- default sleep-session gap threshold

### ConfigLoader

`tests/config/test_config_loader.py` contains **27 test cases** covering TOML configuration loading.

The suite verifies:

- default `AppConfig` behavior when no path is provided
- full and partial source configuration
- case-insensitive configuration keys
- unknown top-level, source, and nested fields
- missing and malformed TOML files
- sleep-session configuration
- nested Sleep Score configuration
- bedtime and wake-up `HH:MM` parsing
- duration configuration
- daily score component weights
- monthly bonus thresholds
- numeric string coercion for numeric fields
- strict boolean and string typing
- invalid threshold shapes
- final configuration validation
- preservation of defaults for omitted nested values

The loader tests treat configuration loading as a public boundary: valid TOML must produce a validated `AppConfig`, while invalid configuration must fail with `ConfigurationError`.

### SleepConfig

`tests/config/test_sleep_config.py` contains **3 test cases** covering sleep-level configuration validation.

The suite verifies:

- validity of the default sleep configuration
- rejection of negative sleep-session gap thresholds
- acceptance of a zero-minute gap threshold

## Sleep Score configuration

`tests/config/test_sleep_score_config.py` contains **32 parameterized test cases** covering configuration validation.

The suite verifies:

- validity of the default configuration
- non-negative daily component weights
- rejection of an all-zero component-weight configuration
- positive penalty intervals
- non-negative penalty points
- positive sleep-duration target
- non-negative sleep-duration tolerance
- requirement for tolerance to remain below the target duration
- non-negative undersleep and oversleep penalty weights
- valid `0-100` monthly average bonus thresholds
- non-negative average bonus points
- strictly decreasing average-score thresholds
- non-increasing bonuses as average-score thresholds decrease
- positive consistency thresholds
- non-negative consistency bonuses
- strictly increasing consistency thresholds
- non-increasing bonuses as allowed deviation increases
- enforcement of the configured maximum monthly bonus cap

Each validation test creates its own `SleepScoreConfig` instance, so invalid test values remain isolated without mutating shared application state.

## Report models

`tests/test_report_models.py` contains **17 test cases** covering calculated properties exposed by report models.

The suite verifies:

- daily average step length
- zero-step behavior
- daily TDEE
- daily calorie balance
- missing nutrition behavior
- monthly `data_through`
- zero-reporting-day behavior
- average monthly TDEE
- body-weight change
- incomplete body-weight change data
- average monthly calorie balance
- sleep efficiency
- sleep reporting dates before noon and from noon onward
- monthly Sleep Score composition
- preservation of the analyzer-calculated daily `total_score` value

Simple dataclass field storage is intentionally not tested; the suite focuses on derived behavior and business-relevant properties.

## TextRenderer

`tests/renderers/test_text_renderer.py` contains **12 test cases** covering the renderer's public textual output contract.

The suite verifies:

- presence of all major sections in the monthly summary
- inclusion of daily reports in a full monthly report
- omission of the monthly body-weight section when no measurements exist
- explicit messaging when daily nutrition data is missing
- distinction between activity without workouts and complete absence of activity
- rendering of the disabled monthly Sleep Score bonus state
- omission of monthly sleep sections when sleep data is unavailable
- omission of the monthly workouts section when no workouts exist
- omission of monthly nutrition when nutrition data is unavailable
- omission of monthly energy expenditure when energy data is unavailable
- omission of monthly general activity when step and distance data are unavailable
- rendering of the effective injected Sleep configuration in monthly summaries

The renderer tests intentionally avoid testing every private `print()` helper individually. They verify user-visible behavior through the public `render_month()` and `render_month_summary()` methods.

### Partial monthly reports

Monthly reports are designed to remain renderable when individual data categories are unavailable. The report header is always produced, while optional sections are rendered only when their underlying data exists.

The regression suite explicitly protects partial-report behavior for:

- missing sleep data
- missing workouts
- missing activity metrics
- missing nutrition data
- missing energy expenditure data
- missing general activity data
- missing body-weight measurements

This allows a valid monthly report to be produced from incomplete Apple Health datasets without representing missing information as real zero-valued measurements.


## JsonRenderer

`tests/renderers/test_json_renderer.py` contains **21 test cases** covering the versioned JSON report contract for both monthly summaries and detailed daily reports.

The monthly contract tests verify:

- stable top-level schema keys and `schema_version`
- report metadata and ISO-compatible `data_through`
- general activity representation
- sleep summary, sleep stages and monthly Sleep Score data
- configured maximum monthly Sleep Score
- stable workout identifiers derived from enum names
- explicit workout averaging basis (`daily` or `workout`)
- body-weight statistics
- energy expenditure
- nutrition
- calorie balance as a separate top-level API concept
- normalized two-decimal numeric precision
- `null` for unavailable optional sections
- `[]` for empty workout collections
- partial metric availability
- reports with zero completed reporting days
- injected configuration for the maximum monthly Sleep Score
- exposure of the effective injected Sleep configuration, including API-friendly threshold objects

The daily contract tests verify:

- inclusion of detailed `days` in full monthly JSON output
- daily general activity
- daily workout details without monthly averaging fields
- daily body weight
- daily energy expenditure and TDEE
- daily nutrition with calorie balance kept as a separate concept
- full ISO sleep timestamps with timezone offsets
- daily sleep-stage details
- daily Sleep Score components and total
- preservation of `null` and empty collections in partial daily reports

The JSON tests deserialize renderer output with `json.loads()` and validate the resulting data structure rather than whitespace or indentation. This treats JSON as a stable external data contract while allowing harmless formatting changes.

The renderer intentionally does not serialize internal dataclasses directly. Its explicit builder methods define a controlled API-friendly representation with stable field names, measurement units encoded in keys, technical enum identifiers, and predictable handling of missing data.

## AppleHealthImporter

`tests/test_importer.py` contains **6 test cases** using temporary ZIP archives.

The suite verifies:

- missing archive handling
- successful opening of an archive containing exactly one valid export XML
- ignoring non-XML files
- ignoring CDA XML documents
- rejection of archives containing no valid export XML
- rejection of archives containing more than one valid export XML

Temporary files are created with pytest's `tmp_path` fixture, allowing the importer to be tested against real ZIP archives without storing generated archives in the repository.

## Integration tests

`tests/integration/test_full_report_pipeline.py` contains **10 end-to-end integration tests**.

They exercise the complete application pipeline using one shared `AppConfig` instance across configuration-aware components:

```text
ZIP archive
    ↓
AppleHealthImporter
    ↓
AppleHealthParser
    ↓
AppleHealthData
    ↓
HealthAnalyzer
    ├── ActivityAnalyzer
    ├── MetricsAnalyzer
    └── SleepAnalyzer
    ↓
MonthlySummary
    ├──→ TextRenderer
    │        ↓
    │    Final text report
    │
    └──→ JsonRenderer
             ↓
         Final JSON report
```

The end-to-end integration suite exercises both the text- and JSON-rendering pipelines. `JsonRenderer` is additionally covered by dedicated contract tests at the renderer layer.

The integration suite verifies:

- successful execution of the complete report-generation pipeline
- propagation of one shared `AppConfig` through parser, analyzer, and renderer layers
- preservation of expected values across importing, parsing, analysis, and aggregation
- generation of a monthly-summary-only text report without daily sections
- exact deterministic text output through a golden-report comparison
- generation of a valid full JSON report containing monthly summary data and detailed daily reports
- generation of a valid JSON monthly summary without the `days` collection
- loading the committed example TOML configuration
- observable report changes produced by runtime TOML overrides
- preservation of default pipeline behavior when no configuration file is supplied
- presence of effective Sleep configuration in monthly text and JSON report output

The approved reference output is stored in:

```text
tests/integration/fixtures/expected_report.txt
```

The fixture contains synthetic test data only and does not contain a real Apple Health export.

## Golden report

The golden-report integration test compares the complete generated report against the approved `expected_report.txt` fixture.

This protects the final report contract from accidental changes such as:

- modified calculations
- missing sections
- changed ordering
- unexpected formatting changes
- changed whitespace or line breaks

When a report-format change is intentional, the generated diff should be reviewed before updating the golden fixture.

## Running the tests

Run the complete suite:

```bash
pytest
```

Run the complete suite with verbose output:

```bash
pytest -v
```

Run a specific test module:

```bash
pytest tests/analyzers/test_sleep_analyzer.py
```

Run a specific test:

```bash
pytest tests/analyzers/test_sleep_analyzer.py::test_reconstructs_single_sleep_session
```

Disable pytest output capturing when temporary diagnostic `print()` output is needed:

```bash
pytest -s
```

Collect tests without executing them:

```bash
pytest --collect-only -q
```

## Code quality

Run Ruff:

```bash
ruff check .
```

Check Black formatting:

```bash
black --check .
```

## Test design principles

The suite follows several general rules:

- test public behavior and business rules rather than implementation details wherever practical
- use synthetic health data instead of private Apple Health exports
- use configuration-relative expectations instead of hardcoding configurable values
- use one explicit configuration instance when a test verifies dependency-injected behavior
- cover meaningful boundary conditions explicitly
- use parameterization when the same rule applies to multiple configuration values
- use integration tests to protect component wiring
- use a golden report to protect the deterministic final text output contract
- test JSON through parsed structures to protect the versioned API contract independently of whitespace
- preserve explicit `null` and empty-collection semantics in JSON contract tests
- avoid tests that merely confirm that dataclass fields store assigned values

This keeps the test suite useful during future refactoring while still providing strong regression protection for the application's core behavior.
