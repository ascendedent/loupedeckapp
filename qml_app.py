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
import system_shortcuts
from profile_manager import ProfileManager
from device_controller import DeviceController
from DeviceProfile import WHEEL_DISPLAY, WS_KEYS

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
        self._clipboard = None   # copied control function (see copyControl)
        self._sys_shortcuts = None   # lazily-read KDE shortcuts (cached)
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

    @Property("QVariantList", constant=True)
    def actionLibrary(self):
        return [{"category": c, "label": l, "type": t, "value": v}
                for (c, l, t, v) in self.ACTION_LIBRARY]

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
        """Label fields for the inspector — ignores the on/off toggle and image
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
        self._ctl.set_action(slot_key, a_type, value)
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

    @Slot()
    def save(self):
        self._ctl.save()
        self.stateChanged.emit()

    @Slot()
    def revert(self):
        self._ctl.revert()
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
