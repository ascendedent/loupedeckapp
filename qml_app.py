"""PySide6 + QML front-end (M4).

New UI shell that reuses the decoupled core (DeviceProfile, LdConfiguration,
input_backend, window_watcher, profile_manager) and drives the real device via
DeviceController. Runs alongside the existing PyQt5 app.py during migration.

Run:  QT_QPA_PLATFORM=xcb .venv/bin/python qml_app.py
"""

import os
import sys
import glob
import threading

from PySide6.QtCore import QObject, Property, Signal, Slot, QUrl, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

import window_watcher
from profile_manager import ProfileManager
from device_controller import DeviceController
from DeviceProfile import WHEEL_DISPLAY

APP_DIR = os.path.dirname(os.path.abspath(__file__))


class Backend(QObject):
    stateChanged = Signal()
    selectionChanged = Signal()
    # private cross-thread marshals -> delivered on the Qt main thread
    _marshal = Signal(str)
    _focusSig = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._selected = ""
        self._ctl = DeviceController(on_state=lambda kind: self._marshal.emit(kind))
        self._pm = ProfileManager(os.path.join(APP_DIR, "dynamic_profiles.json"))
        self._watcher = window_watcher.get_watcher(
            on_change=lambda c, t: self._focusSig.emit(c, t))
        self._marshal.connect(self._on_state_main, Qt.QueuedConnection)
        self._focusSig.connect(self._on_focus_main, Qt.QueuedConnection)

    # -- lifecycle ---------------------------------------------------------
    def start(self):
        threading.Thread(target=self._ctl.connect, daemon=True).start()
        if self._pm.dynamic_mode:
            self._watcher.start()

    def shutdown(self):
        self._watcher.stop()
        self._ctl.close()

    def _on_state_main(self, kind):
        self.stateChanged.emit()

    def _on_focus_main(self, wm_class, title):
        if not self._pm.dynamic_mode:
            return
        name = self._pm.resolve(wm_class)
        if name and name != self._ctl.config.profile:
            print("dynamic: %s -> profile '%s'" % (wm_class, name))
            self._ctl.load_profile(name)
            self.stateChanged.emit()

    # -- read properties ---------------------------------------------------
    @Property(str, notify=stateChanged)
    def deviceName(self):
        return self._ctl.profile.display_name

    @Property(bool, notify=stateChanged)
    def connected(self):
        return self._ctl.connected

    @Property(bool, notify=stateChanged)
    def hasWheel(self):
        return self._ctl.profile.has_wheel

    @Property(int, notify=stateChanged)
    def columns(self):
        return self._ctl.profile.columns

    @Property(int, notify=stateChanged)
    def rows(self):
        return self._ctl.profile.rows

    @Property(bool, notify=stateChanged)
    def dynamicMode(self):
        return self._pm.dynamic_mode

    @Property(str, notify=stateChanged)
    def activeProfile(self):
        return self._ctl.config.profile or "(none)"

    @Property("QStringList", notify=stateChanged)
    def profiles(self):
        files = glob.glob(os.path.join(APP_DIR, "Profiles", "*.json"))
        return sorted(os.path.splitext(os.path.basename(f))[0] for f in files)

    @Property("QStringList", constant=True)
    def actionCategories(self):
        return ["General", "Adjustments", "Navigation", "Media", "System", "Applications"]

    @Property("QStringList", constant=True)
    def ctExtraButtons(self):
        return list(self._ctl.profile.extra_buttons)

    # -- on-screen mirror of the currently displayed menu ------------------
    def _menu(self):
        """The workspace or submenu whose images/actions are live on the
        device right now. Works before connect too (empty default config)."""
        try:
            return self._ctl.current_menu()
        except Exception:
            return None

    @Property("QVariantMap", notify=stateChanged)
    def keyImages(self):
        """control-key -> file:// URL for every slot with an image (touch
        buttons, side-display cells, wheel), for the DeviceView mirror."""
        menu = self._menu()
        out = {}
        if not menu:
            return out
        for key, path in menu.images.items():
            if not path:
                continue
            ap = path if os.path.isabs(path) else os.path.join(APP_DIR, path)
            out[key] = QUrl.fromLocalFile(ap).toString()
        return out

    @Property("QVariantMap", notify=stateChanged)
    def boundActions(self):
        """control-key -> action summary for every bound (non-'none') control,
        so the mirror can highlight encoders/dial/CT-buttons that do something."""
        menu = self._menu()
        out = {}
        if not menu:
            return out
        for key, action in menu.actions.items():
            if action is not None and getattr(action, "a_type", "none") != "none":
                out[key] = getattr(action, "summary", "") or action.a_type
        return out

    @Property(str, notify=stateChanged)
    def selectedWs(self):
        return self._ctl.selected_ws

    @Property(int, notify=stateChanged)
    def menuDepth(self):
        return len(self._ctl.submenu_stack)

    # -- control selection + action editing (inspector) --------------------
    ACTION_TYPES = ["none", "command", "hotkey", "text", "media"]

    def _slot_defs(self, key):
        """(slot-key, label) pairs a control exposes. Encoders and the dial
        have press + two rotate slots; everything else is a single action."""
        if key.startswith("enc"):
            return [(key, "Press"), (key + "-l", "Rotate ◀"), (key + "-r", "Rotate ▶")]
        if key in ("dial", "dial-l", "dial-r"):
            return [("dial", "Press"), ("dial-l", "Rotate ◀"), ("dial-r", "Rotate ▶")]
        return [(key, "Action")]

    def _label(self, key):
        if key.startswith("tb"):
            return "Touch key %s,%s" % (key[2], key[3])
        if key.startswith("dis"):
            return "Side %s cell %s" % ("left" if key[4] == "L" else "right", key[3])
        if key.startswith("enc"):
            return "Encoder %s%s" % (key[3], key[4])
        if key == "dial":
            return "Dial"
        if key == WHEEL_DISPLAY:
            return "Wheel"
        return "Button %s" % key.upper()

    @Property(str, notify=selectionChanged)
    def selectedControl(self):
        return self._selected

    @Property(str, notify=selectionChanged)
    def selectedLabel(self):
        return self._label(self._selected) if self._selected else ""

    @Property(bool, notify=selectionChanged)
    def selectedHasImage(self):
        k = self._selected
        return bool(k) and (k.startswith("tb") or k.startswith("dis") or k == WHEEL_DISPLAY)

    @Property(str, notify=stateChanged)
    def selectedImage(self):
        if not self._selected:
            return ""
        return self.keyImages.get(self._selected, "")

    @Property("QVariantList", notify=stateChanged)
    def selectedSlots(self):
        """Editor rows for the selected control: slot key, label, current
        action type + value."""
        out = []
        if not self._selected:
            return out
        menu = self._menu()
        for slot, label in self._slot_defs(self._selected):
            act = menu.actions.get(slot) if menu else None
            out.append({
                "slot": slot,
                "label": label,
                "type": getattr(act, "a_type", "none") if act else "none",
                "value": getattr(act, "action", "") if act else "",
            })
        return out

    @Property("QStringList", constant=True)
    def actionTypes(self):
        return list(self.ACTION_TYPES)

    @Slot(str)
    def selectControl(self, key):
        # normalise encoder/dial rotate slots to their base control
        if key.endswith("-l") or key.endswith("-r"):
            key = key[:-2]
        self._selected = key
        self.selectionChanged.emit()
        self.stateChanged.emit()

    @Slot()
    def deselect(self):
        self._selected = ""
        self.selectionChanged.emit()
        self.stateChanged.emit()

    @Slot(str, str, str)
    def setActionSlot(self, slot_key, a_type, value):
        self._ctl.set_action(slot_key, a_type, value)
        self._ctl.save()
        self.stateChanged.emit()

    @Slot(str, str)
    def setImage(self, key, file_url):
        path = QUrl(file_url).toLocalFile() if file_url else ""
        self._ctl.set_image(key, path)
        self._ctl.save()
        self.stateChanged.emit()

    @Slot(str)
    def clearImage(self, key):
        self._ctl.set_image(key, "")
        self._ctl.save()
        self.stateChanged.emit()

    # -- slots -------------------------------------------------------------
    @Slot(str)
    def loadProfile(self, name):
        self._ctl.load_profile(name)
        self.stateChanged.emit()

    @Slot(bool)
    def setDynamicMode(self, enabled):
        self._pm.set_dynamic_mode(enabled)
        self._pm.save()
        if enabled:
            self._watcher.start()
            cls, ttl = self._watcher.poll_once()
            self._on_focus_main(cls, ttl)
        else:
            self._watcher.stop()
        self.stateChanged.emit()


def main():
    app = QGuiApplication(sys.argv)
    app.setApplicationName("Loupedeck Config")
    engine = QQmlApplicationEngine()
    backend = Backend()
    engine.rootContext().setContextProperty("backend", backend)
    engine.load(QUrl.fromLocalFile(os.path.join(APP_DIR, "qml", "Main.qml")))
    if not engine.rootObjects():
        sys.exit("Failed to load QML")
    app.aboutToQuit.connect(backend.shutdown)
    backend.start()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
