from io import BytesIO
from pathlib import Path

import pytest

from apple_health.exceptions import InvalidArchiveError
from apple_health.models import HealthData
from apple_health.providers.apple.config import AppleProviderConfig
from apple_health.providers.apple.provider import AppleHealthProvider
from apple_health.providers.contract import HealthDataProviderError


def test_apple_provider_returns_canonical_data_and_provenance(monkeypatch) -> None:
    expected = HealthData(workouts=[], daily_metrics=[], sleep_records=[])

    class FakeImporter:
        def __init__(self, path: Path) -> None:
            assert path == Path("export.zip")

        def open_export(self):
            class Export:
                def __enter__(self):
                    return BytesIO(b"<HealthData />")

                def __exit__(self, *args):
                    return False

            return Export()

    class FakeParser:
        def __init__(self, xml_stream, config) -> None:
            assert isinstance(config, AppleProviderConfig)

        def parse(self) -> HealthData:
            return expected

    monkeypatch.setattr("apple_health.providers.apple.provider.AppleHealthImporter", FakeImporter)
    monkeypatch.setattr("apple_health.providers.apple.provider.AppleHealthParser", FakeParser)

    loaded = AppleHealthProvider().load(Path("export.zip"), config=AppleProviderConfig())

    assert loaded.data is expected
    assert loaded.provenance.provider_id == "apple_health"
    assert loaded.provenance.display_label == "Apple Health"


def test_apple_provider_translates_apple_input_errors(monkeypatch) -> None:
    class FakeImporter:
        def __init__(self, path: Path) -> None:
            pass

        def open_export(self):
            raise InvalidArchiveError

    monkeypatch.setattr("apple_health.providers.apple.provider.AppleHealthImporter", FakeImporter)

    with pytest.raises(HealthDataProviderError, match="invalid_archive"):
        AppleHealthProvider().load(Path("invalid.zip"), config=AppleProviderConfig())
