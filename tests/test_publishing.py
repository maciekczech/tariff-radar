import subprocess
from datetime import UTC, datetime

import pytest

from tariff_radar.models import TariffEvent
from tariff_radar.publishers.xurl import publish_thread_with_xurl
from tariff_radar.publishing import build_x_thread, x_weighted_length


def event(number: int, title: str) -> TariffEvent:
    return TariffEvent(
        external_id=str(number),
        source="WTO",
        source_url=f"https://example.test/{number}",
        title=title,
        published_at=datetime(2026, 8, 26, tzinfo=UTC),
        reporter="European Union",
        status="final",
    )


def test_x_thread_is_numbered_linked_and_within_limit() -> None:
    posts = build_x_thread(
        [event(1, "A" * 400), event(2, "Steel duty changed")],
        generated_at=datetime(2026, 8, 27, tzinfo=UTC),
    )
    assert len(posts) == 3
    assert all(len(post) <= 280 for post in posts)
    assert all(x_weighted_length(post) <= 280 for post in posts)
    assert posts[0].startswith("Tariff Radar — daily brief")
    assert "1/3" in posts[0]
    assert "https://example.test/1" in posts[1]
    assert posts[2].endswith("3/3")


def test_empty_x_thread_has_single_post() -> None:
    posts = build_x_thread([], generated_at=datetime(2026, 8, 27, tzinfo=UTC))
    assert len(posts) == 1
    assert "No new official tariff signals" in posts[0]


def test_x_weighting_treats_urls_and_unicode_conservatively() -> None:
    assert x_weighted_length("https://example.test/a-very-long-path") == 23
    assert x_weighted_length("cło ✅") == 7


def test_x_thread_handles_cjk_long_url_and_neutralizes_mentions() -> None:
    signal = event(3, "関税" * 200)
    signal.reporter = "@everyone"
    signal.source_url = "https://example.test/" + "x" * 400
    posts = build_x_thread([signal], generated_at=datetime(2026, 8, 27, tzinfo=UTC))
    assert all(x_weighted_length(post) <= 280 for post in posts)
    assert "@\u200beveryone" in posts[1]


def test_live_x_publish_requires_installed_official_cli(monkeypatch) -> None:
    monkeypatch.setattr("shutil.which", lambda _: None)
    with pytest.raises(RuntimeError, match="xurl is not installed"):
        publish_thread_with_xurl(["preview"])


def test_x_thread_posts_then_replies_without_shell(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        post_id = str(len(calls))
        return subprocess.CompletedProcess(command, 0, f'{{"data":{{"id":"{post_id}"}}}}', "")

    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/xurl")
    monkeypatch.setattr("subprocess.run", fake_run)
    assert publish_thread_with_xurl(["first", "second"]) == ["1", "2"]
    assert calls == [
        ["/usr/bin/xurl", "post", "first"],
        ["/usr/bin/xurl", "reply", "1", "second"],
    ]


def test_x_thread_resumes_from_durable_state(monkeypatch, tmp_path) -> None:
    calls: list[list[str]] = []
    fail_reply = True

    def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        nonlocal fail_reply
        calls.append(command)
        if command[1] == "reply" and fail_reply:
            fail_reply = False
            raise subprocess.CalledProcessError(1, command)
        post_id = "1" if command[1] == "post" else "2"
        return subprocess.CompletedProcess(command, 0, f'{{"data":{{"id":"{post_id}"}}}}', "")

    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/xurl")
    monkeypatch.setattr("subprocess.run", fake_run)
    state = tmp_path / "x-state.json"
    with pytest.raises(subprocess.CalledProcessError):
        publish_thread_with_xurl(["first", "second"], state_path=state)
    calls.clear()
    assert publish_thread_with_xurl(["first", "second"], state_path=state) == ["1", "2"]
    assert calls == [["/usr/bin/xurl", "reply", "1", "second"]]
