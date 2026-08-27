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
    since = datetime.now(UTC) - timedelta(hours=24)
    with sqlite3.connect(DB) as connection:
        connection.row_factory = sqlite3.Row
        events = connection.execute(
            """SELECT title, source, source_url, reporter, status, published_at
            FROM events WHERE published_at >= ?
            ORDER BY published_at DESC LIMIT 5""",
            (since.isoformat(),),
        ).fetchall()
        event_total = connection.execute(
            "SELECT COUNT(*) FROM events WHERE published_at >= ?", (since.isoformat(),)
        ).fetchone()[0]
        counts = connection.execute(
            """SELECT status, COUNT(*) AS count FROM events
            WHERE published_at >= ? GROUP BY status ORDER BY count DESC""",
            (since.isoformat(),),
        ).fetchall()
        sources = connection.execute(
            """SELECT source, status FROM source_runs AS run
            WHERE id = (SELECT MAX(id) FROM source_runs WHERE source = run.source)
            ORDER BY source"""
        ).fetchall()

    ok_sources = sum(row["status"] == "ok" for row in sources)
    lines = [
        "📡 **Tariff Radar — raport dzienny**",
        f"🗓️ {now_warsaw:%d.%m.%Y, %H:%M} · Europe/Warsaw",
        "",
        f"✅ **Źródła:** {ok_sources}/{len(sources)} działają poprawnie",
        f"🆕 **Nowe publikacje z ostatnich 24 h:** {event_total}",
        f"📥 **Synchronizacja:** {sync_data.get('fetched', 0)} pobranych · "
        f"{sync_data.get('inserted', 0)} nowych w bazie",
    ]
    if counts:
        breakdown = " · ".join(f"{row['status']}: {row['count']}" for row in counts)
        lines.append(f"📊 **Etapy:** {breakdown}")

    lines.extend(["", "**Najważniejsze sygnały**"])
    if not events:
        lines.append("• Brak nowych oficjalnych publikacji w tym okresie.")
    for row in events:
        title = " ".join(row["title"].split())
        if len(title) > 110:
            title = title[:109].rstrip() + "…"
        actor = _discord_text(row["reporter"] or "wiele / nieokreślone")
        title = _discord_text(title)
        source = _discord_text(row["source"])
        status = _discord_text(row["status"])
        lines.append(f"• **{status}** · {actor}\n  [{title}]({row['source_url']}) · _{source}_")

    lines.extend(
        [
            "",
            f"🔗 [Repozytorium i metodologia]({REPO_URL})",
            "_To indeks oficjalnych sygnałów, nie kalkulator należności ani porada prawna._",
        ]
    )
    return "\n".join(lines)


def _discord_text(value: str) -> str:
    value = value.replace("@", "@\u200b")
    for character in ("\\", "[", "]", "*", "_", "`", "~", "|", ">"):
        value = value.replace(character, f"\\{character}")
    return value


if __name__ == "__main__":
    main()
