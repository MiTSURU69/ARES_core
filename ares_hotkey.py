"""
ares_hotkey.py - native Windows global hotkey for the ARES Companion.

Uses a WH_KEYBOARD_LL hook (no 'keyboard' package needed).
Default hotkey is the bare backtick key:  `
  * Only the plain ` press is caught. Shift+` (~), Ctrl+`, Alt+`, Win+` pass straight through.
  * The key is swallowed ONLY while is_active() is True. While Ares is hidden (paused / a game or
    fullscreen app is in front) every key passes through untouched.
  * Keystrokes injected by other programs (including Ares' own pasting) are never touched.

ARES_HOTKEY examples:  `   f9   right shift+f9   ctrl+alt+a
"""
import time
import threading

_VK = {"`": 0xC0, "grave": 0xC0, "tilde": 0xC0, "space": 0x20, "tab": 0x09, "caps lock": 0x14,
       "insert": 0x2D, "pause": 0x13, "scroll lock": 0x91, "home": 0x24, "end": 0x23,
       "page up": 0x21, "page down": 0x22, "-": 0xBD, "=": 0xBB, ";": 0xBA, "'": 0xDE,
       ",": 0xBC, ".": 0xBE, "/": 0xBF, "\\": 0xDC, "[": 0xDB, "]": 0xDD}
for _i in range(1, 25):
    _VK[f"f{_i}"] = 0x6F + _i
for _c in "abcdefghijklmnopqrstuvwxyz0123456789":
    _VK[_c] = ord(_c.upper())

# modifier token -> (class, specific vk or None)
_MODS = {"shift": ("shift", None), "left shift": ("shift", 0xA0), "right shift": ("shift", 0xA1),
         "ctrl": ("ctrl", None), "control": ("ctrl", None), "left ctrl": ("ctrl", 0xA2), "right ctrl": ("ctrl", 0xA3),
         "alt": ("alt", None), "left alt": ("alt", 0xA4), "right alt": ("alt", 0xA5),
         "win": ("win", None), "windows": ("win", None), "left windows": ("win", 0x5B), "right windows": ("win", 0x5C)}
_GENERIC = {"shift": 0x10, "ctrl": 0x11, "alt": 0x12}


class Spec:
    def __init__(self, text: str):
        parts = [p.strip().lower() for p in text.replace("+ ", "+").split("+") if p.strip()]
        if text.strip().endswith("++"):
            parts.append("+")
        if not parts:
            parts = ["`"]
        key = parts[-1]
        if key not in _VK:
            raise ValueError(f"unknown hotkey '{key}'")
        self.vk = _VK[key]
        self.required = {}                      # class -> specific vk or None
        for m in parts[:-1]:
            if m not in _MODS:
                raise ValueError(f"unknown modifier '{m}'")
            cls, vk = _MODS[m]
            self.required[cls] = vk
        self.text = text


def mods_ok(spec: Spec, down: dict) -> bool:
    """down: {'shift','ctrl','alt','win'} -> bool (generic), and 'vk:<n>' -> bool for specific keys.
    Trigger only when every required modifier is down and NO other modifier is down."""
    for cls in ("shift", "ctrl", "alt", "win"):
        if cls in spec.required:
            specific = spec.required[cls]
            if specific is not None:
                if not down.get(f"vk:{specific}", False):
                    return False
            elif not down.get(cls, False):
                return False
        elif down.get(cls, False):
            return False
    return True


def decide(spec: Spec, vk: int, is_down: bool, down_mods: dict, state: dict, active: bool, enabled: bool,
           suppress: bool, now: float):
    """Pure decision logic. state = {'held': bool, 'swallow': bool, 'last': float}.
    Returns (fire: bool, swallow_this_event: bool)."""
    if vk != spec.vk:
        return False, False
    if is_down:
        if state["held"] and now - state["last"] > 1.5:      # missed key-up: recover
            state["held"] = state["swallow"] = False
        state["last"] = now
        if state["held"]:                                     # auto-repeat of a press we already handled
            return False, state["swallow"]
        if enabled and active and mods_ok(spec, down_mods):
            state["held"] = True
            state["swallow"] = bool(suppress)
            return True, bool(suppress)
        return False, False
    # key up
    if state["held"]:
        sw = state["swallow"]
        state["held"] = state["swallow"] = False
        return False, sw
    return False, False


class HotkeyHook:
    def __init__(self, spec_text, on_press, is_active=lambda: True, suppress=True, log=lambda *a: None):
        self.spec = Spec(spec_text)
        self.on_press, self.is_active, self.suppress, self.log = on_press, is_active, suppress, log
        self.enabled = True
        self._state = {"held": False, "swallow": False, "last": 0.0}
        self._thread = None
        self._tid = 0
        self._ready = threading.Event()
        self._ok = False

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True, name="ares-hotkey")
        self._thread.start()
        self._ready.wait(3)
        if not self._ok:
            raise RuntimeError("could not install the keyboard hook")

    def stop(self):
        try:
            import ctypes
            if self._tid:
                ctypes.windll.user32.PostThreadMessageW(self._tid, 0x0012, 0, 0)     # WM_QUIT
        except Exception:
            pass

    def _run(self):
        import ctypes
        from ctypes import wintypes
        user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
        LRESULT = ctypes.c_ssize_t
        HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)

        class KBDLLHOOKSTRUCT(ctypes.Structure):
            _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD), ("flags", wintypes.DWORD),
                        ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]

        user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, ctypes.c_void_p, wintypes.DWORD]
        user32.SetWindowsHookExW.restype = ctypes.c_void_p
        user32.CallNextHookEx.argtypes = [ctypes.c_void_p, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
        user32.CallNextHookEx.restype = LRESULT
        user32.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]
        user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
        user32.GetAsyncKeyState.restype = ctypes.c_short
        user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        kernel32.GetModuleHandleW.restype = ctypes.c_void_p

        def key_down(vk):
            return bool(user32.GetAsyncKeyState(vk) & 0x8000)

        def snapshot():
            d = {"shift": key_down(0x10), "ctrl": key_down(0x11), "alt": key_down(0x12),
                 "win": key_down(0x5B) or key_down(0x5C)}
            for vk in self.spec.required.values():
                if vk is not None:
                    d[f"vk:{vk}"] = key_down(vk)
            return d

        def proc(nCode, wParam, lParam):
            try:
                if nCode == 0:
                    k = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                    if k.vkCode == self.spec.vk and not (k.flags & 0x10):            # ignore injected keys
                        is_down = wParam in (0x0100, 0x0104)
                        fire, swallow = decide(self.spec, k.vkCode, is_down, snapshot() if is_down else {},
                                               self._state, bool(self.is_active()), self.enabled,
                                               self.suppress, time.time())
                        if fire:
                            try:
                                self.on_press()
                            except Exception:
                                pass
                        if swallow:
                            return 1
            except Exception:
                pass
            return user32.CallNextHookEx(None, nCode, wParam, lParam)

        cb = HOOKPROC(proc)                                   # keep a reference or it gets garbage collected
        hook = user32.SetWindowsHookExW(13, cb, kernel32.GetModuleHandleW(None), 0)
        self._tid = kernel32.GetCurrentThreadId()
        self._ok = bool(hook)
        self._ready.set()
        if not hook:
            self.log("SetWindowsHookExW failed, error", ctypes.get_last_error())
            return
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        user32.UnhookWindowsHookEx(hook)
