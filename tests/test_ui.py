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
# Autostart writes under XDG_CONFIG_HOME. Redirect it too, or toggling the
# switch below would install a real entry into the developer's session.
os.environ["XDG_CONFIG_HOME"] = os.path.join(tmp, "config")
# Forced, not defaulted: a test must never put a window on the desktop.
os.environ["QT_QPA_PLATFORM"] = "offscreen"

c = Checks()

try:
    from PySide6.QtCore import QMetaObject, QUrl, Qt
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

# -- empty states ------------------------------------------------------------
hint = find("emptyMenuHint")
c.eq("the empty-menu hint exists", hint is not None, True)
c.eq("and follows whether anything is bound",
     hint.property("visible"), backend.menuEmpty)

backend.selectControl("tb12")
backend.setActionSlot("tb12", "text", "hello")
c.eq("binding a key means the menu is no longer empty", backend.menuEmpty, False)
c.eq("so the hint goes away", hint.property("visible"), False)
backend.setActionSlot("tb12", "none", "")

# The CT's labelled buttons are wired by default, so counting them would mean
# this hint never appeared on the device it was written for.
c.eq("default button bindings do not count as content", backend.menuEmpty, True)
c.eq("and the hint is back", hint.property("visible"), True)

lib_empty = find("libraryEmpty")
c.eq("the library empty state exists", lib_empty is not None, True)
c.eq("it is hidden while there are matches", lib_empty.property("visible"), False)
if search is not None:
    search.setProperty("text", "zzzznotanaction")
    c.eq("a search that matches nothing says so",
         lib_empty.property("visible"), True)
    c.eq("and the search really found nothing",
         len(backend.filterLibrary("zzzznotanaction")), 0)
    search.setProperty("text", "")
    c.eq("clearing the search brings the list back",
         lib_empty.property("visible"), False)

prof_empty = find("profilesEmpty")
c.eq("the profiles empty state exists", prof_empty is not None, True)
c.eq("hidden while profiles exist",
     prof_empty.property("visible"), len(backend.profiles) == 0)

# -- toasts ------------------------------------------------------------------
toasts = find("toastArea")
c.eq("the toast area exists", toasts is not None, True)


def toast_texts():
    """Text of every toast currently up."""
    raw = toasts.property("toastTexts") or ""
    return raw.split("\n") if raw else []


QMetaObject.invokeMethod(toasts, "clearToasts")
c.eq("the area can be cleared", toast_texts(), [])

backend.notify.emit("Saved to work")
c.eq("a notification becomes a toast", toast_texts(), ["Saved to work"])

# Pressing Save twice should not stack two identical lines.
backend.notify.emit("Saved to work")
c.eq("a repeat re-times the one already up", toast_texts(), ["Saved to work"])

backend.notify.emit("Copied Touch key 1,1")
c.eq("a different one is added",
     toast_texts(), ["Saved to work", "Copied Touch key 1,1"])

# Four at once would cover the device mirror.
for i in range(3):
    backend.notify.emit("message %d" % i)
c.eq("no more than three are kept", len(toast_texts()), 3)
c.eq("and the newest survive", toast_texts()[-1], "message 2")

backend.notify.emit("")
c.eq("an empty message is not a toast", len(toast_texts()), 3)

# The slots that raise them: this is what makes the signal worth having.
before = len(toast_texts())
backend.save()
c.eq("saving says so", any("Saved" in t for t in toast_texts()), True)

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

# Autostart writes into XDG_CONFIG_HOME, which points at this test's temp
# directory, so toggling it here cannot touch the real session.
auto = find("autostartSwitch")
c.eq("the autostart switch exists", auto is not None, True)
if auto is not None:
    c.eq("it starts off", backend.autostartEnabled, False)
    c.eq("turning it on reports no error", backend.setAutostart(True), "")
    c.eq("and it reads as on", backend.autostartEnabled, True)
    c.eq("pointing at this copy", backend.autostartStale, False)
    c.eq("turning it off again", backend.setAutostart(False), "")
    c.eq("leaves nothing behind", backend.autostartEnabled, False)

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
