from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ReportPeriod:
    year: int
    month: int
