"""FX from the ECB euro reference rates (official, published each working day), kept fresh while the server runs.

data/rates.csv ships a dated snapshot. A server that runs for weeks would otherwise price with a rate that is weeks
old, so `start_refresher` fetches the ECB rates at startup and once a day and replaces the three FX rows in memory.
Each replaced row keeps its provenance: the ECB date becomes its snapshot date, and its note says it was fetched live.

A fetch is used only if it passes sanity checks: a newer ECB date than the row it replaces, and a rate within 15% of
the shipped snapshot (a broken feed must not reprice every product). Anything else keeps the last good value.
Standard library only. `scripts/refresh_fx.py` uses `fetch` to write a new snapshot into the repository.
"""
from __future__ import annotations

import csv
import logging
import math
import os
import statistics
import threading
import urllib.request
from dataclasses import replace
from datetime import date, timedelta

from . import data

API = "https://data-api.ecb.europa.eu/service/data/EXR/D.{cur}.EUR.SP00.A?startPeriod={start}&format=csvdata"
SOURCE = "https://data-api.ecb.europa.eu/service/data/EXR/D.CNY.EUR.SP00.A"
HORIZON = 42  # trading days, about 60 calendar days
MAX_JUMP = 0.15  # a refresh may move a rate at most 15% away from the shipped snapshot
REFRESH_S = 24 * 3600
RETRY_S = 3600

log = logging.getLogger("landed.fx")
_status: dict = {"live": False, "date": None, "checked_at": None, "error": None}


def _series(cur: str, start: str, timeout: float) -> dict[str, float]:
    with urllib.request.urlopen(API.format(cur=cur, start=start), timeout=timeout) as r:
        rows = csv.DictReader(r.read().decode("utf-8").splitlines())
        return {x["TIME_PERIOD"]: float(x["OBS_VALUE"]) for x in rows if x["OBS_VALUE"]}


def pretty(day: str) -> str:
    d = date.fromisoformat(day)
    return f"{d.day} {d.strftime('%b %Y')}"


def fetch(timeout: float = 60) -> dict:
    """The latest ECB rates and the 60-day volatility, with the notes each rates.csv row carries."""
    start = (date.today() - timedelta(days=730)).isoformat()
    cny, usd = _series("CNY", start, timeout), _series("USD", start, timeout)
    days = sorted(set(cny) & set(usd))
    if len(days) < 300:
        raise ValueError(f"ECB returned only {len(days)} common days")
    last = days[-1]
    eur_cny = cny[last]
    usd_cny = round(eur_cny / usd[last], 4)
    logs = [math.log(cny[days[i + HORIZON]] / cny[days[i]]) for i in range(len(days) - HORIZON)]
    sd = round(statistics.pstdev(logs), 3)
    p = pretty(last)
    return {
        "date": last,
        "first_day": days[0],
        "windows": len(logs),
        "eur_usd": usd[last],
        "rows": {
            "fx_cny_per_eur": (eur_cny, f"ECB euro foreign exchange reference rate, EUR/CNY, {p} (published daily). "
                                        "Your bank or payment provider adds a spread."),
            "fx_cny_per_usd": (usd_cny, f"Cross rate from the ECB reference rates of {p}: EUR/CNY {eur_cny} divided by "
                                        f"EUR/USD {usd[last]}. Your bank or payment provider adds a spread."),
            "fx_horizon_sd": (sd, f"Standard deviation of {HORIZON}-trading-day log changes in the ECB EUR/CNY reference "
                                  f"rate, {days[0]} to {last} ({len(logs)} overlapping windows). The USD/CNY cross is "
                                  "calmer, so this is conservative for the US."),
        },
    }


_MARKET = {"fx_cny_per_eur": "EU", "fx_cny_per_usd": "US", "fx_horizon_sd": "ALL"}


def apply(result: dict) -> list[str]:
    """Replace the in-memory FX rows with a fetched result that passes the sanity checks. Returns the keys replaced."""
    table = data.rates()
    shipped = data.shipped_rates()
    changed = []
    for key, (value, note) in result["rows"].items():
        k = (key, _MARKET[key])
        cur, base = table.get(k), shipped.get(k)
        if cur is None or base is None or not base.value:
            continue
        if not (isinstance(value, (int, float)) and math.isfinite(value) and value > 0):
            continue
        if result["date"] <= cur.snapshot_date:
            continue  # nothing newer than what is in use
        if key != "fx_horizon_sd" and abs(value / base.value - 1) > MAX_JUMP:
            log.warning("ECB %s %s is more than %.0f%% from the snapshot %s; ignored", key, value, MAX_JUMP * 100, base.value)
            continue
        table[k] = replace(cur, value=float(value), snapshot_date=result["date"], status="verified", source_url=SOURCE,
                           note=note + " Fetched live from the ECB by the server.")
        changed.append(key)
    return changed


def refresh_once(timeout: float = 20) -> list[str]:
    from time import time

    _status["checked_at"] = time()
    try:
        changed = apply(fetch(timeout))
    except Exception as e:  # network, parse or ECB format errors: keep the last good value
        _status["error"] = f"{type(e).__name__}: {e}"[:200]
        log.warning("FX refresh failed, keeping %s: %s", status()["date"], _status["error"])
        return []
    _status["error"] = None
    if changed:
        _status["live"] = True
        log.info("FX refreshed from the ECB: %s", ", ".join(changed))
    return changed


def status() -> dict:
    """What /api/health reports: the FX date in use and whether it came from a live fetch."""
    r = data.rates().get(("fx_cny_per_eur", "EU"))
    return {**_status, "date": r.snapshot_date if r else None}


def enabled() -> bool:
    return os.environ.get("LANDED_LIVE_FX", "1").strip().lower() not in ("0", "false", "no", "off")


_started = False


def start_refresher(wait_s: float = 5.0) -> bool:
    """Refresh now and then daily, in a daemon thread. Off with LANDED_LIVE_FX=0.

    Startup waits up to `wait_s` for the first refresh, so the first visitor after a cold start sees the same FX
    date in the header as in the prices. A slow or unreachable ECB only costs those seconds: the shipped snapshot
    stays in use and the thread keeps trying every hour."""
    global _started
    if _started or not enabled():
        return False
    _started = True
    first = threading.Event()

    def loop() -> None:
        import time

        while True:
            ok = refresh_once() or _status["error"] is None
            first.set()
            time.sleep(REFRESH_S if ok else RETRY_S)

    threading.Thread(target=loop, name="fx-refresh", daemon=True).start()
    first.wait(wait_s)
    return True
