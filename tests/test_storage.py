from datetime import UTC, datetime

from tariff_radar.models import TariffEvent
from tariff_radar.storage import EventStore


def make_event(title: str = "Tariff raised") -> TariffEvent:
    return TariffEvent(
        external_id="abc",
        source="test",
        source_url="https://example.test/a",
        title=title,
        summary="Import duty changed",
        published_at=datetime(2026, 8, 20, tzinfo=UTC),
        reporter="Country A",
        raw={"official": True},
    )


def test_upsert_is_idempotent_and_updates_content(tmp_path) -> None:
    store = EventStore(tmp_path / "radar.db")
    assert store.upsert_many([make_event()]) == 1
    assert store.upsert_many([make_event("Tariff raised — corrected")]) == 0
    events = store.list_events()
    assert len(events) == 1
    assert events[0].title == "Tariff raised — corrected"
    assert events[0].raw == {"official": True}


def test_filters_by_reporter_and_query(tmp_path) -> None:
    store = EventStore(tmp_path / "radar.db")
    store.upsert_many([make_event()])
    assert len(store.list_events(reporter="Country A")) == 1
    assert len(store.list_events(reporter="Country B")) == 0
    assert len(store.list_events(query="Import duty")) == 1
    assert len(store.list_events(query="%")) == 0
