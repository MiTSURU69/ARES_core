"""
ARES pixel sprites, drawn in code (original art, no image files needed).
Pure Python: every function returns a 2D grid of (r, g, b, a) tuples or None.
The companion app turns those grids into Qt images.

Canvas: 32 x 36 pixels, front-facing golden Spartan with a red crest, round shield, sword.
"""

W, H = 32, 36

# ── palette ──────────────────────────────────────────────────────────
OUTLINE = (28, 16, 16, 255)
GOLD = (242, 194, 48, 255)
GOLD_HI = (255, 232, 130, 255)
GOLD_DK = (190, 132, 20, 255)
RED = (205, 52, 43, 255)
RED_DK = (140, 32, 32, 255)
RED_HI = (235, 90, 70, 255)
SKIN = (232, 160, 106, 255)
SKIN_DK = (196, 122, 78, 255)
STEEL = (214, 222, 230, 255)
STEEL_DK = (150, 162, 176, 255)
BROWN = (110, 62, 30, 255)
VISOR = (30, 20, 24, 255)

EYE_COLORS = {
    "white": (255, 255, 255, 255),
    "cyan": (110, 225, 255, 255),
    "amber": (255, 205, 70, 255),
    "red": (255, 80, 80, 255),
    "green": (120, 255, 150, 255),
    "gray": (140, 140, 150, 255),
}


# ── tiny drawing kit ─────────────────────────────────────────────────
def _blank():
    return [[None] * W for _ in range(H)]


def _px(cv, x, y, c):
    if 0 <= x < W and 0 <= y < H:
        cv[y][x] = c


def _rect(cv, x, y, w, h, c):
    for yy in range(y, y + h):
        for xx in range(x, x + w):
            _px(cv, xx, yy, c)


def _disc(cv, cx, cy, r, c):
    for yy in range(cy - r, cy + r + 1):
        for xx in range(cx - r, cx + r + 1):
            if (xx - cx) ** 2 + (yy - cy) ** 2 <= r * r + r * 0.6:
                _px(cv, xx, yy, c)


def _outline(cv):
    """Add a 1px dark outline around every filled pixel (the classic pixel-art look)."""
    marks = []
    for y in range(H):
        for x in range(W):
            if cv[y][x] is None:
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < W and 0 <= ny < H and cv[ny][nx] is not None and cv[ny][nx] != OUTLINE:
                        marks.append((x, y))
                        break
    for x, y in marks:
        cv[y][x] = OUTLINE


# ── eyes (inside the two visor windows: left x12-15, right x17-20, y9-12) ──
def _eyes(cv, kind, color):
    c = EYE_COLORS.get(color, EYE_COLORS["white"])
    L, R = 13, 18  # left-most x of each eye
    if kind == "open":
        _rect(cv, L, 10, 2, 2, c)
        _rect(cv, R, 10, 2, 2, c)
    elif kind == "blink":
        _rect(cv, L, 11, 2, 1, c)
        _rect(cv, R, 11, 2, 1, c)
    elif kind == "wide":
        _rect(cv, L, 9, 2, 3, c)
        _rect(cv, R, 9, 2, 3, c)
    elif kind == "happy":                       # ^ ^
        for x0 in (L - 1, R - 1):
            _px(cv, x0, 11, c)
            _px(cv, x0 + 1, 10, c)
            _px(cv, x0 + 2, 10, c)
            _px(cv, x0 + 3, 11, c)
    elif kind == "think":                       # looking up and to the side
        _rect(cv, L + 1, 9, 2, 2, c)
        _rect(cv, R + 1, 9, 2, 2, c)
    elif kind == "confused":                    # one small, one big
        _px(cv, L, 11, c)
        _rect(cv, R, 9, 2, 3, c)
    elif kind == "x":                           # X X
        for x0 in (L - 1, R - 1):
            _px(cv, x0, 10, c)
            _px(cv, x0 + 2, 10, c)
            _px(cv, x0 + 1, 11, c)
            _px(cv, x0, 12, c)
            _px(cv, x0 + 2, 12, c)
    elif kind == "closed":                      # sleeping
        _rect(cv, L - 1, 11, 3, 1, c)
        _rect(cv, R - 1, 11, 3, 1, c)


def make_sprite(eyes="open", color="white", legs=0):
    """
    Build one sprite frame.
    eyes: open | blink | wide | happy | think | confused | x | closed
    color: white | cyan | amber | red | green | gray
    legs: 0 = standing, 1 = left leg lifted, 2 = right leg lifted (walk cycle)
    """
    cv = _blank()

    # cape (behind everything)
    _rect(cv, 9, 16, 15, 10, RED_DK)
    _rect(cv, 10, 26, 13, 1, RED_DK)

    # legs + feet
    for side, x0 in ((1, 13), (2, 17)):
        lift = 2 if legs == side else 0
        _rect(cv, x0, 26 - lift, 3, 2, SKIN)              # thigh
        _rect(cv, x0, 28 - lift, 3, 4, GOLD)               # gold greave
        _px(cv, x0, 29 - lift, GOLD_HI)
        _px(cv, x0 + 2, 30 - lift, GOLD_DK)
        _rect(cv, x0 - 1, 32 - lift, 5, 2, RED)            # sandal
        _rect(cv, x0 - 1, 33 - lift, 5, 1, RED_DK)

    # tunic skirt
    _rect(cv, 12, 22, 9, 4, RED)
    for x in (14, 17):
        _rect(cv, x, 23, 1, 3, RED_DK)
    _rect(cv, 12, 25, 9, 1, RED_DK)

    # torso: red shirt, smaller gold breastplate, belt
    _rect(cv, 12, 16, 9, 6, RED)
    _rect(cv, 13, 16, 7, 5, GOLD)
    _rect(cv, 14, 17, 2, 2, GOLD_HI)
    _rect(cv, 19, 17, 1, 4, GOLD_DK)
    _rect(cv, 16, 18, 1, 3, GOLD_DK)
    _rect(cv, 12, 21, 9, 1, BROWN)
    _px(cv, 16, 21, GOLD)

    # pauldrons
    _rect(cv, 10, 16, 3, 3, GOLD)
    _rect(cv, 20, 16, 3, 3, GOLD)
    _px(cv, 10, 18, GOLD_DK)
    _px(cv, 22, 18, GOLD_DK)

    # sword arm (viewer's right) + sword
    _rect(cv, 22, 19, 2, 3, SKIN)
    _rect(cv, 24, 22, 3, 2, SKIN_DK)                       # fist on the hilt
    _rect(cv, 25, 9, 2, 13, STEEL)                         # blade
    _rect(cv, 26, 10, 1, 11, STEEL_DK)
    _px(cv, 25, 8, STEEL)
    _rect(cv, 23, 21, 6, 1, GOLD)                          # crossguard
    _rect(cv, 25, 24, 2, 2, BROWN)                         # grip end

    # shield (viewer's left)
    _disc(cv, 8, 22, 5, GOLD_DK)
    _disc(cv, 8, 22, 4, GOLD)
    _disc(cv, 8, 22, 2, GOLD_HI)
    _px(cv, 8, 22, RED)
    _px(cv, 7, 21, RED)

    # helmet dome + cheek guards
    _rect(cv, 11, 6, 11, 9, GOLD)
    _px(cv, 11, 6, None)
    _px(cv, 21, 6, None)
    _rect(cv, 12, 7, 2, 3, GOLD_HI)
    _rect(cv, 21, 8, 1, 7, GOLD_DK)
    _rect(cv, 11, 14, 3, 3, GOLD)
    _rect(cv, 19, 14, 3, 3, GOLD)
    _rect(cv, 14, 14, 5, 2, SKIN)                          # jaw
    _px(cv, 16, 15, SKIN_DK)

    # visor windows + nose guard
    _rect(cv, 12, 9, 9, 4, VISOR)
    _rect(cv, 16, 9, 1, 5, GOLD)
    _eyes(cv, eyes, color)

    # crest (tall red fan)
    for i, w in enumerate((3, 5, 7, 9, 11)):
        _rect(cv, 16 - w // 2, 1 + i, w, 1, RED_DK if i == 4 else RED)
    _rect(cv, 15, 1, 2, 1, RED_HI)
    _rect(cv, 14, 2, 2, 1, RED_HI)
    _rect(cv, 13, 3, 2, 1, RED_HI)

    _outline(cv)
    return cv


# ── little icons drawn above his head (not mirrored) ─────────────────
ICONS = {
    "?": ["..###.", ".#...#", ".....#", "...##.", "..#...", "......", "..#..."],
    "!": ["##", "##", "##", "##", "..", "##"],
    "z": ["####", "..#.", ".#..", "####"],
    "Z": ["#####", "...#.", "..#..", ".#...", "#####"],
    "heart": [".##.##.", "#######", "#######", ".#####.", "..###..", "...#..."],
    "spark": ["..#..", "..#..", "#####", "..#..", "..#.."],
    "drop": [".#.", "###", "###", ".#."],
}
ICON_COLORS = {
    "?": (255, 215, 90, 255),
    "!": (255, 90, 90, 255),
    "z": (200, 220, 255, 255),
    "Z": (220, 235, 255, 255),
    "heart": (255, 105, 140, 255),
    "spark": (255, 240, 150, 255),
    "drop": (110, 190, 255, 255),
}


# ── mood table: how each emotion looks and animates ──────────────────
# fd = seconds per frame. Each frame: eyes, color, legs, dy (vertical hop in sprite pixels), icon spec
MOODS = {
    "idle": dict(fd=0.55, frames=[
        dict(eyes="open", dy=0), dict(eyes="open", dy=1), dict(eyes="open", dy=0), dict(eyes="blink", dy=1)]),
    "walk": dict(fd=0.15, frames=[
        dict(eyes="open", legs=0, dy=0), dict(eyes="open", legs=1, dy=-1),
        dict(eyes="open", legs=0, dy=0), dict(eyes="open", legs=2, dy=-1)]),
    "listen": dict(fd=0.14, frames=[
        dict(eyes="wide", color="cyan", dy=0, icon="bars:0:cyan"),
        dict(eyes="wide", color="cyan", dy=0, icon="bars:1:cyan"),
        dict(eyes="wide", color="cyan", dy=-1, icon="bars:2:cyan"),
        dict(eyes="wide", color="cyan", dy=0, icon="bars:1:cyan")]),
    "dictate": dict(fd=0.14, frames=[
        dict(eyes="wide", color="green", dy=0, icon="bars:0:green"),
        dict(eyes="wide", color="green", dy=0, icon="bars:1:green"),
        dict(eyes="wide", color="green", dy=-1, icon="bars:2:green"),
        dict(eyes="wide", color="green", dy=0, icon="bars:1:green")]),
    "think": dict(fd=0.42, frames=[
        dict(eyes="think", color="amber", dy=0, icon="dots:1"),
        dict(eyes="think", color="amber", dy=0, icon="dots:2"),
        dict(eyes="think", color="amber", dy=1, icon="dots:3"),
        dict(eyes="think", color="amber", dy=0, icon="dots:2")]),
    "speak": dict(fd=0.11, frames=[
        dict(eyes="open", dy=0), dict(eyes="open", dy=-2), dict(eyes="happy", dy=-1), dict(eyes="open", dy=0)]),
    "happy": dict(fd=0.12, frames=[
        dict(eyes="happy", dy=0, icon="spark"), dict(eyes="happy", dy=-4, icon="heart"),
        dict(eyes="happy", dy=-6, icon="spark"), dict(eyes="happy", dy=-4, icon="heart"),
        dict(eyes="happy", dy=0, icon="spark")]),
    "error": dict(fd=0.30, frames=[
        dict(eyes="confused", color="red", dy=0, icon="?"),
        dict(eyes="x", color="red", dy=1, icon="drop"),
        dict(eyes="confused", color="red", dy=0, icon="?")]),
    "sleep": dict(fd=0.75, frames=[
        dict(eyes="closed", color="gray", dy=0, icon="z"),
        dict(eyes="closed", color="gray", dy=1, icon="Z"),
        dict(eyes="closed", color="gray", dy=1, icon="z")]),
}


def all_sprite_keys():
    """Every unique (eyes, color, legs) combination we need to pre-render."""
    keys = set()
    for spec in MOODS.values():
        for f in spec["frames"]:
            keys.add((f.get("eyes", "open"), f.get("color", "white"), f.get("legs", 0)))
    return sorted(keys)

# ══════════════════════════════════════════════════════════════════════
#  MORE EMOTIONS  (added)
#  Each new mood has  base = the animator pose it borrows (one of idle/walk/listen/dictate/think/speak/happy/error/sleep)
#  and  dur = seconds it lasts when it is a one-off reaction.  Eyes only use the eight kinds the 3D model already draws.
# ══════════════════════════════════════════════════════════════════════
EYE_COLORS.update({
    "pink": (255, 140, 190, 255),
    "purple": (190, 150, 255, 255),
    "orange": (255, 150, 60, 255),
    "blue": (110, 150, 255, 255),
})

ICONS.update({
    "note": ["..###", "..#.#", "..#..", "..#..", "###..", "###.."],
    "star": ["..#..", ".###.", "#####", ".###.", ".#.#."],
    "book": ["####.####", "#..#.#..#", "#.##.##.#", "#..#.#..#", "####.####"],
    "code": ["..#...#.#..", ".#...#...#.", "#....#....#", ".#..#....#.", "..#.#...#.."],
    "anger": ["#...#", ".#.#.", "..#..", ".#.#.", "#...#"],
})
ICON_COLORS.update({
    "note": (150, 220, 255, 255),
    "star": (255, 225, 90, 255),
    "book": (190, 150, 255, 255),
    "code": (120, 255, 150, 255),
    "anger": (255, 70, 70, 255),
})

MOODS["happy"]["dur"] = 2.6
MOODS["error"]["dur"] = 2.6

MOODS.update({
    "excited": dict(base="happy", dur=3.0, fd=0.13, frames=[
        dict(eyes="wide", color="orange", dy=-2, icon="star"), dict(eyes="happy", color="orange", dy=-5, icon="spark"),
        dict(eyes="wide", color="orange", dy=-2, icon="!"), dict(eyes="happy", color="orange", dy=-5, icon="star")]),
    "love": dict(base="happy", dur=3.2, fd=0.28, frames=[
        dict(eyes="happy", color="pink", dy=0, icon="heart"), dict(eyes="happy", color="pink", dy=-2, icon="heart"),
        dict(eyes="happy", color="pink", dy=0, icon="heart"), dict(eyes="blink", color="pink", dy=-1, icon="heart")]),
    "proud": dict(base="happy", dur=3.0, fd=0.3, frames=[
        dict(eyes="happy", color="amber", dy=0, icon="star"), dict(eyes="open", color="amber", dy=-1, icon="star"),
        dict(eyes="happy", color="amber", dy=0, icon="spark")]),
    "celebrate": dict(base="happy", dur=3.5, fd=0.12, frames=[
        dict(eyes="happy", color="amber", dy=-5, icon="spark"), dict(eyes="wide", color="orange", dy=-2, icon="star"),
        dict(eyes="happy", color="pink", dy=-6, icon="heart"), dict(eyes="wide", color="cyan", dy=-2, icon="note")]),
    "groove": dict(base="happy", dur=6.0, fd=0.22, frames=[
        dict(eyes="happy", color="cyan", dy=0, icon="note"), dict(eyes="closed", color="cyan", dy=-2, icon="note"),
        dict(eyes="happy", color="cyan", dy=-1, icon="note"), dict(eyes="closed", color="cyan", dy=-2, icon="note")]),
    "surprised": dict(base="happy", dur=1.8, fd=0.16, frames=[
        dict(eyes="wide", color="white", dy=-4, icon="!"), dict(eyes="wide", color="white", dy=-2, icon="!")]),
    "sad": dict(base="idle", dur=4.0, fd=0.6, frames=[
        dict(eyes="blink", color="blue", dy=1, icon="drop"), dict(eyes="closed", color="blue", dy=1, icon="drop"),
        dict(eyes="blink", color="blue", dy=1)]),
    "angry": dict(base="error", dur=3.0, fd=0.18, frames=[
        dict(eyes="wide", color="red", dy=0, icon="anger"), dict(eyes="confused", color="red", dy=-1, icon="anger")]),
    "worried": dict(base="error", dur=3.0, fd=0.3, frames=[
        dict(eyes="confused", color="amber", dy=0, icon="drop"), dict(eyes="think", color="amber", dy=1, icon="drop")]),
    "curious": dict(base="think", dur=5.0, fd=0.45, frames=[
        dict(eyes="confused", color="cyan", dy=0, icon="?"), dict(eyes="think", color="cyan", dy=0, icon="?"),
        dict(eyes="wide", color="cyan", dy=-1, icon="?")]),
    "bored": dict(base="idle", dur=6.0, fd=0.7, frames=[
        dict(eyes="open", color="gray", dy=0), dict(eyes="blink", color="gray", dy=1, icon="dots:3"),
        dict(eyes="open", color="gray", dy=0, icon="dots:2")]),
    "sleepy": dict(base="idle", dur=4.0, fd=0.8, frames=[
        dict(eyes="open", color="gray", dy=0, icon="z"), dict(eyes="blink", color="gray", dy=1, icon="z"),
        dict(eyes="closed", color="gray", dy=1, icon="Z")]),
    # working moods (stay until the answer arrives)
    "read": dict(base="think", fd=0.4, frames=[
        dict(eyes="think", color="purple", dy=0, icon="book"), dict(eyes="open", color="purple", dy=0, icon="book"),
        dict(eyes="think", color="purple", dy=1, icon="book")]),
    "code": dict(base="think", fd=0.35, frames=[
        dict(eyes="wide", color="green", dy=0, icon="code"), dict(eyes="think", color="green", dy=0, icon="code"),
        dict(eyes="wide", color="green", dy=1, icon="code")]),
})


# ══════════════════════════════════════════════════════════════════════
#  OUTFITS  (added)  — colour swaps on the existing model:  (hue in degrees, saturation x, brightness x)
#  "armor" retints everything gold (armour, greaves, shield, sword guard); "cape" retints everything red
#  (cape, crest, tunic, sandals).  None = leave as is.  Skin, steel and the eyes are never touched.
# ══════════════════════════════════════════════════════════════════════
OUTFITS = {
    "spartan": dict(label="Golden Spartan", aliases=("gold", "golden", "classic", "default", "original", "normal"),
                    armor=None, cape=None),
    "racing": dict(label="Racing Livery", aliases=("f1", "formula", "race", "red and white", "livery"),
                   armor=(0, 0.0, 1.0), cape=None),
    "steel": dict(label="Steel Knight", aliases=("silver", "knight", "iron"),
                  armor=(215, 0.12, 1.0), cape=(220, 0.75, 0.85)),
    "shadow": dict(label="Shadow Armor", aliases=("dark", "black", "night", "ninja"),
                   armor=(265, 0.35, 0.38), cape=(285, 0.9, 0.85)),
    "emerald": dict(label="Emerald Guard", aliases=("green", "forest"),
                    armor=(150, 0.85, 0.85), cape=(170, 0.85, 0.6)),
    "royal": dict(label="Royal Purple", aliases=("purple", "king", "royalty"),
                  armor=None, cape=(275, 0.85, 0.85)),
    "frost": dict(label="Frost Plate", aliases=("ice", "icy", "blue", "winter"),
                  armor=(195, 0.5, 1.0), cape=(210, 0.6, 0.95)),
    "sakura": dict(label="Sakura Blossom", aliases=("pink", "blossom", "cherry"),
                   armor=(338, 0.42, 1.0), cape=(330, 0.55, 0.9)),
}


import colorsys as _colorsys
from functools import lru_cache as _lru_cache


@_lru_cache(maxsize=8192)
def _recolor(col, outfit):
    spec = OUTFITS.get(outfit)
    if not spec:
        return col
    h, s, v = _colorsys.rgb_to_hsv(col[0] / 255.0, col[1] / 255.0, col[2] / 255.0)
    hd = h * 360.0
    if s > 0.45 and 33 <= hd <= 55:                        # gold family
        tone = spec.get("armor")
    elif s > 0.5 and (hd >= 345 or hd <= 14):              # red family
        tone = spec.get("cape")
    else:
        return col
    if not tone:
        return col
    nh, sm, vm = tone
    r, g, b = _colorsys.hsv_to_rgb((nh % 360) / 360.0, min(1.0, s * sm), min(1.0, v * vm))
    return (int(r * 255 + 0.5), int(g * 255 + 0.5), int(b * 255 + 0.5)) + tuple(col[3:])


def recolor(col, outfit, keep=None):
    """Retint one polygon colour for an outfit. `keep` = set of (r, g, b) that must stay as they are (eye colour)."""
    if outfit == "spartan" or (keep and tuple(col[:3]) in keep):
        return col
    return _recolor(tuple(col), outfit)