"""Default CT button bindings, and the workspace / keyboard action types."""
import os
import shutil
import sys
import tempfile

from _harness import Checks, controller

tmp = tempfile.mkdtemp(prefix="ldbtn-")
os.environ["LOUPEDECKAPP_CONFIG_DIR"] = os.path.join(tmp, "config")

import LdConfiguration as LC                        # noqa: E402
from DeviceProfile import WS_KEYS                   # noqa: E402
from LdConfiguration import (LdConfiguration, LdAction, apply_default_bindings,
                             DEFAULT_BUTTON_BINDINGS)   # noqa: E402

c = Checks()

# -- defaults ------------------------------------------------------------------
cfg = apply_default_bindings(LdConfiguration(profile="fresh"))
ws = cfg.workspaces[0]
c.eq("home goes to workspace 1",
     (ws.actions["home"].a_type, ws.actions["home"].action), ("workspace", WS_KEYS[0]))
c.eq("undo is ctrl+z", ws.actions["undo"].action, "ctrl+z")
c.eq("save is ctrl+s", ws.actions["save"].action, "ctrl+s")
c.eq("enter is enter", ws.actions["enter"].action, "enter")
c.eq("keyboard toggles the on-screen keyboard",
     (ws.actions["keyboard"].a_type, ws.actions["keyboard"].action),
     ("keyboard", "toggle"))
c.eq("fn is left alone: it is a modifier, not an action",
     ws.actions["fnL"].a_type, "none")
c.eq("defaults reach every workspace",
     all(w.actions["undo"].action == "ctrl+z" for w in cfg.workspaces), True)
c.eq("they carry a summary for the auto-label",
     ws.actions["undo"].summary, "Undo")

# An existing binding must never be overwritten by the defaults.
custom = LdConfiguration(profile="custom")
custom.workspaces[0].actions["undo"] = LdAction(action_type="text", action="mine")
apply_default_bindings(custom)
c.eq("an existing binding is not clobbered",
     custom.workspaces[0].actions["undo"].action, "mine")
c.eq("but empty ones alongside it are still filled",
     custom.workspaces[0].actions["save"].action, "ctrl+s")

plain = LdConfiguration(profile="plain")
c.eq("apply_default_bindings is explicit: a plain config has none",
     plain.workspaces[0].actions["undo"].a_type, "none")

# -- applied on load, so profiles predating this are not left with dead keys ---
saved = LdConfiguration(profile="older")
saved.workspaces[0].actions["undo"] = LdAction(action_type="text", action="mine")
saved.save("older")

dc2, _ = controller()
dc2.render_workspace = lambda *a, **k: None
dc2.load_profile("older")
c.eq("loading fills the empty labelled buttons",
     dc2.config.workspaces[0].actions["save"].action, "ctrl+s")
c.eq("without disturbing one that was already bound",
     dc2.config.workspaces[0].actions["undo"].action, "mine")
c.eq("and without marking the profile dirty", dc2.dirty, False)

dc2.auto_bind_buttons = False
dc2.load_profile("older")
c.eq("the behaviour can be turned off",
     dc2.config.workspaces[0].actions["save"].a_type, "none")
dc2.close()

# -- workspace action ----------------------------------------------------------
calls = []


def fake(key):
    class A(LdAction):
        def __init__(self):
            LdAction.__init__(self, action_type="hotkey", action="x")

        def execute(self, repeat=1):
            calls.append((key, repeat))
    return A()


dc, ws0 = controller(action_factory=fake, controls=("enc1L",))
dc.render_workspace = lambda *a, **k: None
switched = []
real_press = dc.on_workspace_press
dc.on_workspace_press = lambda k: (switched.append(k), real_press(k))[1]

ws0.actions["tb11"] = LdAction(action_type="workspace", action=WS_KEYS[3])
dc.on_touch_press("tb11")
c.eq("a workspace action switches workspace", switched, [WS_KEYS[3]])
c.eq("and the controller followed it", dc.selected_ws, WS_KEYS[3])

# switching to the one already active is a no-op, not a re-render
del switched[:]
dc.current_ws().actions["tb12"] = LdAction(action_type="workspace",
                                           action=WS_KEYS[3])
dc.on_touch_press("tb12")
c.eq("switching to the active workspace does nothing", switched, [])

# an unknown workspace key is ignored rather than crashing
dc.current_ws().actions["tb13"] = LdAction(action_type="workspace", action="nope")
dc.on_touch_press("tb13")
c.eq("an unknown workspace key is ignored", switched, [])
dc.close()

# -- keyboard action -----------------------------------------------------------
import virtual_keyboard as vk                       # noqa: E402

seen = []


class FakeKeyboard(vk.VirtualKeyboard):
    name = "fake"

    def __init__(self):
        self.on = False

    def available(self):
        return True

    def is_active(self):
        return self.on

    def set_active(self, on):
        self.on = bool(on)
        seen.append("on" if on else "off")
        return True


vk._keyboard = FakeKeyboard()
try:
    LdAction(action_type="keyboard", action="toggle").execute()
    c.eq("toggle turns it on from off", seen, ["on"])
    LdAction(action_type="keyboard", action="toggle").execute()
    c.eq("and off again", seen, ["on", "off"])
    del seen[:]
    LdAction(action_type="keyboard", action="show").execute()
    LdAction(action_type="keyboard", action="show").execute()
    c.eq("show is idempotent", seen, ["on", "on"])
    LdAction(action_type="keyboard", action="hide").execute()
    c.eq("hide turns it off", seen[-1], "off")
    # A rotary control could ask for a repeat; flapping the keyboard N times
    # would be useless, so it must act once.
    del seen[:]
    LdAction(action_type="keyboard", action="toggle").execute(repeat=5)
    c.eq("a repeat still acts once", len(seen), 1)
finally:
    vk.reset()

shutil.rmtree(tmp, ignore_errors=True)
sys.exit(c.done())
