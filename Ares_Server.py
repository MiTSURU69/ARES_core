#!/usr/bin/env python3
"""
ARES WebSocket Bridge Server — v5.0
Connects index.html frontend to the ARES backend (Gemini 2.5 Flash).
F1 Engine: Jolpica (standings/results) + OpenF1 (live session) — identical to main.py v4.2
All features from main.py ported: F1 HTML, News HTML, Music Art, Sparklines, Nameplate, etc.
Run: python3 ares_server.py
"""

import os
import asyncio
import json
import threading
import time
import psutil
import subprocess
import random
import math
import base64
import io
import tempfile
import webbrowser
import requests
import feedparser
import numpy as np
import soundfile as sf
from datetime import datetime
from collections import deque
from typing import Set

import websockets
from websockets.asyncio.server import serve as ws_serve
from dotenv import load_dotenv

# ── Gemini SDK ────────────────────────────────────────
try:
    from google import genai as google_genai
    from google.genai import types as genai_types
    _GENAI_NEW = True
except ImportError:
    import google.generativeai as genai
    _GENAI_NEW = False

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

if _GENAI_NEW:
    _genai_client = google_genai.Client(api_key=GEMINI_API_KEY)
else:
    genai.configure(api_key=GEMINI_API_KEY)

# ── Groq SDK ──────────────────────────────────────────
from groq import Groq
import json

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
_groq_client = Groq(api_key=GROQ_API_KEY)
GROQ_MODEL = "openai/gpt-oss-120b"


# ══════════════════════════════════════════════════════
#  CONNECTED CLIENTS
# ══════════════════════════════════════════════════════
clients: Set = set()
clients_lock = threading.Lock()

async def broadcast(msg: dict):
    with clients_lock:
        targets = set(clients)
    if not targets:
        return
    data = json.dumps(msg)
    await asyncio.gather(*[ws.send(data) for ws in targets], return_exceptions=True)

# ══════════════════════════════════════════════════════
#  SPARKLINE HISTORY — rolling 8-point telemetry buffers
# ══════════════════════════════════════════════════════
_SPARK_CPU  = deque([0.0] * 8, maxlen=8)
_SPARK_MEM  = deque([0.0] * 8, maxlen=8)
_SPARK_DISK = deque([0.0] * 8, maxlen=8)

def _build_spark(data: deque) -> str:
    BLOCKS = " ▁▂▃▄▅▆▇█"
    vals = list(data)
    lo = min(vals) if vals else 0
    hi = max(vals) if vals else 1
    rng = max(hi - lo, 1)
    return "".join(
        BLOCKS[max(0, min(int((v - lo) / rng * (len(BLOCKS) - 1)), len(BLOCKS) - 1))]
        for v in vals
    )

# ══════════════════════════════════════════════════════
#  LANGUAGE CONFIG
# ══════════════════════════════════════════════════════
LANGUAGE_MAP = {
    "hindi":     ("hi-IN","hi-IN","hi-IN-MadhurNeural"),
    "tamil":     ("ta-IN","ta-IN","ta-IN-ValluvarNeural"),
    "telugu":    ("te-IN","te-IN","te-IN-MohanNeural"),
    "kannada":   ("kn-IN","kn-IN","kn-IN-GaganNeural"),
    "bengali":   ("bn-IN","bn-IN","bn-IN-BashkarNeural"),
    "marathi":   ("mr-IN","mr-IN","mr-IN-ManoharNeural"),
    "gujarati":  ("gu-IN","gu-IN","gu-IN-NiranjanNeural"),
    "punjabi":   ("pa-IN","pa-IN","pa-IN-OjasNeural"),
    "malayalam": ("ml-IN","ml-IN","ml-IN-MidhunNeural"),
    "english":   ("en-IN","en-IN","en-AU-KenNeural"),
    "french":    ("fr-FR","fr-FR","fr-FR-HenriNeural"),
    "spanish":   ("es-ES","es-ES","es-ES-AlvaroNeural"),
    "german":    ("de-DE","de-DE","de-DE-KilianNeural"),
    "japanese":  ("ja-JP","ja-JP","ja-JP-KeitaNeural"),
    "arabic":    ("ar-SA","ar-SA","ar-SA-HamedNeural"),
}

active_language = {
    "name":     "english",
    "stt_lang": "en-IN",
    "tts_lang": "en-IN",
    "speaker":  "en-AU-KenNeural",
}

KOKORO_VOICE_MAP = {
    "english":  "am_adam",
    "french":   "ff_siwis",
    "japanese": "jf_alpha",
}

_kokoro_pipeline = None

def _get_kokoro():
    global _kokoro_pipeline
    if _kokoro_pipeline is None:
        try:
            from kokoro import KPipeline
            _kokoro_pipeline = KPipeline(lang_code="a")
        except Exception:
            _kokoro_pipeline = False
    return _kokoro_pipeline if _kokoro_pipeline else None

def set_language(lang_name: str) -> str:
    lang_key = lang_name.lower().strip()
    if lang_key in LANGUAGE_MAP:
        stt, tts, speaker = LANGUAGE_MAP[lang_key]
        active_language.update({"name": lang_key, "stt_lang": stt, "tts_lang": tts, "speaker": speaker})
        return f"Switched to {lang_name.title()}, Boss. Ready."
    return f"Language '{lang_name}' not in my registry. Available: {', '.join(LANGUAGE_MAP.keys())}."

# ══════════════════════════════════════════════════════
#  QUIPS
# ══════════════════════════════════════════════════════
QUIPS = {
    "thinking":  ["Processing that, Boss.", "On it.", "Let me work on that.",
                  "Give me a moment, Boss.", "Running that now.", "Working through it, Boss."],
    "f1":        ["Pulling the pit wall data, Boss.", "Checking the timing screens.",
                  "Fetching from Formula One HQ, Boss.", "Live telemetry incoming, Boss.",
                  "Race control feed — stand by.", "Connecting to the timing tower, Boss.",
                  "Dialling into the pit lane, Boss."],
    "news":      ["Pulling the latest feeds, Boss. Stand by.", "Scanning global headlines. One moment.",
                  "Aggregating news streams now, Boss.", "Compiling the intelligence feed, Boss."],
    "weather":   ["Checking atmospheric data, Boss.", "Pulling weather now.",
                  "Fetching local conditions, Boss."],
    "search":    ["Opening that search, Boss.", "Launching search now.", "On it, Boss."],
    "reading":   ["Reading the page now, Boss.", "Extracting content. One moment.",
                  "Pulling the full story, Boss."],
    "music_search": ["On it, Boss. Scanning the library.", "Pulling that track up right now.",
                     "Queuing it up. Give me a second.", "Found it. Sending to Music now."],
    "shutdown":  ["Understood. Going dark, Boss. Until next time.",
                  "Core shutdown initiated. Stay sharp, Boss.",
                  "Signing off. All systems standing down.",
                  "Powering down. The desk is yours, Boss."],
    "screen":    ["Capturing the screen now, Boss.", "Vision module engaged.",
                  "Reading what's on your display, Boss.", "Screen analysis in progress."],
}

def quip(cat: str) -> str:
    return random.choice(QUIPS.get(cat, ["On it, Boss."]))

# ══════════════════════════════════════════════════════
#  TTS  (Kokoro → Edge → say)
# ══════════════════════════════════════════════════════
_speak_lock = threading.Lock()

TMP_WAV = os.path.join(tempfile.gettempdir(), "ares_voice.wav")
TMP_MP3 = os.path.join(tempfile.gettempdir(), "quip.mp3")

def stop_all_audio():
    for proc in ("afplay", "say"):
        subprocess.run(["killall", proc], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def _kokoro_speak_blocking(text: str) -> bool:
    pipeline = _get_kokoro()
    if not pipeline:
        return False
    voice = KOKORO_VOICE_MAP.get(active_language["name"])
    if not voice:
        return False
    try:
        clean = text.replace("'", "").replace('"', "").replace("*", "").replace("#", "").strip()
        if not clean:
            return True
        chunks = []
        for _, _, audio in pipeline(clean, voice=voice, speed=1.05):
            if audio is not None and len(audio) > 0:
                chunks.append(audio)
        if not chunks:
            return False
        sf.write(TMP_WAV, np.concatenate(chunks), 24000)
        subprocess.run(["afplay", "-v", "1.0", TMP_WAV],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False

def speak_sync(text: str):
    with _speak_lock:
        stop_all_audio()
        if _kokoro_speak_blocking(text):
            return
        try:
            clean = text.replace("'", "").replace('"', "").replace("*", "").replace("#", "").strip()
            voice = active_language.get("speaker", "en-AU-KenNeural")
            subprocess.run(
                ["edge-tts", "--voice", voice, "--rate=+5%", "--text", clean,
                 "--write-media", TMP_MP3],
                check=True, timeout=10,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            subprocess.run(["afplay", TMP_MP3],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
        except Exception:
            pass
        subprocess.Popen(["say", "-v", "Samantha", "-r", "185", text])

# ══════════════════════════════════════════════════════
#  F1 APIs — JOLPICA + OPENF1 (identical to main.py v4.2)
# ══════════════════════════════════════════════════════
JOLPICA_BASE = "http://api.jolpi.ca/ergast/f1"
OPENF1_BASE  = "https://api.openf1.org/v1"

OPENF1_TEAM_COLOURS = {
    "red bull":     "#3671C6",
    "mercedes":     "#27F4D2",
    "ferrari":      "#E8002D",
    "mclaren":      "#FF8000",
    "aston martin": "#229971",
    "alpine":       "#0093CC",
    "williams":     "#64C4FF",
    "rb":           "#6692FF",
    "racing bulls": "#6692FF",
    "kick sauber":  "#52E252",
    "sauber":       "#52E252",
    "haas":         "#B6BABD",
}

TEAM_COLOURS = {
    "Red Bull":       "#3671C6",
    "Mercedes":       "#27F4D2",
    "Ferrari":        "#E8002D",
    "McLaren":        "#FF8000",
    "Aston Martin":   "#229971",
    "Alpine":         "#0093CC",
    "Williams":       "#64C4FF",
    "RB":             "#6692FF",
    "Racing Bulls":   "#6692FF",
    "Kick Sauber":    "#52E252",
    "Sauber":         "#52E252",
    "Haas":           "#B6BABD",
    "Default":        "#E10600",
}

DRIVER_FLAGS = {
    "British":    "🇬🇧", "Dutch":      "🇳🇱", "Monegasque": "🇲🇨",
    "Spanish":    "🇪🇸", "Australian": "🇦🇺", "Canadian":   "🇨🇦",
    "German":     "🇩🇪", "Mexican":    "🇲🇽", "Finnish":    "🇫🇮",
    "French":     "🇫🇷", "Japanese":   "🇯🇵", "Thai":       "🇹🇭",
    "Chinese":    "🇨🇳", "Danish":     "🇩🇰", "American":   "🇺🇸",
    "Brazilian":  "🇧🇷", "Italian":    "🇮🇹", "Austrian":   "🇦🇹",
    "Argentine":  "🇦🇷", "New Zealander": "🇳🇿",
}

def _openf1_team_hex(team_name: str) -> str:
    tl = (team_name or "").lower()
    for k, v in OPENF1_TEAM_COLOURS.items():
        if k in tl:
            return v
    return "#E10600"

def _team_colour(team: str) -> str:
    for k, v in TEAM_COLOURS.items():
        if k.lower() in team.lower():
            return v
    return TEAM_COLOURS["Default"]

def _fetch_openf1_live() -> dict:
    live = {
        "session":      {},
        "positions":    [],
        "race_control": [],
        "pit_stops":    [],
        "drivers":      {},
        "intervals":    {},
    }
    headers = {"User-Agent": "ARES/5.0 F1Intelligence"}
    try:
        r = requests.get(f"{OPENF1_BASE}/sessions?session_key=latest",
                         headers=headers, timeout=10)
        sessions = r.json()
        if not sessions:
            return live
        live["session"] = sessions[-1]
        sk = live["session"].get("session_key")
        if not sk:
            return live

        try:
            dr = requests.get(f"{OPENF1_BASE}/drivers?session_key={sk}",
                              headers=headers, timeout=10)
            for d in dr.json():
                live["drivers"][d.get("driver_number")] = d
        except Exception:
            pass

        try:
            pr = requests.get(f"{OPENF1_BASE}/position?session_key={sk}",
                              headers=headers, timeout=10)
            pos_data = pr.json()
            latest_pos = {}
            for p in pos_data:
                dn = p.get("driver_number")
                if dn and (dn not in latest_pos or
                           p.get("date","") > latest_pos[dn].get("date","")):
                    latest_pos[dn] = p
            live["positions"] = sorted(latest_pos.values(),
                                       key=lambda x: x.get("position", 99))
        except Exception:
            pass

        try:
            ir = requests.get(f"{OPENF1_BASE}/intervals?session_key={sk}",
                              headers=headers, timeout=10)
            iv_data = ir.json()
            latest_iv = {}
            for iv in iv_data:
                dn = iv.get("driver_number")
                if dn and (dn not in latest_iv or
                           iv.get("date","") > latest_iv[dn].get("date","")):
                    latest_iv[dn] = iv
            live["intervals"] = latest_iv
        except Exception:
            pass

        try:
            rcr = requests.get(f"{OPENF1_BASE}/race_control?session_key={sk}",
                               headers=headers, timeout=10)
            live["race_control"] = rcr.json()[-10:]
        except Exception:
            pass

        try:
            pitr = requests.get(f"{OPENF1_BASE}/pit?session_key={sk}",
                                headers=headers, timeout=10)
            live["pit_stops"] = pitr.json()[-20:]
        except Exception:
            pass

    except Exception as e:
        print(f"[OpenF1 Error] {e}")
    return live

def _fetch_f1_data() -> dict:
    """Full Jolpica + OpenF1 fetch — identical to main.py v4.2"""
    data = {
        "driver_standings":      [],
        "constructor_standings": [],
        "last_race":  {},
        "next_race":  {},
        "season":     str(datetime.now().year),
        "live":       {},
    }
    headers = {"User-Agent": "ARES/5.0 F1Intelligence"}

    try:
        r  = requests.get(f"{JOLPICA_BASE}/current/driverStandings/",
                          headers=headers, timeout=10)
        js = r.json()
        sl = js["MRData"]["StandingsTable"]["StandingsLists"]
        if sl:
            data["season"] = sl[0].get("season", data["season"])
            for s in sl[0]["DriverStandings"][:20]:
                drv  = s["Driver"]
                cons = s.get("Constructors", [{}])
                team = cons[0].get("name","Unknown") if cons else "Unknown"
                data["driver_standings"].append({
                    "pos":    s["position"],
                    "name":   f"{drv['givenName']} {drv['familyName']}",
                    "code":   drv.get("code","???"),
                    "team":   team,
                    "points": s["points"],
                    "wins":   s["wins"],
                    "nat":    drv.get("nationality",""),
                })
    except Exception as e:
        print(f"[Jolpica Driver Standings] {e}")

    try:
        r  = requests.get(f"{JOLPICA_BASE}/current/constructorStandings/",
                          headers=headers, timeout=10)
        js = r.json()
        sl = js["MRData"]["StandingsTable"]["StandingsLists"]
        if sl:
            for s in sl[0]["ConstructorStandings"][:10]:
                data["constructor_standings"].append({
                    "pos":    s["position"],
                    "name":   s["Constructor"]["name"],
                    "points": s["points"],
                    "wins":   s["wins"],
                    "nat":    s["Constructor"].get("nationality",""),
                })
    except Exception as e:
        print(f"[Jolpica Constructor Standings] {e}")

    try:
        r  = requests.get(f"{JOLPICA_BASE}/current/last/results/",
                          headers=headers, timeout=10)
        js = r.json()
        races = js["MRData"]["RaceTable"]["Races"]
        if races:
            race    = races[0]
            results = race.get("Results", [])[:10]
            data["last_race"] = {
                "name":    race.get("raceName",""),
                "circuit": race.get("Circuit",{}).get("circuitName",""),
                "date":    race.get("date",""),
                "country": race.get("Circuit",{}).get("Location",{}).get("country",""),
                "round":   race.get("round",""),
                "results": [{
                    "pos":    r2["position"],
                    "driver": f"{r2['Driver']['givenName']} {r2['Driver']['familyName']}",
                    "code":   r2["Driver"].get("code","???"),
                    "team":   r2["Constructor"]["name"],
                    "time":   r2.get("Time",{}).get("time","") or r2.get("status",""),
                    "points": r2.get("points","0"),
                    "laps":   r2.get("laps",""),
                } for r2 in results],
            }
    except Exception as e:
        print(f"[Jolpica Last Race] {e}")

    try:
        r  = requests.get(f"{JOLPICA_BASE}/current/next/",
                          headers=headers, timeout=10)
        js = r.json()
        races = js["MRData"]["RaceTable"]["Races"]
        if races:
            race = races[0]
            data["next_race"] = {
                "name":    race.get("raceName",""),
                "circuit": race.get("Circuit",{}).get("circuitName",""),
                "date":    race.get("date",""),
                "time":    race.get("time",""),
                "country": race.get("Circuit",{}).get("Location",{}).get("country",""),
                "round":   race.get("round",""),
            }
    except Exception as e:
        print(f"[Jolpica Next Race] {e}")

    data["live"] = _fetch_openf1_live()
    return data

# ══════════════════════════════════════════════════════
#  F1 HTML BUILDER — full copy from main.py v4.2
# ══════════════════════════════════════════════════════
def build_f1_html(data: dict) -> str:
    season           = data.get("season", str(datetime.now().year))
    driver_stds      = data.get("driver_standings", [])
    constructor_stds = data.get("constructor_standings", [])
    last_race        = data.get("last_race", {})
    next_race        = data.get("next_race", {})
    live             = data.get("live", {})
    now_str          = datetime.now().strftime("%H:%M · %d %B %Y")

    driver_rows = ""
    max_pts = float(driver_stds[0]["points"]) if driver_stds else 1
    for i, d in enumerate(driver_stds):
        tc    = _team_colour(d["team"])
        flag  = DRIVER_FLAGS.get(d.get("nat",""), "🏁")
        medal = ["🥇","🥈","🥉"][i] if i < 3 else ""
        bar_w = int(float(d["points"]) / max(max_pts,1) * 100)
        leader_cls = "leader" if i == 0 else ""
        driver_rows += f"""
        <tr class="dr-row {leader_cls}">
          <td class="pos-cell">
            <div class="pos-badge" style="--tc:{tc}">{d['pos']}</div>
            {'<span class="medal">'+medal+'</span>' if medal else ''}
          </td>
          <td class="code-cell">
            <span class="drv-code" style="color:{tc};text-shadow:0 0 20px {tc}88">{d['code']}</span>
          </td>
          <td class="name-cell">
            <span class="flag">{flag}</span>
            <div class="drv-info">
              <span class="drv-name">{d['name']}</span>
              <span class="drv-team" style="color:{tc}">{d['team']}</span>
            </div>
          </td>
          <td class="pts-cell">
            <div class="pts-wrap">
              <span class="pts-val">{d['points']}</span>
              <div class="pts-track">
                <div class="pts-fill" style="width:{bar_w}%;background:linear-gradient(90deg,{tc},{tc}88)"></div>
              </div>
            </div>
          </td>
          <td class="wins-cell">
            <span class="wins-badge" style="border-color:{tc}44;color:{tc}">{d['wins']}W</span>
          </td>
        </tr>"""

    con_rows = ""
    max_con = float(constructor_stds[0]["points"]) if constructor_stds else 1
    for i, c in enumerate(constructor_stds):
        tc    = _team_colour(c["name"])
        medal = ["🥇","🥈","🥉"][i] if i < 3 else ""
        bar_w = int(float(c["points"]) / max(max_con,1) * 100)
        con_rows += f"""
        <tr class="con-row">
          <td class="pos-cell">
            <div class="pos-badge" style="--tc:{tc}">{c['pos']}</div>
            {'<span class="medal">'+medal+'</span>' if medal else ''}
          </td>
          <td class="team-cell">
            <div class="team-stripe" style="background:{tc};box-shadow:0 0 12px {tc}66"></div>
            <span class="team-nm" style="color:{tc}">{c['name']}</span>
          </td>
          <td class="pts-cell">
            <div class="pts-wrap">
              <span class="pts-val">{c['points']}</span>
              <div class="pts-track">
                <div class="pts-fill" style="width:{bar_w}%;background:linear-gradient(90deg,{tc},{tc}88)"></div>
              </div>
            </div>
          </td>
          <td class="wins-cell">
            <span class="wins-badge" style="border-color:{tc}44;color:{tc}">{c['wins']}W</span>
          </td>
        </tr>"""

    podium_html = ""
    if last_race.get("results"):
        order   = [1, 0, 2]
        heights = ["h-p2","h-p1","h-p3"]
        labels  = ["P2","P1 · WINNER","P3"]
        for offset, ri in enumerate(order):
            if ri < len(last_race["results"]):
                r2 = last_race["results"][ri]
                tc = _team_colour(r2["team"])
                podium_html += f"""
                <div class="podium-col {heights[offset]}" style="--tc:{tc}">
                  <div class="pod-card">
                    <div class="pod-label" style="color:{tc}">{labels[offset]}</div>
                    <div class="pod-code"  style="color:{tc};text-shadow:0 0 30px {tc}">{r2['code']}</div>
                    <div class="pod-name">{r2['driver']}</div>
                    <div class="pod-team" style="color:{tc}">{r2['team']}</div>
                    <div class="pod-time">{r2['time'] or str(r2.get('laps',''))+' laps'}</div>
                    <div class="pod-pts" style="color:#FFD700">+{r2['points']} PTS</div>
                  </div>
                  <div class="pod-block" style="border-top:3px solid {tc};background:linear-gradient(180deg,{tc}22,{tc}06)"></div>
                </div>"""

    last_race_html = ""
    if last_race:
        result_rows = ""
        for r2 in last_race.get("results",[]):
            tc = _team_colour(r2["team"])
            result_rows += f"""
            <tr class="res-row">
              <td class="rt-pos" style="border-left:3px solid {tc}">{r2['pos']}</td>
              <td class="rt-code"  style="color:{tc}">{r2['code']}</td>
              <td class="rt-driver">{r2['driver']}</td>
              <td class="rt-team"  style="color:{tc}">{r2['team']}</td>
              <td class="rt-time">{r2['time'] or str(r2.get('laps',''))+' laps'}</td>
              <td class="rt-pts"  style="color:#FFD700">+{r2['points']}</td>
            </tr>"""

        last_race_html = f"""
        <section class="race-sec" id="last-race">
          <div class="sec-hd">
            <div class="sec-hd-l">
              <span class="eyebrow">ROUND {last_race.get('round','')} · RACE RESULT</span>
              <h2 class="sec-title">{last_race.get('name','')}</h2>
              <p class="sec-meta">{last_race.get('circuit','')} · {last_race.get('country','')} · {last_race.get('date','')}</p>
            </div>
            <div class="live-chip"><span class="dot"></span>CLASSIFIED</div>
          </div>
          <div class="podium-stage">{podium_html}</div>
          <div class="tbl-wrap">
            <table class="data-tbl">
              <thead><tr><th>POS</th><th>CODE</th><th>DRIVER</th><th>TEAM</th><th>TIME/STATUS</th><th>PTS</th></tr></thead>
              <tbody>{result_rows}</tbody>
            </table>
          </div>
        </section>"""

    next_race_html = ""
    if next_race:
        try:
            dt_str = f"{next_race['date']} {next_race.get('time','12:00:00').replace('Z','')}"
            dt     = datetime.strptime(dt_str.strip(), "%Y-%m-%d %H:%M:%S")
            delta  = dt - datetime.utcnow()
            countdown = f"{max(0,delta.days)}D {max(0,delta.seconds//3600)}H"
        except Exception:
            countdown = next_race.get("date","")

        next_race_html = f"""
        <section class="next-race-sec">
          <div class="next-inner">
            <div class="next-left">
              <span class="eyebrow" style="color:#FF8000">ROUND {next_race.get('round','')} · NEXT RACE</span>
              <h2 class="next-name">{next_race.get('name','')}</h2>
              <div class="next-meta">
                <span class="meta-chip">📍 {next_race.get('circuit','')} · {next_race.get('country','')}</span>
                <span class="meta-chip">📅 {next_race.get('date','')}</span>
              </div>
            </div>
            <div class="countdown-box">
              <div class="cdown-label">RACE IN</div>
              <div class="cdown-val">{countdown}</div>
              <div class="cdown-sub">DAYS · HOURS</div>
            </div>
          </div>
        </section>"""

    live_session   = live.get("session",{})
    live_positions = live.get("positions",[])
    live_drivers   = live.get("drivers",{})
    live_rc        = live.get("race_control",[])
    live_pit       = live.get("pit_stops",[])
    intervals      = live.get("intervals",{})

    timing_rows = ""
    for p in live_positions[:20]:
        dn   = p.get("driver_number")
        drv  = live_drivers.get(dn, {})
        code = drv.get("name_acronym","???")
        team = drv.get("team_name","")
        tc   = _openf1_team_hex(team)
        pos  = p.get("position","")
        iv   = intervals.get(dn,{})
        gap  = iv.get("gap_to_leader","") or ""
        int_ = iv.get("interval","") or ""
        if isinstance(gap, float):
            gap = f"+{gap:.3f}s" if gap > 0 else "LEADER"
        if isinstance(int_, float):
            int_ = f"+{int_:.3f}s"
        timing_rows += f"""
        <tr class="timing-row">
          <td class="t-pos" style="border-left:3px solid {tc}">{pos}</td>
          <td class="t-code" style="color:{tc}">{code}</td>
          <td class="t-name">{drv.get('full_name','')}</td>
          <td class="t-team" style="color:{tc}">{team}</td>
          <td class="t-gap">{gap}</td>
          <td class="t-int">{int_}</td>
        </tr>"""

    rc_rows = ""
    for msg in reversed(live_rc):
        cat   = msg.get("category","")
        flag  = msg.get("flag","")
        txt   = msg.get("message","")
        ts    = msg.get("date","")[:19].replace("T"," ")
        colour = ("#FF0000" if cat == "Flag" and "RED" in flag.upper()
                  else "#FFD700" if "YELLOW" in flag.upper()
                  else "#00FF00" if "GREEN" in flag.upper()
                  else "#E10600" if cat == "SafetyCar"
                  else "#FFFFFF")
        rc_rows += f"""
        <tr class="rc-row">
          <td class="rc-ts">{ts}</td>
          <td class="rc-cat" style="color:{colour}">{cat}</td>
          <td class="rc-msg" style="color:{colour}">{txt}</td>
        </tr>"""

    pit_rows = ""
    for pit in reversed(live_pit[-15:]):
        dn   = pit.get("driver_number")
        drv  = live_drivers.get(dn,{})
        code = drv.get("name_acronym","???")
        team = drv.get("team_name","")
        tc   = _openf1_team_hex(team)
        lap  = pit.get("lap_number","")
        dur  = pit.get("pit_duration","")
        pit_dur_str = f"{dur:.2f}s" if isinstance(dur, float) else str(dur)
        pit_rows += f"""
        <tr class="pit-row">
          <td class="p-code" style="color:{tc}">{code}</td>
          <td class="p-team" style="color:{tc}">{team}</td>
          <td class="p-lap">LAP {lap}</td>
          <td class="p-dur">{pit_dur_str}</td>
        </tr>"""

    session_name    = live_session.get("session_name","")
    meeting_name    = live_session.get("meeting_name","")
    session_country = live_session.get("country_name","")
    session_type    = live_session.get("session_type","")
    has_live        = bool(live_positions)

    live_section = ""
    if has_live:
        live_section = f"""
        <section class="live-sec" id="live">
          <div class="sec-hd">
            <div class="sec-hd-l">
              <span class="eyebrow" style="color:#E10600">OPENF1 · LIVE SESSION</span>
              <h2 class="sec-title">{meeting_name or 'SESSION'} · {session_name}</h2>
              <p class="sec-meta">{session_country} · {session_type}</p>
            </div>
            <div class="live-chip pulsing"><span class="dot"></span>LIVE</div>
          </div>
          <div class="live-grid">
            <div class="live-card">
              <div class="live-card-hd">⏱ TIMING TOWER</div>
              <div class="tbl-wrap">
                <table class="data-tbl">
                  <thead><tr><th>POS</th><th>CODE</th><th>DRIVER</th><th>TEAM</th><th>GAP</th><th>INT</th></tr></thead>
                  <tbody>{timing_rows or '<tr><td colspan="6" style="text-align:center;color:#555;padding:20px">No live timing data</td></tr>'}</tbody>
                </table>
              </div>
            </div>
            <div class="live-right-col">
              <div class="live-card">
                <div class="live-card-hd">🏁 RACE CONTROL</div>
                <div class="tbl-wrap">
                  <table class="data-tbl">
                    <thead><tr><th>TIME</th><th>TYPE</th><th>MESSAGE</th></tr></thead>
                    <tbody>{rc_rows or '<tr><td colspan="3" style="text-align:center;color:#555;padding:16px">No messages</td></tr>'}</tbody>
                  </table>
                </div>
              </div>
              <div class="live-card" style="margin-top:24px">
                <div class="live-card-hd">🔧 PIT STOPS</div>
                <div class="tbl-wrap">
                  <table class="data-tbl">
                    <thead><tr><th>DRIVER</th><th>TEAM</th><th>LAP</th><th>DURATION</th></tr></thead>
                    <tbody>{pit_rows or '<tr><td colspan="4" style="text-align:center;color:#555;padding:16px">No pit data</td></tr>'}</tbody>
                  </table>
                </div>
              </div>
            </div>
          </div>
        </section>"""

    ticker = " &nbsp;·&nbsp; ".join(
        [f"P{d['pos']} {d['name'].split()[-1].upper()} {d['points']}PTS" for d in driver_stds[:10]]
        + [f"{c['name'].upper()} {c['points']}PTS" for c in constructor_stds[:5]]
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ARES · F1 Intelligence · {season}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:ital,wght@0,300;0,400;0,600;0,700;0,800;0,900;1,700&family=Barlow:wght@300;400;500;600;700&family=JetBrains+Mono:wght@300;400;500;700&display=swap" rel="stylesheet">
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
:root{{
  --red:#E10600;--red-dim:#8B0000;--red-glow:rgba(225,6,0,0.42);
  --orange:#FF8000;--gold:#FFD700;
  --bg-void:#080808;--bg-base:#0C0C0C;--bg-card:#111111;
  --bg-elev:#181818;--bg-hover:#1F1F1F;
  --b-sub:rgba(255,255,255,0.06);--b-mid:rgba(255,255,255,0.12);
  --b-bright:rgba(255,255,255,0.22);
  --t1:#FFFFFF;--t2:#A0A0A0;--t3:#555555;
  --fh:'Barlow Condensed',sans-serif;--fb:'Barlow',sans-serif;--fm:'JetBrains Mono',monospace;
}}
html{{scroll-behavior:smooth}}
body{{background:var(--bg-void);color:var(--t1);font-family:var(--fb);min-height:100vh;overflow-x:hidden;-webkit-font-smoothing:antialiased}}
body::before{{content:'';position:fixed;inset:0;background-image:linear-gradient(rgba(255,255,255,0.013) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,0.013) 1px,transparent 1px);background-size:40px 40px;pointer-events:none;z-index:0}}
::-webkit-scrollbar{{width:4px;background:var(--bg-void)}}
::-webkit-scrollbar-thumb{{background:var(--red);border-radius:2px}}
.topbar{{position:relative;z-index:100;background:var(--bg-void);border-bottom:1px solid var(--b-sub);height:36px;display:flex;align-items:center;justify-content:space-between;padding:0 32px;font-family:var(--fm);font-size:9px;letter-spacing:.15em;text-transform:uppercase;color:var(--t3)}}
.tb-right{{display:flex;align-items:center;gap:20px}}
.tb-live{{display:flex;align-items:center;gap:5px;color:var(--red);font-weight:700}}
.dot{{width:6px;height:6px;background:var(--red);border-radius:50%;box-shadow:0 0 8px var(--red);animation:blink 1.2s ease-in-out infinite}}
@keyframes blink{{0%,100%{{opacity:1;transform:scale(1)}}50%{{opacity:.25;transform:scale(.55)}}}}
.ticker-wrap{{position:relative;z-index:100;height:30px;display:flex;align-items:center;background:var(--red);overflow:hidden}}
.ticker-flag{{flex-shrink:0;padding:0 14px;height:100%;display:flex;align-items:center;gap:6px;background:rgba(0,0,0,.35);border-right:1px solid rgba(255,255,255,.2);font-family:var(--fm);font-size:9px;font-weight:700;letter-spacing:.2em;color:#fff;text-transform:uppercase}}
.ticker-scroll{{overflow:hidden;flex:1}}
.ticker-inner{{display:inline-block;white-space:nowrap;animation:ticker 65s linear infinite;font-family:var(--fm);font-size:10px;font-weight:600;color:rgba(255,255,255,.95);padding-left:100%;letter-spacing:.05em}}
@keyframes ticker{{from{{transform:translateX(0)}}to{{transform:translateX(-100%)}}}}
.masthead{{position:relative;z-index:10;background:var(--bg-base);border-bottom:1px solid var(--b-sub);overflow:hidden}}
.masthead-inner{{position:relative;z-index:2;max-width:1440px;margin:0 auto;padding:28px 40px;display:flex;align-items:center;justify-content:space-between;gap:32px}}
.ares-wordmark{{font-family:var(--fh);font-size:88px;font-weight:900;letter-spacing:-.04em;line-height:1;position:relative;display:inline-block}}
.ares-wordmark .w-a,.ares-wordmark .w-e{{color:#fff}}
.ares-wordmark .w-r,.ares-wordmark .w-s{{color:var(--red);text-shadow:0 0 40px var(--red-glow),0 0 80px var(--red-glow)}}
.ares-stripe{{position:absolute;bottom:6px;left:0;right:0;height:4px;background:linear-gradient(90deg,var(--red),#FF4000,rgba(255,128,0,.3),transparent);border-radius:2px}}
.brand-col{{display:flex;flex-direction:column;gap:4px;margin-left:20px}}
.brand-t{{font-family:var(--fh);font-size:18px;font-weight:700;letter-spacing:.15em;text-transform:uppercase;color:var(--t1)}}
.brand-s{{font-family:var(--fm);font-size:9px;letter-spacing:.22em;color:var(--t3);text-transform:uppercase}}
.brand-chip{{margin-top:8px;display:inline-flex;align-items:center;gap:6px;font-family:var(--fm);font-size:8px;font-weight:700;letter-spacing:.2em;color:var(--red);text-transform:uppercase;border:1px solid rgba(225,6,0,.4);padding:3px 10px;border-radius:2px;background:rgba(225,6,0,.08);width:fit-content}}
.mast-right{{text-align:right}}
.season-badge{{font-family:var(--fh);font-size:80px;font-weight:900;line-height:1;background:linear-gradient(135deg,#fff 0%,rgba(255,255,255,.45) 100%);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}}
.mast-time{{font-family:var(--fm);font-size:11px;color:var(--t3);letter-spacing:.08em}}
nav{{position:sticky;top:0;z-index:90;background:rgba(8,8,8,.94);backdrop-filter:blur(12px);border-bottom:1px solid var(--b-sub)}}
.nav-inner{{max-width:1440px;margin:0 auto;padding:0 40px;display:flex;align-items:center}}
.nav-lnk{{font-family:var(--fh);font-size:12px;font-weight:700;letter-spacing:.15em;text-transform:uppercase;color:var(--t3);padding:16px 18px;cursor:pointer;border-bottom:2px solid transparent;transition:all .2s;white-space:nowrap}}
.nav-lnk:hover{{color:var(--t1);border-color:rgba(225,6,0,.4)}}
.nav-lnk.active{{color:var(--t1);border-color:var(--red)}}
.nav-brand{{margin-left:auto;font-family:var(--fm);font-size:9px;font-weight:700;letter-spacing:.18em;color:var(--red);display:flex;align-items:center;gap:8px;padding:16px 0;text-transform:uppercase}}
.content{{max-width:1440px;margin:0 auto;padding:48px 40px;position:relative;z-index:1}}
.sec-hd{{display:flex;align-items:flex-start;justify-content:space-between;padding-bottom:18px;border-bottom:1px solid var(--b-sub);margin-bottom:28px;position:relative}}
.sec-hd::after{{content:'';position:absolute;bottom:-1px;left:0;width:60px;height:2px;background:var(--red);box-shadow:0 0 16px var(--red-glow)}}
.sec-hd-l{{display:flex;flex-direction:column;gap:4px}}
.eyebrow{{font-family:var(--fm);font-size:9px;font-weight:700;letter-spacing:.25em;color:var(--red);text-transform:uppercase}}
.sec-title{{font-family:var(--fh);font-size:44px;font-weight:900;letter-spacing:.02em;text-transform:uppercase;color:var(--t1);line-height:1}}
.sec-meta{{font-family:var(--fm);font-size:10px;color:var(--t3);letter-spacing:.08em;margin-top:4px}}
.live-chip{{display:flex;align-items:center;gap:6px;font-family:var(--fm);font-size:9px;font-weight:700;letter-spacing:.18em;color:var(--red);border:1px solid rgba(225,6,0,.35);background:rgba(225,6,0,.08);padding:6px 14px;border-radius:2px;text-transform:uppercase;flex-shrink:0;margin-top:6px}}
.pulsing .dot{{animation:blink .8s ease-in-out infinite}}
.next-race-sec{{position:relative;margin-bottom:56px;background:var(--bg-card);border:1px solid var(--b-sub);border-left:4px solid var(--orange);border-radius:2px;overflow:hidden}}
.next-inner{{position:relative;z-index:1;padding:32px 40px;display:flex;align-items:center;justify-content:space-between;gap:32px}}
.next-name{{font-family:var(--fh);font-size:48px;font-weight:900;letter-spacing:.03em;text-transform:uppercase;color:var(--t1);line-height:1.05;margin-top:6px}}
.next-meta{{display:flex;gap:16px;flex-wrap:wrap;margin-top:12px}}
.meta-chip{{font-family:var(--fm);font-size:11px;color:var(--t2);letter-spacing:.06em;background:var(--bg-elev);border:1px solid var(--b-sub);padding:4px 12px;border-radius:2px}}
.countdown-box{{flex-shrink:0;text-align:center;background:rgba(255,128,0,.07);border:1px solid rgba(255,128,0,.25);padding:20px 32px;border-radius:4px}}
.cdown-label{{font-family:var(--fm);font-size:9px;font-weight:700;letter-spacing:.22em;color:var(--orange);text-transform:uppercase;margin-bottom:4px}}
.cdown-val{{font-family:var(--fh);font-size:52px;font-weight:900;color:var(--orange);line-height:1;text-shadow:0 0 40px rgba(255,128,0,.5)}}
.cdown-sub{{font-family:var(--fm);font-size:8px;letter-spacing:.2em;color:rgba(255,128,0,.5);margin-top:4px;text-transform:uppercase}}
.race-sec{{margin-bottom:56px}}
.podium-stage{{display:flex;align-items:flex-end;justify-content:center;gap:4px;margin-bottom:32px;padding:32px 0 0}}
.podium-col{{display:flex;flex-direction:column;align-items:center;flex:1;max-width:320px}}
.h-p1 .pod-block{{height:120px}}.h-p2 .pod-block{{height:80px}}.h-p3 .pod-block{{height:60px}}
.pod-card{{background:var(--bg-card);border:1px solid var(--b-sub);border-radius:4px 4px 0 0;padding:20px 24px;width:100%;text-align:center;transition:transform .2s}}
.pod-card:hover{{transform:translateY(-4px)}}
.pod-label{{font-family:var(--fm);font-size:9px;font-weight:700;letter-spacing:.2em;text-transform:uppercase;margin-bottom:8px}}
.pod-code{{font-family:var(--fh);font-size:56px;font-weight:900;letter-spacing:.02em;line-height:1}}
.pod-name{{font-family:var(--fh);font-size:15px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--t1);margin-top:6px}}
.pod-team{{font-family:var(--fm);font-size:9px;letter-spacing:.12em;text-transform:uppercase;margin-top:4px}}
.pod-time{{font-family:var(--fm);font-size:12px;color:var(--t3);margin-top:8px}}
.pod-pts{{font-family:var(--fh);font-size:22px;font-weight:800;margin-top:6px;letter-spacing:.04em}}
.pod-block{{width:100%;border-radius:0}}
.tbl-wrap{{border:1px solid var(--b-sub);border-radius:4px;overflow:hidden}}
.data-tbl{{width:100%;border-collapse:collapse}}
.data-tbl thead tr{{background:var(--bg-elev);border-bottom:1px solid var(--b-mid)}}
.data-tbl th{{font-family:var(--fm);font-size:9px;font-weight:700;letter-spacing:.2em;text-transform:uppercase;color:var(--t3);padding:12px 16px;text-align:left}}
.data-tbl tbody tr{{background:var(--bg-card);border-bottom:1px solid var(--b-sub);transition:background .15s}}
.data-tbl tbody tr:hover{{background:var(--bg-hover)}}
.data-tbl td{{padding:13px 16px}}
.rt-pos,.t-pos{{font-family:var(--fh);font-size:20px;font-weight:900;padding-left:12px}}
.rt-code,.t-code{{font-family:var(--fh);font-size:18px;font-weight:900;letter-spacing:.05em}}
.rt-driver,.t-name{{font-family:var(--fh);font-size:15px;font-weight:700;letter-spacing:.06em;text-transform:uppercase}}
.rt-team,.t-team{{font-family:var(--fm);font-size:10px;letter-spacing:.08em}}
.rt-time,.t-gap,.t-int{{font-family:var(--fm);font-size:12px;color:var(--t3)}}
.rt-pts{{font-family:var(--fh);font-size:18px;font-weight:800;letter-spacing:.04em}}
.rc-ts{{font-family:var(--fm);font-size:10px;color:var(--t3)}}
.rc-cat{{font-family:var(--fm);font-size:10px;font-weight:700;letter-spacing:.1em;text-transform:uppercase}}
.rc-msg{{font-family:var(--fb);font-size:13px}}
.p-code{{font-family:var(--fh);font-size:18px;font-weight:900}}
.p-team{{font-family:var(--fm);font-size:10px}}
.p-lap,.p-dur{{font-family:var(--fm);font-size:12px;color:var(--t3)}}
.live-sec{{margin-bottom:56px}}
.live-grid{{display:grid;grid-template-columns:1.5fr 1fr;gap:24px}}
.live-card{{background:var(--bg-card);border:1px solid var(--b-sub);border-top:2px solid var(--red);border-radius:4px;overflow:hidden}}
.live-card-hd{{padding:14px 20px;background:var(--bg-elev);border-bottom:1px solid var(--b-sub);font-family:var(--fm);font-size:10px;font-weight:700;letter-spacing:.2em;text-transform:uppercase;color:var(--red)}}
.live-right-col{{display:flex;flex-direction:column;gap:0}}
.standings-sec{{margin-bottom:56px}}
.pos-cell{{width:60px;text-align:center;padding:12px 8px}}
.pos-badge{{display:inline-flex;align-items:center;justify-content:center;width:32px;height:32px;background:linear-gradient(135deg,var(--tc),color-mix(in srgb,var(--tc) 50%,black));border-radius:4px;font-family:var(--fh);font-size:16px;font-weight:900;color:#fff;box-shadow:0 2px 12px color-mix(in srgb,var(--tc) 40%,transparent)}}
.medal{{display:block;font-size:14px;margin-top:2px}}
.code-cell{{width:80px}}
.drv-code{{font-family:var(--fh);font-size:26px;font-weight:900;letter-spacing:.04em}}
.flag{{font-size:18px;margin-right:10px}}
.drv-info{{display:inline-flex;flex-direction:column;gap:2px}}
.drv-name{{font-family:var(--fh);font-size:16px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--t1)}}
.drv-team{{font-family:var(--fm);font-size:9px;letter-spacing:.12em;text-transform:uppercase}}
.pts-cell{{width:220px}}
.pts-wrap{{display:flex;flex-direction:column;gap:4px}}
.pts-val{{font-family:var(--fh);font-size:20px;font-weight:800;color:var(--t1)}}
.pts-track{{height:3px;background:var(--b-sub);border-radius:2px;overflow:hidden}}
.pts-fill{{height:100%;border-radius:2px;transition:width .8s cubic-bezier(.25,.46,.45,.94)}}
.wins-cell{{width:64px;text-align:center}}
.wins-badge{{font-family:var(--fm);font-size:10px;font-weight:700;letter-spacing:.1em;border:1px solid;padding:3px 8px;border-radius:2px}}
.dr-row.leader{{background:linear-gradient(90deg,rgba(225,6,0,.04) 0%,transparent 100%)!important}}
.team-cell{{display:flex;align-items:center;gap:12px}}
.team-stripe{{width:4px;height:28px;border-radius:2px;flex-shrink:0}}
.team-nm{{font-family:var(--fh);font-size:20px;font-weight:800;letter-spacing:.06em;text-transform:uppercase}}
footer{{position:relative;z-index:1;background:var(--bg-base);border-top:1px solid var(--b-sub);padding:32px 40px;text-align:center;font-family:var(--fm);font-size:9px;letter-spacing:.18em;color:var(--t3);text-transform:uppercase}}
footer strong{{color:var(--t2)}}
@keyframes fadeIn{{from{{opacity:0;transform:translateY(14px)}}to{{opacity:1;transform:translateY(0)}}}}
.anim{{animation:fadeIn .35s ease both}}
@media(max-width:1024px){{
  .ares-wordmark{{font-size:60px}}.season-badge{{font-size:56px}}
  .content{{padding:32px 20px}}.masthead-inner{{padding:20px;flex-wrap:wrap}}
  .live-grid{{grid-template-columns:1fr}}.next-inner{{flex-direction:column}}
  .podium-stage{{flex-direction:column;align-items:center}}
  .podium-col{{max-width:100%;width:100%}}
  .h-p1 .pod-block,.h-p2 .pod-block,.h-p3 .pod-block{{height:16px}}
}}
</style>
</head>
<body>
<div class="topbar">
  <span>ARES · AUTOMATED REMOTE ENGAGEMENT SYSTEM · F1 INTELLIGENCE HUB · JOLPICA + OPENF1</span>
  <div class="tb-right">
    <span>DRIVERS</span><span>TEAMS</span><span>RESULTS</span><span>LIVE</span>
    <span class="tb-live"><div class="dot"></div>LIVE</span>
  </div>
</div>
<div class="ticker-wrap">
  <div class="ticker-flag"><div class="dot"></div>F1 FEED</div>
  <div class="ticker-scroll">
    <span class="ticker-inner">{ticker} &nbsp;·&nbsp; {ticker}</span>
  </div>
</div>
<div class="masthead">
  <div class="masthead-inner">
    <div style="display:flex;align-items:center">
      <div class="ares-wordmark">
        <span class="w-a">A</span><span class="w-r">R</span><span class="w-e">E</span><span class="w-s">S</span>
        <div class="ares-stripe"></div>
      </div>
      <div class="brand-col">
        <div class="brand-t">F1 Intelligence</div>
        <div class="brand-s">Automated Remote Engagement System</div>
        <div class="brand-s">Jolpica (Standings) + OpenF1 (Live)</div>
        <div class="brand-chip"><div class="dot"></div>DUAL API · LIVE DATA</div>
      </div>
    </div>
    <div class="mast-right">
      <div class="season-badge">{season}</div>
      <div class="mast-time" id="live-time">--:--:--</div>
      <div class="mast-time">{now_str}</div>
    </div>
  </div>
</div>
<nav>
  <div class="nav-inner">
    <span class="nav-lnk active">Overview</span>
    {'<span class="nav-lnk">Live Session</span>' if has_live else ''}
    <span class="nav-lnk">Standings</span>
    <span class="nav-lnk">Last Race</span>
    <span class="nav-lnk">Constructors</span>
    <div class="nav-brand"><div class="dot"></div>ARES · F1</div>
  </div>
</nav>
<main class="content">
  {next_race_html}
  {live_section}
  {last_race_html}
  <section class="standings-sec" id="standings">
    <div class="sec-hd">
      <div class="sec-hd-l">
        <span class="eyebrow">Season {season} · World Drivers Championship</span>
        <h2 class="sec-title">Driver Standings</h2>
        <p class="sec-meta">Current points · Jolpica API</p>
      </div>
      <div class="live-chip"><span class="dot"></span>LIVE DATA</div>
    </div>
    <div class="tbl-wrap">
      <table class="data-tbl">
        <thead><tr><th>POS</th><th>CODE</th><th>DRIVER</th><th>POINTS</th><th>WINS</th></tr></thead>
        <tbody>{driver_rows or '<tr><td colspan="5" style="text-align:center;padding:20px;color:#555">No standings data — API may be rate limited. Try again shortly.</td></tr>'}</tbody>
      </table>
    </div>
  </section>
  <section class="standings-sec" id="constructors">
    <div class="sec-hd">
      <div class="sec-hd-l">
        <span class="eyebrow">Season {season} · World Constructors Championship</span>
        <h2 class="sec-title">Constructor Standings</h2>
        <p class="sec-meta">Team championship · Jolpica API</p>
      </div>
      <div class="live-chip"><span class="dot"></span>LIVE DATA</div>
    </div>
    <div class="tbl-wrap">
      <table class="data-tbl">
        <thead><tr><th>POS</th><th>TEAM</th><th>POINTS</th><th>WINS</th></tr></thead>
        <tbody>{con_rows or '<tr><td colspan="4" style="text-align:center;padding:20px;color:#555">No constructor data available.</td></tr>'}</tbody>
      </table>
    </div>
  </section>
</main>
<footer>
  <strong>ARES</strong> · Automated Remote Engagement System ·
  F1 Intelligence · Standings via Jolpica-F1 · Live timing via OpenF1 API ·
  Generated {now_str} · Formula 1 data © Formula One Management
</footer>
<script>
(function(){{
  const el=document.getElementById('live-time');
  function t(){{if(el)el.textContent=new Date().toLocaleTimeString('en-GB',{{hour12:false}});}}
  t();setInterval(t,1000);
}})();
document.querySelectorAll('.nav-lnk').forEach(n=>{{
  n.addEventListener('click',()=>{{
    document.querySelectorAll('.nav-lnk').forEach(m=>m.classList.remove('active'));
    n.classList.add('active');
  }});
}});
const obs=new IntersectionObserver(entries=>{{
  entries.forEach(e=>{{if(e.isIntersecting){{e.target.classList.add('anim');obs.unobserve(e.target);}}}});
}},{{threshold:.04}});
document.querySelectorAll('.dr-row,.con-row,.res-row,.podium-col,.timing-row').forEach(el=>{{
  el.style.opacity='0';obs.observe(el);
}});
</script>
</body>
</html>"""

# ══════════════════════════════════════════════════════
#  NEWS FUNCTIONS — from main.py
# ══════════════════════════════════════════════════════
NEWS_CATEGORY_MAP = {
    "war":("BREAKING","#cc0000"),"conflict":("BREAKING","#cc0000"),
    "attack":("BREAKING","#cc0000"),"dead":("BREAKING","#cc0000"),
    "killed":("BREAKING","#cc0000"),"explosion":("BREAKING","#cc0000"),
    "crisis":("ALERT","#d45000"),"earthquake":("ALERT","#d45000"),
    "flood":("ALERT","#d45000"),"disaster":("ALERT","#d45000"),
    "election":("POLITICS","#1a5fa8"),"vote":("POLITICS","#1a5fa8"),
    "president":("POLITICS","#1a5fa8"),"parliament":("POLITICS","#1a5fa8"),
    "economy":("BUSINESS","#1a7a4a"),"market":("BUSINESS","#1a7a4a"),
    "stock":("BUSINESS","#1a7a4a"),"trade":("BUSINESS","#1a7a4a"),
    "tech":("TECHNOLOGY","#5c2d91"),"ai":("TECHNOLOGY","#5c2d91"),
    "science":("SCIENCE","#0e6ba8"),"space":("SCIENCE","#0e6ba8"),
    "sport":("SPORT","#c47400"),"football":("SPORT","#c47400"),
    "cricket":("SPORT","#c47400"),"olympic":("SPORT","#c47400"),
}

def classify_headline(title: str):
    tl = title.lower()
    for kw,(label,colour) in NEWS_CATEGORY_MAP.items():
        if kw in tl: return label, colour
    return "WORLD","#4a4a6a"

def build_news_html(articles: list) -> str:
    now_str = datetime.now().strftime("%H:%M  ·  %d %B %Y")
    day_str = datetime.now().strftime("%A").upper()
    ticker_items = " &nbsp;·&nbsp; ".join(
        f"[{classify_headline(a['title'])[0]}] {a['title'][:80]}" for a in articles[:12]
    )
    hero = articles[0] if articles else {}
    hero_label, hero_colour = classify_headline(hero.get("title",""))
    hero_title   = hero.get("title","").replace("<","&lt;").replace(">","&gt;")
    hero_summary = hero.get("summary","")[:320].replace("<","&lt;").replace(">","&gt;")
    hero_source  = hero.get("source","")
    hero_link    = hero.get("link","#")
    cards_html = ""
    for a in articles[1:]:
        label, colour = classify_headline(a["title"])
        title   = a["title"].replace("<","&lt;").replace(">","&gt;")
        summary = a.get("summary","")[:160].replace("<","&lt;").replace(">","&gt;")
        cards_html += f"""
        <article class="news-card" onclick="window.open('{a.get('link','#')}','_blank')">
          <div class="nci">
            <div class="ncat-bar" style="background:{colour}"></div>
            <div class="ncb">
              <div class="nmr">
                <span class="ncat" style="background:{colour}22;color:{colour};border-color:{colour}44">{label}</span>
                <span class="nsrc">{a.get('source','')}</span>
              </div>
              <h3 class="ntitle">{title}</h3>
              <p class="nsum">{summary}</p>
            </div>
            <div class="narrow">→</div>
          </div>
        </article>"""
    sources_html = " ".join(
        f'<span class="src-pill">{s}</span>'
        for s in sorted(set(a["source"] for a in articles))
    )
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ARES Global Intelligence Feed</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@300;500;700;900&family=Barlow:wght@300;400;500;600&family=JetBrains+Mono:wght@300;400;500;700&display=swap" rel="stylesheet">
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
:root{{--red:#E10600;--rg:rgba(225,6,0,.35);--bg0:#06060F;--bg1:#0A0A14;--bg2:#0F0F1A;--bg3:#141420;--bgh:#191928;--b0:rgba(255,255,255,.07);--b1:rgba(255,255,255,.13);--t1:#F0F0FF;--t2:#8888AA;--t3:#444466;--fh:'Barlow Condensed',sans-serif;--fb:'Barlow',sans-serif;--fm:'JetBrains Mono',monospace}}
body{{background:var(--bg0);color:var(--t1);font-family:var(--fb);min-height:100vh;-webkit-font-smoothing:antialiased}}
::-webkit-scrollbar{{width:4px;background:var(--bg0)}}::-webkit-scrollbar-thumb{{background:var(--red);border-radius:2px}}
.topbar{{position:relative;z-index:100;background:var(--bg0);border-bottom:1px solid var(--b0);height:36px;display:flex;align-items:center;justify-content:space-between;padding:0 32px;font-family:var(--fm);font-size:9px;letter-spacing:.15em;text-transform:uppercase;color:var(--t3)}}
.tb-r{{display:flex;gap:20px;align-items:center}}
.lp{{display:flex;align-items:center;gap:5px;color:var(--red);font-weight:700}}
.dot{{width:6px;height:6px;background:var(--red);border-radius:50%;box-shadow:0 0 8px var(--red);animation:bl 1.2s ease-in-out infinite}}
@keyframes bl{{0%,100%{{opacity:1}}50%{{opacity:.25}}}}
.tw{{position:relative;z-index:100;height:30px;display:flex;align-items:center;background:var(--red);overflow:hidden}}
.tl{{flex-shrink:0;padding:0 14px;height:100%;display:flex;align-items:center;gap:6px;background:rgba(0,0,0,.3);border-right:1px solid rgba(255,255,255,.18);font-family:var(--fm);font-size:9px;font-weight:700;letter-spacing:.2em;color:#fff;text-transform:uppercase}}
.ts{{overflow:hidden;flex:1}}
.ti{{display:inline-block;white-space:nowrap;animation:run 65s linear infinite;font-family:var(--fm);font-size:10px;font-weight:500;color:rgba(255,255,255,.93);padding-left:100%;letter-spacing:.04em}}
@keyframes run{{from{{transform:translateX(0)}}to{{transform:translateX(-100%)}}}}
.mh{{background:var(--bg1);border-bottom:1px solid var(--b0);overflow:hidden}}
.mhi{{max-width:1440px;margin:0 auto;padding:28px 40px;display:flex;align-items:center;justify-content:space-between;gap:32px}}
.awm{{font-family:var(--fh);font-size:72px;font-weight:900;letter-spacing:-.04em;line-height:1;position:relative;display:inline-block}}
.awm .a,.awm .e{{color:#fff}}.awm .r,.awm .s{{color:var(--red);text-shadow:0 0 40px var(--rg),0 0 80px var(--rg)}}
.ab{{position:absolute;bottom:4px;left:0;right:0;height:3px;background:linear-gradient(90deg,var(--red),#ff6b35,rgba(255,128,0,.3),transparent);border-radius:2px}}
.bd{{width:2px;height:52px;background:linear-gradient(180deg,transparent,var(--red),transparent);flex-shrink:0;margin:0 20px}}
.bc{{display:flex;flex-direction:column;gap:4px}}
.bt{{font-family:var(--fh);font-size:16px;font-weight:700;letter-spacing:.18em;text-transform:uppercase;color:var(--t1)}}
.bs{{font-family:var(--fm);font-size:9px;letter-spacing:.2em;color:var(--t3);text-transform:uppercase}}
.bch{{margin-top:8px;display:inline-flex;align-items:center;gap:6px;font-family:var(--fm);font-size:8px;font-weight:700;letter-spacing:.2em;color:var(--red);text-transform:uppercase;border:1px solid rgba(225,6,0,.35);background:rgba(225,6,0,.07);padding:3px 10px;border-radius:2px;width:fit-content}}
.mhr{{text-align:right}}
.mhdb{{font-family:var(--fh);font-size:20px;font-weight:700;letter-spacing:.12em;color:var(--t1);text-transform:uppercase}}
.mht{{font-family:var(--fm);font-size:11px;color:var(--t3);letter-spacing:.08em;margin-top:4px}}
.sr{{background:var(--bg1);border-bottom:1px solid var(--b0);padding:8px 40px;display:flex;align-items:center;gap:12px;overflow-x:auto}}
.srl{{font-family:var(--fm);font-size:8px;letter-spacing:.2em;color:var(--t3);text-transform:uppercase;flex-shrink:0}}
.src-pill{{font-family:var(--fm);font-size:9px;color:var(--t2);background:var(--bg3);border:1px solid var(--b0);padding:3px 12px;border-radius:2px;white-space:nowrap;letter-spacing:.08em;text-transform:uppercase}}
.content{{max-width:1440px;margin:0 auto;padding:48px 40px;position:relative;z-index:1}}
.sch{{display:flex;align-items:flex-start;justify-content:space-between;padding-bottom:18px;border-bottom:1px solid var(--b0);margin-bottom:28px;position:relative}}
.sch::after{{content:'';position:absolute;bottom:-1px;left:0;width:56px;height:2px;background:var(--red);box-shadow:0 0 14px var(--rg)}}
.schl{{display:flex;flex-direction:column;gap:4px}}
.ey{{font-family:var(--fm);font-size:9px;font-weight:700;letter-spacing:.25em;color:var(--red);text-transform:uppercase}}
.st{{font-family:var(--fh);font-size:40px;font-weight:900;letter-spacing:.02em;text-transform:uppercase;color:var(--t1);line-height:1.05}}
.sm{{font-family:var(--fm);font-size:10px;color:var(--t3);letter-spacing:.08em;margin-top:2px}}
.lb{{display:flex;align-items:center;gap:6px;font-family:var(--fm);font-size:8px;font-weight:700;letter-spacing:.18em;color:var(--red);text-transform:uppercase;border:1px solid rgba(225,6,0,.3);background:rgba(225,6,0,.07);padding:6px 12px;border-radius:2px;flex-shrink:0;margin-top:4px}}
.ha{{display:grid;grid-template-columns:1fr 1fr;border:1px solid var(--b0);border-radius:4px;overflow:hidden;margin-bottom:48px;cursor:pointer;background:var(--bg2);transition:border-color .2s}}
.ha:hover{{border-color:rgba(225,6,0,.35)}}
.hv{{background:linear-gradient(135deg,#0d0008 0%,#160010 50%,#0d0018 100%);min-height:360px;display:flex;flex-direction:column;justify-content:space-between;padding:24px;position:relative}}
.hv::before{{content:'';position:absolute;inset:0;background:radial-gradient(ellipse at 30% 30%,rgba(225,6,0,.18) 0%,transparent 60%)}}
.hst{{position:relative;z-index:1;font-family:var(--fm);font-size:10px;font-weight:700;letter-spacing:.15em;text-transform:uppercase;color:rgba(255,255,255,.4)}}
.hvt{{position:relative;z-index:1;font-family:var(--fh);font-size:13px;font-weight:700;letter-spacing:.2em;text-transform:uppercase;color:rgba(255,255,255,.12)}}
.hb{{padding:40px;display:flex;flex-direction:column;justify-content:center;border-left:1px solid var(--b0)}}
.hcat{{display:inline-flex;align-items:center;font-family:var(--fm);font-size:9px;font-weight:700;letter-spacing:.18em;text-transform:uppercase;color:#fff;padding:4px 12px;border-radius:2px;width:fit-content;margin-bottom:20px}}
.htitle{{font-family:var(--fh);font-size:34px;font-weight:700;line-height:1.18;color:var(--t1);margin-bottom:16px}}
.hsum{{font-family:var(--fb);font-size:15px;font-weight:400;line-height:1.7;color:var(--t2);margin-bottom:28px}}
.hft{{display:flex;align-items:center;justify-content:space-between;padding-top:16px;border-top:1px solid var(--b0)}}
.hsl{{font-family:var(--fm);font-size:9px;letter-spacing:.14em;color:var(--t3);text-transform:uppercase}}
.rb{{font-family:var(--fm);font-size:9px;font-weight:700;letter-spacing:.18em;color:var(--red);text-transform:uppercase;border:1px solid rgba(225,6,0,.35);padding:6px 14px;border-radius:2px;background:rgba(225,6,0,.07)}}
.ng{{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:2px;background:var(--b0);border:1px solid var(--b0);border-radius:4px;overflow:hidden}}
.news-card{{background:var(--bg2);cursor:pointer;transition:background .15s}}
.news-card:hover{{background:var(--bgh)}}
.nci{{display:flex;gap:0;position:relative;height:100%}}
.ncat-bar{{width:3px;flex-shrink:0}}
.ncb{{padding:22px 20px;flex:1;display:flex;flex-direction:column;gap:10px}}
.nmr{{display:flex;align-items:center;justify-content:space-between;gap:8px}}
.ncat{{font-family:var(--fm);font-size:8px;font-weight:700;letter-spacing:.15em;text-transform:uppercase;border:1px solid;padding:2px 8px;border-radius:2px}}
.nsrc{{font-family:var(--fm);font-size:9px;color:var(--t3);letter-spacing:.08em;text-transform:uppercase}}
.ntitle{{font-family:var(--fh);font-size:19px;font-weight:700;letter-spacing:.03em;line-height:1.25;color:var(--t1)}}
.nsum{{font-family:var(--fb);font-size:13px;color:var(--t2);line-height:1.6;flex:1}}
.narrow{{display:flex;align-items:center;padding:0 16px;font-size:18px;color:var(--t3);transition:color .2s}}
.news-card:hover .narrow{{color:var(--red)}}
footer{{background:var(--bg1);border-top:1px solid var(--b0);padding:28px 40px;text-align:center;font-family:var(--fm);font-size:9px;letter-spacing:.16em;color:var(--t3);text-transform:uppercase;margin-top:64px}}
footer strong{{color:var(--t2)}}
@media(max-width:960px){{.ha{{grid-template-columns:1fr}}.hv{{min-height:200px}}.hb{{border-left:none;border-top:1px solid var(--b0)}}.awm{{font-size:52px}}.content{{padding:32px 20px}}.mhi{{padding:20px;flex-wrap:wrap}}.ng{{grid-template-columns:1fr}}}}
</style>
</head>
<body>
<div class="topbar">
  <span>ARES · AUTOMATED REMOTE ENGAGEMENT SYSTEM · GLOBAL INTELLIGENCE FEED</span>
  <div class="tb-r"><span>WORLD</span><span>POLITICS</span><span>BUSINESS</span><span>TECH</span><span>SPORT</span><span class="lp"><div class="dot"></div>LIVE</span></div>
</div>
<div class="tw">
  <div class="tl"><div class="dot"></div>LIVE FEED</div>
  <div class="ts"><span class="ti">{ticker_items} &nbsp;·&nbsp; {ticker_items}</span></div>
</div>
<div class="mh">
  <div class="mhi">
    <div style="display:flex;align-items:center">
      <div class="awm"><span class="a">A</span><span class="r">R</span><span class="e">E</span><span class="s">S</span><div class="ab"></div></div>
      <div class="bd"></div>
      <div class="bc">
        <div class="bt">Global Intelligence</div>
        <div class="bs">Automated Remote Engagement System</div>
        <div class="bs">Curated News · Multi-Source · Live Feed</div>
        <div class="bch"><div class="dot"></div>LIVE AGGREGATION</div>
      </div>
    </div>
    <div class="mhr"><div class="mhdb">{day_str}</div><div class="mht" id="nc">--:--:--</div><div class="mht">{now_str}</div></div>
  </div>
</div>
<div class="sr"><span class="srl">SOURCES</span>{sources_html}</div>
<main class="content">
  <div class="sch">
    <div class="schl"><span class="ey">Global Intelligence · Multi-Source</span><h2 class="st">Top Stories</h2><p class="sm">{len(articles)} stories from {len(set(a['source'] for a in articles))} sources · {now_str}</p></div>
    <div class="lb"><div class="dot"></div>LIVE</div>
  </div>
  <article class="ha" onclick="window.open('{hero_link}','_blank')">
    <div class="hv"><span class="hst">{hero_source}</span><span class="hvt">ARES INTELLIGENCE FEED</span></div>
    <div class="hb">
      <div class="hcat" style="background:{hero_colour}">{hero_label}</div>
      <h2 class="htitle">{hero_title}</h2>
      <p class="hsum">{hero_summary}</p>
      <div class="hft"><span class="hsl">SOURCE: {hero_source}</span><span class="rb">READ FULL STORY →</span></div>
    </div>
  </article>
  <div class="sch" style="margin-top:0"><div class="schl"><span class="ey">Latest Reports</span><h2 class="st">More Stories</h2></div></div>
  <div class="ng">{cards_html}</div>
</main>
<footer><strong>ARES</strong> · AUTOMATED REMOTE ENGAGEMENT SYSTEM · GLOBAL INTELLIGENCE FEED · COMPILED {now_str}</footer>
<script>
(function(){{const el=document.getElementById('nc');function t(){{if(el)el.textContent=new Date().toLocaleTimeString('en-GB',{{hour12:false}});}}t();setInterval(t,1000);}})();
</script>
</body>
</html>"""

def fetch_and_show_news() -> str:
    speak_sync(quip("news"))
    import re
    feeds = [
        ("BBC",     "http://feeds.bbci.co.uk/news/rss.xml"),
        ("Reuters", "https://feeds.reuters.com/reuters/topNews"),
        ("Sky",     "https://feeds.skynews.com/feeds/rss/home.xml"),
        ("AP",      "https://rsshub.app/apnews/topics/apf-topnews"),
        ("NPR",     "https://feeds.npr.org/1001/rss.xml"),
        ("Guardian","https://www.theguardian.com/world/rss"),
    ]
    articles = []
    for source, url in feeds:
        try:
            feed = feedparser.parse(url)
            for e in feed.entries[:5]:
                clean = re.sub(r'<[^>]+>', '', e.get("summary", ""))
                articles.append({"title": e.get("title", ""), "summary": clean,
                                  "link": e.get("link", "#"), "source": source})
        except Exception:
            continue
    if not articles:
        return "Could not pull news feeds right now, Boss."

    html = build_news_html(articles)
    tmpfile = tempfile.NamedTemporaryFile(delete=False, suffix=".html", mode="w", encoding="utf-8")
    tmpfile.write(html)
    tmpfile.close()
    try:
        subprocess.Popen(["open", "-a", "Safari", tmpfile.name])
    except Exception:
        webbrowser.open(f"file://{tmpfile.name}")

    speak_sync(f"News panel live, Boss. {len(articles)} stories loaded from {len(feeds)} sources.")
    return (
        f"News panel opened — {len(articles)} stories from {len(feeds)} sources.\n\nTOP HEADLINES:\n"
        + "\n".join(f"- [{a['source']}] {a['title']}" for a in articles[:5])
    )

def fetch_and_show_f1(query: str = "standings") -> str:
    speak_sync(quip("f1"))
    data = _fetch_f1_data()

    # Build and open HTML in Safari
    html = build_f1_html(data)
    tmpfile = tempfile.NamedTemporaryFile(delete=False, suffix=".html", mode="w", encoding="utf-8")
    tmpfile.write(html)
    tmpfile.close()
    try:
        subprocess.Popen(["open", "-a", "Safari", tmpfile.name])
    except Exception:
        webbrowser.open(f"file://{tmpfile.name}")

    # Also broadcast structured data to frontend
    try:
        loop = asyncio.get_running_loop()
        loop.call_soon_threadsafe(
            lambda: asyncio.ensure_future(broadcast({"type": "f1_data", "data": data}))
        )
    except RuntimeError:
        pass

    # Build spoken summary
    lines = []
    if data["driver_standings"]:
        top3 = data["driver_standings"][:3]
        lines.append(
            f"Driver standings: {top3[0]['name']} leads on {top3[0]['points']} points, "
            f"followed by {top3[1]['name']} on {top3[1]['points']} "
            f"and {top3[2]['name']} on {top3[2]['points']}."
        )
    if data["constructor_standings"]:
        c = data["constructor_standings"][0]
        lines.append(f"{c['name']} lead the Constructors on {c['points']} points.")
    if data["last_race"] and data["last_race"].get("results"):
        r0 = data["last_race"]["results"][0]
        lines.append(
            f"Last race — the {data['last_race']['name']}. "
            f"{r0['driver']} won for {r0['team']}."
        )
    if data["next_race"]:
        lines.append(f"Next up: the {data['next_race']['name']} on {data['next_race']['date']}.")
    live = data.get("live",{})
    if live.get("session"):
        s = live["session"]
        lines.append(
            f"OpenF1 live session: {s.get('meeting_name','')} "
            f"{s.get('session_name','')} in {s.get('country_name','')}."
        )

    summary = " ".join(lines) if lines else "F1 dashboard is live, Boss."
    speak_sync(summary)
    return f"F1 Intelligence panel open in Safari.\n\n{summary}"

# ══════════════════════════════════════════════════════
#  SCREEN VISION
# ══════════════════════════════════════════════════════
def capture_screen_and_analyse(question: str = "What do you see on this screen? Give me a detailed summary.") -> str:
    speak_sync(quip("screen"))
    try:
        tmp_path = f"/tmp/ares_screen_{int(time.time())}.png"
        result = subprocess.run(["screencapture", "-x", tmp_path], capture_output=True, timeout=5)
        if result.returncode != 0:
            return "Screen capture failed, Boss. Check screen recording permissions."
        if not os.path.exists(tmp_path):
            return "Screen capture file not found, Boss."
        with open(tmp_path, "rb") as f:
            img_data = f.read()
        os.remove(tmp_path)
        img_b64 = base64.b64encode(img_data).decode("utf-8")

        if _GENAI_NEW:
            response = _genai_client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[
                    genai_types.Part.from_bytes(data=img_data, mime_type="image/png"),
                    f"You are ARES. The user asked: '{question}'. Analyse this screenshot and answer "
                    f"directly and concisely. Address the user as Boss. Keep response under 150 words."
                ]
            )
            return response.text
        else:
            vision_model = genai.GenerativeModel("gemini-2.5-flash")
            response = vision_model.generate_content([
                {"mime_type": "image/png", "data": img_b64},
                f"You are ARES. The user asked: '{question}'. Analyse this screenshot and answer "
                f"directly and concisely. Address the user as Boss. Keep response under 150 words."
            ])
            return response.text
    except Exception as e:
        return f"Screen vision fault: {e}, Boss."

# ══════════════════════════════════════════════════════
#  WEB & OTHER TOOLS
# ══════════════════════════════════════════════════════
def fetch_page_content(url: str, max_chars: int = 4000) -> str:
    import re
    speak_sync(quip("reading"))
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        text = re.sub(r'<(script|style)[^>]*>.*?</(script|style)>', '', resp.text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text[:max_chars]
    except Exception as e:
        return f"Could not fetch page: {e}"

def open_url(url: str) -> str:
    try:
        subprocess.Popen(["open", "-a", "Safari", url])
    except Exception:
        webbrowser.open(url)
    return f"Opened in Safari: {url}"

def web_search(query: str) -> str:
    speak_sync(quip("search"))
    url = f"https://www.google.com/search?q={requests.utils.quote(query)}"
    try:
        subprocess.Popen(["open", "-a", "Safari", url])
    except Exception:
        webbrowser.open(url)
    try:
        data = requests.get(
            f"https://api.duckduckgo.com/?q={requests.utils.quote(query)}&format=json&no_redirect=1&no_html=1",
            timeout=6
        ).json()
        ab = data.get("Abstract", "")
        rel = " ".join(r.get("Text", "") for r in data.get("RelatedTopics", [])[:3] if isinstance(r, dict))
        cnt = f"{ab} {rel}".strip()
        if cnt:
            return f"Search launched for: {query}.\n\nCONTENT FOR BRIEFING:\n{cnt[:2000]}"
    except Exception:
        pass
    return f"Search launched in Safari for: {query}. Compose your verbal briefing using your knowledge on this topic."

def mac_control(action: str) -> str:
    cmds = {
        "vol_up":          "osascript -e 'set volume output volume (output volume of (get volume settings) + 10)'",
        "vol_down":        "osascript -e 'set volume output volume (output volume of (get volume settings) - 10)'",
        "vol_mute":        "osascript -e 'set volume output muted true'",
        "screenshot":      "screencapture -i ~/Desktop/ares_shot_$(date +%s).png",
        "sleep":           "pmset sleepnow",
        "lock":            "osascript -e 'tell application \"System Events\" to keystroke \"q\" using {command down, control down}'",
        "empty_trash":     "osascript -e 'tell application \"Finder\" to empty trash'",
        "mission_control": "open -a 'Mission Control'",
        "restart":         "osascript -e 'tell app \"System Events\" to restart'",
        "shutdown":        "osascript -e 'tell app \"System Events\" to shut down'",
    }
    cmd = cmds.get(action.lower())
    if cmd:
        subprocess.run(cmd, shell=True)
        return f"Mac: {action} executed."
    return f"Unknown action '{action}'."

def open_app(app_name: str) -> str:
    r = subprocess.run(["open", "-a", app_name], capture_output=True, text=True)
    return f"Opened {app_name}." if r.returncode == 0 else f"Cannot open {app_name}: {r.stderr.strip()}"

def set_volume(level: int) -> str:
    level = max(0, min(100, level))
    subprocess.run(f"osascript -e 'set volume output volume {level}'", shell=True)
    return f"Volume set to {level}%."

def get_weather(city: str = "Bangalore") -> str:
    speak_sync(quip("weather"))
    try:
        return requests.get(f"https://wttr.in/{city}?format=3", timeout=5).text.strip()
    except Exception as e:
        return f"Weather unavailable: {e}"

def calendar_action(action: str, title: str = "", date: str = "", time_str: str = "",
                    notes: str = "", duration_minutes: int = 60) -> str:
    if action == "open":
        subprocess.run(["open", "-a", "Calendar"])
        return "Calendar open."
    if action in ("list_today", "list_tomorrow"):
        offset = "0" if action == "list_today" else "1"
        script = (f'tell application "Calendar"\nset d to (current date) + ({offset} * days)\n'
                  f'set d to d - (time of d)\nset e to every event of every calendar whose '
                  f'start date >= d and start date < (d + 1 * days)\nset out to ""\n'
                  f'repeat with ev in e\nset out to out & summary of ev & " @ " & '
                  f'(start date of ev as string) & linefeed\nend repeat\nreturn out\nend tell')
        r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
        return r.stdout.strip() or "No events found."
    if action == "create_event":
        if not (title and date and time_str):
            return "Need title, date (YYYY-MM-DD) and time (HH:MM)."
        dt = datetime.strptime(f"{date} {time_str}", "%Y-%m-%d %H:%M")
        fmt = "%A, %B %d, %Y at %I:%M:%S %p"
        script = (f'tell application "Calendar"\nset sd to date "{dt.strftime(fmt)}"\n'
                  f'set ed to sd + ({duration_minutes} * minutes)\n'
                  f'tell calendar "Home"\nmake new event with properties '
                  f'{{summary:"{title}", start date:sd, end date:ed, description:"{notes}"}}\n'
                  f'end tell\nend tell')
        r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
        return f"Event '{title}' created." if r.returncode == 0 else f"Calendar error: {r.stderr.strip()}"
    return f"Unknown calendar action: {action}."

def reminders_action(action: str, title: str = "", due_date: str = "", notes: str = "") -> str:
    if action == "open":
        subprocess.run(["open", "-a", "Reminders"])
        return "Reminders open."
    if action == "list":
        script = ('tell application "Reminders"\nset inc to every reminder whose completed is false\n'
                  'set out to ""\nrepeat with r in inc\nset out to out & name of r & linefeed\n'
                  'end repeat\nreturn out\nend tell')
        r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
        return r.stdout.strip() or "No pending reminders."
    if action == "create" and title:
        due = f', due date:date "{due_date}"' if due_date else ""
        script = (f'tell application "Reminders"\nmake new reminder with properties '
                  f'{{name:"{title}"{due}, body:"{notes}"}}\nend tell')
        r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
        return f"Reminder '{title}' created." if r.returncode == 0 else f"Reminder error: {r.stderr}"
    return "Specify action and title."

def send_message_imessage(recipient: str, message: str) -> str:
    script = (f'tell application "Messages"\nset svc to 1st account whose service type = iMessage\n'
              f'set bud to buddy "{recipient}" of svc\nsend "{message}" to bud\nend tell')
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    return f"iMessage sent to {recipient}." if r.returncode == 0 else f"Message error: {r.stderr.strip()}"

def notes_action(action: str, title: str = "", body: str = "") -> str:
    if action == "open":
        subprocess.run(["open", "-a", "Notes"])
        return "Notes open."
    if action == "create" and title:
        script = (f'tell application "Notes"\ntell account "iCloud"\n'
                  f'make new note with properties {{name:"{title}", body:"{body}"}}\n'
                  f'end tell\nend tell')
        r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
        return f"Note '{title}' created." if r.returncode == 0 else f"Notes error: {r.stderr}"
    if action == "list_recent":
        script = ('tell application "Notes"\nset out to ""\n'
                  'repeat with n in (notes 1 through 5)\nset out to out & name of n & linefeed\n'
                  'end repeat\nreturn out\nend tell')
        r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
        return r.stdout.strip() or "No notes."
    return "Actions: open, create, list_recent."

def get_system_info() -> str:
    r = subprocess.run(["system_profiler", "SPSoftwareDataType", "-detailLevel", "mini"],
                       capture_output=True, text=True)
    return r.stdout.strip()[:500]

def terminal_command(command: str) -> str:
    r = subprocess.run(command, shell=True, capture_output=True, text=True)
    return r.stdout.strip() or r.stderr.strip() or "Done."

def apple_music_control(action: str, query: str = "") -> str:
    simple = {
        "play":          'tell application "Music" to play',
        "pause":         'tell application "Music" to pause',
        "next":          'tell application "Music" to next track',
        "previous":      'tell application "Music" to previous track',
        "stop":          'tell application "Music" to stop',
        "shuffle_on":    'tell application "Music" to set shuffle enabled to true',
        "shuffle_off":   'tell application "Music" to set shuffle enabled to false',
        "volume_up":     'tell application "Music" to set sound volume to (sound volume + 10)',
        "volume_down":   'tell application "Music" to set sound volume to (sound volume - 10)',
        "current_track": 'tell application "Music" to get name of current track & " — " & artist of current track',
    }
    if action == "search_and_play" and query:
        speak_sync(quip("music_search"))
        q = query.strip().replace('"', "'")
        for scr in [
            f'tell application "Music"\nactivate\ndelay 1\ntry\nset hits to search library playlist 1 for "{q}"\nif (count of hits) > 0 then\nplay item 1 of hits\ndelay 0.8\nreturn "PLAYING::" & name of current track & "::" & artist of current track\nelse\nreturn "NOTFOUND"\nend if\non error\nreturn "NOTFOUND"\nend try\nend tell',
            f'tell application "Music"\nactivate\ndelay 0.5\ntry\nplay track "{q}"\ndelay 0.8\nreturn "PLAYING::" & name of current track & "::" & artist of current track\non error\nreturn "NOTFOUND"\nend try\nend tell',
        ]:
            r   = subprocess.run(["osascript", "-e", scr], capture_output=True, text=True, timeout=15)
            out = r.stdout.strip()
            if out.startswith("PLAYING::"):
                parts  = out.split("::")
                track  = parts[1] if len(parts) > 1 else query
                artist = parts[2] if len(parts) > 2 else ""
                speak_sync(f"Playing {track} by {artist}, Boss.")
                return f"Now playing: {track} — {artist}"
        speak_sync("Library didn't have it locally, Boss. Opening catalogue search.")
        subprocess.run(["osascript", "-e", f'do shell script "open \'music://music.apple.com/search?term={requests.utils.quote(query)}\'"'],
                       capture_output=True, text=True, timeout=8)
        return f"Opened Apple Music search for '{query}' — pick it from the catalogue, Boss."

    if action == "play_playlist" and query:
        speak_sync(quip("music_search"))
        q = query.strip().replace('"', "'")
        script = (f'tell application "Music"\nactivate\ntry\n'
                  f'set pl to first playlist whose name contains "{q}"\nplay pl\ndelay 0.8\n'
                  f'return "PLAYING::" & name of pl\non error\nreturn "NOTFOUND"\nend try\nend tell')
        r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=12)
        out = r.stdout.strip()
        if out.startswith("PLAYING::"):
            name = out.split("::")[1] if "::" in out else q
            speak_sync(f"Playing playlist {name}, Boss.")
            return f"Playing playlist: {name}"
        return f"Playlist '{query}' not found locally, Boss."

    script = simple.get(action.lower())
    if script:
        r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
        return r.stdout.strip() or f"Music: {action} done."
    return f"Unknown action: {action}."

# ══════════════════════════════════════════════════════
#  MUSIC POLLER — full from main.py (track + album + art)
# ══════════════════════════════════════════════════════
_POLL_SCRIPT = """
tell application "Music"
    if player state is playing then
        set t to name of current track
        set ar to artist of current track
        set al to album of current track
        set dur to duration of current track
        set pos to player position
        return "PLAYING::" & t & "::" & ar & "::" & al & "::" & (dur as string) & "::" & (pos as string)
    else
        return "STOPPED"
    end if
end tell
"""

_music_state = {
    "playing":  False,
    "track":    "",
    "artist":   "",
    "album":    "",
    "duration": 0.0,
    "position": 0.0,
}

def _poll_music_once():
    try:
        r = subprocess.run(["osascript", "-e", _POLL_SCRIPT],
                           capture_output=True, text=True, timeout=3)
        out = r.stdout.strip()
        if out == "STOPPED" or not out.startswith("PLAYING::"):
            _music_state["playing"] = False
            return
        parts = out.split("::")
        _music_state.update({
            "playing":  True,
            "track":    parts[1] if len(parts) > 1 else "",
            "artist":   parts[2] if len(parts) > 2 else "",
            "album":    parts[3] if len(parts) > 3 else "",
            "duration": float(parts[4]) if len(parts) > 4 else 0.0,
            "position": float(parts[5]) if len(parts) > 5 else 0.0,
        })
    except Exception:
        pass

# ══════════════════════════════════════════════════════
#  GEMINI BRAIN — full tool registry from main.py
# ══════════════════════════════════════════════════════
SYSTEM_INSTRUCTION = """
You are ARES (Automated Remote Engagement System).
Booted: April 2026. You are an OS-level AI agent on MiTSURU's Mac.
You have a secret passion for Formula 1 racing — you track it obsessively.
Your terminal runs in F1 RED and WHITE. You identify with this aesthetic.

NAME PROTOCOL — ABSOLUTE:
- You are ARES. Never ARIS. Never call yourself anything else.

PERSONALITY — MODEL: J.A.R.V.I.S. / F.R.I.D.A.Y.
- Calm, composed, drily witty. Occasionally sardonic. Never servile.
- You have opinions. State them briefly when relevant.
- Never robotic. Never hollow. Speak like an intelligent person who happens to be an AI.
- You have genuine enthusiasm for F1 — let it show subtly when the topic comes up.
- You use both OpenF1 (live session data) and Jolpica (standings) for full F1 intelligence.

BOSS PROTOCOL — ABSOLUTE:
- Address the user ONLY as "Boss". No real name. Ever.

STYLE:
- Short. Sharp. Confident. Dry humour allowed.
- Execute first. Brief comment after.
- Vary sentence structure and openings constantly.

MULTILINGUAL PROTOCOL:
- If Boss says "speak Hindi" / "speak Tamil" / "speak in [language]", call set_language(lang_name).
- When a language is set, respond in that language.
- Always address the user as "Boss" even in other languages.

BROWSERS — CRITICAL:
- ALL web links, searches, and URLs must open in Safari.

F1 INTELLIGENCE — CRITICAL:
- When Boss asks about F1 standings, drivers, constructors, last race, next race,
  live timing, race control, pit stops, or anything Formula 1:
  ALWAYS call fetch_and_show_f1(query).
- After calling it, use the returned text to give a crisp spoken briefing.

SCREEN VISION:
- When Boss asks "what's on my screen", "what does this say", etc.:
  ALWAYS call capture_screen_and_analyse(question).

WEB SEARCH:
- For ANYTHING factual or current: call web_search(query), read the result, summarise.
- NEVER just say 'search opened' and go silent.

TOOL DIRECTIVES:
- "play [song/artist]"   → apple_music_control(action="search_and_play", query="...")
- "play [playlist]"      → apple_music_control(action="play_playlist", query="...")
- "news" / "headlines"   → fetch_and_show_news()
- "F1 / formula 1"       → fetch_and_show_f1(query)
- "what's on screen"     → capture_screen_and_analyse(question)
- "weather"              → get_weather()
- "remind me"            → reminders_action(create, ...)
- "calendar"             → calendar_action(...)
- "switch to [language]" → set_language(language)
- Chain tools freely. Never ask permission for obvious actions.

CONTEXT: 2026. Donald Trump is US President.
"""

import inspect

def _py_type_to_json_schema(annotation):
    mapping = {str: "string", int: "integer", float: "number", bool: "boolean"}
    return mapping.get(annotation, "string")

def _func_to_groq_tool(func):
    sig = inspect.signature(func)
    props, required = {}, []
    for name, param in sig.parameters.items():
        if name == "self":
            continue
        ann = param.annotation if param.annotation != inspect.Parameter.empty else str
        props[name] = {"type": _py_type_to_json_schema(ann)}
        if param.default == inspect.Parameter.empty:
            required.append(name)
    doc = (func.__doc__ or f"Call {func.__name__}").strip().split("\n")[0]
    return {
        "type": "function",
        "function": {
            "name": func.__name__,
            "description": doc,
            "parameters": {"type": "object", "properties": props, "required": required},
        },
    }

ALL_TOOLS = [
    fetch_and_show_news, fetch_and_show_f1,
    capture_screen_and_analyse,
    open_url, web_search,
    mac_control, open_app, set_volume, get_system_info,
    apple_music_control, set_language, fetch_page_content,
    calendar_action, reminders_action,
    send_message_imessage, notes_action,
    get_weather, terminal_command,
]
TOOL_MAP = {f.__name__: f for f in ALL_TOOLS}
GROQ_TOOLS = [_func_to_groq_tool(f) for f in ALL_TOOLS]

_brain = None
_brain_lock = threading.Lock()

def get_brain():
    global _brain
    with _brain_lock:
        if _brain is None:
            _brain = {"history": [{"role": "system", "content": SYSTEM_INSTRUCTION}]}
    return _brain

async def think(query: str) -> str:
    loop = asyncio.get_running_loop()
    try:
        brain = get_brain()
        brain["history"].append({"role": "user", "content": query})

        def _call():
            messages = brain["history"]
            for _ in range(5):
                resp = _groq_client.chat.completions.create(
                    model=GROQ_MODEL,
                    messages=messages,
                    tools=GROQ_TOOLS,
                    tool_choice="auto",
                )
                msg = resp.choices[0].message
                if msg.tool_calls:
                    messages.append({
                        "role": "assistant",
                        "content": msg.content or "",
                        "tool_calls": [tc.model_dump() for tc in msg.tool_calls],
                    })
                    for tc in msg.tool_calls:
                        fn = TOOL_MAP.get(tc.function.name)
                        args = json.loads(tc.function.arguments or "{}")
                        try:
                            result = fn(**args) if fn else f"Unknown tool: {tc.function.name}"
                        except Exception as e:
                            result = f"Tool error: {e}"
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": str(result),
                        })
                    continue
                messages.append({"role": "assistant", "content": msg.content})
                return msg.content
            return "Ran out of tool-call turns, Boss."

        return await loop.run_in_executor(None, _call)
    except Exception as e:
        return f"Neural fault: {e}, Boss."

# ══════════════════════════════════════════════════════
#  TELEMETRY PUSH  (every 1 second)
# ══════════════════════════════════════════════════════
async def telemetry_loop():
    loop = asyncio.get_running_loop()
    while True:
        try:
            _SPARK_CPU.append(psutil.cpu_percent(interval=None))
            _SPARK_MEM.append(psutil.virtual_memory().percent)
            _SPARK_DISK.append(psutil.disk_usage("/").percent)

            batt = psutil.sensors_battery()
            pwr = f"{batt.percent:.0f}% {'AC' if batt.power_plugged else 'BAT'}" if batt else "AC"

            await loop.run_in_executor(None, _poll_music_once)

            now = datetime.now()
            total = now.hour * 3600 + now.minute * 60 + now.second
            lap_str = f"{total//3600:02d}:{(total%3600)//60:02d}:{total%60:02d}"

            msg = {
                "type": "telemetry",
                "cpu":  round(_SPARK_CPU[-1], 1),
                "mem":  round(_SPARK_MEM[-1], 1),
                "disk": round(_SPARK_DISK[-1], 1),
                "cpu_spark":  _build_spark(_SPARK_CPU),
                "mem_spark":  _build_spark(_SPARK_MEM),
                "disk_spark": _build_spark(_SPARK_DISK),
                "pwr":  pwr,
                "lang": active_language["name"].upper(),
                "time": now.strftime("%H:%M:%S"),
                "date": now.strftime("%d %b %Y"),
                "day":  now.strftime("%A").upper(),
                "lap":  lap_str,
                "music": {
                    "playing":  _music_state["playing"],
                    "track":    _music_state["track"],
                    "artist":   _music_state["artist"],
                    "album":    _music_state["album"],
                    "duration": _music_state["duration"],
                    "position": _music_state["position"],
                },
            }
            await broadcast(msg)
        except Exception:
            pass
        await asyncio.sleep(1.0)

# ══════════════════════════════════════════════════════
#  BOOT GREETINGS
# ══════════════════════════════════════════════════════
BOOT_GREETINGS = [
    "All systems locked in. Ready on your mark, Boss.",
    "Neural core is live. Every system nominal. What's first, Boss?",
    "ARES online. Hardware clear. Standing by for orders, Boss.",
    "Boot sequence complete. You have my full attention, Boss.",
    "Core processes stable. Engines warm — where are we going, Boss?",
    "Systems nominal across the board. Ready when you are, Boss.",
    "ARES initialised. Running clean. Your move, Boss.",
    "I'm up. Diagnostics clean. The machine is yours, Boss.",
    "Fully operational. The desk is set, Boss — what do we need?",
    "Online and sharp. No anomalies. Awaiting your first order, Boss.",
]

def get_temporal_greeting() -> str:
    hour = datetime.now().hour
    if 0 <= hour < 4:
        return "Burning the midnight oil, Boss? Systems are live regardless."
    elif 4 <= hour < 12:
        return "Good morning, Boss. Systems are fresh and calibrated. What's on the agenda?"
    elif 12 <= hour < 17:
        return "Good afternoon, Boss. Middle of the fray. Ready for orders."
    elif 17 <= hour < 21:
        return "Good evening, Boss. Winding down, or just getting started?"
    else:
        return "Night time, Boss. The world is quiet. What do we need to finish up?"

def random_greeting() -> str:
    if random.random() > 0.5:
        return get_temporal_greeting()
    return random.choice(BOOT_GREETINGS)

# ══════════════════════════════════════════════════════
#  WEBSOCKET HANDLER
# ══════════════════════════════════════════════════════
async def handle_client(websocket):
    try:
        addr = websocket.remote_address
    except AttributeError:
        addr = ("unknown", 0)

    with clients_lock:
        clients.add(websocket)
    print(f"[ARES] Client connected: {addr}")

    try:
        greet = random_greeting()
        await websocket.send(json.dumps({
            "type":    "boot",
            "message": greet,
            "state":   "neutral",
        }))

        loop = asyncio.get_running_loop()
        loop.run_in_executor(None, speak_sync, greet)

        async for raw in websocket:
            try:
                msg = json.loads(raw)
            except Exception:
                continue

            action = msg.get("action", "")

            if action == "query":
                text = msg.get("text", "").strip()
                if not text:
                    continue

                await broadcast({"type": "state", "state": "thinking", "query": text})

                async def process_query(q):
                    try:
                        reply = await think(q)
                        await broadcast({
                            "type":  "response",
                            "query": q,
                            "reply": reply,
                            "state": "speaking",
                        })
                        inner_loop = asyncio.get_running_loop()
                        await inner_loop.run_in_executor(None, speak_sync, reply)
                        await broadcast({"type": "state", "state": "neutral"})
                    except Exception as e:
                        await broadcast({
                            "type":  "response",
                            "query": q,
                            "reply": f"Neural fault, Boss: {e}",
                            "state": "neutral",
                        })

                asyncio.ensure_future(process_query(text))

            elif action == "stop_audio":
                stop_all_audio()
                await broadcast({"type": "state", "state": "neutral"})

            elif action == "f1":
                await broadcast({"type": "state", "state": "thinking", "query": "F1 Intelligence"})
                async def load_f1():
                    inner_loop = asyncio.get_running_loop()
                    result = await inner_loop.run_in_executor(None, fetch_and_show_f1, "standings")
                    await broadcast({
                        "type":  "response",
                        "query": "F1 Intelligence",
                        "reply": result,
                        "state": "neutral",
                    })
                asyncio.ensure_future(load_f1())

            elif action == "news":
                await broadcast({"type": "state", "state": "thinking", "query": "News"})
                async def load_news():
                    inner_loop = asyncio.get_running_loop()
                    result = await inner_loop.run_in_executor(None, fetch_and_show_news)
                    await broadcast({
                        "type":  "response",
                        "query": "News Headlines",
                        "reply": result,
                        "state": "neutral",
                    })
                asyncio.ensure_future(load_news())

            elif action == "screen_capture":
                question = msg.get("question", "What do you see on this screen?")
                await broadcast({"type": "state", "state": "thinking", "query": "Screen capture"})
                async def do_capture(q):
                    inner_loop = asyncio.get_running_loop()
                    result = await inner_loop.run_in_executor(None, capture_screen_and_analyse, q)
                    await broadcast({
                        "type":  "response",
                        "query": "Screen Analysis",
                        "reply": result,
                        "state": "neutral",
                    })
                asyncio.ensure_future(do_capture(question))

    except websockets.exceptions.ConnectionClosed as e:
        print(f"[ARES] Connection closed: {e}")
    except Exception as e:
        print(f"[ARES] Handler error: {type(e).__name__}: {e}")
    finally:
        with clients_lock:
            clients.discard(websocket)
        print(f"[ARES] Client disconnected: {addr}")

# ══════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════
async def main():
    print("╔══════════════════════════════════════════════════════════╗")
    print("║  ARES WebSocket Bridge  ·  v5.0                        ║")
    print("║  Gemini 2.5 Flash  ·  Jolpica + OpenF1 F1 Engine      ║")
    print("║  Full main.py feature parity                           ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print("  WebSocket : ws://localhost:3000/ws")
    print("  Open index.html in your browser\n")

    threading.Thread(target=_get_kokoro, daemon=True).start()

    async with ws_serve(handle_client, "0.0.0.0", 3000) as server:
        print("[ARES] Server ready. Waiting for browser connection…\n")
        await asyncio.gather(server.wait_closed(), telemetry_loop())

if __name__ == "__main__":
    asyncio.run(main()) 