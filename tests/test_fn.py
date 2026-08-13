"""The fn layer: hold vs latch, secondary dispatch, and not getting stuck."""
import os
import shutil
import sys
import tempfile

from _harness import Checks, controller

tmp = tempfile.mkdtemp(prefix="ldfn-")
os.environ["LOUPEDECKAPP_CONFIG_DIR"] = os.path.join(tmp, "config")

from DeviceProfile import WS_KEYS                   # noqa: E402
from LdConfiguration import LdAction                # noqa: E402

c = Checks()
fired = []


def act(tag):
    class A(LdAction):
        def __init__(self):
            LdAction.__init__(self, action_type="hotkey", action=tag)

        def execute(self, repeat=1):
            fired.append((tag, repeat))
    return A()


def build():
    dc, ws = controller()
    dc.render_workspace = lambda *a, **k: None
    ws.actions["tb11"] = act("primary")
    ws.set_fn_action("tb11", act("secondary"))
    ws.actions["tb12"] = act("only-primary")     # no fn binding
    return dc, ws


# -- hold ----------------------------------------------------------------------
dc, ws = build()
c.eq("hold is the default mode", dc.fn_mode, "hold")
c.eq("and the layer starts off", dc.fn_active, False)

dc.on_touch_press("tb11")
c.eq("without fn, the primary fires", fired, [("primary", 1)])

del fired[:]
dc.on_fn("fnL", "down")
c.eq("holding fn engages the layer", dc.fn_active, True)
dc.on_touch_press("tb11")
c.eq("with fn held, the secondary fires", fired, [("secondary", 1)])

del fired[:]
dc.on_touch_press("tb12")
c.eq("a control with no secondary keeps its primary under fn",
     fired, [("only-primary", 1)])

del fired[:]
dc.on_fn("fnL", "up")
c.eq("releasing fn drops the layer", dc.fn_active, False)
dc.on_touch_press("tb11")
c.eq("and the primary is back", fired, [("primary", 1)])

# either fn key drives the same layer
del fired[:]
dc.on_fn("fnR", "down")
dc.on_touch_press("tb11")
c.eq("the right fn key works the same", fired, [("secondary", 1)])
dc.on_fn("fnR", "up")

# -- latch ---------------------------------------------------------------------
dc.fn_mode = "latch"
del fired[:]
dc.on_fn("fnL", "down")
dc.on_fn("fnL", "up")            # release must not drop a latched layer
c.eq("latch survives the key release", dc.fn_active, True)
dc.on_touch_press("tb11")
c.eq("and fires the secondary", fired, [("secondary", 1)])

del fired[:]
dc.on_fn("fnL", "down")
dc.on_fn("fnL", "up")
c.eq("a second press releases the latch", dc.fn_active, False)
dc.on_touch_press("tb11")
c.eq("back to the primary", fired, [("primary", 1)])

# -- the layer must not get stuck ----------------------------------------------
dc.fn_mode = "hold"
dc.on_fn("fnL", "down")
c.eq("layer is on", dc.fn_active, True)
dc.on_workspace_press(WS_KEYS[2])
c.eq("changing workspace releases it, since the key-up lands elsewhere",
     dc.fn_active, False)
dc.close()

# -- encoders and CT buttons take the layer too --------------------------------
dc, ws = build()
ws.actions["enc1L"] = act("enc-press")
ws.set_fn_action("enc1L", act("enc-press-fn"))
ws.actions["home"] = act("home")
ws.set_fn_action("home", act("home-fn"))
del fired[:]
dc.on_fn("fnL", "down")
dc.run_bound_action("enc1L")
dc.run_bound_action("home")
c.eq("encoder press and CT buttons use their secondary",
     fired, [("enc-press-fn", 1), ("home-fn", 1)])
dc.on_fn("fnL", "up")
dc.close()

# -- the fn key itself never runs a binding ------------------------------------
dc, ws = build()
ws.actions["fnL"] = act("should-never-fire")
del fired[:]


class Msg(dict):
    pass


from Loupedeck.Devices.LoupedeckLive import CALLBACK_KEYWORD as CBC   # noqa: E402

dc.profile.extra_buttons = tuple(list(dc.profile.extra_buttons) + ["fnL"]) \
    if "fnL" not in dc.profile.extra_buttons else dc.profile.extra_buttons
dc.device_callback(None, {CBC.IDENTIFIER.value: "fnL", CBC.STATE.value: "down"})
c.eq("pressing fn engages the layer rather than running a binding",
     (dc.fn_active, fired), (True, []))
dc.device_callback(None, {CBC.IDENTIFIER.value: "fnL", CBC.STATE.value: "up"})
c.eq("and releasing it drops the layer", dc.fn_active, False)
dc.close()

# -- fn key colours ------------------------------------------------------------
lit = []


class FakeDevice:
    DECK_TYPE = "LoupedeckLive"
    path = None
    reading_thread = None

    def set_button_color(self, key, color): lit.append((key, color))
    def reset(self): pass
    def stop(self): pass


dc, ws = build()
dc.device = FakeDevice()
dc.profile.extra_buttons = tuple(
    list(dc.profile.extra_buttons) + [k for k in ("fnL", "fnR")
                                      if k not in dc.profile.extra_buttons])

c.eq("the default on-colour is white", dc.fn_active_color, "#ffffff")
c.eq("and off is blank, meaning use the LED colour", dc.fn_inactive_color, "")

del lit[:]
dc.on_fn("fnL", "down")
c.eq("engaging lights both fn keys with the on-colour",
     sorted(lit), [("fnL", (255, 255, 255)), ("fnR", (255, 255, 255))])

del lit[:]
dc.on_fn("fnL", "up")
c.eq("releasing falls back to the dim default",
     sorted(lit), [("fnL", (63, 63, 63)), ("fnR", (63, 63, 63))])

# an explicit off-colour wins over the fallback
dc.set_fn_colors(active="#ff0044", inactive="#101820")
del lit[:]
dc.on_fn("fnL", "down")
c.eq("a custom on-colour is used", lit[0][1], (255, 0, 68))
del lit[:]
dc.on_fn("fnL", "up")
c.eq("and a custom off-colour", lit[0][1], (16, 24, 32))

# clearing the off-colour returns to the workspace's own LED colour
ws.led_colors["fnL"] = "#00ff00"
dc.set_fn_colors(inactive="")
del lit[:]
dc.on_fn("fnL", "down")
dc.on_fn("fnL", "up")
c.eq("with no off-colour, the button's LED colour is used",
     dict(lit)["fnL"], (0, 255, 0))

# setting colours repaints immediately, so the choice is visible while picking
del lit[:]
dc.set_fn_colors(active="#0000ff")
c.eq("changing a colour repaints the keys at once", len(lit) > 0, True)
dc.close()

shutil.rmtree(tmp, ignore_errors=True)
sys.exit(c.done())
