"""The tray menu and the settings behind it.

The icon itself needs a running QApplication and a desktop with a tray, so what
is checked here is the logic around it: the settings that decide whether there
is a tray at all, and the menu built from backend state (with a stand-in
backend, so no device or Qt is involved).
"""
import os
import sys
import tempfile

from _harness import Checks

tmp = tempfile.mkdtemp()
os.environ["LOUPEDECKAPP_CONFIG_DIR"] = os.path.join(tmp, "config")

import settings as settings_mod                                   # noqa: E402
import tray                                                       # noqa: E402

c = Checks()

# -- the settings ------------------------------------------------------------
s = settings_mod.Settings()
c.eq("the tray is on by default", s.tray_enabled, True)
c.eq("and closing the window goes to it", s.close_to_tray, True)
c.eq("but the app does not start hidden", s.start_hidden, False)

s.tray_enabled = False
c.eq("turning the tray off turns off close-to-tray with it", s.close_to_tray, False)
c.eq("and start-hidden, which would otherwise strand the app", s.start_hidden, False)
s.start_hidden = True
c.eq("start-hidden stays off while there is no tray", s.start_hidden, False)
s.tray_enabled = True
c.eq("and comes back when there is", s.start_hidden, True)

s.close_to_tray = False
c.eq("close-to-tray can be off with the tray on", (s.tray_enabled, s.close_to_tray),
     (True, False))

s.save()
c.eq("the choices persist", settings_mod.Settings(s.path).close_to_tray, False)

# -- availability ------------------------------------------------------------
# No QApplication has been constructed here, which is the case that used to
# crash rather than answer.
c.eq("asking with no application running answers no", tray.available(), False)


# -- the menu ----------------------------------------------------------------
class FakeBackend:
    """Only what Tray reads. Deliberately not a Backend: constructing one opens
    settings, a watcher and a controller."""

    def __init__(self):
        self.activeProfile = "default"
        self.profiles = ["default", "work"]
        self.dynamicMode = False
        self.connected = True
        self.dirty = False
        self.windowVisible = True
        self.loaded = []
        self.dynamic_calls = []

    def loadProfile(self, name):
        self.loaded.append(name)
        self.activeProfile = name

    def setDynamicMode(self, enabled):
        self.dynamic_calls.append(enabled)
        self.dynamicMode = enabled


class FakeMenu:
    """Stands in for QMenu. Records what was built."""

    def __init__(self):
        self.entries = []
        self.submenus = []

    def clear(self):
        self.entries = []
        self.submenus = []

    def addAction(self, text):
        act = FakeAction(text)
        self.entries.append(act)
        return act

    def addMenu(self, title):
        sub = FakeMenu()
        sub.title = title
        self.submenus.append(sub)
        self.entries.append(sub)
        return sub

    def addSeparator(self):
        self.entries.append("---")


class FakeAction:
    def __init__(self, text):
        self.text = text
        self.enabled = True
        self.checkable = False
        self.checked = False
        self.handlers = []
        self.triggered = self

    def connect(self, fn):
        self.handlers.append(fn)

    def emit(self, checked=False):
        for fn in self.handlers:
            fn(checked)

    def setEnabled(self, v):
        self.enabled = v

    def setCheckable(self, v):
        self.checkable = v

    def setChecked(self, v):
        self.checked = v


def build(backend):
    """Run Tray.refresh against fakes, without constructing a QSystemTrayIcon."""
    t = tray.Tray.__new__(tray.Tray)
    t._backend = backend
    t._menu = FakeMenu()
    t._on_quit = lambda: quits.append(True)
    t._tray = FakeTrayIcon()
    t.refresh()
    return t


class FakeTrayIcon:
    def __init__(self):
        self.tooltip = ""

    def setToolTip(self, text):
        self.tooltip = text


quits = []
b = FakeBackend()
t = build(b)
labels = [e.text if isinstance(e, FakeAction) else
          (e.title if isinstance(e, FakeMenu) else e) for e in t._menu.entries]
c.eq("the menu leads with the live profile", labels[0], "default")
c.eq("and offers profile, dynamic mode, window and quit",
     [l for l in labels if l != "---"],
     ["default", "Profile", "Dynamic mode", "Hide window", "Quit"])

header = t._menu.entries[0]
c.eq("the profile line is a label, not a button", header.enabled, False)

profiles = t._menu.submenus[0]
c.eq("every profile is listed", [a.text for a in profiles.entries],
     ["default", "work"])
c.eq("the live one is ticked",
     [a.checked for a in profiles.entries], [True, False])

profiles.entries[1].emit()
c.eq("picking one loads it", b.loaded, ["work"])
c.eq("and the tick moves with it",
     [a.checked for a in t._menu.submenus[0].entries], [False, True])

dyn = [e for e in t._menu.entries
       if isinstance(e, FakeAction) and e.text == "Dynamic mode"][0]
c.eq("dynamic mode is a checkbox", dyn.checkable, True)
dyn.emit(True)
c.eq("toggling it reaches the backend", b.dynamic_calls, [True])

# -- state the tooltip and labels follow -------------------------------------
b.dirty = True
b.windowVisible = False
b.connected = False
t.refresh()
labels = [e.text if isinstance(e, FakeAction) else
          (e.title if isinstance(e, FakeMenu) else e) for e in t._menu.entries]
c.eq("an unsaved draft is marked", labels[0], "work *")
c.eq("a hidden window offers to come back",
     "Show window" in labels, True)
c.eq("the tooltip says when the device is not there",
     "not connected" in t._tray.tooltip, True)

sys.exit(c.done())
