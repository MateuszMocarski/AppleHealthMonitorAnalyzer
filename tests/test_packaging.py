import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


# =====================================================================
# Verifies that runtime web assets and configuration examples are
# explicitly included in the built Python package.
# =====================================================================


def test_runtime_package_data_is_configured() -> None:
    pyproject_path = Path("pyproject.toml")

    with pyproject_path.open("rb") as file:
        pyproject = tomllib.load(file)

    package_data = pyproject["tool"]["setuptools"]["package-data"]

    assert package_data["apple_health.api"] == [
        "web/*.html",
        "web/*.svg",
    ]
    assert package_data["apple_health.config"] == [
        "examples/*.toml",
    ]
