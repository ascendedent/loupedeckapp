"""Platform detection and the factories that depend on it."""
import os
import sys

from _harness import Checks

import platform_env

c = Checks()

SAVED = {k: os.environ.get(k) for k in
         ("XDG_SESSION_TYPE", "XDG_CURRENT_DESKTOP", "KDE_FULL_SESSION",
          "WAYLAND_DISPLAY", "DISPLAY")}


def env(**kw):
    """Set exactly the given vars, clearing the rest of the session ones."""
    for k in SAVED:
        os.environ.pop(k, None)
    for k, v in kw.items():
        if v is not None:
            os.environ[k] = v


def restore():
    for k, v in SAVED.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


real_platform = sys.platform


class FakePlatform:
    """sys.platform is read at call time, so it can be swapped per case.

    Restores whatever was there on entry rather than the host value, so these
    nest: the file fakes Linux for its length and fakes another platform inside
    that for the cases that need one.
    """

    def __init__(self, value):
        self.value = value

    def __enter__(self):
        self.prev = sys.platform
        sys.platform = self.value

    def __exit__(self, *a):
        sys.platform = self.prev


try:
    # These checks describe what the app does on Linux, not what it does on the
    # machine running them, and the two stopped being the same once there was a
    # Mac to run them on. Faking the host keeps the answers identical wherever
    # the suite runs; the cases that are about another platform fake their own.
    sys.platform = "linux"
    # -- session detection -----------------------------------------------------
    env(XDG_SESSION_TYPE="wayland")
    c.eq("XDG_SESSION_TYPE=wayland", platform_env.session_type(), "wayland")
    env(XDG_SESSION_TYPE="x11")
    c.eq("XDG_SESSION_TYPE=x11", platform_env.session_type(), "x11")

    # Falling back to the sockets matters: XDG_SESSION_TYPE is not always set,
    # and what decides connectivity is whether a display is actually reachable.
    env(WAYLAND_DISPLAY="wayland-0")
    c.eq("no XDG var, WAYLAND_DISPLAY set", platform_env.session_type(), "wayland")
    env(DISPLAY=":0")
    c.eq("no XDG var, DISPLAY set", platform_env.session_type(), "x11")
    env(XDG_SESSION_TYPE="tty")
    c.eq("a headless session reports none", platform_env.session_type(), "none")
    env()
    c.eq("nothing set at all reports none", platform_env.session_type(), "none")

    with FakePlatform("darwin"):
        env(DISPLAY=":0")     # an X server on a Mac must not fool it
        c.eq("macOS has no X11/Wayland session", platform_env.session_type(), "none")
        c.eq("macOS is detected", platform_env.os_name(), "macos")
    with FakePlatform("win32"):
        c.eq("an unknown platform is 'other'", platform_env.os_name(), "other")
    c.eq("linux is detected", platform_env.os_name(), "linux")

    # -- desktop detection -----------------------------------------------------
    env(XDG_CURRENT_DESKTOP="KDE")
    c.eq("XDG_CURRENT_DESKTOP=KDE", platform_env.desktop(), "kde")
    env(XDG_CURRENT_DESKTOP="ubuntu:GNOME")
    c.eq("a compound GNOME value still matches", platform_env.desktop(), "gnome")
    env(KDE_FULL_SESSION="true")
    c.eq("KDE_FULL_SESSION alone is enough", platform_env.desktop(), "kde")
    env(XDG_CURRENT_DESKTOP="XFCE")
    c.eq("anything else is 'other'", platform_env.desktop(), "other")

    # -- input backend selection ----------------------------------------------
    import input_backend

    names = lambda order: [cls().name for cls in order]
    c.eq("Wayland prefers ydotool",
         names(input_backend._ORDER[platform_env.WAYLAND])[0], "ydotool")
    c.eq("X11 prefers xdotool",
         names(input_backend._ORDER[platform_env.X11])[0], "xdotool")
    c.eq("ydotool is still reachable on X11",
         "ydotool" in names(input_backend._ORDER[platform_env.X11]), True)

    # Availability beats preference: a backend that suits the session but is not
    # installed must lose to one that is.
    real_which = input_backend.shutil.which
    input_backend.shutil.which = lambda name: None      # nothing installed
    try:
        env(XDG_SESSION_TYPE="wayland")
        input_backend.reset_backend()
        c.eq("with no tools installed, the null backend is used",
             input_backend.get_backend().name, "null")
    finally:
        input_backend.shutil.which = real_which
        input_backend.reset_backend()

    input_backend.shutil.which = lambda name: "/usr/bin/" + name
    try:
        env(XDG_SESSION_TYPE="x11", DISPLAY=":0")
        input_backend.reset_backend()
        c.eq("on X11 with everything installed, xdotool wins",
             input_backend.get_backend().name, "xdotool")
        env(XDG_SESSION_TYPE="wayland")
        input_backend.reset_backend()
        c.eq("on Wayland with everything installed, ydotool wins",
             input_backend.get_backend().name, "ydotool")
    finally:
        input_backend.shutil.which = real_which
        input_backend.reset_backend()

    # -- action library --------------------------------------------------------
    import action_library

    env(XDG_CURRENT_DESKTOP="KDE")
    kde = {e[1]: e[3] for e in action_library.default_library()}
    c.eq("KDE gets konsole", kde["Terminal"], "konsole")
    c.eq("KDE gets dolphin", kde["Files"], "dolphin")
    c.eq("KDE gets spectacle", kde["Screenshot"], "spectacle")
    c.eq("editing shortcuts use ctrl on Linux", kde["Copy"], "ctrl+c")

    env(XDG_CURRENT_DESKTOP="GNOME")
    gnome = {e[1]: e[3] for e in action_library.default_library()}
    c.eq("GNOME gets its own terminal", gnome["Terminal"], "gnome-terminal")
    c.eq("GNOME gets nautilus", gnome["Files"], "nautilus")

    env(XDG_CURRENT_DESKTOP="XFCE")
    other = {e[1]: e[3] for e in action_library.default_library()}
    c.eq("an unknown desktop falls back to generic commands",
         other["Terminal"], "x-terminal-emulator")

    with FakePlatform("darwin"):
        env()
        mac = {e[1]: e[3] for e in action_library.default_library()}
        c.eq("macOS uses the command key for editing", mac["Copy"], "super+c")
        c.eq("macOS opens Terminal.app", mac["Terminal"], "open -a Terminal")
        c.eq("macOS browser uses open", mac["Browser"], "open https://")

    env(XDG_CURRENT_DESKTOP="KDE")
    lib = action_library.default_library()
    c.eq("every entry has all four fields", all(len(e) == 4 for e in lib), True)
    c.eq("every category is a known one",
         sorted({e[0] for e in lib}) == sorted(set(action_library.CATEGORIES)
                                               & {e[0] for e in lib}), True)
    cats = [e[0] for e in lib]
    order = {name: i for i, name in enumerate(action_library.CATEGORIES)}
    c.eq("entries are grouped by category",
         cats == sorted(cats, key=lambda x: order[x]), True)
finally:
    sys.platform = real_platform
    restore()
    import input_backend as _ib
    _ib.reset_backend()

sys.exit(c.done())
