"""ares_tools.py - smart YouTube, quick maths, unit conversions, translation requests.
Every function returns None when the text is not for it, so callers can fall through to other handlers."""
import ast, json, math, operator, re, urllib.parse

try:
    import requests
except Exception:                                    # pragma: no cover
    requests = None

_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleServices/1.0 Chrome/120 Safari/537.36",
       "Accept-Language": "en-US,en;q=0.9"}
_last = {"q": "", "ids": []}                         # last YouTube search, for "play the second one"
_ORD = {"first": 0, "1st": 0, "one": 0, "second": 1, "2nd": 1, "two": 1, "third": 2, "3rd": 2, "three": 2,
        "fourth": 3, "4th": 3, "four": 3, "fifth": 4, "5th": 4, "five": 4}


# ─────────────────────────── YouTube ───────────────────────────
def _search_ids(q: str, n: int = 6):
    if requests is None:
        return []
    try:
        r = requests.get("https://www.youtube.com/results", params={"search_query": q}, headers=_UA, timeout=6)
        ids = []
        for m in re.finditer(r'"videoId":"([\w-]{11})"', r.text):
            if m.group(1) not in ids:
                ids.append(m.group(1))
            if len(ids) >= n:
                break
        return ids
    except Exception:
        return []


def _clean(q: str) -> str:
    q = re.sub(r"\b(?:please|for me|now|on youtube|in youtube|from youtube|youtube)\b", " ", q, flags=re.I)
    return re.sub(r"\s+", " ", q).strip(" ,.!?")


def youtube_command(text: str, open_browser):
    t = (text or "").strip().rstrip(".!?")
    low = t.lower()
    if not low:
        return None
    # "play the second one" (only right after a YouTube search)
    m = re.match(r"^(?:play|open)\s+(?:the\s+)?(\w+)\s+(?:one|result|video)$", low)
    if m and _last["ids"] and m.group(1) in _ORD:
        i = _ORD[m.group(1)]
        if i < len(_last["ids"]):
            open_browser(f"https://www.youtube.com/watch?v={_last['ids'][i]}")
            return f"Playing result number {i + 1}, Boss."
        return "I only found a few results, Boss."
    if "youtube" not in low:
        return None
    # search only
    m = re.match(r"^(?:search|look up|find)\s+(?:for\s+)?(.+?)\s+(?:on|in)\s+youtube$", low) \
        or re.match(r"^(?:search|look up|find)\s+youtube\s+for\s+(.+)$", low)
    if m:
        q = _clean(m.group(1))
        _last["q"], _last["ids"] = q, _search_ids(q)
        open_browser("https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(q))
        return f"Searching YouTube for {q}, Boss. Say 'play the first one' to start one."
    # play
    m = re.match(r"^(?:open\s+youtube\s+(?:and|then)\s+)?(?:play|put on|watch)\s+(.+)$", low) \
        or re.match(r"^open\s+youtube\s+(?:and|then)\s+(?:play|search(?:\s+for)?)\s+(.+)$", low)
    if m:
        q = _clean(m.group(1))
        if not q:
            return None
        ids = _search_ids(q)
        _last["q"], _last["ids"] = q, ids
        if ids:
            open_browser(f"https://www.youtube.com/watch?v={ids[0]}")
            return f"Playing {q} on YouTube, Boss."
        open_browser("https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(q))
        return f"Couldn't pick a video directly, so I opened the YouTube results for {q}."
    if re.match(r"^open\s+youtube$", low):
        open_browser("https://www.youtube.com")
        return "Opening YouTube, Boss."
    return None


# ─────────────────────────── maths ───────────────────────────
_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.Pow: operator.pow, ast.Mod: operator.mod, ast.FloorDiv: operator.floordiv,
        ast.USub: operator.neg, ast.UAdd: operator.pos}
_FUNCS = {"sqrt": math.sqrt, "abs": abs, "round": round, "sin": math.sin, "cos": math.cos, "tan": math.tan,
          "log": math.log10, "ln": math.log}
_CONST = {"pi": math.pi, "e": math.e}


def _ev(n):
    if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
        return n.value
    if isinstance(n, ast.BinOp) and type(n.op) in _OPS:
        a, b = _ev(n.left), _ev(n.right)
        if isinstance(n.op, ast.Pow) and abs(b) > 1000:
            raise ValueError("too big")
        return _OPS[type(n.op)](a, b)
    if isinstance(n, ast.UnaryOp) and type(n.op) in _OPS:
        return _OPS[type(n.op)](_ev(n.operand))
    if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in _FUNCS and len(n.args) == 1:
        return _FUNCS[n.func.id](_ev(n.args[0]))
    if isinstance(n, ast.Name) and n.id in _CONST:
        return _CONST[n.id]
    raise ValueError("unsupported")


def _num(v) -> str:
    if isinstance(v, float):
        if v == int(v) and abs(v) < 1e15:
            return f"{int(v):,}"
        return f"{v:,.6g}" if abs(v) >= 1e6 else f"{round(v, 4):,}".rstrip("0").rstrip(".")
    return f"{v:,}"


def _calc(expr: str):
    expr = expr.replace("×", "*").replace("÷", "/").replace("^", "**").replace(",", "")
    expr = re.sub(r"(?<=\d)\s*x\s*(?=[\d(])", "*", expr)
    expr = re.sub(r"\bsquare root of\s*([\d.]+)", r"sqrt(\1)", expr)
    if not re.search(r"\d", expr) or not re.fullmatch(r"[\w\s+\-*/().%]+", expr):
        return None
    if "%" in expr:
        return None
    if not re.search(r"[+\-*/]|\bsqrt\b|\bln\b|\blog\b|\bsin\b|\bcos\b|\btan\b", expr):
        return None
    try:
        return _ev(ast.parse(expr.strip(), mode="eval").body)
    except Exception:
        return None


# ─────────────────────────── units ───────────────────────────
_LEN = {"mm": .001, "cm": .01, "m": 1, "km": 1000, "in": .0254, "inch": .0254, "inches": .0254, "ft": .3048,
        "foot": .3048, "feet": .3048, "yd": .9144, "yard": .9144, "yards": .9144, "mi": 1609.344, "mile": 1609.344,
        "miles": 1609.344, "meter": 1, "meters": 1, "metre": 1, "metres": 1, "km": 1000, "kilometer": 1000,
        "kilometers": 1000, "kilometre": 1000, "kilometres": 1000, "centimeter": .01, "centimeters": .01}
_MASS = {"mg": 1e-6, "g": .001, "gram": .001, "grams": .001, "kg": 1, "kgs": 1, "kilogram": 1, "kilograms": 1,
         "lb": .45359237, "lbs": .45359237, "pound": .45359237, "pounds": .45359237, "oz": .028349523, "ounce": .028349523,
         "ounces": .028349523}
_VOL = {"ml": .001, "l": 1, "litre": 1, "litres": 1, "liter": 1, "liters": 1, "gal": 3.78541, "gallon": 3.78541,
        "gallons": 3.78541, "cup": .236588, "cups": .236588, "floz": .0295735}
_DATA = {"b": 1, "kb": 1024, "mb": 1024 ** 2, "gb": 1024 ** 3, "tb": 1024 ** 4}
_TEMP = {"c": "c", "celsius": "c", "centigrade": "c", "f": "f", "fahrenheit": "f", "k": "k", "kelvin": "k"}
_TABLES = (_LEN, _MASS, _VOL, _DATA)


def _convert(v: float, a: str, b: str):
    a, b = a.lower().strip(), b.lower().strip()
    if a in _TEMP and b in _TEMP:
        a, b = _TEMP[a], _TEMP[b]
        c = v if a == "c" else (v - 32) * 5 / 9 if a == "f" else v - 273.15
        r = c if b == "c" else c * 9 / 5 + 32 if b == "f" else c + 273.15
        return r, {"c": "°C", "f": "°F", "k": "K"}[b]
    for tb in _TABLES:
        if a in tb and b in tb:
            return v * tb[a] / tb[b], b
    return None


def quick_answer(text: str):
    t = (text or "").strip().rstrip("?!. ").lower()
    if not t:
        return None
    t = re.sub(r"^(?:hey ares[, ]*|ares[, ]*)?(?:what(?:'s| is)|whats|calculate|compute|how much is|tell me)\s+", "", t)
    # percentages
    m = re.fullmatch(r"([\d.,]+)\s*(?:%|percent|per cent)\s+of\s+([\d.,]+)", t)
    if m:
        try:
            p, n = float(m.group(1).replace(",", "")), float(m.group(2).replace(",", ""))
            return f"{_num(p)}% of {_num(n)} is {_num(round(p * n / 100, 6))}, Boss."
        except Exception:
            return None
    # unit conversion
    m = re.fullmatch(r"(-?[\d.,]+)\s*°?\s*([a-z ]+?)\s+(?:to|in|into|as)\s+°?\s*([a-z ]+)", t)
    if m:
        try:
            v = float(m.group(1).replace(",", ""))
        except ValueError:
            return None
        res = _convert(v, m.group(2), m.group(3))
        if res:
            return f"{_num(v)} {m.group(2).strip()} is {_num(round(res[0], 4))} {res[1]}, Boss."
        return None
    # plain arithmetic
    r = _calc(t)
    if r is not None:
        return f"{_num(round(r, 8) if isinstance(r, float) else r)}, Boss."
    return None


# ─────────────────────────── translation ───────────────────────────
def translate_request(t: str):
    """'translate good morning to hindi' -> ('Hindi', 'good morning'); None otherwise."""
    m = re.match(r"^translate\s+(.+?)\s+(?:to|into)\s+([a-zA-Z]+)$", (t or "").strip().rstrip(".!?"), re.I)
    if m:
        return m.group(2).capitalize(), m.group(1).strip(" \"'")
    m = re.match(r"^how (?:do you|do i|to) say\s+(.+?)\s+in\s+([a-zA-Z]+)$", (t or "").strip().rstrip(".!?"), re.I)
    if m:
        return m.group(2).capitalize(), m.group(1).strip(" \"'")
    return None
