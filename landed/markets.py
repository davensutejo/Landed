"""EU destination countries: one table, used by the engine, agent, compliance and profile.

The EUR 3 flat duty (<= EUR 150) and the compliance rules are EU-wide, so a country only
differs by its standard VAT rate (data/rates.csv: vat_standard,<code>).
"""
from __future__ import annotations

# code -> (English, Chinese, extra English patterns). Germany first; Greece is GR (TEDB says EL).
EU_COUNTRIES: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "DE": ("Germany", "德国", ("german", "deutschland")),
    "AT": ("Austria", "奥地利", ("austria",)),
    "BE": ("Belgium", "比利时", ("belgium",)),
    "BG": ("Bulgaria", "保加利亚", ("bulgaria",)),
    "HR": ("Croatia", "克罗地亚", ("croatia",)),
    "CY": ("Cyprus", "塞浦路斯", ("cyprus",)),
    "CZ": ("Czechia", "捷克", ("czech",)),
    "DK": ("Denmark", "丹麦", ("denmark",)),
    "EE": ("Estonia", "爱沙尼亚", ("estonia",)),
    "FI": ("Finland", "芬兰", ("finland",)),
    "FR": ("France", "法国", ("france",)),
    "GR": ("Greece", "希腊", ("greece",)),
    "HU": ("Hungary", "匈牙利", ("hungary",)),
    "IE": ("Ireland", "爱尔兰", ("ireland",)),
    "IT": ("Italy", "意大利", ("italy",)),
    "LV": ("Latvia", "拉脱维亚", ("latvia",)),
    "LT": ("Lithuania", "立陶宛", ("lithuania",)),
    "LU": ("Luxembourg", "卢森堡", ("luxembourg",)),
    "MT": ("Malta", "马耳他", ("malta",)),
    "NL": ("Netherlands", "荷兰", ("netherlands", "holland")),
    "PL": ("Poland", "波兰", ("poland",)),
    "PT": ("Portugal", "葡萄牙", ("portugal",)),
    "RO": ("Romania", "罗马尼亚", ("romania",)),
    "SK": ("Slovakia", "斯洛伐克", ("slovakia",)),
    "SI": ("Slovenia", "斯洛文尼亚", ("slovenia",)),
    "ES": ("Spain", "西班牙", ("spain",)),
    "SE": ("Sweden", "瑞典", ("sweden",)),
}


# The language a marketplace listing is written in. Belgium is Dutch- and French-speaking; the agent
# writes Dutch unless the seller says otherwise. Switzerland-style cases do not arise (EU only).
LISTING_LANGUAGE = {
    "DE": "German", "AT": "German", "BE": "Dutch (or French if the seller targets Wallonia)", "BG": "Bulgarian",
    "HR": "Croatian", "CY": "Greek", "CZ": "Czech", "DK": "Danish", "EE": "Estonian", "FI": "Finnish",
    "FR": "French", "GR": "Greek", "HU": "Hungarian", "IE": "English", "IT": "Italian", "LV": "Latvian",
    "LT": "Lithuanian", "LU": "French", "MT": "English", "NL": "Dutch", "PL": "Polish", "PT": "Portuguese",
    "RO": "Romanian", "SK": "Slovak", "SI": "Slovene", "ES": "Spanish", "SE": "Swedish", "US": "English",
}


def listing_language(market: str) -> str:
    return LISTING_LANGUAGE.get(market, "English")


def listing_language_rule() -> str:
    """One line for the system prompt: which language each market's listing is written in."""
    return "; ".join(f"{m} {lang}" for m, lang in LISTING_LANGUAGE.items())


def is_eu(market: str) -> bool:
    return market in EU_COUNTRIES


def name(market: str, lang: str = "en") -> str:
    if market == "US":
        return "美国" if lang == "zh" else "United States"
    en, zh, _ = EU_COUNTRIES[market]
    return zh if lang == "zh" else en
