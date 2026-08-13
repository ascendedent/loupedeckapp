"""What kind of machine and session are we on?

Every `sys.platform`, `XDG_*` and `DISPLAY` test in the app funnels through
here, so adding a platform means editing one file rather than hunting for
scattered environment checks. Nothing here imports Qt or touches the device.

The values are read on each call rather than cached: a long-lived process can
outlive a session change, and these are cheap.
"""

import os
import shutil
import sys

LINUX, MACOS, OTHER = "linux", "macos", "other"
WAYLAND, X11, NO_SESSION = "wayland", "x11", "none"
KDE, GNOME, OTHER_DE = "kde", "gnome", "other"


def os_name():
    if sys.platform.startswith("linux"):
        return LINUX
    if sys.platform == "darwin":
        return MACOS
    return OTHER


def session_type():
    """wayland / x11 / none. Trusts XDG_SESSION_TYPE, then falls back to the
    presence of WAYLAND_DISPLAY or DISPLAY, which is what actually decides
    whether a client can connect."""
    if os_name() == MACOS:
        return NO_SESSION            # Quartz, no X11/Wayland notion
    declared = os.environ.get("XDG_SESSION_TYPE", "").strip().lower()
    if declared in (WAYLAND, X11):
        return declared
    if os.environ.get("WAYLAND_DISPLAY"):
        return WAYLAND
    if os.environ.get("DISPLAY"):
        return X11
    return NO_SESSION


def desktop():
    """kde / gnome / other, from XDG_CURRENT_DESKTOP."""
    current = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
    if "kde" in current or os.environ.get("KDE_FULL_SESSION"):
        return KDE
    if "gnome" in current:
        return GNOME
    return OTHER_DE


def has_tool(name):
    """Is an external helper on PATH? Factories use this to prefer a backend
    that can actually run over one that merely suits the platform."""
    return bool(shutil.which(name))


def describe():
    return "%s / %s / %s" % (os_name(), session_type(), desktop())
