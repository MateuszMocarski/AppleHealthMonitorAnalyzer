from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from apple_health.models import HealthData


@dataclass(frozen=True, slots=True)
class DatasetProvenance:
    provider_id: str
    display_label: str


@dataclass(frozen=True, slots=True)
class LoadedHealthData:
    data: HealthData
    provenance: DatasetProvenance


class HealthDataProvider(Protocol):
    provider_id: str

    def load(self, path: Path, *, config: object) -> LoadedHealthData: ...


class HealthDataProviderError(Exception):
    """Safe provider-neutral classification of an expected input failure."""

    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)
