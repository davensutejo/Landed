"""What each onboarding answer changes, and that the front end and back end agree on the ids."""
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api import accounts
from landed import compliance, profile as pm

ROOT = Path(__file__).resolve().parent.parent


def flag_ids(niche, market="DE"):
    return {f["id"] for f in compliance.flags(market, pm.compliance_attrs({"niche": niche}))["flags"]}


def test_every_niche_triggers_the_checks_that_apply_to_it():
    assert {"textile_label_eu", "gpsr_eu"} <= flag_ids("basics")
    assert {"un3481", "ce_eu", "weee_battery_eu"} <= flag_ids("audio")
    assert {"cosmetic_eu"} <= flag_ids("skincare") and "textile_label_eu" not in flag_ids("skincare")
    assert {"toy_eu"} <= flag_ids("toys_games")
    assert {"food_contact_eu"} <= flag_ids("utensils") and "ce_eu" not in flag_ids("utensils")
    assert {"ce_eu", "food_contact_eu"} <= flag_ids("kitchen_appliance")
    assert flag_ids("decor") == {"gpsr_eu", "packaging_epr_eu"}  # every consumer product: EU responsible person + packaging registration
    assert "ce_eu" not in flag_ids("phone_acc")


def test_electrical_alias_and_us_rules():
    assert "ce_eu" in {f["id"] for f in compliance.flags("DE", {"has_electric_motor": True})["flags"]}
    assert "fcc_us" in {f["id"] for f in compliance.flags("US", {"electrical": True})["flags"]}


def test_niche_implies_category_and_unknown_values_are_dropped():
    p = pm.clean({"niche": "audio", "category": "toys", "parcel": "weird", "worries": ["fx", "fx", "nope"], "cost_band": "lt20", "platform": "temu"})
    assert p == {"niche": "audio", "category": "electronics", "cost_band": "lt20", "platform": "temu", "worries": ["fx"]}
    assert pm.compliance_attrs({"category": "apparel"}) == {"textile": True}
    assert pm.compliance_attrs({"category": "beauty"}) == {}


def test_front_end_lists_every_backend_niche_and_category():
    js = (ROOT / "src" / "agent" / "onboarding.js").read_text(encoding="utf-8")
    for niche in pm.NICHES:
        assert f"['{niche}'," in js, f"onboarding.js is missing niche {niche}"
    for cat in pm.CATEGORIES:
        assert f"['{cat}'," in js, f"onboarding.js is missing category {cat}"
    for band in pm.COST_BANDS:
        assert band in js
    from landed import platforms
    for platform in platforms.ids():
        assert f"['{platform}'," in js, f"onboarding.js is missing platform {platform}"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(accounts, "DB_PATH", tmp_path / "t.sqlite3")
    accounts._attempts.clear()
    accounts.init()
    from api.main import app
    return TestClient(app)


def test_full_profile_round_trips_through_an_account_and_bad_values_are_rejected(client):
    client.post("/api/auth/register", json={"email": "a@example.com", "password": "correct horse", "consent": True})
    full = {"niche": "skincare", "category": "beauty", "market": "DE", "platform": "temu", "parcel": "mixed",
            "cost_band": "20_60", "worries": ["returns", "compliance"], "target_margin": 0.3, "fee_rate": 0.08}
    assert client.put("/api/profile", json=full).status_code == 200
    assert client.get("/api/me").json()["user"]["profile"] == full
    for bad in ({"niche": "rockets"}, {"worries": ["fx", "boredom"]}, {"parcel": "pallet"}, {"cost_band": "huge"}, {"platform": "ebay2"}):
        assert client.put("/api/profile", json=bad).status_code == 422


def test_compliance_endpoint_uses_the_niche(client):
    r = client.post("/api/compliance", json={"market": "DE", "attributes": {"item_categories": 1}, "profile": {"niche": "toys_games"}})
    assert "toy_eu" in {f["id"] for f in r.json()["flags"]}
    r = client.post("/api/compliance", json={"market": "DE", "attributes": {"toy": False}, "profile": {"niche": "toys_games"}})
    assert "toy_eu" not in {f["id"] for f in r.json()["flags"]}  # what the agent states beats the niche default


def test_packaging_registration_applies_in_every_eu_country_not_the_us():
    from landed.markets import EU_COUNTRIES
    assert all("packaging_epr_eu" in flag_ids("decor", c) for c in EU_COUNTRIES)
    assert "packaging_epr_eu" not in flag_ids("decor", "US")
