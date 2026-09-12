from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ReportOutputs:
    full_text: bool = False
    full_json: bool = True
    summary_text: bool = False
    summary_json: bool = False

    def __post_init__(self) -> None:
        if not any(
            (
                self.full_text,
                self.full_json,
                self.summary_text,
                self.summary_json,
            )
        ):
            raise ValueError("At least one report output must be selected.")
