"""Platform input backends: send hotkeys / text / media to the OS.

Qt-agnostic on purpose (see docs/PLAN.md 4.2 - platform adapter layer, no Qt
imports below the UI layer). The action engine calls into ``get_backend()``.

Wayland-first
-------------
This machine is KDE Plasma on Wayland. Two consequences drive the design:

* ``pyautogui`` / ``xdotool`` are X11-only and cannot inject input into native
  Wayland clients.
* ``wtype`` uses the ``virtual-keyboard`` Wayland protocol, which **KWin does
  not implement** - so it silently does nothing on KDE.

That leaves **ydotool**, which synthesizes input at the kernel level via
``/dev/uinput`` and therefore works regardless of compositor. It needs the
``ydotoold`` daemon running with uinput access (see docs / M2 setup). On X11 we
fall back to ``xdotool`` then ``pyautogui``.
"""

import os
import shutil
import subprocess

# evdev key codes (from linux/input-event-codes.h). ydotool's `key` verb takes
# CODE:STATE pairs (1=down, 0=up); it does not accept key *names*, so we map
# here. Names are lowercased and stripped before lookup.
KEY = {
    # modifiers
    "ctrl": 29, "control": 29, "leftctrl": 29, "rightctrl": 97,
    "shift": 42, "leftshift": 42, "rightshift": 54,
    "alt": 56, "leftalt": 56, "rightalt": 100, "altgr": 100,
    "super": 125, "meta": 125, "win": 125, "cmd": 125, "command": 125,
    # editing / navigation
    "enter": 28, "return": 28, "esc": 1, "escape": 1, "tab": 15, "space": 57,
    "backspace": 14, "delete": 111, "del": 111, "insert": 110,
    "up": 103, "down": 108, "left": 105, "right": 106,
    "home": 102, "end": 107, "pageup": 104, "pagedown": 109,
    "capslock": 58, "printscreen": 99, "menu": 127,
    # letters
    "a": 30, "b": 48, "c": 46, "d": 32, "e": 18, "f": 33, "g": 34, "h": 35,
    "i": 23, "j": 36, "k": 37, "l": 38, "m": 50, "n": 49, "o": 24, "p": 25,
    "q": 16, "r": 19, "s": 31, "t": 20, "u": 22, "v": 47, "w": 17, "x": 45,
    "y": 21, "z": 44,
    # digits
    "0": 11, "1": 2, "2": 3, "3": 4, "4": 5, "5": 6, "6": 7, "7": 8, "8": 9, "9": 10,
    # function keys
    "f1": 59, "f2": 60, "f3": 61, "f4": 62, "f5": 63, "f6": 64,
    "f7": 65, "f8": 66, "f9": 67, "f10": 68, "f11": 87, "f12": 88,
    # punctuation
    "minus": 12, "equal": 13, "comma": 51, "dot": 52, "period": 52,
    "slash": 53, "semicolon": 39, "apostrophe": 40, "grave": 41,
    "leftbrace": 26, "rightbrace": 27, "backslash": 43,
    # media / volume
    "playpause": 164, "play": 164, "pause": 164, "stop": 166,
    "next": 163, "nextsong": 163, "prev": 165, "previous": 165, "previoussong": 165,
    "volumeup": 115, "volup": 115, "volumedown": 114, "voldown": 114, "mute": 113,
    "brightnessup": 225, "brightnessdown": 224,
}


def _parse_combo(combo):
    """'ctrl+shift+c' -> [29, 42, 46]. Raises KeyError on unknown key names."""
    names = [k.strip().lower() for k in str(combo).replace(" ", "").split("+") if k.strip()]
    return [KEY[n] for n in names]


class InputBackend:
    name = "none"

    def available(self):
        return False

    def send_hotkey(self, combo):
        raise NotImplementedError

    def type_text(self, text):
        raise NotImplementedError


class NullBackend(InputBackend):
    """Used when no working backend exists; logs instead of crashing."""
    name = "null"

    def available(self):
        return True

    def send_hotkey(self, combo):
        print("[input] no working backend; would send hotkey: %s" % combo)

    def type_text(self, text):
        print("[input] no working backend; would type: %r" % text)


class YdotoolBackend(InputBackend):
    """Wayland/uinput backend. Requires the `ydotool` binary + a running
    `ydotoold` daemon."""
    name = "ydotool"

    def __init__(self):
        self.bin = shutil.which("ydotool")
        self.env = dict(os.environ)
        # Help the client find the daemon socket if the user didn't export it.
        if "YDOTOOL_SOCKET" not in self.env:
            for cand in ("/run/user/%d/.ydotool_socket" % os.getuid(),
                         "/tmp/.ydotool_socket", "/run/.ydotool_socket"):
                if os.path.exists(cand):
                    self.env["YDOTOOL_SOCKET"] = cand
                    break

    def available(self):
        return bool(self.bin)

    def send_hotkey(self, combo):
        codes = _parse_combo(combo)
        if not codes:
            return
        down = ["%d:1" % c for c in codes]
        up = ["%d:0" % c for c in reversed(codes)]
        subprocess.run([self.bin, "key", *down, *up], env=self.env, check=True)

    def type_text(self, text):
        subprocess.run([self.bin, "type", "--", text], env=self.env, check=True)


class XdotoolBackend(InputBackend):
    """X11 backend."""
    name = "xdotool"

    def __init__(self):
        self.bin = shutil.which("xdotool")

    def available(self):
        return bool(self.bin) and os.environ.get("DISPLAY")

    def send_hotkey(self, combo):
        # xdotool uses '+' combos with names like ctrl/shift/super/Return.
        subprocess.run([self.bin, "key", combo.replace(" ", "")], check=True)

    def type_text(self, text):
        subprocess.run([self.bin, "type", "--", text], check=True)


class PyAutoGuiBackend(InputBackend):
    """X11 fallback via pyautogui (python-xlib)."""
    name = "pyautogui"

    def available(self):
        if not os.environ.get("DISPLAY"):
            return False
        try:
            import pyautogui  # noqa: F401
            return True
        except Exception:
            return False

    def send_hotkey(self, combo):
        import pyautogui
        keys = [k.strip().lower() for k in combo.split("+") if k.strip()]
        pyautogui.hotkey(*keys)  # NOTE: *keys, not a list (the old code passed a list -> bug)

    def type_text(self, text):
        import pyautogui
        pyautogui.typewrite(text)


_backend = None


def detect_backend():
    """Pick the best backend for this session, preferring Wayland-capable ones."""
    session = os.environ.get("XDG_SESSION_TYPE", "").lower()
    if session == "wayland":
        order = [YdotoolBackend, XdotoolBackend, PyAutoGuiBackend]
    else:
        order = [XdotoolBackend, PyAutoGuiBackend, YdotoolBackend]
    for cls in order:
        b = cls()
        if b.available():
            return b
    return NullBackend()


def get_backend():
    """Cached backend selection."""
    global _backend
    if _backend is None:
        _backend = detect_backend()
    return _backend


def reset_backend():
    """Force re-detection (e.g. after installing ydotool)."""
    global _backend
    _backend = None


# -- convenience action helpers ------------------------------------------------

def send_hotkey(combo):
    get_backend().send_hotkey(combo)


def type_text(text):
    get_backend().type_text(text)


def launch_app(command):
    """Launch a desktop app / run a command, fully detached from this process."""
    subprocess.Popen(command, shell=True, start_new_session=True,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL)


def media(action):
    """Media transport control. Prefers MPRIS (playerctl); falls back to a
    synthetic media key via the active input backend.

    action: play-pause | play | pause | next | previous | stop
    """
    pctl = shutil.which("playerctl")
    if pctl:
        mapping = {"play-pause": "play-pause", "playpause": "play-pause",
                   "play": "play", "pause": "pause", "next": "next",
                   "previous": "previous", "prev": "previous", "stop": "stop"}
        subprocess.run([pctl, mapping.get(action, action)], check=False)
        return
    keyname = {"play-pause": "playpause", "playpause": "playpause", "play": "play",
               "pause": "pause", "next": "next", "previous": "previous",
               "prev": "previous", "stop": "stop"}.get(action, action)
    get_backend().send_hotkey(keyname)
