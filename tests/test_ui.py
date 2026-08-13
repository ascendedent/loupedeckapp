"""Drives the real QML in an offscreen window.

Everything else here tests the core with no Qt involved. This one exists for
the last hop the core cannot cover: whether a control in Main.qml is actually
wired to the backend slot it is supposed to call. Key events go through Qt to
the offscreen window, so nothing reaches the desktop, no other application can
receive them, and no device is opened (Backend does not connect until start()).
"""
import os
import sys
import tempfile

from _harness import Checks

tmp = tempfile.mkdtemp()
os.environ["LOUPEDECKAPP_CONFIG_DIR"] = os.path.join(tmp, "config")
# Forced, not defaulted: a test must never put a window on the desktop.
os.environ["QT_QPA_PLATFORM"] = "offscreen"

c = Checks()

try:
    from PySide6.QtCore import QUrl, Qt
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtTest import QTest
except ImportError as e:                       # no Qt here: the rest still runs
    print("skipping UI checks: %s" % e)
    sys.exit(0)

import app_paths                                                  # noqa: E402
from DeviceProfile import WS_KEYS                                 # noqa: E402
from qml_app import Backend                                       # noqa: E402

app = QGuiApplication(["ui-check"])
backend = Backend()                            # not start()ed: no device opened
engine = QQmlApplicationEngine()
engine.rootContext().setContextProperty("backend", backend)
engine.load(QUrl.fromLocalFile(
    app_paths.asset_path(os.path.join("qml", "Main.qml"))))

roots = engine.rootObjects()
c.eq("Main.qml loads", bool(roots), True)
if not roots:
    sys.exit(c.done())

window = roots[0]


def find(name):
    return window.findChild(object, name)


# -- first run ---------------------------------------------------------------
# A fresh config directory is a first run, so the setup dialog should be up
# already. It is modal, which is why it has to be closed before anything below
# can send a key to the window.
setup = find("setupDialog")
c.eq("the setup dialog exists", setup is not None, True)
c.eq("and opens by itself on a first run", setup.property("opened"), True)
c.eq("opening it counts as seen", backend.setupFirstRun, False)
setup.setProperty("visible", False)
c.eq("it closes", setup.property("opened"), False)


# -- the workspace name field ------------------------------------------------
backend.showWorkspace(WS_KEYS[4])
c.eq("selecting a workspace makes it the current one",
     backend.selectedWs, WS_KEYS[4])
c.eq("and selects it for editing", backend.selectedControl, WS_KEYS[4])
c.eq("the inspector titles it by its number, not the firmware key name",
     backend.selectedLabel, "Workspace 5")

field = find("wsInspectorName")
c.eq("the name field exists", field is not None, True)
if field is not None:
    field.setProperty("text", "Editing")
    field.editingFinished.emit()               # what leaving the field does
    c.eq("typing a name reaches the workspace",
         backend.workspaceNameOf(WS_KEYS[4]), "Editing")
    c.eq("the header follows it", backend.workspaceLabel, "Editing")
    c.eq("naming stages an unsaved change", backend.dirty, True)

    field.setProperty("text", "")
    field.editingFinished.emit()
    c.eq("clearing it goes back to the number",
         backend.workspaceLabel, "Workspace 5")

# -- keyboard shortcuts ------------------------------------------------------
QTest.keyClick(window, Qt.Key_1, Qt.ControlModifier)
c.eq("Ctrl+1 switches to the first workspace", backend.selectedWs, WS_KEYS[0])
QTest.keyClick(window, Qt.Key_6, Qt.ControlModifier)
c.eq("Ctrl+6 switches to the sixth", backend.selectedWs, WS_KEYS[5])

QTest.keyClick(window, Qt.Key_Escape)
c.eq("Escape clears the selection", backend.selectedControl, "")

search = find("librarySearch")
QTest.keyClick(window, Qt.Key_F, Qt.ControlModifier)
c.eq("Ctrl+F puts the cursor in the search box",
     search is not None and search.property("activeFocus"), True)

# Editing keys belong to whatever has focus. A Shortcut is application-wide, so
# without the guard in Main.qml this Ctrl+C would copy a device control instead
# of the text in the box. Keys go to the window; Qt routes them to the focused
# item, which is what makes this a real test of the guard.
backend.selectControl("tb11")
QTest.keyClick(window, Qt.Key_C, Qt.ControlModifier)
c.eq("Ctrl+C while typing does not copy the selected control",
     backend.canPaste, False)

search.setProperty("focus", False)   # release it back to the window
c.eq("focus can leave the search box",
     search is not None and not search.property("activeFocus"), True)
QTest.keyClick(window, Qt.Key_C, Qt.ControlModifier)
c.eq("Ctrl+C outside a text field copies the control", backend.canPaste, True)

# -- tray / close behaviour --------------------------------------------------
# Offscreen has no tray, which is the case worth pinning: hiding the window
# with nothing to restore it from would strand the app.
c.eq("no tray offscreen", backend.traySupported, False)
c.eq("so closing the window cannot mean hiding it", backend.closeToTray, False)
c.eq("and starting hidden is off too", backend.startHidden, False)

c.eq("the window reports itself visible", backend.windowVisible, True)
backend.setWindowVisible(False)
c.eq("and follows what QML tells it", backend.windowVisible, False)
backend.setWindowVisible(True)

# Quit from the tray with a draft open: it must ask, not take. The window comes
# back (it may have been hidden) and the same dialog as a manual close opens.
close_dialog = find("closeDialog")
c.eq("the unsaved-changes dialog exists", close_dialog is not None, True)
c.eq("it starts closed", close_dialog.property("opened"), False)

backend.setWorkspaceName(WS_KEYS[0], "draft")     # anything to make it dirty
c.eq("there is now an unsaved change", backend.dirty, True)
backend.quitRequested.emit()
c.eq("quitting from the tray with a draft asks first",
     close_dialog.property("opened"), True)
c.eq("and puts the window back on screen so the question is visible",
     backend.windowVisible, True)

backend.revert()
c.eq("reverting clears the draft", backend.dirty, False)

# -- preferences popup -------------------------------------------------------
prefs = find("prefsPopup")
c.eq("the preferences popup exists", prefs is not None, True)
if prefs is not None:
    c.eq("it starts closed", prefs.property("opened"), False)
    prefs.setProperty("visible", True)
    c.eq("and opens", prefs.property("opened"), True)
    prefs.setProperty("visible", False)

# Brightness moved in there when the top bar ran out of room, so it has to
# still reach the device settings from its new home.
before = backend.brightness
backend.setBrightness(70)
c.eq("brightness is settable from preferences", backend.brightness, 70)
backend.setBrightness(before)

backend.shutdown()
window.close()

# Leave without unwinding. Python would otherwise collect the Backend while the
# QML engine is still live, every binding would re-evaluate against a null
# context property, and a hundred "property of null" lines would bury the
# results above. Nothing here needs teardown: the watcher is stopped and no
# device was ever opened.
rc = c.done()
sys.stdout.flush()
os._exit(rc)
