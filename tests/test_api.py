from datetime import UTC, datetime

from fastapi.testclient import TestClient

from tariff_radar.api import create_app
from tariff_radar.models import TariffEvent
from tariff_radar.storage import EventStore


def test_events_api_and_digest(tmp_path) -> None:
    store = EventStore(tmp_path / "radar.db")
    store.upsert_many(
        [
            TariffEvent(
                external_id="1",
                source="WTO",
                source_url="https://example.test/1",
                title="New steel tariff",
                summary="A duty was imposed",
                published_at=datetime(2026, 8, 20, tzinfo=UTC),
                reporter="Country A",
            )
        ]
    )
    client = TestClient(create_app(store))
    response = client.get("/api/v1/events")
    assert response.status_code == 200
    assert response.json()["total"] == 1
    digest = client.get("/api/v1/digest?days=3650")
    assert digest.status_code == 200
    assert "New steel tariff" in digest.json()["markdown"]
    assert digest.json()["total"] == 1
    assert digest.json()["truncated"] is False


def test_dashboard_and_health(tmp_path) -> None:
    store = EventStore(tmp_path / "radar.db")
    store.record_source_run(source="WTO", status="ok", fetched_count=2, inserted_count=1)
    client = TestClient(create_app(store))
    assert client.get("/").status_code == 200
    assert "Tariff Radar" in client.get("/").text
    assert client.get("/healthz").json() == {"status": "ok", "events": 0}
    assert client.get("/api/v1/sources").json()["items"][0]["source"] == "WTO"


def test_filtered_total_is_not_limited_to_page_size(tmp_path) -> None:
    store = EventStore(tmp_path / "radar.db")
    for number in ("1", "2"):
        store.upsert_many(
            [
                TariffEvent(
                    external_id=number,
                    source="WTO",
                    source_url=f"https://example.test/{number}",
                    title=f"Steel duty {number}",
                    published_at=datetime(2026, 8, 20, tzinfo=UTC),
                    reporter="Country A",
                )
            ]
        )
    response = TestClient(create_app(store)).get("/api/v1/events?reporter=Country%20A&limit=1")
    assert response.json()["total"] == 2
    assert len(response.json()["items"]) == 1


def test_query_limits_reject_abusive_inputs(tmp_path) -> None:
    client = TestClient(create_app(EventStore(tmp_path / "radar.db")))
    assert client.get("/api/v1/events?offset=1000001").status_code == 422
    assert client.get(f"/api/v1/events?q={'x' * 201}").status_code == 422
