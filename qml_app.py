"""PySide6 + QML front-end (M4).

New UI shell that reuses the decoupled core (DeviceProfile, LdConfiguration,
input_backend, window_watcher, profile_manager) and drives the real device via
DeviceController. Runs alongside the existing PyQt5 app.py during migration.

Run:  QT_QPA_PLATFORM=xcb .venv/bin/python qml_app.py
"""

import os
import shutil
import sys
import glob
import json

from PySide6.QtCore import QObject, Property, Signal, Slot, QUrl, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

import action_library
import app_paths
import autostart
import macro
import input_backend
import device_lib
import installed_apps
import settings as settings_mod
import setup_check
import tray
import platform_env
import window_watcher
import system_shortcuts
from profile_manager import ProfileManager
from device_controller import DeviceController
from LdConfiguration import (LdConfiguration, SCHEMA_VERSION,
                             apply_default_bindings)
from DeviceProfile import WHEEL_DISPLAY, WS_KEYS
from LdConfiguration import (ROTATE_CONTROLS, SIDE_LAYOUTS, TUNING_PRESETS, DEFAULT_TUNING,
                             preset_to_tuning, tuning_to_preset)


class Backend(QObject):
    stateChanged = Signal()
    selectionChanged = Signal()
    # private cross-thread marshals -> delivered on the Qt main thread
    _marshal = Signal(str)
    _focusSig = Signal(str, str)
    # the tray asking the window to do something (QML holds the window)
    windowShowRequested = Signal()
    windowHideRequested = Signal()
    quitRequested = Signal()
    # tray turned on or off: main() creates or tears the icon down
    trayConfigChanged = Signal()
    setupChanged = Signal()
    # A line of text for the toast area: things that happened and are done,
    # where a dialog would be an interruption and the console is invisible.
    notify = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._selected = ""
        self._clipboard = None   # copied control function (see copyControl)
        self._sys_shortcuts = None   # lazily-read KDE shortcuts (cached)
        # Last focused window that was not this app. Clicking "bind" focuses our
        # own window first, so polling at click time would always answer
        # "Loupedeck Config"; remember what you were actually in instead.
        self._last_app = ""
        # Title of that window, which is what an app's pages match on.
        self._last_title = ""
        # An app being browsed that is not the loaded profile's, or "".
        self._browsing_app = ""
        # Applications installed on this machine, read on first use.
        self._installed = None
        # A profile switch dynamic mode wanted to make while edits were unsaved.
        self._pending_profile = ""
        # Whether the window is on screen. QML owns the window and tells us; the
        # tray needs to know which of show/hide to offer.
        self._window_visible = True
        # Last device connection state seen, so a reconnect can be announced
        # once rather than on every state refresh.
        self._was_connected = False
        # Machine setup (udev rule, input backend, helper tools). Run once at
        # startup and on demand: these are all things the user changes outside
        # the app, so a cached answer is fine until they say they fixed it.
        self._setup = setup_check.run()
        self._ctl = DeviceController(on_state=lambda kind: self._marshal.emit(kind))
        self._pm = ProfileManager(app_paths.dynamic_profiles_path())
        self._settings = settings_mod.Settings()
        self._ctl.brightness = self._settings.brightness
        self._ctl.auto_bind_buttons = self._settings.auto_bind_ct_buttons
        self._ctl.fn_mode = self._settings.fn_mode
        self._ctl.fn_active_color = self._settings.fn_active_color
        self._ctl.fn_inactive_color = self._settings.fn_inactive_color
        self._watcher = window_watcher.get_watcher(
            on_change=lambda c, t: self._focusSig.emit(c, t))
        self._marshal.connect(self._on_state_main, Qt.QueuedConnection)
        self._focusSig.connect(self._on_focus_main, Qt.QueuedConnection)

    # -- lifecycle ---------------------------------------------------------
    # Our own window is never a useful thing to bind. It cannot be recognised
    # by name: the class is whatever the toolkit reports, which is
    # "Loupedeck Config" under XWayland but "python3" on native Wayland, and
    # would be something else again once packaged. The PID is unambiguous.
    SELF_WM_CLASS = "loupedeck config"

    def _is_self_window(self, wm_class):
        pid = getattr(self._watcher, "last_pid", 0)
        if pid and pid == os.getpid():
            return True
        return bool(wm_class) and wm_class.strip().lower() == self.SELF_WM_CLASS

    # Shipped with the app, and what a first run should open with rather than
    # an empty device and no clue what to do with it.
    STARTER_PROFILE = "Starter"

    def _startup_profile(self):
        """Which profile to open on launch, as an "App/Profile" reference.

        The one you had open last, so the device comes back the way you left
        it. Failing that the starter, so a first run is a working deck rather
        than a blank one. Failing that whatever exists, because a profile list
        with something in it and nothing loaded is a confusing place to start.
        """
        available = app_paths.list_all_profiles()
        if not available:
            return ""
        starter = app_paths.make_ref(app_paths.DEFAULT_APP, self.STARTER_PROFILE)
        for candidate in (self._settings.last_profile, starter):
            if candidate and candidate in available:
                return candidate
        return available[0]

    def start(self):
        name = self._startup_profile()
        if name:
            self._ctl.load_profile(name)
        # Supervised: connects when the device appears and reconnects after an
        # unplug, rather than a single attempt at launch.
        self._ctl.start()
        # Always watch, even with dynamic mode off: the watcher is what records
        # which app you were last in, which the bind button needs. Acting on a
        # focus change is still gated on dynamic_mode below.
        self._watcher.start()

    def shutdown(self):
        self._watcher.stop()
        self._ctl.close()

    def _on_state_main(self, kind):
        if kind == "connected":
            now = self._ctl.connected
            if now != self._was_connected:
                self._was_connected = now
                self.notify.emit("%s connected" % self._ctl.profile.display_name
                                 if now else "Device disconnected")
        self.stateChanged.emit()

    def _on_focus_main(self, wm_class, title):
        if wm_class and not self._is_self_window(wm_class):
            if wm_class != self._last_app:
                self._last_app = wm_class
                self.stateChanged.emit()      # refresh the bind button's label
            # Kept for the pages editor, which matches on the title: you cannot
            # write a rule for a window you cannot see the title of.
            self._last_title = title or ""
        if not self._pm.dynamic_mode:
            return
        # Title as well as class: an app's pages are told apart by it.
        name = self._pm.resolve(wm_class, title)
        if not name or name == self._ctl.config.profile:
            return
        if self._ctl.dirty:
            # Never discard unsaved edits for a switch the user did not ask
            # for, and never raise a dialog either: they are looking at another
            # app, not at us. Hold the switch until the draft is resolved.
            if self._pending_profile != name:
                self._pending_profile = name
                print("dynamic: holding switch to '%s' (unsaved changes)" % name)
                self.stateChanged.emit()
            return
        print("dynamic: %s -> profile '%s'" % (wm_class, name))
        self._ctl.load_profile(name)
        self.stateChanged.emit()

    def _apply_pending_profile(self):
        """Run a switch dynamic mode deferred, now that the draft is resolved."""
        name = self._pending_profile
        self._pending_profile = ""
        if name and name != self._ctl.config.profile:
            print("dynamic: applying held switch to '%s'" % name)
            self._ctl.load_profile(name)

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

    # The device view draws whatever these list, so a Live S comes out with two
    # dials, no side strips and four round buttons without the QML knowing
    # which model it is.
    @Property("QStringList", notify=stateChanged)
    def encodersLeft(self):
        return list(self._ctl.profile.encoders_left)

    @Property("QStringList", notify=stateChanged)
    def encodersRight(self):
        return list(self._ctl.profile.encoders_right)

    @Property("QStringList", notify=stateChanged)
    def sideCellsLeft(self):
        return self._ctl.profile.side_cell_keys("L")

    @Property("QStringList", notify=stateChanged)
    def sideCellsRight(self):
        return self._ctl.profile.side_cell_keys("R")

    # -- side display layout (schema v8) ------------------------------------
    @Property("QVariantMap", notify=stateChanged)
    def sideLayout(self):
        """{"L": "cells"|"single", "R": ...} for the menu on screen."""
        return {side: self._ctl.side_layout(side) for side in ("L", "R")}

    @Property(bool, notify=selectionChanged)
    def selectedIsSideCell(self):
        return bool(self._selected) and self._selected.startswith("dis")

    @Property(str, notify=stateChanged)
    def selectedSideLayout(self):
        k = self._selected
        return self._ctl.side_layout(k[4]) if k and k.startswith("dis") else ""

    @Slot(str, str)
    def setSideLayout(self, side, mode):
        self._ctl.set_side_layout(side, mode)
        self.selectionChanged.emit()
        self.stateChanged.emit()

    @Property("QStringList", constant=True)
    def sideLayoutModes(self):
        return list(SIDE_LAYOUTS)

    # -- window / tray -----------------------------------------------------
    @Property(bool, notify=stateChanged)
    def windowVisible(self):
        return self._window_visible

    @Slot(bool)
    def setWindowVisible(self, visible):
        self._window_visible = bool(visible)
        self.stateChanged.emit()

    @Slot()
    def showWindow(self):
        self.windowShowRequested.emit()

    @Slot()
    def hideWindow(self):
        self.windowHideRequested.emit()

    @Property(bool, constant=True)
    def traySupported(self):
        return tray.available()

    @Property(bool, notify=stateChanged)
    def trayEnabled(self):
        return self._settings.tray_enabled and tray.available()

    @Property(bool, notify=stateChanged)
    def closeToTray(self):
        """Whether closing the window should hide it instead of quitting. False
        with no tray to close to: hiding the window then leaves no way back."""
        return self._settings.close_to_tray and tray.available()

    # -- autostart ---------------------------------------------------------
    @Property(bool, notify=stateChanged)
    def autostartEnabled(self):
        return autostart.enabled()

    @Property(bool, notify=stateChanged)
    def autostartStale(self):
        """On, but pointing at something else. The session still runs whatever
        the entry says, so nothing looks wrong until the app never starts."""
        on, current, _ = autostart.status()
        return on and not current

    @Property(str, notify=stateChanged)
    def autostartDetail(self):
        return autostart.status()[2]

    @Slot(bool, result=str)
    def setAutostart(self, enabled):
        """Returns "" or a message: writing into the config directory can fail,
        and a toggle that silently does not stick is worse than an error."""
        error = autostart.enable() if enabled else autostart.disable()
        self.stateChanged.emit()
        return error

    @Property(bool, notify=stateChanged)
    def startHidden(self):
        return self._settings.start_hidden and tray.available()

    @Slot(bool)
    def setStartHidden(self, enabled):
        self._settings.start_hidden = bool(enabled)
        self._settings.save()
        self.stateChanged.emit()

    @Slot(bool)
    def setCloseToTray(self, enabled):
        self._settings.close_to_tray = bool(enabled)
        self._settings.save()
        self.stateChanged.emit()

    @Slot(bool)
    def setTrayEnabled(self, enabled):
        self._settings.tray_enabled = bool(enabled)
        self._settings.save()
        self.stateChanged.emit()
        self.trayConfigChanged.emit()

    @Property(bool, notify=stateChanged)
    def menuEmpty(self):
        """Nothing bound on the workspace or submenu on screen.

        The CT's labelled buttons (home, undo, save, ...) are excluded: they
        are wired by default, so counting them would mean the "drag something
        onto a key" hint never appeared on the device it was written for.
        """
        menu = self._menu()
        if menu is None:
            return True
        skip = set(self._ctl.profile.extra_buttons) | set(WS_KEYS)
        return not any(a.a_type != "none"
                       for key, a in menu.actions.items() if key not in skip)

    @Property("QStringList", notify=stateChanged)
    def workspaceButtons(self):
        return self._ctl.profile.visible_workspace_keys

    @Property("QVariantMap", notify=stateChanged)
    def inputHealth(self):
        """{ok, name, detail} for the input backend. A backend that cannot
        inject otherwise fails invisibly: every action appears to do nothing
        and the only clue is on stderr."""
        ok, name, detail = input_backend.health()
        return {"ok": bool(ok), "name": name, "detail": detail}

    # -- machine setup -----------------------------------------------------
    @Property("QVariantList", notify=setupChanged)
    def setupChecks(self):
        return self._setup

    @Property(bool, notify=setupChanged)
    def setupOk(self):
        return setup_check.summary(self._setup)[0]

    @Property(bool, notify=setupChanged)
    def setupBlocking(self):
        """Something is wrong that stops the app doing its job, as opposed to
        losing an optional feature."""
        return bool(setup_check.summary(self._setup)[1])

    @Property(bool, notify=setupChanged)
    def setupFirstRun(self):
        return not self._settings.setup_seen

    @Slot()
    def recheckSetup(self):
        """Re-run after the user has gone and fixed something. The input
        backend is re-detected too: it caches which one it picked, and starting
        ydotoold would otherwise not be noticed."""
        input_backend.reset_backend()
        self._setup = setup_check.run()
        self.setupChanged.emit()
        self.stateChanged.emit()

    @Slot()
    def markSetupSeen(self):
        self._settings.setup_seen = True
        self._settings.save()
        self.setupChanged.emit()

    @Property("QVariantMap", notify=stateChanged)
    def deviceHealth(self):
        """{ok, detail} for the device library. Without it nothing can be found
        and the device pill would just say "not connected" forever, with the
        real reason only on stderr."""
        ok, detail = device_lib.health()
        return {"ok": bool(ok), "detail": detail}

    @Slot()
    def recheckInput(self):
        """Re-detect after the user fixes things (starting ydotoold, say)."""
        input_backend.reset_backend()
        self.stateChanged.emit()

    @Property(int, notify=stateChanged)
    def brightness(self):
        return self._ctl.brightness

    @Slot(int)
    def setBrightness(self, value):
        """Apply and remember. The device quantises to steps of 10, so small
        slider movements legitimately show no change."""
        self._ctl.set_brightness(value)
        self._settings.brightness = self._ctl.brightness
        self._settings.save()
        self.stateChanged.emit()

    @Property(bool, notify=stateChanged)
    def dynamicMode(self):
        return self._pm.dynamic_mode

    # -- applications and their profiles -----------------------------------
    # An application owns a folder of profiles and the window classes that mean
    # it is in front. The profile list in the UI is always the current app's.
    @Property(str, notify=stateChanged)
    def activeRef(self):
        """The full "App/Profile" reference of what is loaded."""
        return self._ctl.config.profile or ""

    @Property(str, notify=stateChanged)
    def activeApp(self):
        """The app being edited. Normally the loaded profile's, but it can be
        switched to browse another app without loading anything from it."""
        if self._browsing_app:
            return self._browsing_app
        return app_paths.split_ref(self.activeRef)[0]

    @Property(str, notify=stateChanged)
    def activeProfile(self):
        name = app_paths.split_ref(self.activeRef)[1]
        return name or "(none)"

    @Property(bool, notify=stateChanged)
    def activeProfileInApp(self):
        """Whether the loaded profile belongs to the app on screen. False while
        browsing another app, where the profile list highlights nothing."""
        return app_paths.split_ref(self.activeRef)[0] == self.activeApp

    @Property("QStringList", notify=stateChanged)
    def apps(self):
        return app_paths.list_apps()

    @Property("QStringList", notify=stateChanged)
    def profiles(self):
        return app_paths.list_profiles(self.activeApp)

    @Slot(str)
    def selectApp(self, app):
        """Show an app's profiles. Deliberately does not load one: switching
        app in the UI should not change what the device is doing until a
        profile is picked."""
        if app in app_paths.list_apps():
            self._browsing_app = ("" if app == app_paths.split_ref(self.activeRef)[0]
                                  else app)
            self.stateChanged.emit()

    @Property("QStringList", notify=stateChanged)
    def appMatches(self):
        """Window classes that make the current app the focused one."""
        return app_paths.app_matches(self.activeApp)

    @Slot(str)
    def addAppMatch(self, wm_class):
        wm_class = (wm_class or "").strip()
        if not wm_class:
            return
        matches = app_paths.app_matches(self.activeApp)
        if wm_class.lower() not in [m.lower() for m in matches]:
            app_paths.set_app_matches(self.activeApp, matches + [wm_class])
        self.stateChanged.emit()

    @Slot(str)
    def removeAppMatch(self, wm_class):
        matches = [m for m in app_paths.app_matches(self.activeApp)
                   if m.lower() != (wm_class or "").lower()]
        app_paths.set_app_matches(self.activeApp, matches)
        self.stateChanged.emit()

    @Property(str, notify=stateChanged)
    def appDefaultProfile(self):
        """The profile dynamic mode loads for this app when no page matches."""
        return app_paths.app_default_profile(self.activeApp)

    @Slot(str)
    def setAppDefaultProfile(self, name):
        app_paths.set_app_default_profile(self.activeApp, name)
        self.stateChanged.emit()

    # -- pages inside an application ---------------------------------------
    @Property(str, notify=stateChanged)
    def focusedTitle(self):
        """Title of the last window that was not ours, for writing a page rule
        against. A rule for a title you cannot see is guesswork."""
        return self._last_title

    @Property("QVariantList", notify=stateChanged)
    def appPages(self):
        return app_paths.app_pages(self.activeApp)

    @Slot(str, str, str)
    def addAppPage(self, name, match, profile):
        """A page is a named window-title rule pointing at one of this app's
        profiles: Premiere Pro is one app, but Cut, Edit and Sound each want a
        different deck."""
        name = (name or "").strip()
        profile = (profile or "").strip()
        if not name or profile not in app_paths.list_profiles(self.activeApp):
            return
        pages = [p for p in app_paths.app_pages(self.activeApp)
                 if p["name"].lower() != name.lower()]
        pages.append({"name": name, "match": (match or "").strip(),
                      "profile": profile})
        app_paths.set_app_pages(self.activeApp, pages)
        self.notify.emit("Page '%s' set" % name)
        self.stateChanged.emit()

    @Slot(str)
    def removeAppPage(self, name):
        pages = [p for p in app_paths.app_pages(self.activeApp)
                 if p["name"].lower() != (name or "").lower()]
        app_paths.set_app_pages(self.activeApp, pages)
        self.stateChanged.emit()

    @Slot(int, int)
    def moveAppPage(self, index, delta):
        """Pages are tried in order, so their order is the precedence and has
        to be editable."""
        pages = app_paths.app_pages(self.activeApp)
        target = index + delta
        if not (0 <= index < len(pages) and 0 <= target < len(pages)):
            return
        pages[index], pages[target] = pages[target], pages[index]
        app_paths.set_app_pages(self.activeApp, pages)
        self.stateChanged.emit()

    @Property("QStringList", constant=True)
    def actionCategories(self):
        return list(action_library.CATEGORIES)

    @Property("QVariantList", constant=True)
    def actionLibrary(self):
        return [{"category": c, "label": l, "type": t, "value": v}
                for (c, l, t, v) in self.ACTION_LIBRARY]

    # -- control selection + action editing (inspector) --------------------
    ACTION_TYPES = ["none", "command", "hotkey", "text", "scroll", "media",
                    "keyboard", "workspace", "macro"]

    # Per-platform, from action_library: the applications differ by desktop.
    ACTION_LIBRARY = action_library.default_library()

    @Slot(str, result=str)
    def describeMacro(self, text):
        """'3 steps, 1 problem' for the editor, so a typo is visible without
        having to press the button and notice nothing happened."""
        return macro.describe(text)

    @Slot(str, result="QStringList")
    def macroProblems(self, text):
        """Human-readable problems, one per bad line."""
        _steps, errors = macro.parse(text)
        return ["line %d: %s" % (lineno, msg) for lineno, msg in errors]

    @Property("QStringList", constant=True)
    def macroStepKinds(self):
        return list(macro.STEP_KINDS)

    @Slot(str, result="QVariantList")
    def macroSteps(self, text):
        """The macro as a list of {kind, value}, for the list editor. The text
        remains the stored form; this is a second view of it."""
        return macro.steps_for_ui(text)

    @Slot("QVariantList", result=str)
    def macroText(self, steps):
        """The list editor's steps back as text, which is what gets stored."""
        return macro.to_text(steps)

    @Slot(str, result="QVariantList")
    def filterLibrary(self, query):
        """Library entries matching `query`, or all of them when it is empty.

        Every whitespace-separated term must appear somewhere in the entry, so
        "vol up" narrows the way you would expect. Matching covers the value and
        type as well as the label, which is what makes "ctrl" or "scroll" useful
        searches."""
        terms = [t for t in str(query or "").lower().split() if t]
        if not terms:
            return self.actionLibrary
        out = []
        for entry in self.actionLibrary:
            hay = " ".join((entry["label"], entry["category"],
                            entry["type"], entry["value"])).lower()
            if all(t in hay for t in terms):
                out.append(entry)
        return out

    @Slot(str, str, str, str)
    def applyLibraryAction(self, key, a_type, value, label=""):
        """Bind a library action onto a control (drag-drop target). Nav actions
        (submenu/back) only apply to single-action 'key' controls; a plain
        action dropped on an encoder/dial/knob binds its press slot. ``label`` is
        the library's friendly name, used for the auto-label."""
        if not key:
            return
        if a_type in ("submenu", "back") and self._kind(key) != "key":
            return
        self._ctl.set_action(key, a_type, value, summary=label)
        # select the base control (encoders/dial expose all their slots there)
        self._selected = key[:-2] if key.endswith(("-l", "-r")) else key
        self.selectionChanged.emit()
        self.stateChanged.emit()

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
            out[key] = QUrl.fromLocalFile(app_paths.asset_path(path)).toString()
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

    @Property(str, notify=stateChanged)
    def workspaceLabel(self):
        """Name of the workspace on screen, or 'Workspace <n>'. Eight numbered
        buttons say nothing about what is on them."""
        return self._ctl.workspace_label()

    @Property(str, notify=stateChanged)
    def workspaceName(self):
        """The raw name (blank when unnamed), for the editor field."""
        return self._ctl.workspace_name()

    @Slot(str)
    def showWorkspace(self, key):
        """Put a workspace on the device and select it. Editing workspace 5
        otherwise meant reaching over and pressing the physical button."""
        if key in WS_KEYS:
            self._ctl.on_workspace_press(key)
            self.selectControl(key)
        self.stateChanged.emit()

    @Slot(str, str)
    def setWorkspaceName(self, key, name):
        self._ctl.set_workspace_name(key or self._ctl.selected_ws, name)
        self.stateChanged.emit()

    @Slot(str, result=str)
    def workspaceNameOf(self, key):
        return self._ctl.workspace_name(key) if key in WS_KEYS else ""

    @Property(int, notify=stateChanged)
    def menuDepth(self):
        return len(self._ctl.submenu_stack)

    # -- control selection + action editing (inspector) --------------------
    ACTION_TYPES = ["none", "command", "hotkey", "text", "scroll", "media",
                    "keyboard", "workspace", "macro"]

    # Ready-to-use actions for the left-panel library (category, label, type,
    # value). Dragged onto a control to bind it; templates (empty value) are
    # filled in via the inspector afterwards.
    ACTION_LIBRARY = [
        ("General", "Type text…", "text", ""),
        ("General", "Run command…", "command", ""),
        ("System", "Copy", "hotkey", "ctrl+c"),
        ("System", "Paste", "hotkey", "ctrl+v"),
        ("System", "Cut", "hotkey", "ctrl+x"),
        ("System", "Undo", "hotkey", "ctrl+z"),
        ("System", "Redo", "hotkey", "ctrl+shift+z"),
        ("System", "Select all", "hotkey", "ctrl+a"),
        ("System", "Save", "hotkey", "ctrl+s"),
        ("System", "Screenshot", "command", "spectacle"),
        ("Adjustments", "Scroll up", "scroll", "up"),
        ("Adjustments", "Scroll down", "scroll", "down"),
        ("Adjustments", "Scroll left", "scroll", "left"),
        ("Adjustments", "Scroll right", "scroll", "right"),
        # Volume is a hotkey rather than a media action: playerctl drives the
        # media player, while these are the system-wide multimedia keys, which
        # is what people mean by "bind volume to a knob".
        ("Adjustments", "Volume up", "hotkey", "volumeup"),
        ("Adjustments", "Volume down", "hotkey", "volumedown"),
        ("Adjustments", "Mute", "hotkey", "mute"),
        ("Media", "Play / Pause", "media", "play-pause"),
        ("Media", "Next track", "media", "next"),
        ("Media", "Previous track", "media", "previous"),
        ("Media", "Stop", "media", "stop"),
        ("Navigation", "Submenu", "submenu", "submenu"),
        ("Navigation", "Back", "back", ""),
        ("Applications", "Terminal", "command", "konsole"),
        ("Applications", "Files", "command", "dolphin"),
        ("Applications", "Browser", "command", "xdg-open https://"),
    ]

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
        if key in WS_KEYS:
            # Numbered from 1 like the device view, not by the firmware name:
            # the button drawn "3" was reading "Button 2" here, because the
            # first one is called 'circle'.
            return self._ctl.workspace_label(key)
        return "Button %s" % key.upper()

    @Property(str, notify=selectionChanged)
    def selectedControl(self):
        return self._selected

    @Property(str, notify=selectionChanged)
    def selectedLabel(self):
        return self._label(self._selected) if self._selected else ""

    @Property(bool, notify=selectionChanged)
    def selectedIsWorkspace(self):
        return self._selected in WS_KEYS

    @Property(bool, notify=selectionChanged)
    def selectedHasImage(self):
        k = self._selected
        return bool(k) and (k.startswith("tb") or k.startswith("dis") or k == WHEEL_DISPLAY)

    @Property(str, notify=stateChanged)
    def selectedImage(self):
        if not self._selected:
            return ""
        return self.keyImages.get(self._selected, "")

    @Property(str, notify=stateChanged)
    def selectedImageDims(self):
        """The device pixel size of the selected image control, e.g. '90 × 90
        px', shown as a hint (images are fit, not cropped, so this is the size to
        make a source image for a pixel-perfect fill)."""
        k = self._selected
        p = self._ctl.profile
        if not k:
            return ""
        if k.startswith("tb"):
            w, h = p.key_size
        elif k.startswith("dis"):
            w, h = p.side_cell_size
            if self._ctl.side_layout(k[4]) == "single":
                # One image for the strip, so the size to make is the strip's,
                # not a cell's. Getting this wrong sends people off to crop a
                # 60x90 image for a 60x270 space.
                h *= p.side_cells
        elif k == WHEEL_DISPLAY:
            w, h = p.wheel_size or (0, 0)
        else:
            return ""
        return "%d × %d px" % (w, h) if w and h else ""

    @Property("QVariantMap", notify=stateChanged)
    def controlLabels(self):
        """Effective label per image-bearing control (explicit or auto-derived),
        for the on-screen mirror overlay."""
        menu = self._menu()
        out = {}
        if not menu:
            return out
        for key in menu.images.keys():
            lbl = self._ctl.effective_label(menu, key)
            if lbl:
                out[key] = lbl
        return out

    def _effective_label(self):
        """Label fields for the inspector. Ignores the on/off toggle and image
        so the text/placement controls always show the effective values (the
        text never blanks when you hide the label or add an image)."""
        menu = self._menu()
        if not menu or not self._selected:
            return {}
        entry = dict(menu.labels.get(self._selected) or {})
        text = (entry.get("text") or "").strip()
        if not text:
            act = menu.actions.get(self._selected)
            if act is not None and getattr(act, "a_type", "none") != "none":
                text = self._ctl._auto_label_text(act)
        pos = entry.get("pos", "bottom")
        mode = entry.get("mode", "over")
        if mode == "shrink" and pos == "middle":
            mode = "over"
        out = {"text": text, "pos": pos, "mode": mode}
        bc = entry.get("bar_color")
        if not bc and mode == "shrink":
            bc = self._ctl.effective_bg(menu, self._selected)
        if bc:
            out["bar_color"] = bc
        return out

    @Property(bool, notify=stateChanged)
    def selectedLabelEnabled(self):
        menu = self._menu()
        if not menu or not self._selected:
            return True
        return not (menu.labels.get(self._selected) or {}).get("off")

    @Slot(str, bool)
    def setLabelEnabled(self, key, enabled):
        self._ctl.set_label_enabled(key, enabled)
        self.stateChanged.emit()

    @Property(str, notify=stateChanged)
    def selectedLabelText(self):
        # effective text (explicit, else the friendly auto-label) so the field
        # is pre-filled with e.g. "Copy" rather than blank
        return self._effective_label().get("text", "")

    @Property(str, notify=stateChanged)
    def selectedLabelPos(self):
        return self._effective_label().get("pos", "bottom")

    @Property(str, notify=stateChanged)
    def selectedLabelMode(self):
        return self._effective_label().get("mode", "over")

    @Property(str, notify=stateChanged)
    def selectedLabelBarColor(self):
        return self._effective_label().get("bar_color", "")

    @Property("QStringList", constant=True)
    def labelPositions(self):
        return ["top", "middle", "bottom"]

    @Property("QStringList", constant=True)
    def labelModes(self):
        # over = text on top of the image; bar = text on a band over the image;
        # shrink = image resized so the text sits in a band beside it
        return ["over", "bar", "shrink"]

    @Slot(str, str, str, str, str)
    def setLabel(self, key, text, pos, mode, bar_color=""):
        self._ctl.set_label(key, text, pos, mode, bar_color)
        self.stateChanged.emit()

    # -- per-control background fill colour --------------------------------
    @Property(bool, notify=selectionChanged)
    def selectedHasBg(self):
        # any control that can hold an image can hold a background colour
        return self.selectedHasImage

    @Property(str, notify=stateChanged)
    def selectedBg(self):
        menu = self._menu()
        if menu and self._selected:
            return (getattr(menu, "bg_colors", {}) or {}).get(self._selected, "")
        return ""

    @Property("QVariantMap", notify=stateChanged)
    def controlBgs(self):
        """control-key -> #rrggbb background fill, for the on-screen mirror."""
        menu = self._menu()
        return dict(getattr(menu, "bg_colors", {}) or {}) if menu else {}

    @Slot(str, str)
    def setBg(self, key, color):
        self._ctl.set_bg(key, color)
        self.stateChanged.emit()

    # -- hotkey helpers (recorder + pick-lists) ----------------------------
    # Common editing/window shortcuts offered as a quick pick-list.
    COMMON_HOTKEYS = [
        ("Copy", "ctrl+c"), ("Paste", "ctrl+v"), ("Cut", "ctrl+x"),
        ("Undo", "ctrl+z"), ("Redo", "ctrl+shift+z"), ("Select all", "ctrl+a"),
        ("Save", "ctrl+s"), ("Save as", "ctrl+shift+s"), ("Find", "ctrl+f"),
        ("New", "ctrl+n"), ("Open", "ctrl+o"), ("Print", "ctrl+p"),
        ("Close tab", "ctrl+w"), ("Quit", "ctrl+q"), ("Switch app", "alt+tab"),
        ("Show desktop", "super+d"), ("Lock screen", "super+l"),
        ("Screenshot region", "shift+printscreen"), ("Terminal", "ctrl+alt+t"),
    ]

    @Property("QVariantList", constant=True)
    def commonHotkeys(self):
        return [{"label": l, "value": v} for (l, v) in self.COMMON_HOTKEYS]

    @Property("QVariantList", constant=True)
    def systemShortcuts(self):
        """The user's configured KDE global shortcuts (best-effort), so they can
        bind an existing machine shortcut without retyping it."""
        if self._sys_shortcuts is None:
            try:
                self._sys_shortcuts = [{"label": l, "value": v}
                                       for (l, v) in system_shortcuts.read_shortcuts()]
            except Exception:
                self._sys_shortcuts = []
        return self._sys_shortcuts

    # -- physical button RGB LEDs ------------------------------------------
    @Property(bool, notify=selectionChanged)
    def selectedHasLed(self):
        k = self._selected
        return bool(k) and (k in WS_KEYS or k in self._ctl.profile.extra_buttons)

    @Property(str, notify=stateChanged)
    def selectedLed(self):
        menu = self._menu()
        if menu and self._selected:
            return menu.led_colors.get(self._selected, "")
        return ""

    @Property("QVariantMap", notify=stateChanged)
    def controlLeds(self):
        """Button-name -> #rrggbb for the on-screen mirror to tint buttons."""
        menu = self._menu()
        return dict(menu.led_colors) if menu else {}

    @Slot(str, str)
    def setLed(self, key, color):
        self._ctl.set_led(key, color)
        self.stateChanged.emit()

    # -- encoder feel (schema v5) ------------------------------------------
    def _has_tuning(self):
        """Plain helper, not the Property: reading a Property off `self` inside
        a method yields the descriptor (always truthy), which would silently
        defeat every guard below."""
        return self._selected in ROTATE_CONTROLS

    @Property(bool, notify=selectionChanged)
    def selectedHasTuning(self):
        """Rotate controls only: the encoders and the CT dial."""
        return self._has_tuning()

    @Property("QVariantList", constant=True)
    def tuningPresets(self):
        """Speed presets for the inspector dropdown. The two integers behind
        them stay authoritative; this is only the surface."""
        return [{"id": pid, "label": label} for pid, label, _d, _s in TUNING_PRESETS]

    @Property(bool, notify=stateChanged)
    def selectedInvert(self):
        if not self._has_tuning():
            return False
        return bool(self._ctl.effective_tuning(self._selected)["invert"])

    @Property(str, notify=stateChanged)
    def selectedPreset(self):
        """Preset id for the selected control, or '' for a hand-edited
        combination the presets do not cover."""
        if not self._has_tuning():
            return ""
        return tuning_to_preset(self._ctl.effective_tuning(self._selected)) or ""

    @Property(str, notify=stateChanged)
    def selectedTuningSummary(self):
        """Plain-language description of the current feel, so the effect is
        legible without decoding two integers."""
        if not self._has_tuning():
            return ""
        t = self._ctl.effective_tuning(self._selected)
        dps, spd = t["detents_per_step"], t["steps_per_detent"]
        if dps > 1:
            s = "%d detents = 1 step" % dps
        elif spd > 1:
            s = "1 detent = %d steps" % spd
        else:
            s = "1 detent = 1 step"
        s += ", reversed" if t["invert"] else ""
        if t["curve"] == "accel":
            s += ", accelerating when spun"
        # Say so when this menu is only borrowing the setting, otherwise an
        # inherited Fast 3x reads as if it were set here.
        menu = self._menu()
        if menu is not None and self._selected not in getattr(menu, "tuning", {}) \
                and t != DEFAULT_TUNING:
            s += " (inherited)"
        return s

    @Property(bool, notify=stateChanged)
    def selectedAccel(self):
        if not self._has_tuning():
            return False
        return self._ctl.effective_tuning(self._selected)["curve"] == "accel"

    @Slot(str, bool, bool)
    def setTuning(self, preset_id, invert, accel=False):
        """Apply a preset (plus invert and acceleration) to the selected
        rotate control."""
        if not self._has_tuning():
            return
        t = preset_to_tuning(preset_id, invert)
        t["curve"] = "accel" if accel else "linear"
        self._ctl.set_tuning(self._selected, t)
        self.stateChanged.emit()

    @Property("QVariantList", notify=stateChanged)
    def selectedSlots(self):
        """Editor rows for the selected control: slot key, label, current
        action type + value."""
        out = []
        if not self._selected:
            return out
        if self._selected in WS_KEYS:
            return out   # workspace buttons switch pages; they have no action, only an LED
        menu = self._menu()
        for slot, label in self._slot_defs(self._selected):
            act = menu.actions.get(slot) if menu else None
            a_type = getattr(act, "a_type", "none") if act else "none"
            if a_type == "submenu":
                value = getattr(act, "name", "")     # .action is a workspace
            elif a_type == "back":
                value = ""
            else:
                value = getattr(act, "action", "") if act else ""
            fn_act = menu.fn_action(slot) if menu else None
            out.append({"slot": slot, "label": label, "type": a_type,
                        "value": value,
                        "fnType": getattr(fn_act, "a_type", "none") if fn_act else "none",
                        "fnValue": getattr(fn_act, "action", "") if fn_act else ""})
        return out

    @Property("QStringList", constant=True)
    def actionTypes(self):
        return list(self.ACTION_TYPES)

    @Property("QStringList", notify=selectionChanged)
    def selectedActionTypes(self):
        """Action types offered for the selected control: submenu/back are only
        meaningful on single-action 'key' controls, not encoders/dial."""
        types = list(self.ACTION_TYPES)
        if self._selected and self._kind(self._selected) == "key":
            types += ["submenu", "back"]
        return types

    @Property(bool, notify=stateChanged)
    def selectedIsSubmenu(self):
        menu = self._menu()
        if not self._selected or not menu:
            return False
        act = menu.actions.get(self._selected)
        return getattr(act, "a_type", "") == "submenu"

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

    @Property(bool, notify=stateChanged)
    def dirty(self):
        return self._ctl.dirty

    @Slot(str, str, str)
    def setActionSlot(self, slot_key, a_type, value):
        # Switching an empty slot to a fixed-choice type should land on a valid
        # option, not an empty string that silently does nothing.
        opts = self.VALUE_OPTIONS.get(a_type)
        if opts and value not in [o["value"] for o in opts]:
            value = opts[0]["value"]
        self._ctl.set_action(slot_key, a_type, value)
        self.stateChanged.emit()

    # Action types whose value is a fixed set rather than free text. Typing
    # 'up' by hand is a needless way to get 'sideways' wrong.
    VALUE_OPTIONS = {
        "scroll": [{"label": "Up", "value": "up"},
                   {"label": "Down", "value": "down"},
                   {"label": "Left", "value": "left"},
                   {"label": "Right", "value": "right"}],
        "media": [{"label": "Play / Pause", "value": "play-pause"},
                  {"label": "Next track", "value": "next"},
                  {"label": "Previous track", "value": "previous"},
                  {"label": "Stop", "value": "stop"}],
        "keyboard": [{"label": "Toggle", "value": "toggle"},
                     {"label": "Show", "value": "show"},
                     {"label": "Hide", "value": "hide"}],
        "workspace": [{"label": "Workspace %d" % (i + 1), "value": k}
                      for i, k in enumerate(WS_KEYS)],
    }

    @Property("QVariantMap", constant=True)
    def valueOptions(self):
        """action type -> [{label, value}] for types the inspector should
        present as a dropdown."""
        return dict(self.VALUE_OPTIONS)

    # -- fn layer ----------------------------------------------------------
    @Slot(str, str, str)
    def setFnActionSlot(self, slot_key, a_type, value):
        """Set the secondary (fn) binding for a slot. 'none' clears it."""
        opts = self.VALUE_OPTIONS.get(a_type)
        if opts and value not in [o["value"] for o in opts]:
            value = opts[0]["value"]
        self._ctl.set_fn_action(slot_key, a_type, value)
        self.stateChanged.emit()

    @Property(bool, notify=stateChanged)
    def fnLatched(self):
        """Whether the fn layer is currently engaged, so the UI can show it."""
        return self._ctl.fn_active

    @Property(str, notify=stateChanged)
    def fnMode(self):
        return self._ctl.fn_mode

    @Property(str, notify=stateChanged)
    def fnActiveColor(self):
        return self._ctl.fn_active_color

    @Property(str, notify=stateChanged)
    def fnInactiveColor(self):
        """Blank means the fn keys use the workspace's LED colour, like any
        other button."""
        return self._ctl.fn_inactive_color

    @Slot(str, str)
    def setFnColors(self, active, inactive):
        self._ctl.set_fn_colors(active=active, inactive=inactive)
        self._settings.set("fn_active_color", self._ctl.fn_active_color)
        self._settings.set("fn_inactive_color", self._ctl.fn_inactive_color)
        self._settings.save()
        self.stateChanged.emit()

    @Slot(str)
    def setFnMode(self, mode):
        """'hold' (default) or 'latch'."""
        mode = mode if mode in ("hold", "latch") else "hold"
        self._ctl.fn_mode = mode
        self._ctl.fn_active = False
        self._settings.set("fn_mode", mode)
        self._settings.save()
        self.stateChanged.emit()

    @Slot(str, str)
    def setImage(self, key, file_url):
        path = QUrl(file_url).toLocalFile() if file_url else ""
        self._ctl.set_image(key, path)
        self.stateChanged.emit()

    @Slot(str)
    def clearImage(self, key):
        self._ctl.set_image(key, "")
        self.stateChanged.emit()

    @Property(str, notify=stateChanged)
    def pendingProfile(self):
        """Profile that dynamic mode is waiting to switch to, or "". The UI
        surfaces this so a held switch is visible rather than mysterious."""
        return self._pending_profile

    @Slot()
    def save(self):
        self._ctl.save()
        self._apply_pending_profile()
        self.notify.emit("Saved to %s" % self.activeProfile)
        self.selectionChanged.emit()
        self.stateChanged.emit()

    @Slot()
    def revert(self):
        self._ctl.revert()
        self._apply_pending_profile()
        self.selectionChanged.emit()
        self.stateChanged.emit()

    # -- submenu navigation ------------------------------------------------
    @Slot()
    def enterSubmenu(self):
        if self._selected and self._ctl.open_submenu(self._selected):
            self._selected = ""      # selection belonged to the parent menu
            self.selectionChanged.emit()
            self.stateChanged.emit()

    @Slot()
    def goBack(self):
        if self._ctl.close_submenu():
            self._selected = ""
            self.selectionChanged.emit()
            self.stateChanged.emit()

    # -- copy / paste a control's function ---------------------------------
    def _kind(self, key):
        """Paste-compatibility class: 'knob' (encoder/dial, press + 2 rotate
        slots) vs 'key' (single-action buttons, touch keys, side cells, wheel)."""
        if key.startswith("enc") or key in ("dial", "dial-l", "dial-r"):
            return "knob"
        return "key"

    @Property(bool, notify=selectionChanged)
    def hasClipboard(self):
        return self._clipboard is not None

    @Property(str, notify=selectionChanged)
    def clipboardLabel(self):
        return self._clipboard["label"] if self._clipboard else ""

    @Property(bool, notify=selectionChanged)
    def canPaste(self):
        return (self._clipboard is not None and bool(self._selected)
                and self._kind(self._selected) == self._clipboard["kind"])

    @Slot()
    def copyControl(self):
        key = self._selected
        if not key:
            return
        menu = self._menu()
        slots = {}
        for slot, _ in self._slot_defs(key):
            act = menu.actions.get(slot) if menu else None
            suffix = slot[len(key):]   # "" / "-l" / "-r"
            slots[suffix] = (getattr(act, "a_type", "none") if act else "none",
                             getattr(act, "action", "") if act else "")
        self._clipboard = {
            "kind": self._kind(key),
            "label": self._label(key),
            "slots": slots,
            "image": (menu.images.get(key, "") if (menu and self.selectedHasImage) else None),
        }
        self.notify.emit("Copied %s" % self._label(key))
        self.selectionChanged.emit()

    @Slot()
    def pasteControl(self):
        key = self._selected
        if not key or not self.canPaste:
            return
        for suffix, (a_type, value) in self._clipboard["slots"].items():
            self._ctl.set_action(key + suffix, a_type, value)
        img = self._clipboard.get("image")
        if img is not None and self.selectedHasImage:
            self._ctl.set_image(key, img)
        self.notify.emit("Pasted onto %s" % self._label(key))
        self.stateChanged.emit()

    # -- slots -------------------------------------------------------------
    @Slot(str)
    def loadProfile(self, name):
        """`name` is a profile in the app on screen, or a full reference."""
        ref = name if app_paths.REF_SEP in (name or "") else self._ref(name)
        self._ctl.load_profile(ref)
        self._remember_profile(ref)
        self._browsing_app = ""
        self.stateChanged.emit()

    def _remember_profile(self, name):
        """Record what is open, so the next launch opens the same thing.

        Dynamic mode changes the profile constantly and none of that should
        count: what is remembered is what the user chose, which is why this is
        called from the slots the UI drives and not from the controller.
        """
        if name and name != self._settings.last_profile:
            self._settings.last_profile = name
            self._settings.save()

    # -- profile lifecycle -------------------------------------------------
    @staticmethod
    def _clean_profile_name(name):
        """A profile name becomes a filename, so keep it to something that
        cannot escape the Profiles directory or collide with path syntax."""
        name = (name or "").strip()
        if not name:
            return ""
        bad = set('/\\:*?"<>|')
        if any(ch in bad for ch in name) or name in (".", ".."):
            return ""
        return name

    def _profile_path(self, name, app=None):
        """Where a profile *would* be read from, user copy preferred. Scoped to
        the app on screen unless one is named."""
        return app_paths.profile_read_path(app or self.activeApp, name)

    def _ref(self, name, app=None):
        return app_paths.make_ref(app or self.activeApp, name)

    @Property("QStringList", constant=True)
    def profileNameRules(self):
        return ["Cannot be empty", "No / \\ : * ? \" < > |"]

    @Slot(str, result=str)
    def validateProfileName(self, name):
        """'' when the name is usable, otherwise why it is not. Lets the UI
        explain the problem before the button is pressed."""
        clean = self._clean_profile_name(name)
        if not clean:
            return "Enter a name without / \\ : * ? \" < > |"
        if os.path.exists(self._profile_path(clean)):
            return "A profile called '%s' already exists" % clean
        return ""

    # -- application lifecycle ---------------------------------------------
    @Slot(str, result=str)
    def validateAppName(self, name):
        clean = self._clean_profile_name(name)
        if not clean:
            return "Enter a name without / \\ : * ? \" < > |"
        if clean in app_paths.list_apps():
            return "An app called '%s' already exists" % clean
        return ""

    # -- what this machine has installed -----------------------------------
    # Read once: scanning a few hundred desktop entries on every keystroke
    # would be wasteful, and applications do not appear while a dialog is open.
    @Property("QVariantList", notify=stateChanged)
    def installedApps(self):
        if self._installed is None:
            self._installed = installed_apps.list_installed()
        return self._installed

    @Slot(str, result="QVariantList")
    def searchInstalledApps(self, query):
        """Installed applications matching a query, minus the ones already
        added: offering an app you have is offering a name that will be
        refused."""
        taken = {a.lower() for a in app_paths.list_apps()}
        return [e for e in installed_apps.search(query, self.installedApps)
                if e["name"].lower() not in taken]

    @Slot()
    def rescanInstalledApps(self):
        self._installed = None
        self.stateChanged.emit()

    @Slot(str, str)
    def createApp(self, name, match=""):
        """A new application, with one empty profile in it.

        Empty apps are a trap: the app list would show something that cannot be
        selected onto the device, so it gets a profile to start from. `match`
        is the window class that means it is focused, filled in by the picker
        when the app was chosen from what is installed.
        """
        clean = self._clean_profile_name(name)
        if not clean or clean in app_paths.list_apps():
            return
        app_paths.ensure_user_app_dir(clean)
        if match:
            app_paths.set_app_matches(clean, [match])
        ref = app_paths.make_ref(clean, clean)
        cfg = apply_default_bindings(LdConfiguration(profile=ref))
        with open(app_paths.profile_write_path(ref), "w") as f:
            json.dump(cfg.to_JSON(), f, indent=True)
        app_paths.set_app_default_profile(clean, clean)
        self._browsing_app = clean
        self.notify.emit("Created app %s" % clean)
        self.stateChanged.emit()

    @Slot(str, str)
    def renameApp(self, old, name):
        clean = self._clean_profile_name(name)
        if not clean or not old or clean == old:
            return
        if clean in app_paths.list_apps() or old == app_paths.DEFAULT_APP:
            return
        src = app_paths.user_app_dir(old)
        if not os.path.isdir(src):
            return
        os.rename(src, app_paths.user_app_dir(clean))
        # Every reference to it moves too, or dynamic mode resolves to a folder
        # that is no longer there.
        for binding in self._pm.app_profiles:
            b_app, b_name = app_paths.split_ref(binding["profile"])
            if b_app == old:
                binding["profile"] = app_paths.make_ref(clean, b_name)
        if self._pm.default_profile:
            d_app, d_name = app_paths.split_ref(self._pm.default_profile)
            if d_app == old:
                self._pm.default_profile = app_paths.make_ref(clean, d_name)
        self._pm.save()
        cur_app, cur_name = app_paths.split_ref(self.activeRef)
        if cur_app == old:
            self._ctl.config.profile = app_paths.make_ref(clean, cur_name)
        if self._browsing_app == old:
            self._browsing_app = clean
        self.notify.emit("Renamed app %s to %s" % (old, clean))
        self.stateChanged.emit()

    @Slot(str)
    def deleteApp(self, name):
        """Remove an application and everything in it."""
        if not name or name == app_paths.DEFAULT_APP:
            return
        path = app_paths.user_app_dir(name)
        if not os.path.isdir(path):
            return
        # Into the trash rather than gone: an application is a folder of work.
        kept = app_paths.trash(path, "app %s" % name)
        for ref in [b["profile"] for b in self._pm.app_profiles]:
            if app_paths.split_ref(ref)[0] == name:
                self._repoint_bindings(ref, None)
        if self._browsing_app == name:
            self._browsing_app = ""
        if app_paths.split_ref(self.activeRef)[0] == name:
            fallback = app_paths.list_profiles(app_paths.DEFAULT_APP)
            if fallback:
                self._ctl.load_profile(
                    app_paths.make_ref(app_paths.DEFAULT_APP, fallback[0]))
        self.notify.emit("Deleted app %s%s"
                         % (name, "" if kept else " (no copy kept)"))
        self.stateChanged.emit()

    @Slot(str)
    def createProfile(self, name):
        """New empty profile, saved to disk and loaded."""
        clean = self._clean_profile_name(name)
        if not clean or os.path.exists(self._profile_path(clean)):
            return
        ref = self._ref(clean)
        cfg = apply_default_bindings(LdConfiguration(profile=ref))
        with open(app_paths.profile_write_path(ref), "w") as f:
            json.dump(cfg.to_JSON(), f, indent=True)
        self._ctl.load_profile(ref)
        self._remember_profile(ref)
        self.notify.emit("Created %s" % clean)
        self.stateChanged.emit()

    @Slot(str, str)
    def duplicateProfile(self, source, name):
        """Copy `source` to `name` and switch to it. Copies the file rather
        than the in-memory config, so unsaved edits are deliberately not
        carried over: what you duplicate is what is on disk."""
        clean = self._clean_profile_name(name)
        if not clean or not source or os.path.exists(self._profile_path(clean)):
            return
        src = self._profile_path(source)
        if not os.path.exists(src):
            return
        with open(src) as f:
            data = json.load(f)
        ref = self._ref(clean)
        data["profile"] = ref
        with open(app_paths.profile_write_path(ref), "w") as f:
            json.dump(data, f, indent=True)
        self._ctl.load_profile(ref)
        self._remember_profile(ref)
        self.notify.emit("Duplicated %s to %s" % (source, clean))
        self.stateChanged.emit()

    @Slot(str, str)
    def renameProfile(self, old, name):
        clean = self._clean_profile_name(name)
        if not clean or not old or clean == old:
            return
        src = self._profile_path(old)
        if not os.path.exists(src) or os.path.exists(self._profile_path(clean)):
            return
        with open(src) as f:
            data = json.load(f)
        ref, old_ref = self._ref(clean), self._ref(old)
        data["profile"] = ref
        with open(app_paths.profile_write_path(ref), "w") as f:
            json.dump(data, f, indent=True)
        # Only a user copy can be removed; a bundled original stays put, so a
        # renamed starter profile leaves the original still available.
        if app_paths.is_user_profile(old_ref):
            os.remove(app_paths.profile_write_path(old_ref))
        self._repoint_bindings(old_ref, ref)
        self._repoint_pages(old, clean)
        if self._ctl.config.profile == old_ref:
            self._ctl.load_profile(ref)
            self._remember_profile(ref)
        self.notify.emit("Renamed %s to %s" % (old, clean))
        self.stateChanged.emit()

    @Slot(str)
    def deleteProfile(self, name):
        """Delete a profile and drop any app bindings that pointed at it, so
        dynamic mode cannot resolve to a profile that no longer exists."""
        if not name:
            return
        ref = self._ref(name)
        if not app_paths.is_user_profile(ref):
            # Nothing writable to delete: this is a bundled profile, which the
            # app must not remove from its own installation.
            print("profiles: '%s' ships with the app and cannot be deleted" % name)
            return
        kept = app_paths.trash(app_paths.profile_write_path(ref),
                               "%s %s.json" % (self.activeApp, name))
        if not kept and os.path.exists(app_paths.profile_write_path(ref)):
            os.remove(app_paths.profile_write_path(ref))
        self._repoint_bindings(ref, None)
        self._repoint_pages(name, None)
        if self._ctl.config.profile == ref:
            remaining = self.profiles
            if remaining:
                self._ctl.load_profile(self._ref(remaining[0]))
        self.notify.emit("Deleted %s%s"
                         % (name, "" if kept else " (no copy kept)"))
        self.stateChanged.emit()

    def _repoint_pages(self, old, new):
        """Follow a profile rename inside the app's pages, or drop the page
        when the profile is gone: a page pointing at nothing would switch the
        device to a blank deck."""
        pages = app_paths.app_pages(self.activeApp)
        changed, kept = False, []
        for page in pages:
            if page["profile"] != old:
                kept.append(page)
                continue
            changed = True
            if new is not None:
                page["profile"] = new
                kept.append(page)
        if changed:
            app_paths.set_app_pages(self.activeApp, kept)

    def _repoint_bindings(self, old, new):
        """Follow a rename, or drop the entry entirely when new is None."""
        changed = False
        kept = []
        for b in self._pm.app_profiles:
            if b.get("profile") != old:
                kept.append(b)
                continue
            changed = True
            if new is not None:
                b["profile"] = new
                kept.append(b)
        self._pm.app_profiles = kept
        if self._pm.default_profile == old:
            self._pm.default_profile = new
            changed = True
        if changed:
            self._pm.save()

    # -- import / export ---------------------------------------------------
    @Slot(str, str, result=str)
    def exportProfile(self, name, file_url):
        """Write `name` to a file the user picked. Returns "" or an error.

        Exports what is on disk, not the in-memory draft, so an export is
        always something that can be re-imported and reproduced.
        """
        path = QUrl(file_url).toLocalFile() if file_url else ""
        if not name or not path:
            return "Nothing to export"
        if not path.lower().endswith(".json"):
            path += ".json"
        try:
            with open(self._profile_path(name)) as f:
                data = json.load(f)
            with open(path, "w") as f:
                json.dump(data, f, indent=True)
        except (OSError, ValueError) as e:
            return "Could not export: %s" % e
        print("exported '%s' to %s" % (name, path))
        self.notify.emit("Exported %s" % os.path.basename(path))
        return ""

    # An application is a folder, so sharing one means sharing the folder.
    # Bundling it into a single file is what makes that something a person can
    # actually send to somebody.
    APP_BUNDLE_KIND = "loupedeckapp.application"

    @Slot(str, result=str)
    def exportApp(self, file_url):
        """Write the whole application, profiles and all, to one file."""
        path = QUrl(file_url).toLocalFile() if file_url else ""
        app = self.activeApp
        if not path:
            return "Nothing to export"
        if not path.lower().endswith(".json"):
            path += ".json"
        names = app_paths.list_profiles(app)
        if not names:
            return "'%s' has no profiles to export" % app
        bundle = {
            "kind": self.APP_BUNDLE_KIND,
            "schema_version": SCHEMA_VERSION,
            "app": app,
            "match": app_paths.app_matches(app),
            "default_profile": app_paths.app_default_profile(app),
            "pages": app_paths.app_pages(app),
            "profiles": {},
        }
        try:
            for name in names:
                with open(self._profile_path(name, app)) as f:
                    bundle["profiles"][name] = json.load(f)
            with open(path, "w") as f:
                json.dump(bundle, f, indent=True)
        except (OSError, ValueError) as e:
            return "Could not export: %s" % e
        print("exported app '%s' (%d profiles) to %s" % (app, len(names), path))
        self.notify.emit("Exported %s" % os.path.basename(path))
        return ""

    @Slot(str, result=str)
    def importApp(self, file_url):
        """Read an exported application in as a new one.

        Validated before anything is written, and never merged into an existing
        app: a name that is taken gets a numbered suffix, so importing someone
        else's Premiere setup cannot quietly overwrite yours.
        """
        path = QUrl(file_url).toLocalFile() if file_url else ""
        if not path:
            return "No file chosen"
        try:
            with open(path) as f:
                bundle = json.load(f)
        except OSError as e:
            return "Could not read the file: %s" % e
        except ValueError:
            return "That file is not valid JSON"

        if not isinstance(bundle, dict) or bundle.get("kind") != self.APP_BUNDLE_KIND:
            return ("That is not an exported application. A single profile "
                    "imports with Import in the profile list.")
        profiles = bundle.get("profiles")
        if not isinstance(profiles, dict) or not profiles:
            return "That application has no profiles in it"
        version = bundle.get("schema_version", 1)
        try:
            if int(version) > SCHEMA_VERSION:
                return ("Application is schema v%s; this build understands v%s"
                        % (version, SCHEMA_VERSION))
        except (TypeError, ValueError):
            return "Application has an unreadable schema_version"
        # Prove every profile loads before any of them appears in the list.
        for name, data in profiles.items():
            if not self._clean_profile_name(name):
                return "Profile name '%s' cannot be used" % name
            try:
                LdConfiguration().from_JSON(data)
            except Exception as e:
                return "Profile '%s' could not be read: %s: %s" % (
                    name, type(e).__name__, e)

        base = self._clean_profile_name(bundle.get("app") or "")
        if not base:
            return "Application has no usable name"
        app, n = base, 2
        while app in app_paths.list_apps():
            app, n = "%s %d" % (base, n), n + 1

        app_paths.ensure_user_app_dir(app)
        for name, data in profiles.items():
            data["profile"] = app_paths.make_ref(app, name)
            with open(app_paths.profile_write_path(app, name), "w") as f:
                json.dump(data, f, indent=True)
        app_paths.set_app_matches(app, bundle.get("match") or [])
        app_paths.set_app_pages(app, bundle.get("pages") or [])
        default = bundle.get("default_profile")
        if default in profiles:
            app_paths.set_app_default_profile(app, default)
        print("imported app '%s' (%d profiles) from %s"
              % (app, len(profiles), path))
        self._browsing_app = app
        self.notify.emit("Imported %s" % app)
        self.stateChanged.emit()
        return ""

    @Slot(str, result=str)
    def importProfile(self, file_url):
        """Read a profile file into the user's profile directory.

        Validates before writing: an unreadable or wrong-shaped file must not
        land in the profile list as something that fails only when loaded. The
        name comes from the file, with a numeric suffix if it is taken, so an
        import never silently overwrites an existing profile.
        """
        path = QUrl(file_url).toLocalFile() if file_url else ""
        if not path:
            return "No file chosen"
        try:
            with open(path) as f:
                data = json.load(f)
        except OSError as e:
            return "Could not read the file: %s" % e
        except ValueError:
            return "That file is not valid JSON"

        if not isinstance(data, dict) or "workspaces" not in data:
            return "That does not look like a profile (no workspaces)"
        version = data.get("schema_version", 1)
        try:
            if int(version) > SCHEMA_VERSION:
                return ("Profile is schema v%s; this build understands v%s"
                        % (version, SCHEMA_VERSION))
        except (TypeError, ValueError):
            return "Profile has an unreadable schema_version"
        # Prove it actually loads before it appears in the list.
        try:
            LdConfiguration().from_JSON(data)
        except Exception as e:
            return "Profile could not be read: %s: %s" % (type(e).__name__, e)

        base = self._clean_profile_name(
            data.get("profile") or os.path.splitext(os.path.basename(path))[0])
        if not base:
            return "Profile has no usable name"
        name, n = base, 2
        while os.path.exists(self._profile_path(name)):
            name, n = "%s %d" % (base, n), n + 1

        ref = self._ref(name)
        data["profile"] = ref
        with open(app_paths.profile_write_path(ref), "w") as f:
            json.dump(data, f, indent=True)
        print("imported %s as '%s'" % (path, ref))
        self._ctl.load_profile(ref)
        self.notify.emit("Imported as %s" % name)
        self.stateChanged.emit()
        return ""

    # -- dynamic mode: focused app -> profile bindings ---------------------
    @Property("QVariantList", notify=stateChanged)
    def appBindings(self):
        """[{app, profile}] for the bindings list, sorted for a stable UI."""
        out = [{"app": b.get("match", {}).get("wm_class", ""),
                "profile": b.get("profile", "")}
               for b in self._pm.app_profiles]
        return sorted(out, key=lambda b: b["app"].lower())

    @Property(bool, notify=stateChanged)
    def activeProfileIsUser(self):
        """False for a profile that ships with the app: it can be edited (which
        writes a user copy) but never deleted from the installation."""
        return app_paths.is_user_profile(self.activeRef or "")

    @Property(str, notify=stateChanged)
    def defaultProfile(self):
        """Used when the focused app has no binding of its own."""
        return self._pm.default_profile or ""

    @Slot(str)
    def setDefaultProfile(self, ref):
        """The fallback is app-wide, so it is named by full reference: which
        app it comes from is part of the answer."""
        self._pm.default_profile = ref or None
        self._pm.save()
        self.stateChanged.emit()

    @Property("QVariantList", notify=stateChanged)
    def deletedItems(self):
        """What is in the trash, newest first, for the recovery list."""
        return app_paths.list_trash()

    @Property(str, notify=stateChanged)
    def trashPath(self):
        return app_paths.trash_dir()

    @Property("QStringList", notify=stateChanged)
    def allProfiles(self):
        """Every profile in every app, as references. For the fallback, which
        is not scoped to the app on screen."""
        return app_paths.list_all_profiles()

    @Property(str, notify=stateChanged)
    def focusedApp(self):
        """The app the bind button would act on: the last focused window that
        was not this one.

        Deliberately not a live poll. Pressing the button focuses our own
        window, so a poll at that moment always answers "Loupedeck Config" and
        you could never bind anything else. (The PyQt5 tree has that bug.)"""
        return self._last_app

    @Slot(str)
    def bindFocusedApp(self, profile_name):
        """Bind the currently focused app to `profile_name` (defaults to the
        loaded profile). Binding replaces any existing entry for that app."""
        wm_class = self._last_app
        if not wm_class:
            print("dynamic: no other app has been focused yet, nothing to bind")
            return
        name = profile_name or self._ctl.config.profile
        if not name:
            return
        self._pm.set_binding(wm_class, name)
        if not self._pm.default_profile:
            # Without a default, switching away from a bound app would leave the
            # device on whatever was last loaded.
            self._pm.default_profile = name
        self._pm.save()
        print("dynamic: bound %s -> %s" % (wm_class, name))
        self.stateChanged.emit()

    @Slot(str)
    def removeBinding(self, wm_class):
        self._pm.remove_binding(wm_class)
        self._pm.save()
        self.stateChanged.emit()

    @Slot(bool)
    def setDynamicMode(self, enabled):
        self._pm.set_dynamic_mode(enabled)
        self._pm.save()
        if enabled:
            # The watcher already runs; just act on where focus is right now so
            # enabling it takes effect without waiting for the next switch.
            self._watcher.start()
            cls, ttl = self._watcher.poll_once()
            self._on_focus_main(cls, ttl)
        self.stateChanged.emit()


DESKTOP_ENTRY = "loupedeckapp.desktop"


def _desktop_entry_installed():
    home = os.path.expanduser("~/.local/share")
    dirs = [os.environ.get("XDG_DATA_HOME") or home]
    dirs += (os.environ.get("XDG_DATA_DIRS")
             or "/usr/local/share:/usr/share").split(":")
    return any(os.path.exists(os.path.join(d, "applications", DESKTOP_ENTRY))
               for d in dirs if d)


def main():
    # QApplication rather than QGuiApplication: the tray icon and its menu come
    # from QtWidgets. It is a QGuiApplication subclass, so QML is unaffected.
    try:
        from PySide6.QtWidgets import QApplication
        app = QApplication(sys.argv)
    except ImportError:                    # PySide6 without QtWidgets: no tray
        app = QGuiApplication(sys.argv)
    app.setApplicationName("Loupedeck Config")
    # Only claim the desktop entry when one is actually installed. Setting it
    # regardless makes the portal complain ("App info not found") on every
    # launch from a checkout, which is where most of the development happens.
    if _desktop_entry_installed():
        app.setDesktopFileName("loupedeckapp")
    app.setWindowIcon(tray.icon())
    moved = app_paths.migrate_legacy()
    if moved:
        print("migrated to %s: %s" % (app_paths.user_dir(), ", ".join(moved)))
    # Profiles used to sit loose in one directory; they belong to an
    # application now. Runs before anything reads the profile list.
    into_apps = app_paths.migrate_to_apps()
    if into_apps:
        print("moved into the %s app: %s"
              % (app_paths.DEFAULT_APP, ", ".join(into_apps)))
    print("%s | %s" % (platform_env.describe(), app_paths.describe()))
    engine = QQmlApplicationEngine()
    backend = Backend()
    engine.rootContext().setContextProperty("backend", backend)
    engine.load(QUrl.fromLocalFile(app_paths.asset_path(os.path.join("qml", "Main.qml"))))
    if not engine.rootObjects():
        sys.exit("Failed to load QML")

    # With a tray, closing the window only hides it, so the app must not quit
    # when the last window goes. Without one it must, or the close button would
    # leave a process running with no way to reach it.
    holder = _TrayHolder(app, backend)
    holder.apply()
    backend.trayConfigChanged.connect(holder.apply)

    app.aboutToQuit.connect(backend.shutdown)
    backend.start()
    if backend.startHidden:
        backend.hideWindow()
    sys.exit(app.exec())


class _TrayHolder:
    """Creates and tears down the tray icon as the setting changes.

    Kept out of Backend so the Qt-widgets dependency stays at the entry point:
    Backend is loaded by the offscreen UI test, which has no tray to talk to.
    """

    def __init__(self, app, backend):
        self._app = app
        self._backend = backend
        self._tray = None

    def apply(self):
        want = self._backend.trayEnabled
        if want and self._tray is None:
            self._tray = tray.Tray(
                self._backend,
                on_show=self._backend.showWindow,
                on_hide=self._backend.hideWindow,
                on_quit=self._quit)
            self._backend.stateChanged.connect(self._tray.refresh)
        elif not want and self._tray is not None:
            self._backend.stateChanged.disconnect(self._tray.refresh)
            self._tray.close()
            self._tray = None
            # Nothing is holding the app up any more, and the window may be
            # hidden: bring it back rather than stranding the process.
            self._backend.showWindow()
        self._app.setQuitOnLastWindowClosed(self._tray is None)

    def _quit(self):
        """Ask, do not take. Quitting from the tray with a draft open would
        throw it away silently, and there is no window on screen to notice.
        QML brings the window back, prompts, and calls Qt.quit() itself."""
        self._backend.quitRequested.emit()


if __name__ == "__main__":
    main()
