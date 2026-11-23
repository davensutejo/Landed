"""Landed API: streaming /api/chat, deterministic /api/calc, and the static site."""
from __future__ import annotations

import json
import time
from collections import defaultdict, deque
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

from contextlib import asynccontextmanager  # noqa: E402

from landed import agent, data, engine, fx, hs, platforms  # noqa: E402
from api import accounts  # noqa: E402


@asynccontextmanager
async def lifespan(_app: FastAPI):
    import asyncio

    # live ECB rates, daily; LANDED_LIVE_FX=0 keeps the shipped snapshot. Waits at most 5 s for the first fetch.
    await asyncio.to_thread(fx.start_refresher)
    yield


app = FastAPI(title="Landed 到岸", version="0.1.0", lifespan=lifespan)


@app.exception_handler(RequestValidationError)
async def _validation_error(request: Request, exc: RequestValidationError):
    """FastAPI echoes each bad input in its 422. A NaN or Infinity sent as a JSON number cannot be encoded back,
    which turned the 422 into a 500. Drop the echo when it is not plain JSON."""
    errors = exc.errors()
    try:
        json.dumps(jsonable_encoder(errors), allow_nan=False)
    except (TypeError, ValueError):
        errors = [{k: v for k, v in e.items() if k not in ("input", "ctx")} for e in errors]
    return JSONResponse(status_code=422, content={"detail": jsonable_encoder(errors)})
accounts.init()
app.include_router(accounts.router)

# --- simple per-IP rate limit (judges share links; protect the API key) ---
WINDOW_S, MAX_REQ = 600, 60
_hits: dict[str, deque] = defaultdict(deque)


def _rate_limit(req: Request) -> None:
    ip = accounts.client_ip(req)
    q = _hits[ip]
    now = time.time()
    while q and now - q[0] > WINDOW_S:
        q.popleft()
    if len(q) >= MAX_REQ:
        raise HTTPException(429, "Too many requests. Please wait a few minutes.")
    q.append(now)


class Msg(BaseModel):
    role: str
    content: str = Field(max_length=8000)


class ChatIn(BaseModel):
    messages: list[Msg] = Field(min_length=1, max_length=24)
    profile: accounts.Profile | None = None  # the seller's saved defaults; validated, then applied in code


class CalcIn(BaseModel):
    market: str = "DE"
    hs_code: str | None = None
    cogs_cny: float = 38
    weight_kg: float = 0.6
    target_margin: float = 0.25
    item_categories: int = 1
    fee_rate: float | None = None
    platform: str | None = Field(default=None, max_length=24)
    fee_category: str | None = Field(default=None, max_length=24)
    freight_cny_per_kg: float | None = None
    return_rate: float | None = None
    fx: float | None = None
    ad_rate: float | None = None
    payout_rate: float | None = None
    fulfilment_fee: float | None = None
    dims_cm: list[float] | None = Field(default=None, min_length=3, max_length=3)
    volumetric_divisor: float | None = None
    indicative: bool = False
    hs_assumed: bool = False


class ClassifyIn(BaseModel):
    description: str
    attributes: dict = {}


FX_KEYS = {"fx_cny_per_eur", "fx_cny_per_usd", "fx_horizon_sd"}


def snapshot_info() -> dict:
    """The oldest check date of the tables (every row except FX was checked on or after it), and the date and
    origin of the FX rates in use."""
    rows = data.rates().values()
    return {
        "snapshot": min(r.snapshot_date for r in rows if r.key not in FX_KEYS and r.snapshot_date),
        "fx": fx.status(),
    }


@app.get("/api/health")
def health():
    return {"ok": True, "rates": len(data.rates()), **snapshot_info()}


@app.post("/api/calc")
def calc(body: CalcIn):
    try:
        return engine.landed_cost(engine.Inputs(**body.model_dump(exclude_none=True)))
    except data.MissingRate as e:
        raise HTTPException(422, {"status": "abstain", "error": str(e)})
    except engine.EngineError as e:
        raise HTTPException(422, {"status": "error", "error": str(e)})


@app.post("/api/sweep")
def sweep(body: CalcIn):
    try:
        return engine.sweep(engine.Inputs(**body.model_dump(exclude_none=True)))
    except data.MissingRate as e:
        raise HTTPException(422, {"status": "abstain", "error": str(e)})
    except engine.EngineError as e:
        raise HTTPException(422, {"status": "error", "error": str(e)})


class PriceIn(CalcIn):
    # Range checks live in the engine: a pydantic gt/le error would echo NaN/inf into a 422 that can't be JSON-encoded.
    list_price: float | None = Field(default=None, strict=True)  # strict: `true` is not a price of 1


def _engine_call(fn, *args):
    try:
        return fn(*args)
    except data.MissingRate as e:
        raise HTTPException(422, {"status": "abstain", "error": str(e)})
    except engine.EngineError as e:
        raise HTTPException(422, {"status": "error", "error": str(e)})


@app.post("/api/price-check")
def price_check(body: PriceIn):
    if body.list_price is None:
        raise HTTPException(422, {"status": "error", "error": "list_price is required"})
    return _engine_call(engine.price_check, engine.Inputs(**body.model_dump(exclude_none=True, exclude={"list_price"})), body.list_price)


@app.post("/api/compare-eu")
def compare_eu(body: PriceIn):
    return _engine_call(engine.compare_eu, engine.Inputs(**body.model_dump(exclude_none=True, exclude={"list_price"})), body.list_price)


@app.post("/api/classify")
def classify(body: ClassifyIn):
    return hs.classify(body.description, body.attributes)


class ComplianceIn(BaseModel):
    market: str = "DE"
    attributes: dict = {}
    profile: accounts.Profile | None = None  # the seller's niche settles attributes the agent did not state


@app.post("/api/compliance")
def compliance_flags(body: ComplianceIn):
    from landed import compliance

    from landed import profile as pm

    attrs = {**(pm.compliance_attrs(body.profile.clean()) if body.profile else {}), **body.attributes}
    return compliance.flags(body.market, attrs)


@app.get("/api/platforms")
def platform_list(market: str = "DE", category: str | None = None):
    if market not in engine.MARKETS:
        raise HTTPException(422, "unknown market")
    return {"market": market, "snapshot_date": platforms.table()["snapshot_date"], "platforms": platforms.listing(market, category)}


@app.get("/api/sources")
def sources():
    return [r.provenance() for r in data.rates().values()]


def _friendly(e: Exception) -> str:
    """Never show raw provider errors (they can name the account or key). Calculator still works."""
    code = getattr(e, "status_code", None)
    if code in (401, 403):
        return "The language model rejected our key, so chat is unavailable. The calculator still works."
    if code in (402, 429):
        return "The language model is out of quota or rate-limited right now, so chat is unavailable. The calculator still works; try chat again in a minute."
    if isinstance(e, RuntimeError) and "LLM_API_KEY" in str(e):
        return "Chat is not configured on this server (no model key). The calculator still works."
    return "Chat hit an error. The calculator still works; please try again."


@app.post("/api/chat")
def chat(body: ChatIn, request: Request):
    try:
        _rate_limit(request)
    except HTTPException:
        msg = {"type": "error", "code": "rate_limited", "message": "Too many messages in a short time."}
        return StreamingResponse(iter([f"data: {json.dumps(msg)}\n\n"]), media_type="text/event-stream")
    history = [m.model_dump() for m in body.messages]
    profile = body.profile.clean() if body.profile else None

    def stream():
        try:
            for ev in agent.run(history, profile=profile):
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
        except Exception as e:  # surface failures to the UI instead of hanging
            yield f"data: {json.dumps({'type': 'error', 'message': _friendly(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# Serve the built landing page (npm run build -> dist/) from the same origin.
DIST = ROOT / "dist"


@app.get("/agent", include_in_schema=False)
def agent_page():
    page = DIST / "agent.html"
    if not page.exists():
        raise HTTPException(404, "Run `npm run build` first.")
    return FileResponse(page)


if DIST.exists():
    app.mount("/", StaticFiles(directory=DIST, html=True), name="site")
