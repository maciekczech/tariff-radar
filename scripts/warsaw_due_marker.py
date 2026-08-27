#!/usr/bin/env python3
"""Emit a stable date marker that changes exactly at 09:00 Europe/Warsaw."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

now = datetime.now(ZoneInfo("Europe/Warsaw"))
report_date = now.date() if now.hour >= 9 else (now - timedelta(days=1)).date()
print(report_date.isoformat())
