"""Toggle the desktop's on-screen keyboard.

The CT has a dedicated keyboard button, and every desktop already ships a
virtual keyboard, so this drives the system one rather than drawing our own.

KDE Plasma exposes it on DBus (`org.kde.kwin.VirtualKeyboard`), which is the
only interface here that reports state as well as changing it. Elsewhere we
fall back to launching a known keyboard binary, where "toggle" means start it
or kill it, because those have no shared control interface.

Note KDE's `active` means *enabled*, not *on screen*: the panel appears when a
text field takes focus. That is the same behaviour as the physical button.

Qt-free, like the other platform adapters.
"""

import shutil
import subprocess

import platform_env

# KDE's DBus address for the compositor-owned keyboard.
_KDE_SERVICE = "org.kde.keyboard"
_KDE_PATH = "/VirtualKeyboard"
_KDE_IFACE = "org.kde.kwin.VirtualKeyboard"

# Keyboards that are just a process: running means shown.
_PROCESS_KEYBOARDS = ("squeekboard", "wvkbd-mobintl", "onboard", "florence")


class VirtualKeyboard:
    name = "none"

    def available(self):
        return False

    def is_active(self):
        return False

    def set_active(self, on):
        return False

    def toggle(self):
        return self.set_active(not self.is_active())


class NullKeyboard(VirtualKeyboard):
    name = "null"

    def toggle(self):
        print("[keyboard] no virtual keyboard available on this desktop")
        return False


class KdeKeyboard(VirtualKeyboard):
    """KWin's keyboard, over DBus. `busctl` ships with systemd, so this needs
    no Python DBus binding."""
    name = "kde"

    def __init__(self):
        self.bin = shutil.which("busctl")

    def _prop(self, verb, *extra):
        return subprocess.run(
            [self.bin, "--user", verb, _KDE_SERVICE, _KDE_PATH, _KDE_IFACE,
             *extra],
            capture_output=True, text=True, timeout=5)

    def available(self):
        if not self.bin:
            return False
        try:
            r = self._prop("get-property", "available")
        except (OSError, subprocess.SubprocessError):
            return False
        return r.returncode == 0 and "true" in r.stdout

    def is_active(self):
        try:
            r = self._prop("get-property", "active")
        except (OSError, subprocess.SubprocessError):
            return False
        return r.returncode == 0 and "true" in r.stdout

    def set_active(self, on):
        try:
            r = self._prop("set-property", "active", "b",
                           "true" if on else "false")
        except (OSError, subprocess.SubprocessError) as e:
            print("[keyboard] %s" % e)
            return False
        if r.returncode != 0:
            print("[keyboard] %s" % (r.stderr or "").strip())
            return False
        return True


class ProcessKeyboard(VirtualKeyboard):
    """A keyboard that is simply a program: running means on screen."""
    name = "process"

    def __init__(self):
        self.bin = None
        for candidate in _PROCESS_KEYBOARDS:
            path = shutil.which(candidate)
            if path:
                self.bin = path
                self.command = candidate
                break
        self._proc = None

    def available(self):
        return bool(self.bin)

    def is_active(self):
        return self._proc is not None and self._proc.poll() is None

    def set_active(self, on):
        if on:
            if self.is_active():
                return True
            self._proc = subprocess.Popen(
                [self.bin], start_new_session=True,
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL)
            return True
        if self.is_active():
            self._proc.terminate()
            self._proc = None
        return True


_keyboard = None


def detect():
    """KDE's interface first where it is present, then any keyboard binary."""
    if platform_env.desktop() == platform_env.KDE:
        k = KdeKeyboard()
        if k.available():
            return k
    k = ProcessKeyboard()
    if k.available():
        return k
    # KDE's interface works even when XDG_CURRENT_DESKTOP says otherwise.
    k = KdeKeyboard()
    if k.available():
        return k
    return NullKeyboard()


def get_keyboard():
    global _keyboard
    if _keyboard is None:
        _keyboard = detect()
    return _keyboard


def reset():
    global _keyboard
    _keyboard = None


def toggle():
    return get_keyboard().toggle()


def set_active(on):
    return get_keyboard().set_active(on)


def is_active():
    return get_keyboard().is_active()
