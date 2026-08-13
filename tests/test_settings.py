"""App preferences: persistence, clamping, and brightness on the device."""
import json
import os
import shutil
import sys
import tempfile

from _harness import Checks

tmp = tempfile.mkdtemp(prefix="ldset-")
os.environ["LOUPEDECKAPP_CONFIG_DIR"] = os.path.join(tmp, "config")

import app_paths                                    # noqa: E402
import settings as settings_mod                     # noqa: E402
from device_controller import DeviceController      # noqa: E402

c = Checks()
path = os.path.join(tmp, "settings.json")

# -- defaults and persistence --------------------------------------------------
st = settings_mod.Settings(path)
c.eq("a missing file gives defaults", st.brightness,
     settings_mod.DEFAULTS["brightness"])
st.brightness = 70
st.save()
c.eq("saving writes the file", os.path.exists(path), True)
c.eq("it round-trips", settings_mod.Settings(path).brightness, 70)

# -- clamping and garbage ------------------------------------------------------
st.brightness = 500
c.eq("above range clamps to 100", st.brightness, 100)
st.brightness = -20
c.eq("below range clamps to 0", st.brightness, 0)
st.brightness = "bright"
c.eq("garbage is ignored rather than stored", st.brightness, 0)

json.dump({"brightness": "nonsense"}, open(path, "w"))
c.eq("a garbage value in the file falls back to the default",
     settings_mod.Settings(path).brightness, settings_mod.DEFAULTS["brightness"])

open(path, "w").write("{ not json")
c.eq("an unreadable file falls back to defaults",
     settings_mod.Settings(path).brightness, settings_mod.DEFAULTS["brightness"])

# Unknown keys must survive: a newer build's preference should not be dropped
# by an older one loading and re-saving the file.
json.dump({"brightness": 30, "future_option": "keep me"}, open(path, "w"))
st = settings_mod.Settings(path)
st.brightness = 50
st.save()
c.eq("an unknown key survives a load/save round-trip",
     json.load(open(path)).get("future_option"), "keep me")
c.eq("alongside the changed one", json.load(open(path))["brightness"], 50)

# -- applied to the device -----------------------------------------------------
sent = []


class FakeDevice:
    DECK_TYPE = "LoupedeckLive"
    path = None
    reading_thread = None

    def set_brightness(self, v): sent.append(v)
    def reset(self): pass
    def set_button_color(self, *a): pass
    def stop(self): pass


dc = DeviceController()
c.eq("the controller starts at the default brightness", dc.brightness, 40)

dc.set_brightness(80)
c.eq("setting it with no device still remembers", dc.brightness, 80)
c.eq("and sends nothing", sent, [])

dc.device = FakeDevice()
dc.set_brightness(60)
c.eq("with a device it is sent", sent, [60])
c.eq("and remembered", dc.brightness, 60)

dc.set_brightness(999)
c.eq("out-of-range is clamped before sending", sent[-1], 100)
dc.set_brightness("dim")
c.eq("garbage sends nothing more", len(sent), 2)

# The point of remembering: a reconnect must not silently revert to 40.
del sent[:]
dc.init_device()
c.eq("init_device re-applies the remembered brightness", sent, [100])

dc.close()
shutil.rmtree(tmp, ignore_errors=True)
sys.exit(c.done())
