"""
ares_extras.py - reminders, timers, Pomodoro, quick notes, system stats and time-of-day reactions (pure Python, no Qt).

  ex = Extras(announce, is_active)      announce(text, hint) makes Ares say something; is_active() -> True if you're around
  ex.handle(text)   -> (reply, hint, kind) if the sentence was one of the commands below, else None
  ex.session_prefix()  -> "Good morning, Boss. " the first time you talk to him in the morning, else ""
  ex.start()        starts the background loop (fires reminders, watches battery / CPU, late-night nudge)

Commands:
  "remind me to call mom in 20 minutes" / "in 2 hours remind me to stretch"      "what reminders do I have"  "cancel my reminders"
  "set a timer for 10 minutes" / "5 minute timer"                                 "start a pomodoro" / "stop the pomodoro"
  "note this down: buy milk" / "take a note ..." (bare "note this down" saves his last answer)   "read my notes"
  "how's my battery" / "system stats" / "how's my cpu" / "how much ram"
Files: ARES_Data/ares_reminders.json, ARES_Data/ares_notes.txt
"""
import json
import re
import time
import datetime
import threading
from pathlib import Path

DATA_DIR = Path.home() / "ARES_Data"
REM_FILE = DATA_DIR / "ares_reminders.json"
NOTES_FILE = DATA_DIR / "ares_notes.txt"

_NUM = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
        "ten": 10, "fifteen": 15, "twenty": 20, "thirty": 30, "forty": 40, "forty five": 45, "sixty": 60}
_DUR = (r"(?:half an? hour|(?:\d+(?:\.\d+)?|an?|one|two|three|four|five|six|seven|eight|nine|ten|fifteen|twenty|thirty|forty five|forty|sixty)"
        r"\s*(?:seconds?|secs?|minutes?|mins?|hours?|hrs?))")
_DUR_RE = re.compile(r"(\d+(?:\.\d+)?|an?|one|two|three|four|five|six|seven|eight|nine|ten|fifteen|twenty|thirty|forty five|forty|sixty)"
                     r"\s*(seconds?|secs?|minutes?|mins?|hours?|hrs?)", re.I)


def parse_duration(s: str):
    s = (s or "").lower()
    if "half an hour" in s or "half a hour" in s:
        return 1800
    m = _DUR_RE.search(s)
    if not m:
        return None
    n = float(m.group(1)) if m.group(1)[0].isdigit() else _NUM.get(m.group(1).lower(), 1)
    u = m.group(2).lower()
    return int(n * (3600 if u.startswith(("h")) else 60 if u.startswith("m") else 1))


def nice_duration(sec: int) -> str:
    if sec >= 3600 and sec % 1800 == 0:
        h = sec / 3600
        return f"{h:g} hour{'s' if h != 1 else ''}"
    if sec >= 60:
        m = round(sec / 60)
        return f"{m} minute{'s' if m != 1 else ''}"
    return f"{sec} second{'s' if sec != 1 else ''}"


_R1 = re.compile(r"^(?:please\s+)?(?:remind me|set (?:a )?reminder)\s+(?:to |about |that )?(?P<what>.+?)\s+(?:in|after)\s+(?P<d>" + _DUR + r")$", re.I)
_R2 = re.compile(r"^(?:please\s+)?(?:in|after)\s+(?P<d>" + _DUR + r"),?\s*remind me\s+(?:to |about |that )?(?P<what>.+)$", re.I)
_TIMER = re.compile(r"^(?:please\s+)?(?:(?:set|start)\s+(?:a\s+)?)?(?:timer\s+(?:for\s+)?(?P<d1>" + _DUR + r")|(?P<d2>" + _DUR + r")\s+timer)$", re.I)
_POMO = re.compile(r"^(?:please\s+)?(?:start\s+(?:a\s+)?)?(?:pomodoro|focus (?:mode|session|timer))(?:\s+(?:mode|session|timer))?$", re.I)
_POMO_STOP = re.compile(r"^(?:please\s+)?(?:stop|cancel|end)\s+(?:the\s+|my\s+)?(?:pomodoro|focus)(?:\s+\w+)?$", re.I)
_NOTE = re.compile(r"^(?:please\s+)?(?:note (?:this )?down|take (?:a )?note|make (?:a )?note|note that|jot (?:this )?down|write (?:this )?down)[:,\s]*(?:that\s+)?(?P<t>.*)$", re.I)
_NOTES_READ = re.compile(r"^(?:read|show|what(?:'s| are| is)?)\s+(?:me\s+)?(?:my\s+|the\s+)?(?:quick\s+)?notes\b", re.I)
_REM_LIST = re.compile(r"^(?:what|which|list|show|any)\b.*\b(?:reminders?|timers?)\b", re.I)
_REM_CANCEL = re.compile(r"^(?:please\s+)?(?:cancel|clear|delete|remove)\s+(?:all\s+)?(?:my\s+)?(?:reminders?|timers?)$", re.I)
_STATS = re.compile(r"^(?:how(?:'s| is| are)\s+(?:my\s+|the\s+)?(?:battery|cpu|ram|memory|pc|computer|laptop|system)|battery(?: level| status| left)?|"
                    r"system (?:stats|status|health)|cpu (?:usage|load)|ram usage|(?:how much|what(?:'s| is)) (?:my )?(?:battery|ram|cpu)|"
                    r"is my (?:pc|laptop|computer) (?:ok|okay|hot|healthy))\b.*$", re.I)


def system_report(kind: str = "all") -> str:
    try:
        import psutil
    except Exception:
        return "I need psutil to read your system, Boss. Run pip install psutil."
    out, warn = [], []
    cpu = psutil.cpu_percent(interval=0.6)
    ram = psutil.virtual_memory().percent
    out.append(f"CPU {cpu:.0f} percent")
    out.append(f"RAM {ram:.0f} percent")
    try:
        b = psutil.sensors_battery()
    except Exception:
        b = None
    if b is not None:
        out.append(f"battery {b.percent:.0f} percent, {'charging' if b.power_plugged else 'on battery'}")
        if not b.power_plugged and b.percent < 20:
            warn.append("Battery is low, plug me in, Boss.")
    if cpu > 85:
        warn.append("The CPU is working hard, it may be running hot.")
    if ram > 90:
        warn.append("Memory is almost full, close something, Boss.")
    try:
        temps = getattr(psutil, "sensors_temperatures", lambda: {})() or {}
        hot = max((t.current for v in temps.values() for t in v), default=0)
        if hot:
            out.append(f"temperature {hot:.0f} degrees")
            if hot > 85:
                warn.append("It's running hot, give it some air.")
    except Exception:
        pass
    if kind == "battery":
        pick = [x for x in out if x.startswith("battery")] or ["no battery found, this looks like a desktop"]
        return "Boss, " + pick[0] + "."
    return "Boss, " + ", ".join(out) + ". " + " ".join(warn)


class Extras:
    def __init__(self, announce, is_active=lambda: True):
        self.announce, self.is_active = announce, is_active
        self.lock = threading.RLock()
        self.items = []                       # {"id", "t", "text", "kind", "meta"}
        self.warned = {}                      # key -> last time warned
        self.greeted = None                   # date the morning greeting was given
        self.late_date = None
        self._load()

    # ── storage ──────────────────────────────────────────────────────
    def _load(self):
        try:
            if REM_FILE.exists():
                data = json.loads(REM_FILE.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    self.items = [d for d in data if isinstance(d, dict) and "t" in d and "text" in d]
        except Exception:
            self.items = []

    def _save(self):
        try:
            DATA_DIR.mkdir(exist_ok=True)
            REM_FILE.write_text(json.dumps(self.items, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    def add(self, delay: float, text: str, kind: str = "reminder", meta=None):
        with self.lock:
            self.items.append({"id": int(time.time() * 1000) % 10 ** 9, "t": time.time() + delay, "text": text, "kind": kind, "meta": meta or {}})
            self._save()

    def cancel(self, kinds=("reminder", "timer")) -> int:
        with self.lock:
            n = len([i for i in self.items if i["kind"] in kinds])
            self.items = [i for i in self.items if i["kind"] not in kinds]
            self._save()
        return n

    # ── commands ─────────────────────────────────────────────────────
    def handle(self, text: str, last_reply: str = ""):
        t = text.strip().rstrip(".!?")
        m = _R1.match(t) or _R2.match(t)
        if m:
            sec = parse_duration(m.group("d"))
            what = m.group("what").strip()
            if sec:
                self.add(sec, f"Reminder, Boss: {what}.", "reminder")
                return f"Okay Boss, I'll remind you to {what} in {nice_duration(sec)}.", "happy", "reminder"
        m = _TIMER.match(t)
        if m:
            sec = parse_duration(m.group("d1") or m.group("d2"))
            if sec:
                self.add(sec, f"Timer done, Boss. {nice_duration(sec)} are up.", "timer")
                return f"Timer set for {nice_duration(sec)}, Boss.", "happy", "reminder"
        if _POMO.match(t):
            self.cancel(("pomo",))
            self.add(25 * 60, "Focus block finished, Boss. Take a five minute break.", "pomo", {"phase": "focus", "n": 1})
            return "Pomodoro started, Boss. Twenty five minutes of focus. I'll nudge you for the breaks.", "proud", "reminder"
        if _POMO_STOP.match(t):
            n = self.cancel(("pomo",))
            return ("Pomodoro stopped, Boss." if n else "No Pomodoro running, Boss."), "happy", "reminder"
        if _REM_CANCEL.match(t):
            n = self.cancel(("reminder", "timer"))
            return (f"Cancelled {n} reminder{'s' if n != 1 else ''}, Boss." if n else "Nothing to cancel, Boss."), "happy", "reminder"
        if _REM_LIST.match(t):
            return self.list_text(), "happy", "reminder"
        m = _NOTE.match(t)
        if m:
            body = m.group("t").strip() or (last_reply or "").strip()
            if not body:
                return "What should I note down, Boss?", "curious", "note"
            try:
                DATA_DIR.mkdir(exist_ok=True)
                with open(NOTES_FILE, "a", encoding="utf-8") as f:
                    f.write(f"[{datetime.datetime.now():%Y-%m-%d %H:%M}] {body}\n")
            except Exception:
                return "I couldn't save that note, Boss.", "error", "note"
            return "Noted, Boss.", "proud", "note"
        if _NOTES_READ.match(t):
            try:
                lines = NOTES_FILE.read_text(encoding="utf-8").strip().splitlines()[-5:]
            except Exception:
                lines = []
            if not lines:
                return "You have no notes yet, Boss.", "happy", "note"
            return "Your latest notes, Boss: " + " ... ".join(re.sub(r"^\[[^\]]*\]\s*", "", l) for l in lines), "happy", "note"
        if _STATS.match(t):
            low = t.lower()
            return system_report("battery" if "battery" in low else "all"), "happy", "local"
        return None

    def list_text(self) -> str:
        with self.lock:
            items = sorted(self.items, key=lambda i: i["t"])
        if not items:
            return "You have no reminders or timers, Boss."
        parts = []
        for i in items[:5]:
            left = max(0, int(i["t"] - time.time()))
            parts.append(f"{i['text'].replace('Reminder, Boss: ', '').rstrip('.')} in {nice_duration(left)}")
        return "Boss, coming up: " + "; ".join(parts) + "."

    # ── time-of-day reactions ────────────────────────────────────────
    def session_prefix(self) -> str:
        now = datetime.datetime.now()
        if self.greeted != now.date() and 5 <= now.hour < 12:
            self.greeted = now.date()
            return "Good morning, Boss. "
        return ""

    # ── background loop ──────────────────────────────────────────────
    def start(self):
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        tick = 0
        while True:
            time.sleep(1.0)
            tick += 1
            try:
                self._fire_due()
                if tick % 60 == 0:
                    self._watch()
            except Exception:
                pass

    def _fire_due(self):
        now = time.time()
        with self.lock:
            due = [i for i in self.items if i["t"] <= now]
            if due:
                self.items = [i for i in self.items if i["t"] > now]
                self._save()
        for i in due:
            if i["kind"] == "pomo":
                meta = i.get("meta", {})
                if meta.get("phase") == "focus":
                    n = meta.get("n", 1)
                    brk = 15 if n % 4 == 0 else 5
                    self.add(brk * 60, "Break over, Boss. Back to focus.", "pomo", {"phase": "break", "n": n})
                    self.announce(i["text"] if brk == 5 else "Focus block finished, Boss. Take a proper fifteen minute break.", "celebrate")
                else:
                    self.add(25 * 60, "Focus block finished, Boss. Take a five minute break.", "pomo", {"phase": "focus", "n": meta.get("n", 1) + 1})
                    self.announce(i["text"], "excited")
            else:
                self.announce(i["text"], "excited")

    def _cooldown(self, key: str, secs: float) -> bool:
        now = time.time()
        if now - self.warned.get(key, 0) < secs:
            return False
        self.warned[key] = now
        return True

    def _watch(self):
        now = datetime.datetime.now()
        if 1 <= now.hour < 5 and self.late_date != now.date() and self.is_active():
            self.late_date = now.date()
            self.announce("Boss, it's past one in the morning. Go to sleep.", "sleepy")
            return
        try:
            import psutil
        except Exception:
            return
        try:
            b = psutil.sensors_battery()
            if b and not b.power_plugged and b.percent <= 15 and self._cooldown("battery", 1200):
                self.announce(f"Boss, battery is at {b.percent:.0f} percent. Plug in soon.", "worried")
                return
            if psutil.virtual_memory().percent > 93 and self._cooldown("ram", 1800):
                self.announce("Boss, memory is almost full. Something is hogging it.", "worried")
                return
            temps = getattr(psutil, "sensors_temperatures", lambda: {})() or {}
            hot = max((t.current for v in temps.values() for t in v), default=0)
            if hot > 90 and self._cooldown("heat", 1800):
                self.announce("Boss, your machine is running very hot. Give it some air.", "shiver")
        except Exception:
            pass
