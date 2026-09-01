# Test Suite

The Apple Health Monitor Analyzer test suite provides automated coverage of the application's core business logic, Apple Health data processing, report generation, configuration validation, and end-to-end component integration.

The suite currently contains **386 collected test cases**.

## Test structure

| Area | Test cases |
| --- | ---: |
| `SleepAnalyzer` | 45 |
| `ActivityAnalyzer` | 9 |
| `MetricsAnalyzer` | 17 |
| `HealthAnalyzer` | 14 |
| FastAPI | 40 |
| `AppleHealthParser` | 36 |
| CLI | 5 |
| `AppleHealthApplication` | 4 |
| `ReportPeriod` | 10 |
| `RunOptions` | 1 |
| `RunOptionsResolver` | 9 |
| `RunProfile` | 1 |
| `RunProfileLoader` | 8 |
| `AppConfig` | 1 |
| `ConfigLoader` | 40 |
| `SleepConfig` | 3 |
| Sleep Score configuration | 39 |
| Report models | 26 |
| `TextRenderer` | 23 |
| `JsonRenderer` | 32 |
| `AppleHealthImporter` | 11 |
| Packaging | 1 |
| Integration tests | 11 |
| **Total** | **386** |

Counts are based on `pytest --collect-only -q`, so parameterized cases are counted individually.

## Analyzers

### SleepAnalyzer

`tests/analyzers/test_sleep_analyzer.py` contains **45 test cases** covering the complete sleep-analysis and scoring flow.

The suite verifies:

- reconstruction of sleep sessions from individual Apple Health sleep records
- chronological normalization of unsorted sleep records before session reconstruction
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
- exact matching for explicit Apple Watch sleep sources and family matching for the built-in default
- safe zero-duration sleep efficiency
- `AsleepUnspecified` contribution to total sleep time and monthly stage averages

### ActivityAnalyzer

`tests/analyzers/test_activity_analyzer.py` contains **9 test cases**.

The suite verifies:

- grouping workouts by calendar day
- counting unique active days
- returning an empty list for days without workouts
- daily aggregation of workouts by activity type
- separation of different workout types
- preservation of `None` when activity distance is unavailable
- preservation of `None` for aggregate distance when any contributing workout is missing distance
- preservation of `None` for aggregate active energy when any contributing workout is missing energy
- monthly aggregation limited by the completed reporting-day range

### MetricsAnalyzer

`tests/analyzers/test_metrics_analyzer.py` contains **17 collected test cases**.

The suite verifies:

- lookup of metrics for a specific day
- missing-day lookup behavior
- reporting-day filtering
- monthly step and distance totals
- daily step and distance averages
- basal and active energy averages
- TDEE averaging only across days where both basal and active energy exist
- independent basal, active, and TDEE contributing-day coverage
- average step length
- zero-step handling
- preservation of completely missing nutrition
- nutrition averaging only across days where each specific nutrient exists
- independent calorie, protein, carbohydrate, and fat coverage
- calorie balance calculated from complete daily intersections of calories, basal energy, and active energy
- independent step, distance, and step-length contributing-day coverage
- body-weight statistics
- behavior when no weight measurements are available

These tests explicitly protect the rule that derived monthly values are calculated from complete daily inputs rather than by combining independently averaged metrics with different denominators.

### HealthAnalyzer

`tests/analyzers/test_health_analyzer.py` contains **14 test cases**.

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
- empty `AppleHealthData` without reporting-boundary crashes
- workout-only and sleep-only datasets determining the last available data day
- preservation of missing workout active energy in daily totals

## AppleHealthParser

`tests/test_parser.py` contains **36 collected test cases** using synthetic Apple Health XML.

The suite verifies:

- standard workout-type mapping
- indoor cycling detection through workout metadata
- outdoor cycling fallback
- unknown workout mapping to `OTHER`
- workout active-energy parsing
- walking/running distance parsing
- cycling distance parsing
- aggregation of Apple Watch daily metrics
- preservation of missing active/basal energy as `None`
- rejection of Apple Watch metrics from incorrect sources
- ignoring unsupported daily metric types
- nutrition aggregation
- preservation of missing individual nutrients as `None`
- rejection of Apple Health metrics from incorrect sources
- preference for user-entered body-weight measurements
- selection of the latest weight measurement when entry types are equivalent
- chronological sorting of parsed daily metrics
- all known Apple sleep-stage mappings
- fallback of unknown sleep stages to `OTHER`
- sleep-record duration calculation from timestamps
- injected custom Apple Watch source selection
- injected custom Apple Health application source selection
- exact matching for explicit source overrides and standard device-name family matching for the built-in Apple Watch source
- preservation of missing steps/distance on days without those activity records
- rejection of XML documents whose root element is not Apple Health `HealthData`
- rejection of malformed XML syntax
- rejection of invalid numeric values and missing required attributes in supported records
- rejection of non-finite numeric values (`NaN` and positive/negative infinity)

The parser regression tests protect `missing != zero` and the parser error contract: missing measurements remain unavailable, while malformed or semantically invalid supported XML is normalized to `HealthDataParseError` instead of leaking implementation exceptions.

## CLI

`tests/test_cli.py` contains **5 test cases** covering command-line parsing and validation.

The suite verifies:

- unresolved optional CLI arguments remain `None` for later profile/default resolution
- parsing of a complete import command into typed argument values
- explicit `--enforce-daily` handling for monthly-summary precedence
- rejection of the `import` command without an archive path
- rejection of an archive path supplied without the `import` command

The CLI tests focus on the command-line adapter boundary. Application execution, run-profile precedence, and report-generation behavior remain covered independently by the application and integration test suites.

## FastAPI

`tests/api/test_api.py` contains **40 collected test cases** covering the HTTP boundary and browser-facing report-generation behavior.

The suite verifies:

- the `/health` endpoint
- availability of the browser favicon
- successful report generation through the real application pipeline
- multi-month requests and four report variants per month
- strict period validation, whitespace handling, duplicate rejection, and the maximum requested-period limit
- missing uploads
- chunked archive upload handling and the compressed upload-size limit
- malformed, empty, and otherwise invalid ZIP archives
- missing and multiple eligible Apple Health export XML entries
- malformed XML and non-Apple-Health XML roots
- localized/non-standard filenames without trusting the client filename or MIME type as proof of validity
- the uncompressed export XML size limit
- deletion of the temporary archive after both successful and failed processing
- stable client-facing mappings for known upload/XML errors
- preservation of unexpected server exceptions as server errors
- prevention of internal exception messages and local filesystem paths leaking into 500 responses
- `Cache-Control: no-store` on responses containing generated health reports
- forwarding explicit Apple Watch and Apple Health source overrides
- normalization of blank/whitespace source fields to “no override”
- presence of source-override controls and built-in Apple Watch family/NBSP guidance in the browser UI
- canonical `/config.example.toml` download backed by the packaged example file
- optional `config.toml` upload and forwarding through `config_path`
- deletion of the temporary uploaded configuration after request completion
- malformed and non-finite TOML mapping to HTTP 422
- semantically invalid/non-finite Apple Health XML mapping to the stable invalid-XML HTTP 422 response
- the dedicated uploaded-config size limit and HTTP 413 behavior
- request-scoped temporary-directory cleanup while keeping files reopenable by path during application processing

API tests intentionally exercise both synthetic real-pipeline requests and isolated error/orchestration cases. This keeps the HTTP contract explicit without duplicating analyzer and renderer business-rule coverage.

## Application layer

Application-layer tests cover both the original single-month CLI execution contract and the multi-month report-generation workflow used by the FastAPI adapter.

### AppleHealthApplication

`tests/application/test_application.py` contains **4 collected test cases**.

The suite verifies:

- orchestration of a single monthly text report independently of the CLI
- selection of JSON monthly-summary rendering from resolved `RunOptions`
- generation of all four report variants for multiple months
- exactly one parser invocation for a multi-month generation call
- preservation of requested period order
- forwarding runtime source overrides from `MultiMonthRunOptions` to `ConfigLoader`

The multi-month application tests therefore protect both parse-once behavior and the configuration bridge used by the web/API adapter.

### ReportPeriod

`tests/application/test_report_period.py` contains **10 collected test cases** after parameterization.

The suite verifies:

- parsing of the strict `YYYY-MM` representation
- rejection of malformed period formats
- rejection of month values outside `1`–`12`
- rejection of non-positive years

### Run options and profiles

The remaining application tests cover `RunOptions`, `RunOptionsResolver`, `RunProfile`, and `RunProfileLoader`.

The suite verifies:

- construction of final `RunOptions`
- partial `RunProfile` values
- TOML run-profile loading
- rejection of unknown run-profile fields and top-level sections
- validation of supported output formats
- validation of resolved month/year ranges, output format, and monthly-summary type
- built-in run-option defaults
- run-profile values overriding defaults
- explicit CLI values overriding run-profile values
- boolean precedence for monthly-summary mode
- rejection of execution without an archive path
- compatibility of all committed example run-profile TOML files

The resolver establishes the runtime precedence contract:

```text
CLI flags > run profile > built-in defaults
```

The application boundary keeps CLI and HTTP adapters out of report-processing business logic. `AppleHealthApplication.run()` preserves the single-month CLI contract, while `generate_reports()` provides the parse-once, multi-month contract used by the API.

## Application configuration

### AppConfig

`tests/config/test_app_config.py` contains **1 test case** verifying root configuration composition.

The test verifies:

- creation of the default `SourceConfig`
- creation of the default `SleepConfig`
- default source values
- default sleep-session gap threshold

### ConfigLoader

`tests/config/test_config_loader.py` contains **40 collected test cases** covering TOML configuration loading and runtime source overrides.

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
- compatibility of all committed example application configuration TOML files
- runtime source overrides replacing built-in defaults
- runtime source overrides taking precedence over TOML while preserving non-overridden TOML values
- rejection of blank configured/runtime source values
- rejection of non-finite numeric TOML values

The loader tests treat configuration loading as a public boundary: valid inputs must produce a validated `AppConfig`, invalid configuration must fail with `ConfigurationError`, and precedence must remain `runtime source overrides > TOML > defaults`.

### SleepConfig

`tests/config/test_sleep_config.py` contains **3 test cases** covering sleep-level configuration validation.

The suite verifies:

- validity of the default sleep configuration
- rejection of negative sleep-session gap thresholds
- acceptance of a zero-minute gap threshold

## Sleep Score configuration

`tests/config/test_sleep_score_config.py` contains **39 collected test cases** covering configuration validation.

The suite verifies:

- validity of the default configuration
- non-negative daily component weights
- rejection of an all-zero component-weight configuration
- non-negative wake-up component weights and rejection of an all-zero wake-up weighting
- rejection of non-finite Sleep Score values and monthly bonus thresholds
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

`tests/test_report_models.py` contains **26 collected test cases** covering business-relevant properties and incomplete-data semantics exposed by report models.

The suite verifies:

- daily average step length
- zero-step behavior
- daily TDEE with complete energy data
- unavailable daily TDEE when basal or active energy is missing
- daily calorie balance
- unavailable calorie balance without nutrition, calories, or complete energy data
- monthly `data_through`
- zero-reporting-day behavior
- preservation of analyzer-calculated monthly TDEE with contributing-day coverage
- body-weight change
- incomplete body-weight change data
- preservation of analyzer-calculated monthly calorie balance with contributing-day coverage
- sleep efficiency
- sleep reporting dates before noon and from noon onward
- monthly Sleep Score composition
- preservation of the analyzer-calculated daily `total_score` value
- monthly total calorie balance derived from its own average/coverage pair
- safe zero-duration sleep efficiency

Simple dataclass field storage remains intentionally under-tested; the suite focuses on derived behavior, incomplete-data boundaries, and business-relevant properties.

## TextRenderer

`tests/renderers/test_text_renderer.py` contains **23 collected test cases** covering the renderer's public textual output contract.

The suite verifies:

- presence of all major sections in the monthly summary
- inclusion of daily reports in a full monthly report
- omission of the monthly body-weight section when no measurements exist
- explicit messaging when daily nutrition data is missing
- explicit messaging when daily energy data is missing
- distinction between activity without workouts and complete absence of activity
- rendering of the disabled monthly Sleep Score bonus state
- use of the configured monthly bonus maximum in the displayed monthly Sleep Score maximum
- omission of monthly sleep sections when sleep data is unavailable
- omission of the monthly workouts section when no workouts exist
- omission of monthly nutrition when nutrition data is unavailable
- omission of monthly energy expenditure when energy data is unavailable
- omission of monthly general activity when step and distance data are unavailable
- rendering of the effective injected Sleep configuration in monthly summaries
- independent rendering of partially available energy averages
- independent rendering of partially available nutrition averages
- rendering monthly calorie balance from its stored value and its own coverage
- partial daily energy and nutrition without fabricated zero values
- conditional `based on X day(s)` coverage labels only when contributing days are fewer than reporting days
- singular `day` wording for one-day coverage
- independent general-activity coverage rendering
- omission of workout energy when the aggregate is incomplete

The renderer tests intentionally avoid testing private writer helpers individually. They verify user-visible behavior through the public `render_month()` and `render_month_summary()` methods.

### Partial monthly reports

Monthly reports are designed to remain renderable when individual data categories or individual metrics are unavailable. The report header is always produced, while optional sections are rendered only when their underlying data exists.

The regression suite explicitly protects partial-report behavior for:

- missing sleep data
- missing workouts
- missing activity metrics
- missing nutrition data
- missing energy expenditure data
- missing general activity data
- missing body-weight measurements
- mixed energy coverage where basal, active, and TDEE do not share the same contributing days
- mixed nutrition coverage where individual nutrients are independently available

Missing values are never rendered as measured zero values. When a monthly metric uses fewer than all reporting days, text output shows its contributing-day coverage; full coverage intentionally omits the redundant suffix.

## JsonRenderer

`tests/renderers/test_json_renderer.py` contains **32 collected test cases** covering the versioned JSON report contract for both monthly summaries and detailed daily reports.

The monthly contract tests verify:

- stable top-level schema keys and `schema_version`
- report metadata and ISO-compatible `data_through`
- general activity representation
- sleep summary, sleep stages and monthly Sleep Score data
- configured maximum monthly Sleep Score
- base 100-point monthly Sleep Score maximum when the monthly bonus system is disabled
- stable workout identifiers derived from enum names
- explicit workout averaging basis (`daily` or `workout`)
- body-weight statistics
- energy expenditure values with independent `*_count_days` coverage fields
- nutrition values with independent `*_count_days` coverage fields
- calorie balance as a separate top-level API concept with average, total, and its own coverage
- independent general-activity coverage fields for steps, distance, and step length
- preservation of missing workout energy in monthly output
- normalized two-decimal numeric precision
- rejection of non-finite numbers through `allow_nan=False`
- `null` for unavailable optional sections
- `[]` for empty workout collections
- stable section shape when only some energy or nutrition metrics are available
- reports with zero completed reporting days
- injected configuration for the maximum monthly Sleep Score
- exposure of the effective injected Sleep configuration, including API-friendly threshold objects

The daily contract tests verify:

- inclusion of detailed `days` in full monthly JSON output
- daily general activity
- daily workout details without monthly averaging fields
- daily body weight
- partial and complete daily energy expenditure
- TDEE remaining `null` when daily energy is incomplete
- partial and complete daily nutrition
- calorie balance kept as a separate concept and remaining `null` without all required daily inputs
- empty `NutritionData` represented as `null`
- full ISO sleep timestamps with timezone offsets
- daily sleep-stage details
- daily Sleep Score components and total
- preservation of `null` and empty collections in partial daily reports

The JSON tests deserialize renderer output with `json.loads()` and validate the resulting data structure rather than whitespace or indentation. Internal `(average, contributing_days)` tuples are deliberately flattened into stable value/count fields instead of leaking as JSON arrays.

## AppleHealthImporter

`tests/test_importer.py` contains **11 collected test cases** using temporary ZIP archives.

The suite verifies:

- missing archive handling
- successful opening of an archive containing exactly one valid export XML
- ignoring non-XML files
- ignoring CDA XML documents
- rejection of archives containing no valid export XML
- rejection of archives containing more than one valid export XML
- typed rejection of invalid ZIP archives, missing export XML, and multiple export XML files
- acceptance of a localized main export XML filename in the Apple Health export directory
- rejection of an export XML whose declared uncompressed size exceeds the safety limit

Temporary files are created with pytest's `tmp_path` fixture, allowing the importer to be tested against real ZIP archives without storing generated archives in the repository.

`AppleHealthImporter` owns the lifecycle of both the ZIP archive and the streamed XML entry through its context-managed `open_export()` interface, preventing callers from managing archive resources directly. The importer opens the selected entry rather than extracting it to an arbitrary filesystem path.

## Packaging

`tests/test_packaging.py` contains **1 test case** protecting the explicit package-data configuration required by the web runtime. It verifies that the built package is configured to include the browser HTML/SVG assets and the TOML configuration examples, including the canonical `config.example.toml` served by the API.

The final PRE5.6 verification additionally builds and installs the wheel outside the source tree to sanity-check that `/`, `/favicon.svg`, `/config.example.toml`, and `/health` remain available from the installed package.

## Integration tests

`tests/integration/test_full_report_pipeline.py` contains **11 end-to-end integration tests**.

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

The end-to-end integration suite exercises both the text- and JSON-rendering pipelines. It also protects the multi-month invariant that one archive is parsed once and then reused to generate independent monthly outputs. `JsonRenderer` is additionally covered by dedicated contract tests at the renderer layer.

The integration suite verifies:

- successful execution of the complete report-generation pipeline
- propagation of one shared `AppConfig` through parser, analyzer, and renderer layers
- preservation of expected values across importing, parsing, analysis, and aggregation
- generation of a monthly-summary-only text report without daily sections
- exact deterministic text output through a golden-report comparison, including incomplete-data and coverage semantics
- generation of a valid full JSON report containing monthly summary data and detailed daily reports
- generation of a valid JSON monthly summary without the `days` collection
- loading the committed example TOML configuration
- observable report changes produced by runtime TOML overrides
- preservation of default pipeline behavior when no configuration file is supplied
- presence of effective Sleep configuration in monthly text and JSON report output
- multi-month generation from one archive with month-isolated output and one shared parse

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
- accidental reintroduction of missing-as-zero behavior or incorrect coverage text

When a report-format change is intentional, the generated diff should be reviewed before updating the golden fixture.

## Running the tests

Install the project with the development dependencies from `pyproject.toml`:

```bash
python -m pip install -e ".[dev]"
```

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

Measure statement coverage for the application package:

```bash
pytest --cov=apple_health --cov-report=term-missing
```

The final PRE5.6 suite collects **386 tests** and currently reports **97% statement coverage** for `apple_health`.

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
- exercise the API boundary with synthetic archives rather than private health exports
- verify temporary-file cleanup and stable error behavior at the HTTP boundary
- protect the parse-once multi-month generation contract with application and integration tests
- avoid tests that merely confirm that dataclass fields store assigned values

This keeps the test suite useful during future refactoring while still providing strong regression protection for the application's core behavior.
