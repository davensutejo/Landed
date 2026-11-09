"""Refresh the FX defaults from the ECB euro reference rates (official, published each working day).

    python scripts/refresh_fx.py            # update data/rates.csv and the copies in src/
    python scripts/refresh_fx.py --dry-run  # only print what would change

Updates: fx_cny_per_eur, fx_cny_per_usd (EUR/CNY divided by EUR/USD) and fx_horizon_sd (std of
42-trading-day log changes in EUR/CNY over the last two years). Standard library only.
After a refresh, rebuild the front end (npm run build). The tests pin FX, so they do not move.
"""
from __future__ import annotations

import csv
import math
import re
import statistics
import sys
import urllib.request
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = "https://data-api.ecb.europa.eu/service/data/EXR/D.{cur}.EUR.SP00.A?startPeriod={start}&format=csvdata"
SOURCE = "https://data-api.ecb.europa.eu/service/data/EXR/D.CNY.EUR.SP00.A"
HORIZON = 42  # trading days, about 60 calendar days


def series(cur: str, start: str) -> dict[str, float]:
    with urllib.request.urlopen(API.format(cur=cur, start=start), timeout=60) as r:
        rows = csv.DictReader(r.read().decode("utf-8").splitlines())
        return {x["TIME_PERIOD"]: float(x["OBS_VALUE"]) for x in rows if x["OBS_VALUE"]}


def main(dry: bool) -> None:
    start = (date.today() - timedelta(days=730)).isoformat()
    cny, usd = series("CNY", start), series("USD", start)
    days = sorted(set(cny) & set(usd))
    if len(days) < 300:
        raise SystemExit(f"ECB returned only {len(days)} common days; not updating")
    last = days[-1]
    eur_cny = cny[last]
    usd_cny = round(eur_cny / usd[last], 4)
    logs = [math.log(cny[days[i + HORIZON]] / cny[days[i]]) for i in range(len(days) - HORIZON)]
    sd = round(statistics.pstdev(logs), 3)
    print(f"ECB {last}: EUR/CNY {eur_cny}, USD/CNY {usd_cny}, 60-day sd {sd} ({len(logs)} windows from {days[0]})")
    if dry:
        return

    p = ROOT / "data/rates.csv"
    rows = list(csv.reader(p.open(encoding="utf-8", newline="")))
    ix = {h: i for i, h in enumerate(rows[0])}
    pretty = date.fromisoformat(last).strftime("%-d %b %Y") if sys.platform != "win32" else date.fromisoformat(last).strftime("%d %b %Y").lstrip("0")
    updates = {
        "fx_cny_per_eur": (eur_cny, f"ECB euro foreign exchange reference rate, EUR/CNY, {pretty} (published daily). Your bank or payment provider adds a spread."),
        "fx_cny_per_usd": (usd_cny, f"Cross rate from the ECB reference rates of {pretty}: EUR/CNY {eur_cny} divided by EUR/USD {usd[last]}. Your bank or payment provider adds a spread."),
        "fx_horizon_sd": (sd, f"Standard deviation of {HORIZON}-trading-day log changes in the ECB EUR/CNY reference rate, {days[0]} to {last} ({len(logs)} overlapping windows). The USD/CNY cross is calmer, so this is conservative for the US."),
    }
    for r in rows[1:]:
        if r[ix["key"]] in updates:
            v, note = updates[r[ix["key"]]]
            r[ix["value"]], r[ix["note"]], r[ix["snapshot_date"]], r[ix["status"]], r[ix["source_url"]] = str(v), note, last, "verified", SOURCE
    with p.open("w", encoding="utf-8", newline="") as f:
        csv.writer(f, lineterminator="\n").writerows(rows)

    def sub(path: str, pairs: list[tuple[str, str]]) -> None:
        f = ROOT / path
        s = f.read_text(encoding="utf-8")
        for pattern, repl in pairs:
            s, n = re.subn(pattern, repl, s, count=1)
            if n != 1:
                print(f"  warning: {path}: pattern not found: {pattern[:40]}")
        f.write_text(s, encoding="utf-8")

    sub("src/data/landed.js", [
        (r"fxMean: [\d.]+,[^\n]*", f"fxMean: {eur_cny},   // CNY per EUR, ECB reference rate {last}"),
        (r"fxSd: [\d.]+,[^\n]*", f"fxSd: {sd},      // relative sd of ~60-day changes, computed from ECB daily rates"),
        (r"CNY per EUR [\d.]+ \(ECB reference rate, [^)]*\) and a [\d.]+% volatility", f"CNY per EUR {eur_cny} (ECB reference rate, {pretty}) and a {sd * 100:.1f}% volatility"),
    ])
    sub("src/agent/main.js", [(r"fx: \{ DE: [\d.]+, US: [\d.]+ \}", f"fx: {{ DE: {eur_cny}, US: {usd_cny} }}")])
    print("updated data/rates.csv, src/data/landed.js, src/agent/main.js. Now run: npm run build")


if __name__ == "__main__":
    main("--dry-run" in sys.argv)
