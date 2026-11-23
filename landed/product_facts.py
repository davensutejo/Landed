"""Product facts for the compliance check, read from the seller's own words in code.

The model was asked to pass `battery_builtin`, `food_contact` and the rest to compliance_flags, and it did
not always do it: "portable blender with built-in battery" once came back with no battery flag and no
food-contact flag, so the seller's must-do list left out the two rules that block that product. A missed
blocker is worse than a wrong price, so these facts are read here, like the fee, FX and freight the seller
states (agent.stated_overrides), and they win over what the model passed.

Only facts that the words make certain are set: "rechargeable" means a battery, "socks" means a textile.
A negation ("no battery", "battery not included", "不含电池", "not a toy") sets the fact to False, and so does
a "no" in the input form. Anything unclear is left out for the model to judge.
"""
from __future__ import annotations

import re

_I = re.IGNORECASE

# attribute -> patterns whose match makes the attribute true for the product
POSITIVE: dict[str, list[re.Pattern]] = {
    "battery_builtin": [re.compile(p, _I) for p in (
        r"built[- ]?in (?:lithium |li-?ion |rechargeable )?batter(?:y|ies)",
        r"\bwith (?:a |its own )?(?:lithium |li-?ion |rechargeable )?batter(?:y|ies)\b",
        r"\brechargeable\b", r"\bcordless\b", r"\blithium\b", r"\bli-?ion\b", r"\bli-?po\b", r"\d\s*mah\b",
        r"\bpower ?banks?\b", r"\be-?scooters?\b", r"\belectric (?:scooter|bike|bicycle)s?\b", r"\be-?bikes?\b",
        r"电动(?:滑板车|自行车|车)", r"\b(?:wireless|bluetooth) (?:earbuds|earphones|headphones)\b", r"\bearbuds?\b",
        r"内置(?:锂)?电池", r"带(?:锂)?电池", r"锂电", r"可充电", r"充电(?!器|线|头|插)", r"充电宝", r"移动电源",
        r"无线(?:蓝牙)?耳机", r"蓝牙耳机",
    )],
    "food_contact": [re.compile(p, _I) for p in (
        r"\bblenders?\b", r"\bjuicers?\b", r"\bsmoothie", r"\bfood processors?\b", r"\b(?:food|vegetable|onion|garlic) choppers?\b",
        r"\b(?:coffee|spice|pepper|salt|meat) grinders?\b", r"\bjars?\b", r"\bjugs?\b", r"\belectric kettles?\b", r"\bkettles?\b",
        r"\bteapots?\b", r"\bcoffee (?:maker|cup|mug)s?\b", r"\bmugs?\b", r"(?<!suction )\bcups?\b(?!\s*holders?)", r"\btumblers?\b",
        r"\b(?:water|drinking|sports|baby|insulated|vacuum|glass) bottles?\b", r"\blunch ?box(?:es)?\b", r"\bbento\b",
        r"\bfood (?:containers?|storage)\b", r"\b(?:cutting|chopping) boards?\b", r"\butensils?\b", r"\bspatulas?\b",
        r"\bladles?\b", r"\bcutlery\b", r"\bchopsticks\b", r"\bkitchen knives\b", r"\bkitchen knife\b", r"\bbakeware\b",
        r"\bbaking (?:tray|mould|mold|pan|sheet)s?\b", r"\b(?:frying |sauce)pans?\b", r"\bwoks?\b", r"\bcookware\b",
        r"\b(?:dinner|salad|soup|rice|serving) (?:plates?|bowls?)\b", r"\bdrinking straws?\b", r"\bstraws?\b",
        r"榨汁", r"搅拌(?:机|杯|器)", r"料理机", r"破壁机", r"水杯", r"杯子", r"保温杯", r"咖啡杯", r"马克杯", r"随行杯",
        r"水壶", r"水瓶", r"饭盒", r"便当", r"餐具", r"筷子", r"勺子", r"碗", r"餐盘", r"盘子", r"锅", r"砧板", r"菜板",
        r"吸管", r"奶瓶", r"保鲜盒", r"烘焙",
    )],
    "electrical": [re.compile(p, _I) for p in (
        r"\belectric(?:al)?\b", r"\busb\b", r"\bleds?\b", r"\bchargers?\b", r"\bplug-?in\b", r"\b\d+(?:\.\d+)?\s*w(?:att)?s?\b",
        r"\b\d+(?:\.\d+)?\s*v(?:olts?)?\b", r"\bmotor", r"\bblenders?\b", r"\bjuicers?\b", r"\bfood processors?\b",
        r"\bsmoothie (?:machine|maker)s?\b",
        r"\bhair ?dryers?\b", r"\bstraighteners?\b", r"\bcurling (?:iron|wand)s?\b", r"\bfans?\b", r"\blamps?\b",
        r"\bheadphones?\b", r"\bearphones?\b", r"\bspeakers?\b", r"\bbluetooth\b", r"\bsmart ?watch", r"\bmassage gun",
        r"\bvacuum cleaner", r"\belectric toothbrush",
        r"电动", r"电器", r"USB", r"LED", r"插电", r"蓝牙", r"耳机", r"音箱", r"台灯", r"风扇", r"吹风机", r"榨汁机",
        r"搅拌机", r"料理机", r"破壁机", r"榨汁杯", r"电热水壶", r"电机", r"马达", r"充电器",
    )],
    "textile": [re.compile(p, _I) for p in (
        r"\bsocks?\b", r"\bt-?shirts?\b", r"\btees?\b", r"\bshirts?\b", r"\bhoodies?\b", r"\bsweaters?\b", r"\bsweatshirts?\b",
        r"\bdress(?:es)?\b", r"\bskirts?\b", r"\bjeans\b", r"\btrousers\b", r"\bpants\b", r"\bleggings\b", r"\bjackets?\b",
        r"\bcoats?\b", r"\bunderwear\b", r"\bbras?\b", r"\bpaj?jamas?\b", r"\bscarf\b", r"\bscarves\b", r"\btowels?\b",
        r"\bbed ?sheets?\b", r"\bbedding\b", r"\bduvet", r"\bpillow ?cases?\b", r"\bcurtains?\b", r"\bblankets?\b",
        r"\btablecloths?\b", r"\bcotton\b(?!\s*(?:swabs?|buds?|pads?|candy))", r"\bpolyester\b", r"\blinen\b", r"\bwool(?:len)?\b",
        r"袜", r"T恤", r"衬衫", r"卫衣", r"毛衣", r"连衣裙", r"裙", r"裤", r"外套", r"夹克", r"内衣", r"睡衣", r"围巾",
        r"毛巾", r"床单", r"被套", r"枕套", r"窗帘", r"毯子", r"纯棉", r"全棉", r"棉质", r"涤纶",
    )],
    "toy": [re.compile(p, _I) for p in (
        r"(?<!dog )(?<!cat )(?<!pet )\btoys?\b", r"\bplush", r"\bstuffed animals?\b", r"\bjigsaw", r"\bpuzzles?\b",
        r"\bbuilding blocks?\b", r"\bdolls?\b", r"\baction figures?\b", r"\bfidget", r"\b(?:rc|remote[- ]control) cars?\b",
        r"(?<!宠物)玩具", r"毛绒", r"积木", r"拼图", r"娃娃", r"手办",
    )],
    "cosmetic": [re.compile(p, _I) for p in (
        r"\bskin ?care\b", r"\bserums?\b", r"\bface cream", r"\bmoisturi[sz]er", r"\blotions?\b", r"\bsunscreen",
        r"\blipsticks?\b", r"\blip ?gloss", r"\bmascara", r"\beyeliner", r"\bmakeup\b(?!\s*(?:brush|bag|mirror|organi[sz]er|sponge|case))",
        r"\bnail polish", r"\bperfume", r"\bshampoo", r"\b(?<!air )conditioner\b", r"\bbody wash", r"\bsoap\b(?!\s*(?:dispenser|dish|holder))",
        r"\bcosmetics?\b(?!\s*(?:bag|case|mirror|brush|organi[sz]er|pouch))",
        r"护肤", r"精华", r"面霜", r"乳液", r"防晒", r"口红", r"唇膏", r"睫毛膏", r"眼线", r"化妆品", r"指甲油", r"香水",
        r"洗发水", r"护发素", r"沐浴露",
    )],
}

# A negation just before the match: "no battery", "without a lithium battery", "non-rechargeable", "不含电池".
_NEG_BEFORE = re.compile(
    r"(?:\b(?:no|not|without|non|free of|excluding|isn'?t)\b[\s-]*(?:\w+[\s-]+){0,2}|(?:不含|不带|不是|没有|不|无|非)\s*)$",
    _I,
)
# "manual juicer" still touches food; it only rules out the electrical part.
_MANUAL_BEFORE = re.compile(r"(?:\b(?:manual|hand-?operated|non-electric)\b[\s-]*(?:\w+[\s-]+){0,1}|手动|手摇)$", _I)
# A negation just after it: "battery not included", "batteries sold separately", "电池另购".
_NEG_AFTER = re.compile(r"^\s*(?:not included|sold separately|excluded|另购|不含|除外)", _I)

# The input form posts its yes/no answers as text (src/lib/askWidgets.js FIELD_DEF): "Built-in lithium battery? no".
FORM_ANSWER = {
    "battery_builtin": re.compile(r"(?:Built-in lithium battery\?|是否内置锂电池？)\s*(yes|no|是|否)", _I),
    "food_contact": re.compile(r"(?:Touches food or drink\?|是否接触食品或饮料？)\s*(yes|no|是|否)", _I),
}
# Lines only the form writes. A form answer adds to the product the seller described; it is not a new product.
_FORM_LINE = re.compile(
    r"Unit cost \(CNY\):|Shipping weight \(kg\):|Built-in lithium battery\?|Touches food or drink\?|Tariff categories per parcel:"
    r"|单位成本（元）:|发货重量（kg）:|是否内置锂电池？|是否接触食品或饮料？|每个包裹的税则类别数:",
    _I,
)
_COST = re.compile(
    r"(?:¥|￥|CNY|RMB)\s*\d|\d+(?:\.\d+)?\s*(?:元|块|CNY|RMB|yuan)|\b(?:costs?|cost price|unit price)\b\D{0,12}\d|成本|进价|采购价|拿货价|出厂价",
    _I,
)


def _hits(text: str, rx: re.Pattern, attr: str) -> list[bool]:
    """For each match: True if stated, False if negated."""
    out = []
    for m in rx.finditer(text):
        before = text[max(0, m.start() - 30): m.start()]
        after = text[m.end(): m.end() + 24]
        negated = _NEG_BEFORE.search(before) or _NEG_AFTER.search(after)
        if attr == "electrical" and _MANUAL_BEFORE.search(before):
            negated = True
        out.append(not negated)
    return out


def facts_in(text: str) -> dict:
    """The attributes one text states (True) or rules out (False)."""
    out: dict = {}
    for attr, rxs in POSITIVE.items():
        hits = [h for rx in rxs for h in _hits(text, rx, attr)]
        if hits:
            # a negation of any mention wins: "blender, no battery, not rechargeable" has no battery
            out[attr] = all(hits)
    for attr, rx in FORM_ANSWER.items():
        for m in rx.finditer(text):
            out[attr] = m.group(1).lower() in ("yes", "是")
    if out.get("battery_builtin"):
        out.setdefault("electrical", True)  # a built-in battery makes it an electrical product
    return out


def _describes_product(text: str) -> bool:
    if _FORM_LINE.search(text):
        return False
    return bool(_COST.search(text)) or any(rx.search(text) for rxs in POSITIVE.values() for rx in rxs)


def current_product(seller_texts: list[str]) -> list[str]:
    """The seller's messages about the product being priced now: the latest message that describes a product
    (a cost or a product word, not a form answer) and everything after it. "What about France?" keeps the
    earlier product; "cotton socks, ¥12" starts a new one, so a blender asked about before does not carry over."""
    for i in range(len(seller_texts) - 1, -1, -1):
        if _describes_product(seller_texts[i]):
            return seller_texts[i:]
    return seller_texts


def stated(seller_texts: list[str]) -> dict:
    """Compliance attributes for the current product, later messages winning ("it has no battery after all")."""
    out: dict = {}
    for text in current_product(seller_texts):
        out.update(facts_in(text))
    return out
