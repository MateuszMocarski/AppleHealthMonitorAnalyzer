import pytest

from health_analyzer.application.report_period import ReportPeriod

# =====================================================================
# Verifies that a report period can be created from the supported
# YYYY-MM representation.
# =====================================================================


def test_report_period_parses_valid_string() -> None:
    period = ReportPeriod.from_string(
        "2026-08",
    )

    assert period == ReportPeriod(
        year=2026,
        month=8,
    )


# =====================================================================
# Verifies that report period parsing rejects values that do not use
# the required YYYY-MM representation.
# =====================================================================


@pytest.mark.parametrize(
    "value",
    [
        "2026-8",
        "26-08",
        "2026/08",
        "2026-08-01",
        "invalid",
        "",
    ],
)
def test_report_period_rejects_invalid_format(
    value: str,
) -> None:
    with pytest.raises(
        ValueError,
        match="Report period must use YYYY-MM format.",
    ):
        ReportPeriod.from_string(value)


# =====================================================================
# Verifies that a report period rejects month values outside the
# supported calendar range.
# =====================================================================


@pytest.mark.parametrize(
    "month",
    [
        0,
        13,
    ],
)
def test_report_period_rejects_invalid_month(
    month: int,
) -> None:
    with pytest.raises(
        ValueError,
        match="Month must be between 1 and 12.",
    ):
        ReportPeriod(
            year=2026,
            month=month,
        )


# =====================================================================
# Verifies that a report period rejects non-positive year values.
# =====================================================================


def test_report_period_rejects_invalid_year() -> None:
    with pytest.raises(
        ValueError,
        match="Year must be greater than zero.",
    ):
        ReportPeriod(
            year=0,
            month=8,
        )
