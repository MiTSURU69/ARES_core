"""Patches ares_companion.py to use the native backtick hotkey (safe to run more than once)."""
import shutil, sys
from pathlib import Path

p = Path(__file__).resolve().parent / "ares_companion.py"
src = p.read_text(encoding="utf-8")
shutil.copy(p, p.with_name("ares_companion.py.bak"))

def swap(old, new):
    global src
    if old not in src:
        print("Could not find this text in ares_companion.py:\n   ", old[:80])
        sys.exit(1)
    src = src.replace(old, new, 1)

if "import ares_hotkey" not in src:
    swap('HOTKEY = os.getenv("ARES_HOTKEY", "right shift+`")', 'HOTKEY = os.getenv("ARES_HOTKEY", "`")')

    a = src.index("def register_hotkey(bridge: Bridge):")
    b = src.index("def main():", a)
    new_fn = '''def register_hotkey(bridge: Bridge, comp):
        """Native Windows keyboard hook (ares_hotkey.py). Swallows the key only while Ares is visible."""
        try:
            import ares_hotkey
            hk = ares_hotkey.HotkeyHook(HOTKEY, on_press=lambda: bridge.hotkey.emit(),
                                        is_active=lambda: not comp.hidden_reasons,
                                        suppress=HOTKEY_SUPPRESS, log=log)
            hk.start()
            log(f"hotkey ready: {HOTKEY} (suppress={HOTKEY_SUPPRESS})")
            return hk
        except Exception:
            log("hotkey failed:", traceback.format_exc())
            return None


    '''
    src = src[:a] + new_fn + src[b:]

    swap("kb = register_hotkey(bridge)", "kb = register_hotkey(bridge, comp)")
    swap("kb.unhook_all()", "kb.stop()")
    swap('    pause_act = act("Pause / hide", lambda c: comp.set_hidden("paused", c), checkable=True)\n',
         '    pause_act = act("Pause / hide", lambda c: comp.set_hidden("paused", c), checkable=True)\n'
         '    act("Hotkey on (lets you type ` when off)", lambda c: setattr(kb, "enabled", bool(c)) if kb else None,\n'
         '        checkable=True, checked=True)\n')
src = src.replace("Press  Right Shift + ~  and he listens", "Press  `  (backtick) and he listens")
# log hotkey presses so problems are visible in companion.log
if 'log("hotkey pressed")' not in src:
    src = src.replace("on_press=lambda: bridge.hotkey.emit(),", 'on_press=lambda: (log("hotkey pressed"), bridge.hotkey.emit()),', 1)
    src = src.replace("    def on_hotkey(self):\n        if self.hidden_reasons or self.agent is None:\n            return\n",
                      "    def on_hotkey(self):\n        if self.hidden_reasons or self.agent is None:\n            log('hotkey ignored: hidden=%s agent=%s' % (self.hidden_reasons, self.agent))\n            return\n", 1)
# the ARES brain file is called main.py on this machine
src = src.replace("import ares as core", "import main as core")
src = src.replace("Files:  ares.py and", "Files:  main.py and")
p.write_text(src, encoding="utf-8")
print("ares_companion.py patched. Backup saved as ares_companion.py.bak")
