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

APP_DIR = os.path.dirname(os.path.abspath(__file__))


class Backend(QObject):
    stateChanged = Signal()
    # private cross-thread marshals -> delivered on the Qt main thread
    _marshal = Signal(str)
    _focusSig = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
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
