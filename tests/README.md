# Test Suite

The Apple Health Monitor Analyzer test suite provides automated coverage of the application's core business logic, Apple Health data processing, report generation, configuration validation, and end-to-end component integration.

The suite currently contains **157 test cases**.

## Test structure

| Area | Test cases |
| --- | ---: |
| `SleepAnalyzer` | 38 |
| `ActivityAnalyzer` | 7 |
| `MetricsAnalyzer` | 11 |
| `HealthAnalyzer` | 9 |
| `AppleHealthParser` | 22 |
| Sleep Score configuration | 32 |
| Report models | 17 |
| `TextRenderer` | 11 |
| `AppleHealthImporter` | 6 |
| Integration tests | 4 |
| **Total** | **157** |

## Analyzers

### SleepAnalyzer

`tests/analyzers/test_sleep_analyzer.py` contains **38 test cases** covering the complete sleep-analysis and scoring flow.

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

`tests/analyzers/test_health_analyzer.py` contains **9 test cases**.

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

## AppleHealthParser

`tests/test_parser.py` contains **22 test cases** using synthetic Apple Health XML.

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

## Sleep Score configuration

`tests/test_sleep_score_config.py` contains **32 parameterized test cases** covering configuration validation.

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

The tests use `pytest`'s `monkeypatch` fixture so that intentionally invalid configurations are isolated to individual test cases and the default module configuration is restored automatically afterwards.

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
- weighted daily Sleep Score calculation

Simple dataclass field storage is intentionally not tested; the suite focuses on derived behavior and business-relevant properties.

## TextRenderer

`tests/renderers/test_text_renderer.py` contains **11 test cases** covering the renderer's public textual output contract.

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

`tests/integration/test_full_report_pipeline.py` contains **4 end-to-end integration tests**.

They exercise the complete application pipeline:

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
    ↓
TextRenderer
    ↓
Final text report
```

The integration suite verifies:

- successful execution of the complete report-generation pipeline
- preservation of expected values across importing, parsing, analysis, and aggregation
- generation of a monthly-summary-only report without daily sections
- exact deterministic output through a golden-report comparison

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
- cover meaningful boundary conditions explicitly
- use parameterization when the same rule applies to multiple configuration values
- use integration tests to protect component wiring
- use a golden report to protect the deterministic final output contract
- avoid tests that merely confirm that dataclass fields store assigned values

This keeps the test suite useful during future refactoring while still providing strong regression protection for the application's core behavior.
