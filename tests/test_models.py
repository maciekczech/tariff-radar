from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from tariff_radar.models import TariffEvent


def test_rejects_non_http_source_urls() -> None:
    with pytest.raises(ValidationError):
        TariffEvent(
            external_id="1",
            source="bad",
            source_url="javascript:alert(1)",
            title="Bad link",
            published_at=datetime.now(UTC),
        )

    with pytest.raises(ValidationError):
        TariffEvent(
            external_id="2",
            source="bad",
            source_url="https://example.test/) @everyone",
            title="Bad display URL",
            published_at=datetime.now(UTC),
        )


def test_normalizes_event_datetimes_to_utc() -> None:
    event = TariffEvent(
        external_id="1",
        source="test",
        source_url="https://example.test/1",
        title="Changed duty",
        published_at=datetime(2026, 8, 20, 14, tzinfo=timezone(timedelta(hours=2))),
    )
    assert event.published_at.isoformat() == "2026-08-20T12:00:00+00:00"
