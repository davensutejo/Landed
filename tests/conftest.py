import sys
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# FX moves with every `scripts/refresh_fx.py`. The tests assert exact prices, so they run on pinned FX.
PINNED_FX = {"fx_cny_per_eur": 7.4485, "fx_cny_per_usd": 6.6713, "fx_horizon_sd": 0.027}


@pytest.fixture(autouse=True)
def pinned_fx(monkeypatch):
    from landed import data

    real = data.rate

    def rate(key, market):
        r = real(key, market)
        return replace(r, value=PINNED_FX[key]) if key in PINNED_FX else r

    monkeypatch.setattr(data, "rate", rate)
