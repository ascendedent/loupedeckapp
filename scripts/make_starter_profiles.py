"""Generate the profile a fresh install opens with.

Written as a script rather than by hand because a profile is 50 controls of
JSON, and one that has been hand-edited is a profile nobody dares regenerate.
Run it after changing what the starter should contain:

    .venv/bin/python scripts/make_starter_profiles.py

It writes Profiles/Starter.json in the repo, which ships with the app. Nothing
here touches the user's own profiles.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from DeviceProfile import WS_KEYS                                 # noqa: E402
from LdConfiguration import LdConfiguration, LdAction             # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(REPO, "Profiles", "Starter.json")

# Editing shortcuts are spelled with ctrl. macOS wants command, and the app
# maps "super" to it, but a shipped file has to pick one; a mac user changes
# the modifier in the inspector. See docs/MACOS.md.
MOD = "ctrl"

# Key colours by role, so a workspace reads as a group at a glance rather than
# as twelve identical black squares.
BLUE, GREEN, AMBER, GREY = "#1e3a8a", "#14532d", "#78350f", "#27272a"


def key(ws, name, a_type, value, label, color=GREY):
    ws.actions[name] = LdAction(action_type=a_type, action=value)
    ws.labels[name] = {"text": label, "pos": "bottom", "mode": "bar"}
    ws.bg_colors[name] = color


def rotate(ws, control, left, right, press=None):
    """Bind a knob: (type, value) for each direction, and optionally a press."""
    ws.actions[control + "-l"] = LdAction(action_type=left[0], action=left[1])
    ws.actions[control + "-r"] = LdAction(action_type=right[0], action=right[1])
    if press:
        ws.actions[control] = LdAction(action_type=press[0], action=press[1])


def scroll_knob(ws, *controls):
    """Scrolling, on every knob named.

    Two of them, on purpose. A CT and a Live have knobs down both sides and
    scroll belongs under the off hand; a Live S has neither of those and only
    two knobs in total, both on the right. Binding both means the profile has
    a working scroll wheel whichever device opens it.
    """
    for control in controls:
        rotate(ws, control, ("scroll", "up"), ("scroll", "down"))


def led(ws, button, color):
    ws.led_colors[button] = color


def build():
    cfg = LdConfiguration(profile="Starter")
    media, editing, browser = (cfg.workspaces[0], cfg.workspaces[1],
                               cfg.workspaces[2])

    # -- 1: Media ----------------------------------------------------------
    media.name = "Media"
    key(media, "tb11", "media", "previous", "Prev", BLUE)
    key(media, "tb12", "media", "play-pause", "Play", GREEN)
    key(media, "tb13", "media", "next", "Next", BLUE)
    key(media, "tb14", "hotkey", "mute", "Mute", AMBER)
    key(media, "tb21", "hotkey", "volumedown", "Vol -", GREY)
    key(media, "tb22", "hotkey", "volumeup", "Vol +", GREY)
    key(media, "tb23", "media", "stop", "Stop", GREY)
    # Volume on a knob is the reason most people buy one of these.
    rotate(media, "enc1R", ("hotkey", "volumedown"), ("hotkey", "volumeup"),
           press=("hotkey", "mute"))
    scroll_knob(media, "enc1L", "enc2R")
    # CT only: the dial and its screen. Unbound controls on a Live are simply
    # never pressed, so this costs nothing there.
    rotate(media, "dial", ("hotkey", "volumedown"), ("hotkey", "volumeup"),
           press=("media", "play-pause"))
    media.labels["wheel"] = {"text": "Volume", "pos": "middle", "mode": "over"}

    # -- 2: Editing --------------------------------------------------------
    editing.name = "Editing"
    key(editing, "tb11", "hotkey", "%s+c" % MOD, "Copy", BLUE)
    key(editing, "tb12", "hotkey", "%s+v" % MOD, "Paste", BLUE)
    key(editing, "tb13", "hotkey", "%s+x" % MOD, "Cut", BLUE)
    key(editing, "tb14", "hotkey", "%s+a" % MOD, "All", GREY)
    key(editing, "tb21", "hotkey", "%s+z" % MOD, "Undo", AMBER)
    key(editing, "tb22", "hotkey", "%s+shift+z" % MOD, "Redo", AMBER)
    key(editing, "tb23", "hotkey", "%s+s" % MOD, "Save", GREEN)
    key(editing, "tb24", "hotkey", "%s+f" % MOD, "Find", GREY)
    scroll_knob(editing, "enc1L", "enc2R")
    rotate(editing, "enc1R", ("hotkey", "%s+z" % MOD),
           ("hotkey", "%s+shift+z" % MOD))

    # -- 3: Browser --------------------------------------------------------
    browser.name = "Browser"
    key(browser, "tb11", "hotkey", "alt+left", "Back", BLUE)
    key(browser, "tb12", "hotkey", "alt+right", "Fwd", BLUE)
    key(browser, "tb13", "hotkey", "%s+r" % MOD, "Reload", GREY)
    key(browser, "tb14", "hotkey", "%s+t" % MOD, "New tab", GREEN)
    key(browser, "tb21", "hotkey", "%s+w" % MOD, "Close", AMBER)
    key(browser, "tb22", "hotkey", "%s+shift+t" % MOD, "Reopen", GREY)
    key(browser, "tb23", "hotkey", "%s+l" % MOD, "Address", GREY)
    key(browser, "tb24", "hotkey", "%s+f" % MOD, "Find", GREY)
    scroll_knob(browser, "enc1L", "enc2R")
    rotate(browser, "enc1R", ("hotkey", "%s+shift+tab" % MOD),
           ("hotkey", "%s+tab" % MOD))

    # The round buttons switch workspace on the hardware already; colouring the
    # three that lead somewhere says which ones are worth pressing.
    for ws in (media, editing, browser):
        led(ws, WS_KEYS[0], "#2563eb")
        led(ws, WS_KEYS[1], "#16a34a")
        led(ws, WS_KEYS[2], "#d97706")

    return cfg


def main():
    cfg = build()
    data = cfg.to_JSON()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(data, f, indent=True, sort_keys=True)
        f.write("\n")
    bound = sum(1 for ws in data["workspaces"].values()
                for a in ws["actions"].values() if a["a_type"] != "none")
    print("wrote %s: %d bound controls across %d named workspaces"
          % (os.path.relpath(OUT, REPO), bound,
             sum(1 for ws in data["workspaces"].values() if ws.get("name"))))


if __name__ == "__main__":
    main()
