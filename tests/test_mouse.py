"""Mouse actions: clicks, the wheel, moving and dragging, with keys held
around them (input_backend.mouse), as actions, as macro steps, and from
imported Loupedeck profiles. Run against a backend that records what it is
asked to do, so nothing moves the real pointer."""
import os
import tempfile

from _harness import Checks

tmp = tempfile.mkdtemp()
os.environ["LOUPEDECKAPP_CONFIG_DIR"] = os.path.join(tmp, "config")

import input_backend                                              # noqa: E402
import lp5_import as lp5                                          # noqa: E402
import macro                                                      # noqa: E402
from LdConfiguration import LdAction                              # noqa: E402

c = Checks()


class Recorder(input_backend.InputBackend):
    name = "recorder"
    hold = True

    def __init__(self):
        self.calls = []

    def available(self):
        return True

    def key_down(self, name):
        if not self.hold:
            raise NotImplementedError
        self.calls.append(("down", name))

    def key_up(self, name):
        self.calls.append(("up", name))

    def click(self, button="left", count=1):
        self.calls.append(("click", button, count))

    def mouse_move(self, dx, dy):
        self.calls.append(("move", dx, dy))

    def mouse_down(self, button="left"):
        self.calls.append(("press", button))

    def mouse_up(self, button="left"):
        self.calls.append(("release", button))

    def scroll(self, direction, amount=1):
        self.calls.append(("scroll", direction, amount))


rec = Recorder()
input_backend._backend = rec


def run(action, amount=1):
    del rec.calls[:]
    input_backend.mouse(action, amount)
    return list(rec.calls)


c.eq("a click is a left click", run("click"), [("click", "left", 1)])
c.eq("a double click clicks twice", run("doubleclick"), [("click", "left", 2)])
c.eq("right and middle", (run("rightclick"), run("middleclick")),
     ([("click", "right", 1)], [("click", "middle", 1)]))
c.eq("keys before + are held around it", run("ctrl+shift+click"),
     [("down", "ctrl"), ("down", "shift"), ("click", "left", 1), ("up", "shift"), ("up", "ctrl")])
c.eq("ctrl + wheel, by a knob's notches", run("ctrl+scroll-up", 3),
     [("down", "ctrl"), ("scroll", "up", 3), ("up", "ctrl")])
c.eq("a move goes a step per notch", run("move-left", 2), [("move", -20, 0)])
c.eq("a drag holds the button while it moves", run("drag-down"),
     [("press", "left"), ("move", 0, 10), ("release", "left")])
c.eq("a click happens once however fast the knob turns", run("click", 5), [("click", "left", 1)])
rec.hold = False
c.eq("where keys cannot be held, the click is plain", run("alt+click"), [("click", "left", 1)])
rec.hold = True
for bad in ("fly", "ctrl+", "hyper+click", ""):
    try:
        input_backend.parse_mouse(bad)
        ok = False
    except ValueError:
        ok = True
    c.eq("%r is refused" % bad, ok, True)

del rec.calls[:]
LdAction(action_type="mouse", action="move-right").execute(repeat=3)
c.eq("an action passes a knob's notches on", rec.calls, [("move", 30, 0)])
steps, errors = macro.parse("mouse ctrl+click\nmouse fly")
c.eq("a macro step", (steps, len(errors)), ([("mouse", "ctrl+click")], 1))
c.eq("and the step editor offers it", "mouse" in macro.STEP_KINDS, True)

# -- from Loupedeck profiles -------------------------------------------------------
g = "$@generic___"
PROFILE = {
    "macroCommands": [
        {"name": "PICK", "displayName": "Pick", "actions": [g + "@MouseClick___AltLeft"]},
        {"name": "CLICKTYPE", "displayName": "Click and type",
         "actions": [g + "@MouseDoubleClick", g + "@KeyboardShortcut___KeyA"]},
    ],
    "macroAdjustments": [
        {"name": "ZOOM", "displayName": "Zoom", "actionsLeft": [g + "@MouseWheel___ControlLeft"],
         "actionsRight": [g + "@MouseWheel___ControlLeft"]},
    ],
    "layout": {"roundPage": {"controls": [press for press in [{"pressAction": g + "@ChangeWorkspace___main|A"}]]},
               "squarePage": {"controls": []},
               "layoutModes": [{
                   "workspaces": [{"name": "A", "displayName": "A", "touchPageNames": ["T"],
                                   "encoderPageNames": ["E"]}],
                   "touchPages": [{"name": "T", "controls": [
                       {"pressAction": g + "@MouseClick"}, {"pressAction": g + "@MouseClickRight___ControlLeft"},
                       {"pressAction": g + "@Macro___PICK"}, {"pressAction": g + "@Macro___CLICKTYPE"}]}],
                   "encoderPages": [{"name": "E", "controls": [
                       {"rotateAction": g + "@MouseDragAndDropVertically"},
                       {"rotateAction": g + "@MouseMoveHorizontal"},
                       {"rotateAction": g + "@Macro adjustment___ZOOM"},
                       {"rotateAction": g + "@MouseWheel"}]}],
                   "wheelPages": []}]}}
cfg, notes = lp5.convert(PROFILE, {}, os.path.join(tmp, "img"), "X/Y")
ws = cfg.workspaces[0]


def got(slot):
    a = ws.actions.get(slot)
    return (a.a_type, a.action) if a is not None else None


c.eq("a profile's click", got("tb11"), ("mouse", "click"))
c.eq("with a key held", got("tb12"), ("mouse", "ctrl+rightclick"))
c.eq("in a macro of one step", got("tb13"), ("mouse", "alt+click"))
c.eq("and among other steps", got("tb14"), ("macro", "mouse doubleclick\nwait 50\nhotkey a"))
c.eq("a dragging knob", (got("enc1L-l"), got("enc1L-r")), (("mouse", "drag-up"), ("mouse", "drag-down")))
c.eq("a moving knob", (got("enc2L-l"), got("enc2L-r")), (("mouse", "move-left"), ("mouse", "move-right")))
c.eq("ctrl + wheel in a knob macro", (got("enc3L-l"), got("enc3L-r")),
     (("mouse", "ctrl+scroll-up"), ("mouse", "ctrl+scroll-down")))
c.eq("the plain wheel stays a scroll", (got("enc1R-l"), got("enc1R-r")), (("scroll", "up"), ("scroll", "down")))
c.eq("none of it is reported as unsupported", [n for n in notes if "not something" in n], [])
c.eq("and all of it validates", lp5.validate(cfg), [])

raise SystemExit(c.done())
