"""System tray presence. UI layer: this is the one module besides qml_app that
may touch Qt widgets.

The app is only useful while it is running, so the window closing should not
have to mean the process ending. This puts an icon in the tray with the things
worth reaching without opening the window: which profile is live, switching to
another, the dynamic-mode toggle, show/hide, and quit.

Tray support is not guaranteed. A desktop with no StatusNotifierItem host, or
Qt built without it, leaves QSystemTrayIcon::isSystemTrayAvailable() false; the
app then runs windowed exactly as it did before, rather than hiding itself
somewhere the user cannot get it back from.
"""

import os

import app_paths


def available():
    """Whether a tray exists to sit in. Import errors count as 'no': PySide6
    can be installed without QtWidgets.

    isSystemTrayAvailable() segfaults with no QApplication constructed yet, so
    the check for one is not defensiveness for its own sake. Anything asking
    this before the application exists gets "no", which is also the truth:
    there is nothing to put in a tray yet.
    """
    try:
        from PySide6.QtWidgets import QApplication, QSystemTrayIcon
    except ImportError:
        return False
    if QApplication.instance() is None:
        return False
    return bool(QSystemTrayIcon.isSystemTrayAvailable())


def icon():
    """The app icon, from the installed hicolor theme or the shipped SVG.

    Falls back to a themed name so a distro package that installs the icon
    elsewhere still gets one, and to a blank QIcon if there is nothing: a tray
    entry with no picture is still clickable, an exception is not.
    """
    from PySide6.QtGui import QIcon
    path = app_paths.asset_path(os.path.join("packaging", "icons",
                                             "loupedeckapp.svg"))
    if os.path.exists(path):
        return QIcon(path)
    themed = QIcon.fromTheme("loupedeckapp")
    return themed if not themed.isNull() else QIcon()


class Tray:
    """Owns the tray icon and its menu.

    Deliberately dumb: every entry calls back into the Backend, which is what
    the window's own controls do. The menu is rebuilt on refresh() rather than
    kept in sync entry by entry, because the profile list changes underneath it
    and a stale menu is worse than a rebuilt one.
    """

    def __init__(self, backend, on_show, on_hide, on_quit):
        from PySide6.QtWidgets import QMenu, QSystemTrayIcon
        self._backend = backend
        self._on_show = on_show
        self._on_hide = on_hide
        self._on_quit = on_quit
        self._menu = QMenu()
        self._tray = QSystemTrayIcon(icon())
        self._tray.setContextMenu(self._menu)
        self._tray.activated.connect(self._on_activated)
        self.refresh()
        self._tray.show()

    def _on_activated(self, reason):
        """Left click toggles the window. The context menu is the right button,
        which Qt handles itself."""
        from PySide6.QtWidgets import QSystemTrayIcon
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.toggle_window()

    def toggle_window(self):
        if self._backend.windowVisible:
            self._on_hide()
        else:
            self._on_show()

    # -- menu ---------------------------------------------------------------
    def refresh(self):
        """Rebuild the menu and the tooltip from current state."""
        if self._menu is None:
            return
        self._menu.clear()
        b = self._backend

        active = b.activeProfile
        self._tray.setToolTip("Loupedeck Config\n%s%s" % (
            active, "" if b.connected else "  (device not connected)"))

        header = self._menu.addAction(
            "%s%s" % (active, " *" if b.dirty else ""))
        header.setEnabled(False)
        self._menu.addSeparator()

        profiles = self._menu.addMenu("Profile")
        for name in b.profiles:
            act = profiles.addAction(name)
            act.setCheckable(True)
            act.setChecked(name == active)
            # Late binding in a loop would hand every entry the last name.
            act.triggered.connect(lambda checked=False, n=name: self._load(n))

        dyn = self._menu.addAction("Dynamic mode")
        dyn.setCheckable(True)
        dyn.setChecked(b.dynamicMode)
        dyn.triggered.connect(lambda checked: self._set_dynamic(checked))

        self._menu.addSeparator()
        show = self._menu.addAction(
            "Hide window" if b.windowVisible else "Show window")
        show.triggered.connect(self.toggle_window)
        quit_act = self._menu.addAction("Quit")
        quit_act.triggered.connect(self._on_quit)

    def _load(self, name):
        self._backend.loadProfile(name)
        self.refresh()

    def _set_dynamic(self, enabled):
        self._backend.setDynamicMode(bool(enabled))
        self.refresh()

    def message(self, title, text):
        """A tray notification. Used for things that happen with the window
        hidden, where there is otherwise nowhere to say them."""
        try:
            self._tray.showMessage(title, text, icon())
        except Exception as e:                      # notifications are optional
            print("tray: could not show message: %s" % e)

    def hide(self):
        if self._tray is not None:
            self._tray.hide()

    def close(self):
        self.hide()
        self._tray = None
        self._menu = None
