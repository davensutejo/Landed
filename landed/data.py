"""Loads the hand-verified tables in /data. Every value keeps its provenance."""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@dataclass(frozen=True)
class Rate:
    key: str
    market: str
    value: float | None
    unit: str
    status: str  # verified | secondary | assumption | unknown
    source_url: str
    snapshot_date: str
    note: str

    def provenance(self) -> dict:
        return {
            "key": self.key,
            "market": self.market,
            "value": self.value,
            "unit": self.unit,
            "status": self.status,
            "source_url": self.source_url or None,
            "snapshot_date": self.snapshot_date,
            "note": self.note,
        }


class MissingRate(LookupError):
    """Raised when a figure has no sourced row. The agent must abstain, never invent."""


@lru_cache
def rates() -> dict[tuple[str, str], Rate]:
    out: dict[tuple[str, str], Rate] = {}
    with open(DATA_DIR / "rates.csv", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            value = float(row["value"]) if row["value"].strip() else None
            r = Rate(
                key=row["key"],
                market=row["market"],
                value=value,
                unit=row["unit"],
                status=row["status"],
                source_url=row["source_url"],
                snapshot_date=row["snapshot_date"],
                note=row["note"],
            )
            out[(r.key, r.market)] = r
    return out


def rate(key: str, market: str) -> Rate:
    table = rates()
    r = table.get((key, market)) or table.get((key, "ALL"))
    if r is None or r.value is None:
        raise MissingRate(f"No sourced value for {key!r} in market {market!r}")
    return r


@lru_cache
def hs_tree() -> dict:
    return json.loads((DATA_DIR / "hs_tree.json").read_text(encoding="utf-8"))


@lru_cache
def compliance_rules() -> dict:
    return json.loads((DATA_DIR / "compliance.json").read_text(encoding="utf-8"))
