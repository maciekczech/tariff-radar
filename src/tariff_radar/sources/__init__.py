from tariff_radar.sources.base import Source
from tariff_radar.sources.federal_register import FederalRegisterSource
from tariff_radar.sources.rss import RssSource


def default_sources() -> list[Source]:
    return [
        FederalRegisterSource(),
        RssSource(
            name="WTO News",
            url="https://www.wto.org/library/rss/latest_news_e.xml",
            reporter=None,
        ),
        RssSource(
            name="European Commission DG Trade",
            url="https://policy.trade.ec.europa.eu/node/2/rss_en",
            reporter="European Union",
        ),
        RssSource(
            name="EUR-Lex Official Journal L",
            url="https://eur-lex.europa.eu/EN/display-feed.rss?rssId=222",
            reporter="European Union",
        ),
    ]


__all__ = ["Source", "FederalRegisterSource", "RssSource", "default_sources"]
