"""Per-model control inventory: what each device physically has.

The device view draws from these lists, so a wrong entry shows up as a Live S
with six encoders or a CT missing its side strips.
"""
import sys

from _harness import Checks

import DeviceProfile as DP
from LdConfiguration import LdWorkspace, MAX_TOUCH_COLUMNS, TOUCH_KEYS

c = Checks()

ct = DP.DeviceProfile.for_model(DP.MODEL_CT)
live = DP.DeviceProfile.for_model(DP.MODEL_LIVE)
live_s = DP.DeviceProfile.for_model(DP.MODEL_LIVE_S)

# -- CT ----------------------------------------------------------------------
c.eq("CT has six encoders",
     len(ct.encoders_left) + len(ct.encoders_right), 6)
c.eq("CT side strips are three cells each",
     (ct.side_cell_keys("L"), ct.side_cell_keys("R")),
     (["dis1L", "dis2L", "dis3L"], ["dis1R", "dis2R", "dis3R"]))
c.eq("CT has side displays", ct.has_side_displays, True)
c.eq("CT has the wheel and dial", (ct.has_wheel, ct.has_dial), (True, True))
c.eq("CT shows eight round buttons", len(ct.visible_workspace_keys), 8)
c.eq("CT keys are a 4x3 grid", ct.touch_keys[:5],
     ["tb11", "tb12", "tb13", "tb14", "tb21"])
c.eq("CT has twelve keys", len(ct.touch_keys), 12)

# -- Live --------------------------------------------------------------------
c.eq("Live has the CT's encoders and strips",
     (len(live.encoders_left), len(live.encoders_right),
      live.has_side_displays), (3, 3, True))
c.eq("Live has no wheel or dial", (live.has_wheel, live.has_dial), (False, False))
c.eq("Live shows eight round buttons", len(live.visible_workspace_keys), 8)

# -- Live S ------------------------------------------------------------------
c.eq("Live S has two dials", len(live_s.encoders_left) + len(live_s.encoders_right), 2)
c.eq("Live S has no side displays", live_s.has_side_displays, False)
c.eq("Live S side cells are empty",
     (live_s.side_cell_keys("L"), live_s.side_cell_keys("R")), ([], []))
c.eq("Live S has no wheel", live_s.has_wheel, False)
c.eq("Live S shows four round buttons", live_s.visible_workspace_keys,
     ["circle", "1", "2", "3"])
c.eq("Live S keys are a 5x3 grid", len(live_s.touch_keys), 15)
c.eq("Live S last key is tb35", live_s.touch_keys[-1], "tb35")

# -- PID routing -------------------------------------------------------------
c.eq("PID 0x0003 is the CT", DP.DeviceProfile.for_pid(0x0003).model, DP.MODEL_CT)
c.eq("PID 0x0006 is the Live S", DP.DeviceProfile.for_pid(0x0006).model, DP.MODEL_LIVE_S)
c.eq("an unknown PID falls back to Live geometry",
     DP.DeviceProfile.for_pid(0x1234).model, DP.MODEL_LIVE)

# -- storage covers the widest model ----------------------------------------
ws = LdWorkspace()
c.eq("a profile stores five columns so a Live S fits", MAX_TOUCH_COLUMNS, 5)
c.eq("every model's keys have somewhere to live",
     all(k in ws.actions for k in ct.touch_keys + live_s.touch_keys), True)
c.eq("and every one of those keys can hold an image",
     all(k in ws.images for k in TOUCH_KEYS), True)

# The controller derives a key name from the touch index using the model's
# column count, so a Live S must land on the fifth column rather than wrap.
class FakeCtl:
    profile = live_s

    def __init__(self):
        self.pressed = []

    def on_touch_press(self, name):
        self.pressed.append(name)


from device_controller import DeviceController   # noqa: E402

fake = FakeCtl()
DeviceController.on_touchkey_press(fake, 4)      # first row, last column
DeviceController.on_touchkey_press(fake, 14)     # last row, last column
c.eq("a Live S touch index maps across five columns", fake.pressed, ["tb15", "tb35"])

# -- model override ----------------------------------------------------------
import os   # noqa: E402

for raw, want in (("ct", DP.MODEL_CT), ("CT", DP.MODEL_CT),
                  ("live-s", DP.MODEL_LIVE_S), ("live_s", DP.MODEL_LIVE_S),
                  ("LiveS", DP.MODEL_LIVE_S), ("live", DP.MODEL_LIVE)):
    os.environ[DP.FORCE_MODEL_ENV] = raw
    c.eq("%s forces %s" % (raw, want), DP.forced_model(), want)

os.environ[DP.FORCE_MODEL_ENV] = "nonsense"
c.eq("an unknown model name is ignored", DP.forced_model(), None)
os.environ.pop(DP.FORCE_MODEL_ENV)
c.eq("no override means no forced model", DP.forced_model(), None)


class FakeDevice:
    path = "/dev/null"


os.environ[DP.FORCE_MODEL_ENV] = "live-s"
try:
    forced, _ = DP.DeviceProfile.detect(FakeDevice())
    c.eq("detect honours the override over the PID", forced.model, DP.MODEL_LIVE_S)
finally:
    os.environ.pop(DP.FORCE_MODEL_ENV)

sys.exit(c.done())
