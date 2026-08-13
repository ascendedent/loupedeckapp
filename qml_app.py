"""PySide6 + QML front-end (M4).

New UI shell that reuses the decoupled core (DeviceProfile, LdConfiguration,
input_backend, window_watcher, profile_manager) and drives the real device via
DeviceController. Runs alongside the existing PyQt5 app.py during migration.

Run:  QT_QPA_PLATFORM=xcb .venv/bin/python qml_app.py
"""

import os
import sys
import glob
import json

from PySide6.QtCore import QObject, Property, Signal, Slot, QUrl, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

import action_library
import app_paths
import input_backend
import settings as settings_mod
import platform_env
import window_watcher
import system_shortcuts
from profile_manager import ProfileManager
from device_controller import DeviceController
from LdConfiguration import LdConfiguration, SCHEMA_VERSION
from DeviceProfile import WHEEL_DISPLAY, WS_KEYS
from LdConfiguration import (ROTATE_CONTROLS, TUNING_PRESETS, DEFAULT_TUNING,
                             preset_to_tuning, tuning_to_preset)


class Backend(QObject):
    stateChanged = Signal()
    selectionChanged = Signal()
    # private cross-thread marshals -> delivered on the Qt main thread
    _marshal = Signal(str)
    _focusSig = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._selected = ""
        self._clipboard = None   # copied control function (see copyControl)
        self._sys_shortcuts = None   # lazily-read KDE shortcuts (cached)
        # Last focused window that was not this app. Clicking "bind" focuses our
        # own window first, so polling at click time would always answer
        # "Loupedeck Config"; remember what you were actually in instead.
        self._last_app = ""
        # A profile switch dynamic mode wanted to make while edits were unsaved.
        self._pending_profile = ""
        self._ctl = DeviceController(on_state=lambda kind: self._marshal.emit(kind))
        self._pm = ProfileManager(app_paths.dynamic_profiles_path())
        self._settings = settings_mod.Settings()
        self._ctl.brightness = self._settings.brightness
        self._watcher = window_watcher.get_watcher(
            on_change=lambda c, t: self._focusSig.emit(c, t))
        self._marshal.connect(self._on_state_main, Qt.QueuedConnection)
        self._focusSig.connect(self._on_focus_main, Qt.QueuedConnection)

    # -- lifecycle ---------------------------------------------------------
    # Our own window, which is never a useful thing to bind.
    SELF_WM_CLASS = "loupedeck config"

    def start(self):
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
        self.stateChanged.emit()

    def _on_focus_main(self, wm_class, title):
        if wm_class and wm_class.strip().lower() != self.SELF_WM_CLASS:
            if wm_class != self._last_app:
                self._last_app = wm_class
                self.stateChanged.emit()      # refresh the bind button's label
        if not self._pm.dynamic_mode:
            return
        name = self._pm.resolve(wm_class)
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

    @Property("QVariantMap", notify=stateChanged)
    def inputHealth(self):
        """{ok, name, detail} for the input backend. A backend that cannot
        inject otherwise fails invisibly: every action appears to do nothing
        and the only clue is on stderr."""
        ok, name, detail = input_backend.health()
        return {"ok": bool(ok), "name": name, "detail": detail}

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

    @Property(str, notify=stateChanged)
    def activeProfile(self):
        return self._ctl.config.profile or "(none)"

    @Property("QStringList", notify=stateChanged)
    def profiles(self):
        return app_paths.list_profiles()

    @Property("QStringList", constant=True)
    def actionCategories(self):
        return list(action_library.CATEGORIES)

    @Property("QVariantList", constant=True)
    def actionLibrary(self):
        return [{"category": c, "label": l, "type": t, "value": v}
                for (c, l, t, v) in self.ACTION_LIBRARY]

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

    @Property(int, notify=stateChanged)
    def menuDepth(self):
        return len(self._ctl.submenu_stack)

    # -- control selection + action editing (inspector) --------------------
    ACTION_TYPES = ["none", "command", "hotkey", "text", "scroll", "media"]

    # Per-platform, from action_library: the applications differ by desktop.
    ACTION_LIBRARY = action_library.default_library()

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

    @Property(int, notify=stateChanged)
    def menuDepth(self):
        return len(self._ctl.submenu_stack)

    # -- control selection + action editing (inspector) --------------------
    ACTION_TYPES = ["none", "command", "hotkey", "text", "scroll", "media"]

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

    @Property(str, notify=selectionChanged)
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
            out.append({"slot": slot, "label": label, "type": a_type, "value": value})
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
    }

    @Property("QVariantMap", constant=True)
    def valueOptions(self):
        """action type -> [{label, value}] for types the inspector should
        present as a dropdown."""
        return dict(self.VALUE_OPTIONS)

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
        self.stateChanged.emit()

    # -- slots -------------------------------------------------------------
    @Slot(str)
    def loadProfile(self, name):
        self._ctl.load_profile(name)
        self.stateChanged.emit()

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

    def _profile_path(self, name):
        """Where a profile *would* be read from, user copy preferred."""
        return app_paths.profile_read_path(name)

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

    @Slot(str)
    def createProfile(self, name):
        """New empty profile, saved to disk and loaded."""
        clean = self._clean_profile_name(name)
        if not clean or os.path.exists(self._profile_path(clean)):
            return
        cfg = LdConfiguration(profile=clean)
        with open(app_paths.profile_write_path(clean), "w") as f:
            json.dump(cfg.to_JSON(), f, indent=True)
        self._ctl.load_profile(clean)
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
        data["profile"] = clean
        with open(app_paths.profile_write_path(clean), "w") as f:
            json.dump(data, f, indent=True)
        self._ctl.load_profile(clean)
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
        data["profile"] = clean
        with open(app_paths.profile_write_path(clean), "w") as f:
            json.dump(data, f, indent=True)
        # Only a user copy can be removed; a bundled original stays put, so a
        # renamed starter profile leaves the original still available.
        if app_paths.is_user_profile(old):
            os.remove(app_paths.profile_write_path(old))
        self._repoint_bindings(old, clean)
        if self._ctl.config.profile == old:
            self._ctl.load_profile(clean)
        self.stateChanged.emit()

    @Slot(str)
    def deleteProfile(self, name):
        """Delete a profile and drop any app bindings that pointed at it, so
        dynamic mode cannot resolve to a profile that no longer exists."""
        if not name:
            return
        if not app_paths.is_user_profile(name):
            # Nothing writable to delete: this is a bundled profile, which the
            # app must not remove from its own installation.
            print("profiles: '%s' ships with the app and cannot be deleted" % name)
            return
        os.remove(app_paths.profile_write_path(name))
        self._repoint_bindings(name, None)
        if self._ctl.config.profile == name:
            remaining = self.profiles
            if remaining:
                self._ctl.load_profile(remaining[0])
        self.stateChanged.emit()

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
            with open(app_paths.profile_read_path(name)) as f:
                data = json.load(f)
            with open(path, "w") as f:
                json.dump(data, f, indent=True)
        except (OSError, ValueError) as e:
            return "Could not export: %s" % e
        print("exported '%s' to %s" % (name, path))
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
        while os.path.exists(app_paths.profile_read_path(name)):
            name, n = "%s %d" % (base, n), n + 1

        data["profile"] = name
        with open(app_paths.profile_write_path(name), "w") as f:
            json.dump(data, f, indent=True)
        print("imported %s as '%s'" % (path, name))
        self._ctl.load_profile(name)
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
        return app_paths.is_user_profile(self._ctl.config.profile or "")

    @Property(str, notify=stateChanged)
    def defaultProfile(self):
        """Used when the focused app has no binding of its own."""
        return self._pm.default_profile or ""

    @Slot(str)
    def setDefaultProfile(self, name):
        self._pm.default_profile = name or None
        self._pm.save()
        self.stateChanged.emit()

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


def main():
    app = QGuiApplication(sys.argv)
    app.setApplicationName("Loupedeck Config")
    moved = app_paths.migrate_legacy()
    if moved:
        print("migrated to %s: %s" % (app_paths.user_dir(), ", ".join(moved)))
    print("%s | %s" % (platform_env.describe(), app_paths.describe()))
    engine = QQmlApplicationEngine()
    backend = Backend()
    engine.rootContext().setContextProperty("backend", backend)
    engine.load(QUrl.fromLocalFile(app_paths.asset_path(os.path.join("qml", "Main.qml"))))
    if not engine.rootObjects():
        sys.exit("Failed to load QML")
    app.aboutToQuit.connect(backend.shutdown)
    backend.start()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
