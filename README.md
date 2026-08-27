# Apple Health Monitor Analyzer

### Highlights

- 📅 Daily and monthly reports
- 😴 Automatic sleep session reconstruction
- 🚶 Activity and workout aggregation
- 📊 Deterministic and comparable reports
- 🤖 AI-friendly text and JSON report formats

## Overview

Apple Health Monitor Analyzer is a Python application that transforms raw Apple Health exports into structured daily and monthly reports.

The application parses Apple Health XML exports, reconstructs sleep sessions, aggregates daily activity, energy, body weight, and nutrition metrics, and generates comprehensive reports designed for long-term health and fitness tracking.

Unlike the Apple Health application, which focuses on browsing recorded data, Apple Health Monitor Analyzer emphasizes consistency, transparency, and comparability. Every reported metric follows a documented methodology, allowing reports to be reliably compared across different reporting periods and parser versions.

The generated reports are intended to serve as a solid foundation for both personal analysis and AI-assisted interpretation, providing meaningful insights without requiring direct access to raw Apple Health data.

## Project Philosophy

Apple Health already provides an excellent interface for viewing health data.
This project is not intended to replace it.

Instead, its purpose is to transform Apple Health exports into deterministic,
well-documented reports that remain comparable over time.

Every design decision follows a simple principle:

> The same input data should always produce the same report.

This philosophy makes the reports suitable for long-term trend analysis,
independent verification, and AI-assisted interpretation.

## Features

### Data Processing

- Import Apple Health XML exports
- Parse and normalize health records
- Deterministic report generation
- Versioned report schema

### Activity Analysis

- Daily activity summaries
- Monthly activity summaries
- Steps, distance, active energy and exercise time
- Workout aggregation by activity type
- Daily and monthly workout statistics
- Daily energy expenditure analysis (Basal Energy, Active Energy, TDEE)

### Body Weight Analysis

- Daily body weight tracking
- Monthly average, start, end, minimum and maximum weight
- Monthly body weight change
- Measurement coverage across the reporting period

### Nutrition Analysis

- Daily nutrition summaries
- Monthly nutrition summaries
- Energy intake
- Protein, carbohydrates and fat tracking
- Daily averages based on completed reporting days
- Daily and monthly calorie balance based on energy intake and TDEE

### Sleep Analysis

- Automatic sleep session reconstruction
- Sleep stage aggregation
- Sleep duration and efficiency
- Average bedtime and wake-up time
- Configurable daily sleep scoring
- Monthly sleep score averages and component breakdown
- Optional configurable monthly sleep score bonuses
- Monthly sleep statistics

### Reporting

- Human-readable text reports
- Structured JSON reports with a versioned schema
- Daily and monthly summaries
- AI-friendly report formats
- Effective Sleep configuration included in monthly text and JSON reports
- Partial monthly reports that preserve available data when individual sections are missing
- Documented calculation methodology

### Design

- Deterministic output
- Transparent calculations
- Comparable reports across time
- Extensible architecture

## Usage

Run the application from the command line using the `import` command followed by the path to the Apple Health export archive.

### Basic Usage

```bash
python app.py import export.zip
```

Analyzes the current month of the current year.

### Analyze a Specific Month

```bash
python app.py import export.zip --month 7
```

Analyzes the specified month of the current year.

### Analyze a Specific Year and Month

```bash
python app.py import export.zip --year 2025 --month 12
```

Both `--year` and `--month` can be used together to analyze a specific month from a different year.

### Show Only Monthly Summary

```bash
python app.py import export.zip --month 7 --month-summary
```

Displays only the aggregated monthly statistics without the detailed daily report.


### JSON Output

Use `--format json` to generate a structured JSON report instead of the default text output.

```bash
python app.py import export.zip --month 8 --format json
```

JSON output uses a versioned schema intended for machine consumption, API integration, and future frontend clients. Numeric values remain JSON numbers, dates and timestamps use ISO-compatible representations, and unavailable report sections are represented explicitly with `null` while empty collections remain `[]`.

Combine JSON output with `--month-summary` to return only monthly aggregates without daily entries:

```bash
python app.py import export.zip --month 8 --month-summary --format json
```

Text output remains the default when `--format` is omitted.

### Run Profiles

Application execution can be described by an optional TOML run profile. A profile may define the archive path, reporting period, output mode, monthly-summary mode, and the path to the application configuration file.

```bash
python app.py --profile apple_health/application/examples/run.example.toml
```

Run profiles may be partial. Final run options are resolved using the following precedence:

```text
CLI flags
    ↓
run.toml
    ↓
built-in defaults
```

This allows a reusable profile to provide normal execution settings while individual CLI flags override them for a single run. For example:

```bash
python app.py --profile apple_health/application/examples/run.month-summary.toml --enforce-daily --format text
```

`--month-summary` explicitly enables summary-only output, while `--enforce-daily` explicitly disables it and requests daily report details.

Example run profiles are available in `apple_health/application/examples/`.

### Runtime Configuration

Use `--config` to load an optional TOML application configuration file:

```bash
python app.py import export.zip --month 8 --config apple_health/config/examples/config.example.toml
```

When `--config` is omitted, the application uses the defaults defined by the configuration dataclasses.

TOML files may be partial: only explicitly provided values override defaults. Configuration keys are case-insensitive, unknown fields fail fast, and invalid values stop the application with a configuration error.

Example application configuration files are available in [`apple_health/config/examples/`](apple_health/config/examples/). For the complete configuration reference, see [`apple_health/config/README.md`](apple_health/config/README.md).

### Command Line Arguments

| Argument | Description |
|----------|-------------|
| `import` | Imports and analyzes an Apple Health export archive. |
| `file` | Path to the exported Apple Health ZIP archive. |
| `--profile` | Path to an optional TOML run profile. |
| `--month` | Month to analyze (`1`–`12`). Overrides the profile value when supplied. |
| `--year` | Year to analyze. Overrides the profile value when supplied. |
| `--month-summary` | Explicitly enables monthly-summary-only output. |
| `--enforce-daily` | Explicitly requests daily report details, overriding `month_summary = true` from a profile. |
| `--format` | Output format: `text` or `json`. Overrides the profile value when supplied. |
| `--config` | Path to an optional TOML application configuration file. Overrides the profile value when supplied. |

The application processes the archive and generates either a structured human-readable text report or a versioned JSON representation containing monthly summaries, activity, energy, body weight, nutrition and sleep statistics.

## Project Architecture

The application follows a layered architecture that separates application execution, data import, parsing, analysis, and presentation. Each component has a single responsibility, making the codebase easier to maintain, test, and extend.

```mermaid
flowchart TD

    ENTRY["⌨️ app.py<br/><i>CLI Entry Point</i>"]
    CLI["apple_health.cli<br/><i>CLI Adapter</i>"]
    PROFILE["📋 Run Profile<br/><i>Optional TOML</i>"]
    APP["AppleHealthApplication<br/><i>Application Orchestrator</i>"]
    A["📦 Apple Health Export<br/><b>export.zip</b>"]
    CFG["⚙️ AppConfig<br/><i>Application Configuration</i>"]

    B["AppleHealthImporter"]
    C["AppleHealthParser"]
    D["AppleHealthData<br/><i>Domain Model Root</i>"]

    E["HealthAnalyzer<br/><i>Orchestrator</i>"]
    EA["ActivityAnalyzer"]
    EM["MetricsAnalyzer"]
    ES["SleepAnalyzer"]

    F["Health Report<br/><i>Monthly • Daily • Statistics</i>"]
    G["TextRenderer"]
    GJ["JsonRenderer"]
    H["📄 Text Report"]
    HJ["🧩 JSON Report"]

    ENTRY --> CLI
    PROFILE -.->|"Load optional settings"| CLI
    CLI -->|"Resolve RunOptions"| APP
    APP -->|"Select archive and configuration"| A
    APP -.->|"Load configuration"| CFG
    A -->|"Load archive"| B
    B -->|"Extract XML"| C
    C -->|"Parse records"| D
    D -->|"Analyze health data"| E

    CFG -.->|"Configure"| C
    CFG -.->|"Configure"| E
    CFG -.->|"Configure"| G
    CFG -.->|"Configure"| GJ

    E --> EA
    E --> EM
    E --> ES

    EA -->|"Activity summaries"| E
    EM -->|"Daily and monthly metrics"| E
    ES -->|"Sleep sessions and scores"| E

    E -->|"Build report model"| F
    F -->|"Render to text"| G
    F -->|"Render to JSON"| GJ
    G --> H
    GJ --> HJ

    classDef import fill:#D6EAF8,stroke:#2E86C1,color:#000,stroke-width:2px;
    classDef config fill:#FDEBD0,stroke:#CA6F1E,color:#000,stroke-width:2px;
    classDef domain fill:#D5F5E3,stroke:#239B56,color:#000,stroke-width:2px;
    classDef analysis fill:#FCF3CF,stroke:#B7950B,color:#000,stroke-width:2px;
    classDef presentation fill:#E8DAEF,stroke:#8E44AD,color:#000,stroke-width:2px;
    classDef output fill:#FADBD8,stroke:#CB4335,color:#000,stroke-width:2px;

    class A,B,C import;
    class CFG config;
    class D domain;
    class E,EA,EM,ES,F analysis;
    class G,GJ presentation;
    class H,HJ output;
```

The diagram is organized into five logical layers, each with a clearly defined responsibility.

| Layer | Responsibility |
|-------|----------------|
| 🔵 **Import** | Load and parse Apple Health export |
| 🟢 **Domain** | In-memory representation of imported health data |
| 🟡 **Analysis** | Calculate statistics and build report models |
| 🟣 **Presentation** | Render report models into text or JSON representations |
| 🔴 **Output** | Final human-readable or machine-readable report |

Application execution is coordinated by `AppleHealthApplication`, which receives resolved `RunOptions` independently of the CLI. This keeps the processing pipeline reusable by future entry points such as an API. Run profiles and CLI values are resolved before execution.

Configuration is treated as a cross-cutting application concern rather than a separate processing layer. A single `AppConfig` instance is created for each application run and injected into components that require configurable behavior.

#### CLI

The `apple_health.cli` module owns command-line argument parsing and validation. It combines explicit CLI input with optional run-profile values and delegates final option resolution to `RunOptionsResolver`.

The top-level `app.py` module acts only as the CLI entry point and delegates execution to this adapter. Report-processing logic remains isolated in `AppleHealthApplication`, allowing future entry points such as an API to reuse the same application workflow without depending on command-line parsing.

#### AppConfig

Acts as the root of the application's configuration model. It groups configuration by responsibility and is created once for each application run before being injected into configurable components.

Detailed configuration structure, TOML loading behavior, defaults, validation rules, and examples are documented in [`apple_health/config/README.md`](apple_health/config/README.md).

#### AppleHealthImporter

Responsible for loading the Apple Health export archive and extracting the XML data required for further processing.
The importer is intentionally isolated from the parsing logic, allowing the parser to operate independently of the data source.

#### AppleHealthParser

Parses Apple Health XML records and converts them into strongly typed domain objects.
The parser performs data transformation only and does not calculate statistics or generate reports.

#### AppleHealthData (Domain Model Root)

Acts as the central in-memory representation of imported health data.
All subsequent analysis operates exclusively on this domain model, making it the single source of truth for the application.

#### HealthAnalyzer

Acts as the analysis-layer orchestrator.
It coordinates specialized analyzers and combines their results into daily and monthly report models.

#### ActivityAnalyzer

Processes workout data and builds daily and monthly activity summaries, including workout duration, active energy expenditure and distance.

#### MetricsAnalyzer

Processes aggregated daily metrics and calculates daily and monthly statistics for steps, walking/running distance, energy expenditure, body weight and nutrition.

#### SleepAnalyzer

Reconstructs sleep sessions from Apple Health sleep records, selects the primary sleep session for each reporting day, calculates sleep statistics and applies the configurable Sleep Score model.

#### Health Report

Represents the complete report independently of its presentation.
Separating report generation from rendering makes it easy to support additional output formats (e.g. HTML, Markdown or PDF) without modifying the analysis layer.

#### TextRenderer

Transforms the report model into a human-readable text representation.
The renderer contains no business logic and returns the rendered report as a string, leaving the application layer responsible for deciding where that output is sent.

#### JsonRenderer

Transforms the same report models into a structured, versioned JSON representation intended for machine consumption, future API endpoints, frontend clients, and AI-assisted workflows.

The JSON contract uses stable technical identifiers, explicit measurement units in field names, ISO-compatible date/time representations, `null` for unavailable optional sections, `[]` for empty collections, and normalized numeric precision. Monthly and daily report data share the same high-level section structure wherever practical.

Both renderers are isolated in the `renderers` package, allowing presentation formats to evolve independently from import, parsing, and analysis logic.

### Architectural Principles

- Single Responsibility Principle for every major component.
- Clear separation between parsing, specialized analysis, report construction, rendering, and output.
- Domain-driven workflow based on an in-memory domain model.
- Deterministic report generation — the same input always produces the same output.
- Report models are presentation-agnostic, allowing multiple output formats to reuse the same analysis results.
- Specialized analyzers separate activity, daily metrics and sleep responsibilities behind a single `HealthAnalyzer` orchestration layer.
- Renderers produce representations of report models without controlling the final output destination.
- Configurable components receive application settings through dependency injection rather than depending on module-level configuration globals.

## Configuration

Application behavior is represented by a hierarchy of strongly typed Python dataclasses rooted in `AppConfig`.

The configuration model separates settings by responsibility, including source selection, sleep-session reconstruction, and Sleep Score behavior. A single `AppConfig` instance is created for each application run and passed through the processing pipeline using dependency injection.

```text
AppConfig
├── AppleHealthParser
├── HealthAnalyzer
│   └── SleepAnalyzer
├── TextRenderer
└── JsonRenderer
```

Components retain default configuration behavior when instantiated independently, while the application can supply one shared configuration instance for a complete processing run.

Configuration values come from defaults defined by the configuration dataclasses and may be overridden at runtime by an optional TOML file loaded through `ConfigLoader`. Missing values continue to use dataclass defaults.

For the complete configuration hierarchy, default values, validation rules, and configuration architecture, see [`apple_health/config/README.md`](apple_health/config/README.md).

## Domain Model

The domain model represents the in-memory structure of Apple Health data after it has been parsed from the XML export.
It serves as the single source of truth for all analyses and report generation.

```mermaid
classDiagram

class AppleHealthData {
    +workouts
    +dailyMetrics
    +sleepRecords
}

class Workout {
    +activityType
    +start
    +end
    +duration
    +distance
    +activeEnergy
}

class DailyMetrics {
    +date
    +steps
    +distance
    +activeEnergy
    +basalEnergy
    +weight
    +nutrition
}

class WeightMeasurement {
    +value
    +timestamp
    +isUserEntered
}

class NutritionData {
    +caloriesKcal
    +proteinG
    +carbohydratesG
    +fatG
}

class SleepRecord {
    +start
    +end
    +stage
    +sourceName
}

AppleHealthData "1" o-- "*" Workout
AppleHealthData "1" o-- "*" DailyMetrics
AppleHealthData "1" o-- "*" SleepRecord

DailyMetrics "1" o-- "0..1" WeightMeasurement
DailyMetrics "1" o-- "0..1" NutritionData
```
#### AppleHealthData

Acts as the root of the application's domain model.
It aggregates all imported health data and serves as the single source of truth for every analysis performed by the application.

#### Workout

Represents a single workout session imported from Apple Health.
It contains the workout type, start and end time, duration, active energy expenditure and, where available, distance.

#### DailyMetrics

Represents aggregated metrics for a single calendar day.
It stores step count, walking/running distance, active and basal energy expenditure, and optional body weight and nutrition data.
Body weight and nutrition are represented by dedicated domain objects because they contain additional information and require their own parsing and aggregation rules.

#### WeightMeasurement

Represents the body weight measurement selected for a given day.
It stores the measured value, timestamp and whether the measurement was manually entered by the user.
When multiple eligible body weight records exist for the same day, this information allows the parser to deterministically select the preferred measurement.

#### NutritionData

Represents aggregated nutrition data for a single calendar day.
It stores recorded energy intake together with protein, carbohydrate and fat consumption.
Nutrition data is aggregated from individual Apple Health dietary records before being exposed to the analysis layer.

#### SleepRecord

Represents a single sleep stage interval (e.g. Core, Deep, REM or Awake) recorded by Apple Health.

### Domain Model Principles

- XML-independent domain representation.
- Strongly typed domain objects.
- AppleHealthData acts as the single source of truth for parsed health data.
- Domain objects contain data rather than reporting or presentation logic.
- Related daily metrics are grouped into dedicated domain objects where appropriate.
- Business rules, aggregation and report generation are implemented by analyzers rather than domain entities.

## Report Format

The application can generate both a structured, human-readable text report and a versioned JSON representation summarizing activity, energy expenditure, calorie balance, body weight, nutrition, sleep, sleep scoring, and detailed daily health metrics.

The report is organized hierarchically, progressing from high-level monthly summaries to detailed daily breakdowns.

### Monthly Report Structure

```mermaid
flowchart TD

    A["Monthly Report"]
    B["General Activity"]
    C["Sleep Summary"]
    D["Activity Summary"]
    E["Nutrition"]
    F["Body Weight"]
    G["Energy Expenditure"]
    H["Calorie Balance"]
    I["Daily Reports"]

    CS["Sleep Score"]
    CC["Sleep Score Configuration"]

    A --> B
    A --> C
    C --> CS
    C --> CC
    A --> D
    A --> E
    A --> F
    A --> G
    A --> H
    A --> I
```

### Daily Report Structure

```mermaid
flowchart TD

    A["Daily Report"]
    B["Sleep"]
    C["Activities"]
    D["Body Weight"]
    E["Energy Expenditure"]
    F["Nutrition"]
    G["Calorie Balance"]

    BS["Sleep Score"]
    CW["Workout Details"]

    A --> B
    B --> BS
    A --> C
    C --> CW
    A --> D
    A --> E
    A --> F
    A --> G
```

### Reporting Areas

The report combines aggregated monthly statistics with detailed daily breakdowns.

Key reporting areas include:

- **General Activity** – steps, walking/running distance and average step length.
- **Workout Statistics** – recorded workout sessions, duration, energy and distance.
- **Energy Expenditure** – basal energy, active energy and TDEE.
- **Body Weight** – daily measurements and monthly weight statistics.
- **Nutrition** – daily and monthly energy intake and macronutrient summaries.
- **Sleep Summary** – sleep duration, stages, efficiency, bedtime and wake-up statistics.
- **Sleep Score** – configurable daily scoring based on bedtime, sleep duration and wake-up time, with monthly component averages and optional performance and consistency bonuses.
- **Sleep Configuration** – effective sleep-session and Sleep Score settings used to calculate the reported monthly results.
- **Daily Reports** – day-by-day sleep, activity, workout, energy, body weight and nutrition data.

### Design Goals

- Human-readable text output and machine-readable JSON output.
- Consistent formatting and stable JSON schema contracts.
- Monthly overview followed by progressively more detailed information.
- Aggregated metrics presented before individual workout sessions.
- Report generation remains independent of its presentation layer, allowing additional output formats to be added in the future.


### JSON Report Contract

JSON reports use `schema_version: "1.0"` and preserve a stable top-level structure for monthly report data:

- `report` – report metadata such as year, month, reporting days and data coverage
- `general_activity` – steps, distance and step length
- `sleep` – monthly or daily sleep details and Sleep Score data; monthly sleep output also exposes the effective sleep configuration used for scoring
- `workouts` – workout summaries using stable technical identifiers such as `indoor_cycling`
- `body_weight` – body-weight measurements and monthly statistics
- `energy_expenditure` – basal energy, active energy and TDEE
- `nutrition` – calorie intake and macronutrients
- `average_calories_balance_kcal` / `calories_balance_kcal` – calorie balance kept separate from nutrition because it depends on both energy intake and expenditure
- `days` – detailed daily reports when the full monthly report is requested

Unavailable optional sections are represented as `null`, while empty collections such as months or days without workouts are represented as `[]`. Numeric measurements remain JSON numbers and are normalized to two decimal places for a predictable external contract.

The JSON renderer deliberately exposes a presentation/API contract rather than directly serializing internal dataclasses. This allows the internal report models to evolve without automatically breaking external consumers.

## Report Interpretation

The report is intended to provide meaningful trends rather than medical or scientific conclusions. Several metrics require proper interpretation due to the way Apple Health records and aggregates data.

### Sleep

Sleep statistics are calculated from recorded sleep stages and may differ from values reported directly by Apple Health.

Short interruptions, missing stages or incomplete recordings may affect sleep duration and efficiency calculations.

### Sleep Score

The Daily Sleep Score evaluates adherence to configurable sleep targets using three components: bedtime, sleep duration and wake-up time.

Each component is scored on a 0–100 scale. The final daily score is calculated as a configurable weighted average of the three component scores.

Bedtime scoring rewards going to sleep at or before the configured target and applies penalties for later bedtimes.

Sleep duration scoring uses a configurable target and tolerance range, with separate penalty weights for oversleeping and undersleeping.

Wake-up scoring uses the Bedtime Score and Duration Score to determine the maximum available Wake-up Score before applying any penalty for waking later than the configured target. The relative influence of bedtime and sleep duration on this maximum score is configurable.

Penalties can be calculated using either step-based or linear progression. Step-based penalties are used by default.

Sleep stages such as Core, Deep and REM remain available for analysis but do not affect the Sleep Score.

Monthly sleep scoring reports the average Bedtime Score, Duration Score, Wake-up Score and Total Sleep Score across completed reporting days.

Monthly text and JSON reports also include the effective `AppConfig.sleep` configuration used for the run. This makes the reported scores self-describing and allows the same output to be interpreted correctly even when runtime TOML overrides were used.

An optional monthly bonus system can extend the monthly score from 0–100 to 0–120. The bonus system consists of two independently calculated components:

- **Average Bonus** – rewards reaching configurable monthly average Sleep Score thresholds.
- **Consistency Bonus** – rewards consistency based on the population standard deviation of Daily Sleep Scores.

Both bonus threshold sets are configurable. The maximum combined bonus is also configurable and validated against the configured threshold values.

When the monthly bonus system is disabled, the report continues to provide the standard monthly Sleep Score without applying any bonuses.

### Activities

Workout statistics are based solely on activities explicitly recorded in Apple Health.

Walking distance and step count are reported independently and should not be interpreted as direct indicators of workout intensity.

### Daily Metrics

Daily summaries aggregate all available records for a given calendar day.

If Apple Health contains incomplete or missing data, the report reflects the available information without attempting to estimate missing values.

### Nutrition

Nutrition values represent data recorded in Apple Health and are not inferred from other metrics.

For in-progress months, daily nutrition averages are calculated using completed reporting days only. The current day is excluded because its nutrition data may still be incomplete.

### Data Quality

The accuracy of every metric depends entirely on the quality of the exported Apple Health data.

The application does not modify, interpolate or infer missing values.

### General Notes

- The report is designed for long-term trend analysis rather than day-to-day fluctuations.
- Missing data is reported as missing whenever possible.
- For in-progress months, averages use completed reporting days only.
- All calculations are deterministic — identical input data and identical sleep scoring configuration always produce identical results.

## AI Analysis

The generated report is designed to be consumed not only by humans but also by Large Language Models (LLMs). Monthly reports include the effective sleep-scoring configuration alongside the calculated Sleep Score, allowing an AI consumer to interpret the result using the exact targets, weights, penalties, and bonus thresholds that produced it.

Prompt example:
```bash
Analyze the following Apple Health report. Focus on long-term trends rather than isolated daily values. Identify improvements, regressions, unusual patterns, consistency of physical activity, sleep quality, recovery and possible lifestyle observations. Base your conclusions only on the provided report and clearly distinguish facts from assumptions.
```

## Testing

The project includes a comprehensive automated test suite covering the
core application logic and the complete report-generation pipeline.

The test suite currently contains **237 test cases**, covering:

-   sleep analysis and scoring
-   activity and health metrics analysis
-   Apple Health XML parsing
-   configuration validation
-   report models
-   text rendering
-   JSON rendering and API contract behavior
-   ZIP import handling
-   command-line parsing and CLI validation
-   application execution and run-option resolution
-   TOML run-profile loading and precedence
-   end-to-end report generation

Run the complete test suite with:

``` bash
pytest
```

Code quality checks:

``` bash
ruff check .
black --check .
```

For a detailed breakdown of the test suite, see
[`tests/README.md`](tests/README.md).

## Future Development

The project currently fulfills its original purpose.

Future development may include additional health metrics when practical needs arise, additional presentation formats where justified, API and frontend integration, and further technical improvements focused on maintainability, code quality and architecture.

## License

MIT License

See LICENSE for details.