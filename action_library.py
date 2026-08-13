"""Ready-to-use actions for the left-panel library, per platform.

The portable entries (clipboard, scroll, volume, media, navigation) are the same
everywhere; only the *applications* differ, because "Terminal" means a different
binary on KDE, GNOME and macOS. Keeping them in one table with a per-platform
tail means adding a desktop is a few lines here rather than a fork of the UI.

Entries are `(category, label, action_type, value)`. A blank value marks a
template the user fills in from the inspector.

Qt-free: the UI reads this, nothing here reads the UI.
"""

import platform_env

CATEGORIES = ["General", "Adjustments", "Navigation", "Media", "System",
              "Applications"]

# Everything that does not depend on which desktop is installed.
PORTABLE = [
    ("General", "Type text…", "text", ""),
    ("General", "Run command…", "command", ""),

    ("Adjustments", "Scroll up", "scroll", "up"),
    ("Adjustments", "Scroll down", "scroll", "down"),
    ("Adjustments", "Scroll left", "scroll", "left"),
    ("Adjustments", "Scroll right", "scroll", "right"),
    # Volume is a hotkey rather than a media action: playerctl drives the media
    # player, while these are the system-wide multimedia keys, which is what
    # people mean by "bind volume to a knob".
    ("Adjustments", "Volume up", "hotkey", "volumeup"),
    ("Adjustments", "Volume down", "hotkey", "volumedown"),
    ("Adjustments", "Mute", "hotkey", "mute"),

    ("Media", "Play / Pause", "media", "play-pause"),
    ("Media", "Next track", "media", "next"),
    ("Media", "Previous track", "media", "previous"),
    ("Media", "Stop", "media", "stop"),

    ("Navigation", "Submenu", "submenu", "submenu"),
    ("Navigation", "Back", "back", ""),
]

# Editing shortcuts. The modifier differs on macOS, so the table is generated
# rather than written twice and left to drift.
_EDIT = [("Copy", "c"), ("Paste", "v"), ("Cut", "x"), ("Undo", "z"),
         ("Select all", "a"), ("Save", "s")]


def _editing(mod):
    out = [("System", label, "hotkey", "%s+%s" % (mod, key))
           for label, key in _EDIT]
    # Redo is the one that is not simply mod+letter on every platform.
    out.append(("System", "Redo", "hotkey", "%s+shift+z" % mod))
    return out


_APPS = {
    platform_env.KDE: [
        ("System", "Screenshot", "command", "spectacle"),
        ("Applications", "Terminal", "command", "konsole"),
        ("Applications", "Files", "command", "dolphin"),
    ],
    platform_env.GNOME: [
        ("System", "Screenshot", "command", "gnome-screenshot"),
        ("Applications", "Terminal", "command", "gnome-terminal"),
        ("Applications", "Files", "command", "nautilus"),
    ],
    platform_env.OTHER_DE: [
        ("Applications", "Terminal", "command", "x-terminal-emulator"),
        ("Applications", "Files", "command", "xdg-open ."),
    ],
}

_MAC_APPS = [
    ("System", "Screenshot", "hotkey", "super+shift+4"),
    ("Applications", "Terminal", "command", "open -a Terminal"),
    ("Applications", "Files", "command", "open ."),
]


def default_library():
    """The action library for this machine."""
    if platform_env.os_name() == platform_env.MACOS:
        # macOS uses Command where Linux uses Ctrl; input_backend maps "cmd"
        # and "super" to the same key, so "super" is spelled here for both.
        entries = list(PORTABLE) + _editing("super") + list(_MAC_APPS)
        browser = ("Applications", "Browser", "command", "open https://")
    else:
        entries = list(PORTABLE) + _editing("ctrl")
        entries += _APPS.get(platform_env.desktop(), _APPS[platform_env.OTHER_DE])
        browser = ("Applications", "Browser", "command", "xdg-open https://")
    entries.append(browser)
    # Stable order for the UI: by category as listed, then as written.
    order = {name: i for i, name in enumerate(CATEGORIES)}
    return sorted(entries, key=lambda e: order.get(e[0], len(order)))
