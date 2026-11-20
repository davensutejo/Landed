"""Catalogue audit: CSV in, ranked verdicts out, every figure equal to a single engine call."""
import pytest
from fastapi.testclient import TestClient

from api.main import app
from landed import catalog, engine

SHEET = """商品名称,成本,重量,售价,市场,月销量,备注
棉袜5双装,¥12,250g,8.99,德国,300,x
便携榨汁杯,38元,0.6,29.99,DE,120,
电动滑板车,900,14,399,DE,5,
坏行,abc,0.2,9.99,DE,,
蓝牙耳机,30,0.1,,DE,,
巴西货,10,0.1,9.99,Brazil,,
"""


def _by_name(res):
    return {r["name"]: r for r in res["rows"]}


def test_rows_match_single_engine_calls():
    rows = _by_name(catalog.audit(SHEET))
    socks = rows["棉袜5双装"]
    x = engine.Inputs(market="DE", cogs_cny=12, weight_kg=0.25, target_margin=0.25, paths=catalog.AUDIT_PATHS)
    check = engine.price_check(x, 8.99)
    assert socks["verdict"] == "loses_money" and socks["profit_per_unit"] == check["profit_per_unit"]
    assert socks["target_price"] == engine.landed_cost(x)["waterfall"]["price"]
    assert socks["monthly_profit"] == round(check["profit_per_unit"] * 300, 2)
    assert [a["kind"] for a in socks["actions"]][:1] == ["raise_price"]


def test_every_kind_of_row_gets_its_own_verdict_and_the_worst_come_first():
    res = catalog.audit(SHEET)
    rows = _by_name(res)
    assert rows["便携榨汁杯"]["verdict"] == "on_target"
    assert rows["电动滑板车"]["verdict"] == "not_priced"        # above the EUR 150 flat-duty ceiling
    assert rows["坏行"]["verdict"] == "error" and "not a number" in rows["坏行"]["error"]
    assert rows["蓝牙耳机"]["verdict"] == "no_price" and rows["蓝牙耳机"]["target_price"] > 0
    assert rows["巴西货"]["verdict"] == "error" and "not covered" in rows["巴西货"]["error"]
    order = [r["verdict"] for r in res["rows"]]
    assert order == sorted(order, key=catalog.ORDER.index)
    assert res["summary"]["columns_ignored"] == ["备注"]


@pytest.mark.parametrize("raw,field,want", [
    ("¥38", "cogs_cny", 38), ("38元", "cogs_cny", 38), ("1,299.00", "cogs_cny", 1299), ("1.299,00", "cogs_cny", 1299),
    ("12,5", "cogs_cny", 12.5), ("1,299", "cogs_cny", 1299), ("600g", "weight_kg", 0.6), ("600 g", "weight_kg", 0.6),
    ("0.6kg", "weight_kg", 0.6), ("1,2", "weight_kg", 1.2), ("600", "weight_g", 0.6), ("25%", "target_margin", 0.25),
    ("25", "target_margin", 0.25), ("0.25", "target_margin", 0.25), ("€8.99", "list_price", 8.99),
])
def test_parse_number(raw, field, want):
    assert catalog.parse_number(raw, field) == pytest.approx(want)


@pytest.mark.parametrize("raw", ["abc", "", "1e400", "nan", "--3", "3..5"])
def test_parse_number_rejects(raw):
    with pytest.raises(catalog.RowError):
        catalog.parse_number(raw, "cogs_cny")


def test_semicolon_sheet_with_english_headers_and_defaults():
    sheet = "Product;Unit cost;Weight (g);Price\nMug;20;400;14,99\n"
    res = catalog.audit(sheet, {"market": "FR", "target_margin": 0.3})
    row = res["rows"][0]
    assert row["market"] == "FR" and row["target_margin"] == 0.3 and row["weight_kg"] == 0.4 and row["list_price"] == 14.99


def test_price_in_cny_is_refused_not_misread():
    res = catalog.audit("cost,weight,price\n12,0.2,¥30\n")
    assert res["rows"][0]["verdict"] == "error" and "must be in EUR" in res["rows"][0]["error"]


def test_us_row_without_code_is_a_floor():
    res = catalog.audit("cost,weight,price,market\n38,0.6,24.99,US\n")
    assert res["rows"][0]["us_lower_bound"] is True and res["rows"][0]["currency"] == "USD"


@pytest.mark.parametrize("sheet,msg", [
    ("", "empty"), ("name,weight\nx,1\n", "unit-cost column"), ("cost,price\n1,2\n", "weight column"),
])
def test_unreadable_files_fail_whole(sheet, msg):
    with pytest.raises(engine.EngineError, match=msg):
        catalog.audit(sheet)


def test_row_limit():
    with pytest.raises(engine.EngineError, match="At most"):
        catalog.audit("cost,weight\n" + "1,1\n" * (catalog.MAX_ROWS + 1))


def test_api_audit_uses_profile_defaults():
    c = TestClient(app)
    r = c.post("/api/audit", json={"csv": "cost,weight,price\n38,0.6,29.99\n", "profile": {"market": "PL", "target_margin": 0.2}})
    assert r.status_code == 200
    row = r.json()["rows"][0]
    assert row["market"] == "PL" and row["target_margin"] == 0.2
    assert c.post("/api/audit", json={"csv": "name\nx\n"}).status_code == 422


# --- regressions from the Haiku bug hunt (20 Nov 2026), one per confirmed bug ---

def _one(sheet, defaults=None):
    return catalog.audit(sheet, defaults)["rows"][0]


def test_unquoted_comma_in_a_name_is_refused_not_shifted():
    row = _one("name,cost,weight\nPack, 2,12.5,0.3\n")
    assert row["verdict"] == "error" and "double quotes" in row["error"]
    assert _one('name,cost,weight\n"Pack, 2",12.5,0.3\n')["cogs_cny"] == 12.5
    assert _one("name,cost,weight,\nCup,12,0.3,\n")["verdict"] != "error"  # trailing empty cells are fine


@pytest.mark.parametrize("raw,field,want", [
    ("0,250 kg", "weight_kg", 0.25), ("0,250kg", "weight_kg", 0.25), ("1,250", "weight_kg", 1.25),
    ("1kg", "weight_g", 1.0), ("0,250", "cogs_cny", 0.25), ("1.200", "monthly_units", 1200),
    ("1 299", "cogs_cny", 1299), ("1 299", "cogs_cny", 1299),
])
def test_number_formats_from_the_bug_hunt(raw, field, want):
    assert catalog.parse_number(raw, field) == pytest.approx(want)


@pytest.mark.parametrize("raw,field", [("250", "weight_kg"), ("1,2,3", "cogs_cny"), ("1.2,3.4", "cogs_cny"),
                                       ("1.5", "monthly_units"), ("1" + "0" * 307, "monthly_units")])
def test_numbers_that_must_be_refused(raw, field):
    with pytest.raises(catalog.RowError):
        catalog.parse_number(raw, field)


def test_a_bad_number_fails_its_row_not_the_file():
    res = catalog.audit('name,cost,weight\nCup,"1,2,3",0.3\nMug,20,0.4\n')
    assert [r["verdict"] for r in res["rows"]].count("error") == 1 and len(res["rows"]) == 2


@pytest.mark.parametrize("price,market", [("$24.99", "DE"), ("12块", "DE"), ("30人民币", "FR"), ("€24.99", "US")])
def test_price_in_the_wrong_currency_is_refused(price, market):
    row = _one(f"cost,weight,price,market\n38,0.6,{price},{market}\n")
    assert row["verdict"] == "error" and "must be in" in row["error"]


@pytest.mark.parametrize("header,field", [
    ("Cost (¥)", "cogs_cny"), ("Weight(kg)", "weight_kg"), ("重量（克）", "weight_g"), ("售价(€)", "list_price"),
    ("Price (EUR)", "list_price"), ("毛重(kg)", "weight_kg"), ("Cost/unit", "cogs_cny"), ("cost price", "cogs_cny"),
    ("成本价", "cogs_cny"), ("目标毛利率", "target_margin"), ("Weight (g)", "weight_g"), ("cogs_cny", "cogs_cny"),
])
def test_headers_with_units_and_currencies(header, field):
    assert catalog.map_headers([header]) == {field: 0}


@pytest.mark.parametrize("header", ["毛利", "毛利率", "margin"])
def test_a_bare_margin_column_is_not_taken_as_the_target(header):
    res = catalog.audit(f"cost,weight,price,{header}\n38,0.6,29.99,10%\n", {"target_margin": 0.25})
    assert res["rows"][0]["target_margin"] == 0.25 and header in res["summary"]["columns_ignored"]


def test_us_line_with_unloaded_list_duty_is_a_floor():
    row = _one("cost,weight,price,market,hs code\n40,0.5,50,US,6109.10\n")
    assert row["us_lower_bound"] is True


def test_line_numbers_are_the_files_own():
    res = catalog.audit("name,cost,weight,price\nA,40,0.5,20\n\nB,40,0.5,20\n")
    assert {r["name"]: r["line"] for r in res["rows"]} == {"A": 2, "B": 4}


def test_monthly_totals_never_mix_currencies():
    res = catalog.audit("cost,weight,price,market,monthly units\n40,0.5,17,DE,10\n38,0.6,5,US,10\n")
    loss = res["summary"]["monthly_loss_from_losing_products"]
    assert set(loss) == {"EUR", "USD"} and all(v < 0 for v in loss.values())


def test_unreadable_csv_is_a_422_not_a_500():
    c = TestClient(app)
    r = c.post("/api/audit", json={"csv": "name,cost,weight\nx,10,1," + "a" * 140_000})
    assert r.status_code == 422 and "could not be read" in r.json()["detail"]["error"]


def test_nan_in_a_profile_is_a_422_not_a_500():
    c = TestClient(app)
    body = '{"csv": "cost,weight\n10,1\n", "profile": {"fx": NaN}}'
    r = c.post("/api/audit", content=body, headers={"Content-Type": "application/json"})
    assert r.status_code == 422
    r = c.post("/api/compliance", content='{"market": "DE", "profile": {"fx": Infinity}}',
               headers={"Content-Type": "application/json"})
    assert r.status_code == 422
