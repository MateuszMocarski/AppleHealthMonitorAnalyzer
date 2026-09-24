# Health Data Providers

This directory owns **provider-specific ingestion** for Connected Health Analyzer.

A health-data provider understands one external export format and normalizes it into the
shared canonical `HealthData` model. Everything below that boundary must remain
provider-neutral.

```text
provider export
    ↓
provider-owned import / parse / normalize
    ↓
HealthDataProvider
    ↓
LoadedHealthData
    ├── HealthData
    └── DatasetProvenance / diagnostics
    ↓
ReportGenerationApplication
    ↓
HealthAnalyzer
    ↓
MonthlySummary
    ↓
shared renderers
```

> **Hard rule:** provider-specific code stops at the `HealthData` boundary.

Apple Health is the first implemented provider. A new provider should follow the same
architectural boundary without mechanically copying every Apple module or filename.

## Step-by-step: adding a provider

### 1. Create a provider-owned package

Create a package under:

```text
connected_health/providers/<provider>/
```

For example:

```text
connected_health/providers/garmin/
```

Keep code here when it exists only because of that provider's export format or semantics.

Typical provider-owned responsibilities include:

- archive/file validation,
- raw export parsing,
- raw provider identifiers and mappings,
- provider-specific activity/sleep/source interpretation,
- normalization into canonical domain values,
- provider-specific configuration,
- provider-specific processing errors,
- provider load diagnostics.

Do **not** move provider-specific details into shared analyzers merely because more than
one module needs them.

### 2. Define the provider boundary

Implement the existing `HealthDataProvider` contract.

The provider load operation must produce `LoadedHealthData`, containing:

- canonical `HealthData`,
- adjacent `DatasetProvenance` / load diagnostics.

Conceptually:

```text
load(provider_input, provider_config)
    -> LoadedHealthData(
         data=HealthData(...),
         provenance=DatasetProvenance(...),
       )
```

Provenance and diagnostics may describe where the dataset came from, but they must not
change report calculations.

### 3. Parse raw data only inside the provider

Raw provider structures must not cross into the shared processing pipeline.

Examples of provider-only data:

- vendor record/type identifiers,
- raw activity codes,
- source/device names,
- export-specific metadata,
- vendor-specific sleep-stage names,
- parser-only intermediate objects.

Translate them before returning `HealthData`.

Bad:

```text
HealthAnalyzer
    -> if provider == "garmin": ...
```

Good:

```text
Garmin raw value
    -> Garmin normalization
    -> canonical WorkoutType / SleepStage / domain value
    -> HealthAnalyzer
```

### 4. Normalize into canonical `HealthData`

Map the provider export into the existing canonical domain model.

Preserve current domain semantics:

- missing data stays missing,
- measured zero stays zero,
- numeric values must be finite,
- timestamps/dates must be valid,
- workout and sleep semantics must use canonical enums/types,
- incomplete source measurements must not become fabricated totals.

Do not add a new shared-domain field merely because the provider exposes extra metadata.
Add shared data only when it has provider-independent product meaning.

### 5. Keep configuration ownership separated

Shared analysis configuration belongs in `AnalysisConfig`.

Settings required only to interpret one provider belong to that provider's configuration.

For Apple, the current compatibility surface remains wrapped by `AppConfig` and includes
Apple-specific source settings. A new provider does not need to imitate those fields.

Avoid:

```text
AnalysisConfig.garmin_specific_toggle
```

Prefer:

```text
GarminProviderConfig(...)
```

when the setting is required only during Garmin ingestion/normalization.

### 6. Reuse the neutral application pipeline

A working provider should be able to feed the existing neutral workflow:

```text
HealthDataProvider
    -> ReportGenerationApplication
    -> HealthAnalyzer
    -> existing report models
    -> existing renderers
```

Do not create provider-specific copies of:

- `HealthAnalyzer`,
- report models,
- `TextRenderer`,
- `JsonRenderer`,
- `MonthlySummary`,
- generic report-generation orchestration.

If a new provider appears to require such a branch, first check whether the problem is
really an ingestion/normalization issue.

### 7. Add backend/provider dispatch only when the provider is real

The browser already has an explicit provider-selection boundary, but the current backend
generation contract is intentionally still Apple-specific.

Do not add placeholder dispatch for hypothetical providers.

When the second provider is actually usable:

1. connect the provider selector to the backend request,
2. select the correct provider implementation at the application/API boundary,
3. keep provider choice out of shared analyzers/renderers,
4. preserve the existing Apple request contract where compatibility requires it.

The exact public API shape should be introduced with the real second-provider workflow,
not earlier.

### 8. Add provider-aware persistence only when needed

Current Google Drive report identity is still legacy Apple-oriented.

The decided future identity is:

```text
ReportIdentity = (provider_id, period)
```

Implement it only when more than one provider can persist reports.

Compatibility rule:

- existing persisted reports without provider metadata are interpreted as legacy Apple
  at read time,
- do not automatically rewrite old Drive data merely to add provider identity.

Google Drive itself is **not** a health-data provider. It remains identity/storage
infrastructure.

### 9. Add tests at the provider boundary

A new provider should have focused tests proving at least:

- valid provider input loads successfully,
- malformed/unsupported input fails through controlled provider errors,
- provider-specific identifiers do not leak into canonical `HealthData`,
- raw values normalize into the expected canonical types,
- missing-data semantics are preserved,
- `LoadedHealthData` contains truthful provenance/diagnostics,
- the provider can run through `ReportGenerationApplication`,
- existing shared analyzers/renderers need no provider-specific branch,
- the Apple regression suite still passes.

Add architecture guards when a regression could otherwise allow provider code to leak
into shared layers.

### 10. Run the normal repository gate

Before considering the provider integration complete, run the normal project checks:

```bash
pytest -q
black --check .
ruff check .
git diff --check
python -m pip check
python -m build
```

Also perform an installed-package/runtime sanity check when packaging or public wiring
changes.

## Definition of done

A provider is architecturally complete when this path works:

```text
real provider export
    ↓
provider-owned parsing / normalization
    ↓
canonical HealthData
    ↓
ReportGenerationApplication
    ↓
existing HealthAnalyzer
    ↓
existing report models / renderers
```

and no provider-specific logic is required below the `HealthData` boundary.

For a provider that is exposed through the web application, completion additionally
requires the real provider-selection/backend-dispatch path and relevant browser/API
integration tests.

## Current providers

### Apple Health

Apple Health is the current production provider and the reference implementation for the
provider boundary.

Apple-specific responsibilities stay under Apple ownership, including ZIP/XML handling,
raw `HK*` mappings, Apple source-selection policy, Apple provider configuration, and
Apple-specific processing errors.

The following Apple-facing compatibility surfaces are intentionally stable and should not
be renamed while adding another provider:

- `provider_id = "apple_health"`
- `AppleHealthApplication`
- `apple_watch_source`
- `apple_health_app_source`
- TOML `[source]`
- exact text title `Apple Health Monthly Report`
- JSON schema `1.0`
- existing Drive `ahm_*` metadata

### Future providers

Garmin is the first planned additional provider.

Its intended boundary is:

```text
Garmin export
    -> Garmin importer / parser / normalizer
    -> canonical HealthData
    -> existing shared analysis and reporting
```

The architecture does not require every provider package to use identical filenames.
Match the provider's actual complexity while preserving the ownership and boundary rules
above.
