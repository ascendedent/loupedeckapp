"""Unsaved-edit handling: a draft must never be discarded without asking."""
import os
import shutil
import sys
import tempfile

from _harness import Checks

tmp = tempfile.mkdtemp(prefix="lddraft-")
os.environ["LOUPEDECKAPP_CONFIG_DIR"] = os.path.join(tmp, "config")

import app_paths                                    # noqa: E402
from LdConfiguration import LdConfiguration         # noqa: E402

c = Checks()

# Two profiles to switch between, in an isolated config dir.
for name in ("alpha", "beta"):
    cfg = LdConfiguration(profile=name)
    cfg.save(name)

from PySide6.QtGui import QGuiApplication           # noqa: E402
app = QGuiApplication.instance() or QGuiApplication(["test"])
import profile_manager                             # noqa: E402
from qml_app import Backend                        # noqa: E402

b = Backend()
b._pm = profile_manager.ProfileManager(os.path.join(tmp, "dyn.json"))
get = lambda n: type(b).__dict__[n].fget(b)

b.loadProfile("alpha")
c.eq("loaded the first profile", get("activeProfile"), "alpha")
c.eq("a freshly loaded profile is clean", get("dirty"), False)

# -- dynamic switching with a clean draft --------------------------------------
b._pm.set_binding("firefox", "beta")
b._pm.set_dynamic_mode(True)
b._on_focus_main("firefox", "")
c.eq("a clean profile switches immediately", get("activeProfile"), "beta")
c.eq("nothing is left pending", get("pendingProfile"), "")

# -- dynamic switching with unsaved edits --------------------------------------
b.loadProfile("alpha")
b.setActionSlot("tb11", "hotkey", "ctrl+j")
c.eq("editing marks the profile dirty", get("dirty"), True)

b._on_focus_main("firefox", "")
c.eq("a dirty profile is NOT switched away from", get("activeProfile"), "alpha")
c.eq("the switch is held, not dropped", get("pendingProfile"), "beta")
c.eq("the edit survives",
     b._ctl.current_menu().actions["tb11"].action, "ctrl+j")

# repeated focus events must not spam or lose the held switch
b._on_focus_main("firefox", "")
c.eq("a repeated focus event changes nothing", get("pendingProfile"), "beta")

# -- resolving the draft applies the held switch -------------------------------
b.save()
c.eq("saving applies the held switch", get("activeProfile"), "beta")
c.eq("and clears it", get("pendingProfile"), "")
c.eq("saving cleared dirty", get("dirty"), False)

reloaded = LdConfiguration(); reloaded.load("alpha")
c.eq("the edit was written to disk",
     reloaded.workspaces[0].actions["tb11"].action, "ctrl+j")

# -- discarding also applies it ------------------------------------------------
b.loadProfile("alpha")
b.setActionSlot("tb12", "hotkey", "ctrl+k")
b._on_focus_main("firefox", "")
c.eq("held again", get("pendingProfile"), "beta")
b.revert()
c.eq("reverting applies the held switch too", get("activeProfile"), "beta")
c.eq("and clears it", get("pendingProfile"), "")
reloaded = LdConfiguration(); reloaded.load("alpha")
c.eq("the discarded edit never reached disk",
     reloaded.workspaces[0].actions["tb12"].a_type, "none")

# -- a switch to the profile already loaded is not "held" ----------------------
b.loadProfile("beta")
b.setActionSlot("tb13", "hotkey", "ctrl+l")
b._on_focus_main("firefox", "")        # firefox maps to beta, already active
c.eq("no hold when the target is already active", get("pendingProfile"), "")
c.eq("and the draft is untouched", get("dirty"), True)

# -- our own window is never offered as a binding target ----------------------
# The class cannot identify us: it is "Loupedeck Config" under XWayland but
# "python3" on native Wayland. The PID can.
class FakeWatcher:
    last_pid = 0
    def start(self): pass
    def stop(self): pass
    def poll_once(self): return ("", "")

b._watcher = FakeWatcher()
b._last_app = ""

b._watcher.last_pid = os.getpid()
b._on_focus_main("python3", "Loupedeck Config")
c.eq("our own window is skipped even when the class looks foreign",
     get("focusedApp"), "")

b._on_focus_main("Loupedeck Config", "Loupedeck Config")
c.eq("and skipped by name too, when the pid is unavailable", get("focusedApp"), "")

b._watcher.last_pid = os.getpid() + 1
b._on_focus_main("firefox", "a page")
c.eq("another app is recorded", get("focusedApp"), "firefox")

b._watcher.last_pid = 0            # pid unknown: fall back to the name check
b._on_focus_main("python3", "some other python app")
c.eq("with no pid, an unrelated python app is not mistaken for us",
     get("focusedApp"), "python3")

b.revert()
b._ctl.close()
shutil.rmtree(tmp, ignore_errors=True)
sys.exit(c.done())
