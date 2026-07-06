"""PySide6 + QML front-end (M4).

New UI shell that reuses the already-decoupled core (DeviceProfile, LdConfiguration,
input_backend, window_watcher, profile_manager). It runs *alongside* the existing
PyQt5 app during the migration — app.py is untouched.

Run:  QT_QPA_PLATFORM=xcb .venv/bin/python qml_app.py

The Backend object is exposed to QML as `backend` and carries device/profile
info. Slice 1 is layout + read-only data; device I/O and editing wire up next.
"""

import os
import sys
import glob

from PySide6.QtCore import QObject, Property, Signal, Slot, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

from DeviceProfile import DeviceProfile, MODEL_CT
from profile_manager import ProfileManager

APP_DIR = os.path.dirname(os.path.abspath(__file__))


class Backend(QObject):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        # Slice 1: assume the CT profile for the mock (this machine's device)
        # without opening the serial port; live detection wires up in a later
        # increment.
        self._profile = DeviceProfile.for_model(MODEL_CT)
        self._pm = ProfileManager(os.path.join(APP_DIR, "dynamic_profiles.json"))
        self._connected = False

    @Property(str, notify=changed)
    def deviceName(self):
        return self._profile.display_name

    @Property(bool, notify=changed)
    def connected(self):
        return self._connected

    @Property(bool, notify=changed)
    def hasWheel(self):
        return self._profile.has_wheel

    @Property(int, notify=changed)
    def columns(self):
        return self._profile.columns

    @Property(int, notify=changed)
    def rows(self):
        return self._profile.rows

    @Property(bool, notify=changed)
    def dynamicMode(self):
        return self._pm.dynamic_mode

    @Property(str, notify=changed)
    def activeProfile(self):
        return self._pm.default_profile or "(none)"

    @Property("QStringList", notify=changed)
    def profiles(self):
        files = glob.glob(os.path.join(APP_DIR, "Profiles", "*.json"))
        return sorted(os.path.splitext(os.path.basename(f))[0] for f in files)

    @Property("QStringList", constant=True)
    def actionCategories(self):
        # Placeholder action library taxonomy (mirrors the official app).
        return ["General", "Adjustments", "Navigation", "Media", "System", "Applications"]

    @Property("QStringList", constant=True)
    def ctExtraButtons(self):
        return list(self._profile.extra_buttons)

    @Slot(bool)
    def setDynamicMode(self, enabled):
        self._pm.set_dynamic_mode(enabled)
        self._pm.save()
        self.changed.emit()


def main():
    app = QGuiApplication(sys.argv)
    app.setApplicationName("Loupedeck Config")
    engine = QQmlApplicationEngine()
    backend = Backend()
    engine.rootContext().setContextProperty("backend", backend)
    engine.load(QUrl.fromLocalFile(os.path.join(APP_DIR, "qml", "Main.qml")))
    if not engine.rootObjects():
        sys.exit("Failed to load QML")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
