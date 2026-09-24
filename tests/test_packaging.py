import re
import tomllib
from pathlib import Path

# =====================================================================
# Verifies that runtime web assets and configuration examples are
# explicitly included in the built Python package.
# =====================================================================


def test_runtime_package_data_is_configured() -> None:
    pyproject_path = Path("pyproject.toml")

    with pyproject_path.open("rb") as file:
        pyproject = tomllib.load(file)

    package_data = pyproject["tool"]["setuptools"]["package-data"]

    assert package_data["connected_health.api"] == [
        "web/*.html",
        "web/*.svg",
    ]
    assert package_data["connected_health.config"] == [
        "examples/*.toml",
    ]


def test_frontend_provider_selection_requires_explicit_apple_choice() -> None:
    index = Path("connected_health/api/web/index.html").read_text(encoding="utf-8")

    assert "<title>Connected Health Analyzer</title>" in index
    assert "Connected Health Analyzer" in index
    assert 'id="apple-provider-button"' in index
    assert 'aria-pressed="false"' in index
    assert 'id="generation-workflow"' in index
    assert 'data-provider-workflow="apple"' in index
    assert re.search(
        r'id="generation-workflow"[\s\S]*?hidden',
        index,
    )
    assert "let selectedProvider = null;" in index
    assert 'selectedProvider = "apple";' in index
    assert "Provider: ${" in index


def test_frontend_keeps_apple_contract_inside_selected_workflow() -> None:
    index = Path("connected_health/api/web/index.html").read_text(encoding="utf-8")

    assert "Apple Health export" in index
    assert "Apple Watch source" in index
    assert "Apple Health app source" in index
    assert 'name="apple_watch_source"' in index
    assert 'name="apple_health_app_source"' in index
    assert "Garmin" not in index

    form_data_function = re.search(
        (
            r"function buildGenerationFormData\([\s\S]*?\n        }\n\n"
            r"        async function readResponseError"
        ),
        index,
    )

    assert form_data_function is not None
    assert 'formData.append(\n                "provider"' not in form_data_function.group()
    assert 'formData.append(\n                "provider_id"' not in form_data_function.group()
    assert 'formData.append(\n                "health_provider"' not in form_data_function.group()


def test_source_tree_has_no_legacy_root_package_imports() -> None:
    python_sources = Path("connected_health").rglob("*.py")

    assert not any(
        "apple_health." in source.read_text(encoding="utf-8") for source in python_sources
    )
