import re
from dataclasses import dataclass

_PERIOD_PATTERN = re.compile(r"^(?P<year>\d{4})-(?P<month>\d{2})$")


@dataclass(frozen=True, slots=True)
class ReportPeriod:
    year: int
    month: int

    def __post_init__(self) -> None:
        if self.year < 1:
            raise ValueError("Year must be greater than zero.")

        if not 1 <= self.month <= 12:
            raise ValueError("Month must be between 1 and 12.")

    @classmethod
    def from_string(
        cls,
        value: str,
    ) -> "ReportPeriod":
        match = _PERIOD_PATTERN.fullmatch(value)

        if match is None:
            raise ValueError("Report period must use YYYY-MM format.")

        return cls(
            year=int(match.group("year")),
            month=int(match.group("month")),
        )
