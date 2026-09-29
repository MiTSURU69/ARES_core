#!/usr/bin/env python3
"""
ARES Companion — a 3D Ares that lives on your desktop.

  * Starts with Windows by itself (registered on first run, no terminal ever needed again)
  * Roams around your screen (walks along the top of the taskbar), click-through, always on top
  * Press  `  (backtick) and he listens (default; change with ARES_HOTKEY in .env)
  * Uses the ARES brain + tools from main.py (open apps, music, search, volume, screen vision...)
  * Dictation:  "dictate" ... speak ... "stop dictation"      (types into whatever app has focus)
  * Type:       "type hello there"                            (types that exact text)
  * Write:      "write a short paragraph about F1"            (AI writes it, pastes it in)
  * Email:      "write an email to John about tomorrow's meeting"  -> Gmail draft opens, YOU press send
  * Screen:     "what's on my screen" / "summarise this page" / "read this" / "translate this"
  * Code:       "explain this code" / "what's wrong with this error" / "fix this bug" / "review this code"
                (he looks at your focused window; a short answer is spoken, the full answer goes on your clipboard;
                 then say "more" or "explain that simpler" within 3 minutes to dig deeper into the same screenshot)
  * Emotions:   happy, excited, love, proud, celebrate, groove (music), surprised, sad, angry (after repeated fails),
                worried, curious, bored, sleepy, reading, coding ... he reacts to what you say and to being ignored
  * Outfits:    "change your outfit" / "wear the racing outfit" / "what outfits do you have" (or the tray menu):
                spartan, racing, steel, shadow, emerald, royal, frost, sakura. Remembered between runs.
  * Perching: now and then he hops up onto the top edge of an open window, sits there (rides along if you drag
    the window) and hops back down when it closes / minimises. Turn off in the tray menu or ARES_PERCH=0
  * Sitting / antics: he sits (legs folded on the floor, dangling off a window edge), fights imaginary enemies with sparks and
    shouts, practises sword forms, dances (dance / disco / robot / twirl), flips, jumps, stretches, flexes, meditates, runs to
    your cursor, and walks in different gaits. Ask: "sit down" / "dance" / "have a sword fight" / "do a flip" / "run around" /
    "come here" / "show me your moves" / "stand up"  (or tray menu: Do something). Random antics off: ARES_ANTICS=0
  * Memory:     "remember that ..." / "forget ..." / "what do you remember" / "catch me up". Every exchange is kept (ares_memory.py),
                so "that" / "it" / "again" work after restarts; kind words make him chattier, harsh ones quieter
  * Extras:     "remind me to X in 20 minutes", "set a timer for 10 minutes", "start a pomodoro", "note this down ...",
                "read my notes", "how's my battery / cpu / ram", good-morning and late-night nudges (ares_extras.py)
  * Clicks:     poke him (he reacts, and gets annoyed if you keep going), stroke the mouse back and forth over him to pet him,
                drag him anywhere and drop him. ARES_CLICKS=0 turns it off
  * YouTube:    "open youtube and play despacito" / "play X on youtube" / "search X on youtube" / "play the second one" (ares_tools.py)
  * Quick:      "what is 15% of 240", "12 * (3 + 4)", "5 km in miles", "72 f to c", "translate good morning to hindi"
  * Briefing:   the first time you talk to him each day he reads out today's calendar + to-do list. Ask any time: "brief me"
  * Breaks:     after ~45 min of solid work he nudges you (water, stretch, eyes, walk).  "stop break reminders" / "turn on break reminders"
                / "snooze break reminders".  ARES_BREAKS=0 turns them off, ARES_BREAK_MIN=45 sets the interval (ares_habits.py)
  * Hides itself while you game / any fullscreen app is in front; returns afterwards

Needs:  pip install PySide6 psutil      (plus everything main.py already needs)
Files:  main.py, ares_3d.py, ares_sprites.py, ares_scenes.py, ares_memory.py, ares_extras.py, ares_tools.py, ares_habits.py and ares_hotkey.py must sit in the same folder as this file.

Start him without a terminal: double-click Ares.pyw, or search "ARES Companion" in the Start menu
(the shortcut is created on first run).

.env options (all optional):
  ARES_HOTKEY=`                  ARES_SCALE=4            ARES_USER_NAME=Priya
  ARES_BROWSER=chrome            ARES_GMAIL_ACCOUNT=0    ARES_HIDE_WHEN_GAMING=1
  ARES_HOTKEY_SUPPRESS=1         ARES_PERCH=1           ARES_OUTFIT=spartan
  ARES_ANTICS=1                  ARES_OLD_POSES=0       ARES_HIDE_FULLSCREEN=0
  ARES_CLICKS=1                  ARES_BREAKS=1          ARES_BREAK_MIN=45       ARES_CITY=Bangalore
Extra files in %USERPROFILE%\\ARES_Data\\:
  contacts.json  {"john": "john@example.com"}      games.txt   (one game .exe / folder keyword per line)
"""

import os
import re
import sys
import json
import math
import time
import random
import socket
import threading
import traceback
import asyncio
from pathlib import Path

HERE = Path(__file__).resolve().parent
os.chdir(HERE)
sys.path.insert(0, str(HERE))
DATA_DIR = Path.home() / "ARES_Data"
DATA_DIR.mkdir(exist_ok=True)
IS_WIN = os.name == "nt"

# pythonw.exe has no console: send prints to a log file so errors are never silent
if sys.stdout is None or sys.stderr is None or "pythonw" in os.path.basename(sys.executable).lower():
    _lf = open(DATA_DIR / "companion.log", "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr = _lf


def log(*a):
    try:
        print(time.strftime("%H:%M:%S"), *a, flush=True)
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════════
#  START-WITH-WINDOWS  (works before any heavy import)
# ══════════════════════════════════════════════════════════════════════

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_RUN_NAME = "ARESCompanion"
_STARTUP_MARK = DATA_DIR / ".startup_registered"


def _pythonw() -> str:
    exe = sys.executable
    if exe.lower().endswith("python.exe"):
        cand = exe[:-10] + "pythonw.exe"
        if os.path.exists(cand):
            return cand
    return exe


def _startup_command() -> str:
    # --autostart: after a fresh boot wait a few seconds so network / audio / microphone are ready
    return f'"{_pythonw()}" "{Path(__file__).resolve()}" --autostart'


def is_startup_enabled() -> bool:
    if not IS_WIN:
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as k:
            winreg.QueryValueEx(k, _RUN_NAME)
            return True
    except Exception:
        return False


def set_startup(enable: bool) -> str:
    if not IS_WIN:
        return "Windows only."
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            if enable:
                winreg.SetValueEx(k, _RUN_NAME, 0, winreg.REG_SZ, _startup_command())
                return "ARES Companion will now start with Windows."
            try:
                winreg.DeleteValue(k, _RUN_NAME)
            except FileNotFoundError:
                pass
            return "ARES Companion removed from startup."
    except Exception as e:
        return f"Startup change failed: {e}"


def ensure_startup():
    """First run: register auto-start. Later runs: keep the entry pointing at THIS file (folder moved, Python updated),
    but never re-enable it if you switched it off in the tray menu."""
    if not IS_WIN:
        return
    try:
        if not _STARTUP_MARK.exists():
            log(set_startup(True))
            _STARTUP_MARK.write_text("1", encoding="utf-8")
        elif is_startup_enabled():
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as k:
                cur = winreg.QueryValueEx(k, _RUN_NAME)[0]
            if cur != _startup_command():
                set_startup(True)
                log("startup entry refreshed")
    except Exception as e:
        log("ensure_startup:", e)


def ensure_start_menu_shortcut():
    """Start menu entry 'ARES Companion' so he can be relaunched without a terminal after quitting."""
    if not IS_WIN:
        return
    try:
        import subprocess
        lnk = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "ARES Companion.lnk"
        if lnk.exists() or not lnk.parent.exists():
            return
        q = lambda v: str(v).replace("'", "''")
        ps = ("$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%s');$s.TargetPath='%s';"
              "$s.Arguments='\"%s\"';$s.WorkingDirectory='%s';$s.Save()") % (
            q(lnk), q(_pythonw()), q(Path(__file__).resolve()), q(HERE))
        subprocess.run(["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps],
                       creationflags=0x08000000, timeout=25, capture_output=True)
    except Exception as e:
        log("shortcut:", e)


def _uptime_seconds() -> float:
    try:
        import ctypes
        ctypes.windll.kernel32.GetTickCount64.restype = ctypes.c_ulonglong
        return ctypes.windll.kernel32.GetTickCount64() / 1000.0
    except Exception:
        return 9999.0


if "--install-startup" in sys.argv:
    print(set_startup(True))
    sys.exit(0)
if "--remove-startup" in sys.argv:
    print(set_startup(False))
    sys.exit(0)
if "--autostart" in sys.argv and IS_WIN and _uptime_seconds() < 180:
    time.sleep(10)                                       # just booted: let audio / network / mic come up first

# ══════════════════════════════════════════════════════════════════════
#  HEAVY IMPORTS
# ══════════════════════════════════════════════════════════════════════

try:
    from PySide6.QtCore import Qt, QTimer, QObject, Signal, QRect, QRectF, QPointF
    from PySide6.QtGui import (QImage, QPixmap, QPainter, QColor, QFont, QFontMetrics, QIcon, QAction,
                               QPen, QPolygonF, QGuiApplication, QActionGroup, QCursor)
    from PySide6.QtWidgets import QApplication, QWidget, QSystemTrayIcon, QMenu, QInputDialog
except ImportError:
    print("PySide6 is missing. Run:  pip install PySide6")
    sys.exit(1)

import requests
import main as core                      # the ARES brain, tools and voice
import ares_sprites as SP                # mood table + little icons above his head
import ares_3d as A3                     # the 3D model + animator
import ares_scenes as SC                 # extra moods, scripted scenes, action commands
import ares_memory as MEM                # long-term memory
import ares_extras as EX                 # reminders, timers, notes, system stats
import ares_tools as TOOLS               # smart YouTube, quick maths, unit conversions, translation requests
import ares_habits as HAB                # morning briefing + break nudges

SCALE = max(2, int(os.getenv("ARES_SCALE", "4")))      # 4 = about 140px tall; try 5 or 6 on a big/hi-res screen
HOTKEY = os.getenv("ARES_HOTKEY", "`")
HOTKEY_SUPPRESS = os.getenv("ARES_HOTKEY_SUPPRESS", "1") != "0"
USER_NAME = os.getenv("ARES_USER_NAME", "").strip()
GMAIL_ACCOUNT = os.getenv("ARES_GMAIL_ACCOUNT", "0").strip() or "0"
MAIL_BROWSER = os.getenv("ARES_BROWSER", "default").strip() or "default"
HIDE_WHEN_GAMING = os.getenv("ARES_HIDE_WHEN_GAMING", "1") != "0"
PERCH = os.getenv("ARES_PERCH", "1") != "0"
HIDE_FULLSCREEN = os.getenv("ARES_HIDE_FULLSCREEN", "0") == "1"    # 0 = stay visible over fullscreen windows (only real games hide him)
ANTICS = os.getenv("ARES_ANTICS", "1") != "0"           # random idle behaviour: fights, dances, sitting ...
CLICKS = IS_WIN and os.getenv("ARES_CLICKS", "1") != "0"   # poke / pet / drag him (he is click-through everywhere else)
CITY = os.getenv("ARES_CITY", "Bangalore").strip() or "Bangalore"
OLD_POSES = os.getenv("ARES_OLD_POSES", "0") == "1"    # 1 = keep the older emotions on their original body poses
SC.register(SP, upgrade=not OLD_POSES)                 # extra moods + richer old emotions

# ── outfit (remembered in ARES_Data/outfit.txt, default from ARES_OUTFIT) ──
OUTFIT_FILE = DATA_DIR / "outfit.txt"


def _load_outfit() -> str:
    for cand in ((OUTFIT_FILE.read_text(encoding="utf-8").strip() if OUTFIT_FILE.exists() else ""),
                 os.getenv("ARES_OUTFIT", "").strip().lower()):
        if cand in SP.OUTFITS:
            return cand
    return "spartan"


_STATE = {"outfit": _load_outfit()}

# ══════════════════════════════════════════════════════════════════════
#  GAME / FULLSCREEN DETECTION
# ══════════════════════════════════════════════════════════════════════

_DEFAULT_GAMES = {
    "valorant-win64-shipping.exe", "cs2.exe", "csgo.exe", "dota2.exe", "fortniteclient-win64-shipping.exe",
    "eldenring.exe", "gta5.exe", "gtav.exe", "rdr2.exe", "r5apex.exe", "overwatch.exe", "league of legends.exe",
    "robloxplayerbeta.exe", "genshinimpact.exe", "cyberpunk2077.exe", "witcher3.exe", "minecraft.exe",
    "hogwartslegacy.exe", "starfield.exe", "bg3.exe", "bg3_dx11.exe", "forzahorizon5.exe", "eafc24.exe",
    "fc25.exe", "fc26.exe", "f1_24.exe", "f1_25.exe", "rocketleague.exe", "pubg.exe", "tslgame.exe",
}
_GAME_PATH_HINTS = ("\\steamapps\\common\\", "\\epic games\\", "\\riot games\\", "\\xboxgames\\",
                    "\\gog galaxy\\games\\", "\\rockstar games\\", "\\ubisoft game launcher\\games\\", "\\ea games\\")
_SHELL_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"}


def _user_games() -> set:
    try:
        return {ln.strip().lower() for ln in (DATA_DIR / "games.txt").read_text(encoding="utf-8").splitlines()
                if ln.strip() and not ln.startswith("#")}
    except Exception:
        return set()


def detect_gaming():
    """Returns (is_gaming, reason). Fullscreen apps, known games, borderless-fullscreen windows."""
    if not IS_WIN:
        return False, ""
    import ctypes
    from ctypes import wintypes
    user32, shell32 = ctypes.windll.user32, ctypes.windll.shell32

    # 1) Windows' own "a fullscreen app / D3D game / presentation is running" flag
    try:
        state = ctypes.c_int()
        if HIDE_FULLSCREEN and shell32.SHQueryUserNotificationState(ctypes.byref(state)) == 0 and state.value in (2, 3, 4):
            return True, f"windows-notification-state={state.value}"
    except Exception:
        pass

    try:
        class RECT(ctypes.Structure):
            _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

        class MONITORINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", RECT), ("rcWork", RECT), ("dwFlags", wintypes.DWORD)]

        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]
        user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
        user32.MonitorFromWindow.restype = wintypes.HMONITOR
        user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MONITORINFO)]
        user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]

        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return False, ""
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == os.getpid():
            return False, ""
        buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, buf, 256)
        if buf.value in _SHELL_CLASSES:
            return False, ""

        # 2) foreground process is a known game / lives in a game-launcher folder
        try:
            import psutil
            proc = psutil.Process(pid.value)
            name = (proc.name() or "").lower()
            exe = (proc.exe() or "").lower()
            if name in _DEFAULT_GAMES:
                return True, f"known-game={name}"
            for g in _user_games():
                if g in name or g in exe:
                    return True, f"games.txt={g}"
            if any(h in exe for h in _GAME_PATH_HINTS):
                return True, f"game-folder={name}"
        except Exception:
            pass

        # 3) borderless fullscreen: covers the whole monitor and has no title bar
        rect = RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        mon = user32.MonitorFromWindow(hwnd, 2)
        mi = MONITORINFO()
        mi.cbSize = ctypes.sizeof(MONITORINFO)
        if user32.GetMonitorInfoW(mon, ctypes.byref(mi)):
            m = mi.rcMonitor
            covers = rect.left <= m.left and rect.top <= m.top and rect.right >= m.right and rect.bottom >= m.bottom
            style = user32.GetWindowLongW(hwnd, -16)
            if HIDE_FULLSCREEN and covers and not (style & 0x00C00000):           # no WS_CAPTION
                return True, "borderless-fullscreen"
    except Exception as e:
        log("gaming check error:", e)
    return False, ""


if "--gaming-check" in sys.argv:
    print("Switch to your game now... checking in 6 seconds.")
    time.sleep(6)
    print("RESULT:", detect_gaming())
    sys.exit(0)

# ══════════════════════════════════════════════════════════════════════
#  WINDOWS HELPERS: clipboard paste, beep
# ══════════════════════════════════════════════════════════════════════


def set_clipboard(text: str) -> bool:
    import ctypes
    from ctypes import wintypes
    u, k = ctypes.windll.user32, ctypes.windll.kernel32
    k.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    k.GlobalAlloc.restype = wintypes.HGLOBAL
    k.GlobalLock.argtypes = [wintypes.HGLOBAL]
    k.GlobalLock.restype = ctypes.c_void_p
    k.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    u.OpenClipboard.argtypes = [wintypes.HWND]
    u.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    data = (text + "\0").encode("utf-16-le")
    opened = False
    for _ in range(20):
        if u.OpenClipboard(None):
            opened = True
            break
        time.sleep(0.05)
    if not opened:
        return False
    try:
        u.EmptyClipboard()
        h = k.GlobalAlloc(0x0042, len(data))               # GMEM_MOVEABLE | GMEM_ZEROINIT
        ptr = k.GlobalLock(h)
        ctypes.memmove(ptr, data, len(data))
        k.GlobalUnlock(h)
        u.SetClipboardData(13, h)                          # CF_UNICODETEXT
        return True
    finally:
        u.CloseClipboard()


def paste_text(text: str) -> bool:
    """Put text on the clipboard and press Ctrl+V in whatever window has focus (works for any language)."""
    if not IS_WIN or not text:
        return False
    if not set_clipboard(text):
        return False
    import ctypes
    u = ctypes.windll.user32
    time.sleep(0.08)
    u.keybd_event(0x11, 0, 0, 0)                           # Ctrl down
    u.keybd_event(0x56, 0, 0, 0)                           # V down
    time.sleep(0.02)
    u.keybd_event(0x56, 0, 2, 0)
    u.keybd_event(0x11, 0, 2, 0)
    time.sleep(0.12)
    return True


def beep(freq=1000, ms=70):
    try:
        import winsound
        winsound.Beep(freq, ms)
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════════
#  ROAMING (pure logic, no Qt)
# ══════════════════════════════════════════════════════════════════════


class WinPerch:
    """Win32 side of perching: finds the top edges of open windows he can stand on. Physical pixels in, logical out.
    Uses its own private user32/dwmapi handles so it never disturbs the argtypes detect_gaming() sets."""

    def __init__(self):
        import ctypes
        from ctypes import wintypes
        self.ct, self.wt = ctypes, wintypes
        u = self.u = ctypes.WinDLL("user32")
        d = self.dwm = ctypes.WinDLL("dwmapi")

        class RECT(ctypes.Structure):
            _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

        self.RECT = RECT
        self._enum_t = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        u.EnumWindows.argtypes = [self._enum_t, wintypes.LPARAM]
        for fn in (u.IsWindow, u.IsWindowVisible, u.IsIconic, u.GetWindowTextLengthW):
            fn.argtypes = [wintypes.HWND]
        u.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
        u.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        u.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        u.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]
        d.DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
        self.pid = os.getpid()

    def _cloaked(self, hwnd) -> bool:
        c = self.wt.DWORD()
        if self.dwm.DwmGetWindowAttribute(hwnd, 14, self.ct.byref(c), self.ct.sizeof(c)) == 0:   # DWMWA_CLOAKED
            return bool(c.value)
        return False

    def _frame(self, hwnd):
        """Visible window bounds (without the invisible resize border) as (l, t, r, b)."""
        r = self.RECT()
        if self.dwm.DwmGetWindowAttribute(hwnd, 9, self.ct.byref(r), self.ct.sizeof(r)) != 0:   # EXTENDED_FRAME_BOUNDS
            if not self.u.GetWindowRect(hwnd, self.ct.byref(r)):
                return None
        return r.left, r.top, r.right, r.bottom

    def _alive(self, hwnd) -> bool:
        u = self.u
        return bool(u.IsWindow(hwnd) and u.IsWindowVisible(hwnd) and not u.IsIconic(hwnd) and not self._cloaked(hwnd))

    def _usable(self, hwnd) -> bool:
        u = self.u
        if not self._alive(hwnd):
            return False
        if u.GetWindowLongW(hwnd, -20) & (0x00000080 | 0x00000020 | 0x08000000):   # toolwindow / click-through / no-activate
            return False
        if u.GetWindowTextLengthW(hwnd) == 0:
            return False
        buf = self.ct.create_unicode_buffer(256)
        u.GetClassNameW(hwnd, buf, 256)
        if buf.value in _SHELL_CLASSES:
            return False
        pid = self.wt.DWORD()
        u.GetWindowThreadProcessId(hwnd, self.ct.byref(pid))
        return pid.value != self.pid

    @staticmethod
    def _cut(segs, cl, cr):
        out = []
        for a, z in segs:
            if cr <= a or cl >= z:
                out.append((a, z))
                continue
            if cl > a:
                out.append((a, cl))
            if cr < z:
                out.append((cr, z))
        return out

    def find(self, scale: float):
        """Open windows front-to-back as (hwnd, left, top, right, seg_left, seg_right) in logical pixels.
        seg_* is the part of the top edge that no other window covers."""
        found, above = [], []

        def cb(hwnd, _lp):
            try:
                if hwnd and self._usable(hwnd):
                    fr = self._frame(hwnd)
                    if fr and fr[2] - fr[0] >= 300 and fr[3] - fr[1] >= 80:
                        l, t, r, b = fr
                        segs = [(l, r)]
                        for al, at, ar, ab in above:
                            if at <= t + 2 <= ab:
                                segs = self._cut(segs, al, ar)
                        for a, z in segs:
                            if z - a >= 140:
                                found.append((hwnd, l / scale, t / scale, r / scale, a / scale, z / scale))
                        above.append(fr)
            except Exception:
                pass
            return True

        self.u.EnumWindows(self._enum_t(cb), 0)
        return found

    def rect(self, hwnd, scale: float):
        """(left, top, right) of a window he is on / heading to, or None if it is gone, minimised or hidden."""
        try:
            if not self._alive(hwnd):
                return None
            fr = self._frame(hwnd)
            return (fr[0] / scale, fr[1] / scale, fr[2] / scale) if fr else None
        except Exception:
            return None


class Roamer:
    """Free 2D wandering. (x, y) is the position of his FEET on screen.
    Perching: now and then he walks to the top edge of an open window, sits there (riding along if the window is
    dragged) and drops back to the floor when it closes, minimises or moves out of reach."""

    def __init__(self, bounds, sw, sh, perch_finder=None, perch_rect=None):
        self.l, self.t, self.r, self.b = bounds
        self.sw, self.sh = sw, sh
        self.x = random.uniform(*self._xr())
        self.y = random.uniform(*self._yr())
        self.tx, self.ty = self.x, self.y
        self.state, self.timer = "idle", random.uniform(1.5, 4)
        self.facing, self.speed, self.moving = 1, 70.0, False
        self.vx = self.vy = 0.0
        self.perch_finder, self.perch_rect = perch_finder, perch_rect
        self.perch_enabled = perch_finder is not None
        self.perch = None                      # window handle he is heading to / sitting on
        self.perch_dx = 0.0                    # his x offset from that window's left edge
        self.perched = False
        self.gait = "walk"                     # how he walks this trip: walk / march / sneak / skip / run
        self.gait_queue = []                   # forced gaits for the next trips ("run around")
        self.script_v = None                   # (vx, vy) px/s while a scene moves him
        self.hold = False                      # True during a scene: no wandering of his own

    def _xr(self):
        return self.l + self.sw / 2 + 4, self.r - self.sw / 2 - 4

    def _yr(self):
        return self.t + self.sh + 8, self.b - 8

    def set_bounds(self, bounds):
        self.l, self.t, self.r, self.b = bounds
        self._clamp()

    def _clamp(self):
        x0, x1 = self._xr()
        y0, y1 = self._yr()
        self.x = min(max(self.x, x0), x1)
        self.y = min(max(self.y, y0), y1)

    def set_perch_enabled(self, on: bool):
        self.perch_enabled = bool(on) and self.perch_finder is not None
        if not self.perch_enabled and self.perch is not None:
            self._drop()

    def _drop(self):
        self.perch, self.perched = None, False
        self.state, self.timer = "idle", 0.3

    def _pick_perch(self, x0, x1, y0, y1):
        spots = []
        for hwnd, wl, top, wr, sl, sr in self.perch_finder():
            lo, hi = max(sl + 20, x0), min(sr - 20, x1)
            if hi > lo and y0 <= top <= y1:                    # needs room above his head and to be on screen
                spots.append((hwnd, wl, top, lo, hi))
        if not spots:
            return None
        hwnd, wl, top, lo, hi = random.choice(spots)
        tx = random.uniform(lo, hi)
        return hwnd, tx, top, tx - wl

    def _track_perch(self):
        """Follow the window he is on (or walking to); let go if it is gone or out of reach."""
        if self.perch is None:
            return
        try:
            rect = self.perch_rect(self.perch) if self.perch_rect else None
        except Exception:
            rect = None
        x0, x1 = self._xr()
        y0, y1 = self._yr()
        if rect is None or not (y0 <= rect[1] <= y1):
            self._drop()
            return
        left, top, right = rect
        lo, hi = max(left + 20, x0), min(right - 20, x1)
        if hi <= lo:
            self._drop()
            return
        tx = min(max(left + self.perch_dx, lo), hi)
        self.tx, self.ty = tx, top
        if self.perched:
            self.x, self.y = tx, top

    def pick_target(self):
        self.perch, self.perched = None, False
        x0, x1 = self._xr()
        y0, y1 = self._yr()
        self.gait, self.speed = self._pick_gait()
        if self.perch_enabled and self.perch_finder and random.random() < 0.4:
            try:
                spot = self._pick_perch(x0, x1, y0, y1)
            except Exception:
                spot = None
            if spot:
                self.perch, self.tx, self.ty, self.perch_dx = spot
                self.gait, self.speed = "walk", random.uniform(55, 95)
                return
        for _ in range(8):
            tx, ty = random.uniform(x0, x1), random.uniform(y0, y1)
            if math.hypot(tx - self.x, ty - self.y) > 220:
                break
        self.tx, self.ty = tx, ty

    def _pick_gait(self):
        """(gait, px/s). Mostly a normal stroll; now and then he marches, sneaks, skips or runs."""
        g = self.gait_queue.pop(0) if self.gait_queue else random.choices(
            ("walk", "march", "sneak", "skip", "run"), weights=(52, 10, 9, 9, 20))[0]
        lo, hi = {"walk": (55, 95), "march": (62, 82), "sneak": (28, 42), "skip": (70, 95), "run": (135, 180)}[g]
        return g, random.uniform(lo, hi)

    def update(self, dt, can_move=True):
        self.moving = False
        self.vx = self.vy = 0.0
        self._track_perch()                                   # rides his window even while napping / listening
        if self.script_v and not self.perched:                # a scene is walking him (fight advance, run to cursor)
            vx, vy = self.script_v
            self.x += vx * dt
            self.y += vy * dt
            self._clamp()
            self.vx, self.vy, self.moving = vx, vy, True
            if abs(vx) > 1:
                self.facing = 1 if vx > 0 else -1
            return
        if not can_move or self.hold:
            return
        if self.state == "idle":
            self.timer -= dt
            if self.timer <= 0:
                self.pick_target()
                self.state = "walk"
        if self.state == "walk":
            dx, dy = self.tx - self.x, self.ty - self.y
            dist = math.hypot(dx, dy)
            step = self.speed * dt
            if dist <= step:
                self.x, self.y = self.tx, self.ty
                self.state = "idle"
                if self.perch is not None:
                    self.perched, self.timer = True, random.uniform(15, 45)
                else:
                    self.timer = random.uniform(2.5, 9)
            else:
                self.x += dx / dist * step
                self.y += dy / dist * step
                self.vx, self.vy = dx / dist * self.speed, dy / dist * self.speed
                self.moving = True
                if abs(dx) > 4:
                    self.facing = 1 if dx > 0 else -1


# ══════════════════════════════════════════════════════════════════════
#  3D MODEL -> Qt painting
# ══════════════════════════════════════════════════════════════════════

_OUTLINE = QColor(28, 16, 16)


def draw_ares(p: QPainter, fr, scale: float, keep=None):
    """Paint one 3D frame (from ares_3d) : ground shadow, dark silhouette outline, then flat-shaded polygons."""
    cx, cy, rx, ry, alpha = fr.shadow
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(0, 0, 0, alpha))
    p.drawEllipse(QPointF(cx, cy), rx, ry)

    outfit = _STATE["outfit"]                     # keep = eye colours that must not be retinted
    polys = [(QPolygonF([QPointF(x, y) for x, y in pts]), SP.recolor(col, outfit, keep)) for pts, col in fr.polys]
    p.setBrush(_OUTLINE)
    p.setPen(QPen(_OUTLINE, max(2.0, scale * 0.55), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    for poly, col in polys:                       # pass 1: fat dark strokes -> only the silhouette survives pass 2
        if len(col) == 3:
            p.drawPolygon(poly)
    for poly, col in polys:                       # pass 2: the actual surfaces (thin same-hue edge hides AA seams)
        c = QColor(*col)
        p.setBrush(c)
        p.setPen(QPen(c.darker(112), 0.7) if len(col) == 3 else Qt.PenStyle.NoPen)
        p.drawPolygon(poly)


def head_icon(size=64) -> QPixmap:
    """Tray icon: 3D head, rendered once."""
    an = A3.Animator()
    fr = an.render("open", (255, 255, 255), size / 21.0, size * 0.5, size * 1.74, pitch=0.2)
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    pp = QPainter(pm)
    pp.setRenderHint(QPainter.RenderHint.Antialiasing)
    draw_ares(pp, fr, size / 21.0)
    pp.end()
    return pm


def _iv(x) -> int:
    try:
        return int(x.value)
    except Exception:
        return int(x)


TEXT_FLAGS = _iv(Qt.AlignmentFlag.AlignLeft) | _iv(Qt.AlignmentFlag.AlignTop) | _iv(Qt.TextFlag.TextWordWrap)
WRAP_ONLY = _iv(Qt.TextFlag.TextWordWrap)

BAR_COLORS = {"cyan": (110, 225, 255), "green": (120, 255, 150)}
BAR_HEIGHTS = [[3, 5, 2], [5, 2, 4], [2, 4, 5]]

# ══════════════════════════════════════════════════════════════════════
#  THE OVERLAY WIDGET
# ══════════════════════════════════════════════════════════════════════


class Bridge(QObject):
    """Thread-safe messages from the worker/hotkey threads into the GUI thread."""
    mood = Signal(str)
    bubble = Signal(str, float)
    hotkey = Signal()
    quit_sig = Signal()
    outfit = Signal(str)
    scene = Signal(str)


class Companion(QWidget):
    SLEEP_AFTER = 240.0                      # seconds of nothing before he naps

    def __init__(self, bridge: Bridge):
        super().__init__()
        flags = (Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool |
                 Qt.WindowType.NoDropShadowWindowHint | Qt.WindowType.WindowDoesNotAcceptFocus)
        if not CLICKS:                                       # old behaviour: completely click-through
            flags |= Qt.WindowType.WindowTransparentForInput
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        if not CLICKS:
            self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self.SW, self.SH = SP.W * SCALE, SP.H * SCALE
        self.BH = 190 + 8 * SCALE                           # room for the speech bubble + the icon above his head
        self.WW = max(460, self.SW + 200)
        self.WH = self.BH * 2 + self.SH
        self.resize(self.WW, self.WH)

        self.anim = A3.Animator()
        self.roamer = Roamer(self._work_area(), self.SW, self.SH)
        self.winperch = None
        if IS_WIN and PERCH:
            try:
                wp = self.winperch = WinPerch()
                dpr = lambda: max(0.5, float(QGuiApplication.primaryScreen().devicePixelRatio()))
                self.roamer.perch_finder = lambda: wp.find(dpr())
                self.roamer.perch_rect = lambda h: wp.rect(h, dpr())
                self.roamer.perch_enabled = True
            except Exception:
                self.winperch = None
                log("perching unavailable:", traceback.format_exc())

        self.forced = None
        self.forced_since = 0.0
        self.sleep_until = 0.0
        self.last_activity = time.time()
        self.anim_t = 0.0
        self.last_tick = time.time()
        self.bubble_text = ""
        self.bubble_until = 0.0
        self.hidden_reasons = set()
        self.agent = None
        self.ambient, self.ambient_until = None, 0.0        # passing moods (curious / bored) while nothing is going on
        self.next_ambient = time.time() + random.uniform(40, 90)
        self.scene = None                                   # running scripted scene (see ares_scenes.py)
        self.fx = []                                        # sparks / dust particles
        self.next_antic = time.time() + random.uniform(20, 45)
        self._through = False                               # True = mouse clicks pass straight through his window
        self.press = None                                   # left button held on him: {"g": (x, y), "drag": bool}
        self.dragging = False
        self.clicks = []                                    # times of recent pokes
        self._click_token = self._react_tok = 0
        self._drag_x = 0
        self._pet_last, self._pet_dir, self._pet_run = None, 0, 0.0
        self._pet_strokes, self._pet_cool = [], 0.0

        bridge.mood.connect(self.set_mood)
        bridge.bubble.connect(self.set_bubble)
        bridge.hotkey.connect(self.on_hotkey)
        bridge.scene.connect(self.start_scene)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(33)
        self.show()
        self._topmost()
        self._set_through(True)

    # ── screen ───────────────────────────────────────────────────────
    @staticmethod
    def _work_area():
        """Primary screen minus the taskbar, so he walks ON the taskbar instead of behind it."""
        g = QGuiApplication.primaryScreen().availableGeometry()
        return (g.left(), g.top(), g.right(), g.bottom() + 6)

    def refresh_screen(self):
        try:
            b = self._work_area()
            if b != (self.roamer.l, self.roamer.t, self.roamer.r, self.roamer.b):
                self.roamer.set_bounds(b)
                self.roamer.tx = min(max(self.roamer.tx, self.roamer._xr()[0]), self.roamer._xr()[1])
                self.roamer.ty = min(max(self.roamer.ty, self.roamer._yr()[0]), self.roamer._yr()[1])
        except Exception:
            pass

    # ── state ────────────────────────────────────────────────────────
    def set_mood(self, mood: str):
        self.cancel_scene()                                     # anything the agent shows interrupts a scene
        self.forced = None if mood in ("", "idle") else mood
        self.forced_since = time.time()
        self.anim_t = 0.0
        self.last_activity = time.time()
        self.sleep_until = 0.0

    def set_bubble(self, text: str, seconds: float):
        self.bubble_text = text
        self.bubble_until = (time.time() + seconds) if seconds > 0 else (1e18 if text else 0)

    def current_mood(self) -> str:
        now = time.time()
        if self.dragging:
            return "surprised"
        if self.forced:
            dur = SP.MOODS.get(self.forced, {}).get("dur")          # one-off reactions fade after `dur` seconds
            if dur and now - self.forced_since > dur:
                self.forced = None
            else:
                return self.forced
        if self.scene:
            return self.scene["steps"][self.scene["i"]][0]
        if self.sleep_until:
            if now >= self.sleep_until:
                self.sleep_until, self.last_activity = 0.0, now
            else:
                return "sleep"
        elif now - self.last_activity > self.SLEEP_AFTER:
            self.sleep_until = now + random.uniform(45, 100)
            return "sleep"
        idle_for = now - self.last_activity
        if idle_for > self.SLEEP_AFTER - 30:                        # drowsy just before the nap
            return "sleepy"
        if self.ambient and now < self.ambient_until:
            return self.ambient
        self.ambient = None
        if idle_for > 30 and now >= self.next_ambient:              # nothing going on: a small mood now and then
            self.ambient = "curious" if idle_for < 90 else "bored"
            self.ambient_until = now + random.uniform(4, 6)
            self.next_ambient = self.ambient_until + random.uniform(35, 80)
            return self.ambient
        return "walk" if self.roamer.moving else "idle"

    def on_hotkey(self):
        if self.hidden_reasons or self.agent is None:
            log("hotkey ignored: hidden=%s agent=%s" % (self.hidden_reasons, self.agent))
            return
        if self.current_mood() == "sleep":                      # woken up: a startled hop first, then he listens
            self.set_mood("surprised")
            QTimer.singleShot(650, self.agent.start_session)
            return
        self.agent.start_session()

    def set_hidden(self, reason: str, hidden: bool):
        before = bool(self.hidden_reasons)
        (self.hidden_reasons.add if hidden else self.hidden_reasons.discard)(reason)
        now_hidden = bool(self.hidden_reasons)
        if now_hidden and not before:
            self.timer.stop()
            self.hide()
        elif before and not now_hidden:
            self.last_tick = time.time()
            self.show()
            self.timer.start(33)
            self._topmost()
            self._through = False
            self._set_through(True)

    def _topmost(self):
        if not IS_WIN:
            return
        try:
            import ctypes
            ctypes.windll.user32.SetWindowPos(int(self.winId()), -1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)
        except Exception:
            pass

    # ── clicks: poke, pet, drag ──────────────────────────────────────
    # He is click-through except while the cursor is over his body: then the window turns solid (WS_EX_TRANSPARENT toggled per frame).
    def _set_through(self, on: bool):
        if not CLICKS or on == self._through:
            return
        self._through = on
        try:
            import ctypes
            u = ctypes.windll.user32
            h = int(self.winId())
            ex = u.GetWindowLongW(h, -20)
            u.SetWindowLongW(h, -20, (ex | 0x20) if on else (ex & ~0x20))      # -20 = GWL_EXSTYLE, 0x20 = WS_EX_TRANSPARENT
        except Exception:
            pass

    def _body_rect(self):
        r = self.roamer
        hw = self.SW * 0.28 + 6
        return r.x - hw, r.y - self.SH * 0.95, r.x + hw, r.y + 4

    def _busy(self) -> bool:
        return bool(self.agent and self.agent.lock.locked())

    def _react(self, mood: str, text: str, secs: float = 2.5):
        self.set_mood(mood)
        self.set_bubble(text, secs)
        self._react_tok += 1
        tok = self._react_tok
        QTimer.singleShot(int(secs * 1000), lambda: self._end_react(tok, mood))

    def _end_react(self, tok: int, mood: str):
        if tok == self._react_tok and self.forced == mood and not self.dragging:
            self.forced = None

    def _mem_nudge(self, delta: float):
        try:
            if self.agent:
                self.agent.mem.nudge(delta)
        except Exception:
            pass

    def _interact_tick(self, now: float):
        if not CLICKS:
            return
        try:
            c = QCursor.pos()
        except Exception:
            return
        x0, y0, x1, y1 = self._body_rect()
        inside = x0 <= c.x() <= x1 and y0 <= c.y() <= y1
        self._set_through(not (inside or self.dragging or self.press is not None))
        if not inside or self.dragging or self.press is not None or self._busy():
            self._pet_last, self._pet_dir, self._pet_run = None, 0, 0.0
            return
        if self._pet_last is not None:                       # petting = stroking the cursor back and forth over him
            dx = c.x() - self._pet_last
            if abs(dx) >= 2:
                s = 1 if dx > 0 else -1
                if self._pet_dir in (0, s):
                    self._pet_run += abs(dx)
                else:
                    if self._pet_run >= 16:
                        self._pet_strokes = [t for t in self._pet_strokes if now - t < 2.2] + [now]
                    self._pet_run = abs(dx)
                self._pet_dir = s
                if len(self._pet_strokes) >= 4 and now >= self._pet_cool:
                    self._pet_strokes, self._pet_cool = [], now + 8.0
                    self._mem_nudge(0.05)
                    self._react("love", random.choice(("Mm. That's nice, Boss.", "Systems nominal. Very nominal.",
                                                        "Keep going, Boss. Don't stop.", "I could get used to this.")), 3.2)
        self._pet_last = c.x()

    def mousePressEvent(self, ev):
        b = ev.button()
        if b == Qt.MouseButton.LeftButton:
            gp = ev.globalPosition().toPoint()
            self.press = {"g": (gp.x(), gp.y()), "drag": False}
            ev.accept()
        else:
            ev.ignore()

    def mouseMoveEvent(self, ev):
        if not self.press or not (ev.buttons() & Qt.MouseButton.LeftButton):
            return
        gp = ev.globalPosition().toPoint()
        if not self.press["drag"]:
            if math.hypot(gp.x() - self.press["g"][0], gp.y() - self.press["g"][1]) < 8:
                return
            self._drag_start(gp.x())
        self._drag_to(gp.x(), gp.y())

    def mouseReleaseEvent(self, ev):
        if ev.button() != Qt.MouseButton.LeftButton or not self.press:
            return
        p, self.press = self.press, None
        if p["drag"]:
            self._drag_end()
        else:
            self._click()

    def _drag_start(self, gx: int):
        r = self.roamer
        self.press["drag"] = self.dragging = True
        self.cancel_scene()
        r._drop()                                            # lets go of any window he was perched on
        r.hold, r.script_v = True, None
        self.forced, self.sleep_until = None, 0.0
        self.last_activity = time.time()
        self._drag_x = gx
        self.set_bubble(random.choice(("Whoa!", "Hey, careful!", "Put me down, Boss!", "I can walk, you know.")), 2.0)

    def _drag_to(self, gx: int, gy: int):
        r = self.roamer
        if abs(gx - self._drag_x) > 2:
            r.facing = 1 if gx > self._drag_x else -1
            self._drag_x = gx
        r.x, r.y = gx, gy + self.SH * 0.55                   # you hold him about the middle
        r._clamp()
        r.tx, r.ty = r.x, r.y
        self.last_activity = time.time()

    def _drag_end(self):
        r = self.roamer
        self.dragging = False
        r.hold = False
        r.state, r.timer = "idle", 1.5
        self._burst("dust")
        self._react("happy", random.choice(("Thanks for the lift, Boss.", "Smooth landing.", "New spot. I like it.",
                                            "Put me down gently next time.")), 2.6)

    def _click(self):
        now = time.time()
        self.clicks = [t for t in self.clicks if now - t < 4.0] + [now]
        self._click_token += 1
        tok = self._click_token
        QTimer.singleShot(0, lambda: self._poke(tok))

    def _poke(self, tok: int):
        if tok != self._click_token or self.dragging or self._busy():
            return
        n = len(self.clicks)
        if n >= 5:
            self.clicks = []
            self._mem_nudge(-0.06)
            self._react("angry", random.choice(("That's enough poking, Boss!", "Boss. Stop. Poking.")), 3.2)
        elif n >= 3:
            self._react("surprised", random.choice(("Boss...", "Okay, okay, I'm awake.", "Do that again and I'm filing a complaint.")), 2.4)
        else:
            self._react(random.choice(("surprised", "curious")),
                        random.choice(("Hm?", "Yes, Boss?", "Hey, that tickles.", "I'm working here, Boss.")), 2.2)

    # ── scenes: sit, fight, dance, flips ... ─────────────────────────
    def cancel_scene(self):
        self.scene = None
        self.roamer.hold = False
        self.roamer.script_v = None

    def start_scene(self, name: str, user: bool = True):
        r = self.roamer
        self.cancel_scene()
        if user:
            self.forced = None
            self.last_activity = time.time()
            self.sleep_until = 0.0
        if name in SC.GAIT_SCENES:
            r.gait_queue = [name] * 3
            r.state, r.timer = "idle", 0.1
            return
        if name == "stand":
            r.state, r.timer = "idle", 0.6
            return
        target = None
        if name == "cursor":
            try:
                c = QCursor.pos()
                x0, x1 = r._xr()
                y0, y1 = r._yr()
                target = (min(max(c.x(), x0), x1), min(max(c.y() + 10, y0), y1))
                if r.perched:
                    r._drop()
            except Exception:
                name = "wave"
        self.scene = {"steps": SC.make_scene(name, r.perched, target), "i": 0, "name": name}
        r.hold = True
        self._enter_step()

    def _enter_step(self):
        sc = self.scene
        mood, secs, o = sc["steps"][sc["i"]]
        sc.update(t=0.0, hit=False, land=False)
        self.anim_t = 0.0
        if o.get("say"):
            self.set_bubble(o["say"], 2.2)

    def _end_scene(self):
        r = self.roamer
        self.scene = None
        r.hold = False
        r.script_v = None
        r.state, r.timer = "idle", random.uniform(2, 5)
        self.next_antic = time.time() + random.uniform(35, 90)

    def _scene_tick(self, dt):
        sc = self.scene
        if not sc:
            return
        r = self.roamer
        mood, secs, o = sc["steps"][sc["i"]]
        sc["t"] += dt
        done = sc["t"] >= secs
        r.script_v = None
        if "go" in o:
            tx, ty = o["go"]
            dx, dy = tx - r.x, ty - r.y
            d = math.hypot(dx, dy)
            if d < 10:
                done = True
            else:
                r.script_v = (dx / d * 165.0, dy / d * 165.0)
        elif "mv" in o and not r.perched:
            r.script_v = (r.facing * o["mv"], 0.0)
        if o.get("hit") is not None and not sc["hit"] and sc["t"] >= o["hit"]:
            sc["hit"] = True
            self._burst("spark")
        if o.get("land") is not None and not sc["land"] and sc["t"] >= o["land"]:
            sc["land"] = True
            self._burst("dust")
        if done:
            sc["i"] += 1
            if sc["i"] >= len(sc["steps"]):
                self._end_scene()
            else:
                self._enter_step()

    def _burst(self, kind: str):
        ox, oy = self.WW / 2, self.BH + self.SH - 2 * SCALE
        f = self.roamer.facing
        if kind == "spark":
            x, y = ox + f * 13 * SCALE, oy - 17 * SCALE
            for _ in range(11):
                a = random.uniform(-math.pi, 0)
                v = random.uniform(80, 260)
                self.fx.append(dict(x=x, y=y, vx=math.cos(a) * v, vy=math.sin(a) * v, life=random.uniform(0.25, 0.5), max=0.5,
                                    col=random.choice(((255, 236, 140), (255, 190, 70), (255, 255, 255))), sz=random.choice((2, 3, 4)), g=500))
            threading.Thread(target=beep, args=(1700, 30), daemon=True).start()
        else:
            for sgn in (-1, 1):
                for _ in range(5):
                    self.fx.append(dict(x=ox + sgn * random.uniform(3, 8) * SCALE, y=oy, vx=sgn * random.uniform(20, 90),
                                        vy=random.uniform(-25, -5), life=random.uniform(0.35, 0.6), max=0.6,
                                        col=(200, 190, 175), sz=random.choice((4, 5, 6)), g=-10))

    def _fx_update(self, dt):
        for p in self.fx:
            p["x"] += p["vx"] * dt
            p["y"] += p["vy"] * dt
            p["vy"] += p["g"] * dt
            p["life"] -= dt
        self.fx = [p for p in self.fx if p["life"] > 0]

    def _draw_fx(self, p):
        for q in self.fx:
            c = QColor(*q["col"], int(255 * max(0.0, min(1.0, q["life"] / q["max"]))))
            p.fillRect(int(q["x"]), int(q["y"]), q["sz"], q["sz"], c)

    # ── frame loop ───────────────────────────────────────────────────
    def tick(self):
        now = time.time()
        dt = min(now - self.last_tick, 0.1)
        self.last_tick = now
        self._scene_tick(dt)
        self._fx_update(dt)
        self._interact_tick(now)
        mood = self.current_mood()
        r = self.roamer
        r.update(dt, mood in ("idle", "walk"))
        self.anim_t += dt
        if (ANTICS and not self.scene and mood == "idle" and now >= self.next_antic and now - self.last_activity > 8
                and not (self.agent and self.agent.lock.locked())):     # nothing going on: he entertains himself
            far = True
            try:
                c = QCursor.pos()
                far = math.hypot(c.x() - r.x, c.y() - r.y) > 350
            except Exception:
                pass
            self.next_antic = now + random.uniform(35, 90)
            self.start_scene(SC.pick_scene(r.perched, far), user=False)
            mood = self.current_mood()
        gait = r.gait
        if self.scene:
            gait = self.scene["steps"][self.scene["i"]][2].get("gait", "walk")
        base = SP.MOODS.get(mood, {}).get("base", mood)         # new emotions borrow an existing body pose
        self.anim.face, self.anim.edge = r.facing, r.perched
        self.anim.update(dt, base, math.hypot(r.vx, r.vy) / SCALE, r.vx, r.vy, gait)
        self.move(int(r.x - self.WW / 2), int(r.y - (self.BH + self.SH)))
        self.update()

    # ── drawing ──────────────────────────────────────────────────────
    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        p.fillRect(self.rect(), QColor(0, 0, 0, 0))
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        mood = self.current_mood()
        spec = SP.MOODS.get(mood, SP.MOODS["idle"])
        idx = int(self.anim_t / spec["fd"]) % len(spec["frames"])
        f = spec["frames"][idx]
        kind = f.get("eyes", "open")
        if self.anim.blinking():
            kind = "blink"
        rgb = SP.EYE_COLORS.get(f.get("color", "white"), SP.EYE_COLORS["white"])[:3]

        ox = self.WW / 2                                    # ground point under his feet, inside this window
        oy = self.BH + self.SH - 2 * SCALE
        fr = self.anim.render(kind, rgb, SCALE, ox, oy)
        draw_ares(p, fr, SCALE, keep={tuple(rgb)})
        self._draw_fx(p)

        if f.get("icon"):                                   # little icon floats above the top of his head
            hx, hy = fr.head_top
            self._icon(p, f["icon"], int(hx + 4 * SCALE), int(hy - 8 * SCALE))

        now = time.time()
        if self.bubble_text and now < self.bubble_until:
            scr = QGuiApplication.primaryScreen().geometry()
            room_above = (self.roamer.y - self.SH) - scr.top()
            room_below = scr.bottom() - self.roamer.y
            self._bubble(p, self.bubble_text, above=(room_above >= self.BH or room_above >= room_below))
        elif self.bubble_text and self.bubble_until < 1e17:
            self.bubble_text = ""
        p.end()

    def _icon(self, p, spec: str, x: int, y: int):
        name, *rest = spec.split(":")
        px = max(3, SCALE)
        rects, color = [], QColor(255, 255, 255)
        if name == "bars":
            heights = BAR_HEIGHTS[int(rest[0])]
            color = QColor(*BAR_COLORS.get(rest[1], (110, 225, 255)))
            for i, h in enumerate(heights):
                rects.append((x + i * px * 2, y + (6 - h) * px, px, h * px))
        elif name == "dots":
            color = QColor(255, 205, 70)
            for i in range(int(rest[0])):
                rects.append((x + i * px * 3, y + px * 4, px * 2, px * 2))
        elif name in SP.ICONS:
            color = QColor(*SP.ICON_COLORS[name])
            for r, row in enumerate(SP.ICONS[name]):
                for c, ch in enumerate(row):
                    if ch == "#":
                        rects.append((x + c * px, y + r * px, px, px))
        dark = QColor(28, 16, 16)
        for dx, dy in ((px, 0), (-px, 0), (0, px), (0, -px)):     # pixel outline
            for (rx, ry, rw, rh) in rects:
                p.fillRect(rx + dx, ry + dy, rw, rh, dark)
        for (rx, ry, rw, rh) in rects:
            p.fillRect(rx, ry, rw, rh, color)

    def _bubble(self, p, text: str, above: bool):
        font = QFont("Consolas", 10)
        font.setBold(True)
        p.setFont(font)
        fm = QFontMetrics(font)
        maxw = min(330, self.WW - 30)
        r = fm.boundingRect(QRect(0, 0, maxw, 1000), WRAP_ONLY, text)
        gap = 9 * SCALE                                     # keeps the bubble clear of the crest and the icons
        w, h = r.width() + 24, min(r.height() + 20, self.BH - gap - 14)
        cx = self.WW / 2
        x = max(6, min(self.WW - w - 6, cx - w / 2))
        y = (self.BH - gap - h) if above else (self.BH + self.SH + 14)
        p.setPen(QPen(QColor(225, 6, 0), 2))
        p.setBrush(QColor(18, 18, 18, 238))
        p.drawRoundedRect(QRectF(x, y, w, h), 6, 6)
        if above:
            tail = QPolygonF([QPointF(cx - 8, y + h), QPointF(cx + 8, y + h), QPointF(cx, y + h + 11)])
        else:
            tail = QPolygonF([QPointF(cx - 8, y), QPointF(cx + 8, y), QPointF(cx, y - 11)])
        p.drawPolygon(tail)
        p.setPen(QColor(255, 255, 255))
        p.drawText(QRect(int(x + 12), int(y + 10), int(w - 24), int(h - 20)), TEXT_FLAGS, text)


# ══════════════════════════════════════════════════════════════════════
#  LLM HELPER (email drafting, writing) — uses the same Groq models as the brain
# ══════════════════════════════════════════════════════════════════════


def llm_chat(brain, system: str, user: str, temperature: float = 0.4) -> str:
    key = brain.groq_key
    if not key:
        raise RuntimeError("GROQ_API_KEY missing")
    discovered = False
    last = "no models"
    while True:
        for m in list(brain.models):
            body = {"model": m, "temperature": temperature,
                    "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
            if "gpt-oss" in m:
                body["reasoning_effort"] = "low"
            try:
                r = requests.post(core.GROQ_URL, headers={"Authorization": f"Bearer {key}"}, json=body, timeout=45)
                if r.status_code == 200:
                    return (r.json()["choices"][0]["message"].get("content") or "").strip()
                last = f"{m}: HTTP {r.status_code} {r.text[:120]}"
            except Exception as e:
                last = f"{m}: {e}"
        if discovered:
            raise RuntimeError(last)
        discovered = True
        found = core.discover_chat_models(key)
        if not found:
            raise RuntimeError(last)
        brain.models = found[:4]


def parse_json_object(text: str) -> dict:
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    m = re.search(r"\{.*\}", text, re.S)
    return json.loads(m.group(0) if m else text)


def load_contacts() -> dict:
    try:
        return json.loads((DATA_DIR / "contacts.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


# ══════════════════════════════════════════════════════════════════════
#  COMMAND ROUTING
# ══════════════════════════════════════════════════════════════════════

_QUIT_RE = re.compile(r"\b(?:quit|exit|close|terminate|kill|shut ?down)\b.*\bares\b", re.I)
_DICT_RE = re.compile(r"^(?:please )?(?:start |begin |open )?(?:dictation|dictate)(?: mode)?$|^take (?:a )?dictation$|"
                      r"^let me dictate$|write (?:what(?:ever)? i (?:say|dictate)|as i (?:speak|talk|say))", re.I)
_EMAIL_RE = re.compile(r"\b(?:write|draft|compose|send|prepare|create|make)\b.{0,50}\b(?:e-?mail|mail|gmail)\b|"
                       r"\b(?:e-?mail|gmail)\b.{0,50}\b(?:to|about|saying|regarding)\b", re.I)
_SCREEN_RE = re.compile(r"what(?:'s| is)(?: currently| now)? (?:on )?(?:my|the) screen|(?:look|looking) at (?:my|the|this) screen|"
                        r"\b(?:see|read|check|describe|analy[sz]e|summari[sz]e)\b.{0,25}\b(?:my screen|the screen|this screen|"
                        r"this page|this window|my display)\b|what am i (?:looking at|seeing)", re.I)
_TYPE_RE = re.compile(r"^(?:please )?type\s+(.+)$", re.I)
_WRITE_RE = re.compile(r"^(?:please )?(?:write|draft|compose)\s+(?!down\b|a note\b|note\b|this down\b)(.+)$", re.I)
_FAIL_RE = re.compile(r"\b(couldn't|could not|can't|cannot|failed|fault|error|not found|isn't running|unavailable|blind|broke)\b", re.I)

_STOP_DICT = {"stop dictation", "stop dictating", "end dictation", "finish dictation", "stop", "done", "that's all",
              "that is all", "finished", "end"}
_PUNCT = [(r"\b(?:full stop|period)\b", "."), (r"\bcomma\b", ","), (r"\bquestion mark\b", "?"),
          (r"\bexclamation (?:mark|point)\b", "!"), (r"\bsemicolon\b", ";"), (r"\bcolon\b", ":"),
          (r"\bnew paragraph\b", "\n\n"), (r"\b(?:new|next) line\b", "\n"),
          (r"\bopen (?:bracket|parenthesis)\b", "("), (r"\bclose (?:bracket|parenthesis)\b", ")")]


def apply_punct(t: str) -> str:
    """Spoken punctuation -> real punctuation, keeps leading line breaks, capitalises sentence starts."""
    if core.active_language.get("name") != "english":
        return t
    for pat, rep in _PUNCT:
        t = re.sub(pat, rep, t, flags=re.I)
    t = t.strip(" \t")
    t = re.sub(r"[ \t]+([.,?!:;)])", r"\1", t)
    t = re.sub(r"\([ \t]+", "(", t)
    t = re.sub(r"[ \t]*\n[ \t]*", "\n", t)
    return re.sub(r"(^|[.!?]\s+|\n)([a-z])", lambda m: m.group(1) + m.group(2).upper(), t)


# ── screen reading: summaries, code explanations, fixes ──────────────
_SCR_NOT = re.compile(r"^(?:please )?(?:write|draft|compose|send|type|make|create|prepare|open|play|search|google)\b", re.I)
_SCR_VERB = re.compile(r"^(?:hey ares[,! ]*)?(?:please |can you |could you |would you )?(?:summari[sz]e|sum up|tl;?dr|"
                       r"give me (?:a )?(?:summary|gist|tl;?dr)|explain|walk me through|read|review|debug|fix|find|check|"
                       r"analy[sz]e|describe|translate|proofread|what|why|how|tell me|help me|look)\b", re.I)
_SCR_TARGET = re.compile(r"\b(?:on (?:my |the )?screen|my screen|the screen|this screen|(?:this|that|these|the current|the open) "
                         r"(?:page|window|tab|code|file|script|function|error|errors|message|article|document|doc|pdf|slide|email|"
                         r"mail|thread|chat|paper|website|site|text|output|log|terminal|traceback|stack ?trace|snippet|program|"
                         r"project|class|query|sheet|table|chart|diagram|problem|question|screenshot|image|diff|bug)|"
                         r"what i(?:'m| am) (?:looking at|reading|working on|coding|seeing))\b", re.I)
_SCR_CODE = re.compile(r"\b(?:code|script|function|bug|bugs|error|errors|traceback|stack ?trace|exception|compile|compiler|syntax|"
                       r"terminal|snippet|program|class|query|regex|debug|diff|commit|coding)\b", re.I)
_SCR_FIX = re.compile(r"\b(?:fix|debug|bug|bugs|wrong|broken|failing|fails|crash|crashing|traceback|exception|error|errors|"
                      r"not working|doesn'?t work)\b", re.I)
_SCR_REVIEW = re.compile(r"\b(?:review|improve|optimi[sz]e|refactor|clean up|better way)\b", re.I)
_SCR_SUM = re.compile(r"\b(?:summari[sz]e|summary|sum up|tl;?dr|gist|key points|main points|in short|brief me)\b", re.I)
_FOLLOW_RE = re.compile(r"^(?:ok(?:ay)?,? )?(?:tell me |say )?(?:more|more about (?:that|it|this)|explain (?:that|it|this)"
                        r"(?: (?:more|again|in detail|simply|simpler|better))?|go deeper|elaborate|in (?:more )?detail|"
                        r"(?:explain )?(?:that )?simpler|explain like i'?m five|what do you mean)$", re.I)

_SCREEN_PROMPTS = {
    "describe": "Describe what is on the screen: the app or site, what the user seems to be doing, and the important content. Max 120 words in DETAILS.",
    "summary": "Summarise the MAIN content (article, email, chat, document, page or code) in 3 to 6 short lines that each start with '- '. "
               "Ignore menus, ads, sidebars and browser chrome. If it is code, say what it does.",
    "read": "SPOKEN must read aloud the first 40 or so words of the main body text exactly as written (skip menus and UI). "
            "DETAILS must be the full main text transcribed as written.",
    "translate": "Translate the main visible text into English (or into the language the user asked for). "
                 "SPOKEN is the first sentence or two of the translation. DETAILS is the full translation.",
    "code": "The screen shows code. Explain it in plain language: purpose first, then the key steps or functions, and name the language. "
            "Refer to function names or line numbers you can see. Max 250 words in DETAILS.",
    "fix": "The screen shows code and/or an error. Give the most likely cause and the exact fix: quote the faulty line(s) and the corrected "
           "line(s). If there are several errors, deal with the first / top one first. If part of the code is cut off, say what you cannot see. "
           "Max 300 words in DETAILS.",
    "review": "Review the code shown: give up to 5 concrete improvements ordered by importance (bugs, edge cases, naming, performance), "
              "each with a one-line reason and the change to make. Max 300 words in DETAILS.",
}


def screen_intent(low: str):
    """'summarise this page', 'explain this code', 'fix this error', 'what's on my screen' -> (mode, scope), else None."""
    if _SCR_NOT.match(low):
        return None
    if not (_SCREEN_RE.search(low) or (_SCR_TARGET.search(low) and _SCR_VERB.match(low))):
        return None
    if re.search(r"\btranslate\b", low):
        mode = "translate"
    elif _SCR_FIX.search(low):
        mode = "fix"
    elif _SCR_CODE.search(low) and _SCR_REVIEW.search(low):
        mode = "review"
    elif _SCR_SUM.search(low):
        mode = "summary"
    elif _SCR_CODE.search(low):
        mode = "code"
    elif re.search(r"\bread\b", low):
        mode = "read"
    else:
        mode = "describe"
    return mode, ("screen" if re.search(r"\bscreen\b", low) else "window")


def _foreground_bbox():
    """Bounds (physical px) of the window you are working in, or None if it is the desktop / taskbar / ARES itself."""
    if not IS_WIN:
        return None
    try:
        import ctypes
        from ctypes import wintypes
        u, d = ctypes.WinDLL("user32"), ctypes.WinDLL("dwmapi")

        class RECT(ctypes.Structure):
            _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

        u.GetForegroundWindow.restype = wintypes.HWND
        u.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        u.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        u.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]
        d.DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
        hwnd = u.GetForegroundWindow()
        if not hwnd:
            return None
        pid = wintypes.DWORD()
        u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        buf = ctypes.create_unicode_buffer(256)
        u.GetClassNameW(hwnd, buf, 256)
        if pid.value == os.getpid() or buf.value in _SHELL_CLASSES:
            return None
        r = RECT()
        if d.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(r), ctypes.sizeof(r)) != 0:
            if not u.GetWindowRect(hwnd, ctypes.byref(r)):
                return None
        if r.right - r.left < 200 or r.bottom - r.top < 120:
            return None
        return r.left, r.top, r.right, r.bottom
    except Exception:
        return None


def grab_screen(scope: str = "window") -> str:
    """Screenshot as base64 JPEG. 'window' = the window you're working in (sharper text for code), else the primary screen."""
    import io
    import base64
    from PIL import ImageGrab
    img = None
    if scope == "window":
        bb = _foreground_bbox()
        if bb:
            try:
                img = ImageGrab.grab(bbox=bb, all_screens=True)
            except Exception:
                img = None
    if img is None:
        img = ImageGrab.grab()
    img = img.convert("RGB")
    img.thumbnail((2000, 2000))                                # keeps small code readable, stays well under the API size limit
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=88)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def vision_ask(prompt: str, img_b64: str, max_tokens: int = 900) -> str:
    key = os.getenv("GROQ_API_KEY", "").strip()
    if not key:
        raise RuntimeError("GROQ_API_KEY is missing from .env")
    model = core.pick_vision_model(key)
    if not model:
        raise RuntimeError("no vision model on your Groq account; set GROQ_VISION_MODEL in .env")
    body = {"model": model, "temperature": 0.2, "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}}]}]}
    r = requests.post(core.GROQ_URL, headers={"Authorization": f"Bearer {key}"}, json=body, timeout=60)
    if r.status_code != 200:
        raise RuntimeError(f"{model}: HTTP {r.status_code} {r.text[:120]}")
    return (r.json()["choices"][0]["message"].get("content") or "").strip()


def split_answer(raw: str):
    """'SPOKEN: ... DETAILS: ...' -> (short spoken line, full text)."""
    m = re.search(r"SPOKEN:\s*(.*?)\s*DETAILS:\s*(.*)$", raw, re.S | re.I)
    if m and m.group(1).strip():
        spoken, details = m.group(1).strip(), m.group(2).strip()
    else:
        details = raw.strip()
        spoken = core._short(details)
    return spoken.replace("**", ""), details.replace("**", "")


# ── outfits by voice ─────────────────────────────────────────────────
_OUTFIT_WORD = re.compile(r"\b(?:outfits?|armou?rs?|costumes?|skins?)\b|^(?:please )?(?:wear|put on|equip|dress up)\b", re.I)
_OUTFIT_SKIP = re.compile(r"\b(?:should i|for me|for my|for a|to wear|i wear|i'm wearing|my outfit|do i|how do i)\b", re.I)


def match_outfit(low: str):
    """-> ('set', key) | ('list', None) | ('random', None) | ('next', None) | None"""
    if not _OUTFIT_WORD.search(low) or _OUTFIT_SKIP.search(low):
        return None
    for key, spec in SP.OUTFITS.items():
        if any(re.search(r"\b%s\b" % re.escape(n), low) for n in (key,) + tuple(spec.get("aliases", ()))):
            return "set", key
    if re.search(r"\b(?:list|what|which|show|available|options|have|got)\b", low):
        return "list", None
    if re.search(r"\b(?:random|surprise)\b", low):
        return "random", None
    if re.search(r"\b(?:change|switch|swap|next|another|new|different|dress|wear)\b", low):
        return "next", None
    return None


# ── which emotion a reply deserves ───────────────────────────────────
_RUDE_RE = re.compile(r"\b(?:stupid|useless|idiot|dumb|shut up|hate you|you suck)\b", re.I)
_LOVE_RE = re.compile(r"\b(?:thank(?:s| you)|love you|you(?:'re| are) (?:the best|amazing|awesome|great)|appreciate)\b", re.I)
_PRAISE_RE = re.compile(r"\b(?:good (?:job|boy|work)|well done|nice (?:work|one|job)|great (?:job|work)|nailed it|perfect)\b", re.I)
_GREET_RE = re.compile(r"^(?:hey|hi|hello|yo|good (?:morning|afternoon|evening))\b", re.I)
_MUSIC_RE = re.compile(r"\b(?:play|music|song|playlist|spotify)\b", re.I)
_BYE_RE = re.compile(r"\b(?:good ?night|bye|goodbye|see you|going to sleep)\b", re.I)


def weather_line() -> str:
    """Short weather for the morning briefing (3 s timeout, '' on any failure)."""
    try:
        r = requests.get(f"https://wttr.in/{CITY}?format=%C,+%t", timeout=3)
        txt = r.text.strip()
        return f"{txt} in {CITY}" if r.status_code == 200 and txt and "<" not in txt else ""
    except Exception:
        return ""


class Agent:
    """Runs one voice session at a time on a worker thread."""

    def __init__(self, bridge: Bridge):
        self.b = bridge
        self.brain = core.AresBrain()
        self.lock = threading.Lock()
        self.speaking = False
        self._outcome = False          # True once a happy/error mood was shown (don't reset to idle over it)
        self.hint = None               # emotion a handler wants for this reply (overrides the automatic pick)
        self.fail_streak = 0           # failed replies in a row -> he gets properly annoyed after 3
        self.last_shot = None          # last screenshot + answer, so "more" / "explain simpler" can follow up
        self.mem = MEM.Memory()        # long-term memory (facts, turns, summary, mood)
        self.extras = EX.Extras(self.announce)          # reminders / timers / pomodoro / notes / stats / nudges
        self.brief = HAB.Briefing(core._jload, weather_line)      # first chat of the day: calendar + to-dos
        self.breaks = HAB.BreakNudger(self.announce)              # water / stretch / eyes after long stretches of work
        self.pending = None            # scene to start after he finishes speaking
        self.kind = "chat"             # what kind of exchange this was (stored with the memory turn)
        self._summarising = False

    # ── entry point ──────────────────────────────────────────────────
    def start_session(self, preset: str = None):
        if not self.lock.acquire(blocking=False):
            if self.speaking:                      # pressing the hotkey while he talks shuts him up
                core.stop_all_audio()
            return
        threading.Thread(target=self._run, args=(preset,), daemon=True).start()

    def _run(self, preset):
        quit_after = False
        self._outcome = False
        self.hint = None
        self.pending, self.kind = None, "chat"
        try:
            if preset is None:
                self.b.mood.emit("listen")
                self.b.bubble.emit("Listening…", 0)
                beep(1000)
                text = self.listen(timeout=7, phrase=20)
                if not text:
                    self.b.bubble.emit("Didn't catch that, Boss.", 3.5)
                    self.b.mood.emit("error")
                    self._outcome = True
                    return
            else:
                text = preset
            log("heard:", text)
            self.b.mood.emit("think")
            self.b.bubble.emit(f"“{text[:120]}”", 0)
            if _QUIT_RE.search(text):
                quit_after = True
                self.finish("Going dark, Boss. Until next time.")
                return
            reply = self.route(text)
            if self.kind in ("chat", "local"):
                reply = self.extras.session_prefix() + reply         # "Good morning, Boss." once a day
            brief = self._maybe_brief(reply)                         # first real chat of the day: calendar + to-dos afterwards
            self._record(text, reply)
            self.finish(reply, text)
            if brief:
                self.finish(brief, "")
            if self.pending:                                         # a scene he was asked to perform
                name, self.pending = self.pending, None
                self.b.scene.emit(name)
        except Exception:
            log(traceback.format_exc())
            self.finish("Something broke, Boss. Details are in companion.log.")
        finally:
            if quit_after:
                self.b.quit_sig.emit()
            elif not self._outcome:
                self.b.mood.emit("idle")
            self.lock.release()

    def _maybe_brief(self, reply: str) -> str:
        try:
            if self.kind not in ("chat", "local") or _FAIL_RE.search(reply) or not self.brief.due():
                return ""
            text = self.brief.build()
            self.brief.mark_done()
            self.mem.add_turn("assistant", text, "reminder")
            return text
        except Exception:
            log("briefing:", traceback.format_exc())
            return ""

    def pick_emotion(self, ask: str, reply: str, bad: bool) -> str:
        if self.hint:
            self.fail_streak = self.fail_streak + 1 if self.hint == "error" else 0
            return self.hint
        if bad:
            self.fail_streak += 1
            return "angry" if self.fail_streak >= 3 else "error"
        self.fail_streak = 0
        a = ask.lower()
        if _RUDE_RE.search(a):
            return "sad"
        if _LOVE_RE.search(a):
            return "love"
        if _PRAISE_RE.search(a):
            return "proud"
        if _GREET_RE.match(a):
            return "excited"
        if _MUSIC_RE.search(a):
            return "groove"
        if _BYE_RE.search(a):
            return "sleepy"
        m = self.mem.mood()
        if m >= 0.35:                                        # you have been kind: he is glowing
            return random.choice(("happy", "excited", "love", "proud"))
        if m <= -0.35:                                       # you have been harsh: he is subdued
            return random.choice(("sad", "sad", "worried", "happy"))
        return random.choice(("happy", "happy", "happy", "excited", "proud"))

    def finish(self, reply: str, ask: str = ""):
        reply = reply or "Done, Boss."
        bad = bool(_FAIL_RE.search(reply))
        self.b.bubble.emit(reply[:230], max(4.0, min(14.0, 2 + len(reply) * 0.045)))
        self.b.mood.emit("speak")
        self.speaking = True
        core._final_speaking.set()
        try:
            core.speak_sync(core._short(reply))
        except Exception:
            log("speak error:", traceback.format_exc())
        finally:
            core._final_speaking.clear()
            self.speaking = False
        self.b.mood.emit(self.pick_emotion(ask, reply, bad))
        self._outcome = True

    # ── listening ────────────────────────────────────────────────────
    def listen(self, timeout=7, phrase=20) -> str:
        sr = core.sr
        try:
            with sr.Microphone(device_index=core.get_live_mic_index()) as src:
                audio = core.recognizer.listen(src, timeout=timeout, phrase_time_limit=phrase)
            return core.recognizer.recognize_google(audio, language=core.active_language["stt_lang"]).strip()
        except (sr.WaitTimeoutError, sr.UnknownValueError):
            return ""
        except Exception as e:
            log("listen error:", e)
            return ""

    # ── routing ──────────────────────────────────────────────────────
    def route(self, text: str) -> str:
        t = text.strip().rstrip(".!?")
        low = t.lower()
        self.kind = "chat"
        mc = MEM.match_memory_command(t)
        if mc:
            return self.memory_cmd(*mc)
        if HAB.Briefing.wants(t):
            self.kind, self.hint = "local", "proud"
            self.brief.mark_done()
            return self.brief.build()
        br = self.breaks.handle(t)
        if br:
            self.kind, self.hint = "local", "happy"
            return br
        ex = self.extras.handle(text, self.mem.last_reply())
        if ex:
            reply, self.hint, self.kind = ex
            return reply
        act = SC.match_action(low)
        if act:
            return self.action_cmd(*act)
        o = match_outfit(low)
        if o:
            return self.outfit_cmd(*o)
        if self.last_shot and time.time() - self.last_shot["t"] < 180 and _FOLLOW_RE.match(low):
            return self.screen_task(text, "followup", "window")
        si = screen_intent(low)
        if si:
            return self.screen_task(text, *si)
        if _DICT_RE.search(low):
            return self.dictation()
        if _EMAIL_RE.search(low):
            return self.email_draft(text)
        if _SCREEN_RE.search(low):
            self.kind = "screen"
            return core.capture_screen_and_analyse(text)
        m = _TYPE_RE.match(t)
        if m:
            return "Typed, Boss." if paste_text(m.group(1)) else "I couldn't type that, Boss."
        m = _WRITE_RE.match(t)
        if m:
            return self.write_and_paste(t)
        try:                                                     # smart YouTube / maths / unit conversion (ares_tools.py)
            reply = TOOLS.youtube_command(text, core.open_browser)
            if reply:
                self.kind, self.hint = "local", ("groove" if reply.startswith("Playing") else None)
                return reply
            reply = TOOLS.quick_answer(text)
            if reply:
                self.kind = "local"
                return reply
            tr = TOOLS.translate_request(t)
            if tr and tr[1].lower() not in ("this", "that", "it"):
                self.kind = "chat"
                return self._think(f"Translate into {tr[0]} and reply with only the translation"
                                   f"{'' if tr[0] in ('English', 'Spanish', 'French', 'German', 'Italian', 'Portuguese') else ', then its pronunciation in English letters in brackets'}: {tr[1]}")
        except Exception:
            log("tools:", traceback.format_exc())
        reply = core.try_local_command(text)
        if reply is None:
            self.kind = "chat"
            reply = self._think(text)
        else:
            self.kind = "local"
        return reply

    def _think(self, text: str) -> str:
        """The brain, fed from long-term memory: recent turns (incl. local commands + screen readings) + facts + summary."""
        self.brain._hist = self.mem.recent_messages(10)
        pre = " ".join(x for x in (self.mem.context_block(), self.mem.style_hint()) if x)
        q = f"[Background about the user, use only if relevant: {pre}]\n{text}" if pre else text
        return asyncio.run(self.brain.think(q))

    def _record(self, ask: str, reply: str):
        try:
            extra = ""
            if self.kind == "screen" and self.last_shot and time.time() - self.last_shot["t"] < 30:
                extra = " (screen details: " + self.last_shot["details"][:350] + ")"
            self.mem.add_turn("user", ask, self.kind)
            self.mem.add_turn("assistant", reply + extra, self.kind)
            if self.mem.needs_summary() and not self._summarising:
                self._summarising = True

                def go():
                    try:
                        self.mem.refresh_summary(lambda sy, us: llm_chat(self.brain, sy, us, 0.2))
                    except Exception:
                        log("summary:", traceback.format_exc())
                    finally:
                        self._summarising = False
                threading.Thread(target=go, daemon=True).start()
        except Exception:
            log("memory:", traceback.format_exc())

    def memory_cmd(self, kind: str, arg) -> str:
        self.kind = "memory"
        self.hint = "proud" if kind in ("remember", "catchup") else "happy"
        if kind == "remember":
            return self.mem.remember(arg)
        if kind == "forget":
            return self.mem.forget(arg)
        if kind == "recall":
            return self.mem.facts_text()
        return self.mem.catch_up()

    def action_cmd(self, kind: str, name: str) -> str:
        self.kind = "scene"
        if kind == "mood":
            self.hint = name
            return random.choice(SC.MOOD_LINES.get(name, ("Okay, Boss.",)))
        self.pending = name
        self.hint = "idle"                                   # drop the emotion, the scene takes over after he speaks
        return random.choice(SC.ACT_LINES.get(name, ("On it, Boss.",)))

    def announce(self, text: str, hint: str = None):
        """Reminders, timers and nudges: wait until he is free, then say it out loud (also stored in memory)."""
        def go():
            for _ in range(60):
                if self.lock.acquire(blocking=False):
                    break
                time.sleep(3)
            else:
                return
            try:
                self._outcome, self.hint, self.pending, self.kind = False, hint, None, "reminder"
                self.mem.add_turn("assistant", text, "reminder")
                self.finish(text, "")
            except Exception:
                log("announce:", traceback.format_exc())
            finally:
                self.lock.release()
        threading.Thread(target=go, daemon=True).start()

    # ── looking at the screen ────────────────────────────────────────
    def screen_task(self, ask: str, mode: str, scope: str) -> str:
        self.kind = "screen"
        prev = self.last_shot
        follow = mode == "followup"
        eff = prev["mode"] if follow else mode
        self.b.mood.emit("code" if eff in ("fix", "review", "code") else "read")
        self.b.bubble.emit("Looking at your screen…", 0)
        try:
            if follow:
                img, scope = prev["img"], prev["scope"]
                task = (f"Earlier the user asked: '{prev['ask']}'. You answered: {prev['details'][:1500]}\n"
                        f"Now the user says: '{ask}'. Using the same screenshot, give the deeper or simpler explanation they want.")
            else:
                img = grab_screen(scope)
                task = _SCREEN_PROMPTS[mode]
            prompt = (f"You are ARES, a desktop assistant. You are looking at a screenshot of the user's "
                      f"{'screen' if scope == 'screen' else 'focused window'}. The user said: '{ask}'. Address the user as Boss. {task}\n"
                      "Only use what is visible; never invent text or code you cannot read, and say so if something is unreadable. "
                      "Reply in plain text (no markdown symbols) in EXACTLY this shape:\n"
                      "SPOKEN: <one or two short sentences, max 30 words, read aloud>\nDETAILS: <full answer>")
            spoken, details = split_answer(vision_ask(prompt, img))
        except Exception as e:
            log("screen task:", traceback.format_exc())
            self.hint = "error"
            return f"I couldn't read your screen, Boss ({str(e)[:90]})."
        self.last_shot = dict(t=time.time(), img=img, scope=scope, mode=eff, details=details,
                              ask=prev["ask"] if follow else ask)
        self.hint = "proud" if eff in ("fix", "review", "code") else "happy"
        try:
            if len(details) > len(spoken) + 40 and set_clipboard(details):
                spoken += " Details are on your clipboard."
        except Exception:
            pass
        return spoken

    # ── outfits ──────────────────────────────────────────────────────
    def outfit_cmd(self, kind: str, key) -> str:
        keys, cur = list(SP.OUTFITS), _STATE["outfit"]
        self.hint = "happy"
        if kind == "list":
            return "My outfits, Boss: " + ", ".join(SP.OUTFITS[k]["label"] for k in keys) + ". Say wear, then the name."
        if kind == "random":
            key = random.choice([k for k in keys if k != cur])
        elif kind == "next":
            key = keys[(keys.index(cur) + 1) % len(keys)]
        label = SP.OUTFITS[key]["label"]
        if key == cur:
            return f"I'm already in the {label}, Boss."
        self.b.outfit.emit(key)
        self.hint = "proud"
        return f"Switched to the {label}, Boss."

    # ── dictation ────────────────────────────────────────────────────
    def dictation(self) -> str:
        self.b.mood.emit("dictate")
        self.b.bubble.emit("Dictating… say “stop dictation” to finish.", 0)
        beep(1200, 60)
        silent, chunks = 0, 0
        while True:
            heard = self.listen(timeout=8, phrase=30)
            if not heard:
                silent += 1
                if silent >= 3:
                    break
                continue
            silent = 0
            if heard.lower().strip(" .,!?") in _STOP_DICT:
                break
            out = apply_punct(heard)
            paste_text(out + ("" if out.endswith("\n") else " "))
            chunks += 1
            self.b.bubble.emit(f"✎ {heard[-90:]}", 0)
        self.hint = "celebrate" if chunks >= 3 else None
        return f"Dictation finished, Boss. {chunks} passage{'s' if chunks != 1 else ''} written."

    # ── AI writing straight into the focused app ─────────────────────
    def write_and_paste(self, request: str) -> str:
        system = ("You write text that will be pasted directly into the user's document or app. "
                  "Output ONLY the finished text: no preface, no quotes around it, no markdown formatting, "
                  "no commentary. Match the tone and length the user asks for.")
        try:
            text = llm_chat(self.brain, system, request, 0.6)
        except Exception as e:
            return f"I couldn't reach my writing brain, Boss ({str(e)[:80]})."
        return "Written into your active window, Boss." if paste_text(text) else "I wrote it but couldn't paste it, Boss."

    # ── Gmail draft ──────────────────────────────────────────────────
    def email_draft(self, request: str) -> str:
        contacts = load_contacts()
        signoff = (f"End with 'Best regards,' and then the name {USER_NAME}." if USER_NAME
                   else "End with 'Best regards,' and no name.")
        system = (
            "Turn the user's spoken request into an email. Reply with ONLY one JSON object: "
            '{"to": "", "subject": "", "body": ""}. Rules: convert spoken addresses like "john at gmail dot com" '
            "into real ones; if the recipient is a name found in CONTACTS, use that address; if unknown, leave "
            '"to" empty. Write a clear, polite, natural email in the user\'s voice, with no placeholders like [Name]. '
            f"{signoff} CONTACTS: {json.dumps(contacts)}")
        try:
            data = parse_json_object(llm_chat(self.brain, system, request, 0.4))
        except Exception as e:
            return f"I couldn't draft that email, Boss ({str(e)[:80]})."
        to = str(data.get("to", "")).strip()
        subject = str(data.get("subject", "")).strip()
        body = str(data.get("body", "")).strip()
        q = requests.utils.quote
        base = f"https://mail.google.com/mail/u/{GMAIL_ACCOUNT}/?view=cm&fs=1&tf=1&to={q(to, safe='')}&su={q(subject, safe='')}"
        url = f"{base}&body={q(body, safe='')}"
        note = ""
        if len(url) > 6500:                       # too long for a URL: hand the body over via clipboard
            set_clipboard(body)
            url, note = base, " The body is on your clipboard, paste it with Ctrl V."
        core.open_browser(url, MAIL_BROWSER)
        who = f" to {to}" if to else ""
        return f"Draft{who} is open in Gmail, Boss: {subject or 'no subject'}. Check it and hit send.{note}"


# ══════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════


def register_hotkey(bridge: Bridge, comp):
    """Native Windows keyboard hook (ares_hotkey.py). Swallows the key only while Ares is visible."""
    try:
        import ares_hotkey
        hk = ares_hotkey.HotkeyHook(HOTKEY, on_press=lambda: (log("hotkey pressed"), bridge.hotkey.emit()),
                                    is_active=lambda: not comp.hidden_reasons,
                                    suppress=HOTKEY_SUPPRESS, log=log)
        hk.start()
        log(f"hotkey ready: {HOTKEY} (suppress={HOTKEY_SUPPRESS})")
        return hk
    except Exception:
        log("hotkey failed:", traceback.format_exc())
        return None


def main():
    # only one Ares at a time
    lock = socket.socket()
    try:
        lock.bind(("127.0.0.1", 47653))
    except OSError:
        print("ARES Companion is already running.")
        return

    ensure_startup()                          # first run: registers auto-start (never needs the terminal again)
    threading.Thread(target=ensure_start_menu_shortcut, daemon=True).start()

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    bridge = Bridge()
    comp = Companion(bridge)
    agent = Agent(bridge)
    comp.agent = agent
    agent.extras.is_active = lambda: time.time() - comp.last_activity < 900
    agent.extras.start()
    agent.breaks.can_nudge = lambda: not comp.hidden_reasons     # never nudge while a game is hiding him
    agent.breaks.start()
    bridge.quit_sig.connect(app.quit)

    # warm up voice + microphone in the background
    def _warm():
        try:
            core._get_kokoro()
        except Exception:
            pass
        try:
            with core.sr.Microphone(device_index=core.get_live_mic_index()) as s:
                core.recognizer.adjust_for_ambient_noise(s, duration=0.7)
        except Exception:
            pass
    threading.Thread(target=_warm, daemon=True).start()

    kb = register_hotkey(bridge, comp)

    # tray icon (head of the sprite) + menu
    tray = QSystemTrayIcon(QIcon(head_icon(64)), app)
    menu = QMenu()

    def act(text, fn, checkable=False, checked=False):
        a = QAction(text, menu)
        a.setCheckable(checkable)
        if checkable:
            a.setChecked(checked)
        a.triggered.connect(fn)
        menu.addAction(a)
        return a

    def type_command():
        text, ok = QInputDialog.getText(None, "ARES", "Command:")
        if ok and text.strip():
            agent.start_session(text.strip())

    act(f"Wake ({HOTKEY})", lambda: agent.start_session())
    act("Type a command…", type_command)
    pause_act = act("Pause / hide", lambda c: comp.set_hidden("paused", c), checkable=True)
    act("Hotkey on (untick to type ` normally)", lambda c: setattr(kb, "enabled", bool(c)) if kb else None,
        checkable=True, checked=True)
    outfit_menu = menu.addMenu("Outfit")
    outfit_group = QActionGroup(outfit_menu)
    outfit_group.setExclusive(True)
    outfit_actions = {}
    for _key, _spec in SP.OUTFITS.items():
        _a = QAction(_spec["label"], outfit_menu)
        _a.setCheckable(True)
        _a.setChecked(_key == _STATE["outfit"])
        outfit_group.addAction(_a)
        outfit_menu.addAction(_a)
        _a.triggered.connect(lambda _c=False, k=_key: bridge.outfit.emit(k))
        outfit_actions[_key] = _a

    def apply_outfit(key: str):
        if key not in SP.OUTFITS:
            return
        _STATE["outfit"] = key
        try:
            OUTFIT_FILE.write_text(key, encoding="utf-8")
        except Exception:
            pass
        if key in outfit_actions:
            outfit_actions[key].setChecked(True)
        try:
            tray.setIcon(QIcon(head_icon(64)))
        except Exception:
            pass
    bridge.outfit.connect(apply_outfit)

    do_menu = menu.addMenu("Do something")
    for _label, _nm in (("Sit down", "sit"), ("Sword fight", "battle"), ("Sword practice", "kata"), ("Dance", "dance"),
                        ("Disco", "disco"), ("Robot", "robot"), ("Flip", "flip"), ("Stretch", "stretch"), ("Flex", "flex"),
                        ("Meditate", "meditate"), ("Run around", "run"), ("Come to my cursor", "cursor"), ("Stand up", "stand")):
        _a = QAction(_label, do_menu)
        _a.triggered.connect(lambda _c=False, n=_nm: bridge.scene.emit(n))
        do_menu.addAction(_a)
    act("Random antics", lambda c: globals().__setitem__("ANTICS", bool(c)), checkable=True, checked=ANTICS)
    act("Today's briefing", lambda: agent.start_session("brief me"))
    brk_act = act("Break reminders", lambda c: agent.breaks.set_enabled(bool(c)), checkable=True, checked=agent.breaks.enabled)
    menu.aboutToShow.connect(lambda: brk_act.setChecked(agent.breaks.enabled))     # keeps in step with the voice command
    if comp.winperch:
        act("Perch on windows", lambda c: comp.roamer.set_perch_enabled(bool(c)), checkable=True, checked=True)
    act("Start with Windows", lambda c: log(set_startup(bool(c))), checkable=True, checked=is_startup_enabled())
    menu.addSeparator()
    act("Quit", app.quit)
    tray.setContextMenu(menu)
    tray.setToolTip("ARES Companion")
    tray.show()

    # hide while gaming / fullscreen
    def check_gaming():
        comp.refresh_screen()                     # taskbar moved / resolution changed / monitor swapped
        if not HIDE_WHEN_GAMING:
            if not comp.hidden_reasons:
                comp._topmost()
            return
        gaming, reason = detect_gaming()
        if gaming != ("gaming" in comp.hidden_reasons):
            log("gaming mode:", gaming, reason)
            comp.set_hidden("gaming", gaming)
        elif not gaming and not comp.hidden_reasons:
            comp._topmost()                       # keep him above other windows
    gt = QTimer()
    gt.timeout.connect(check_gaming)
    gt.start(1500)

    log("ARES Companion online.")
    code = app.exec()
    try:
        if kb:
            kb.stop()
    except Exception:
        pass
    core.stop_all_audio()
    sys.exit(code)


if __name__ == "__main__":
    main()