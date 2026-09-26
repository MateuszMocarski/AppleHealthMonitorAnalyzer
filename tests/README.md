# Test Suite

The Connected Health Analyzer suite uses synthetic health data and temporary files; it
does not require personal Apple Health exports or a live Google account. The repository
does not pin a test count or coverage percentage in documentation because both evolve.
Run it with the project baseline of Python 3.14 or later.

## Test organization

| Area | Location | What it protects |
| --- | --- | --- |
| Analysis | `tests/analyzers/` | Activity, energy, nutrition, body weight, sleep-session reconstruction, Sleep Score, coverage, and missing-data behavior |
| Apple ingestion | `tests/test_importer.py`, `tests/test_parser.py`, `tests/providers/` | ZIP/XML safety, Apple identifiers/source policy, parsing, normalization, and the provider boundary |
| Application and CLI | `tests/application/`, `tests/test_cli.py` | Period parsing, run profiles, parse-once multi-month generation, output selection, and CLI precedence |
| Configuration | `tests/config/` | TOML loading, defaults, validation, examples, and runtime source-override precedence |
| Rendering/contracts | `tests/renderers/`, `tests/test_report_models.py` | Text/JSON output, schema `1.0`, coverage fields, finite numbers, and missing-versus-zero semantics |
| Google Drive | `tests/google/` | OAuth/session state, Drive structure, configuration profiles, current generations, report persistence, archives, and replacement conflicts |
| Viewer | `tests/viewer/` | Strict persisted JSON parsing, active-artifact discovery, bounded loading, HTML/SVG rendering, charts, daily navigation markup, and missing-data presentation |
| FastAPI/browser | `tests/api/test_app.py` | HTTP error mapping, temporary-file cleanup, Google recovery, Generate/Viewer frontend state, Viewer request races, and static presentation contracts |
| Integration/package | `tests/integration/`, `tests/test_packaging.py` | Full report pipeline, deterministic golden text output, connected/local workflow matrix, and installed package assets |

## Important behavior covered

The suite specifically protects the current product boundaries:

- Apple Health is the implemented provider; provider-specific parsing ends at canonical
  `HealthData`.
- Missing measurements are not converted to zero. Monthly averages retain independent
  contributing-day coverage, and calorie balance uses complete daily input
  intersections.
- JSON renderer output is schema `1.0`, finite, and distinct from internal report
  dataclasses.
- Persisted Viewer JSON is untrusted: malformed JSON, duplicate object keys, non-finite
  constants, invalid shapes, and incompatible schema/version data are rejected.
- Viewer discovery considers only active current-generation `full.json` and
  `summary.json` artifacts; archive, staging, orphan, and arbitrary Drive files are not
  normal Viewer sources.
- Viewer body loads are bounded, revalidated against managed metadata, and rendered from
  typed Viewer models. The browser only mounts trusted server-rendered HTML/SVG and uses
  JavaScript for presentation/navigation rather than health calculations.
- Google report replacement stages a new generation before moving the previous current
  generation into archive history. Normal Viewer selection excludes that history.
- Local uploads, Drive downloads, configuration files, and Viewer report loads use
  bounded temporary storage and controlled error paths.

## Running tests

Install the development dependencies:

```bash
python -m pip install -e ".[dev]"
```

Run the complete suite:

```bash
python -m pytest -q
```

Useful focused runs:

```bash
python -m pytest -q tests/viewer/
python -m pytest -q tests/google/ tests/api/test_app.py
python -m pytest -q tests/config/
python -m pytest --collect-only -q
```

Run the standard repository gate:

```bash
python -m pytest -q
python -m black --check .
python -m ruff check .
git diff --check
python -m pip check
python -m build
```

Optional local coverage remains available through pytest-cov:

```bash
python -m pytest --cov=connected_health --cov-report=term-missing
```

## Test design principles

- Test public behavior and meaningful boundaries rather than private implementation
  details where practical.
- Use synthetic exports and Drive fakes instead of live accounts or private data.
- Keep configuration-relative expectations explicit; do not hardcode values that a
  supported configuration can change.
- Exercise both focused contracts and integration wiring.
- Parse JSON in contract tests rather than asserting whitespace.
- Preserve deterministic text output with the golden fixture only after reviewing an
  intentional report-format change.
