from pathlib import Path

import pytest

from connected_health.application.multi_month_run_options import (
    MultiMonthRunOptions,
)
from connected_health.application.report_outputs import ReportOutputs

# =====================================================================
# Verifies that report output selection defaults to Full JSON only.
# =====================================================================


def test_report_outputs_default_to_full_json_only() -> None:
    outputs = ReportOutputs()

    assert outputs.full_text is False
    assert outputs.full_json is True
    assert outputs.summary_text is False
    assert outputs.summary_json is False


# =====================================================================
# Verifies that report output selection rejects disabling every output.
# =====================================================================


def test_report_outputs_reject_all_outputs_disabled() -> None:
    with pytest.raises(
        ValueError,
        match="At least one report output must be selected.",
    ):
        ReportOutputs(
            full_text=False,
            full_json=False,
            summary_text=False,
            summary_json=False,
        )


# =====================================================================
# Verifies that multi-month generation uses the default report output
# selection when no explicit selection is provided.
# =====================================================================


def test_multi_month_run_options_default_to_full_json_only() -> None:
    options = MultiMonthRunOptions(
        archive_path=Path("export.zip"),
        periods=(),
        config_path=None,
    )

    assert options.outputs == ReportOutputs()
