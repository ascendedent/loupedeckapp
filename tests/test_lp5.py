"""Loupedeck 5 profiles (.lp5): reading, converting, and installing one.

The package here is built by the test in the shape the official software
exports (the same `$type`-tagged object graph), small enough that every rule
the importer follows has one case: a one-key macro, a two-key one, a mouse
wheel knob, the default plugin's volume knob, workspaces placed by the round
buttons, square buttons with an fn binding, an image, and the things that do
not come across and have to be reported.
"""
import io
import json
import os
import shutil
import tempfile
import zipfile

from _harness import Checks

tmp = tempfile.mkdtemp()
os.environ["LOUPEDECKAPP_CONFIG_DIR"] = os.path.join(tmp, "config")

import app_paths                                                  # noqa: E402
import lp5_import as lp5                                          # noqa: E402

c = Checks()


def macro(name, display, *steps):
    return {"$type": "Loupedeck.Service.ApplicationProfileMacroCommand, LoupedeckService",
            "isCommand": True, "name": name, "displayName": display,
            "actions": ["$@Generic___@KeyboardShortcut___" + s for s in steps]}


def adjustment(name, display, left, right):
    return {"$type": "Loupedeck.Service.ApplicationProfileMacroAdjustment, LoupedeckService",
            "isCommand": False, "name": name, "displayName": display,
            "actionsBefore": [""], "actionsLeft": left, "actionsRight": right,
            "actionsReset": []}


def press(ref, **extra):
    d = {"$type": "Loupedeck.Service.ProfileLayoutControl, LoupedeckService"}
    if ref:
        d["pressAction"] = ref
    d.update(extra)
    return d


M = "$@Generic___@Macro___"
PROFILE = {
    "$type": "Loupedeck.Service.ApplicationProfile, LoupedeckService",
    "name": "P1", "displayName": "Chat", "deviceType": "Loupedeck20",
    "applicationName": "chatapp",
    "macroCommands": [
        macro("BOLD", "Bold", "ControlOrCommand+KeyB"),
        macro("TWO", "Two keys", "ControlOrCommand+KeyK", "KeyZ"),
        macro("REDO", "Redo", "ControlOrCommand+KeyY"),
        macro("UNDO", "Undo", "ControlOrCommand+KeyZ"),
        macro("NOKEY", "Odd", "Hyper+KeyQ"),
    ],
    "macroAdjustments": [
        adjustment("SCROLL", "Scroll", ["$@Generic___@MouseWheel"],
                   ["$@Generic___@MouseWheel"]),
        adjustment("ZOOM", "Zoom", ["$@Generic___@KeyboardShortcut___ControlOrCommand+Subtract"],
                   ["$@Generic___@KeyboardShortcut___ControlOrCommand+Add"]),
    ],
    "layout": {
        "roundPage": {"controls": [
            press("$@Generic___@ChangeWorkspace___main|WS_HOME"),
            press("$@Generic___@ChangeWorkspace___main|WS_TWO"),
        ]},
        "squarePage": {"controls": [
            press(None), press(M + "UNDO", fnPressAction=M + "REDO"),
            press(None), press(None), press(None), press(None),
            press(M + "BOLD"),
        ]},
        "layoutModes": [{
            "modeName": "main", "homeWorkspaceName": "WS_HOME",
            "workspaces": [
                # Listed out of order on purpose: the round buttons decide.
                {"name": "WS_TWO", "displayName": "Second",
                 "touchPageNames": ["T2", "T2b"], "encoderPageNames": ["E1"],
                 "wheelPageNames": []},
                {"name": "WS_HOME", "displayName": "Home",
                 "touchPageNames": ["T1"], "encoderPageNames": ["E1"],
                 "wheelPageNames": ["W1"]},
            ],
            "touchPages": [
                {"name": "T1", "controls": [
                    press(M + "BOLD"), press(M + "TWO"),
                    press(None), press(None),
                    press(M + "NOKEY"),
                    press("$Spotify___Like", longPressAction=M + "BOLD")]},
                {"name": "T2", "controls": [press(None)] * 11 + [press(M + "BOLD")]},
                {"name": "T2b", "controls": []},
            ],
            "encoderPages": [{"name": "E1", "controls": [
                {"pressAction": "$DefaultWin___ResetVolume",
                 "rotateAction": "$DefaultWin___Volume"},
                {}, {"rotateAction": "$@Generic___@MacroAdjustment___SCROLL"},
                {}, {}, {"rotateAction": "$@Generic___@MacroAdjustment___ZOOM"}]}],
            "wheelPages": [{"name": "W1", "templateName": "WheelToolAnalogClock",
                            "parameters": {"adjustment":
                                           "$@Generic___@MacroAdjustment___SCROLL"}}],
        }],
    },
}

APPINFO = {"name": "chatapp", "displayName": "Chat App",
           "processOrBundleName": "chatapp"}


def png_bytes():
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGBA", (90, 90), (0, 128, 255, 255)).save(buf, "PNG")
    return buf.getvalue()


path = os.path.join(tmp, "chat.lp5")
with zipfile.ZipFile(path, "w") as zf:
    zf.writestr("metadata/LoupedeckPackage.yaml", "type: Profile5\nname: P1\n")
    zf.writestr("ApplicationInfo.json", json.dumps(APPINFO))
    # The official files start with a byte-order mark.
    zf.writestr("ProfileInfo.json", "﻿" + json.dumps(PROFILE))
    zf.writestr("ActionImages/$@generic___@Macro___BOLD.png", png_bytes())

# -- key names -----------------------------------------------------------------
c.eq("modifiers and letters", lp5.convert_combo("Shift+ControlOrCommand+KeyX"), "shift+ctrl+x")
c.eq("digits", lp5.convert_combo("ControlOrCommand+Key0"), "ctrl+0")
c.eq("arrows and option", lp5.convert_combo("AltOrOption+ArrowUp"), "alt+up")
c.eq("return is enter", lp5.convert_combo("Shift+Return"), "shift+enter")
c.eq("keypad plus is the = key, which zooms the same",
     lp5.convert_combo("ControlOrCommand+Add"), "ctrl+equal")
c.eq("a key this app has no name for is refused, not guessed",
     lp5.convert_combo("Hyper+KeyQ"), None)

# -- not a profile -------------------------------------------------------------
junk = os.path.join(tmp, "junk.lp5")
with open(junk, "w") as f:
    f.write("nope")
c.eq("a file that is not a zip is refused",
     "not a Loupedeck profile" in lp5.import_lp5(junk)[2], True)

# -- the import ------------------------------------------------------------------
app, notes, error = lp5.import_lp5(path)
c.eq("it imports", (app, error), ("Chat App", ""))
c.eq("the app switches on the profile's process name",
     app_paths.app_matches("Chat App"), ["chatapp"])
c.eq("and opens with it", app_paths.app_default_profile("Chat App"), "Chat")

with open(app_paths.profile_read_path(app_paths.make_ref("Chat App", "Chat"))) as f:
    saved = json.load(f)
home, second = saved["workspaces"]["circle"], saved["workspaces"]["1"]


def act(ws, slot):
    a = ws["actions"].get(slot) or {}
    return (a.get("a_type"), a.get("action"))


c.eq("workspaces go to the round button that chose them",
     (home["name"], second["name"]), ("Home", "Second"))
c.eq("a one-key macro is a hotkey", act(home, "tb11"), ("hotkey", "ctrl+b"))
c.eq("with its name as the label", home["labels"]["tb11"]["text"], "Bold")
c.eq("and its image", os.path.isfile(home["images"]["tb11"]), True)
c.eq("several keys become a macro with waits",
     act(home, "tb12"), ("macro", "hotkey ctrl+k\nwait 50\nhotkey z"))
c.eq("keys go row by row, four across", act(second, "tb34"), ("hotkey", "ctrl+b"))
c.eq("a shortcut with no key here is left unbound", act(home, "tb21"), ("none", ""))
c.eq("as is another plugin's action", act(home, "tb22"), ("none", ""))

c.eq("the volume knob turns volume", (act(home, "enc1L-l"), act(home, "enc1L-r")),
     (("hotkey", "volumedown"), ("hotkey", "volumeup")))
c.eq("and pressing it mutes", act(home, "enc1L"), ("hotkey", "mute"))
c.eq("the mouse wheel scrolls, left up and right down",
     (act(home, "enc3L-l"), act(home, "enc3L-r")), (("scroll", "up"), ("scroll", "down")))
c.eq("the right column is the second three knobs",
     (act(home, "enc3R-l"), act(home, "enc3R-r")),
     (("hotkey", "ctrl+minus"), ("hotkey", "ctrl+equal")))
c.eq("knobs are named on the strip beside them",
     {k: v["text"] for k, v in home["labels"].items() if k.startswith("dis")},
     {"dis1L": "Volume", "dis3L": "Scroll", "dis3R": "Zoom"})
c.eq("the dial keeps the wheel's adjustment",
     (act(home, "dial-l"), act(home, "dial-r")), (("scroll", "up"), ("scroll", "down")))
c.eq("and the wheel shows the workspace's name", home["labels"]["wheel"]["text"], "Home")

c.eq("square buttons follow the hardware order", act(home, "undo"), ("hotkey", "ctrl+z"))
c.eq("index 6 is A", act(home, "a"), ("hotkey", "ctrl+b"))
c.eq("and are the same on every workspace", act(second, "undo"), ("hotkey", "ctrl+z"))
c.eq("fn presses come across, with Windows' redo made native",
     home["fn_actions"]["undo"]["action"], "ctrl+shift+z")

joined = "\n".join(notes)
for what, needle in (("the unknown shortcut", "Hyper+KeyQ"),
                     ("the other plugin's action", "Spotify"),
                     ("the long press", "long press"),
                     ("the second page of keys", "only the first"),
                     ("the clock", "analog clock"),
                     ("the redo translation", "Redo")):
    c.eq("the notes mention %s" % what, needle in joined, True)

cfg, _ = lp5.convert(PROFILE, {}, os.path.join(tmp, "img"), "X/Y")
c.eq("everything bound is something the app accepts", lp5.validate(cfg), [])

# Importing again into an app that is already set up keeps its settings.
app_paths.set_app_matches("Chat App", ["mine"])
app, notes, error = lp5.import_lp5(path)
c.eq("a second import leaves the app's own match alone",
     app_paths.app_matches("Chat App"), ["mine"])

# Newer profiles spell the same things differently: "@generic", "@Macro
# adjustment", "@Keyboard shortcut___arrow up", "@Change workspace".
g = "$@generic___"
NEWER = {
    "macroCommands": [
        {"name": "MIC", "displayName": "Mic", "actions": [g + "@KeyboardShortcut___ControlOrCommand+Shift+KeyA"]},
        {"name": "CODE", "displayName": "Code", "actions": [g + "@TypeText___```"]},
        {"name": "FIT", "displayName": "Fit", "actions": [g + "@KeyboardShortcut___ControlOrCommand+Oem2"]},
        {"name": "MUTE", "displayName": "Mute", "actions": [g + "@KeyboardShortcut___VolumeMute"]},
        {"name": "SKIP", "displayName": "Skip", "actions": [g + "@None", g + "@KeyboardShortcut___KeyS"]},
    ],
    "macroAdjustments": [
        {"name": "MOVE", "displayName": "Move", "actionsLeft": [g + "@HorizontalArrows"],
         "actionsRight": [g + "@HorizontalArrows"]},
    ],
    "layout": {
        "roundPage": {"controls": [press(g + "@Change workspace___main|A"),
                                   press(g + "@Change workspace___main|B"), press(g + "@None")]},
        "squarePage": {"controls": []},
        "layoutModes": [{
            "workspaces": [{"name": "A", "displayName": "A", "touchPageNames": ["TA"],
                            "encoderPageNames": ["EA"]},
                           {"name": "B", "displayName": "B", "touchPageNames": [],
                            "encoderPageNames": []}],
            "touchPages": [{"name": "TA", "controls": [
                press(g + "@Macro___MIC"), press(g + "@Macro___CODE"), press(g + "@Macro___FIT"),
                press(g + "@Macro___MUTE"), press(g + "@Keyboard shortcut___arrow up"),
                press(g + "@Change workspace___main|B"), press(g + "@None"), press(g + "@Macro___SKIP")]}],
            "encoderPages": [{"name": "EA", "controls": [
                {"rotateAction": g + "@Macro adjustment___MOVE"},
                {"rotateAction": g + "@VerticalArrows"}]}],
            "wheelPages": [],
        }],
    },
}
cfg, notes = lp5.convert(NEWER, {}, os.path.join(tmp, "img2"), "X/Z")
ws_a = cfg.workspaces[0]


def got(slot):
    a = ws_a.actions.get(slot)
    return (a.a_type, a.action) if a is not None else (None, None)


c.eq("a macro written @generic is found", got("tb11"), ("hotkey", "ctrl+shift+a"))
c.eq("typing text becomes a text action", got("tb12"), ("text", "```"))
c.eq("Windows' OEM keys have their US meaning", got("tb13"), ("hotkey", "ctrl+slash"))
c.eq("the mute key mutes", got("tb14"), ("hotkey", "mute"))
c.eq("a shortcut written with spaces is read", got("tb21"), ("hotkey", "up"))
c.eq("a key that switches workspace still does", got("tb22"), ("workspace", lp5.WS_KEYS[1]))
c.eq("an empty step in a macro is skipped", got("tb24"), ("hotkey", "s"))
c.eq("a knob macro written @Macro adjustment turns arrows",
     (got("enc1L-l"), got("enc1L-r")), (("hotkey", "left"), ("hotkey", "right")))
c.eq("so does the vertical arrows knob", (got("enc2L-l"), got("enc2L-r")), (("hotkey", "up"), ("hotkey", "down")))
c.eq("and none of it is reported as unsupported",
     [n for n in notes if "not something this app can do" in n or "did something other" in n], [])
c.eq("the newer spellings validate", lp5.validate(cfg), [])

shutil.rmtree(tmp, ignore_errors=True)
raise SystemExit(c.done())
