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

import platform_env

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
    # The names X11 and Qt use for the bracket keys, which is what anyone
    # copying a shortcut out of an application's documentation will type.
    "bracketleft": 26, "bracketright": 27, "backtick": 41,
    # And the characters themselves, which is what anyone reading a shortcut
    # off the screen will type. "+" cannot be one: it separates a combo.
    "-": 12, "=": 13, ",": 51, ".": 52, "/": 53, ";": 39, "'": 40, "`": 41,
    "[": 26, "]": 27, "\\": 43,
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


# Scroll directions -> (dx, dy) unit vectors, in evdev's convention: REL_WHEEL
# positive is up, REL_HWHEEL positive is right. Magnitude is supplied per call
# rather than by repeating, which is why scroll is the natural place to prove an
# acceleration curve (see docs/PLAN.md 5.D.1).
SCROLL_DIRECTIONS = {
    "up": (0, 1), "down": (0, -1), "right": (1, 0), "left": (-1, 0),
}


def _parse_scroll(direction):
    """'up' -> (0, 1). Unknown directions scroll nothing rather than raising."""
    return SCROLL_DIRECTIONS.get(str(direction).strip().lower(), (0, 0))


class InputBackend:
    name = "none"

    def available(self):
        return False

    def health(self):
        """(ok, detail). `detail` explains the problem and, where there is one,
        the fix. Reported in the UI: a backend that cannot inject otherwise
        fails completely silently, with every action appearing to do nothing.
        """
        return False, "No input backend"

    def send_hotkey(self, combo, repeat=1):
        raise NotImplementedError

    def type_text(self, text):
        raise NotImplementedError

    def scroll(self, direction, amount=1):
        raise NotImplementedError


class NullBackend(InputBackend):
    """Used when no working backend exists; logs instead of crashing."""
    name = "null"

    def available(self):
        return True

    def health(self):
        return False, ("No usable input backend for this session. On Wayland "
                       "install ydotool; on X11 install xdotool.")

    def send_hotkey(self, combo, repeat=1):
        print("[input] no working backend; would send hotkey: %s (x%d)" % (combo, repeat))

    def scroll(self, direction, amount=1):
        print("[input] no working backend; would scroll %s x%d" % (direction, amount))

    def type_text(self, text):
        print("[input] no working backend; would type: %r" % text)


class YdotoolBackend(InputBackend):
    """Wayland/uinput backend. Requires the `ydotool` binary + a running
    `ydotoold` daemon."""
    name = "ydotool"

    # `ydotool key` sleeps its delay after *every* key event, not between them:
    # measured cost is 12.1 ms x N events, so a four-event combo (ctrl down, key
    # down, key up, ctrl up) spends ~48 ms in delays. That dominates per-action
    # latency and is the main cost when a rotary control fires once per detent.
    # 0 removes it: a combo drops from ~48.6 ms to ~0.6 ms.
    #
    # Raise this if an app starts missing a modifier that has not settled yet.
    # Measured clean at 0 on this machine (640 combos, paced and back-to-back,
    # native Wayland and XWayland, zero dropped modifiers), but that only covers
    # a Qt receiver; other toolkits have not been checked.
    key_delay_ms = 0

    # ...but a *repeat* needs a gap, or the receiver folds the presses into one.
    # Measured against KDE's volume handler: at 0 ms a repeat of 3 moved the
    # volume exactly 1 step on every trial; at 1 ms and above it moved 3 of 3 on
    # every trial. The threshold is under a millisecond, so this is margin for
    # slower handlers rather than a tuned value. It applies only when repeat > 1,
    # so a single keypress keeps the ~0.6 ms path.
    #
    # Note this is a *semantic* limit, not a delivery one: a Qt client counting
    # key events receives all N even at 0 ms (640-combo test). The volume
    # handler receives them too and chooses to collapse them.
    repeat_delay_ms = 3

    SOCKET_CANDIDATES = ("/run/user/%d/.ydotool_socket", "/tmp/.ydotool_socket",
                        "/run/.ydotool_socket")

    def __init__(self):
        self.bin = shutil.which("ydotool")
        self.env = dict(os.environ)
        self.last_error = ""
        # Help the client find the daemon socket if the user didn't export it.
        if "YDOTOOL_SOCKET" not in self.env:
            for cand in self._socket_candidates():
                if os.path.exists(cand):
                    self.env["YDOTOOL_SOCKET"] = cand
                    break

    def _socket_candidates(self):
        return [c % os.getuid() if "%d" in c else c
                for c in self.SOCKET_CANDIDATES]

    def available(self):
        return bool(self.bin)

    def health(self):
        if not self.bin:
            return False, "ydotool is not installed"
        socket = self.env.get("YDOTOOL_SOCKET")
        if not socket or not os.path.exists(socket):
            return False, ("ydotoold is not running, or its socket is not "
                           "readable by you. Looked in: %s"
                           % ", ".join(self._socket_candidates()))
        if self.last_error:
            # The daemon can be running yet refuse the connection, e.g. when
            # the socket belongs to another user.
            return False, "ydotool failed: %s" % self.last_error
        return True, "ydotool via %s" % socket

    def _run(self, args):
        """Run ydotool, remembering a failure so health() can report it.

        Without this a dead daemon is invisible: the action layer catches the
        exception and logs it to a terminal nobody is looking at.
        """
        try:
            subprocess.run([self.bin] + args, env=self.env, check=True,
                           capture_output=True)
            self.last_error = ""
        except subprocess.CalledProcessError as e:
            detail = (e.stderr or b"").decode(errors="replace").strip()
            self.last_error = detail.splitlines()[-1] if detail else "exit %d" % e.returncode
            raise
        except OSError as e:
            self.last_error = str(e)
            raise

    def send_hotkey(self, combo, repeat=1):
        """Send `combo`, repeating the non-modifier key `repeat` times.

        The modifiers are pressed once and held across the whole run rather than
        re-pressed per step: one invocation cannot be interleaved with another
        control's events, and it is what the encoder Fast presets emit. Measured
        1:1 in delivery against separate invocations up to depth 10, so the
        batched form loses nothing (docs/PLAN.md 5.D.1). repeat=1 produces the
        exact byte sequence this method sent before the argument existed.
        """
        codes = _parse_combo(combo)
        if not codes:
            return
        n = max(1, int(repeat))
        mods, key = codes[:-1], codes[-1]
        args = ["%d:1" % c for c in mods]
        for _ in range(n):
            args += ["%d:1" % key, "%d:0" % key]
        args += ["%d:0" % c for c in reversed(mods)]
        delay = self.key_delay_ms if n == 1 else self.repeat_delay_ms
        self._run(["key", "-d", str(delay), *args])

    def type_text(self, text):
        self._run(["type", "--", text])

    def scroll(self, direction, amount=1):
        """One invocation carrying the whole magnitude, not `amount` clicks."""
        dx, dy = _parse_scroll(direction)
        n = max(1, int(amount))
        if not (dx or dy):
            return
        self._run(["mousemove", "-w", "-x", str(dx * n), "-y", str(dy * n)])


class XdotoolBackend(InputBackend):
    """X11 backend."""
    name = "xdotool"

    def __init__(self):
        self.bin = shutil.which("xdotool")

    def available(self):
        return bool(self.bin) and platform_env.session_type() == platform_env.X11

    def health(self):
        if not self.bin:
            return False, "xdotool is not installed"
        return True, "xdotool"

    def send_hotkey(self, combo, repeat=1):
        # xdotool uses '+' combos with names like ctrl/shift/super/Return.
        n = max(1, int(repeat))
        cmd = [self.bin, "key"]
        if n > 1:
            cmd += ["--repeat", str(n)]
        subprocess.run(cmd + [combo.replace(" ", "")], check=True)

    def type_text(self, text):
        subprocess.run([self.bin, "type", "--", text], check=True)

    def scroll(self, direction, amount=1):
        # X11 has no magnitude: wheel is buttons 4/5 (up/down), 6/7 (left/right).
        button = {"up": "4", "down": "5", "left": "6", "right": "7"}.get(
            str(direction).strip().lower())
        if not button:
            return
        subprocess.run([self.bin, "click", "--repeat", str(max(1, int(amount))),
                        button], check=True)


class PyAutoGuiBackend(InputBackend):
    """X11 fallback via pyautogui (python-xlib)."""
    name = "pyautogui"

    def available(self):
        if platform_env.session_type() != platform_env.X11:
            return False
        try:
            import pyautogui  # noqa: F401
            return True
        except Exception:
            return False

    def health(self):
        return True, "pyautogui (X11)"

    def send_hotkey(self, combo, repeat=1):
        import pyautogui
        keys = [k.strip().lower() for k in combo.split("+") if k.strip()]
        for _ in range(max(1, int(repeat))):
            pyautogui.hotkey(*keys)  # NOTE: *keys, not a list (the old code passed a list -> bug)

    def type_text(self, text):
        import pyautogui
        pyautogui.typewrite(text)

    def scroll(self, direction, amount=1):
        import pyautogui
        dx, dy = _parse_scroll(direction)
        n = max(1, int(amount))
        if dy:
            pyautogui.scroll(dy * n)
        elif dx:
            pyautogui.hscroll(dx * n)


_backend = None


# Preference order per session, most-appropriate first. ydotool leads on
# Wayland because it is the only one that can inject into native Wayland
# clients; on X11 the X-native tools are preferred but ydotool still works, so
# it stays as a last resort rather than being excluded.
class MacBackend(InputBackend):
    """macOS, through AppleScript.

    `osascript` is on every Mac, so there is nothing to install. What there is,
    is a permission: synthesising input requires the app (or the terminal that
    launched it) to be granted Accessibility rights in System Settings, and
    until it is, every keystroke silently does nothing. health() says so.

    UNVERIFIED. This is written from AppleScript's documented behaviour, not
    from a Mac. Corrections welcome; see docs/MACOS.md.
    """
    name = "osascript"

    # AppleScript spells the modifiers out and takes the rest as a keystroke.
    MODIFIERS = {
        "ctrl": "control down", "control": "control down",
        "alt": "option down", "option": "option down",
        "shift": "shift down",
        "cmd": "command down", "command": "command down",
        "super": "command down", "meta": "command down",
    }

    # Keys with no character to type: AppleScript addresses these by code.
    KEY_CODES = {
        "return": 36, "enter": 36, "tab": 48, "space": 49, "delete": 51,
        "backspace": 51, "escape": 53, "esc": 53, "left": 123, "right": 124,
        "down": 125, "up": 126, "home": 115, "end": 119,
        "pageup": 116, "pagedown": 121,
        "f1": 122, "f2": 120, "f3": 99, "f4": 118, "f5": 96, "f6": 97,
        "f7": 98, "f8": 100, "f9": 101, "f10": 109, "f11": 103, "f12": 111,
    }

    def __init__(self):
        self.bin = shutil.which("osascript")
        self.last_error = ""

    def available(self):
        return bool(self.bin) and platform_env.os_name() == platform_env.MACOS

    def health(self):
        if not self.bin:
            return False, "osascript not found (is this macOS?)"
        if self.last_error:
            # The permission failure is the one worth naming: it looks exactly
            # like nothing happening.
            if "1002" in self.last_error or "not allowed" in self.last_error.lower():
                return False, ("macOS is refusing to let this app send "
                               "keystrokes. Grant it Accessibility rights in "
                               "System Settings > Privacy & Security > "
                               "Accessibility, then check again.")
            return False, "osascript failed: %s" % self.last_error
        return True, "osascript (AppleScript)"

    def _run(self, script):
        try:
            subprocess.run([self.bin, "-e", script], check=True,
                           capture_output=True)
            self.last_error = ""
        except subprocess.CalledProcessError as e:
            detail = (e.stderr or b"").decode(errors="replace").strip()
            self.last_error = detail.splitlines()[-1] if detail else (
                "exit %d" % e.returncode)
            raise
        except OSError as e:
            self.last_error = str(e)
            raise

    def _keystroke_script(self, combo):
        """One combo -> the AppleScript that sends it, or None if unmappable."""
        parts = [p.strip().lower() for p in str(combo).split("+") if p.strip()]
        if not parts:
            return None
        mods, key = [], None
        for part in parts:
            if part in self.MODIFIERS:
                mod = self.MODIFIERS[part]
                if mod not in mods:
                    mods.append(mod)
            else:
                key = part
        if key is None:
            return None
        using = (" using {%s}" % ", ".join(mods)) if mods else ""
        if key in self.KEY_CODES:
            action = "key code %d" % self.KEY_CODES[key]
        elif len(key) == 1:
            action = 'keystroke "%s"' % key.replace("\\", "\\\\").replace('"', '\\"')
        else:
            return None
        return 'tell application "System Events" to %s%s' % (action, using)

    def send_hotkey(self, combo, repeat=1):
        script = self._keystroke_script(combo)
        if script is None:
            print("[input] osascript: cannot map combo %r" % combo)
            return
        for _ in range(max(1, int(repeat))):
            self._run(script)

    def type_text(self, text):
        escaped = str(text).replace("\\", "\\\\").replace('"', '\\"')
        self._run('tell application "System Events" to keystroke "%s"' % escaped)

    def scroll(self, direction, amount=1):
        # System Events has no scroll verb; arrow keys are the closest thing
        # AppleScript alone can do. A pyobjc CGEvent scroll would be better and
        # is the obvious next step for anyone with a Mac to test it on.
        key = {"up": "up", "down": "down", "left": "left", "right": "right"}.get(
            str(direction).strip().lower())
        if not key:
            return
        script = self._keystroke_script(key)
        if script is None:
            return
        for _ in range(max(1, int(amount))):
            self._run(script)


_ORDER = {
    platform_env.WAYLAND: [YdotoolBackend, XdotoolBackend, PyAutoGuiBackend],
    platform_env.X11: [XdotoolBackend, PyAutoGuiBackend, YdotoolBackend],
    # macOS reports no X11/Wayland session, which is also what a headless Linux
    # box looks like, so the platform decides rather than the session.
    platform_env.NO_SESSION: [MacBackend, YdotoolBackend],
}


def detect_backend():
    """Pick the best backend that is actually usable on this session.

    Order comes from the session type; availability decides. A backend that
    suits the platform but is not installed loses to one that is.
    """
    for cls in _ORDER.get(platform_env.session_type(), [YdotoolBackend]):
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

def send_hotkey(combo, repeat=1):
    get_backend().send_hotkey(combo, repeat=repeat)


def type_text(text):
    get_backend().type_text(text)


def health():
    """(ok, name, detail) for the active backend."""
    b = get_backend()
    ok, detail = b.health()
    return ok, b.name, detail


def scroll(direction, amount=1):
    """Scroll `direction` ('up'/'down'/'left'/'right') by `amount` notches."""
    get_backend().scroll(direction, amount=amount)


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
