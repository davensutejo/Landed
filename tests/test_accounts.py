"""Accounts ('sign in to save') and the seller profile, against a temporary database."""
import json
from types import SimpleNamespace as NS

import pytest
from fastapi.testclient import TestClient

from api import accounts
from landed import agent


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(accounts, "DB_PATH", tmp_path / "t.sqlite3")
    accounts._attempts.clear()
    accounts.init()
    from api.main import app
    return TestClient(app)


CRED = {"email": "Seller@Example.com", "password": "correct horse", "consent": True}


def test_register_requires_consent_and_sets_http_only_cookie(client):
    assert client.post("/api/auth/register", json={**CRED, "consent": False}).status_code == 422
    r = client.post("/api/auth/register", json=CRED)
    assert r.status_code == 200 and r.json()["email"] == "seller@example.com"
    assert "httponly" in r.headers["set-cookie"].lower() and "samesite=lax" in r.headers["set-cookie"].lower()
    assert client.get("/api/me").json()["user"]["email"] == "seller@example.com"


def test_password_rules_duplicates_and_login(client):
    assert client.post("/api/auth/register", json={**CRED, "password": "short"}).status_code == 422
    assert client.post("/api/auth/register", json={**CRED, "email": "not-an-email"}).status_code == 422
    client.post("/api/auth/register", json=CRED)
    assert client.post("/api/auth/register", json=CRED).status_code == 409
    client.post("/api/auth/logout")
    assert client.get("/api/me").json()["user"] is None
    assert client.post("/api/auth/login", json={**CRED, "password": "wrong password"}).status_code == 401
    assert client.post("/api/auth/login", json={**CRED, "email": "nobody@example.com"}).status_code == 401
    assert client.post("/api/auth/login", json=CRED).status_code == 200
    # the hash is not the password
    with accounts.db() as con:
        row = con.execute("SELECT pw_hash FROM users").fetchone()
    assert b"correct horse" not in row["pw_hash"]


def test_profile_is_validated_and_follows_the_account(client):
    assert client.put("/api/profile", json={"fee_rate": 0.1}).status_code == 401
    client.post("/api/auth/register", json=CRED)
    assert client.put("/api/profile", json={"fee_rate": 0.9}).status_code == 422
    assert client.put("/api/profile", json={"market": "BR"}).status_code == 422
    ok = {"category": "apparel", "market": "DE", "target_margin": 0.3, "fee_rate": 0.12, "freight_cny_per_kg": 38}
    assert client.put("/api/profile", json=ok).status_code == 200
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json=CRED)
    assert client.get("/api/me").json()["user"]["profile"] == ok


def test_products_are_private_capped_and_deletable(client):
    assert client.get("/api/products").status_code == 401
    client.post("/api/auth/register", json=CRED)
    pid = client.post("/api/products", json={"name": "袜子", "data": {"inputs": {"cogs_cny": 12}}}).json()["id"]
    assert [p["name"] for p in client.get("/api/products").json()["products"]] == ["袜子"]
    assert client.post("/api/products", json={"name": "x", "data": {"blob": "a" * 30000}}).status_code == 413
    other = TestClient(client.app)
    other.post("/api/auth/register", json={**CRED, "email": "b@example.com"})
    assert other.get("/api/products").json()["products"] == []
    other.delete(f"/api/products/{pid}")  # someone else's id: no effect
    assert len(client.get("/api/products").json()["products"]) == 1
    client.delete(f"/api/products/{pid}")
    assert client.get("/api/products").json()["products"] == []


def test_delete_account_erases_everything(client):
    client.post("/api/auth/register", json=CRED)
    client.put("/api/profile", json={"market": "DE"})
    client.post("/api/products", json={"name": "a", "data": {}})
    assert client.delete("/api/me").status_code == 200
    with accounts.db() as con:
        assert [con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("users", "sessions", "products")] == [0, 0, 0]
    assert client.get("/api/me").json()["user"] is None


# ---------------------------------------------------------------- the profile inside the agent
def _call(i, name, args):
    return NS(id=f"c{i}", type="function", function=NS(name=name, arguments=json.dumps(args)))


class Fake:
    def __init__(self, script):
        self.script, self.seen = list(script), []
        self.chat = NS(completions=NS(create=self.create))

    def create(self, **kw):
        self.seen.append(kw)
        return NS(choices=[NS(message=self.script.pop(0))])


def run_profile(monkeypatch, script, text, profile):
    fake = Fake(script)
    monkeypatch.setattr(agent, "client", lambda: fake)
    monkeypatch.setattr(agent, "_log", lambda t: None)
    return list(agent.run([{"role": "user", "content": text}], profile=profile)), fake


def test_saved_defaults_price_with_only_cost_and_weight(monkeypatch):
    profile = {"market": "DE", "target_margin": 0.3, "fee_rate": 0.12, "freight_cny_per_kg": 30, "category": "apparel"}
    script = [
        NS(content="", tool_calls=[_call(1, "landed_cost", {"market": "DE", "cogs_cny": 12, "weight_kg": 0.25, "target_margin": 0.3})]),
        NS(content="", tool_calls=[_call(2, "compliance_flags", {"market": "DE"})]),
        NS(content="done", tool_calls=None),
    ]
    events, fake = run_profile(monkeypatch, script, "Cotton socks, ¥12, 0.25 kg", profile)
    priced = events[1]["result"]
    assert priced["waterfall"]["price"] > 0  # the guard accepted market and margin from the saved defaults
    call_args = events[0]["args"]
    assert call_args["fee_rate"] == 0.12 and call_args["freight_cny_per_kg"] == 30
    assert any(p["status"] == "seller_input" for p in priced["provenance"])
    assert events[2]["args"]["textile"] is True  # category default reaches the compliance check
    assert any("saved these defaults" in m["content"] for m in fake.seen[0]["messages"] if m["role"] == "system")


def test_seller_message_beats_saved_defaults_and_bad_profile_is_ignored(monkeypatch):
    script = [NS(content="ok", tool_calls=None)]
    _, fake = run_profile(monkeypatch, script, "Socks ¥12", {"market": "XX", "fee_rate": 9, "junk": 1})
    assert all("saved these defaults" not in m["content"] for m in fake.seen[0]["messages"])
    assert agent.clean_profile({"market": "US", "fx": -1, "target_margin": 0.25}) == {"market": "US", "target_margin": 0.25}
    assert agent.apply_profile("landed_cost", {"fee_rate": 0.2}, {"fee_rate": 0.1})["fee_rate"] == 0.2


def test_repeated_login_attempts_are_throttled(client):
    codes = [client.post("/api/auth/login", json={**CRED, "password": "wrong password"}).status_code for _ in range(32)]
    assert codes[0] == 401 and codes[-1] == 429


def test_saved_fx_rate_only_applies_to_its_own_market():
    profile = {"market": "DE", "fx": 8.1, "fee_rate": 0.1}
    de = agent.apply_profile("landed_cost", {"market": "DE"}, profile)
    us = agent.apply_profile("landed_cost", {"market": "US"}, profile)
    assert de["fx"] == 8.1 and "fx" not in us and us["fee_rate"] == 0.1


def _req(xff=None, host="10.0.0.1"):
    headers = {"x-forwarded-for": xff} if xff is not None else {}
    return NS(headers=headers, client=NS(host=host))


def test_client_ip_ignores_spoofable_forwarded_for(monkeypatch):
    # no proxy in front: the header is the client's own text, so it is ignored
    monkeypatch.setenv("TRUSTED_PROXY_HOPS", "0")
    assert accounts.client_ip(_req("1.2.3.4")) == "10.0.0.1"
    # one proxy: only the entry it appended counts, whatever the client pre-filled
    monkeypatch.setenv("TRUSTED_PROXY_HOPS", "1")
    assert accounts.client_ip(_req("6.6.6.6, 203.0.113.9")) == "203.0.113.9"
    assert accounts.client_ip(_req("203.0.113.9")) == "203.0.113.9"
    assert accounts.client_ip(_req()) == "10.0.0.1"
    monkeypatch.setenv("TRUSTED_PROXY_HOPS", "nonsense")
    assert accounts.client_ip(_req("1.2.3.4")) == "10.0.0.1"


def test_rotating_forwarded_for_does_not_bypass_chat_limit(client, monkeypatch):
    from api import main
    monkeypatch.setenv("TRUSTED_PROXY_HOPS", "0")
    main._hits.clear()
    for i in range(main.MAX_REQ):
        main._rate_limit(_req(f"9.9.9.{i}"))
    with pytest.raises(main.HTTPException):
        main._rate_limit(_req("9.9.9.250"))
    main._hits.clear()
