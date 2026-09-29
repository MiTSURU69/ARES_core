"""
ares_memory.py - Ares' long-term memory (pure Python, no Qt, no network).

Stored in  %USERPROFILE%/ARES_Data/ares_memory.json  and survives restarts:

  * turns     every exchange (typed / spoken / local commands / screen readings / notes / reminders), so "that", "it" and
              "again" still make sense after a local command or a restart
  * facts     things you told him to remember ("remember that my sister's name is Asha")
  * summary   a short rolling summary of older conversation (refreshed in the background once 8+ new turns piled up)
  * mood      a slow-moving number: kind words nudge it up (chattier), harsh words nudge it down (quieter); it drifts
              back to neutral by itself over a few hours
"""
import json
import re
import time
import threading
from pathlib import Path

DATA_DIR = Path.home() / "ARES_Data"
MEM_FILE = DATA_DIR / "ares_memory.json"
MAX_TURNS = 300
MAX_FACTS = 80
SUMMARY_EVERY = 8                 # new turns before the summary is refreshed

_KIND = re.compile(r"\b(?:thank(?:s| you)|thx|love you|you(?:'re| are) (?:the best|amazing|awesome|great|good|brilliant|so helpful)|"
                   r"good (?:job|boy|work)|well done|nice (?:work|one|job)|great (?:job|work)|nailed it|perfect|appreciate|"
                   r"awesome|brilliant|wonderful|i like you|you rock)\b", re.I)
_HARSH = re.compile(r"\b(?:stupid|useless|idiot|dumb|shut up|hate you|you suck|worthless|annoying|garbage|trash|terrible|"
                    r"you(?:'re| are) (?:bad|wrong|slow|awful)|worst|pathetic|moron)\b", re.I)


def sentiment(text: str) -> float:
    """+0.10 per kind phrase, -0.18 per harsh one (capped). 0 for neutral text."""
    k, h = len(_KIND.findall(text or "")), len(_HARSH.findall(text or ""))
    return max(-0.4, min(0.3, 0.10 * k - 0.18 * h))


class Memory:
    def __init__(self, path: Path = MEM_FILE):
        self.path = Path(path)
        self.lock = threading.RLock()
        self.d = {"facts": [], "turns": [], "summary": "", "summarised": 0, "total": 0, "mood": 0.0, "mood_t": time.time()}
        self._load()

    # ── storage ──────────────────────────────────────────────────────
    def _load(self):
        try:
            if self.path.exists():
                data = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    for k in self.d:
                        if k in data:
                            self.d[k] = data[k]
        except Exception:
            try:                                                    # keep a broken file for inspection, start clean
                self.path.replace(self.path.with_suffix(".broken.json"))
            except Exception:
                pass

    def save(self):
        with self.lock:
            try:
                DATA_DIR.mkdir(exist_ok=True)
                tmp = self.path.with_suffix(".tmp")
                tmp.write_text(json.dumps(self.d, ensure_ascii=False, indent=1), encoding="utf-8")
                tmp.replace(self.path)
            except Exception:
                pass

    # ── turns ────────────────────────────────────────────────────────
    def add_turn(self, role: str, text: str, kind: str = "chat"):
        """role: 'user' | 'assistant'.  kind: chat | local | screen | note | reminder | scene | memory ..."""
        text = (text or "").strip()
        if not text:
            return
        with self.lock:
            self.d["turns"].append({"t": int(time.time()), "role": role, "text": text[:700], "kind": kind})
            self.d["total"] += 1
            if len(self.d["turns"]) > MAX_TURNS:
                cut = len(self.d["turns"]) - MAX_TURNS
                del self.d["turns"][:cut]
                self.d["summarised"] = max(0, self.d["summarised"] - cut)
            if role == "user":
                self.nudge(sentiment(text), save=False)
            self.save()

    def recent_messages(self, n: int = 8):
        """Last n turns as chat messages, oldest first (for the brain's history)."""
        with self.lock:
            out = [{"role": t["role"], "content": t["text"][:500]} for t in self.d["turns"][-n:]]
        while out and out[0]["role"] != "user":                     # a chat history has to start with the user
            out.pop(0)
        return out

    def last_reply(self) -> str:
        with self.lock:
            for t in reversed(self.d["turns"]):
                if t["role"] == "assistant":
                    return t["text"]
        return ""

    def last_user(self, skip: int = 0) -> str:
        with self.lock:
            us = [t["text"] for t in self.d["turns"] if t["role"] == "user"]
        return us[-1 - skip] if len(us) > skip else ""

    # ── facts ────────────────────────────────────────────────────────
    def remember(self, fact: str) -> str:
        fact = re.sub(r"\s+", " ", (fact or "")).strip(" .,!?")
        if len(fact) < 3:
            return "What should I remember, Boss?"
        with self.lock:
            if any(f["text"].lower() == fact.lower() for f in self.d["facts"]):
                return "I already have that, Boss."
            self.d["facts"].append({"text": fact[:300], "t": int(time.time())})
            del self.d["facts"][:-MAX_FACTS]
            self.save()
        return f"Got it, Boss. I'll remember that {fact[:120]}."

    def forget(self, what: str) -> str:
        what = (what or "").strip(" .,!?").lower()
        with self.lock:
            if what in ("everything", "all", "all of it", "it all", "everything you know", "everything about me"):
                n = len(self.d["facts"])
                self.d["facts"] = []
                self.save()
                return f"Wiped {n} remembered fact{'s' if n != 1 else ''}, Boss." if n else "There was nothing to forget, Boss."
            words = [w for w in re.findall(r"[a-z0-9']+", what) if w not in ("that", "the", "my", "about", "i", "me", "a", "an", "is", "was")]
            if not words:
                return "What should I forget, Boss?"
            keep, gone = [], []
            for f in self.d["facts"]:
                low = f["text"].lower()
                (gone if all(w in low for w in words) else keep).append(f)
            if not gone:                                            # looser: any word
                keep, gone = [], []
                for f in self.d["facts"]:
                    low = f["text"].lower()
                    (gone if any(w in low for w in words) else keep).append(f)
            if not gone:
                return "I don't have anything like that stored, Boss."
            self.d["facts"] = keep
            self.save()
        return f"Forgotten, Boss: {gone[0]['text'][:100]}" + (f" (and {len(gone) - 1} more)." if len(gone) > 1 else ".")

    def facts_text(self) -> str:
        with self.lock:
            facts = [f["text"] for f in self.d["facts"]]
        if not facts:
            return "Nothing yet, Boss. Say 'remember that' and tell me something."
        return "Here is what I remember, Boss: " + "; ".join(facts[-12:]) + "."

    # ── context for the brain ────────────────────────────────────────
    def context_block(self) -> str:
        with self.lock:
            facts = [f["text"] for f in self.d["facts"]][-15:]
            summary = self.d["summary"]
        parts = []
        if facts:
            parts.append("Things the user asked you to remember: " + "; ".join(facts) + ".")
        if summary:
            parts.append("Earlier conversation (summary): " + summary)
        return " ".join(parts)

    def style_hint(self) -> str:
        m = self.mood()
        if m >= 0.35:
            return "You're in a warm, chatty mood today: a touch more personality and one friendly follow-up is welcome."
        if m <= -0.35:
            return "You feel a bit hurt and subdued: keep answers short and quiet, still helpful."
        return ""

    def catch_up(self) -> str:
        with self.lock:
            summary = self.d["summary"]
            asks = [t["text"] for t in self.d["turns"] if t["role"] == "user"][-4:]
            facts = len(self.d["facts"])
        if not summary and not asks:
            return "We haven't talked much yet, Boss. Nothing to catch you up on."
        out = []
        if summary:
            out.append(summary)
        if asks:
            out.append("Most recently you asked me: " + "; ".join(a[:70] for a in asks) + ".")
        if facts:
            out.append(f"I'm also keeping {facts} thing{'s' if facts != 1 else ''} you told me to remember.")
        return " ".join(out)

    # ── rolling summary ──────────────────────────────────────────────
    def needs_summary(self) -> bool:
        with self.lock:
            return len(self.d["turns"]) - self.d["summarised"] >= SUMMARY_EVERY

    def refresh_summary(self, llm) -> bool:
        """llm(system, user) -> str.  Folds the un-summarised turns into the summary. Returns True if it changed."""
        with self.lock:
            start = self.d["summarised"]
            new = self.d["turns"][start:]
            old = self.d["summary"]
            upto = len(self.d["turns"])
        if len(new) < SUMMARY_EVERY:
            return False
        convo = "\n".join(f"{'User' if t['role'] == 'user' else 'Ares'}: {t['text'][:260]}" for t in new)
        system = ("You keep a short memory for a desktop assistant called Ares. Merge the OLD SUMMARY with the NEW CONVERSATION into one "
                  "updated summary of at most 90 words, plain text, third person about 'the user'. Keep lasting facts, preferences, "
                  "ongoing tasks and topics; drop small talk and trivia. Output only the summary.")
        try:
            text = (llm(system, f"OLD SUMMARY: {old or '(none)'}\n\nNEW CONVERSATION:\n{convo}") or "").strip()
        except Exception:
            return False
        if len(text) < 10:
            return False
        with self.lock:
            self.d["summary"] = text[:900]
            self.d["summarised"] = max(0, min(upto, len(self.d["turns"])))
            self.save()
        return True

    # ── mood ─────────────────────────────────────────────────────────
    def mood(self) -> float:
        with self.lock:
            dt = max(0.0, time.time() - self.d.get("mood_t", time.time()))
            m = self.d["mood"] * (0.5 ** (dt / 10800.0))            # half-life 3 hours
        return m

    def nudge(self, delta: float, save: bool = True):
        if not delta:
            return
        with self.lock:
            self.d["mood"] = max(-1.0, min(1.0, self.mood() + delta))
            self.d["mood_t"] = time.time()
            if save:
                self.save()


# ── spoken memory commands ───────────────────────────────────────────
_REMEMBER = re.compile(r"^(?:please\s+)?(?:remember|memori[sz]e|make a mental note|keep in mind)(?:\s+that)?\s+(.+)$", re.I)
_FORGET = re.compile(r"^(?:please\s+)?forget(?:\s+(?:about|that))?\s+(.+)$", re.I)
_RECALL = re.compile(r"^(?:what|which)\b.*\b(?:do you (?:remember|know)|have you (?:remembered|stored)|did i (?:tell|ask) you to remember)\b|"
                     r"^what do you (?:remember|know) about me\b|^(?:list|show) (?:your )?(?:memories|memory)\b", re.I)
_CATCHUP = re.compile(r"^(?:catch me up|catch up|what did we (?:talk|speak) about|what have we been (?:doing|talking about)|recap|"
                      r"remind me what we (?:were )?(?:doing|talking about))\b", re.I)


def match_memory_command(text: str):
    """-> ('remember', fact) | ('forget', what) | ('recall', None) | ('catchup', None) | None"""
    t = text.strip().rstrip(".!?")
    m = _REMEMBER.match(t)
    if m:
        return "remember", m.group(1)
    m = _FORGET.match(t)
    if m:
        return "forget", m.group(1)
    if _RECALL.search(t):
        return "recall", None
    if _CATCHUP.match(t):
        return "catchup", None
    return None
