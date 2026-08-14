"""Generate a full Visual Studio Code deck.

A worked example of what an application profile looks like when it is actually
finished: five workspaces, every key labelled and coloured, every encoder
bound, both side strips used, and the chord shortcuts done as macros because a
chord is two presses and a hotkey is one.

    .venv/bin/python scripts/make_vscode_profile.py            # into the repo
    .venv/bin/python scripts/make_vscode_profile.py --install  # and into your config

Shortcuts are the Linux/Windows defaults. On macOS they want command rather
than control; the app maps "super" to it, so a search and replace of "ctrl"
with "super" is the whole conversion.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app_paths                                                  # noqa: E402
from LdConfiguration import LdConfiguration, LdAction             # noqa: E402

APP = "Visual Studio Code"
PROFILE = "Visual Studio Code"
# What a VS Code window reports as its class. The installed-app picker fills
# this in from the desktop entry's StartupWMClass.
MATCH = "Code"

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(REPO, "Profiles", APP)

MOD = "ctrl"

# Colour says what a key does before you have read it: destructive in amber,
# the one you press most in green, navigation blue, everything else neutral.
BLUE, GREEN, AMBER, RED, GREY = ("#1e3a8a", "#14532d", "#78350f", "#7f1d1d",
                                 "#27272a")


def key(ws, slot, a_type, value, label, color=GREY):
    ws.actions[slot] = LdAction(action_type=a_type, action=value)
    ws.labels[slot] = {"text": label, "pos": "bottom", "mode": "bar"}
    ws.bg_colors[slot] = color


def hotkey(ws, slot, combo, label, color=GREY):
    key(ws, slot, "hotkey", combo, label, color)


def chord(ws, slot, first, second, label, color=GREY):
    """A VS Code chord (ctrl+k then z) is two presses, not one combo.

    The wait is not decoration: the editor has to see the first press register
    and open its chord prompt before the second arrives.
    """
    key(ws, slot, "macro",
        "hotkey %s\nwait 120\nhotkey %s" % (first, second), label, color)


def palette(ws, slot, command, label, color=GREY):
    """Run a command by name through the command palette.

    Most of Git has no default keybinding, and inventing one in VS Code's own
    settings would be a change to the editor rather than to this deck. Typing
    the command is what a person does, so it is what the macro does.
    """
    key(ws, slot, "macro",
        "hotkey %s+shift+p\nwait 250\ntext %s\nwait 350\nhotkey return"
        % (MOD, command), label, color)


def rotate(ws, control, left, right, press=None):
    ws.actions[control + "-l"] = LdAction(action_type=left[0], action=left[1])
    ws.actions[control + "-r"] = LdAction(action_type=right[0], action=right[1])
    if press:
        ws.actions[control] = LdAction(action_type=press[0], action=press[1])


def side(ws, slot, combo, label, color=GREY):
    hotkey(ws, slot, combo, label, color)


def scroll_and_palette(ws):
    """The bindings every workspace should have in the same place.

    Muscle memory is the point of a deck: scroll must be the same knob in every
    workspace or the knob becomes something you have to look at.
    """
    rotate(ws, "enc1L", ("scroll", "up"), ("scroll", "down"),
           press=("hotkey", "%s+shift+p" % MOD))
    rotate(ws, "enc2R", ("hotkey", "%s+pageup" % MOD),
           ("hotkey", "%s+pagedown" % MOD),
           press=("hotkey", "%s+w" % MOD))
    rotate(ws, "dial", ("scroll", "up"), ("scroll", "down"),
           press=("hotkey", "%s+p" % MOD))
    ws.labels["wheel"] = {"text": "VS Code", "pos": "middle", "mode": "over"}


def build():
    cfg = LdConfiguration(profile=app_paths.make_ref(APP, PROFILE))
    edit, nav, run, git, view = cfg.workspaces[:5]

    # -- 1: Edit -----------------------------------------------------------
    edit.name = "Edit"
    hotkey(edit, "tb11", "%s+c" % MOD, "Copy", BLUE)
    hotkey(edit, "tb12", "%s+v" % MOD, "Paste", BLUE)
    hotkey(edit, "tb13", "%s+x" % MOD, "Cut", BLUE)
    hotkey(edit, "tb14", "%s+f" % MOD, "Find", GREY)
    hotkey(edit, "tb21", "%s+z" % MOD, "Undo", AMBER)
    hotkey(edit, "tb22", "%s+shift+z" % MOD, "Redo", AMBER)
    hotkey(edit, "tb23", "%s+h" % MOD, "Replace", GREY)
    hotkey(edit, "tb24", "%s+/" % MOD, "Comment", GREY)
    hotkey(edit, "tb31", "%s+s" % MOD, "Save", GREEN)
    chord(edit, "tb32", "%s+k" % MOD, "s", "Save all", GREEN)
    hotkey(edit, "tb33", "%s+shift+i" % MOD, "Format", GREY)
    hotkey(edit, "tb34", "f2", "Rename", GREY)
    scroll_and_palette(edit)
    # Zoom on a knob is the one adjustment that wants a knob.
    rotate(edit, "enc1R", ("hotkey", "%s+-" % MOD), ("hotkey", "%s+=" % MOD),
           press=("hotkey", "alt+z"))
    rotate(edit, "enc3R", ("hotkey", "%s+alt+-" % MOD),
           ("hotkey", "%s+shift+-" % MOD),
           press=("hotkey", "%s+g" % MOD))
    rotate(edit, "enc2L", ("hotkey", "alt+up"), ("hotkey", "alt+down"),
           press=("hotkey", "shift+alt+down"))
    rotate(edit, "enc3L", ("hotkey", "%s+[" % MOD), ("hotkey", "%s+]" % MOD),
           press=("hotkey", "%s+space" % MOD))

    # -- 2: Navigate -------------------------------------------------------
    nav.name = "Navigate"
    hotkey(nav, "tb11", "%s+p" % MOD, "Files", GREEN)
    hotkey(nav, "tb12", "%s+shift+o" % MOD, "Symbols", BLUE)
    hotkey(nav, "tb13", "%s+g" % MOD, "Line", BLUE)
    hotkey(nav, "tb14", "%s+shift+f" % MOD, "Search", GREY)
    hotkey(nav, "tb21", "f12", "Definition", BLUE)
    hotkey(nav, "tb22", "alt+f12", "Peek", BLUE)
    hotkey(nav, "tb23", "shift+f12", "References", BLUE)
    hotkey(nav, "tb24", "%s+t" % MOD, "Workspace", GREY)
    hotkey(nav, "tb31", "%s+alt+-" % MOD, "Back", GREY)
    hotkey(nav, "tb32", "%s+shift+-" % MOD, "Forward", GREY)
    hotkey(nav, "tb33", "f8", "Next issue", AMBER)
    hotkey(nav, "tb34", "shift+f8", "Prev issue", AMBER)
    scroll_and_palette(nav)
    rotate(nav, "enc1R", ("hotkey", "shift+f8"), ("hotkey", "f8"),
           press=("hotkey", "%s+shift+m" % MOD))
    rotate(nav, "enc3R", ("hotkey", "%s+alt+-" % MOD),
           ("hotkey", "%s+shift+-" % MOD),
           press=("hotkey", "%s+p" % MOD))

    # -- 3: Run and debug --------------------------------------------------
    run.name = "Run"
    hotkey(run, "tb11", "f5", "Start", GREEN)
    hotkey(run, "tb12", "shift+f5", "Stop", RED)
    hotkey(run, "tb13", "%s+shift+f5" % MOD, "Restart", AMBER)
    hotkey(run, "tb14", "%s+f5" % MOD, "No debug", GREY)
    hotkey(run, "tb21", "f10", "Step over", BLUE)
    hotkey(run, "tb22", "f11", "Step into", BLUE)
    hotkey(run, "tb23", "shift+f11", "Step out", BLUE)
    hotkey(run, "tb24", "f9", "Breakpoint", RED)
    hotkey(run, "tb31", "%s+shift+d" % MOD, "Debug view", GREY)
    hotkey(run, "tb32", "%s+shift+y" % MOD, "Console", GREY)
    hotkey(run, "tb33", "%s+shift+b" % MOD, "Run task", GREEN)
    palette(run, "tb34", "Debug: Remove All Breakpoints", "Clear bps", AMBER)
    scroll_and_palette(run)
    rotate(run, "enc1R", ("hotkey", "shift+f11"), ("hotkey", "f11"),
           press=("hotkey", "f10"))
    rotate(run, "enc3R", ("hotkey", "%s+alt+-" % MOD),
           ("hotkey", "%s+shift+-" % MOD),
           press=("hotkey", "f9"))

    # -- 4: Git ------------------------------------------------------------
    # Almost none of this has a default keybinding, so it is the palette.
    git.name = "Git"
    hotkey(git, "tb11", "%s+shift+g" % MOD, "Source ctl", GREEN)
    palette(git, "tb12", "Git: Stage All Changes", "Stage all", BLUE)
    palette(git, "tb13", "Git: Commit", "Commit", GREEN)
    palette(git, "tb14", "Git: Push", "Push", GREEN)
    palette(git, "tb21", "Git: Pull", "Pull", BLUE)
    palette(git, "tb22", "Git: Sync", "Sync", BLUE)
    palette(git, "tb23", "Git: Checkout to...", "Branch", GREY)
    palette(git, "tb24", "Git: Create Branch...", "New branch", GREY)
    palette(git, "tb31", "Git: Open Changes", "Diff", GREY)
    palette(git, "tb32", "Git: Stash", "Stash", GREY)
    palette(git, "tb33", "Git: Discard All Changes", "Discard", RED)
    palette(git, "tb34", "Git: View History", "History", GREY)
    scroll_and_palette(git)
    rotate(git, "enc1R", ("hotkey", "alt+f5"), ("hotkey", "f5"),
           press=("hotkey", "%s+shift+g" % MOD))

    # -- 5: View and terminal ----------------------------------------------
    view.name = "View"
    hotkey(view, "tb11", "%s+`" % MOD, "Terminal", GREEN)
    hotkey(view, "tb12", "%s+shift+`" % MOD, "New term", GREEN)
    hotkey(view, "tb13", "%s+j" % MOD, "Panel", GREY)
    hotkey(view, "tb14", "%s+b" % MOD, "Sidebar", GREY)
    hotkey(view, "tb21", "%s+backslash" % MOD, "Split", BLUE)
    hotkey(view, "tb22", "%s+w" % MOD, "Close tab", AMBER)
    chord(view, "tb23", "%s+k" % MOD, "z", "Zen", BLUE)
    hotkey(view, "tb24", "f11", "Fullscreen", GREY)
    hotkey(view, "tb31", "%s+shift+e" % MOD, "Explorer", BLUE)
    hotkey(view, "tb32", "%s+shift+x" % MOD, "Extensions", GREY)
    hotkey(view, "tb33", "alt+z", "Word wrap", GREY)
    palette(view, "tb34", "View: Toggle Minimap", "Minimap", GREY)
    scroll_and_palette(view)
    rotate(view, "enc1R", ("hotkey", "%s+-" % MOD), ("hotkey", "%s+=" % MOD),
           press=("hotkey", "%s+k" % MOD))

    # -- side displays, the same on every workspace ------------------------
    # The strips are where a view lives: same place every time, whatever you
    # are doing.
    for ws in (edit, nav, run, git, view):
        side(ws, "dis1L", "%s+shift+e" % MOD, "Files", BLUE)
        side(ws, "dis2L", "%s+shift+f" % MOD, "Find", BLUE)
        side(ws, "dis3L", "%s+shift+g" % MOD, "Git", BLUE)
        side(ws, "dis1R", "%s+shift+d" % MOD, "Debug", GREEN)
        side(ws, "dis2R", "%s+shift+x" % MOD, "Ext", GREY)
        side(ws, "dis3R", "%s+shift+m" % MOD, "Issues", AMBER)
        # The round keys lead somewhere, so they say which.
        for i, colour in enumerate(("#2563eb", "#16a34a", "#dc2626",
                                    "#d97706", "#7c3aed")):
            ws.led_colors[["circle", "1", "2", "3", "4"][i]] = colour

    return cfg


def write(directory, cfg):
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, PROFILE + ".json")
    with open(path, "w") as f:
        json.dump(cfg.to_JSON(), f, indent=True, sort_keys=True)
        f.write("\n")
    meta = os.path.join(directory, app_paths.APP_META)
    with open(meta, "w") as f:
        json.dump({"match": [MATCH], "default_profile": PROFILE}, f, indent=True)
        f.write("\n")
    return path


def main():
    cfg = build()
    path = write(OUT_DIR, cfg)
    bound = sum(1 for ws in cfg.workspaces
                for a in ws.actions.values() if a.a_type != "none")
    print("wrote %s: %d bound controls across %d workspaces"
          % (os.path.relpath(path, REPO), bound,
             sum(1 for ws in cfg.workspaces if ws.name)))
    if "--install" in sys.argv:
        user = write(app_paths.ensure_user_app_dir(APP), cfg)
        print("installed to %s" % user)


if __name__ == "__main__":
    main()
