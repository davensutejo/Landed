"""Accounts for 'sign in to save'. Stdlib only (sqlite3, hashlib.scrypt), no new dependencies.

Guests use the whole product with their settings kept in the browser. An account adds:
settings that follow the seller across devices, and saved products. Personal data is
minimal (email, password hash, the seller's own numbers) and DELETE /api/me erases it all.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator

from landed.markets import EU_COUNTRIES
from landed import profile as pm

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("LANDED_DB", ROOT / "db" / "landed.sqlite3"))
COOKIE = "landed_session"
SESSION_DAYS = 30
MAX_PRODUCTS = 50
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}\.[^@\s]{2,}$")

router = APIRouter(prefix="/api")


@contextmanager
def db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    try:
        yield con
        con.commit()
    finally:
        con.close()


def init() -> None:
    with db() as con:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
              id INTEGER PRIMARY KEY,
              email TEXT NOT NULL UNIQUE,
              pw_salt BLOB NOT NULL,
              pw_hash BLOB NOT NULL,
              consent_at REAL NOT NULL,
              created_at REAL NOT NULL,
              profile TEXT NOT NULL DEFAULT '{}'
            );
            CREATE TABLE IF NOT EXISTS sessions (
              token_hash TEXT PRIMARY KEY,
              user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              expires_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS products (
              id INTEGER PRIMARY KEY,
              user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              name TEXT NOT NULL,
              data TEXT NOT NULL,
              created_at REAL NOT NULL
            );
            """
        )


# ------------------------------------------------------------------ passwords / sessions
def _hash(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _start_session(con: sqlite3.Connection, user_id: int, response: Response, request: Request) -> None:
    token = secrets.token_urlsafe(32)
    con.execute(
        "INSERT INTO sessions(token_hash, user_id, expires_at) VALUES (?,?,?)",
        (_token_hash(token), user_id, time.time() + SESSION_DAYS * 86400),
    )
    secure = request.headers.get("x-forwarded-proto", request.url.scheme) == "https"
    response.set_cookie(COOKIE, token, max_age=SESSION_DAYS * 86400, httponly=True, samesite="lax", secure=secure, path="/")


def current_user(request: Request) -> sqlite3.Row | None:
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    with db() as con:
        con.execute("DELETE FROM sessions WHERE expires_at < ?", (time.time(),))
        return con.execute(
            "SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token_hash = ?",
            (_token_hash(token),),
        ).fetchone()


def require_user(request: Request) -> sqlite3.Row:
    user = current_user(request)
    if user is None:
        raise HTTPException(401, "Sign in required")
    return user


# ------------------------------------------------------------------ models
class Credentials(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(min_length=8, max_length=200)
    consent: bool = False

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        v = v.strip().lower()
        if not EMAIL_RE.match(v):
            raise ValueError("invalid email")
        return v


class Profile(BaseModel):
    """What onboarding learned about the seller. Everything optional; ranges are sanity bounds."""

    category: str | None = None
    niche: str | None = None
    market: str | None = Field(default=None, pattern=r"^(" + "|".join([*EU_COUNTRIES, "US"]) + r")$")
    platform: str | None = None
    parcel: str | None = None
    cost_band: str | None = None
    worries: list[str] | None = Field(default=None, max_length=6)
    target_margin: float | None = Field(default=None, ge=0.01, le=0.7)
    fee_rate: float | None = Field(default=None, ge=0, le=0.5)
    freight_cny_per_kg: float | None = Field(default=None, gt=0, le=500)
    return_rate: float | None = Field(default=None, ge=0, le=0.5)
    fx: float | None = Field(default=None, gt=0, le=100)

    @field_validator("category")
    @classmethod
    def _category(cls, v):
        if v is not None and v not in pm.CATEGORIES:
            raise ValueError("unknown category")
        return v

    @field_validator("niche")
    @classmethod
    def _niche(cls, v):
        if v is not None and v not in pm.NICHES:
            raise ValueError("unknown niche")
        return v

    @field_validator("platform")
    @classmethod
    def _platform(cls, v):
        if v is not None and "platform" not in pm.clean({"platform": v}):
            raise ValueError("unknown platform")
        return v

    @field_validator("parcel")
    @classmethod
    def _parcel(cls, v):
        if v is not None and v not in pm.PARCELS:
            raise ValueError("unknown parcel type")
        return v

    @field_validator("cost_band")
    @classmethod
    def _band(cls, v):
        if v is not None and v not in pm.COST_BANDS:
            raise ValueError("unknown cost band")
        return v

    @field_validator("worries")
    @classmethod
    def _worries(cls, v):
        if v is not None and any(w not in pm.WORRIES for w in v):
            raise ValueError("unknown worry")
        return v

    def clean(self) -> dict:
        return pm.clean({k: v for k, v in self.model_dump().items() if v is not None})


class ProductIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    data: dict


def _validate_product_data(data: dict) -> str:
    raw = json.dumps(data, ensure_ascii=False)
    if len(raw) > 20_000:
        raise HTTPException(413, "Product data too large")
    return raw


# ------------------------------------------------------------------ guards
_attempts: dict[str, list[float]] = {}


def _throttle(request: Request, limit: int = 30, window: int = 600) -> None:
    ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "?").split(",")[0].strip()
    now = time.time()
    hits = [t for t in _attempts.get(ip, []) if now - t < window]
    if len(hits) >= limit:
        raise HTTPException(429, "Too many attempts. Please wait a few minutes.")
    hits.append(now)
    _attempts[ip] = hits


def _public(user: sqlite3.Row) -> dict:
    return {"email": user["email"], "profile": json.loads(user["profile"] or "{}")}


# ------------------------------------------------------------------ routes
@router.post("/auth/register")
def register(body: Credentials, request: Request, response: Response):
    _throttle(request)
    if not body.consent:
        raise HTTPException(422, "Consent to the privacy notice is required")
    salt = secrets.token_bytes(16)
    now = time.time()
    with db() as con:
        try:
            cur = con.execute(
                "INSERT INTO users(email, pw_salt, pw_hash, consent_at, created_at) VALUES (?,?,?,?,?)",
                (body.email, salt, _hash(body.password, salt), now, now),
            )
        except sqlite3.IntegrityError:
            raise HTTPException(409, "This email is already registered")
        _start_session(con, cur.lastrowid, response, request)
        user = con.execute("SELECT * FROM users WHERE id = ?", (cur.lastrowid,)).fetchone()
    return _public(user)


@router.post("/auth/login")
def login(body: Credentials, request: Request, response: Response):
    _throttle(request)
    with db() as con:
        user = con.execute("SELECT * FROM users WHERE email = ?", (body.email,)).fetchone()
        # Always hash, so a wrong email and a wrong password take the same time.
        salt = user["pw_salt"] if user else b"\0" * 16
        ok = hmac.compare_digest(_hash(body.password, salt), user["pw_hash"] if user else b"\0" * 32)
        if not (user and ok):
            raise HTTPException(401, "Wrong email or password")
        _start_session(con, user["id"], response, request)
    return _public(user)


@router.post("/auth/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get(COOKIE)
    if token:
        with db() as con:
            con.execute("DELETE FROM sessions WHERE token_hash = ?", (_token_hash(token),))
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
def me(request: Request):
    user = current_user(request)
    return {"user": _public(user) if user else None}


@router.put("/profile")
def save_profile(body: Profile, request: Request):
    user = require_user(request)
    with db() as con:
        con.execute("UPDATE users SET profile = ? WHERE id = ?", (json.dumps(body.clean(), ensure_ascii=False), user["id"]))
    return {"profile": body.clean()}


@router.get("/products")
def list_products(request: Request):
    user = require_user(request)
    with db() as con:
        rows = con.execute("SELECT * FROM products WHERE user_id = ? ORDER BY created_at DESC", (user["id"],)).fetchall()
    return {"products": [{"id": r["id"], "name": r["name"], "data": json.loads(r["data"]), "created_at": r["created_at"]} for r in rows]}


@router.post("/products")
def add_product(body: ProductIn, request: Request):
    user = require_user(request)
    raw = _validate_product_data(body.data)
    with db() as con:
        n = con.execute("SELECT COUNT(*) FROM products WHERE user_id = ?", (user["id"],)).fetchone()[0]
        if n >= MAX_PRODUCTS:
            raise HTTPException(422, f"You can save up to {MAX_PRODUCTS} products")
        cur = con.execute(
            "INSERT INTO products(user_id, name, data, created_at) VALUES (?,?,?,?)",
            (user["id"], body.name.strip(), raw, time.time()),
        )
    return {"id": cur.lastrowid}


@router.delete("/products/{product_id}")
def delete_product(product_id: int, request: Request):
    user = require_user(request)
    with db() as con:
        con.execute("DELETE FROM products WHERE id = ? AND user_id = ?", (product_id, user["id"]))
    return {"ok": True}


@router.delete("/me")
def delete_account(request: Request, response: Response):
    """Erase the account, its sessions, profile and saved products (PIPL: right to deletion)."""
    user = require_user(request)
    with db() as con:
        con.execute("DELETE FROM users WHERE id = ?", (user["id"],))
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}
