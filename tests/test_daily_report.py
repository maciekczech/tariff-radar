import importlib.util
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from tariff_radar.models import TariffEvent
from tariff_radar.storage import EventStore

_SCRIPT = Path(__file__).parents[1] / "scripts" / "daily_report.py"
_SPEC = importlib.util.spec_from_file_location("tariff_radar_daily_report", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
daily_report = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(daily_report)


def test_daily_report_uses_seven_day_fallback_when_day_is_quiet(tmp_path, monkeypatch) -> None:
    database = tmp_path / "radar.db"
    store = EventStore(database)
    store.upsert_many(
        [
            TariffEvent(
                external_id="1",
                source="Official source",
                source_url="https://example.test/measure",
                title="Final steel duty order",
                summary="The authority issued a final duty order affecting steel imports.",
                published_at=datetime.now(UTC) - timedelta(days=2),
                reporter="Country A",
                status="final",
            )
        ]
    )
    store.record_source_run(
        source="Official source", status="ok", fetched_count=1, inserted_count=1
    )
    monkeypatch.setattr(daily_report, "DB", database)

    report = daily_report.build_report(
        datetime.now(ZoneInfo("Europe/Warsaw")),
        {"fetched": 1, "inserted": 0, "errors": {}},
    )

    assert "Dziś bez nowej decyzji taryfowej" in report
    assert "najważniejsze aktywne tematy z ostatnich 7 dni" in report
    assert "Final steel duty order" in report
    assert "Decyzja końcowa" in report
    assert "Brak nowych oficjalnych publikacji" not in report
