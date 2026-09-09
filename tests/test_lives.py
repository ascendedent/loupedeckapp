"""The Live S patch: where a key image lands, and which key a touch hits.

The vendored library knows one screen layout, the Loupedeck Live's, and a Live S
does not have it: no side screens, one 480-wide screen, five 90px keys starting
15px in. The first Live S report (issue #3) was of a device drawing every key
two thirds of a key to the right and reporting the wrong one when touched.

None of this needs hardware. The arithmetic is the whole bug.
"""
import sys

from _harness import Checks

import device_lib
import live_s_support
from DeviceProfile import DeviceProfile, MODEL_CT, MODEL_LIVE_S

c = Checks()

if not device_lib.available():
    print("the device library is not installed; nothing to patch")
    sys.exit(0)

live_s = DeviceProfile.for_model(MODEL_LIVE_S)
ct = DeviceProfile.for_model(MODEL_CT)


class FakeDevice:
    """Enough of a device to record what the patch asks it to do."""

    def __init__(self):
        self.touches = {}
        self.handlers = {}
        self.callback = None
        self.drawn = []
        self.events = []

    def draw_image(self, image, display, width, height, x, y, **kw):
        self.drawn.append((display, x, y, width, height))

    def record(self, _dev, message):
        self.events.append(message)


def touch_buffer(x, y, finger=0):
    """The five bytes the library's touch handlers read, after the header."""
    return bytes([0]) + x.to_bytes(2, "big") + y.to_bytes(2, "big") + bytes([finger])


# -- it only touches a Live S ------------------------------------------------
other = FakeDevice()
c.eq("installing on a CT does nothing", live_s_support.install(other, ct), False)
c.eq("and leaves its handlers alone", other.handlers, {})

dev = FakeDevice()
c.eq("installing on a Live S patches it",
     live_s_support.install(dev, live_s), True)
dev.callback = dev.record

# -- the screen the library now believes in ----------------------------------
displays = device_lib.module.DISPLAYS
c.eq("the centre screen is the whole framebuffer",
     (displays["center"][device_lib.module.KW_WIDTH],
      displays["center"][device_lib.module.KW_HEIGHT],
      displays["center"][device_lib.module.KW_OFFSET]), (480, 270, 0))
c.eq("and the side screens this model has not are gone",
     sorted(displays.keys()), ["center"])

# -- where a key image lands -------------------------------------------------
# Five to a row from x=15, not four from x=60. Every one of these was wrong
# before, which is why each physical key showed part of two images.
for index, want in ((0, (15, 0)), (4, (375, 0)), (5, (15, 90)),
                    (9, (375, 90)), (10, (15, 180)), (14, (375, 180))):
    dev.drawn = []
    dev.set_key_image(index, object())
    c.eq("key %d draws at %r" % (index, want),
         dev.drawn, [("center", want[0], want[1], 90, 90)])

dev.drawn = []
dev.set_key_image(15, object())
c.eq("a key this model does not have draws nothing", dev.drawn, [])
dev.set_key_image("left", object())
c.eq("and neither does a side screen it does not have", dev.drawn, [])

# -- which key a touch hits --------------------------------------------------
move = dev.handlers[device_lib.module.HEADERS["TOUCH"]]
end = dev.handlers[device_lib.module.HEADERS["TOUCH_END"]]


def press(x, y, finger=0):
    dev.events = []
    move(touch_buffer(x, y, finger))
    end(touch_buffer(x, y, finger))
    return [(e["action"], e["key"]) for e in dev.events]


c.eq("the first key starts at x=15", press(20, 10), [("touchstart", 0), ("touchend", 0)])
c.eq("and ends before x=105", press(104, 10)[0], ("touchstart", 0))
c.eq("x=105 is the second key", press(105, 10)[0], ("touchstart", 1))
c.eq("the last column is the fifth, not a right-hand screen",
     press(460, 10)[0], ("touchstart", 4))
c.eq("the second row starts at y=90", press(20, 90)[0], ("touchstart", 5))
c.eq("and the bottom right key is 14", press(460, 260)[0], ("touchstart", 14))

c.eq("the dead strip on the left is not a control", press(10, 10), [])
c.eq("nor the one on the right", press(470, 10), [])

# A finger that leaves the keys still has to be forgotten, or the next press on
# that slot is reported as a move and never fires anything.
dev.events = []
move(touch_buffer(20, 10, 3))
end(touch_buffer(2, 10, 3))
c.eq("a drag off the edge still releases its finger", dev.touches, {})
c.eq("a second press on the same finger starts again",
     press(20, 10, 3)[0], ("touchstart", 0))

# Holding is a move, not a second press: the controller acts on touchstart, and
# a repeat would fire the binding twice for one finger.
dev.events = []
move(touch_buffer(20, 10, 1))
move(touch_buffer(22, 12, 1))
c.eq("holding reports one start and then moves",
     [e["action"] for e in dev.events], ["touchstart", "touchmove"])
end(touch_buffer(22, 12, 1))

# -- what a profile written on another model renders --------------------------
# Profiles store the widest grid and all eight workspaces so a file moves
# between models. What crosses over has to be filtered on the way to the
# device: the first Live S report showed a CT profile's side strips painted
# over that model's outer key columns, because the library maps its "left" and
# "right" screens onto the first and last 60 pixels of the one screen a Live S
# has.
from device_controller import DeviceController                    # noqa: E402


class Recorder(DeviceController):
    def __init__(self, profile):
        self.profile = profile
        self.drawn = []

    def set_img_to_touchbutton(self, path, keycode, label=None, bg_color=None):
        self.drawn.append(("key", keycode))

    def set_img_to_touchdisplay(self, *a, **kw):
        self.drawn.append(("strip", a[1:3]))

    def set_img_to_side_display(self, *a, **kw):
        self.drawn.append(("strip", a[1]))

    def set_img_to_wheel(self, *a, **kw):
        self.drawn.append(("wheel", None))

    def apply_leds(self, ws):
        pass

    def side_layout(self, side, ws=None):
        return "cells"

    def effective_label(self, ws, key):
        return None

    def effective_bg(self, ws, key):
        return None


class FakeWorkspace:
    def __init__(self, keys):
        self.images = {k: "x.png" for k in keys}


class DeviceStub:
    def reset(self):
        pass


ct_profile_keys = ["tb11", "tb34", "dis1L", "dis3R", "wheel"]
rec = Recorder(live_s)
rec.device = DeviceStub()
rec.render_workspace(FakeWorkspace(ct_profile_keys))
c.eq("a CT profile draws no side strips on a Live S",
     [d for d in rec.drawn if d[0] == "strip"], [])
c.eq("and no wheel", [d for d in rec.drawn if d[0] == "wheel"], [])
c.eq("its keys land on the five-wide grid",
     [d[1] for d in rec.drawn if d[0] == "key"], [0, 13])

# And the other way: a Live S profile's fifth column is not a key on a CT, and
# its index there is the first key of the next row.
rec = Recorder(ct)
rec.device = DeviceStub()
rec.render_workspace(FakeWorkspace(["tb11", "tb15", "tb25", "tb35"]))
c.eq("a Live S profile's fifth column is skipped on a CT",
     [d[1] for d in rec.drawn if d[0] == "key"], [0])

sys.exit(c.done())
