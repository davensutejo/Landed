"""Post-check: every money figure or percentage in the final answer must appear in a
tool result or in the seller's own messages. Anything else is flagged as unverified.
Product specs with units (W, ml, mAh…) must come from the seller's messages, and
certifications or properties stated as facts (CE-certified, BPA-free, dishwasher-safe…)
must appear in a tool result or the seller's messages.

A figure counts as verified if some sourced value rounds to it at the precision it is
written in: "47%" matches a tool's 0.4712, "€25" matches 24.98. Rounding is not invention;
a number that matches nothing at any precision is.
"""
from __future__ import annotations

import json
import re

# A written number: "1.299,00" / "1,299.00" (thousands groups) or "26,37" / "26.37".
_N = r"\d{1,3}(?:[.,]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?"
# Money with the symbol before ("€26.37") or after ("26,37 €", the German and French norm), and
# percentages written with a sign or a word ("19 %", "19 Prozent").
NUM = re.compile(
    rf"(?:€|EUR\s?|US\$|\$|USD\s?|¥|CNY\s?)\s?(?P<pre>{_N})"
    rf"|(?<![\d.,])(?P<suf>{_N})\s?(?:€|EUR\b|euros?\b|Euro\b|USD\b|\$|CNY\b|¥|元|欧元|美元|块)(?!\s?\d)"
    rf"|(?<![\d.,])(?P<pct>{_N})\s?(?:%|％|(?:Prozent|percent|per cent|pour cent|por ciento|per cento|procent)\b)",
    re.IGNORECASE,
)

# Product specs (power, capacity, battery, size). Listings invent these readily; they must
# come from the seller's own messages.
UNIT = re.compile(
    r"(\d+(?:[.,]\d+)?)\s?(mAh|Wh|kW|W|V|mL|ml|L|kg|g|cm|mm|rpm|U/min|毫升|毫安时|瓦|伏|升|千克|公斤|克)(?![A-Za-z])"
)

# Certifications and product properties stated as facts. A compliance flag is a requirement,
# not an achievement, so these must come from the seller (or appear verbatim in a tool result).
CLAIMS = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bCE[- ]?(?:zertifiziert|certified|geprüft|konform|compliant|marked|gekennzeichnet)\w*",
        r"\b\w*zertifiziert\w*",
        r"\bcertified\b",
        r"\bBPA[- ]?(?:frei|free)\b",
        r"\bRoHS[- ]?(?:konform|compliant)\b",
        r"\bTÜV\b",
        r"\bGS[- ]?(?:geprüft|Zeichen)\b",
        r"spülmaschinen(?:fest|geeignet)\w*",
        r"\bdishwasher[- ]?safe\b",
        r"\bwasserdicht\w*",
        r"\bwaterproof\b",
        r"\bIPX\d\b",
        r"\bwaschbeständig\w*",
        r"\bmaschinenwaschbar\w*",
        r"\bwashable\b",
        r"\balle[n]? Größen\b",
        r"\bone size fits all\b",
        r"\batmungsaktiv\w*",
        r"\bbreathable\b",
        r"\bhypoallergen\w*",
        r"\bantibakteriell\w*",
        r"\bantibacterial\b",
        r"\blanglebig\w*",
        r"\blong[- ]lasting\b",
        r"\bbiologisch abbaubar\w*",
        r"\bbiodegradable\b",
        r"\bumweltfreundlich\w*",
        r"\beco[- ]friendly\b",
        r"\bFDA[- ]?(?:approved|zugelassen)\b",
        # the same claims in the other EU listing languages (FR IT ES NL PL PT SV DA)
        r"\bcertifi(?:é|ée|és|ées|cado|cada|cato|cata|cati(?!on)|erad|eret|ceerd|kowan)\w*",
        r"\b(?:homologu[ée]\w*|omologat\w*|homologad\w*)",
        r"\b(?:sans|sin|senza|sem|bez|geen|utan)\s+BPA\b",
        r"\bBPA[- ]?(?:vrij|fri|libre|free|frei)\b",
        r"\b(?:lave-vaisselle|lavastoviglie|lavavajillas|vaatwasser\w*|zmywark\w*|diskmaskin\w*|opvaskemaskine\w*|lava-?loi[cç]a)\b",
        r"\b(?:étanche|imperm[ée]able|impermeabile|waterdicht|wodoodporn\w*|vattentät|vandtæt|à prova de água|resistente al agua)\b",
        r"\b(?:écologique|ecologico|ecológico|ecol[oó]gic\w*|milieuvriendelijk|ekologiczn\w*|miljövänlig|miljøvenlig|amigo do ambiente)\b",
        r"\b(?:hypoallerg[ée]nique|ipoallergenico|hipoalerg[ée]nico|hypoallergeen|hipoalergiczn\w*)\b",
        r"\b(?:antibact[ée]rien\w*|antibatteric\w*|antibacteriano\w*|antibacterieel|antybakteryjn\w*)\b",
        r"\b(?:biod[ée]gradable|biodegradabile|biologisch afbreekbaar|biodegradowaln\w*)\b",
        r"已(?:通过|获得)[^，。,\s]{0,8}认证",
        r"(?:无|不含)\s?BPA",
    )
]
# "not a certified broker" / "keine zertifizierte Zollberatung" are disclaimers, not claims.
NEGATION = re.compile(r"(?:\bnot|\bno|\bnon|\bkeine?\w*|\bnicht|\bpas|\bniet|\bgeen|\bikke|\binte|\bnão|\bnao|不是|并非|非|\bsu\b|\bsobre\b|\bsur\b|\büber\b|\bueber\b|\babout\b|\bregarding\b|\bzu\b|\bover\b)\W{0,3}(?:\w+\W+){0,1}$", re.IGNORECASE)


def _in_placeholder(text: str, pos: int) -> bool:
    """True when `pos` sits inside a [bracketed placeholder] on its own line."""
    line_start = text.rfind("\n", 0, pos) + 1
    opened = text.rfind("[", line_start, pos)
    return opened != -1 and text.find("]", opened, pos) == -1


def _strip_histograms(obj):
    if isinstance(obj, dict):
        obj = {k: v for k, v in obj.items() if k != "histogram"}
        if isinstance(obj.get("monte_carlo"), dict):
            obj = {**obj, "monte_carlo": {k: v for k, v in obj["monte_carlo"].items() if k != "histogram"}}
    return obj


def _raw_numbers(obj) -> list[float]:
    obj = _strip_histograms(obj)
    text = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False)
    return [float(m.group()) for m in re.finditer(r"-?\d+(?:\.\d+)?", text)]


def _decimals(raw: str) -> int:
    return len(raw.split(".")[1]) if "." in raw else 0


def _readings(raw: str) -> list[str]:
    """Plausible readings of a written number, normalised to a '.' decimal point.

    "1.299,00" -> 1299.00; "26,37" -> 26.37. With one separator and exactly three digits after
    it ("1,299" / "1.299") the text is ambiguous between a decimal and a thousands group, so both
    readings are returned and either may match a sourced value.
    """
    if "." in raw and "," in raw:
        dec = "." if raw.rfind(".") > raw.rfind(",") else ","
        return [raw.replace("," if dec == "." else ".", "").replace(dec, ".")]
    sep = "," if "," in raw else "." if "." in raw else None
    if sep is None:
        return [raw]
    parts = raw.split(sep)
    if len(parts) > 2:
        return [raw.replace(sep, "")]  # "1.299.000"
    out = [raw.replace(sep, ".")]
    if len(parts[1]) == 3:
        out.append(raw.replace(sep, ""))
    return out


def _matches(raw: str, pool: list[float]) -> bool:
    for r in _readings(raw):
        d = min(_decimals(r), 2)
        v = round(float(r), d)
        if any(abs(round(a, d) - v) < 1e-9 for a in pool):
            return True
    return False


def check(answer: str, tool_results: list, user_texts: list[str]) -> list[str]:
    values: list[float] = []
    for src in [*tool_results, *user_texts]:
        values.extend(_raw_numbers(src))
    as_pct = values + [v * 100 for v in values]  # ratios (0.25) may be written as 25%

    unverified = []
    for m in NUM.finditer(answer):
        is_pct = m.group("pct") is not None
        raw = m.group("pre") or m.group("suf") or m.group("pct")
        if not _matches(raw, as_pct if is_pct else values):
            unverified.append(m.group(0).strip())

    for m in UNIT.finditer(answer):
        raw = m.group(1).replace(",", ".")
        d = min(_decimals(raw), 2)
        v = round(float(raw), d)
        if not any(abs(round(a, d) - v) < 1e-9 for a in values):
            unverified.append(m.group(0).strip())

    sourced_text = "\n".join(
        t if isinstance(t, str) else json.dumps(t, ensure_ascii=False) for t in [*tool_results, *user_texts]
    ).lower()
    covered: list[tuple[int, int]] = []
    for rx in CLAIMS:
        for m in rx.finditer(answer):
            if any(s <= m.start() < e or s < m.end() <= e for s, e in covered):
                continue  # already reported as part of a longer claim
            if NEGATION.search(answer[max(0, m.start() - 24):m.start()]):
                continue
            if _in_placeholder(answer, m.start()):
                continue  # "[Spülmaschinenfest: bitte bestätigen]" asks the seller; it claims nothing
            if m.group(0).lower() not in sourced_text:
                unverified.append(m.group(0).strip())
                covered.append(m.span())
    return sorted(set(unverified))
