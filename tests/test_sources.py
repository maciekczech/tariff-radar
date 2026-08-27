import json
from pathlib import Path

import httpx
import pytest
import respx

from tariff_radar.sources.federal_register import FederalRegisterSource
from tariff_radar.sources.rss import RssSource

FIXTURES = Path(__file__).parent / "fixtures"


def test_federal_register_parser_filters_false_positive() -> None:
    payload = json.loads((FIXTURES / "federal_register.json").read_text())
    events = FederalRegisterSource().parse(payload)
    assert len(events) == 1
    assert events[0].external_id == "2026-12345"
    assert events[0].reporter == "United States"
    assert events[0].source_document_url == "https://www.govinfo.gov/example.pdf"


def test_federal_register_parser_quarantines_malformed_entry() -> None:
    payload = json.loads((FIXTURES / "federal_register.json").read_text())
    payload["results"].insert(
        0,
        {
            "title": "Import tariffs increased",
            "abstract": "Government raises import duties",
            "document_number": "broken",
            "html_url": "not-a-url",
        },
    )
    events = FederalRegisterSource().parse(payload)
    assert [event.external_id for event in events] == ["2026-12345"]


def test_federal_register_parser_ignores_non_object_entries_and_container() -> None:
    payload = json.loads((FIXTURES / "federal_register.json").read_text())
    payload["results"] = [None, "bad", 42, payload["results"][0]]
    assert [event.external_id for event in FederalRegisterSource().parse(payload)] == ["2026-12345"]
    assert FederalRegisterSource().parse({"results": None}) == []


def test_rss_parser_keeps_only_tariff_signals() -> None:
    xml = (FIXTURES / "wto.xml").read_bytes()
    events = RssSource(name="WTO", url="https://example.test/rss", reporter=None).parse(xml)
    assert len(events) == 1
    assert events[0].external_id == "tariff-1"
    assert events[0].published_at.isoformat().startswith("2026-08-19")


def test_rss_parser_does_not_fabricate_missing_publication_date() -> None:
    xml = b"""<rss><channel><item><title>Import tariffs increased</title>
    <link>https://example.test/change</link><description>Government raises tariffs</description>
    </item></channel></rss>"""
    assert RssSource(name="test", url="https://example.test/rss", reporter=None).parse(xml) == []


def test_rss_parser_rejects_unreadable_feed() -> None:
    with pytest.raises(ValueError, match="unreadable RSS"):
        RssSource(name="test", url="https://example.test/rss", reporter=None).parse(b"not xml")


@pytest.mark.anyio
@respx.mock
async def test_federal_register_fetch_paginates_recent_results() -> None:
    def item(number: str) -> dict[str, object]:
        return {
            "title": f"Import tariffs changed {number}",
            "abstract": "Government increases import duties",
            "document_number": number,
            "html_url": f"https://www.federalregister.gov/documents/{number}",
            "publication_date": "2026-08-20",
            "agencies": [],
        }

    route = respx.get(FederalRegisterSource.url).mock(
        side_effect=[
            httpx.Response(200, json={"total_pages": 2, "results": [item("one")]}),
            httpx.Response(200, json={"total_pages": 2, "results": [item("two")]}),
        ]
    )
    events = await FederalRegisterSource().fetch()
    assert [event.external_id for event in events] == ["one", "two"]
    assert route.call_count == 2


@pytest.mark.anyio
@respx.mock
async def test_rss_fetch_retries_transient_failure(monkeypatch) -> None:
    route = respx.get("https://example.test/rss").mock(
        side_effect=[
            httpx.Response(503),
            httpx.Response(200, content=(FIXTURES / "wto.xml").read_bytes()),
        ]
    )

    async def no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr("asyncio.sleep", no_sleep)
    events = await RssSource(name="WTO", url="https://example.test/rss", reporter=None).fetch()
    assert len(events) == 1
    assert route.call_count == 2
