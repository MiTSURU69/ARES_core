"""ares_habits.py - daily morning briefing + break nudges."""
import os, re, threading, time, random
from datetime import date, datetime, timedelta

_DATA = os.path.join(os.path.expanduser("~"), ".ares")
_STAMP = os.path.join(_DATA, "briefing_day.txt")


class Briefing:
    _WANT = re.compile(r"\b(?:brief me|(?:morning|daily|today'?s?) (?:briefing|brief)|give me (?:a |my |the )?(?:briefing|brief)|what'?s (?:on )?(?:my )?(?:agenda|schedule) today)\b", re.I)

    def __init__(self, jload, weather_fn=None):
        self.jload, self.weather = jload, weather_fn
        self._day = None
        try:
            with open(_STAMP, encoding="utf-8") as f:
                self._day = f.read().strip()
        except Exception:
            pass

    @staticmethod
    def wants(t: str) -> bool:
        return bool(Briefing._WANT.search(t or ""))

    def due(self) -> bool:
        return self._day != str(date.today())

    def mark_done(self):
        self._day = str(date.today())
        try:
            os.makedirs(_DATA, exist_ok=True)
            with open(_STAMP, "w", encoding="utf-8") as f:
                f.write(self._day)
        except Exception:
            pass

    def build(self) -> str:
        today = str(date.today())
        parts = [f"Here's your briefing for {datetime.now().strftime('%A, %d %B')}, Boss."]
        try:
            w = self.weather() if self.weather else ""
            if w:
                parts.append(f"Weather: {w}.")
        except Exception:
            pass
        try:
            ev = sorted((e for e in self.jload("calendar.json") if e.get("date") == today), key=lambda e: e.get("time", ""))
        except Exception:
            ev = []
        if ev:
            parts.append("On the calendar: " + "; ".join(f"{e.get('title', 'event')} at {e.get('time', '?')}" for e in ev[:6]) + ".")
        else:
            parts.append("Nothing on the calendar today.")
        try:
            todo = [r["title"] for r in self.jload("reminders.json") if not r.get("done") and r.get("title")]
        except Exception:
            todo = []
        if todo:
            more = f", and {len(todo) - 5} more" if len(todo) > 5 else ""
            parts.append("To-do: " + "; ".join(todo[:5]) + more + ".")
        else:
            parts.append("Your to-do list is clear.")
        return " ".join(parts)


class BreakNudger:
    _MSGS = ("You've been at it a while, Boss. Drink some water.", "Time to stretch, Boss. Stand up for a minute.",
             "Eyes off the screen for twenty seconds, Boss. Look at something far away.",
             "Quick walk, Boss? Your code will still be here.")

    def __init__(self, announce):
        self.announce = announce
        self.enabled = os.getenv("ARES_BREAKS", "1") != "0"
        try:
            self.interval = max(5, int(os.getenv("ARES_BREAK_MIN", "45"))) * 60
        except ValueError:
            self.interval = 45 * 60
        self.can_nudge = lambda: True
        self._next = time.time() + self.interval
        self._started = False

    def set_enabled(self, on: bool):
        self.enabled = bool(on)
        self._next = time.time() + self.interval

    def start(self):
        if self._started:
            return
        self._started = True
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while True:
            time.sleep(20)
            try:
                if self.enabled and time.time() >= self._next and self.can_nudge():
                    self._next = time.time() + self.interval
                    self.announce(random.choice(self._MSGS), "happy")
            except Exception:
                pass

    def handle(self, t: str):
        low = (t or "").lower()
        if "break reminder" not in low and "break nudge" not in low:
            return None
        if re.search(r"\b(?:stop|turn off|disable|no more|cancel)\b", low):
            self.set_enabled(False)
            return "Break reminders off, Boss."
        if re.search(r"\b(?:turn on|enable|start|resume)\b", low):
            self.set_enabled(True)
            return f"Break reminders on. I'll nudge you every {self.interval // 60} minutes."
        if "snooze" in low:
            self._next = time.time() + self.interval
            return f"Snoozed. Next nudge in {self.interval // 60} minutes."
        return None
