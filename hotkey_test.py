"""Tests ONLY the backtick hook, without the rest of Ares. Run:  python hotkey_test.py"""
import time
import ares_hotkey

hk = ares_hotkey.HotkeyHook("`", on_press=lambda: print("  >>> backtick detected", flush=True),
                            suppress=True, log=print)
hk.start()
print("Hook installed. Click this window, press ` a few times (nothing should be typed),")
print("then press Shift+` (should type ~). Press Ctrl+C to quit.")
try:
    while True:
        time.sleep(0.5)
except KeyboardInterrupt:
    hk.stop()
