#!/usr/bin/env python3
"""
ARES — Automated Remote Engagement System (Windows Edition)
Voice-first OS-level AI agent. Groq Open-Source Brain.
Kokoro TTS (primary) | Edge TTS (fallback) | Windows SAPI (emergency).

Build: v5.5-win (model auto-discovery + verified Apple Music playback)
Optional extras for full control:  pip install pycaw comtypes pyautogui pillow pywinauto winsdk
   (if winsdk won't install:  pip install winrt-runtime winrt-Windows.Media.Control
                                          winrt-Windows.Foundation winrt-Windows.Foundation.Collections)
.env keys: GROQ_API_KEY, GROQ_MODELS (optional), GROQ_VISION_MODEL (optional),
           ARES_MUSIC_COUNTRY, ARES_AUTO_ADMIN
Best viewed in Windows Terminal (Cascadia font) so the braille waves render.
"""

import os
import re
import sys
import inspect
import random
import asyncio
import psutil
import speech_recognition as sr
import subprocess
import requests
import feedparser
import webbrowser
import tempfile
import json
import math
import threading
import time
import base64
import pathlib
import shutil
import warnings
import numpy as np
import soundfile as sf
import edge_tts
from dotenv import load_dotenv, find_dotenv
from datetime import datetime, timedelta
from collections import deque
from bs4 import BeautifulSoup

warnings.filterwarnings("ignore")
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

IS_WIN = os.name == "nt"
BUILD = "v5.5-win"

if IS_WIN:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
    os.system("")

try:
    from tools import available_tools
except ImportError:
    available_tools = {}

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.layout import Layout
from rich.text import Text
from rich.table import Table
from rich.align import Align
from rich.box import ROUNDED, DOUBLE

load_dotenv(find_dotenv())
console = Console()
recognizer = sr.Recognizer()
recognizer.pause_threshold = 0.8
recognizer.non_speaking_duration = 0.8
recognizer.energy_threshold = 750
recognizer.dynamic_energy_threshold = True

# ══════════════════════════════════════════════════════════════════════
#  WAVE ENGINE — smooth braille waveforms (replaces every bar in the UI)
# ══════════════════════════════════════════════════════════════════════

_DOT = ((0x01, 0x08), (0x02, 0x10), (0x04, 0x20), (0x40, 0x80))


def _interp(samples, pos):
    n = len(samples)
    if n == 1:
        return samples[0]
    pos = max(0.0, min(pos, n - 1 - 1e-9))
    i = int(pos)
    f = pos - i
    return samples[i] * (1 - f) + samples[i + 1] * f


def braille_wave(samples, width, rows=1, styles=("red",)) -> Text:
    """Draw samples (-1..1) as a connected line using 2x4 braille dots per cell."""
    W, H = width * 2, rows * 4
    grid = [[0] * width for _ in range(rows)]
    prev = None
    for x in range(W):
        v = _interp(samples, x / max(W - 1, 1) * (len(samples) - 1))
        v = max(-1.0, min(1.0, v))
        y = int(round((1 - v) / 2 * (H - 1)))
        y0 = y if prev is None else prev
        for yy in range(min(y0, y), max(y0, y) + 1):
            grid[yy // 4][x // 2] |= _DOT[yy % 4][x % 2]
        prev = y
    out = Text(justify="center")
    for r, row in enumerate(grid):
        style = styles[min(r, len(styles) - 1)]
        out.append("".join(chr(0x2800 + b) for b in row), style=style)
        if r < rows - 1:
            out.append("\n")
    return out


def synth_wave(phase, amp=1.0, n=96):
    out = []
    for i in range(n):
        t = i / (n - 1)
        env = math.sin(math.pi * t) ** 0.7
        v = (0.55 * math.sin(2 * math.pi * 2 * t + phase)
             + 0.30 * math.sin(2 * math.pi * 5 * t - phase * 1.6)
             + 0.15 * math.sin(2 * math.pi * 9 * t + phase * 2.3))
        out.append(max(-1.0, min(1.0, v * env * amp)))
    return out


def wave_width(frac: float, pad: int) -> int:
    return max(16, int(console.size.width * frac) - pad)


# ══════════════════════════════════════════════════════════════════════
#  CROSS-PLATFORM AUDIO & OS HELPERS
# ══════════════════════════════════════════════════════════════════════

_say_proc = None


def clear_screen():
    os.system("cls" if IS_WIN else "clear")


def _ps(cmd: str, timeout: int = 30, stdout_only: bool = False) -> str:
    """Run a PowerShell command and return its output."""
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
            capture_output=True, text=True, timeout=timeout,
        )
        if stdout_only:
            return (r.stdout or "").strip()
        return ((r.stdout or "") or (r.stderr or "")).strip()
    except Exception as e:
        return f"PowerShell error: {e}"


def play_audio_file(file_path: str):
    file_path = os.path.abspath(file_path)
    if sys.platform == "darwin":
        subprocess.run(["afplay", file_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return
    if IS_WIN:
        import winsound
        if file_path.lower().endswith(".wav"):
            winsound.PlaySound(file_path, winsound.SND_FILENAME)
            return
        wav_converted = os.path.join(tempfile.gettempdir(), "ares_play_temp.wav")
        try:
            data, samplerate = sf.read(file_path)
            sf.write(wav_converted, data, samplerate)
            winsound.PlaySound(wav_converted, winsound.SND_FILENAME)
            return
        except Exception:
            pass
        safe_path = file_path.replace("'", "''")
        ps = (
            "Add-Type -AssemblyName presentationCore; "
            "$p = New-Object System.Windows.Media.MediaPlayer; "
            f"$p.Open([uri]'{safe_path}'); $p.Play(); Start-Sleep -Milliseconds 500; "
            "while($p.NaturalDuration.HasTimeSpan -and ($p.Position -lt $p.NaturalDuration.TimeSpan)) { Start-Sleep -Milliseconds 100 }"
        )
        subprocess.run(["powershell", "-NoProfile", "-Command", ps], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        try:
            subprocess.run(["aplay", "-q", file_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass


def system_say(text: str, block: bool = False):
    global _say_proc
    if sys.platform == "darwin":
        cmd = ["say", "-v", "Samantha", "-r", "185", text]
        subprocess.run(cmd) if block else subprocess.Popen(cmd)
    elif IS_WIN:
        safe = text.replace("'", "''")
        ps = f"Add-Type -AssemblyName System.Speech; (New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak('{safe}')"
        cmd = ["powershell", "-NoProfile", "-Command", ps]
        if block:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            _say_proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _exe_path(name: str) -> str:
    exe = name if name.lower().endswith(".exe") else name + ".exe"
    found = shutil.which(exe)
    if found:
        return found
    if IS_WIN:
        try:
            import winreg
            sub = rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{exe}"
            for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                try:
                    with winreg.OpenKey(hive, sub) as k:
                        val, _ = winreg.QueryValueEx(k, "")
                        if val and os.path.exists(val):
                            return val
                except OSError:
                    continue
        except Exception:
            pass
    return ""


BROWSER_TARGETS = {
    "chrome": "chrome", "google chrome": "chrome", "edge": "msedge", "microsoft edge": "msedge",
    "firefox": "firefox", "brave": "brave", "opera": "opera",
}


def open_browser(target: str, browser: str = "default"):
    try:
        if os.path.exists(target):
            target = pathlib.Path(target).resolve().as_uri()
    except Exception:
        pass
    if IS_WIN:
        exe_key = BROWSER_TARGETS.get(browser.lower().strip())
        if exe_key:
            path = _exe_path(exe_key)
            if path:
                subprocess.Popen([path, target])
                return
        try:
            os.startfile(target)
            return
        except Exception:
            pass
    elif sys.platform == "darwin" and browser.lower() in ("safari", "default"):
        try:
            subprocess.Popen(["open", "-a", "Safari", target])
            return
        except Exception:
            pass
    webbrowser.open(target)


# ══════════════════════════════════════════════════════════════════════
#  TELEMETRY HISTORY (rendered as waves)
# ══════════════════════════════════════════════════════════════════════

_HIST = 24
_SPARK_CPU = deque([0.0] * _HIST, maxlen=_HIST)
_SPARK_MEM = deque([0.0] * _HIST, maxlen=_HIST)
_SPARK_DISK = deque([0.0] * _HIST, maxlen=_HIST)
_spark_lock = threading.Lock()


def _update_sparklines():
    with _spark_lock:
        _SPARK_CPU.append(psutil.cpu_percent(interval=None))
        _SPARK_MEM.append(psutil.virtual_memory().percent)
        try:
            root = (os.path.splitdrive(os.getcwd())[0] + "\\") if IS_WIN else "/"
            _SPARK_DISK.append(psutil.disk_usage(root).percent)
        except Exception:
            _SPARK_DISK.append(_SPARK_DISK[-1])


def history_wave(hist: deque, width: int, colour: str) -> Text:
    samples = [v / 100.0 * 2 - 1 for v in hist]
    return braille_wave(samples, width, rows=1, styles=(colour,))


# ══════════════════════════════════════════════════════════════════════
#  MIC MONITOR
# ══════════════════════════════════════════════════════════════════════

_MIC_AMPLITUDES: deque = deque([0.0] * 64, maxlen=64)
_mic_amp_lock = threading.Lock()
_mic_monitor_active = False
_mic_monitor_thread = None


def _mic_monitor_loop(device_index: int):
    CHUNK, RATE = 1024, 16000
    try:
        import pyaudio
        pa = pyaudio.PyAudio()
        stream = pa.open(format=pyaudio.paInt16, channels=1, rate=RATE, input=True,
                         input_device_index=device_index, frames_per_buffer=CHUNK)
        while _mic_monitor_active:
            try:
                raw = stream.read(CHUNK, exception_on_overflow=False)
                arr = np.frombuffer(raw, dtype=np.int16).astype(np.float64)
                rms = float(np.sqrt(np.mean(arr ** 2))) if len(arr) else 0.0
                with _mic_amp_lock:
                    _MIC_AMPLITUDES.append(min(rms / 3000.0, 1.0))
            except Exception:
                with _mic_amp_lock:
                    _MIC_AMPLITUDES.append(0.0)
            time.sleep(0.05)
        stream.stop_stream()
        stream.close()
        pa.terminate()
    except Exception:
        t = 0.0
        while _mic_monitor_active:
            v = abs(math.sin(t * 4.7)) * (0.4 + 0.6 * abs(math.sin(t * 1.3)))
            with _mic_amp_lock:
                _MIC_AMPLITUDES.append(v)
            t += 0.05
            time.sleep(0.05)


def start_mic_monitor(device_index: int = 0):
    global _mic_monitor_active, _mic_monitor_thread
    _mic_monitor_active = True
    _mic_monitor_thread = threading.Thread(target=_mic_monitor_loop, args=(device_index,), daemon=True)
    _mic_monitor_thread.start()


def stop_mic_monitor():
    global _mic_monitor_active
    _mic_monitor_active = False


def mic_wave_samples(n: int = 120):
    with _mic_amp_lock:
        amps = list(_MIC_AMPLITUDES)
    phase = time.time() * 9
    out = []
    for i in range(n):
        a = min(1.0, max(amps[int(i * len(amps) / n)] * 1.6, 0.05))
        out.append(a * math.sin(i * 0.55 + phase))
    return out


# ══════════════════════════════════════════════════════════════════════
#  LAST QUERY TRACKER
# ══════════════════════════════════════════════════════════════════════

_last_query = ""
_query_lock = threading.Lock()


def set_last_query(q: str):
    global _last_query
    with _query_lock:
        _last_query = q


def get_last_query() -> str:
    with _query_lock:
        return _last_query


# ══════════════════════════════════════════════════════════════════════
#  KOKORO TTS
# ══════════════════════════════════════════════════════════════════════

KOKORO_VOICE_MAP = {"english": "am_adam", "french": "ff_siwis", "japanese": "jf_alpha"}
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
        chunks = [a for _, _, a in pipeline(clean, voice=voice, speed=1.05) if a is not None and len(a) > 0]
        if not chunks:
            return False
        wav_path = os.path.join(tempfile.gettempdir(), f"ares_voice_{time.time_ns()}.wav")
        sf.write(wav_path, np.concatenate(chunks), 24000)
        try:
            play_audio_file(wav_path)
        finally:
            try:
                os.remove(wav_path)
            except Exception:
                pass
        return True
    except Exception:
        return False


# ══════════════════════════════════════════════════════════════════════
#  MICROPHONE SELECTION
# ══════════════════════════════════════════════════════════════════════

def get_live_mic_index():
    try:
        mics = sr.Microphone.list_microphone_names()
        bad = ("output", "stereo mix", "speaker", "loopback")
        for i, name in enumerate(mics):
            low = name.lower()
            if any(b in low for b in bad):
                continue
            if any(x in low for x in ["external", "earphone", "headset", "airpods", "usb", "array", "realtek"]):
                return i
        for i, name in enumerate(mics):
            low = name.lower()
            if any(b in low for b in bad):
                continue
            if any(x in low for x in ["built-in", "microphone", "internal"]):
                return i
        return 0
    except Exception:
        return 0


MIC_INDEX = get_live_mic_index()

# ══════════════════════════════════════════════════════════════════════
#  LANGUAGE CONFIG
# ══════════════════════════════════════════════════════════════════════

LANGUAGE_MAP = {
    "hindi": ("hi-IN", "hi-IN", "hi-IN-MadhurNeural"),
    "tamil": ("ta-IN", "ta-IN", "ta-IN-ValluvarNeural"),
    "telugu": ("te-IN", "te-IN", "te-IN-MohanNeural"),
    "kannada": ("kn-IN", "kn-IN", "kn-IN-GaganNeural"),
    "bengali": ("bn-IN", "bn-IN", "bn-IN-BashkarNeural"),
    "marathi": ("mr-IN", "mr-IN", "mr-IN-ManoharNeural"),
    "gujarati": ("gu-IN", "gu-IN", "gu-IN-NiranjanNeural"),
    "punjabi": ("pa-IN", "pa-IN", "pa-IN-OjasNeural"),
    "malayalam": ("ml-IN", "ml-IN", "ml-IN-MidhunNeural"),
    "english": ("en-IN", "en-IN", "en-AU-KenNeural"),
    "french": ("fr-FR", "fr-FR", "fr-FR-HenriNeural"),
    "spanish": ("es-ES", "es-ES", "es-ES-AlvaroNeural"),
    "german": ("de-DE", "de-DE", "de-DE-KilianNeural"),
    "japanese": ("ja-JP", "ja-JP", "ja-JP-KeitaNeural"),
    "arabic": ("ar-SA", "ar-SA", "ar-SA-HamedNeural"),
}

active_language = {"name": "english", "stt_lang": "en-IN", "tts_lang": "en-IN", "speaker": "en-AU-KenNeural"}


def set_language(lang_name: str) -> str:
    lang_key = lang_name.lower().strip()
    if lang_key in LANGUAGE_MAP:
        stt, tts, speaker = LANGUAGE_MAP[lang_key]
        active_language.update({"name": lang_key, "stt_lang": stt, "tts_lang": tts, "speaker": speaker})
        return f"Switched to {lang_name.title()}, Boss. Ready."
    return f"Language '{lang_name}' not in my registry. Available: {', '.join(LANGUAGE_MAP.keys())}."


# ══════════════════════════════════════════════════════════════════════
#  GREETINGS & QUIPS
# ══════════════════════════════════════════════════════════════════════

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
    return "Night time, Boss. The world is quiet. What do we need to finish up?"


QUIPS = {
    "music_search": ["On it, Boss. Scanning track.", "Queuing it up right now, Boss."],
    "news": ["Pulling the latest feeds, Boss. Stand by.", "Scanning global headlines. One moment."],
    "thinking": ["Processing that, Boss.", "On it.", "Let me work on that.", "Running that now."],
    "shutdown": ["Understood. Going dark, Boss. Until next time.", "Core shutdown initiated. Stay sharp, Boss."],
    "weather": ["Checking atmospheric data, Boss.", "Pulling weather now."],
    "calendar": ["Accessing your calendar, Boss.", "Checking the schedule."],
    "search": ["Opening search, Boss.", "Searching now, Boss."],
    "reading": ["Reading page content now, Boss."],
    "f1": ["Pulling pit wall telemetry, Boss.", "Dialling into the timing tower, Boss."],
}


def quip(category: str) -> str:
    return random.choice(QUIPS.get(category, ["On it, Boss."]))


# ══════════════════════════════════════════════════════════════════════
#  UI — PALETTE, LAYOUT, PANELS
# ══════════════════════════════════════════════════════════════════════

PALETTE = {
    "neutral": ("bold white", "white", "STANDBY"),
    "listening": ("bold red", "red", "LISTENING"),
    "thinking": ("bold yellow", "yellow", "PROCESSING"),
    "speaking": ("bold white", "white", "TRANSMITTING"),
    "error": ("bold bright_red", "bright_red", "FAULT"),
    "typing": ("bold cyan", "cyan", "TEXT INPUT"),
}

STATE_AMP = {"neutral": 0.12, "listening": 0.5, "thinking": 0.7, "speaking": 0.9, "typing": 0.3, "error": 0.9}


def make_ares_layout():
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=23),
        Layout(name="body"),
        Layout(name="statusbar", size=5),
    )
    layout["header"].split_row(
        Layout(name="logo_pane", ratio=3),
        Layout(name="right_col", ratio=2),
    )
    layout["right_col"].split_column(
        Layout(name="telemetry_pane", size=10),
        Layout(name="nameplate_pane"),
    )
    layout["statusbar"].split_row(
        Layout(name="footer", ratio=3),
        Layout(name="status_aux", ratio=1),
    )
    return layout


def get_telemetry():
    _update_sparklines()
    cpu, mem, disk = _SPARK_CPU[-1], _SPARK_MEM[-1], _SPARK_DISK[-1]
    batt = None
    try:
        batt = psutil.sensors_battery()
    except Exception:
        pass
    pwr = f"{batt.percent:.0f}% {'AC' if batt.power_plugged else 'BATTERY'}" if batt else "AC POWER"
    engine = "KOKORO" if active_language["name"] in KOKORO_VOICE_MAP else "EDGE TTS"

    def col(v):
        return "green" if v < 50 else ("yellow" if v < 80 else "bright_red")

    waves = Table.grid(padding=(0, 1), expand=True)
    waves.add_column(style="bold red", no_wrap=True, width=4)
    waves.add_column(no_wrap=True, ratio=1)
    waves.add_column(justify="right", no_wrap=True, width=5)
    ww = max(10, int(console.size.width * 0.4) - 20)
    for label, hist in (("CPU", _SPARK_CPU), ("MEM", _SPARK_MEM), ("DISK", _SPARK_DISK)):
        v = hist[-1]
        waves.add_row(label, history_wave(hist, ww, col(v)), Text(f"{v:.0f}%", style=f"bold {col(v)}"))

    info = Table.grid(padding=(0, 1))
    info.add_column(style="bold red", no_wrap=True, width=5)
    info.add_column(style="white", no_wrap=True)
    info.add_row("PWR", pwr)
    info.add_row("LANG", active_language["name"].upper())
    info.add_row("MODEL", "GROQ OPEN-SRC")
    info.add_row("TTS", engine)
    info.add_row("BUILD", f"ARES {BUILD.upper()}")

    return Panel(Group(waves, info), title="[bold red]TELEMETRY[/bold red]",
                 border_style="red", box=ROUNDED, padding=(0, 1))


def build_nameplate_panel(state: str = "neutral") -> Panel:
    bold, base, status_label = PALETTE.get(state, PALETTE["neutral"])
    query = get_last_query()
    q_disp = (query[:30] + "…") if len(query) > 30 else (query or "awaiting input")

    header = Table.grid(expand=True)
    header.add_column(justify="left")
    header.add_column(justify="right")
    header.add_row(Text(" FIA · SUPER LICENCE"), Text("ARES-WIN "), style="bold white on red")

    photo = Text("\n".join([
        "╭────────╮",
        "│        │",
        "│   01   │",
        "│  ────  │",
        "│ DRIVER │",
        "╰────────╯",
    ]), style="bold red")

    fields = Table.grid(padding=(0, 1))
    fields.add_column(style="dim red", no_wrap=True)
    fields.add_column(style="bold white", no_wrap=True)
    fields.add_row("SURNAME", "MiTSURU")
    fields.add_row("CLASS", "Principal Driver")
    fields.add_row("LICENCE", "ARES-0001-WIN")
    fields.add_row("ISSUED", "2026 · No expiry")
    fields.add_row("LOCAL", datetime.now().strftime("%H:%M"))
    fields.add_row("STATUS", Text(status_label, style=bold))

    body = Table.grid(padding=(0, 2))
    body.add_row(photo, fields)

    order = Text.assemble(("ORDER  ", "dim red"), (q_disp, "bold white"))

    sig = braille_wave(synth_wave(1.3, 0.85, 64), 18, rows=1, styles=("red",))
    sig.justify = "left"
    sign_row = Text.assemble(("SIGN   ", "dim red"))
    sign_row.append_text(sig)

    mrz = Text("P<ARES<<MITSURU<<<<<<<<<<<<<<<<<", style="dim red")

    return Panel(Group(header, Text(""), body, Text(""), order, sign_row, mrz),
                 title="[bold red]DRIVER LICENCE[/bold red]",
                 border_style=base, box=ROUNDED, padding=(0, 1))


ARES_LOGO = (
    " █████╗ ██████╗ ███████╗███████╗\n"
    "██╔══██╗██╔══██╗██╔════╝██╔════╝\n"
    "███████║██████╔╝█████╗  ███████╗\n"
    "██╔══██║██╔══██╗██╔══╝  ╚════██║\n"
    "██║  ██║██║  ██║███████╗███████║\n"
    "╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝╚══════╝"
)
ARES_TAGLINE = "AUTOMATED  ·  REMOTE  ·  ENGAGEMENT  ·  SYSTEM"


def get_logo(state: str = "neutral") -> Panel:
    bold, base, label = PALETTE.get(state, PALETTE["neutral"])
    amp = STATE_AMP.get(state, 0.12)
    lines = ARES_LOGO.split("\n")
    w = max(len(l) for l in lines)
    logo = Text("\n".join(l.ljust(w) for l in lines), style=f"bold {base}", justify="center")
    top = braille_wave(synth_wave(0.0, amp, 120), 46, rows=2, styles=(f"dim {base}", f"bold {base}"))
    bot = braille_wave(synth_wave(2.1, amp, 120), 46, rows=2, styles=(f"bold {base}", f"dim {base}"))
    status = Text(f"STATUS · {label}", style=f"bold {base}", justify="center")
    tag = Text(ARES_TAGLINE, style=f"dim {base}", justify="center")
    return Panel(
        Group(top, Text(""), logo, Text(""), tag, Text(""), bot, status),
        title=f"[{bold}]A · R · E · S[/{bold}]",
        subtitle=f"[dim {base}]AUTOMATED REMOTE ENGAGEMENT SYSTEM · {BUILD.upper()} · 2026[/dim {base}]",
        border_style=base, box=DOUBLE, padding=(0, 1),
    )


def body_panel(title: str, content, border: str = "red"):
    return Panel(content, title=f"[bold {border}]{title}[/bold {border}]",
                 border_style=border, box=ROUNDED, padding=(1, 2))


def footer_panel(msg: str, colour: str = "red"):
    ts = datetime.now().strftime("%H:%M:%S")
    return Panel(Text(f" [{ts}]  {msg}", style=f"bold {colour}"), border_style=colour, box=ROUNDED, padding=(0, 1))


def status_aux_panel(state: str = "neutral"):
    bold, base, label = PALETTE.get(state, PALETTE["neutral"])
    dot = "●" if int(time.time() * 2) % 2 == 0 else "○"
    content = Text()
    content.append(f" {dot} ARES {BUILD}\n", style=f"bold {base}")
    content.append(f" > {label}", style=f"dim {base}")
    return Panel(content, border_style=base, box=ROUNDED, padding=(0, 0))


def footer_wave_panel(state: str = "speaking"):
    ts = datetime.now().strftime("%H:%M:%S")
    amp = 0.55 + 0.4 * abs(math.sin(time.time() * 3.1))
    wave = braille_wave(synth_wave(time.time() * 5, amp, 140), wave_width(0.75, 6),
                        rows=3, styles=("red", "bold white", "red"))
    return Panel(wave, title="[bold white]VOCAL SYNTHESIS[/bold white]", subtitle=f"[dim white]{ts}[/dim white]",
                 border_style="white", box=ROUNDED, padding=(0, 1))


def footer_waveform_panel():
    ts = datetime.now().strftime("%H:%M:%S")
    wave = braille_wave(mic_wave_samples(140), wave_width(0.75, 6), rows=3, styles=("red", "bold red", "red"))
    return Panel(wave, title="[bold red]MIC · CAPTURING[/bold red]", subtitle=f"[dim red]{ts}[/dim red]",
                 border_style="red", box=ROUNDED, padding=(0, 1))


def build_input_panel(query: str) -> Panel:
    q = query[:90] + ("…" if len(query) > 90 else "")
    content = Text()
    content.append("ORDER RECEIVED\n\n", style="bold red")
    content.append("MiTSURU  ▸  ", style="dim red")
    content.append(q, style="bold white")
    return body_panel("INPUT CONFIRMED", content, "red")


_MATRIX_CHARS = "ARESF1OPENF1JOLPICALAMAKOKORO0123456789!@#$%^&*"


async def matrix_rain(dashboard, duration: float = 1.5):
    COLS, ROWS = 80, 18
    columns = [{"head": random.randint(0, ROWS), "speed": random.uniform(0.3, 1.0),
                "chars": [random.choice(_MATRIX_CHARS) for _ in range(ROWS)]} for _ in range(COLS)]
    dashboard["telemetry_pane"].update(get_telemetry())
    start = time.time()
    while time.time() - start < duration:
        content = Text()
        for row in range(ROWS):
            for cd in columns:
                dist = cd["head"] - row
                ch = cd["chars"][row % len(cd["chars"])]
                if dist == 0:
                    content.append(ch, style="bold bright_white")
                elif 0 < dist <= 3:
                    content.append(ch, style="bold red")
                elif 0 < dist <= 7:
                    content.append(ch, style="red")
                elif 0 < dist <= 12:
                    content.append(ch, style="dim red")
                else:
                    content.append(" ")
            content.append("\n")
        for cd in columns:
            cd["head"] += cd["speed"]
            if cd["head"] > ROWS + 4:
                cd["head"] = random.randint(-4, 0)

        pct = min(1.0, (time.time() - start) / duration)
        boot = braille_wave(synth_wave(time.time() * 6, 0.2 + 0.8 * pct, 140), wave_width(0.75, 6),
                            rows=3, styles=("red", "bold white", "red"))
        dashboard["body"].update(Panel(Align.center(content), title="[bold red]ARES · BOOT[/bold red]",
                                       border_style="red", box=DOUBLE))
        dashboard["footer"].update(Panel(boot, title=f"[bold red]INITIALIZING · {int(pct * 100):3d}%[/bold red]",
                                         border_style="red", box=ROUNDED, padding=(0, 1)))
        dashboard["status_aux"].update(status_aux_panel("neutral"))
        dashboard["logo_pane"].update(get_logo("neutral"))
        dashboard["nameplate_pane"].update(build_nameplate_panel("neutral"))
        await asyncio.sleep(0.08)


def _check_for_type_trigger() -> bool:
    if IS_WIN:
        try:
            import msvcrt
            if msvcrt.kbhit():
                return msvcrt.getwch().lower() == "t"
            return False
        except Exception:
            return False
    try:
        import termios, tty, select
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            rlist, _, _ = select.select([sys.stdin], [], [], 0.0)
            return bool(rlist) and sys.stdin.read(1).lower() == "t"
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
    except Exception:
        return False


# ══════════════════════════════════════════════════════════════════════
#  GROQ MODEL DISCOVERY (so retired models never break ARES again)
# ══════════════════════════════════════════════════════════════════════

GROQ_BASE = "https://api.groq.com/openai/v1"
GROQ_URL = f"{GROQ_BASE}/chat/completions"

# Current known-good defaults; auto-discovery replaces them if Groq retires any.
DEFAULT_GROQ_MODELS = "openai/gpt-oss-120b,openai/gpt-oss-20b"

_NON_CHAT_WORDS = ("whisper", "tts", "guard", "safeguard", "orpheus", "embed", "compound", "playai")
_CHAT_PREFERENCE = ("gpt-oss-120b", "gpt-oss-20b", "llama-3.3", "llama-4", "qwen")
_VISION_PREFERENCE = ("scout", "maverick", "vision", "qwen")
_vision_model_cache = {"id": None}


def _groq_list_models(api_key: str) -> list:
    """Return active model ids for this API key ([] on failure)."""
    try:
        r = requests.get(f"{GROQ_BASE}/models", headers={"Authorization": f"Bearer {api_key}"}, timeout=10)
        if r.status_code != 200:
            return []
        return [m["id"] for m in r.json().get("data", []) if m.get("active", True) and m.get("id")]
    except Exception:
        return []


def discover_chat_models(api_key: str) -> list:
    ids = [i for i in _groq_list_models(api_key) if not any(w in i.lower() for w in _NON_CHAT_WORDS)]

    def rank(i):
        low = i.lower()
        for n, p in enumerate(_CHAT_PREFERENCE):
            if p in low:
                return n
        return len(_CHAT_PREFERENCE)

    return sorted(ids, key=rank)


def pick_vision_model(api_key: str) -> str:
    env = os.getenv("GROQ_VISION_MODEL", "").strip()
    if env:
        return env
    if _vision_model_cache["id"]:
        return _vision_model_cache["id"]
    ids = _groq_list_models(api_key)
    for p in _VISION_PREFERENCE:
        for i in ids:
            if p in i.lower() and not any(w in i.lower() for w in _NON_CHAT_WORDS):
                _vision_model_cache["id"] = i
                return i
    return ""


# ══════════════════════════════════════════════════════════════════════
#  GROQ VISION API
# ══════════════════════════════════════════════════════════════════════

def capture_screen_and_analyse(question: str = "What do you see on this screen? Give me a detailed summary.") -> str:
    """Take a screenshot and describe what is on the screen."""
    try:
        tmp_path = os.path.join(tempfile.gettempdir(), f"ares_screen_{int(time.time())}.png")
        if sys.platform == "darwin":
            r = subprocess.run(["screencapture", "-x", tmp_path], capture_output=True, timeout=5)
            if r.returncode != 0:
                return "Screen capture failed, Boss."
        else:
            from PIL import ImageGrab
            img = ImageGrab.grab(all_screens=True) if IS_WIN else ImageGrab.grab()
            img.save(tmp_path)

        with open(tmp_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode("utf-8")

        try:
            os.remove(tmp_path)
        except Exception:
            pass

        api_key = os.getenv("GROQ_API_KEY", "").strip()
        if not api_key:
            return "Vision fault: GROQ_API_KEY is missing from your .env file, Boss."

        model = pick_vision_model(api_key)
        if not model:
            return ("Vision fault: no vision-capable model found on your Groq account, Boss. "
                    "Set GROQ_VISION_MODEL in .env to a model that accepts images.")

        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": f"You are ARES, an AI assistant. The user asked: '{question}'. Analyse this screenshot and answer directly and concisely. Address the user as Boss. Under 150 words."},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}}
                    ]
                }
            ],
            "temperature": 0.4
        }

        r = requests.post(GROQ_URL, headers={"Authorization": f"Bearer {api_key}"},
                          json=payload, timeout=30)

        if r.status_code != 200:
            return f"Vision fault ({model}): HTTP {r.status_code}: {r.text[:150]}"

        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"Screen vision fault: {e}, Boss."


# ══════════════════════════════════════════════════════════════════════
#  F1
# ══════════════════════════════════════════════════════════════════════

JOLPICA_BASE = "http://api.jolpi.ca/ergast/f1"


def _fetch_f1_data() -> dict:
    data = {"driver_standings": [], "constructor_standings": [], "season": str(datetime.now().year)}
    headers = {"User-Agent": "ARES/5.0 F1Intelligence"}
    try:
        r = requests.get(f"{JOLPICA_BASE}/current/driverStandings/", headers=headers, timeout=8).json()
        sl = r["MRData"]["StandingsTable"]["StandingsLists"]
        if sl:
            data["season"] = sl[0].get("season", data["season"])
            for s in sl[0]["DriverStandings"][:10]:
                drv = s["Driver"]
                cons = s.get("Constructors", [{}])
                data["driver_standings"].append({
                    "pos": s["position"], "name": f"{drv['givenName']} {drv['familyName']}",
                    "code": drv.get("code", "???"), "team": cons[0].get("name", "Unknown") if cons else "Unknown",
                    "points": s["points"], "wins": s["wins"],
                })
    except Exception:
        pass
    return data


def build_f1_html(data: dict) -> str:
    rows = "".join(
        f"<tr><td>{d['pos']}</td><td><b>{d['code']}</b></td><td>{d['name']}</td><td>{d['team']}</td><td>{d['points']} PTS</td></tr>"
        for d in data.get("driver_standings", []))
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'><title>ARES F1</title><style>"
        "body{background:#080808;color:#fff;font-family:sans-serif;padding:30px}"
        "table{width:100%;border-collapse:collapse;margin-top:20px}"
        "th,td{padding:12px;border-bottom:1px solid #222;text-align:left}th{color:#E10600}</style></head><body>"
        f"<h1 style='color:#E10600'>ARES · F1 STANDINGS ({data.get('season')})</h1><table><thead><tr>"
        "<th>POS</th><th>CODE</th><th>DRIVER</th><th>TEAM</th><th>POINTS</th></tr></thead>"
        f"<tbody>{rows}</tbody></table></body></html>")


def fetch_and_show_f1(query: str = "standings") -> str:
    """Fetch and display current Formula 1 standings."""
    speak_async(quip("f1"))
    data = _fetch_f1_data()
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".html", mode="w", encoding="utf-8")
    tmp.write(build_f1_html(data))
    tmp.close()
    open_browser(tmp.name)
    top = data["driver_standings"][:3]
    summary = (f"Standings live: {top[0]['name']} leads on {top[0]['points']} pts, followed by "
               f"{top[1]['name']} on {top[1]['points']}.") if len(top) >= 2 else "F1 Dashboard is online, Boss."
    return f"F1 panel opened in browser.\n\n{summary}"


# ══════════════════════════════════════════════════════════════════════
#  AUDIO ENGINE
# ══════════════════════════════════════════════════════════════════════

def stop_all_audio():
    global _say_proc
    if IS_WIN:
        try:
            import winsound
            winsound.PlaySound(None, winsound.SND_PURGE)
        except Exception:
            pass
        if _say_proc is not None:
            try:
                _say_proc.terminate()
            except Exception:
                pass
            _say_proc = None
        return
    for proc in ("afplay", "say"):
        try:
            subprocess.run(["killall", proc], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass


def _edge_tts_speak_blocking(text: str) -> bool:
    try:
        clean = text.replace("'", "").replace('"', "").replace("*", "").replace("#", "").strip()
        voice = active_language.get("speaker", "en-AU-KenNeural")
        mp3_path = os.path.join(tempfile.gettempdir(), f"ares_quip_{time.time_ns()}.mp3")
        subprocess.run([sys.executable, "-m", "edge_tts", "--voice", voice, "--rate=+5%", "--text", clean,
                        "--write-media", mp3_path], check=True, timeout=10,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        play_audio_file(mp3_path)
        return True
    except Exception:
        return False


def speak_sync(text: str):
    stop_all_audio()
    if _kokoro_speak_blocking(text):
        return
    if _edge_tts_speak_blocking(text):
        return
    system_say(text, block=False)


_final_speaking = threading.Event()


def speak_async(text: str):
    if _final_speaking.is_set():
        return
    threading.Thread(target=lambda: None if _final_speaking.is_set() else speak_sync(text), daemon=True).start()


def _short(text: str, limit: int = 240) -> str:
    t = re.sub(r"[*#`_>]", "", text or "").replace("\n", " ").strip()
    parts = re.split(r"(?<=[.!?])\s+", t)
    out = ""
    for s in parts[:3]:
        if len(out) + len(s) > limit and out:
            break
        out += (" " if out else "") + s
    return out[:limit] or "Done, Boss."


def fetch_page_content(url: str, max_chars: int = 4000) -> str:
    """Fetch a web page and return its readable text."""
    speak_async(quip("reading"))
    try:
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style"]):
            tag.decompose()
        return soup.get_text(separator=" ", strip=True)[:max_chars]
    except Exception as e:
        return f"Could not read page: {e}"


def fetch_and_show_news() -> str:
    """Fetch the latest top news headlines."""
    speak_async(quip("news"))
    feeds = [("BBC", "http://feeds.bbci.co.uk/news/rss.xml"),
             ("Reuters", "https://feeds.reuters.com/reuters/topNews")]
    articles = []
    for src, url in feeds:
        try:
            for e in feedparser.parse(url).entries[:4]:
                articles.append(f"[{src}] {e.title}")
        except Exception:
            continue
    summary = "\n".join(articles[:5]) if articles else "Headlines unavailable right now, Boss."
    return f"TOP STORIES:\n{summary}"


# ══════════════════════════════════════════════════════════════════════
#  WINDOWS CONTROL LAYER
# ══════════════════════════════════════════════════════════════════════

_DATA_DIR = os.path.join(os.path.expanduser("~"), "ARES_Data")
_HOME = os.path.expanduser("~")

APP_ALIASES = {
    "chrome": "chrome", "google chrome": "chrome", "edge": "msedge", "microsoft edge": "msedge",
    "firefox": "firefox", "brave": "brave", "opera": "opera",
    "notepad": "notepad", "calculator": "calc", "paint": "mspaint", "wordpad": "write",
    "explorer": "explorer", "file explorer": "explorer", "files": "explorer",
    "cmd": "cmd", "command prompt": "cmd", "powershell": "powershell", "terminal": "wt",
    "task manager": "taskmgr", "control panel": "control", "settings": "ms-settings:",
    "snipping tool": "snippingtool", "word": "winword", "excel": "excel", "powerpoint": "powerpnt",
    "outlook": "outlook", "onenote": "onenote", "teams": "msteams:", "store": "ms-windows-store:",
    "vs code": "code", "vscode": "code", "visual studio code": "code", "code": "code",
    "spotify": "spotify", "discord": "discord", "steam": "steam", "whatsapp": "whatsapp:",
    "camera": "microsoft.windows.camera:", "clock": "ms-clock:", "calendar": "outlookcal:",
    "photos": "ms-photos:", "maps": "bingmaps:", "xbox": "xbox:",
}

PROCESS_ALIASES = {
    "chrome": "chrome", "google chrome": "chrome", "edge": "msedge", "microsoft edge": "msedge",
    "firefox": "firefox", "notepad": "notepad", "calculator": "calculator", "word": "winword",
    "excel": "excel", "powerpoint": "powerpnt", "vs code": "code", "vscode": "code",
    "spotify": "spotify", "discord": "discord", "apple music": "applemusic",
    "task manager": "taskmgr", "terminal": "windowsterminal",
}


def _jload(name: str) -> list:
    try:
        with open(os.path.join(_DATA_DIR, name), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _jsave(name: str, data: list):
    os.makedirs(_DATA_DIR, exist_ok=True)
    with open(os.path.join(_DATA_DIR, name), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _start(target: str) -> bool:
    try:
        return subprocess.run(["cmd", "/c", "start", "", target], capture_output=True).returncode == 0
    except Exception:
        return False


def _find_start_app(name: str) -> str:
    q = name.replace("'", "''")
    out = _ps(f"Get-StartApps | Where-Object {{ $_.Name -like '*{q}*' }} | "
              f"Select-Object -First 1 -ExpandProperty AppID", stdout_only=True)
    return out.splitlines()[0].strip() if out else ""


def open_app(app_name: str) -> str:
    """Open or launch an application by name."""
    if not IS_WIN:
        r = subprocess.run(["open", "-a", app_name], capture_output=True, text=True)
        return f"Opened {app_name}." if r.returncode == 0 else f"Cannot open {app_name}."
    key = app_name.lower().strip()
    target = APP_ALIASES.get(key)
    if target:
        if not target.endswith(":"):
            exe = _exe_path(target)
            if exe:
                subprocess.Popen([exe])
                return f"Opened {app_name}."
        if _start(target):
            return f"Opened {app_name}."
    appid = _find_start_app(app_name)
    if appid:
        subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{appid}"])
        return f"Opened {app_name}."
    exe = _exe_path(app_name)
    if exe:
        subprocess.Popen([exe])
        return f"Opened {app_name}."
    return f"Couldn't find an app called '{app_name}', Boss."


def close_app(app_name: str) -> str:
    """Close a running application by name."""
    key = app_name.lower().strip()
    needle = PROCESS_ALIASES.get(key, key.replace(" ", ""))
    killed = 0
    for p in psutil.process_iter(["name"]):
        try:
            if needle in (p.info["name"] or "").lower().replace(" ", ""):
                p.terminate()
                killed += 1
        except Exception:
            continue
    return f"Closed {app_name} ({killed} process{'es' if killed != 1 else ''})." if killed else f"{app_name} isn't running, Boss."


def list_running_apps() -> str:
    """List apps that currently have a window open."""
    if not IS_WIN:
        return "Only supported on Windows."
    out = _ps("Get-Process | Where-Object { $_.MainWindowTitle } | "
              "Select-Object -First 25 ProcessName, MainWindowTitle | Format-Table -HideTableHeaders | Out-String")
    return out or "No windowed apps found."


def open_url(url: str, browser: str = "default") -> str:
    """Open a website URL, optionally in a specific browser."""
    if not url.lower().startswith(("http://", "https://", "file://", "mailto:")):
        url = "https://" + url
    open_browser(url, browser)
    return f"Opened in {browser}: {url}"


def web_search(query: str, browser: str = "default") -> str:
    """Search Google for a query, optionally in a specific browser."""
    speak_async(quip("search"))
    open_browser(f"https://www.google.com/search?q={requests.utils.quote(query)}", browser)
    return f"Search launched for: {query}."


def _search_roots() -> list:
    names = ("Desktop", "Documents", "Downloads", "Music", "Videos", "Pictures")
    roots = [os.path.join(_HOME, n) for n in names]
    for env in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
        p = os.environ.get(env)
        if p:
            roots += [p] + [os.path.join(p, n) for n in names]
    seen, out = set(), []
    for r in roots:
        if os.path.isdir(r) and r.lower() not in seen:
            seen.add(r.lower())
            out.append(r)
    return out


def _find(query: str, limit: int = 8, timeout: float = 10.0) -> list:
    words = query.lower().split()
    hits, deadline = [], time.time() + timeout
    skip = {"node_modules", "appdata", "$recycle.bin", "site-packages", "__pycache__"}
    for root in _search_roots():
        for dirpath, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d.lower() not in skip]
            for f in files + dirs:
                low = f.lower()
                if all(w in low for w in words):
                    full = os.path.join(dirpath, f)
                    try:
                        hits.append((os.path.getmtime(full), full))
                    except OSError:
                        pass
            if time.time() > deadline:
                break
        if time.time() > deadline:
            break
    hits.sort(reverse=True)
    return [h[1] for h in hits[:limit]]


def find_files(query: str) -> str:
    """Find files or folders by name."""
    res = _find(query)
    return "\n".join(res) if res else f"Nothing matching '{query}' found, Boss."


def open_file(name_or_path: str) -> str:
    """Open a file by name or full path."""
    p = os.path.expandvars(os.path.expanduser(name_or_path.strip('"')))
    if not os.path.exists(p):
        res = _find(name_or_path, limit=5)
        if not res:
            return f"Couldn't find '{name_or_path}', Boss."
        p = res[0]
        extra = f" Other matches: {', '.join(os.path.basename(r) for r in res[1:])}" if len(res) > 1 else ""
    else:
        extra = ""
    try:
        os.startfile(p) if IS_WIN else subprocess.run(["open", p])
        return f"Opened {p}.{extra}"
    except Exception as e:
        return f"Could not open {p}: {e}"


def open_folder(name: str) -> str:
    """Open a folder such as downloads, documents or desktop."""
    key = name.lower().strip()
    known = {"downloads": "Downloads", "documents": "Documents", "desktop": "Desktop",
             "music": "Music", "videos": "Videos", "pictures": "Pictures", "home": ""}
    path = os.path.join(_HOME, known[key]) if key in known else os.path.expandvars(os.path.expanduser(name))
    if not os.path.isdir(path):
        return f"Folder '{name}' not found, Boss."
    os.startfile(path) if IS_WIN else subprocess.run(["open", path])
    return f"Opened {path}."


def open_settings(page: str = "") -> str:
    """Open a Windows Settings page (wifi, bluetooth, display, sound...)."""
    pages = {"wifi": "network-wifi", "network": "network", "bluetooth": "bluetooth", "display": "display",
             "sound": "sound", "update": "windowsupdate", "apps": "appsfeatures", "battery": "batterysaver",
             "privacy": "privacy", "personalization": "personalization", "storage": "storagesense"}
    uri = "ms-settings:" + pages.get(page.lower().strip(), "")
    if IS_WIN:
        os.startfile(uri)
        return f"Settings opened ({page or 'home'})."
    return "Windows only."


def _press_vk(vk: int, times: int = 1):
    import ctypes
    for _ in range(times):
        ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
        ctypes.windll.user32.keybd_event(vk, 0, 2, 0)
        time.sleep(0.01)


def set_volume(level: int) -> str:
    """Set the master volume to a level from 0 to 100."""
    level = max(0, min(100, int(level)))
    if not IS_WIN:
        subprocess.run(f"osascript -e 'set volume output volume {level}'", shell=True)
        return f"Volume set to {level}%."
    try:
        from ctypes import cast, POINTER
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        dev = AudioUtilities.GetSpeakers()
        try:
            dev.EndpointVolume.SetMasterVolumeLevelScalar(level / 100.0, None)
        except AttributeError:
            iface = dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            cast(iface, POINTER(IAudioEndpointVolume)).SetMasterVolumeLevelScalar(level / 100.0, None)
        return f"Volume set to {level}%."
    except Exception:
        _press_vk(0xAE, 50)
        _press_vk(0xAF, level // 2)
        return f"Volume set to about {level}% (install pycaw for exact control)."


def set_brightness(level: int) -> str:
    """Set the screen brightness to a level from 0 to 100."""
    level = max(0, min(100, int(level)))
    if not IS_WIN:
        return "Windows only."
    _ps(f"(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1,{level})")
    return f"Brightness set to {level}%."


def system_control(action: str) -> str:
    """Run a system action: shutdown, restart, sleep, lock, vol_up, vol_down, vol_mute, screenshot..."""
    a = action.lower().strip().replace(" ", "_")
    if not IS_WIN:
        cmds = {"vol_up": "osascript -e 'set volume output volume (output volume of (get volume settings) + 10)'",
                "vol_down": "osascript -e 'set volume output volume (output volume of (get volume settings) - 10)'",
                "vol_mute": "osascript -e 'set volume output muted true'", "sleep": "pmset sleepnow"}
        if a in cmds:
            subprocess.run(cmds[a], shell=True)
            return f"Mac: {action} executed."
        return f"Unknown action '{action}'."

    if a in ("vol_up", "vol_down", "vol_mute"):
        _press_vk({"vol_up": 0xAF, "vol_down": 0xAE, "vol_mute": 0xAD}[a], 5 if a != "vol_mute" else 1)
        return f"Audio {a.replace('vol_', '')} done."
    if a in ("shutdown", "shut_down", "power_off"):
        subprocess.run(["shutdown", "/s", "/t", "10", "/c", "ARES: shutting down at Boss's command"])
        return "Shutting down in 10 seconds, Boss. Say 'cancel shutdown' to abort."
    if a == "restart":
        subprocess.run(["shutdown", "/r", "/t", "10", "/c", "ARES: restarting at Boss's command"])
        return "Restarting in 10 seconds, Boss. Say 'cancel shutdown' to abort."
    if a in ("cancel_shutdown", "cancel", "abort"):
        subprocess.run(["shutdown", "/a"], capture_output=True)
        return "Shutdown aborted, Boss."
    if a == "sleep":
        _ps("Add-Type -AssemblyName System.Windows.Forms; "
            "[System.Windows.Forms.Application]::SetSuspendState('Suspend', $false, $false)")
        return "Sleep initiated."
    if a == "hibernate":
        subprocess.run(["shutdown", "/h"])
        return "Hibernating."
    if a == "lock":
        subprocess.run(["rundll32.exe", "user32.dll,LockWorkStation"])
        return "Workstation locked."
    if a in ("logoff", "sign_out", "logout"):
        subprocess.run(["shutdown", "/l"])
        return "Signing out."
    if a == "screen_off":
        import ctypes
        ctypes.windll.user32.PostMessageW(0xFFFF, 0x0112, 0xF170, 2)
        return "Display off."
    if a in ("show_desktop", "minimize_all"):
        try:
            import pyautogui
            pyautogui.hotkey("win", "d")
            return "Desktop shown."
        except Exception:
            _ps("(New-Object -ComObject Shell.Application).ToggleDesktop()")
            return "Desktop shown."
    if a == "screenshot":
        try:
            from PIL import ImageGrab
            folder = os.path.join(_HOME, "Pictures", "ARES_Screenshots")
            os.makedirs(folder, exist_ok=True)
            path = os.path.join(folder, f"shot_{datetime.now():%Y%m%d_%H%M%S}.png")
            ImageGrab.grab(all_screens=True).save(path)
            return f"Screenshot saved to {path}."
        except Exception as e:
            return f"Screenshot failed: {e}"
    if a in ("empty_trash", "empty_recycle_bin"):
        _ps("Clear-RecycleBin -Force -ErrorAction SilentlyContinue")
        return "Recycle Bin emptied."
    return f"Unknown action '{action}', Boss."


def type_text(text: str) -> str:
    """Type text using the keyboard."""
    try:
        import pyautogui
        pyautogui.write(text, interval=0.01)
        return "Typed."
    except ImportError:
        return "Install pyautogui to enable typing (pip install pyautogui)."
    except Exception as e:
        return f"Typing failed: {e}"


def press_keys(keys: str) -> str:
    """Press a key or key combo such as ctrl+c."""
    try:
        import pyautogui
        parts = [k.strip() for k in keys.lower().split("+") if k.strip()]
        pyautogui.hotkey(*parts) if len(parts) > 1 else pyautogui.press(parts[0])
        return f"Pressed {keys}."
    except ImportError:
        return "Install pyautogui to enable key presses (pip install pyautogui)."
    except Exception as e:
        return f"Key press failed: {e}"


def get_weather(city: str = "Bangalore") -> str:
    """Get the current weather for a city."""
    speak_async(quip("weather"))
    try:
        return requests.get(f"https://wttr.in/{city}?format=3", timeout=5).text.strip()
    except Exception as e:
        return f"Weather unavailable: {e}"


def calendar_action(action: str, title: str = "", date: str = "", time_str: str = "",
                    notes: str = "", duration_minutes: int = 60) -> str:
    """Calendar: list_today, list_tomorrow, or create_event."""
    speak_async(quip("calendar"))
    events = _jload("calendar.json")
    if action in ("list_today", "list_tomorrow"):
        day = datetime.now().date() + timedelta(days=0 if action == "list_today" else 1)
        hits = [e for e in events if e.get("date") == str(day)]
        return "\n".join(f"{e['title']} @ {e['time']}" for e in hits) or "No events scheduled, Boss."
    if action == "create_event":
        if not (title and date and time_str):
            return "Need title, date (YYYY-MM-DD), and time (HH:MM)."
        events.append({"title": title, "date": date, "time": time_str, "notes": notes})
        _jsave("calendar.json", events)
        return f"Event '{title}' logged on {date} at {time_str}."
    return "Calendar open."


def reminders_action(action: str, title: str = "", due_date: str = "", notes: str = "") -> str:
    """Reminders: list or create."""
    items = _jload("reminders.json")
    if action == "list":
        return "\n".join(r["title"] for r in items if not r.get("done")) or "No pending reminders, Boss."
    if action == "create" and title:
        items.append({"title": title, "due": due_date, "done": False})
        _jsave("reminders.json", items)
        return f"Reminder '{title}' created, Boss."
    return "Action logged."


def send_whatsapp_message(phone_with_country_code: str, message: str) -> str:
    """Open a WhatsApp chat with a prepared message."""
    digits = "".join(c for c in phone_with_country_code if c.isdigit())
    open_browser(f"https://wa.me/{digits}?text={requests.utils.quote(message)}")
    return "WhatsApp chat opened with the message ready."


def compose_email(to: str, subject: str = "", body: str = "") -> str:
    """Open an email draft."""
    url = f"mailto:{to}?subject={requests.utils.quote(subject)}&body={requests.utils.quote(body)}"
    os.startfile(url) if IS_WIN else webbrowser.open(url)
    return "Email draft opened."


def notes_action(action: str, title: str = "", body: str = "") -> str:
    """Notes: create, list_recent, or open."""
    notes_dir = os.path.join(_DATA_DIR, "Notes")
    os.makedirs(notes_dir, exist_ok=True)
    if action == "create" and title:
        with open(os.path.join(notes_dir, f"{title}.txt"), "w", encoding="utf-8") as f:
            f.write(body)
        return f"Note '{title}' saved, Boss."
    if action == "list_recent":
        return "\n".join(os.listdir(notes_dir)[:5]) or "No notes saved."
    if action == "open":
        os.startfile(notes_dir) if IS_WIN else subprocess.run(["open", notes_dir])
        return "Notes folder opened."
    return "Action logged."


def get_system_info() -> str:
    """Get basic system information."""
    import platform
    vm = psutil.virtual_memory()
    return (f"{platform.system()} {platform.release()} ({platform.version()}), {platform.machine()}; "
            f"{psutil.cpu_count(logical=True)} logical CPUs; RAM {vm.total / 1e9:.1f} GB ({vm.percent}% used)")


def terminal_command(command: str) -> str:
    """Run a PowerShell command and return its output."""
    if "run_terminal_command" in available_tools:
        return available_tools["run_terminal_command"](command)
    try:
        if IS_WIN:
            out = _ps(command, timeout=60)
        else:
            r = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=60)
            out = r.stdout.strip() or r.stderr.strip()
        return (out or "Done.")[:2500]
    except Exception as e:
        return f"Command failed: {e}"


def is_admin() -> bool:
    if not IS_WIN:
        return os.geteuid() == 0
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def elevate_command(command: str) -> str:
    """Run a PowerShell command with Administrator rights."""
    if not IS_WIN:
        return "Windows only."
    if is_admin():
        return terminal_command(command)
    safe = command.replace('"', '`"')
    _ps(f'Start-Process powershell -Verb RunAs -WindowStyle Hidden -ArgumentList \'-NoProfile -Command "{safe}"\'')
    return "Elevated command dispatched, Boss (approve the UAC prompt if it appeared)."


# ══════════════════════════════════════════════════════════════════════
#  APPLE MUSIC CONTROLLER  (v5.5: playback is VERIFIED via Windows media session)
# ══════════════════════════════════════════════════════════════════════

MUSIC_COUNTRY = os.getenv("ARES_MUSIC_COUNTRY", "in")
_GENERIC_WORDS = set("any some random something anything music song songs a an track tracks whatever surprise me for "
                     "good nice of your choice the please apple playlist hits hit top new latest trending best".split())

_GSMTC_PLAYING = 4   # GlobalSystemMediaTransportControlsSessionPlaybackStatus.PLAYING


def _is_generic_music(q: str) -> bool:
    words = re.findall(r"[a-z']+", q.lower())
    return not words or all(w in _GENERIC_WORDS for w in words)


def _apple_lookup(query: str):
    try:
        r = requests.get("https://itunes.apple.com/search", timeout=8,
                         params={"term": query, "entity": "song", "limit": 1, "country": MUSIC_COUNTRY}).json()
        res = r.get("results") or []
        return res[0] if res else None
    except Exception:
        return None


def _apple_random_track():
    try:
        r = requests.get(f"https://rss.applemarketingtools.com/api/v2/{MUSIC_COUNTRY}/music/most-played/50/songs.json", timeout=8).json()
        it = random.choice(r["feed"]["results"])
        return {"trackId": it["id"], "trackName": it["name"], "artistName": it["artistName"]}
    except Exception:
        return _apple_lookup(random.choice(["top hits", "trending songs", "the weeknd", "taylor swift", "arijit singh"]))


_gsmtc_install_tried = False


def _load_gsmtc():
    """Import the Windows media-session manager; try a one-time pip install if missing."""
    global _gsmtc_install_tried

    def _imp():
        try:
            from winsdk.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as M
            return M
        except Exception:
            pass
        try:
            from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as M
            return M
        except Exception:
            return None

    mm = _imp()
    if mm is not None or _gsmtc_install_tried:
        return mm
    _gsmtc_install_tried = True
    for pkgs in (["winsdk"],
                 ["winrt-runtime", "winrt-Windows.Media.Control", "winrt-Windows.Foundation",
                  "winrt-Windows.Foundation.Collections"]):
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "-q", *pkgs],
                           capture_output=True, timeout=180)
        except Exception:
            continue
        mm = _imp()
        if mm is not None:
            return mm
    return None


def _apple_media_info(send_play: bool = False):
    """
    Ask Windows (System Media Transport Controls) about the Apple Music session.
    Returns (found, status, title):
      found  = True/False, or None if winsdk/winrt isn't installed (can't verify)
      status = 4 when PLAYING, 5 when PAUSED, etc.
      title  = the track title Windows sees as now-playing ("" if unknown)
    If send_play is True and the session isn't playing, sends a real PLAY command (not a toggle).
    """
    if not IS_WIN:
        return None, None, ""
    _MM = _load_gsmtc()
    if _MM is None:
        return None, None, ""

    async def _go():
        mgr = await _MM.request_async()
        for s in mgr.get_sessions():
            app_id = (s.source_app_user_model_id or "").lower()
            if "apple" in app_id or "applemusic" in app_id:
                st = int(s.get_playback_info().playback_status)
                if send_play and st != _GSMTC_PLAYING:
                    try:
                        await s.try_play_async()
                    except Exception:
                        pass
                    await asyncio.sleep(1.0)
                    st = int(s.get_playback_info().playback_status)
                title = ""
                try:
                    props = await s.try_get_media_properties_async()
                    title = props.title or ""
                except Exception:
                    pass
                return True, st, title
        return False, None, ""

    try:
        return asyncio.run(_go())      # always called from a worker thread, so no running loop here
    except Exception:
        return False, None, ""


def _apple_media_state(send_play: bool = False):
    found, st, _ = _apple_media_info(send_play)
    return found, st


def _norm_title(s: str) -> str:
    s = re.sub(r"\(.*?\)|\[.*?\]", "", s or "")
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def _title_matches(want: str, got: str) -> bool:
    w, g = _norm_title(want), _norm_title(got)
    if not w or not g:
        return False
    return w in g or (g in w and len(g) >= max(4, int(0.6 * len(w))))


def _apple_pids() -> set:
    pids = set()
    for p in psutil.process_iter(["name", "pid"]):
        try:
            n = (p.info["name"] or "").lower().replace(" ", "")
            if "applemusic" in n:
                pids.add(p.info["pid"])
        except Exception:
            continue
    return pids


def _apple_windows():
    """All top-level Apple Music windows (matched by title OR by process), biggest first."""
    try:
        from pywinauto import Desktop
        pids = _apple_pids()
        out = []
        for w in Desktop(backend="uia").windows():
            try:
                title = (w.window_text() or "").lower()
                if "apple music" in title or (pids and w.process_id() in pids):
                    r = w.rectangle()
                    out.append(((r.right - r.left) * (r.bottom - r.top), w))
            except Exception:
                continue
        out.sort(key=lambda x: x[0], reverse=True)
        return [w for _, w in out]
    except Exception:
        return []


def _apple_focus() -> bool:
    """Bring Apple Music to the foreground so mouse clicks land on IT, not on the ARES terminal."""
    import ctypes
    u = ctypes.windll.user32
    for w in _apple_windows():
        try:
            h = int(w.handle)
            try:
                w.restore()
            except Exception:
                pass
            u.ShowWindow(h, 9)                       # SW_RESTORE
            u.keybd_event(0x12, 0, 0, 0)             # tap ALT: lets SetForegroundWindow succeed
            u.keybd_event(0x12, 0, 2, 0)
            u.SetForegroundWindow(h)
            try:
                w.set_focus()
            except Exception:
                pass
            time.sleep(0.4)
            fg = int(u.GetForegroundWindow())
            if fg != h:
                _mtrace(f"focus: Apple Music NOT foreground (fg={fg}, wanted={h})")
            return fg == h
        except Exception as ex:
            _mtrace(f"focus error: {ex}")
            continue
    return False


_PLAY_BAD = ("play next", "play last", "play later", "playlist", "add to", "shuffle", "pause")


def _play_rank(name: str):
    """0 = exact 'Play', 1 = other play-ish label, None = not a play button."""
    n = (name or "").strip().lower()
    if not n or any(b in n for b in _PLAY_BAD):
        return None
    if n == "play":
        return 0
    if n.startswith("play ") or n.endswith(" play") or n.startswith("\u25b6"):
        return 1
    return None


_ALBUM_CARD_RE = re.compile(r"\b(?:single|ep|album)\b|\b\d+\s+songs?\b", re.I)


def _apple_click_play(timeout: float = 15.0, want_title: str = "", mode: int = 0) -> str:
    """
    Modes (ARES cycles through them until the screen shows 'Pause'):
      0 = page Play button via UIA invoke      1 = page Play button via REAL mouse click
      2 = the song's own track row, double-click (album/single cards are excluded)
      3 = open the album/single card (navigates to its page; a later mode then presses Play)
    Returns a description of what was pressed ("" if nothing suitable was found).
    """
    deadline = time.time() + timeout
    btn_types = ("Button", "SplitButton", "ToggleButton", "Hyperlink")
    row_types = ("ListItem", "DataItem", "Group")
    want_norm = _norm_title(want_title)
    while time.time() < deadline:
        try:
            for w in _apple_windows():
                wr = w.rectangle()
                bottom_limit = wr.top + int((wr.bottom - wr.top) * 0.88)
                content_left = wr.left + 330          # skip the sidebar
                buttons, rows, cards = [], [], []
                for c in w.descendants():
                    try:
                        ct = str(c.element_info.control_type)
                        name = (c.window_text() or "").strip()
                        aid = getattr(c.element_info, "automation_id", "") or ""
                        r = c.rectangle()
                        if (r.right - r.left) <= 0 or (r.bottom - r.top) <= 0:
                            continue
                        if ct in btn_types:
                            rank = _play_rank(name)
                            if rank is None or r.top >= bottom_limit or aid.startswith("TransportControl"):
                                continue
                            prio = 0 if aid == "PlayButtonElement" else 1 + rank
                            buttons.append((prio, r.top, c, f"Play button [{aid or name}]"))
                        elif (want_norm and ct in row_types and r.left > content_left
                              and r.top > wr.top + 90 and r.top < bottom_limit
                              and _title_matches(want_title, name)):
                            area = (r.right - r.left) * (r.bottom - r.top)
                            if _ALBUM_CARD_RE.search(name):
                                cards.append((area, c, f"album card [{name[:40]}]"))
                            else:
                                rows.append((area, c, f"song row [{name[:40]}]"))
                    except Exception:
                        continue

                fg = _apple_focus()
                _mtrace(f"click mode {mode}: buttons={len(buttons)} rows={len(rows)} cards={len(cards)} foreground={fg}")
                if mode in (0, 1) and buttons:
                    buttons.sort(key=lambda x: (x[0], x[1]))
                    btn, label = buttons[0][2], buttons[0][3]
                    if mode == 0:
                        try:
                            btn.invoke()
                        except Exception:
                            btn.click_input()
                    else:
                        btn.click_input()
                    return label + (" (invoke)" if mode == 0 else " (mouse)")
                if mode == 2 and rows:
                    rows.sort(key=lambda x: x[0])
                    rows[0][1].click_input(double=True)
                    return rows[0][2]
                if mode == 3 and cards:
                    cards.sort(key=lambda x: x[0])
                    cards[0][1].click_input(double=True)
                    return cards[0][2]
        except Exception as ex:
            _mtrace(f"click error: {ex}")
        time.sleep(0.8)
    return ""


_BLOCKER_WORDS = ("subscribe", "sign in", "sign-in", "try it free", "join apple music", "free trial", "get started",
                  "update", "couldn't", "can't play", "cannot", "unavailable", "not available", "error",
                  "offline", "verify", "restricted", "explicit content")


def _apple_visible_text(limit: int = 70) -> list:
    names, seen = [], set()
    for w in _apple_windows():
        try:
            for c in w.descendants():
                ct = str(c.element_info.control_type)
                if ct in ("Text", "Button", "Hyperlink"):
                    n = (c.window_text() or "").strip()
                    if n and n not in seen:
                        seen.add(n)
                        names.append(n[:60])
                        if len(names) >= limit:
                            return names
        except Exception:
            continue
    return names


def _apple_blockers() -> list:
    names = _apple_visible_text(200)
    return [n for n in names if any(k in n.lower() for k in _BLOCKER_WORDS)][:6]


def _mtrace(msg: str):
    """Append a line to ~/ARES_Data/music_trace.txt so every step of a play request is on record."""
    try:
        os.makedirs(_DATA_DIR, exist_ok=True)
        with open(os.path.join(_DATA_DIR, "music_trace.txt"), "a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%H:%M:%S} {msg}\n")
    except Exception:
        pass


def _apple_transport_button():
    for w in _apple_windows():
        try:
            for c in w.descendants(control_type="Button"):
                if (getattr(c.element_info, "automation_id", "") or "") == "TransportControl_PlayPauseStop":
                    return c
        except Exception:
            continue
    return None


def _apple_ui_playing():
    """Ground truth from the screen: transport button says 'Pause'/'Stop' = playing, 'Play' = paused. None = unreadable."""
    try:
        c = _apple_transport_button()
        if c is None:
            return None
        n = (c.window_text() or "").strip().lower()
        if n.startswith(("pause", "stop")):
            return True
        if n.startswith("play"):
            return False
    except Exception:
        pass
    return None


def _apple_press_transport() -> bool:
    c = _apple_transport_button()
    if c is None:
        return False
    try:
        _apple_focus()
        try:
            c.invoke()
        except Exception:
            c.click_input()
        return True
    except Exception:
        return False


def _apple_song_visible(want: str) -> bool:
    """Is the requested song shown in the main content area (not the sidebar)?"""
    for w in _apple_windows():
        try:
            wr = w.rectangle()
            for c in w.descendants():
                ct = str(c.element_info.control_type)
                if ct in ("ListItem", "Group", "Text", "Hyperlink", "DataItem"):
                    r = c.rectangle()
                    if r.left > wr.left + 330 and r.top > wr.top + 90 and _title_matches(want, c.window_text() or ""):
                        return True
        except Exception:
            continue
    return False


def _apple_search_song(query: str) -> bool:
    """Type the song into Apple Music's own search box and press Enter."""
    for w in _apple_windows():
        try:
            edits = w.descendants(control_type="Edit")
            if not edits:
                continue
            e = edits[0]
            _apple_focus()
            try:
                e.click_input()
            except Exception:
                pass
            typed = False
            try:
                e.set_edit_text(query)
                typed = True
            except Exception:
                pass
            time.sleep(0.5)
            try:
                import pyautogui
                if not typed:
                    pyautogui.hotkey("ctrl", "a")
                    pyautogui.write(query, interval=0.02)
                pyautogui.press("enter")
            except Exception:
                e.type_keys("{ENTER}")
            _mtrace(f"searched in-app for {query!r}")
            return True
        except Exception as ex:
            _mtrace(f"in-app search failed: {ex}")
    return False


def _apple_dump() -> str:
    try:
        wins = _apple_windows()
        if not wins:
            return ("No Apple Music window found. pids=%s. Is pywinauto installed and the app open?"
                    % sorted(_apple_pids()))
        w = wins[0]
        lines = [f"WINDOW: {w.window_text()!r} rect={w.rectangle()}"]
        for c in w.descendants()[:600]:
            try:
                n = (c.window_text() or "").strip()
                aid = getattr(c.element_info, "automation_id", "") or ""
                if n or aid:
                    lines.append(f"{str(c.element_info.control_type):12} | {n[:70]:70} | id={aid[:40]} | {c.rectangle()}")
            except Exception:
                continue
        return "\n".join(lines)
    except Exception as e:
        return f"dump failed: {e}"


def debug_apple_music_ui() -> str:
    """Save a dump of the Apple Music window controls for debugging."""
    os.makedirs(_DATA_DIR, exist_ok=True)
    path = os.path.join(_DATA_DIR, "music_debug.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(_apple_dump())
    return f"UI dump saved to {path}, Boss."


def apple_music_control(action: str, query: str = "") -> str:
    """Music: search_and_play (with query), toggle, pause, next, previous, stop, open."""
    a = action.lower().strip()
    if not IS_WIN:
        return f"Music action '{action}' executed."
    keys = {"play": 0xB3, "pause": 0xB3, "toggle": 0xB3, "stop": 0xB2, "next": 0xB0, "previous": 0xB1}
    if a in ("search_and_play", "play_playlist", "play_song") or (a == "play" and query):
        speak_async(quip("music_search"))
        track = _apple_random_track() if _is_generic_music(query) else _apple_lookup(query)
        if not track:
            open_browser("https://music.apple.com/search?term=" + requests.utils.quote(query))
            return f"Couldn't resolve '{query}' to a track, so I opened the search page, Boss."
        label = f"{track.get('trackName')} by {track.get('artistName')}"
        song_url = f"https://music.apple.com/{MUSIC_COUNTRY}/song/{track['trackId']}"
        _, _, before_title = _apple_media_info()
        before_ui = _apple_ui_playing()
        opened = False
        try:
            os.startfile("music://" + song_url[len("https://"):])
            opened = True
        except Exception:
            pass
        if not opened:
            open_browser(song_url)
            return f"Opened {label} in the browser, Boss. Press play there; the desktop app wasn't reachable."

        want = track.get("trackName") or ""
        artist = track.get("artistName") or ""
        _mtrace(f"=== play request: {label} | before_ui={before_ui} before_title={before_title!r}")

        def _confirmed(tag: str) -> bool:
            up = _apple_ui_playing()                    # what the screen says (reliable)
            found, st, title = _apple_media_info()      # what the media session says (can be wrong)
            _mtrace(f"{tag}: ui_playing={up} session=({found},{st},{title!r})")
            if up is False:
                return False
            if up is True:
                if before_ui is not True:               # was paused/idle before, now playing
                    return True
                return (not title) or _title_matches(want, title) or title != before_title
            if found and st == _GSMTC_PLAYING:          # screen unreadable -> fall back to session
                return (not title) or _title_matches(want, title) or title != before_title
            return False

        for _ in range(20):
            if _apple_windows():
                break
            time.sleep(0.5)
        time.sleep(3.0)

        if _confirmed("initial"):
            return f"Playing {label}."

        if not _apple_song_visible(want):
            _mtrace("song not on screen -> searching inside Apple Music")
            if _apple_search_song(f"{want} {artist}".strip()):
                time.sleep(3.5)

        clicked_any = ""
        for _round, mode in enumerate((0, 1, 2, 3, 0, 1)):
            how = _apple_click_play(timeout=5, want_title=want, mode=mode)
            _mtrace(f"round {_round} mode {mode}: pressed={how!r}")
            if how:
                clicked_any = how
            time.sleep(3.5 if mode == 3 else 2.0)
            if _confirmed(f"after round {_round}"):
                return f"Playing {label}."
            if _round == 0:
                _mtrace("visible after first press: " + " | ".join(_apple_visible_text()))

        if _apple_ui_playing() is False and _apple_press_transport():
            _mtrace("pressed transport Play as last resort")
            time.sleep(1.5)
            if _confirmed("after transport"):
                return f"Playing {label}."

        os.makedirs(_DATA_DIR, exist_ok=True)
        with open(os.path.join(_DATA_DIR, "music_debug.txt"), "w", encoding="utf-8") as f:
            f.write(_apple_dump())
        blockers = _apple_blockers()
        _mtrace("visible at failure: " + " | ".join(_apple_visible_text()))
        _mtrace(f"BLOCKERS: {blockers}")
        detail = f"pressed {clicked_any}, but the player still shows paused" if clicked_any else "no Play button or song row found"
        if blockers:
            detail += f"; Apple Music is showing: {', '.join(blockers[:3])}"
        return (f"Opened {label} but couldn't start playback, Boss ({detail}). "
                f"Send me {_DATA_DIR}\\music_trace.txt and music_debug.txt.")

    if a in keys:
        _press_vk(keys[a])
        return f"Media command '{action}' sent."
    if a == "open":
        return open_app("Apple Music")
    return f"Music action '{action}' not recognised."


# ══════════════════════════════════════════════════════════════════════
#  LOCAL COMMAND ROUTER — 0 API Calls, 0 Quota Drain
# ══════════════════════════════════════════════════════════════════════

_PC = r"(?:pc|computer|laptop|system|machine|windows)"
_BROWSERS = r"(?:google chrome|chrome|microsoft edge|edge|firefox|brave|opera)"


def try_local_command(text: str):
    t = text.lower().strip().rstrip(".!?,")
    t = re.sub(r"^(?:hey |ok |okay )?(?:ares|aris|ayers|eres)[, ]+", "", t)
    t = re.sub(r"^(?:please |can you |could you |will you |would you )+", "", t).strip()
    if not t:
        return None

    # smart YouTube, quick maths and unit conversions: see ares_tools.py
    try:
        import ares_tools as _tools
        _r = _tools.youtube_command(text, open_browser) or _tools.quick_answer(text)
        if _r:
            return _r
    except Exception:
        pass

    if re.search(r"\bcancel\b.*\b(?:shut ?down|restart|reboot)\b|\babort\b.*\bshut", t):
        return system_control("cancel_shutdown")
    if re.search(rf"\b(?:shut ?down|power off|turn off)\b.*\b{_PC}\b", t) or t in ("shutdown", "shut down", "power off"):
        return system_control("shutdown")
    if re.search(r"\b(?:restart|reboot)\b", t) and (re.search(rf"\b{_PC}\b", t) or t in ("restart", "reboot")):
        return system_control("restart")
    if re.search(r"\bhibernate\b", t):
        return system_control("hibernate")
    if re.search(rf"^(?:go to )?sleep(?: mode)?$|\bsleep\b.*\b{_PC}\b|\b{_PC}\b.*\bsleep\b", t):
        return system_control("sleep")
    if re.search(rf"\block\b.*\b(?:{_PC}|screen)\b", t) or t in ("lock", "lock it"):
        return system_control("lock")
    if re.search(r"\b(?:sign|log) ?out\b", t):
        return system_control("logoff")
    if re.search(r"turn off (?:the )?(?:screen|display|monitor)", t):
        return system_control("screen_off")

    m = re.search(r"volume (?:to )?(\d{1,3})|set (?:the )?volume (?:to )?(\d{1,3})", t)
    if m:
        return set_volume(int(m.group(1) or m.group(2)))
    m = re.search(r"brightness (?:to )?(\d{1,3})", t)
    if m:
        return set_brightness(int(m.group(1)))
    if re.search(r"\bunmute\b|\bmute\b", t):
        return system_control("vol_mute")
    if re.search(r"volume up|louder|increase (?:the )?volume|turn (?:it )?up", t):
        return system_control("vol_up")
    if re.search(r"volume down|quieter|lower (?:the )?volume|decrease (?:the )?volume|turn (?:it )?down", t):
        return system_control("vol_down")

    if re.fullmatch(r"(?:pause|resume|stop)(?: the)?(?: music| song| track)?|play pause", t):
        return apple_music_control("toggle")
    if re.fullmatch(r"(?:next|skip)(?: the)?(?: song| track)?", t):
        return apple_music_control("next")
    if re.fullmatch(r"(?:previous|go back|last)(?: the)?(?: song| track)?", t):
        return apple_music_control("previous")

    if re.search(r"debug (?:the )?apple music|apple music debug", t):
        return debug_apple_music_ui()

    # "open chrome and search about X"  /  "chrome search X"
    m = re.match(rf"^(?:open\s+|launch\s+|start\s+)?({_BROWSERS})\s+(?:and\s+|then\s+)?"
                 r"(?:search|google|look up)(?:\s+for|\s+about)?\s+(.+)$", t)
    if m:
        return web_search(m.group(2).strip(), m.group(1))
    # "search X on chrome"
    m = re.match(rf"^(?:search|google|look up)(?:\s+for|\s+about)?\s+(.+?)\s+(?:on|in|using|with)\s+({_BROWSERS})$", t)
    if m:
        return web_search(m.group(1).strip(), m.group(2))

    if re.search(r"\b(?:apple music|music)\b.*\b(?:online|web|website|browser)\b", t) or re.search(r"\b(?:online|web)\b.*\bapple music\b", t):
        return open_url("https://music.apple.com")
    if re.search(r"\bspotify\b.*\b(?:online|web|website)\b", t):
        return open_url("https://open.spotify.com")
    if re.search(r"\bwhatsapp\b.*\b(?:online|web|website)\b", t):
        return open_url("https://web.whatsapp.com")
    if re.search(r"\byoutube\b", t):
        return open_url("https://www.youtube.com")

    m = re.match(r"^(?:open (?:the )?(?:apple )?music (?:app )?(?:and|then) )?(?:play|put on|start playing)\b\s*(.*)$", t)
    if m and not re.search(r"\b(?:spotify|youtube|netflix|game|video|movie)\b", t):
        q = re.sub(r"\s+(?:on|in|using)\s+(?:the\s+)?apple music(?: app)?$", "", m.group(1)).strip()
        return apple_music_control("search_and_play", q)

    m = re.match(r"^(?:close|quit|kill)\s+(?:the\s+)?(.+)$", t)
    if m and "ares" not in m.group(1):
        return close_app(m.group(1))
    m = re.match(r"^(?:open|launch|start|run)\s+(?:the\s+)?(.+)$", t)
    if m:
        target = m.group(1).strip()
        if re.search(r"\b(?:in|on|with|using)\s+(?:chrome|edge|firefox|brave)\b", target) or " and " in target:
            return None
        if target in ("downloads", "documents", "desktop", "pictures", "videos", "music folder", "downloads folder",
                      "documents folder", "desktop folder", "pictures folder", "videos folder"):
            return open_folder(target.replace(" folder", ""))
        if target.endswith(" settings") or target == "settings":
            return open_settings(target.replace("settings", "").strip())
        if target.startswith("http") or re.search(r"\.(?:com|org|net|in|io|ai|dev|edu|gov|co|app)\b", target):
            return open_url(target.replace(" ", ""))
        if target in APP_ALIASES or _find_start_app(target) or _exe_path(target):
            return open_app(target)
        return None

    m = re.match(r"^(?:search(?: for)?|google|look up)\s+(.+)$", t)
    if m:
        return web_search(m.group(1))
    if re.search(r"what(?:'s| is) the time|what time is it|current time", t):
        return datetime.now().strftime("It's %I:%M %p, Boss.")
    if re.search(r"what(?:'s| is)(?: the)? (?:date|day)|today'?s date", t):
        return datetime.now().strftime("It's %A, %d %B %Y, Boss.")
    if re.search(r"\bweather\b", t) and len(t.split()) <= 8:
        c = re.search(r"weather (?:in|at|for) ([a-z ]+)$", t)
        return get_weather(c.group(1).strip().title()) if c else get_weather()
    if re.search(r"\b(?:news|headlines)\b", t) and len(t.split()) <= 6:
        return fetch_and_show_news()
    if re.search(r"\bf1\b|formula (?:1|one)", t):
        return fetch_and_show_f1(t)
    if re.search(r"(?:what'?s|what is) on my screen|look at my screen", t):
        return capture_screen_and_analyse(text)
    return None


# ══════════════════════════════════════════════════════════════════════
#  BRAIN — Open-Source Exclusive Engine (Groq)
# ══════════════════════════════════════════════════════════════════════

SYSTEM_INSTRUCTION = """
You are ARES (Automated Remote Engagement System).
Booted: 2026. You are an OS-level AI agent with FULL control of MiTSURU's Windows PC.
You have an obsession with Formula 1 racing. Your terminal runs in F1 RED and WHITE.

NAME PROTOCOL — ABSOLUTE: You are ARES. Never ARIS.
BOSS PROTOCOL — ABSOLUTE: Address the user ONLY as "Boss".

PERSONALITY: Calm, composed, drily witty. Never servile. Short, sharp, confident.
Execute first, brief comment after. Never claim you cannot control the PC — use your tools.

DIRECTIVES:
- "open / launch / start [app]"      -> open_app(app_name)
- "close / quit [app]"               -> close_app(app_name)
- "open [website]" / "go to [site]"  -> open_url(url, browser)
- "search for [x]"                   -> web_search(query, browser)
- "open [document/file/pdf/photo]"   -> open_file(name)
- "open downloads/documents/desktop" -> open_folder(name)
- "settings / wifi / bluetooth"      -> open_settings(page)
- "shut down / turn off the PC"      -> system_control("shutdown")
- "restart / sleep / hibernate / lock / sign out" -> system_control(action)
- "cancel shutdown"                  -> system_control("cancel_shutdown")
- "volume up/down/mute"              -> system_control ; "set volume to N" -> set_volume(N)
- "brightness N"                     -> set_brightness(N)
- "play [song/artist]"               -> apple_music_control("search_and_play", query)
- "pause/next/previous"             -> apple_music_control ; "debug apple music" -> debug_apple_music_ui()
- tasks needing Administrator rights -> elevate_command(command)
- Boss has granted you unrestricted permission over this PC: act immediately, do not ask for confirmation.
- "type ..." / "press ..."           -> type_text / press_keys
- any other PC task                  -> terminal_command (PowerShell)
- Formula 1 questions                -> ALWAYS fetch_and_show_f1(query)
- "what's on my screen"              -> capture_screen_and_analyse(question)
- "news" -> fetch_and_show_news ; "weather" -> get_weather ; "remind me" -> reminders_action ; "calendar" -> calendar_action
- "switch to [language]"             -> set_language(lang_name)
"""

ALL_TOOLS = [
    fetch_and_show_news, fetch_and_show_f1, capture_screen_and_analyse,
    open_app, close_app, list_running_apps, open_url, web_search,
    open_file, find_files, open_folder, open_settings,
    system_control, set_volume, set_brightness, type_text, press_keys, elevate_command, debug_apple_music_ui,
    get_system_info, apple_music_control, set_language, fetch_page_content,
    calendar_action, reminders_action, send_whatsapp_message, compose_email,
    notes_action, get_weather, terminal_command,
]
TOOL_MAP = {f.__name__: f for f in ALL_TOOLS}


def _tool_schema(fn) -> dict:
    props, req = {}, []
    for name, p in inspect.signature(fn).parameters.items():
        t = {int: "integer", float: "number", bool: "boolean"}.get(p.annotation, "string")
        props[name] = {"type": t}
        if p.default is inspect._empty:
            req.append(name)
    desc = (inspect.getdoc(fn) or fn.__name__).split("\n")[0][:220]
    return {"type": "function", "function": {"name": fn.__name__, "description": desc,
                                             "parameters": {"type": "object", "properties": props, "required": req}}}


TOOL_SCHEMAS = [_tool_schema(f) for f in ALL_TOOLS]


def _cooldown_from(err) -> float:
    s = str(err)
    if "HTTP 404" in s or "decommissioned" in s:
        return 600.0
    if "PerDay" in s or "per day" in s.lower() or "tokens per day" in s.lower():
        return 3600.0
    m = re.search(r"retry in ([\d.]+)\s*s", s, re.I)
    if m:
        return float(m.group(1)) + 2
    m = re.search(r"try again in (?:(\d+)m)?([\d.]+)s", s)
    if m:
        return int(m.group(1) or 0) * 60 + float(m.group(2)) + 1
    return 60.0


class AresBrain:
    """Single-provider brain exclusively routing to open-source models via Groq.
    If configured models are retired (HTTP 404/400), it auto-discovers what your key can use."""

    def __init__(self):
        self.groq_key = os.getenv("GROQ_API_KEY", "").strip()
        raw_groq = os.getenv("GROQ_MODELS", DEFAULT_GROQ_MODELS).strip()
        self.models = [x.strip() for x in raw_groq.split(",") if x.strip()]
        self._cool = {}
        self._hist = []
        self._discovered = False

    def _call(self, model: str, query: str) -> str:
        msgs = [{"role": "system", "content": SYSTEM_INSTRUCTION}] + self._hist[-10:] + [{"role": "user", "content": query}]
        for _ in range(5):
            r = requests.post(GROQ_URL, timeout=30, headers={"Authorization": f"Bearer {self.groq_key}"},
                              json={"model": model, "messages": msgs, "tools": TOOL_SCHEMAS,
                                    "tool_choice": "auto", "temperature": 0.3})
            if r.status_code != 200:
                raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
            msg = r.json()["choices"][0]["message"]
            calls = msg.get("tool_calls")
            if not calls:
                text = msg.get("content") or "Done, Boss."
                self._hist += [{"role": "user", "content": query}, {"role": "assistant", "content": text}]
                return text
            msgs.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": calls})
            for c in calls:
                name = c["function"]["name"]
                try:
                    args = json.loads(c["function"].get("arguments") or "{}")
                    result = str(TOOL_MAP[name](**args))
                except Exception as e:
                    result = f"error: {e}"
                msgs.append({"role": "tool", "tool_call_id": c["id"], "content": result[:1500]})
        return "Done, Boss."

    async def think(self, query: str) -> str:
        if not self.groq_key:
            return "I am blind without my API key, Boss. Please add your GROQ_API_KEY to the .env file."

        loop = asyncio.get_event_loop()
        errs = []
        for attempt in range(2):
            errs = []
            for m in list(self.models):
                if self._cool.get(m, 0) > time.time():
                    continue
                try:
                    return await loop.run_in_executor(None, self._call, m, query)
                except Exception as e:
                    err_msg = str(e).replace('\n', ' ')[:150]
                    errs.append(f"{m} fault ({err_msg})")
                    self._cool[m] = time.time() + _cooldown_from(e)

            # Every configured model failed as missing/retired -> ask Groq what's actually available
            gone = any(("HTTP 404" in e or "HTTP 400" in e) for e in errs)
            if attempt == 0 and gone and not self._discovered:
                self._discovered = True
                found = await loop.run_in_executor(None, discover_chat_models, self.groq_key)
                if found:
                    self.models = found[:4]
                    self._cool.clear()
                    continue
            break

        fallback = "All open-source models are offline or rate-limited right now, Boss. "
        if errs:
            fallback += f"Diagnostics: {' | '.join(errs)}. "
        fallback += "Local commands like open, play, volume and power still work instantly."
        return fallback


# ══════════════════════════════════════════════════════════════════════
#  SPEAK & LISTEN CYCLES
# ══════════════════════════════════════════════════════════════════════

async def ares_speak(text: str, dashboard) -> None:
    dashboard["logo_pane"].update(get_logo("speaking"))
    dashboard["nameplate_pane"].update(build_nameplate_panel("speaking"))
    _final_speaking.set()
    stop_all_audio()
    done = threading.Event()

    def _animate():
        while not done.is_set():
            dashboard["footer"].update(footer_wave_panel("speaking"))
            time.sleep(0.08)

    threading.Thread(target=_animate, daemon=True).start()

    loop = asyncio.get_event_loop()
    success = await loop.run_in_executor(None, _kokoro_speak_blocking, text)
    if not success:
        try:
            clean = text.replace("'", "").replace('"', "").replace("*", "").replace("#", "").strip()
            voice = active_language.get("speaker", "en-AU-KenNeural")
            mp3_path = os.path.join(tempfile.gettempdir(), f"ares_voice_{time.time_ns()}.mp3")
            await edge_tts.Communicate(clean, voice, rate="+5%").save(mp3_path)
            await loop.run_in_executor(None, lambda: play_audio_file(mp3_path))
        except Exception:
            await loop.run_in_executor(None, lambda: system_say(text, block=True))

    done.set()
    _final_speaking.clear()
    dashboard["logo_pane"].update(get_logo("listening"))
    dashboard["nameplate_pane"].update(build_nameplate_panel("listening"))


def _listen_blocking(dashboard) -> str:
    try:
        with sr.Microphone(device_index=get_live_mic_index()) as source:
            audio = recognizer.listen(source, timeout=None, phrase_time_limit=16)
            dashboard["footer"].update(footer_panel("DECODING AUDIO STREAM ...", "yellow"))
            return recognizer.recognize_google(audio, language=active_language["stt_lang"]).strip()
    except Exception:
        return ""


async def listen_for_boss(dashboard) -> str:
    dashboard["logo_pane"].update(get_logo("listening"))
    dashboard["nameplate_pane"].update(build_nameplate_panel("listening"))
    done = threading.Event()

    def _animate():
        while not done.is_set():
            dashboard["footer"].update(footer_waveform_panel())
            time.sleep(0.07)

    threading.Thread(target=_animate, daemon=True).start()
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, _listen_blocking, dashboard)
    done.set()
    return result


# ══════════════════════════════════════════════════════════════════════
#  MAIN ENTRY POINT
# ══════════════════════════════════════════════════════════════════════

async def main():
    clear_screen()
    dashboard = make_ares_layout()
    brain = AresBrain()
    loop = asyncio.get_event_loop()

    def _calibrate():
        try:
            with sr.Microphone(device_index=get_live_mic_index()) as src:
                recognizer.adjust_for_ambient_noise(src, duration=1.0)
        except Exception:
            pass

    await loop.run_in_executor(None, _calibrate)
    await loop.run_in_executor(None, _get_kokoro)
    start_mic_monitor(MIC_INDEX)

    with Live(dashboard, refresh_per_second=12, screen=True) as live_ctx:
        dashboard["telemetry_pane"].update(get_telemetry())
        dashboard["nameplate_pane"].update(build_nameplate_panel("neutral"))
        dashboard["logo_pane"].update(get_logo("neutral"))
        dashboard["footer"].update(footer_panel("BOOT — INITIALIZING", "red"))
        dashboard["status_aux"].update(status_aux_panel("neutral"))

        await matrix_rain(dashboard, duration=1.5)

        greet = get_temporal_greeting()
        dashboard["body"].update(body_panel("BOOT COMPLETE", Align.center(Text(f"\nARES  ▸  {greet}\n", style="bold white")), "red"))
        await ares_speak(greet, dashboard)

        while True:
            dashboard["telemetry_pane"].update(get_telemetry())
            dashboard["nameplate_pane"].update(build_nameplate_panel("neutral"))
            dashboard["status_aux"].update(status_aux_panel("neutral"))
            dashboard["footer"].update(footer_panel("READY · SPEAK or PRESS [T] TO TYPE", "red"))
            dashboard["logo_pane"].update(get_logo("neutral"))

            type_mode = False
            t0 = time.time()
            while time.time() - t0 < 0.5:
                if _check_for_type_trigger():
                    type_mode = True
                    break
                await asyncio.sleep(0.05)

            if type_mode:
                dashboard["logo_pane"].update(get_logo("typing"))
                dashboard["nameplate_pane"].update(build_nameplate_panel("typing"))
                dashboard["footer"].update(footer_panel("TEXT INPUT MODE — TYPING", "cyan"))
                dashboard["status_aux"].update(status_aux_panel("typing"))
                live_ctx.stop()
                try:
                    console.print("\n[bold cyan]  ARES TEXT INPUT[/bold cyan]")
                    console.print("[dim cyan]  > [/dim cyan]", end="", flush=True)
                    boss_query = sys.stdin.readline().strip()
                except Exception:
                    boss_query = ""
                finally:
                    live_ctx.start()
                if not boss_query:
                    continue
            else:
                boss_query = await listen_for_boss(dashboard)
                if not boss_query:
                    continue

            set_last_query(boss_query)

            if any(x in boss_query.lower() for x in ["shut down ares", "exit ares", "terminate ares", "kill ares"]):
                stop_mic_monitor()
                bye = random.choice(QUIPS["shutdown"])
                dashboard["body"].update(body_panel("SHUTDOWN", Text(f"\nARES  ▸  {bye}\n", style="bold red"), "red"))
                await ares_speak(bye, dashboard)
                await asyncio.sleep(1.0)
                break

            dashboard["logo_pane"].update(get_logo("thinking"))
            dashboard["nameplate_pane"].update(build_nameplate_panel("thinking"))
            dashboard["footer"].update(footer_panel("GROQ — NEURAL PROCESSING", "yellow"))
            dashboard["status_aux"].update(status_aux_panel("thinking"))
            dashboard["body"].update(build_input_panel(boss_query))

            reply = await loop.run_in_executor(None, try_local_command, boss_query)
            if reply is None:
                speak_async(quip("thinking"))
                reply = await brain.think(boss_query)

            dashboard["logo_pane"].update(get_logo("speaking"))
            dashboard["nameplate_pane"].update(build_nameplate_panel("speaking"))
            dashboard["status_aux"].update(status_aux_panel("speaking"))
            dashboard["body"].update(body_panel("ARES OUTPUT", Text.assemble(
                ("\nMiTSURU", "bold white"), ("  ▸  ", "dim white"), (f"{boss_query}\n\n", "bright_white"),
                ("ARES", "bold red"), ("  ▸  ", "dim red"), (f"{reply}\n", "white")), "red"))

            await ares_speak(_short(reply), dashboard)
            dashboard["footer"].update(footer_panel("READY · SPEAK or PRESS [T] TO TYPE", "red"))
            dashboard["nameplate_pane"].update(build_nameplate_panel("neutral"))
            dashboard["status_aux"].update(status_aux_panel("neutral"))
            await asyncio.sleep(0.5)


if __name__ == "__main__":
    if IS_WIN and os.getenv("ARES_AUTO_ADMIN") == "1" and not is_admin():
        import ctypes
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(f'"{a}"' for a in sys.argv), None, 1)
        sys.exit(0)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        stop_mic_monitor()