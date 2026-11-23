"""Refresh the FX defaults from the ECB euro reference rates (official, published each working day).

    python scripts/refresh_fx.py            # update data/rates.csv and the copies in src/
    python scripts/refresh_fx.py --dry-run  # only print what would change

Updates: fx_cny_per_eur, fx_cny_per_usd (EUR/CNY divided by EUR/USD) and fx_horizon_sd (std of
42-trading-day log changes in EUR/CNY over the last two years). Standard library only.
After a refresh, rebuild the front end (npm run build). The tests pin FX, so they do not move.

A running server also refreshes these three rates in memory every day (landed/fx.py); this script moves
the snapshot that ships in the repository, which the server starts from.
"""
from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from landed import fx  # noqa: E402

SOURCE = fx.SOURCE


def main(dry: bool) -> None:
    try:
        res = fx.fetch()
    except ValueError as e:
        raise SystemExit(f"{e}; not updating")
    last, updates = res["date"], res["rows"]
    eur_cny, usd_cny, sd = (updates[k][0] for k in ("fx_cny_per_eur", "fx_cny_per_usd", "fx_horizon_sd"))
    print(f"ECB {last}: EUR/CNY {eur_cny}, USD/CNY {usd_cny}, 60-day sd {sd} ({res['windows']} windows from {res['first_day']})")
    if dry:
        return

    p = ROOT / "data/rates.csv"
    rows = list(csv.reader(p.open(encoding="utf-8", newline="")))
    ix = {h: i for i, h in enumerate(rows[0])}
    pretty = fx.pretty(last)
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
