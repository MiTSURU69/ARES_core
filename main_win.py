"""
Usage:  python make_windows.py            (reads main.py, writes main_win.py)
        python make_windows.py in.py out.py
Only the Mac-specific bits are changed. Everything else stays identical.
"""
import re
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "main.py"
out  = sys.argv[2] if len(sys.argv) > 2 else "main_win.py"

src = open(path, encoding="utf-8").read()
misses = []


def rep(old, new, label):
    global src
    if old not in src:
        misses.append(label)
        return
    src = src.replace(old, new)


def rrep(pat, new, label, flags=0):
    global src
    src2, n = re.subn(pat, lambda m: new, src, flags=flags)
    if n == 0:
        misses.append(label)
        return
    src = src2


HELPERS = r'''
# ══════════════════════════════════════════════════════════════════════
#  WINDOWS / CROSS-PLATFORM LAYER  (added)
# ══════════════════════════════════════════════════════════════════════
import pathlib
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

IS_WIN = os.name == "nt"
IS_MAC = sys.platform == "darwin"
_say_proc = None
_NO_WINDOW = 0x08000000 if IS_WIN else 0

if IS_WIN:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
    os.system("")  # enables ANSI colours in the Windows console


def clear_screen():
    os.system("cls" if IS_WIN else "clear")


def play_wav_blocking(path: str):
    path = os.path.abspath(path)
    if IS_WIN:
        import winsound
        winsound.PlaySound(path, winsound.SND_FILENAME)
    elif IS_MAC:
        subprocess.run(["afplay", "-v", "1.0", path],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        try:
            subprocess.run(["aplay", "-q", path],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except FileNotFoundError:
            pass


def play_mp3_blocking(path: str):
    path = os.path.abspath(path)
    if IS_MAC:
        subprocess.run(["afplay", path],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return
    try:
        import pygame
        if not pygame.mixer.get_init():
            pygame.mixer.init()
        pygame.mixer.music.load(path)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            time.sleep(0.05)
        try:
            pygame.mixer.music.unload()
        except Exception:
            pass
    except Exception:
        if IS_WIN:
            try:
                os.startfile(path)
            except Exception:
                pass


def system_say(text: str, block: bool = False):
    global _say_proc
    if IS_MAC:
        cmd = ["say", "-v", "Samantha", "-r", "185", text]
        if block:
            subprocess.run(cmd)
        else:
            subprocess.Popen(cmd)
    elif IS_WIN:
        safe = text.replace("'", "''")
        ps = ("Add-Type -AssemblyName System.Speech; "
              "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
              "$s.Speak('" + safe + "')")
        p = subprocess.Popen(
            ["powershell", "-NoProfile", "-Command", ps],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=_NO_WINDOW,
        )
        _say_proc = p
        if block:
            p.wait()


def _open_browser(target: str):
    try:
        if os.path.exists(target):
            target = pathlib.Path(target).resolve().as_uri()
    except Exception:
        pass
    if IS_MAC:
        try:
            subprocess.Popen(["open", "-a", "Safari", target])
            return
        except Exception:
            pass
    webbrowser.open(target)


def _grab_screen(path: str) -> bool:
    try:
        if IS_MAC:
            r = subprocess.run(["screencapture", "-x", path],
                               capture_output=True, timeout=5)
            return r.returncode == 0
        from PIL import ImageGrab
        try:
            img = ImageGrab.grab(all_screens=True) if IS_WIN else ImageGrab.grab()
        except TypeError:
            img = ImageGrab.grab()
        img.save(path)
        return True
    except Exception:
        return False


# ── Windows key / media control ──────────────────────────────────────
_VK = {"mute": 0xAD, "vol_down": 0xAE, "vol_up": 0xAF, "next": 0xB0,
       "prev": 0xB1, "stop": 0xB2, "playpause": 0xB3}


def _press_key(vk: int, times: int = 1):
    import ctypes
    for _ in range(times):
        ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
        ctypes.windll.user32.keybd_event(vk, 0, 2, 0)
        time.sleep(0.01)


def _win_set_volume(level: int) -> str:
    level = max(0, min(100, level))
    try:
        from ctypes import cast, POINTER
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        dev = AudioUtilities.GetSpeakers()
        try:
            vol = dev.EndpointVolume
        except AttributeError:
            iface = dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            vol = cast(iface, POINTER(IAudioEndpointVolume))
        vol.SetMasterVolumeLevelScalar(level / 100.0, None)
        return f"Volume set to {level}%."
    except Exception:
        # Fallback: each volume key press = 2%
        _press_key(_VK["vol_down"], 50)
        _press_key(_VK["vol_up"], level // 2)
        return f"Volume set to about {level}%."


def _win_control(action: str) -> str:
    a = action.lower()
    if a == "vol_up":
        _press_key(_VK["vol_up"], 5)
    elif a == "vol_down":
        _press_key(_VK["vol_down"], 5)
    elif a == "vol_mute":
        _press_key(_VK["mute"])
    elif a == "screenshot":
        desk = os.path.join(os.path.expanduser("~"), "Desktop")
        if not os.path.isdir(desk):
            desk = os.path.expanduser("~")
        p = os.path.join(desk, f"ares_shot_{int(time.time())}.png")
        return f"Screenshot saved: {p}" if _grab_screen(p) else "Screenshot failed."
    elif a == "sleep":
        subprocess.run(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])
    elif a == "lock":
        subprocess.run(["rundll32.exe", "user32.dll,LockWorkStation"])
    elif a == "empty_trash":
        subprocess.run(["powershell", "-NoProfile", "-Command",
                        "Clear-RecycleBin -Force -ErrorAction SilentlyContinue"],
                       creationflags=_NO_WINDOW)
    elif a == "mission_control":
        import ctypes
        u = ctypes.windll.user32
        u.keybd_event(0x5B, 0, 0, 0)
        u.keybd_event(0x09, 0, 0, 0)
        u.keybd_event(0x09, 0, 2, 0)
        u.keybd_event(0x5B, 0, 2, 0)
    elif a == "restart":
        subprocess.run(["shutdown", "/r", "/t", "5"])
    elif a == "shutdown":
        subprocess.run(["shutdown", "/s", "/t", "5"])
    else:
        return f"Unknown action '{action}'."
    return f"Windows: {action} executed."


_APP_ALIASES = {
    "calculator": "calc", "notepad": "notepad", "paint": "mspaint",
    "file explorer": "explorer", "explorer": "explorer",
    "task manager": "taskmgr", "settings": "ms-settings:",
    "cmd": "cmd", "command prompt": "cmd", "terminal": "wt",
    "powershell": "powershell", "chrome": "chrome", "edge": "msedge",
    "firefox": "firefox", "word": "winword", "excel": "excel",
    "powerpoint": "powerpnt", "spotify": "spotify", "vs code": "code",
    "vscode": "code", "camera": "microsoft.windows.camera:",
    "clock": "ms-clock:", "calendar": "outlookcal:", "mail": "outlookmail:",
}


def _win_open_app(app_name: str) -> str:
    target = _APP_ALIASES.get(app_name.lower().strip(), app_name)
    try:
        os.startfile(target)
        return f"Opened {app_name}."
    except Exception:
        r = subprocess.run(["cmd", "/c", "start", "", target],
                           capture_output=True, text=True)
        return (f"Opened {app_name}." if r.returncode == 0
                else f"Cannot open {app_name}.")


def _win_music(action: str, query: str = "") -> str:
    a = action.lower()
    keys = {"play": "playpause", "pause": "playpause", "stop": "stop",
            "next": "next", "previous": "prev"}
    if a in keys:
        _press_key(_VK[keys[a]])
        return f"Music: {action} sent to the active media player."
    if a == "volume_up":
        _press_key(_VK["vol_up"], 5)
        return "Volume up."
    if a == "volume_down":
        _press_key(_VK["vol_down"], 5)
        return "Volume down."
    if a in ("search_and_play", "play_playlist") and query:
        speak_sync(quip("music_search"))
        webbrowser.open("https://music.youtube.com/search?q=" + requests.utils.quote(query))
        return f"Opened YouTube Music search for '{query}' - pick it from the results, Boss."
    return f"Action '{action}' is not supported on Windows."


# ── Local storage for calendar / reminders / notes (Windows) ─────────
_DATA_DIR = os.path.join(os.path.expanduser("~"), "ARES_Data")


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


def _win_calendar(action, title="", date="", time_str="", notes="", duration_minutes=60):
    from datetime import timedelta
    if action == "open":
        try:
            os.startfile("outlookcal:")
        except Exception:
            webbrowser.open("https://calendar.google.com")
        return "Calendar open."
    events = _jload("calendar.json")
    if action in ("list_today", "list_tomorrow"):
        day = datetime.now().date() + timedelta(days=0 if action == "list_today" else 1)
        hits = sorted((e for e in events if e.get("date") == str(day)),
                      key=lambda e: e.get("time", ""))
        return "\n".join(f'{e["title"]} @ {e["time"]}' for e in hits) or "No events found."
    if action == "create_event":
        if not (title and date and time_str):
            return "Need title, date (YYYY-MM-DD) and time (HH:MM)."
        try:
            datetime.strptime(f"{date} {time_str}", "%Y-%m-%d %H:%M")
        except ValueError:
            return "Bad format. Use YYYY-MM-DD and HH:MM."
        events.append({"title": title, "date": date, "time": time_str,
                       "notes": notes, "duration": duration_minutes})
        _jsave("calendar.json", events)
        return f"Event '{title}' created."
    return f"Unknown calendar action: {action}."


def _win_reminders(action, title="", due_date="", notes=""):
    if action == "open":
        try:
            os.startfile("ms-todo:")
        except Exception:
            pass
        return "Reminders open."
    items = _jload("reminders.json")
    if action == "list":
        pending = [r for r in items if not r.get("done")]
        return "\n".join(r["title"] + (f' (due {r["due"]})' if r.get("due") else "")
                         for r in pending) or "No pending reminders."
    if action == "create" and title:
        items.append({"title": title, "due": due_date, "notes": notes, "done": False})
        _jsave("reminders.json", items)
        return f"Reminder '{title}' created."
    return "Specify action and title."


def _win_notes(action, title="", body=""):
    notes_dir = os.path.join(_DATA_DIR, "Notes")
    if action == "open":
        os.makedirs(notes_dir, exist_ok=True)
        os.startfile(notes_dir)
        return "Notes folder open."
    if action == "create" and title:
        os.makedirs(notes_dir, exist_ok=True)
        safe = "".join(c for c in title if c.isalnum() or c in " -_").strip() or "note"
        with open(os.path.join(notes_dir, safe + ".txt"), "w", encoding="utf-8") as f:
            f.write(body)
        return f"Note '{title}' created."
    if action == "list_recent":
        if not os.path.isdir(notes_dir):
            return "No notes."
        files = sorted((os.path.join(notes_dir, n) for n in os.listdir(notes_dir)),
                       key=os.path.getmtime, reverse=True)[:5]
        return "\n".join(os.path.splitext(os.path.basename(p))[0] for p in files) or "No notes."
    return "Actions: open, create, list_recent."

'''

# ── 1. helper block right after the tools import ─────────────────────
rep("from tools import available_tools\n",
    "from tools import available_tools\n" + HELPERS,
    "helpers")

# ── 2. audioop (removed in Python 3.13) → numpy RMS ──────────────────
rep("    import audioop\n    CHUNK = 1024", "    CHUNK = 1024", "audioop import")
rep("rms  = float(np.sqrt(np.mean(np.frombuffer(raw, dtype=np.int16).astype(np.float64) ** 2))) if raw else 0.0",
    "rms  = float(np.sqrt(np.mean(np.frombuffer(raw, dtype=np.int16).astype(np.float64) ** 2))) if raw else 0.0",
    "audioop rms")

# ── 3. Kokoro playback ────────────────────────────────────────────────
rrep(r'subprocess\.run\(\["afplay","-v","1\.0","ares_voice\.wav"\],\s*stdout=subprocess\.DEVNULL, stderr=subprocess\.DEVNULL\)',
     'play_wav_blocking("ares_voice.wav")', "kokoro afplay")

# ── 4. type-to-ask keypress on Windows ───────────────────────────────
rep('    if sys.platform != "darwin" and sys.platform != "linux":\n        return False\n',
    '    if os.name == "nt":\n'
    '        try:\n'
    '            import msvcrt\n'
    '            if msvcrt.kbhit():\n'
    '                return msvcrt.getwch().lower() == "t"\n'
    '            return False\n'
    '        except Exception:\n'
    '            return False\n'
    '    if sys.platform not in ("darwin", "linux"):\n'
    '        return False\n',
    "type trigger")

# ── 5. Screen capture ────────────────────────────────────────────────
rrep(r'tmp_path = f"/tmp/ares_screen_\{int\(time\.time\(\)\)\}\.png"\s+result = subprocess\.run\(\["screencapture", "-x", tmp_path\],\s*capture_output=True, timeout=5\)\s+if result\.returncode != 0:',
     'tmp_path = os.path.join(tempfile.gettempdir(), f"ares_screen_{int(time.time())}.png")\n'
     '        if not _grab_screen(tmp_path):',
     "screen capture")

# ── 6. Music poller only on Mac (osascript) ──────────────────────────
rep("def start_music_poller():\n    global _music_poll_thread, _music_poll_active\n",
    "def start_music_poller():\n    global _music_poll_thread, _music_poll_active\n"
    "    if not IS_MAC:\n        return\n",
    "music poller")

# ── 7. Browser opening ───────────────────────────────────────────────
rrep(r'try:\s*subprocess\.Popen\(\["open",\s*"-a",\s*"Safari",\s*tmpfile\.name\]\)\s*except Exception:\s*webbrowser\.open\(f"file://\{tmpfile\.name\}"\)',
     "_open_browser(tmpfile.name)", "html open")
rrep(r'try: subprocess\.Popen\(\["open","-a","Safari",url\]\)\s*except Exception: webbrowser\.open\(url\)',
     "_open_browser(url)", "url open")
rep("F1 Intelligence panel open in browser.", "F1 Intelligence panel open in browser.", "f1 msg")
rep("Opened in browser: {url}", "Opened in browser: {url}", "open_url msg")
rep("launched in browser", "launched in browser", "search msg")

# ── 8. Audio engine ──────────────────────────────────────────────────
rrep(r'def stop_all_audio\(\):\s+for proc in \("afplay","say"\):\s+subprocess\.run\(\["killall",proc\],[^\n]*\n',
     'def stop_all_audio():\n'
     '    global _say_proc\n'
     '    if IS_WIN:\n'
     '        try:\n'
     '            import winsound\n'
     '            winsound.PlaySound(None, winsound.SND_PURGE)\n'
     '        except Exception:\n'
     '            pass\n'
     '        if "pygame" in sys.modules:\n'
     '            try:\n'
     '                import pygame\n'
     '                if pygame.mixer.get_init():\n'
     '                    pygame.mixer.music.stop()\n'
     '            except Exception:\n'
     '                pass\n'
     '        try:\n'
     '            if _say_proc is not None and _say_proc.poll() is None:\n'
     '                _say_proc.terminate()\n'
     '        except Exception:\n'
     '            pass\n'
     '        return\n'
     '    for proc in ("afplay", "say"):\n'
     '        try:\n'
     '            subprocess.run(["killall", proc], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\n'
     '        except FileNotFoundError:\n'
     '            pass\n',
     "stop_all_audio")

rep('[sys.executable,"-m","edge_tts","--voice"', '[sys.executable,"-m","edge_tts","--voice"', "edge-tts cli")
rrep(r'subprocess\.run\(\["afplay","quip\.mp3"\],[^\n]*\)',
     'play_mp3_blocking("quip.mp3")', "quip afplay")
rrep(r'subprocess\.Popen\(\["say","-v","Samantha","-r","185",text\]\)',
     "system_say(text)", "say popen")
rrep(r'await loop\.run_in_executor\(None, lambda: subprocess\.run\(\s*\["afplay","voice\.mp3"\],[^\n]*\)\)',
     'await loop.run_in_executor(None, lambda: play_mp3_blocking("voice.mp3"))',
     "voice afplay")
rrep(r'await loop\.run_in_executor\(None, lambda: subprocess\.run\(\s*\["say","-v","Samantha","-r","185",text\]\)\)',
     "await loop.run_in_executor(None, lambda: system_say(text, block=True))",
     "say run")

# ── 9. Tools with Windows branches ───────────────────────────────────
rep("def apple_music_control(action: str, query: str = \"\") -> str:\n",
    "def apple_music_control(action: str, query: str = \"\") -> str:\n"
    "    if IS_WIN:\n        return _win_music(action, query)\n",
    "music control")
rep("def mac_control(action: str) -> str:\n",
    "def mac_control(action: str) -> str:\n"
    "    if IS_WIN:\n        return _win_control(action)\n",
    "mac_control")
rep("def open_app(app_name: str) -> str:\n",
    "def open_app(app_name: str) -> str:\n"
    "    if IS_WIN:\n        return _win_open_app(app_name)\n",
    "open_app")
rep("def set_volume(level: int) -> str:\n",
    "def set_volume(level: int) -> str:\n"
    "    if IS_WIN:\n        return _win_set_volume(level)\n",
    "set_volume")
rep("def get_system_info() -> str:\n",
    "def get_system_info() -> str:\n"
    "    if IS_WIN:\n"
    "        import platform\n"
    "        return (f\"{platform.system()} {platform.release()} ({platform.version()}), \"\n"
    "                f\"{platform.machine()}, {platform.processor()}\")[:500]\n",
    "system info")
rep('    speak_sync(quip("calendar"))\n',
    '    speak_sync(quip("calendar"))\n'
    "    if IS_WIN:\n        return _win_calendar(action, title, date, time_str, notes, duration_minutes)\n",
    "calendar")
rep('def reminders_action(action: str, title: str="", due_date: str="", notes: str="") -> str:\n',
    'def reminders_action(action: str, title: str="", due_date: str="", notes: str="") -> str:\n'
    "    if IS_WIN:\n        return _win_reminders(action, title, due_date, notes)\n",
    "reminders")
rep("def send_message_imessage(recipient: str, message: str) -> str:\n",
    "def send_message_imessage(recipient: str, message: str) -> str:\n"
    "    if IS_WIN:\n        return \"iMessage is not available on Windows, Boss.\"\n",
    "imessage")
rep('def notes_action(action: str, title: str="", body: str="") -> str:\n',
    'def notes_action(action: str, title: str="", body: str="") -> str:\n'
    "    if IS_WIN:\n        return _win_notes(action, title, body)\n",
    "notes")

# ── 10. main() + system prompt wording ───────────────────────────────
rep('    os.system("clear")\n    dashboard = make_ares_layout()',
    "    clear_screen()\n    dashboard = make_ares_layout()", "main clear")
rep("on MiTSURU's Windows PC.", "on MiTSURU's Windows PC.", "prompt mac")
rrep(r"- ALL web links, searches, and URLs must open in Safari\.\s*\n- Never suggest or use Chrome\.",
     "- ALL web links, searches, and URLs open in Boss's default browser.\n"
     "- Never claim a specific browser was used.", "prompt browsers")
rep("DEFAULT BROWSER LOCKED", "DEFAULT BROWSER LOCKED", "boot line")

open(out, "w", encoding="utf-8").write(src)

if misses:
    print("Written with warnings. These patches did not match (check that line manually):")
    for m in misses:
        print("  -", m)
else:
    print(f"OK - all patches applied. Wrote {out}")