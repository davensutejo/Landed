"""Post-check: every money figure or percentage in the final answer must appear in a
tool result or in the seller's own messages. Anything else is flagged as unverified.
Product specs with units (W, ml, mAh…) must come from the seller's messages, and
certifications or properties stated as facts (CE-certified, BPA-free, dishwasher-safe…)
must appear in a tool result or the seller's messages.

A figure counts as verified if some sourced value rounds to it at the precision it is
written in: "47%" matches a tool's 0.4712, "€25" matches 24.98. Rounding is not invention;
a number that matches nothing at any precision is.

That pool check ignores what a number is, so a figure written as VAT or duty ("VAT 20%", "Zoll
5 €", "关税3欧元") must also match a value the sources give as VAT or duty. Otherwise a wrong German
VAT of 20% would pass on any figure that rounds to 20, such as a 19.7% stress-test margin.
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


# Labelled facts. The pool check above strips numbers of their meaning, so "VAT 20%" passes for
# Germany whenever any figure (a 19.7% stress margin) rounds to 20. A figure written next to one of
# these labels must instead match a value sourced *as* that thing.
# Chinese labels sit outside the word boundaries: 关税为 has no boundary between 税 and 为.
LABELS = {
    "vat": re.compile(r"(?<!\w)(?:VAT|MwSt\.?|Mehrwertsteuer|Umsatzsteuer|TVA|IVA|BTW|moms)(?!\w)|增值税", re.IGNORECASE),
    "duty": re.compile(
        r"(?<!\w)(?:dut(?:y|ies)|Zoll\w*|droits? de douane|dazi[oi]?|aranceles?|derechos? de aduana|cło|cła)(?!\w)|关税",
        re.IGNORECASE,
    ),
}
_KEY_LABEL = {"vat": re.compile(r"vat", re.I), "duty": re.compile(r"duty|301", re.I)}
# A different subject between label and figure ("VAT, target price €26.37") breaks the link.
_STOP = re.compile(r"[,;!?。，；、\n)）]|\b(?:not|nicht|pas|non|no|and|und|et|or|oder|ou)\b|和|及|与|\.\s|\b(?:price|Preis|prix|prezzo|precio|cost|Kosten|fee|Gebühr|margin|Marge|profit|"
                   r"Gewinn|target|Ziel)\b|价格|售价|成本|利润|毛利", re.IGNORECASE)
# Words that may sit between a figure and a label after it ("€3 flat duty") without the figure
# being that label's value ("€26.37 incl. VAT" is a price, not a VAT amount).
_NOT_OF = {"incl", "inkl", "including", "inclusive", "excl", "exkl", "excluding", "plus", "zzgl", "ttc", "ht", "with",
           "mit", "avec", "con", "after", "before", "nach", "vor", "and", "und", "et", "y", "e", "or", "oder", "ou",
           "o", "net", "netto", "brutto", "gross", "of", "on", "auf", "sur", "su", "in", "for", "für", "pour", "para",
           "the", "a", "an", "der", "die", "das", "le", "la", "les", "il", "el", "de", "des",
           "含", "不含", "税前", "税后", "和", "及"}
# Same line only, at most two short words ("€3 EU flat duty"; Chinese, unspaced: "€3 固定关税").
_AFTER = re.compile(r"[ \t]*(?:([^\W\d]+)\.?[ \t]+)?(?:([^\W\d]+)\.?[ \t]*)?$")
_CJK = re.compile(r"[㐀-鿿]")
# A threshold next to a label is a limit, not the label's value: "duty ceiling of EUR 150", "关税：≤€150".
_LIMIT_BEFORE = re.compile(r"[<>≤≥]|\b(?:above|below|over|under|up to|exceed\w*|über|unter|bis|jusqu|au-dessus|"
                           r"en dessous|sopra|sotto|hasta|más de|menos de)\b|超过|低于|以下|以上|不超过", re.IGNORECASE)
_LIMIT_AFTER = re.compile(r"\s?(?:\w+\s)?(?:ceiling|threshold|limit|cap|Grenze|Schwelle|seuil|soglia|umbral)\b|^\s?的?(?:上限|门槛|起征点)",
                          re.IGNORECASE)


def _label_of(text: str, start: int, end: int, before: int = 20, loose: bool = False) -> str | None:
    """The label a figure at text[start:end] is written as, if any (the nearer one wins).

    `loose` (for sourced text only, where a wider reading can only accept more) also links a label
    up to 24 characters after the figure across any words: "12.5% Section 301 duty".
    """
    best: tuple[int, str] | None = None
    if _LIMIT_BEFORE.search(text[max(0, start - 12):start]) or re.match(r"\s?(?:以下|以上|以内)", text[end:]):
        return None
    for name, rx in LABELS.items():
        window = text[max(0, start - before):start]
        hits = list(rx.finditer(window))
        if hits:
            gap = window[hits[-1].end():]
            if not re.search(r"\d", gap) and not _STOP.search(gap) and (best is None or len(gap) < best[0]):
                best = (len(gap), name)
        m = rx.search(text, end, end + (24 if loose else 14))
        if m:
            gap = text[end:m.start()]
            w = _AFTER.fullmatch(gap)
            words = [x for x in (w.groups() if w else ()) if x]
            fine = w is not None and all(x.lower() not in _NOT_OF and not (_CJK.search(x) and len(x) > 2) for x in words)
            if loose and not fine:
                fine = not _STOP.search(gap) and not re.search(r"[€$¥%]", gap)
            if fine and not _LIMIT_AFTER.match(text, m.end()) and (best is None or len(gap) < best[0]):
                best = (len(gap), name)
    return best[1] if best else None


def _labelled_values(sources: list) -> dict[str, dict[str, list[float]]]:
    """Values each source gives *as* VAT or duty, split into money amounts and percentages.

    Structured fields count as money, and as a rate too when below 1 (0.19 -> 19%). Rates named
    in a snake_case key (list_duty_7_5 -> 7.5%) and labelled prose ("VAT 17%", "EUR 3 duty") add to
    the side their written form says.
    """
    out = {k: {"money": [], "pct": []} for k in LABELS}

    def num(v) -> bool:
        return isinstance(v, (int, float)) and not isinstance(v, bool)

    def add_value(name: str, v: float) -> None:
        out[name]["money"].append(v)
        if abs(v) < 1:
            out[name]["pct"].append(v * 100)

    def walk(o) -> None:
        if isinstance(o, dict):
            for name, rx in _KEY_LABEL.items():
                if isinstance(o.get("key"), str) and rx.search(o["key"]) and num(o.get("value")):
                    add_value(name, float(o["value"]))
            for k, v in o.items():
                if k == "histogram":
                    continue
                for name, rx in _KEY_LABEL.items():
                    if rx.search(k):
                        if num(v):
                            add_value(name, float(v))
                        if re.fullmatch(r"[a-z0-9_]+", k):  # field names, not display labels
                            out[name]["pct"].extend(float(d.replace("_", ".")) for d in re.findall(r"\d+(?:_\d+)?", k))
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
        elif isinstance(o, str):
            for m in NUM.finditer(o):
                name = _label_of(o, m.start(), m.end(), before=40, loose=True)
                if name:
                    raw = m.group("pre") or m.group("suf") or m.group("pct")
                    out[name]["pct" if m.group("pct") else "money"].extend(float(r) for r in _readings(raw))

    walk(sources)
    return out


def check(answer: str, tool_results: list, user_texts: list[str]) -> list[str]:
    values: list[float] = []
    for src in [*tool_results, *user_texts]:
        values.extend(abs(v) for v in _raw_numbers(src))  # written figures carry no sign: "−7.1%" is read as 7.1
    as_pct = values + [v * 100 for v in values]  # ratios (0.25) may be written as 25%
    labelled = _labelled_values([*tool_results, *user_texts])

    unverified = []
    for m in NUM.finditer(answer):
        is_pct = m.group("pct") is not None
        raw = m.group("pre") or m.group("suf") or m.group("pct")
        if not _matches(raw, as_pct if is_pct else values):
            unverified.append(m.group(0).strip())
            continue
        name = _label_of(answer, m.start(), m.end())
        # Only judged when the sources say something about that label; otherwise the pool check stands.
        if name and (labelled[name]["money"] or labelled[name]["pct"]):
            if not _matches(raw, labelled[name]["pct" if is_pct else "money"]):
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
