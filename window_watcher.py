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
        # PID of the window seen in the most recent poll. Callers use it to
        # recognise their own window, which cannot be done by name: the class
        # is the toolkit's ("python3" on native Wayland), not the app's.
        self.last_pid = 0

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
        try:
            self.last_pid = int(_run([self.bin, "getwindowpid", wid]) or 0)
        except (TypeError, ValueError):
            self.last_pid = 0
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


class XpropWatcher(WindowWatcher):
    """X11, through `_NET_ACTIVE_WINDOW`.

    The property the window manager sets to say which window has focus, read
    with `xprop`, which ships with X11 itself rather than being something else
    to install. Works under any X11 session, and under XWayland for the subset
    of windows that are X11 clients, which is why it sits below the
    compositor-native watchers rather than above them.
    """
    name = "xprop"

    ACTIVE = ["-root", "_NET_ACTIVE_WINDOW"]

    def __init__(self, on_change=None, interval=0.4):
        self.bin = shutil.which("xprop")
        self.on_change = on_change
        self.interval = interval
        self._thread = None
        self._stop = threading.Event()
        self._last_class = None
        self.last_pid = 0

    def available(self):
        import platform_env
        if not self.bin:
            return False
        if platform_env.session_type() != platform_env.X11:
            return False
        # An X11 session with no reachable display is not one we can read.
        return bool(_run([self.bin] + self.ACTIVE))

    @staticmethod
    def _window_id(text):
        """`_NET_ACTIVE_WINDOW(WINDOW): window id # 0x3400007` -> the id."""
        if not text or "#" not in text:
            return ""
        wid = text.rsplit("#", 1)[1].strip()
        # A window manager with nothing focused reports 0x0.
        return "" if wid in ("", "0x0") else wid

    @staticmethod
    def _wm_class(text):
        """`WM_CLASS(STRING) = "navigator", "Firefox"` -> "Firefox".

        Two values: the instance name and the class. The class is the one
        applications are known by and the one a desktop entry's StartupWMClass
        matches, so it is the one used, falling back to the instance.
        """
        if "=" not in text:
            return ""
        values = [v.strip().strip('"')
                  for v in text.split("=", 1)[1].split(",")]
        values = [v for v in values if v]
        return values[-1] if values else ""

    @staticmethod
    def _string_value(text):
        if "=" not in text:
            return ""
        return text.split("=", 1)[1].strip().strip('"')

    def poll_once(self):
        if not self.bin:
            return ("", "")
        wid = self._window_id(_run([self.bin] + self.ACTIVE))
        if not wid:
            return ("", "")
        wm_class = self._wm_class(_run([self.bin, "-id", wid, "WM_CLASS"]))
        title = self._string_value(_run([self.bin, "-id", wid, "_NET_WM_NAME"]))
        if not title:
            title = self._string_value(_run([self.bin, "-id", wid, "WM_NAME"]))
        try:
            pid = _run([self.bin, "-id", wid, "_NET_WM_PID"])
            self.last_pid = int(pid.rsplit("=", 1)[1].strip()) if "=" in pid else 0
        except (TypeError, ValueError, IndexError):
            self.last_pid = 0
        return (wm_class, title)

    _loop = KdotoolWatcher._loop
    start = KdotoolWatcher.start
    stop = KdotoolWatcher.stop


class GnomeWatcher(WindowWatcher):
    """GNOME Shell on Wayland, through an extension.

    GNOME deliberately gives no way to ask which window has focus: Eval was
    closed off in GNOME 41 and there is no portal for it. The only route left is
    an extension that exposes the answer on the session bus, so this speaks to
    the two common ones rather than picking a favourite. If neither is
    installed, this watcher declines and the setup checks say which to install.

    That is a real limitation and not one this app can fix from outside; it is
    reported rather than worked around.
    """
    name = "gnome-extension"

    # (object path, method, whether the reply is a list of windows)
    INTERFACES = [
        ("/org/gnome/shell/extensions/FocusedWindow",
         "org.gnome.shell.extensions.FocusedWindow.Get", False),
        ("/org/gnome/Shell/Extensions/Windows",
         "org.gnome.Shell.Extensions.Windows.List", True),
    ]

    def __init__(self, on_change=None, interval=0.4):
        self.bin = shutil.which("gdbus")
        self.on_change = on_change
        self.interval = interval
        self._thread = None
        self._stop = threading.Event()
        self._last_class = None
        self.last_pid = 0
        self._iface = None          # the one that answered, remembered

    def _call(self, path, method):
        return _run([self.bin, "call", "--session", "--dest", "org.gnome.Shell",
                     "--object-path", path, "--method", method])

    @staticmethod
    def _payload(reply):
        """gdbus prints `('<json>',)`; this digs the JSON back out."""
        import json
        text = (reply or "").strip()
        if not text:
            return None
        if text.startswith("(") and text.endswith(",)"):
            text = text[1:-2].strip()
        if len(text) >= 2 and text[0] == text[-1] and text[0] in "'\"":
            text = text[1:-1]
        # gdbus escapes the quotes inside the string it prints.
        text = text.replace("\\\"", "\"").replace("\\'", "'")
        try:
            return json.loads(text)
        except ValueError:
            return None

    @classmethod
    def _focused(cls, data, is_list):
        """The focused window out of an extension's reply, as a dict."""
        if data is None:
            return None
        if is_list:
            if not isinstance(data, list):
                return None
            for window in data:
                if isinstance(window, dict) and window.get("focus"):
                    return window
            return None
        return data if isinstance(data, dict) else None

    def available(self):
        import platform_env
        if not self.bin or platform_env.desktop() != platform_env.GNOME:
            return False
        return self._pick() is not None

    def _pick(self):
        """Which extension interface answers, or None. Cached once it does."""
        if self._iface is not None:
            return self._iface
        for path, method, is_list in self.INTERFACES:
            if self._focused(self._payload(self._call(path, method)), is_list):
                self._iface = (path, method, is_list)
                return self._iface
        return None

    def poll_once(self):
        iface = self._pick()
        if not iface:
            return ("", "")
        path, method, is_list = iface
        window = self._focused(self._payload(self._call(path, method)), is_list)
        if not window:
            return ("", "")
        try:
            self.last_pid = int(window.get("pid") or 0)
        except (TypeError, ValueError):
            self.last_pid = 0
        return (str(window.get("wm_class") or window.get("class") or ""),
                str(window.get("title") or ""))

    _loop = KdotoolWatcher._loop
    start = KdotoolWatcher.start
    stop = KdotoolWatcher.stop


class MacWatcher(WindowWatcher):
    """macOS frontmost application, through AppleScript.

    Reports the **bundle identifier** as the class (`com.apple.Safari`), which
    is macOS's stable name for an application, and the window title where the
    app will admit to one. `wm_class` on Linux and `bundle_id` here are the
    same idea and the profile schema stores whichever the platform gives
    (PLAN 4.4).

    UNVERIFIED. Written from AppleScript's documented behaviour, not from a
    Mac; see docs/MACOS.md. Note that reading the frontmost app needs the same
    Accessibility permission as sending keystrokes does.
    """
    name = "osascript"

    FRONT_APP = (
        'tell application "System Events" to get bundle identifier of '
        'first application process whose frontmost is true')
    FRONT_TITLE = (
        'tell application "System Events" to tell (first application process '
        'whose frontmost is true) to get name of front window')

    def __init__(self, on_change=None, interval=0.4):
        self.bin = shutil.which("osascript")
        self.on_change = on_change
        self.interval = interval
        self._thread = None
        self._stop = threading.Event()
        self._last_class = None
        self.last_pid = 0

    def available(self):
        import platform_env
        return bool(self.bin) and platform_env.os_name() == platform_env.MACOS

    def poll_once(self):
        if not self.bin:
            return ("", "")
        bundle = _run([self.bin, "-e", self.FRONT_APP])
        if not bundle:
            return ("", "")
        # Plenty of apps have no window, or refuse to name it; the bundle id is
        # what dynamic mode matches on, so a missing title is not a failure.
        title = _run([self.bin, "-e", self.FRONT_TITLE]) or ""
        return (bundle, title)

    # The loop is identical to the kdotool one; sharing it keeps the two
    # watchers from drifting apart.
    _loop = KdotoolWatcher._loop
    start = KdotoolWatcher.start
    stop = KdotoolWatcher.stop


def get_watcher(on_change=None, interval=0.4):
    """Best available focus watcher for this session.

    KDE (kdotool), GNOME (via an extension), macOS (AppleScript) and X11
    (`_NET_ACTIVE_WINDOW`). Anything else falls back to a no-op watcher so
    dynamic mode degrades to "never switches" rather than failing.
    """
    # Availability, not desktop identity, decides: kdotool works wherever KWin
    # is running, which XDG_CURRENT_DESKTOP does not always admit to, and the
    # macOS watcher refuses to claim a Linux session. Compositor-native ones
    # come first; xprop sees only X11 clients, so it is the fallback rather
    # than the answer.
    for cls in (KdotoolWatcher, GnomeWatcher, MacWatcher, XpropWatcher):
        w = cls(on_change=on_change, interval=interval)
        if w.available():
            return w
    return WindowWatcher()
