"""
ARES Apple Music diagnostic (read-only: presses nothing).

1. Open the Apple Music app and go to any song/album page (or ask ARES to play a song
   and let it fail).
2. Run:  python ares_music_diag.py
3. Paste the whole output here (also saved to  ~/ARES_Data/music_diag.txt).
"""
import os, sys, ctypes, asyncio, traceback

OUT = []


def log(*a):
    s = " ".join(str(x) for x in a)
    print(s)
    OUT.append(s)


log("=== ENVIRONMENT ===")
log("python:", sys.version.split()[0], "| 64-bit:", sys.maxsize > 2**32)
try:
    log("this script is admin:", bool(ctypes.windll.shell32.IsUserAnAdmin()))
except Exception as e:
    log("admin check failed:", e)

log("\n=== APPLE MUSIC PROCESSES ===")
pids = set()
try:
    import psutil
    for p in psutil.process_iter(["name", "pid", "username"]):
        n = (p.info["name"] or "")
        if "applemusic" in n.lower().replace(" ", ""):
            pids.add(p.info["pid"])
            log(f"pid={p.info['pid']} name={n}")
    if not pids:
        log("NONE FOUND -> Apple Music app is not running (or has a different process name)")
        log("all processes containing 'apple':",
            [p.info["name"] for p in psutil.process_iter(["name"]) if "apple" in (p.info["name"] or "").lower()])
except Exception:
    log(traceback.format_exc())

log("\n=== MEDIA SESSIONS (what Windows thinks is playing) ===")
try:
    try:
        from winsdk.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as MM
        log("using: winsdk")
    except Exception:
        from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as MM
        log("using: winrt")

    async def go():
        mgr = await MM.request_async()
        sessions = list(mgr.get_sessions())
        log("session count:", len(sessions))
        for s in sessions:
            st = int(s.get_playback_info().playback_status)
            names = {0: "CLOSED", 1: "OPENED", 2: "CHANGING", 3: "STOPPED", 4: "PLAYING", 5: "PAUSED"}
            log(f"  app_id={s.source_app_user_model_id}  status={st} ({names.get(st, '?')})")
    asyncio.run(go())
except ImportError:
    log("winsdk/winrt NOT importable -> run:  pip install winsdk")
    log("(on Python 3.13+ use:  pip install winrt-runtime winrt-Windows.Media.Control "
        "winrt-Windows.Foundation winrt-Windows.Foundation.Collections)")
except Exception:
    log(traceback.format_exc())

log("\n=== UI AUTOMATION: WINDOWS ===")
target = None
try:
    from pywinauto import Desktop
    import pywinauto
    log("pywinauto version:", getattr(pywinauto, "__version__", "?"))
    wins = Desktop(backend="uia").windows()
    log("total top-level windows:", len(wins))
    for w in wins:
        try:
            title = w.window_text() or ""
            pid = w.process_id()
            if "apple" in title.lower() or pid in pids:
                r = w.rectangle()
                log(f"  MATCH title={title!r} pid={pid} class={w.class_name()} rect={r} "
                    f"visible={w.is_visible()}")
                if target is None or (r.right - r.left) > 200:
                    target = w
        except Exception:
            continue
    if target is None:
        log("NO Apple Music window matched. Sample of window titles:",
            [ (w.window_text() or "")[:30] for w in wins[:15] ])
except Exception:
    log(traceback.format_exc())

log("\n=== UI AUTOMATION: CONTROLS ===")
if target is not None:
    try:
        desc = target.descendants()
        log("descendant controls:", len(desc))
        by_type = {}
        for c in desc:
            try:
                t = str(c.element_info.control_type)
                by_type[t] = by_type.get(t, 0) + 1
            except Exception:
                pass
        log("by type:", by_type)
        log("\n-- controls whose name contains play/shuffle/pause --")
        hits = 0
        for c in desc:
            try:
                n = (c.window_text() or "").strip()
                if any(k in n.lower() for k in ("play", "shuffle", "pause")):
                    hits += 1
                    aid = getattr(c.element_info, "automation_id", "") or ""
                    log(f"  {str(c.element_info.control_type):12} | {n[:60]:60} | id={aid[:30]} | {c.rectangle()}")
            except Exception:
                continue
        if hits == 0:
            log("  (none) -> the Play button is not exposed by name; see first 60 named controls below")
        log("\n-- first 60 named controls --")
        shown = 0
        for c in desc:
            try:
                n = (c.window_text() or "").strip()
                if n:
                    log(f"  {str(c.element_info.control_type):12} | {n[:70]}")
                    shown += 1
                    if shown >= 60:
                        break
            except Exception:
                continue
    except Exception:
        log(traceback.format_exc())
else:
    log("skipped (no window)")

try:
    d = os.path.join(os.path.expanduser("~"), "ARES_Data")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "music_diag.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(OUT))
    print("\nSaved to", os.path.join(d, "music_diag.txt"))
except Exception as e:
    print("could not save:", e)