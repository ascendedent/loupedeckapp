"""Which profile the app opens with.

A first run used to show a blank device and a profile list you had to know to
click. What is checked here is the order of preference, because getting it
wrong is either "your work is gone" (opening the wrong one) or "nothing
happened" (opening none).
"""
import json
import os
import sys
import tempfile

from _harness import Checks

tmp = tempfile.mkdtemp()
os.environ["LOUPEDECKAPP_CONFIG_DIR"] = os.path.join(tmp, "config")
os.environ["XDG_CONFIG_HOME"] = os.path.join(tmp, "config")
os.environ["QT_QPA_PLATFORM"] = "offscreen"

c = Checks()

try:
    from PySide6.QtGui import QGuiApplication
except ImportError as e:
    print("skipping: %s" % e)
    sys.exit(0)

import app_paths                                                  # noqa: E402

app = QGuiApplication(["startup-check"])

from qml_app import Backend                                       # noqa: E402

backend = Backend()

available = app_paths.list_profiles()
c.eq("the shipped profiles are visible",
     "Starter" in available and "testbothactions" in available, True)

# -- first run ---------------------------------------------------------------
c.eq("nothing has been opened before", backend._settings.last_profile, "")
c.eq("so a first run opens the starter",
     backend._startup_profile(), "Starter")

# -- afterwards --------------------------------------------------------------
backend.loadProfile("testbothactions")
c.eq("opening one records it",
     backend._settings.last_profile, "testbothactions")
c.eq("and it is what the next launch would open",
     backend._startup_profile(), "testbothactions")
c.eq("the choice survives a restart",
     Backend()._startup_profile(), "testbothactions")

# -- a profile that has gone away --------------------------------------------
backend._settings.last_profile = "deleted-by-hand"
c.eq("a remembered profile that no longer exists falls back to the starter",
     backend._startup_profile(), "Starter")

# -- neither ------------------------------------------------------------------
real_list = app_paths.list_profiles
app_paths.list_profiles = lambda: ["something-else"]
try:
    c.eq("with no starter, whatever exists is opened",
         backend._startup_profile(), "something-else")
    app_paths.list_profiles = lambda: []
    c.eq("with nothing at all, nothing is opened rather than guessed",
         backend._startup_profile(), "")
finally:
    app_paths.list_profiles = real_list

# -- dynamic mode must not overwrite the memory ------------------------------
# It switches profiles constantly; remembering those would mean the app opens
# wherever you last happened to be looking, not what you chose.
backend._settings.last_profile = "Starter"
backend._ctl.load_profile("testbothactions")      # what dynamic mode calls
c.eq("a switch the user did not make is not remembered",
     backend._settings.last_profile, "Starter")

backend.shutdown()
# Leave without unwinding: Qt objects outliving the interpreter's teardown make
# noise that buries the results. The summary has to be printed and flushed
# before that, or the runner sees no summary at all.
rc = c.done()
sys.stdout.flush()
os._exit(rc)
