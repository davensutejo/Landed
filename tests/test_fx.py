"""Live FX: the server replaces the shipped ECB snapshot in memory, only with a newer and sane rate."""
import pytest

from landed import data, fx


@pytest.fixture(autouse=True)
def fresh_table():
    data.rates.cache_clear()
    fx._status.update(live=False, error=None, checked_at=None)
    yield
    data.rates.cache_clear()  # the next test starts from the shipped snapshot again


def result(eur=7.60, usd=6.80, sd=0.03, day="2099-01-05"):
    return {"date": day, "rows": {"fx_cny_per_eur": (eur, "EUR note."), "fx_cny_per_usd": (usd, "USD note."),
                                  "fx_horizon_sd": (sd, "sd note.")}}


def test_newer_sane_rates_replace_the_snapshot_with_provenance():
    assert sorted(fx.apply(result())) == ["fx_cny_per_eur", "fx_cny_per_usd", "fx_horizon_sd"]
    r = data.rates()[("fx_cny_per_eur", "EU")]
    assert (r.value, r.snapshot_date, r.status, r.source_url) == (7.60, "2099-01-05", "verified", fx.SOURCE)
    assert "Fetched live" in r.note
    assert data.shipped_rates()[("fx_cny_per_eur", "EU")].value != 7.60  # the shipped snapshot is untouched
    assert fx.status()["date"] == "2099-01-05"


def test_an_older_or_same_day_fetch_changes_nothing():
    shipped = data.rates()[("fx_cny_per_eur", "EU")]
    assert fx.apply(result(day=shipped.snapshot_date)) == []
    assert fx.apply(result(day="2000-01-01")) == []
    assert data.rates()[("fx_cny_per_eur", "EU")] == shipped


def test_a_broken_feed_cannot_reprice_everything():
    base = data.shipped_rates()[("fx_cny_per_eur", "EU")].value
    changed = fx.apply(result(eur=base * 2, usd=float("nan")))
    assert changed == ["fx_horizon_sd"]  # the sd has no fixed anchor; the two rates were refused
    assert data.rates()[("fx_cny_per_eur", "EU")].value == base


def test_a_failed_fetch_keeps_the_last_good_value(monkeypatch):
    fx.apply(result())

    def boom(timeout):
        raise OSError("network down")

    monkeypatch.setattr(fx, "fetch", boom)
    assert fx.refresh_once() == []
    assert data.rates()[("fx_cny_per_eur", "EU")].value == 7.60
    assert "network down" in fx.status()["error"]


def test_the_engine_prices_with_the_live_rate(monkeypatch):
    from landed import engine

    # the conftest pins FX through data.rate; read the live table instead, as the server does
    monkeypatch.setattr(data, "rate", lambda k, m: data.rates().get((k, m)) or data.rates()[(k, "ALL")])
    before = engine.landed_cost(engine.Inputs(market="DE", cogs_cny=38, weight_kg=0.6))["waterfall"]["price"]
    fx.apply(result(eur=data.shipped_rates()[("fx_cny_per_eur", "EU")].value * 1.05))
    after = engine.landed_cost(engine.Inputs(market="DE", cogs_cny=38, weight_kg=0.6))["waterfall"]["price"]
    assert after < before  # more yuan per euro: the same yuan cost is fewer euros


def test_off_switch(monkeypatch):
    monkeypatch.setenv("LANDED_LIVE_FX", "0")
    assert fx.enabled() is False
    monkeypatch.setenv("LANDED_LIVE_FX", "1")
    assert fx.enabled() is True


def test_health_reports_real_dates():
    from fastapi.testclient import TestClient

    from api.main import app

    body = TestClient(app).get("/api/health").json()
    assert body["ok"] and body["snapshot"] == "2026-11-08"  # the oldest check date, not the newest row
    assert body["fx"]["date"] == data.shipped_rates()[("fx_cny_per_eur", "EU")].snapshot_date
    assert body["fx"]["live"] is False  # tests never fetch
