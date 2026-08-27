#!/usr/bin/env python3
from __future__ import annotations

import fcntl
import json
import os
import shutil
import sqlite3
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

WARSAW = ZoneInfo("Europe/Warsaw")
_LOCAL_ROOT = Path(__file__).resolve().parents[1]
ROOT = (
    _LOCAL_ROOT
    if (_LOCAL_ROOT / "pyproject.toml").exists()
    else Path(os.getenv("TARIFF_RADAR_ROOT", "/opt/data/projects/tariff-radar"))
)
DB = ROOT / "data" / "tariff-radar.db"
REPO_URL = "https://github.com/maciekczech/tariff-radar"
UV = shutil.which("uv")


def main() -> None:
    now_warsaw = datetime.now(WARSAW)
    if now_warsaw.hour != 9 and os.getenv("TARIFF_RADAR_FORCE_RUN") != "1":
        return

    DB.parent.mkdir(parents=True, exist_ok=True)
    lock = (DB.parent / "daily-report.lock").open("w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return
    marker = DB.parent / "daily-report-last-date"
    today = now_warsaw.date().isoformat()
    if marker.exists() and marker.read_text().strip() == today:
        return
    if UV is None:
        raise RuntimeError("uv is required to run the Tariff Radar daily report")
    sync = subprocess.run(  # noqa: S603 - fixed executable and argument vector
        [UV, "run", "tariff-radar", "--db", str(DB), "sync"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=180,
    )
    try:
        sync_data = json.loads(sync.stdout)
    except json.JSONDecodeError:
        print(
            "🚨 **Tariff Radar — błąd raportu dziennego**\n\n"
            "Synchronizacja nie zwróciła poprawnego wyniku. "
            f"Sprawdź logi projektu: {REPO_URL}/actions"
        )
        raise SystemExit(1) from None

    report = build_report(now_warsaw, sync_data)
    errors = sync_data.get("errors") or {}
    if errors:
        failed = ", ".join(sorted(errors))
        report += (
            "\n\n⚠️ **Częściowa synchronizacja:** "
            f"nie udało się odświeżyć: {failed}. Pozostałe źródła są ujęte w raporcie."
        )

    x_note = ""
    if os.getenv("TARIFF_RADAR_POST_TO_X", "").casefold() in {"1", "true", "yes"}:
        published = subprocess.run(  # noqa: S603 - fixed executable and argument vector
            [
                UV,
                "run",
                "tariff-radar",
                "--db",
                str(DB),
                "publish-x",
                "--days",
                "1",
                "--state-file",
                str(DB.parent / f"x-publish-{today}.json"),
                "--execute",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=180,
        )
        if published.returncode == 0:
            count = json.loads(published.stdout)["posted"]
            x_note = f"\n\n🐦 **X:** opublikowano wątek ({count} postów)."
        else:
            x_note = "\n\n⚠️ **X:** publikacja nie powiodła się; raport Discord pozostał dostępny."

    temporary_marker = marker.with_suffix(".tmp")
    temporary_marker.write_text(today)
    temporary_marker.replace(marker)
    print(report + x_note)


def build_report(now_warsaw: datetime, sync_data: dict[str, object]) -> str:
    now_utc = datetime.now(UTC)
    since_24h = now_utc - timedelta(hours=24)
    since_7d = now_utc - timedelta(days=7)
    with sqlite3.connect(DB) as connection:
        connection.row_factory = sqlite3.Row
        fresh_total = connection.execute(
            "SELECT COUNT(*) FROM events WHERE published_at >= ?", (since_24h.isoformat(),)
        ).fetchone()[0]
        selection_since = since_24h if fresh_total else since_7d
        candidates = connection.execute(
            """SELECT title, summary, source, source_url, reporter, status, published_at
            FROM events WHERE published_at >= ?
            ORDER BY CASE status
                WHEN 'final' THEN 100
                WHEN 'suspended' THEN 90
                WHEN 'revoked_or_terminated' THEN 80
                WHEN 'announced' THEN 70
                WHEN 'investigation' THEN 40
                WHEN 'review' THEN 20
                ELSE 10 END DESC,
                published_at DESC LIMIT 12""",
            (selection_since.isoformat(),),
        ).fetchall()
        sources = connection.execute(
            """SELECT source, status FROM source_runs AS run
            WHERE id = (SELECT MAX(id) FROM source_runs WHERE source = run.source)
            ORDER BY source"""
        ).fetchall()

    events = _diverse_top_events(candidates, limit=3)
    ok_sources = sum(row["status"] == "ok" for row in sources)
    lines = [
        "📡 **Tariff Radar — poranny brief**",
        f"🗓️ {now_warsaw:%d.%m.%Y} · 09:00 Warszawa",
        "",
    ]
    if fresh_total:
        lines.append(f"🆕 **Od wczoraj:** {fresh_total} nowych oficjalnych publikacji.")
        lines.append("Poniżej najważniejsze z nich — procedury i decyzje końcowe są rozróżnione.")
    else:
        lines.append("🌤️ **Dziś bez nowej decyzji taryfowej.**")
        lines.append("Zamiast pustego raportu: najważniejsze aktywne tematy z ostatnich 7 dni.")

    lines.extend(["", "**Co naprawdę warto wiedzieć**"])
    if not events:
        lines.append("• Brak istotnych oficjalnych sygnałów również w ujęciu 7-dniowym.")
    for index, row in enumerate(events, start=1):
        title = _shorten(" ".join(row["title"].split()), 95)
        actor = _discord_text(row["reporter"] or "wiele / nieokreślone")
        title = _discord_text(title)
        source = _discord_text(row["source"])
        lines.append(
            f"**{index}. {title}**\n"
            f"{_status_takeaway(row['status'])} · {actor} · _{source}_\n"
            f"{_summary_line(row['summary'])}\n"
            f"[Otwórz oficjalne źródło]({row['source_url']})"
        )

    lines.extend(
        [
            "",
            f"_Pokrycie źródeł: {ok_sources}/{len(sources)} · "
            f"synchronizacja: {sync_data.get('inserted', 0)} nowych rekordów_",
            f"Metodologia: <{REPO_URL}>",
        ]
    )
    return "\n".join(lines)


def _diverse_top_events(candidates: list[sqlite3.Row], limit: int) -> list[sqlite3.Row]:
    selected: list[sqlite3.Row] = []
    topics: set[str] = set()
    for row in candidates:
        title = " ".join(row["title"].casefold().split())
        topic = title.split(":", 1)[0]
        if topic in topics:
            continue
        topics.add(topic)
        selected.append(row)
        if len(selected) == limit:
            break
    return selected


def _status_takeaway(status: str) -> str:
    return {
        "final": "✅ Decyzja końcowa — potencjalny realny wpływ na import",
        "suspended": "⏸️ Środek pozostaje wstrzymany — ważne dla terminów i ryzyka odwetu",
        "revoked_or_terminated": "🛑 Środek wycofany lub zakończony",
        "investigation": "🔎 Postępowanie — jeszcze nie jest to nowe obowiązujące cło",
        "review": "📋 Przegląd administracyjny — sygnał do obserwacji",
        "announced": "📣 Oficjalny akt lub komunikat — wymaga sprawdzenia skutków",
    }.get(status, "📡 Oficjalny sygnał taryfowy")


def _summary_line(summary: str) -> str:
    clean = " ".join((summary or "").split())
    if not clean:
        return "Brak krótkiego opisu w kanale źródłowym."
    return _discord_text(_shorten(clean, 140))


def _shorten(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"


def _discord_text(value: str) -> str:
    value = value.replace("@", "@\u200b")
    for character in ("\\", "[", "]", "*", "_", "`", "~", "|", ">"):
        value = value.replace(character, f"\\{character}")
    return value


if __name__ == "__main__":
    main()
