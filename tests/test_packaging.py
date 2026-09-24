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
