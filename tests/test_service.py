from datetime import UTC, datetime

import pytest

from tariff_radar.models import TariffEvent
from tariff_radar.service import sync_sources


class FakeSource:
    def __init__(self, name: str) -> None:
        self.name = name
        self.url = f"https://example.test/{name}"

    async def fetch(self) -> list[TariffEvent]:
        return [
            TariffEvent(
                external_id=self.name,
                source=self.name,
                source_url=self.url,
                title="Import duty changed",
                published_at=datetime(2026, 8, 20, tzinfo=UTC),
            )
        ]


class PartiallyFailingStore:
    def __init__(self) -> None:
        self.saved: list[str] = []
        self.runs: list[tuple[str, str]] = []

    def upsert_many(self, events: list[TariffEvent]) -> int:
        if events[0].source == "bad":
            raise RuntimeError("database rejected source")
        self.saved.append(events[0].source)
        return 1

    def record_source_run(self, *, source: str, status: str, **_: object) -> None:
        self.runs.append((source, status))


@pytest.mark.anyio
async def test_storage_failure_isolated_per_source() -> None:
    store = PartiallyFailingStore()
    result = await sync_sources(store, [FakeSource("bad"), FakeSource("good")])  # type: ignore[arg-type]
    assert result.inserted == 1
    assert store.saved == ["good"]
    assert "bad" in result.errors
    assert store.runs == [("bad", "failed"), ("good", "ok")]
