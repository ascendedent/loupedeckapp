"""Side displays as three buttons or as one image (schema v8).

The part worth checking is the routing: in single mode a touch anywhere on the
strip has to resolve to the cell that carries the image and the action, or the
strip shows one thing and does another.
"""
import os
import sys
import tempfile

from _harness import Checks, controller

tmp = tempfile.mkdtemp()
os.environ["LOUPEDECKAPP_CONFIG_DIR"] = os.path.join(tmp, "config")

from LdConfiguration import (LdWorkspace, SCHEMA_VERSION,          # noqa: E402
                             SIDE_LAYOUTS, DEFAULT_SIDE_LAYOUT)

c = Checks()

# -- the model ---------------------------------------------------------------
ws = LdWorkspace()
c.eq("strips start as separate cells", ws.side_layout, {"L": "cells", "R": "cells"})
c.eq("the layouts are the two that exist", sorted(SIDE_LAYOUTS), ["cells", "single"])
c.eq("this took a schema bump", SCHEMA_VERSION >= 8, True)

ws.side_layout["L"] = "single"
back = LdWorkspace.from_JSON(ws.to_JSON())
c.eq("the choice round-trips", back.side_layout, {"L": "single", "R": "cells"})

older = {k: v for k, v in ws.to_JSON().items() if k != "side_layout"}
c.eq("a pre-v8 profile loads as cells everywhere",
     LdWorkspace.from_JSON(older).side_layout, DEFAULT_SIDE_LAYOUT)

junk = ws.to_JSON()
junk["side_layout"] = {"L": "nonsense", "X": "single"}
loaded = LdWorkspace.from_JSON(junk).side_layout
c.eq("a hand-edited layout cannot smuggle in an unknown mode",
     loaded, DEFAULT_SIDE_LAYOUT)

# -- the controller ----------------------------------------------------------
dc, workspace = controller()
c.eq("it reads cells by default", dc.side_layout("L"), "cells")

dc.dirty = False
dc.set_side_layout("L", "single")
c.eq("setting it takes", dc.side_layout("L"), "single")
c.eq("and stages an unsaved change", dc.dirty, True)
c.eq("the other side is untouched", dc.side_layout("R"), "cells")

dc.set_side_layout("L", "nonsense")
c.eq("an unknown mode is ignored", dc.side_layout("L"), "single")
dc.set_side_layout("X", "cells")
c.eq("so is a side that does not exist", dc.side_layout("L"), "single")

# -- touch routing -----------------------------------------------------------
# The cell height on a CT/Live is 90px, so y=100 is the second cell and y=200
# the third.
dc.set_side_layout("L", "cells")
c.eq("in cells mode the row follows the touch",
     [dc.td_pos_to_display_name(10, y) for y in (10, 100, 200)],
     ["dis1L", "dis2L", "dis3L"])

dc.set_side_layout("L", "single")
c.eq("in single mode every touch is the first cell",
     [dc.td_pos_to_display_name(10, y) for y in (10, 100, 200)],
     ["dis1L", "dis1L", "dis1L"])
c.eq("and the other side still splits",
     [dc.td_pos_to_display_name(500, y) for y in (10, 200)],
     ["dis1R", "dis3R"])

# -- rendering ---------------------------------------------------------------
# No device here, so what is checked is which drawing call would be made.
drawn = []
dc.set_side_layout("L", "single")
dc.set_side_layout("R", "cells")
workspace = dc.current_menu()
for key in ("dis1L", "dis2L", "dis3L", "dis1R", "dis2R", "dis3R"):
    workspace.images[key] = "/nonexistent.png"

dc.device = object()          # truthy: render_workspace only checks presence
dc.set_img_to_touchdisplay = lambda *a, **k: drawn.append(("cells", a[1], a[2]))
dc.set_img_to_side_display = lambda *a, **k: drawn.append(("single", a[1]))
dc.set_img_to_touchbutton = lambda *a, **k: None
dc.set_img_to_wheel = lambda *a, **k: None
dc.apply_leds = lambda ws: None


class FakeDevice:
    def reset(self):
        pass


dc.device = FakeDevice()
dc.render_workspace(workspace)
dc.device = None

c.eq("the single side is drawn once, as a whole strip",
     [d for d in drawn if d[0] == "single"], [("single", "L")])
c.eq("and the cells side is drawn once per cell",
     sorted(d[2] for d in drawn if d[0] == "cells" and d[1] == "R"), [1, 2, 3])
c.eq("nothing draws the hidden cells of the single side",
     [d for d in drawn if d[0] == "cells" and d[1] == "L"], [])

# -- the size hint -----------------------------------------------------------
# Told the cell size for a strip-wide image, people go and crop a 60x90 picture
# for a 60x270 space.
os.environ["QT_QPA_PLATFORM"] = "offscreen"
try:
    from PySide6.QtGui import QGuiApplication
except ImportError:
    print("skipping the size-hint checks: no Qt")
else:
    app = QGuiApplication(["side-check"])
    from qml_app import Backend

    backend = Backend()
    from DeviceProfile import DeviceProfile, MODEL_CT
    backend._ctl.profile = DeviceProfile.for_model(MODEL_CT)

    backend.selectControl("dis1L")
    backend.setSideLayout("L", "cells")
    c.eq("a cell asks for a cell-sized image", backend.selectedImageDims, "60 × 90 px")
    backend.setSideLayout("L", "single")
    c.eq("a whole strip asks for a strip-sized one",
         backend.selectedImageDims, "60 × 270 px")
    backend.selectControl("tb11")
    c.eq("a touch key is unaffected", backend.selectedImageDims, "90 × 90 px")
    backend.shutdown()

rc = c.done()
sys.stdout.flush()
os._exit(rc)
