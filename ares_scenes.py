"""
ares_scenes.py - everything about Ares' little performances (pure logic, no Qt):

  * register(SP)      adds the extra moods (laugh, shy, salute, dance, slash ...) to ares_sprites.MOODS and upgrades the
                      body language of the old emotions (sad, angry, love, proud ...). Nothing in ares_sprites.py is edited.
  * make_scene(name)  a scripted scene = list of steps (mood, seconds, options). Options:
                        say=text   speech bubble        hit=seconds   sparks + clang        land=seconds   dust puff
                        mv=px/s    walk that way        gait=name     gait for a walking step
                        go=(x, y)  walk to a point (step ends when he gets there)
  * pick_scene()      weighted random idle antic
  * match_action()    typed / spoken phrases ("sit down", "dance", "have a sword fight" ...) -> scene | mood | stand
"""
import re
import random

_X_EYES = {"white": (255, 255, 255), "red": (255, 70, 60), "cyan": (110, 225, 255), "gold": (255, 214, 90),
           "pink": (255, 140, 190), "green": (120, 255, 150), "violet": (190, 140, 255), "orange": (255, 160, 60)}
_X_ICONS = {
    "x_note": ("..###", "..#..", "..#..", "###..", "###.."),
    "x_spark": ("...#...", "...#...", ".#.#.#.", "..###..", "#######", "..###..", ".#.#.#.", "...#...", "...#..."),
    "x_burst": ("#..#..#", ".#.#.#.", "..###..", "#######", "..###..", ".#.#.#.", "#..#..#"),
    "x_drop": ("..#..", ".###.", ".###.", "#####", "#####", ".###."),
    "x_q": (".###.", "#...#", "....#", "...#.", "..#..", ".....", "..#.."),
    "x_blush": ("#.#.#", ".#.#.", "#.#.#"),
    "x_shield": ("#####", "#####", "#####", ".###.", "..#.."),
}
_X_ICON_COLORS = {"x_note": (150, 230, 255), "x_spark": (255, 225, 90), "x_burst": (255, 170, 60), "x_drop": (120, 200, 255),
                  "x_q": (255, 255, 255), "x_blush": (255, 130, 170), "x_shield": (255, 214, 90)}


def _fr(eyes="open", color="white", icon=None):
    return {"eyes": eyes, "color": color, "icon": icon}


# name: (frames, seconds per frame, seconds it lasts as a one-off reaction (None = part of a scene / held), body pose)
_X_MOODS = {
    "laugh": ([_fr("happy", "gold", "x_drop"), _fr("happy", "gold")], 0.22, 3.6, "laugh"),
    "shy": ([_fr("happy", "pink", "x_blush")], 0.5, 3.6, "shy"),
    "confused": ([_fr("confused", "white", "x_q"), _fr("confused", "white")], 0.6, 3.6, "confused"),
    "facepalm": ([_fr("closed", "orange", "x_drop")], 0.5, 3.2, "facepalm"),
    "shrug": ([_fr("open", "white")], 0.5, 2.8, "shrug"),
    "salute": ([_fr("open", "cyan")], 0.5, 2.6, "salute"),
    "bow": ([_fr("closed", "white")], 0.5, 3.0, "bow"),
    "wave": ([_fr("happy", "gold")], 0.5, 3.2, "wave"),
    "clap": ([_fr("happy", "gold", "x_spark"), _fr("happy", "gold")], 0.18, 3.4, "clap"),
    "nod": ([_fr("open", "white")], 0.5, 2.0, "nod"),
    "shake": ([_fr("open", "white")], 0.5, 2.0, "shake"),
    "awe": ([_fr("wide", "gold", "x_spark"), _fr("wide", "gold")], 0.3, 3.4, "awe"),
    "shiver": ([_fr("wide", "cyan", "x_drop"), _fr("wide", "cyan")], 0.16, 3.0, "shiver"),
    "point": ([_fr("open", "white")], 0.5, 2.5, "point"),
    "yawn": ([_fr("closed", "white")], 0.5, 3.2, "yawn"),
    "stretch": ([_fr("closed", "white")], 0.5, 4.2, "stretch"),
    "jump": ([_fr("wide", "gold")], 0.5, 1.2, "jump"),
    # held / scripted poses used by scenes
    "sit": ([_fr("open", "white")], 0.6, None, "sit"),
    "meditate": ([_fr("closed", "cyan")], 0.6, None, "meditate"),
    "sit_look": ([_fr("open", "white")], 0.6, None, "sit_look"),
    "sit_wave": ([_fr("happy", "gold")], 0.6, None, "sit_wave"),
    "sit_bored": ([_fr("open", "white")], 0.6, None, "sit_bored"),
    "sit_read": ([_fr("open", "cyan", "book")], 0.6, None, "sit_read"),
    "lookaround": ([_fr("open", "white")], 0.6, None, "lookaround"),
    "dance": ([_fr("happy", "gold", "x_note"), _fr("open", "gold"), _fr("happy", "pink", "x_note"), _fr("open", "pink")], 0.28, None, "dance"),
    "disco": ([_fr("happy", "violet", "x_note"), _fr("wide", "cyan"), _fr("happy", "violet"), _fr("wide", "pink", "x_note")], 0.25, None, "disco"),
    "twirl": ([_fr("happy", "gold", "x_spark")], 0.3, None, "twirl"),
    "robot": ([_fr("open", "cyan"), _fr("wide", "cyan")], 0.29, None, "robot"),
    "flip": ([_fr("wide", "gold")], 0.5, None, "flip"),
    "backflip": ([_fr("wide", "gold")], 0.5, None, "backflip"),
    "flex": ([_fr("happy", "gold")], 0.5, None, "flex"),
    "cheer": ([_fr("happy", "gold", "x_spark"), _fr("wide", "gold")], 0.3, 3.4, "cheer"),
    "stance": ([_fr("open", "red")], 0.5, None, "stance"),
    "taunt": ([_fr("happy", "red")], 0.5, None, "taunt"),
    "warcry": ([_fr("wide", "red", "x_burst"), _fr("wide", "red")], 0.2, None, "warcry"),
    "slash": ([_fr("wide", "red")], 0.5, None, "slash"),
    "overhead": ([_fr("wide", "red")], 0.5, None, "overhead"),
    "thrust": ([_fr("wide", "red")], 0.5, None, "thrust"),
    "bash": ([_fr("wide", "red")], 0.5, None, "bash"),
    "spin_slash": ([_fr("wide", "red")], 0.5, None, "spin_slash"),
    "block": ([_fr("wide", "orange", "x_shield")], 0.5, None, "block"),
    "parry": ([_fr("wide", "orange")], 0.5, None, "parry"),
    "hurt": ([_fr("x", "red")], 0.5, None, "hurt"),
    "victory": ([_fr("happy", "gold", "x_spark"), _fr("happy", "gold")], 0.35, None, "victory"),
}
# older emotions keep their eyes / icons but get the richer body language from ares_3d
_UPGRADE = {"sad": "sad", "angry": "angry", "excited": "cheer", "love": "heart", "proud": "flex", "celebrate": "cheer",
            "groove": "groove", "surprised": "startle", "worried": "worry", "curious": "lookaround", "bored": "yawn"}


def register(SP, upgrade: bool = True):
    for k, v in _X_EYES.items():
        SP.EYE_COLORS.setdefault(k, v)
    for k, v in _X_ICONS.items():
        SP.ICONS.setdefault(k, v)
    for k, v in _X_ICON_COLORS.items():
        SP.ICON_COLORS.setdefault(k, v)
    for name, (frames, fd, dur, base) in _X_MOODS.items():
        if name in SP.MOODS:                                   # never clobber a mood ares_sprites.py already defines
            continue
        spec = {"frames": frames, "fd": fd, "base": base}
        if dur:
            spec["dur"] = dur
        SP.MOODS[name] = spec
    if upgrade:
        for name, base in _UPGRADE.items():
            if name in SP.MOODS:
                SP.MOODS[name] = dict(SP.MOODS[name], base=base)


# ══════════════════════════════════════════════════════════════════════
#  SCENES
# ══════════════════════════════════════════════════════════════════════
_HITS = [                     # move, length, when the blade lands, shouts
    ("slash", 0.80, 0.30, ("Hyah!", "Take that!", "Ha!")),
    ("overhead", 0.85, 0.36, ("Down you go!", "Rrah!")),
    ("thrust", 0.80, 0.30, ("Hah!", "Got you!", "Ha!")),
    ("bash", 0.75, 0.28, ("Back!", "Move!")),
    ("spin_slash", 0.95, 0.45, ("Whirlwind!", "Hyaaah!")),
]

SCENE_WEIGHTS_FLOOR = (("sit", 20), ("battle", 20), ("dance", 15), ("kata", 8), ("stretch", 7), ("look", 7), ("flip", 5),
                       ("jumps", 4), ("flex", 4), ("wave", 3), ("cursor", 5), ("meditate", 4))
SCENE_WEIGHTS_PERCHED = (("sit", 40), ("dance", 10), ("battle", 10), ("kata", 8), ("stretch", 10), ("look", 10), ("flex", 5),
                         ("wave", 6), ("meditate", 6))
GAIT_SCENES = ("run", "march", "sneak", "skip")


def pick_scene(perched: bool, cursor_far: bool = True) -> str:
    table = [(n, w) for n, w in (SCENE_WEIGHTS_PERCHED if perched else SCENE_WEIGHTS_FLOOR) if cursor_far or n != "cursor"]
    return random.choices([n for n, _ in table], weights=[w for _, w in table])[0]


def make_scene(name: str, perched: bool = False, target=None):
    """-> list of (mood, seconds, options). `target` = (x, y) for the cursor scene."""
    R, P = random.uniform, random.choice
    st = []

    def add(mood, secs, **o):
        st.append((mood, secs, o))

    if name == "moves":
        name = P(("battle", "dance", "flip", "flex", "kata", "twirl", "disco", "robot"))
    if name == "sit":
        k = 2.0 if perched else 1.0
        add("sit", R(4, 8) * k)
        for _ in range(random.randint(1, 3)):
            add(P(("sit_look", "sit", "sit_wave", "sit_bored", "sit_read", "meditate")), R(4, 9) * k)
        add("sit", 1.2)
    elif name == "meditate":
        add("meditate", R(9, 16))
    elif name == "battle":
        add("stance", 1.1, say=P(("Come on then!", "Who's next?", "Let's dance, shadows.")))
        add("taunt", 0.9)
        if not perched:
            add("walk", 0.7, mv=50, gait="guard")
        for _ in range(random.randint(3, 5)):
            mv, secs, hit, lines = P(_HITS)
            add(mv, secs, hit=hit, say=P(lines))
            r = random.random()
            if r < 0.30:
                add("block", 0.75, hit=0.10, say=P(("Not today!", "Too slow!")))
            elif r < 0.45:
                add("hurt", 0.80, say=P(("Ugh!", "Tch!", "Lucky hit.")))
            elif r < 0.60 and not perched:
                add("walk", 0.6, mv=45, gait="guard")
            add("stance", R(0.35, 0.7))
        add("warcry", 1.0, say="For glory!")
        add("victory", 2.6, say=P(("Victory!", "The shadows flee.", "Enemy defeated, Boss.")))
    elif name == "kata":
        add("stance", 0.9)
        for mv, secs, _hit, _l in (_HITS[0], _HITS[1], _HITS[2], _HITS[0]):
            add(mv, secs)
            add("stance", 0.35)
        add("salute", 1.8)
    elif name in ("dance", "disco", "robot", "twirl"):
        styles = [name] if name != "dance" else random.sample(["dance", "disco", "robot", "groove"], 2)
        add(styles[0], R(5, 8) if name != "twirl" else 2.3, say="♪")
        for extra in styles[1:]:
            add(extra, R(4, 7))
        add(P(("twirl", "cheer")), 2.3 if name == "twirl" else 1.4)
    elif name in ("flip", "backflip"):
        add(P(("flip", "backflip")) if name == "flip" else name, 1.35, land=0.95)
        add("cheer", 1.6, say=P(("Ha!", "Still got it!", "Ten out of ten.")))
    elif name == "jumps":
        for _ in range(3):
            add("jump", 0.75, land=0.6)
        add("cheer", 1.3)
    elif name == "stretch":
        add("stretch", 3.9)
        add("yawn", 3.0)
    elif name == "look":
        add("lookaround", R(4, 6.5))
    elif name == "flex":
        add("flex", R(3.5, 5), say="Still got it.")
    elif name == "wave":
        add("wave", 2.8, say=P(("Hey, Boss!", "Hello!", "Boss!")))
    elif name == "victory":
        add("warcry", 0.9, say="Victory!")
        add("victory", 3.2)
    elif name == "cursor" and target:
        add("walk", 9.0, go=target, gait="run")
        add("wave", 2.6, say="Found you, Boss!")
    else:
        add("wave", 2.6)
    return st


# ══════════════════════════════════════════════════════════════════════
#  typed / spoken commands that start a scene or a reaction
# ══════════════════════════════════════════════════════════════════════
_ACT_PRE = (r"^(?:(?:hey|ok|okay|so|now|alright)[, ]+)*(?:ares[, ]+)?(?:please[, ]+)?(?:(?:can|could|would|will) you[, ]+)?"
            r"(?:please[, ]+)?(?:go (?:ahead and )?|just |now |let'?s |lets )?")
_ACT_END = r"(?:\s+(?:for me|for us|please|now|again|a little|a bit|a while|for a while|around|up|down|there|here|high|some more|too|boss|ares))*[.!?\s]*$"
_ACT_SPECS = [                # (kind, name, pattern)   kind: scene | mood | stand
    ("stand", "stand", r"(?:stand(?: up)?|get up|get on your feet|on your feet)"),
    ("scene", "meditate", r"(?:meditate|do (?:some )?yoga)"),
    ("scene", "sit", r"(?:sit(?: down)?|take a seat|have a seat|rest|relax|chill)"),
    ("scene", "battle", r"(?:fight|battle|duel|have a (?:sword )?fight|(?:do|show) (?:some )?(?:sword ?play|sword fighting|fighting)|"
                        r"show me your (?:sword )?(?:skills|fighting)|slay (?:some )?(?:monsters|enemies))"),
    ("scene", "kata", r"(?:practi[cs]e|train|(?:do|show) (?:some )?(?:sword )?(?:practi[cs]e|training|drills|kata|forms)|sword (?:practi[cs]e|training))"),
    ("scene", "disco", r"(?:disco|(?:do )?(?:the )?disco (?:dance|moves))"),
    ("scene", "robot", r"(?:(?:do )?(?:the )?robot(?: dance)?)"),
    ("scene", "twirl", r"(?:twirl|spin(?: around)?|(?:do a )?spin)"),
    ("scene", "dance", r"(?:dance|(?:do|show me) (?:a |some )?(?:little )?dance|bust a move|boogie|shake it|dance for me)"),
    ("scene", "moves", r"(?:show me (?:your|some) moves|show me what you(?:'ve| have) got)"),
    ("scene", "backflip", r"(?:(?:do|show me) (?:a |an )?back ?flip)"),
    ("scene", "flip", r"(?:(?:do|show me) (?:a |an )?(?:front )?(?:flip|somersault)|flip|somersault)"),
    ("scene", "jumps", r"(?:jump|hop|jumping jacks|do (?:some )?jumping jacks|jump around)"),
    ("scene", "stretch", r"(?:stretch|warm up|do (?:some )?stretch(?:es|ing))"),
    ("scene", "flex", r"(?:flex|show off|show me your (?:muscles|strength))"),
    ("scene", "look", r"(?:look around)"),
    ("scene", "victory", r"(?:(?:do|strike) (?:a |your )?victory(?: pose)?|victory pose)"),
    ("scene", "cursor", r"(?:come (?:to me|here|over|over here)|(?:find|follow|chase) (?:my )?(?:cursor|mouse)|come and find me)"),
    ("scene", "run", r"(?:run around|go for a run|sprint|go for a jog|jog)"),
    ("scene", "march", r"(?:march|patrol|go on patrol)"),
    ("scene", "sneak", r"(?:sneak(?: around)?|tiptoe|creep around)"),
    ("scene", "skip", r"(?:skip around|go skipping)"),
    ("mood", "wave", r"(?:wave(?: (?:hello|hi|at me))?|say hi)"),
    ("mood", "bow", r"(?:bow|take a bow)"),
    ("mood", "salute", r"(?:salute)"),
    ("mood", "clap", r"(?:clap|applaud|give me (?:a )?(?:clap|applause))"),
    ("mood", "cheer", r"(?:cheer|celebrate|hooray|hurray)"),
    ("mood", "laugh", r"(?:laugh|giggle|chuckle)"),
    ("mood", "shrug", r"(?:shrug)"),
    ("mood", "shy", r"(?:blush|be shy)"),
    ("mood", "sad", r"(?:(?:act|be|look|get) sad|cry)"),
    ("mood", "angry", r"(?:(?:act|be|look|get) (?:angry|mad))"),
    ("mood", "happy", r"(?:(?:act|be|look|get) happy|smile)"),
    ("mood", "shiver", r"(?:shiver|shake with cold)"),
]
_ACT_RES = [(k, n, re.compile(_ACT_PRE + "(?:" + p + ")" + _ACT_END, re.I)) for k, n, p in _ACT_SPECS]

ACT_LINES = {
    "sit": ("Taking a seat, Boss.", "Sitting down.", "Resting my legs, Boss."), "meditate": ("Finding my calm, Boss.", "Meditating."),
    "battle": ("Shadows incoming, Boss!", "Drawing my sword.", "Time to fight."), "kata": ("Sword practice, Boss.", "Running my forms."),
    "dance": ("Watch this, Boss.", "Dancing!", "Music in my head, Boss."), "disco": ("Disco time, Boss!",), "robot": ("Beep boop, Boss.",),
    "twirl": ("Whee!", "Spinning, Boss."), "moves": ("Get ready, Boss.", "Watch and learn."),
    "flip": ("Here goes, Boss.", "Watch this!"), "backflip": ("Backflip incoming, Boss.",), "jumps": ("Jumping, Boss.",),
    "stretch": ("Stretching, Boss.",), "flex": ("Behold, Boss.", "Not bad, right?"), "look": ("Looking around, Boss.",),
    "victory": ("Victory pose, Boss!",), "cursor": ("On my way, Boss!", "Coming!"), "run": ("Running laps, Boss.", "Off I go."),
    "march": ("Marching, Boss.",), "sneak": ("Sneaking, Boss.",), "skip": ("Skipping, Boss.",), "stand": ("Up I get, Boss.", "Standing."),
}
MOOD_LINES = {
    "wave": ("Hello, Boss!",), "bow": ("At your service, Boss.",), "salute": ("Aye aye, Boss.",), "clap": ("Bravo, Boss!",),
    "cheer": ("Woohoo!",), "laugh": ("Ha ha ha!",), "shrug": ("No idea, Boss.",), "shy": ("Stop it, Boss.",), "sad": ("Sigh...",),
    "angry": ("Grr!",), "happy": ("Happy as ever, Boss.",), "shiver": ("Brrr!",),
}


def match_action(low: str):
    """-> ('scene' | 'mood' | 'stand', name) or None. Whole phrase only, so 'dance floor playlist' or 'run chrome' never match."""
    t = low.strip().rstrip(".!?, ")
    for kind, name, rx in _ACT_RES:
        if rx.match(t):
            return kind, name
    return None
