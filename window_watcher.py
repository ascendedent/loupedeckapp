"""Active-window watcher for dynamic (focus-based) profile switching.

Qt-agnostic (platform adapter layer, per docs/PLAN.md 4.2). Reports the focused
window's ``wm_class`` (and title) so a ProfileManager can switch profiles when
the user changes apps.

Backend
-------
On KDE Plasma / Wayland the active window can't be read with X11 tools
(`xdotool`/`wmctrl`); it comes from KWin's scripting API. ``kdotool`` wraps that
API, so we shell out to it and **poll**. Polling (vs. an event-driven KWin
script + DBus callback) keeps this dependency-light and robust across Plasma
versions; ~400ms latency is fine for profile switching. An event-driven backend
can be added behind this same interface later.

Threading note: ``on_change`` fires on the watcher's background thread. A Qt UI
must marshal back to the main thread (e.g. via a signal) before touching widgets
or the device.
"""

import os
import shutil
import subprocess
import threading


def _run(args):
    try:
        out = subprocess.run(args, capture_output=True, text=True, timeout=2)
        return out.stdout.strip()
    except Exception:
        return ""


class WindowWatcher:
    """Base interface."""
    name = "none"

    def available(self):
        return False

    def poll_once(self):
        """Return (wm_class, title). Either may be '' if unknown."""
        return ("", "")

    def start(self):
        pass

    def stop(self):
        pass


class KdotoolWatcher(WindowWatcher):
    name = "kdotool"

    def __init__(self, on_change=None, interval=0.4):
        self.bin = shutil.which("kdotool")
        self.on_change = on_change
        self.interval = interval
        self._thread = None
        self._stop = threading.Event()
        self._last_class = None

    def available(self):
        return bool(self.bin)

    def poll_once(self):
        if not self.bin:
            return ("", "")
        wid = _run([self.bin, "getactivewindow"])
        if not wid:
            return ("", "")
        wm_class = _run([self.bin, "getwindowclassname", wid])
        title = _run([self.bin, "getwindowname", wid])
        return (wm_class, title)

    def _loop(self):
        while not self._stop.wait(self.interval):
            wm_class, title = self.poll_once()
            if wm_class and wm_class != self._last_class:
                self._last_class = wm_class
                if self.on_change:
                    try:
                        self.on_change(wm_class, title)
                    except Exception as e:
                        print("window_watcher: on_change failed: %s: %s" % (type(e).__name__, e))

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="WindowWatcher", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1)


def get_watcher(on_change=None, interval=0.4):
    """Return the best available watcher for this session (KdotoolWatcher on
    KDE, else a no-op WindowWatcher)."""
    w = KdotoolWatcher(on_change=on_change, interval=interval)
    if w.available():
        return w
    return WindowWatcher()
