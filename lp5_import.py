"""Imports Loupedeck 5 profiles (`.lp5`) as an application here.

A `.lp5` is what the official software exports and the marketplace hands out
for an application: a zip holding

    metadata/LoupedeckPackage.yaml   type: Profile5
    ApplicationInfo.json             which application it is for
    ProfileInfo.json                 the layout and the actions
    ActionImages/<action id>.png     key images, by the action they belong to

ProfileInfo is a .NET object graph serialised with `$type` tags. The parts
that matter:

    macroCommands / macroAdjustments    the profile's own actions, each a list
                                        of generic steps ("$@Generic___@
                                        KeyboardShortcut___Shift+Escape")
    layout.layoutModes[0]
        workspaces                      name + the touch/encoder/wheel page
                                        each one shows
        touchPages[].controls[i]        centre keys, row by row, 4 across
        encoderPages[].controls[i]      knobs: 0-2 left column, 3-5 right
        wheelPages[]                    the CT wheel: a tool plus the dial's
                                        adjustment
    layout.roundPage / squarePage       the CT's buttons, the same on every
                                        workspace

The round buttons switch workspaces here as well, so a workspace lands on the
round button that selected it in the original, and the square buttons follow
the hardware's own order (index 1 is Undo and 4 is Save in both).

What has no equivalent here is reported rather than dropped silently:
long and double presses, more than one page per workspace, the wheel's clock
and other tools, and any step this does not recognise.

Qt-free. Also runs from a terminal:

    .venv/bin/python lp5_import.py Slack_CT_Win.lp5
"""

import json
import os
import re
import sys
import zipfile

import app_paths
import input_backend
import macro
from DeviceProfile import CT_EXTRA_BUTTONS, WHEEL_DISPLAY, WS_KEYS
from LdConfiguration import LdAction, LdConfiguration

SUFFIX = ".lp5"

# The CT's square buttons in Loupedeck's order, which is the order of their
# hardware ids (ct_support: 0x0F home ... 0x1A e).
SQUARE = ["home", "undo", "keyboard", "enter", "save", "fnL",
          "a", "c", "fnR", "b", "d", "e"]

# Knobs, by Loupedeck's encoder index.
ENCODERS = ["enc1L", "enc2L", "enc3L", "enc1R", "enc2R", "enc3R"]

# Centre keys are 4 across on the CT and the Live.
TOUCH_COLUMNS = 4

# Loupedeck's key names -> this app's (input_backend.KEY). Letters and digits
# come as KeyA / Key7 and are handled by pattern; these are the rest.
_KEYS = {
    "controlorcommand": "ctrl", "control": "ctrl", "ctrl": "ctrl",
    "command": "super", "windows": "super", "win": "super", "meta": "super",
    "shift": "shift", "alt": "alt", "altoroption": "alt", "option": "alt",
    "arrowup": "up", "arrowdown": "down", "arrowleft": "left",
    "arrowright": "right", "up": "up", "down": "down", "left": "left",
    "right": "right",
    "escape": "escape", "return": "enter", "enter": "enter", "tab": "tab",
    "space": "space", "backspace": "backspace", "delete": "delete",
    "insert": "insert", "home": "home", "end": "end", "pageup": "pageup",
    "pagedown": "pagedown",
    # The numeric keypad has no names here; the main-row keys do the same in
    # every application this has met (zoom in and out, mostly).
    "add": "equal", "subtract": "minus", "plus": "equal", "minus": "minus",
    "equal": "equal", "comma": "comma", "period": "period", "slash": "slash",
    "backslash": "backslash", "semicolon": "semicolon",
    "quote": "apostrophe", "backquote": "grave",
    "bracketleft": "bracketleft", "bracketright": "bracketright",
    "oemminus": "minus", "oemplus": "equal", "oemcomma": "comma",
    "oemperiod": "period", "equals": "equal",
    # Windows' OEM keys, by their US-layout meaning (VK_OEM_1..7).
    "oem1": "semicolon", "oem2": "slash", "oem3": "grave", "oem4": "bracketleft",
    "oem5": "backslash", "oem6": "bracketright", "oem7": "apostrophe",
    "volumemute": "mute", "volumeup": "volumeup", "volumedown": "volumedown",
}

# Built-in actions of the default Windows/macOS plugin that mean the same
# thing here. Adjustments are (left, right).
_DEFAULT_COMMANDS = {
    "resetvolume": ("hotkey", "mute"),
    "mute": ("hotkey", "mute"),
    "playpause": ("media", "play-pause"),
    "nexttrack": ("media", "next"),
    "previoustrack": ("media", "previous"),
    "stop": ("media", "stop"),
}
# Mouse actions -> this app's "mouse" values (input_backend.mouse). A key
# held around one comes as the argument: "@MouseClick___AltLeft".
_MOUSE_COMMANDS = {
    "mouseclick": "click", "mousedoubleclick": "doubleclick",
    "mouseclickright": "rightclick", "mouserightclick": "rightclick",
    "mouseclickmiddle": "middleclick", "mousemiddleclick": "middleclick",
}
# Knobs: turning left is up (or left), right down (or right), as the wheel.
_MOUSE_ADJUSTMENTS = {
    "mousewheel": ("scroll-up", "scroll-down"),
    "mousedraganddropvertically": ("drag-up", "drag-down"),
    "mousedraganddrophorizontally": ("drag-left", "drag-right"),
    "mousemovevertical": ("move-up", "move-down"),
    "mousemovehorizontal": ("move-left", "move-right"),
}
_HELD = {"control": "ctrl", "ctrl": "ctrl", "controlorcommand": "ctrl", "alt": "alt",
         "altoroption": "alt", "option": "alt", "shift": "shift", "command": "super",
         "windows": "super", "win": "super", "meta": "super"}


def _held(arg):
    """'ControlLeft' -> 'ctrl+': the keys held around a mouse action."""
    out = []
    for part in re.split(r"[+,]", str(arg or "")):
        name = re.sub(r"(left|right)$", "", part.strip().lower().replace(" ", ""))
        if _HELD.get(name) and _HELD[name] not in out:
            out.append(_HELD[name])
    return "".join(m + "+" for m in out)


# Knobs that press arrow keys: turning left is left (or up), right is right
# (or down), as the mouse wheel is.
_ARROW_ADJUSTMENTS = {
    "horizontalarrows": ("left", "right"),
    "verticalarrows": ("up", "down"),
}
_DEFAULT_ADJUSTMENTS = {
    "volume": (("hotkey", "volumedown"), ("hotkey", "volumeup")),
}

# Windows shortcuts that are something else on Linux and macOS, keyed by what
# the macro is called so an application's own use of the combo is left alone.
# Chromium and Electron (Slack, Discord, VS Code...) redo with Ctrl+Shift+Z
# off Windows; Ctrl+Y does nothing there.
_OFF_WINDOWS = {
    ("redo", "ctrl+y"): "ctrl+shift+z",
}

_STEP_RE = re.compile(r"^\$([^_]+)___(.*)$")

# An empty slot: "@None", and "@None2" on a knob.
_EMPTY = re.compile(r"^none\d*$")


def parse_ref(ref):
    """("generic", "macroadjustment", arg) from an action reference.

    Profiles spell the same thing several ways: "$@Generic___@MacroAdjustment
    ___id" from one version, "$@generic___@Macro adjustment___id" from
    another, "@Keyboard shortcut" beside "@KeyboardShortcut". Source and
    kind come back lower-cased, without "@" and spaces; arg as it was.
    None when it is not a reference at all."""
    m = _STEP_RE.match(ref or "")
    if not m:
        return None
    kind, _, arg = m.group(2).partition("___")
    norm = lambda t: t.lstrip("@").replace(" ", "").lower()
    return norm(m.group(1)), norm(kind), arg


# -- reading -------------------------------------------------------------------
def read(path):
    """(profile, application, images, error). `images` maps a lower-cased
    action id to the PNG bytes for it."""
    try:
        zf = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as e:
        return None, None, None, "%s is not a Loupedeck profile (%s)" % (
            os.path.basename(path), e)
    with zf:
        names = set(zf.namelist())
        if "ProfileInfo.json" not in names:
            return None, None, None, ("%s has no ProfileInfo.json, so it is not "
                                      "a Loupedeck 5 profile" % os.path.basename(path))
        try:
            profile = json.loads(zf.read("ProfileInfo.json").decode("utf-8-sig"))
            app = (json.loads(zf.read("ApplicationInfo.json").decode("utf-8-sig"))
                   if "ApplicationInfo.json" in names else {})
        except ValueError as e:
            return None, None, None, "the profile could not be read: %s" % e
        images = {}
        for name in names:
            if name.startswith("ActionImages/") and name.lower().endswith(".png"):
                action_id = os.path.splitext(os.path.basename(name))[0]
                images[action_id.lower()] = zf.read(name)
    return profile, app, images, ""


# -- converting ----------------------------------------------------------------
def convert_combo(text):
    """'Shift+ControlOrCommand+KeyX' -> 'shift+ctrl+x', or None."""
    out = []
    for part in str(text or "").split("+"):
        p = part.strip()
        low = p.lower().replace(" ", "")     # "arrow up" as well as "ArrowUp"
        if re.fullmatch(r"key[a-z]", low):
            name = low[3]
        elif re.fullmatch(r"(key|digit|numpad)[0-9]", low):
            name = low[-1]
        elif re.fullmatch(r"f([1-9]|1[0-9]|2[0-4])", low):
            name = low
        else:
            name = _KEYS.get(low)
        if not name:
            return None
        out.append(name)
    combo = "+".join(out)
    try:
        input_backend._parse_combo(combo)
    except (KeyError, ValueError):
        return None
    return combo


class _Converter:
    def __init__(self, profile):
        self.profile = profile
        self.notes = []
        self.macros = {m.get("name"): m for m in profile.get("macroCommands") or []}
        self.adjusts = {m.get("name"): m for m in profile.get("macroAdjustments") or []}
        # Workspace name -> the key that selects it here; set by convert()
        # once workspaces have their buttons.
        self.workspace_keys = {}
        # Workspace name -> its pages of keys, in order, and the workspace
        # being converted, for keys that turn to a page.
        self.page_names = {}
        self.current_ws = None

    def note(self, text):
        if text not in self.notes:
            self.notes.append(text)

    def _steps(self, steps, label, depth=0):
        """Generic steps -> list of macro lines, or None if any is unknown.
        A step may run another of the profile's macros; its steps are put
        in its place (a few levels deep, so a macro that runs itself ends)."""
        lines = []
        for step in steps or []:
            if not step:
                continue
            source, kind, arg = parse_ref(step) or ("", "", "")
            if source == "generic" and _EMPTY.match(kind):
                continue
            if source == "generic" and kind == "macro" and arg in self.macros and depth < 4:
                inner = self._steps(self.macros[arg].get("actions"), label, depth + 1)
                if inner is None:
                    return None
                lines += inner
                continue
            if source == "generic" and kind == "keyboardshortcut":
                combo = convert_combo(arg)
                if combo is None:
                    self.note("%s: the shortcut %s has no equivalent key here" % (label, arg))
                    return None
                lines.append("hotkey %s" % combo)
            elif source == "generic" and kind == "typetext":
                if arg:
                    lines.append("text %s" % arg)
            elif source == "generic" and kind in _MOUSE_COMMANDS:
                lines.append("mouse %s%s" % (_held(arg), _MOUSE_COMMANDS[kind]))
            elif source == "generic" and kind in ("delay", "wait"):
                try:
                    lines.append("wait %d" % int(float(arg)))
                except ValueError:
                    pass
            else:
                self.note("%s: %r is not something this app can do" % (label, step))
                return None
        return lines

    def command(self, ref, label_hint=""):
        """A press action reference -> (a_type, value, label) or None."""
        if not ref:
            return None
        parsed = parse_ref(ref)
        if not parsed:
            self.note("an action %r was not understood" % ref)
            return None
        source, kind, arg = parsed
        m = _STEP_RE.match(ref)
        rest, raw_source = m.group(2), m.group(1)
        if source == "generic" and _EMPTY.match(kind):
            return None                  # an empty slot
        if source == "generic" and kind == "goback":
            return ("back", "", label_hint or "Back")
        if source == "generic" and kind == "changetouchpage":
            parts = arg.split("|")
            ws_name, page_name = (parts[-2], parts[-1]) if len(parts) >= 2 else ("", "")
            names = self.page_names.get(ws_name) or []
            if page_name in names:
                number = names.index(page_name) + 1
                if ws_name == self.current_ws:
                    return ("page", str(number), label_hint or "Page %d" % number)
                key = self.workspace_keys.get(ws_name)
                if key:
                    self.note("a key turns to page %d of another workspace; it switches to "
                              "that workspace" % number)
                    return ("workspace", key, label_hint or "Workspace")
            self.note("a key turns to a page that was not imported")
            return None
        if source == "generic" and kind == "changeworkspace":
            key = self.workspace_keys.get(arg.rsplit("|", 1)[-1])
            if key:
                return ("workspace", key, label_hint or "Workspace")
            self.note("a key switches to a workspace that was not imported")
            return None
        if source == "generic" and kind == "macro":
            mac = self.macros.get(arg)
            if mac is None:
                self.note("a key refers to a macro the profile does not have")
                return None
            label = (mac.get("displayName") or "").strip()
            lines = self._steps(mac.get("actions"), label or "a macro")
            if not lines:
                return None
            if len(lines) == 1 and lines[0].startswith("text "):
                return ("text", lines[0][len("text "):], label)
            if len(lines) == 1 and lines[0].startswith("mouse "):
                return ("mouse", lines[0][len("mouse "):], label)
            if len(lines) == 1 and lines[0].startswith("hotkey "):
                combo = lines[0][len("hotkey "):]
                native = _OFF_WINDOWS.get((label.lower(), combo))
                if native and not sys.platform.startswith("win"):
                    self.note("%s: Windows' %s is %s here, so that is what it sends"
                              % (label, combo, native))
                    combo = native
                return ("hotkey", combo, label)
            # Several keystrokes need the waits a person would leave.
            return ("macro", "\nwait 50\n".join(lines), label)
        if source == "generic" and kind == "typetext" and arg:
            return ("text", arg, label_hint or arg)
        if source == "generic" and kind in _MOUSE_COMMANDS:
            value = _held(arg) + _MOUSE_COMMANDS[kind]
            return ("mouse", value, label_hint or _nice(rest.lstrip("@").split("___")[0]))
        if source == "generic" and kind == "keyboardshortcut":
            combo = convert_combo(arg)
            if combo:
                return ("hotkey", combo, label_hint or combo)
            self.note("the shortcut %s has no equivalent key here" % arg)
            return None
        if source.startswith("default"):
            mapped = _DEFAULT_COMMANDS.get(rest.lower())
            if mapped:
                return (mapped[0], mapped[1], _nice(rest))
        self.note("%s (from %s) is not something this app can do" % (_nice(rest), raw_source))
        return None

    def adjustment(self, ref):
        """A rotate action reference -> ((type, value), (type, value), label)."""
        if not ref:
            return None
        parsed = parse_ref(ref)
        if not parsed:
            return None
        source, kind, arg = parsed
        m = _STEP_RE.match(ref)
        rest, raw_source = m.group(2), m.group(1)
        if source == "generic" and _EMPTY.match(kind):
            return None
        if source == "generic" and kind in _ARROW_ADJUSTMENTS:
            left, right = _ARROW_ADJUSTMENTS[kind]
            return ("hotkey", left), ("hotkey", right), _nice(rest.lstrip("@"))
        if source == "generic" and kind in _MOUSE_ADJUSTMENTS:
            return self._mouse_knob(kind, arg) + (_nice(rest.lstrip("@").split("___")[0]),)
        if source == "generic" and kind == "macroadjustment":
            adj = self.adjusts.get(arg)
            if adj is None:
                self.note("a knob refers to an adjustment the profile does not have")
                return None
            label = (adj.get("displayName") or "").strip()
            left = self._side(adj.get("actionsLeft"), label, "up")
            right = self._side(adj.get("actionsRight"), label, "down")
            if left is None or right is None:
                return None
            return left, right, label
        if source.startswith("default"):
            mapped = _DEFAULT_ADJUSTMENTS.get(rest.lower())
            if mapped:
                return mapped[0], mapped[1], _nice(rest)
        self.note("the knob action %s (from %s) is not something this app can do"
                  % (_nice(rest), raw_source))
        return None

    @staticmethod
    def _mouse_knob(kind, arg):
        """((type, value), (type, value)) for a mouse knob, left then right.
        The plain wheel stays a scroll action, as it always imported."""
        held = _held(arg)
        left, right = _MOUSE_ADJUSTMENTS[kind]
        if kind == "mousewheel" and not held:
            return ("scroll", "up"), ("scroll", "down")
        return ("mouse", held + left), ("mouse", held + right)

    def _side(self, steps, label, wheel_direction):
        """One direction of an adjustment. The mouse wheel is the one generic
        step that is a direction rather than a key: turning left scrolls up,
        right scrolls down, as it does in the official software."""
        steps = [s for s in steps or [] if s]
        if len(steps) == 1 and steps[0].lower().endswith("@mousewheel"):
            return ("scroll", wheel_direction)
        parsed = parse_ref(steps[0]) if len(steps) == 1 else None
        if parsed and parsed[0] == "generic" and parsed[1] in _MOUSE_ADJUSTMENTS:
            back, forward = self._mouse_knob(parsed[1], parsed[2])
            return back if wheel_direction == "up" else forward
        if parsed and parsed[0] == "generic" and parsed[1] in _ARROW_ADJUSTMENTS:
            back, forward = _ARROW_ADJUSTMENTS[parsed[1]]
            return ("hotkey", back if wheel_direction == "up" else forward)
        lines = self._steps(steps, label)
        if not lines:
            return None
        if len(lines) == 1 and lines[0].startswith("hotkey "):
            return ("hotkey", lines[0][len("hotkey "):])
        return ("macro", "\nwait 50\n".join(lines))


def _nice(name):
    """'ResetVolume' -> 'Reset volume'."""
    words = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", str(name)).split()
    return " ".join(words[:1] + [w.lower() for w in words[1:]]) if words else ""


def _label(ws, slot, text):
    if text:
        ws.labels[slot] = {"text": text, "pos": "bottom", "mode": "bar"}


def convert(profile, images, image_dir, ref):
    """Build an LdConfiguration from a parsed profile. Images are written to
    `image_dir`. Returns (cfg, notes)."""
    conv = _Converter(profile)
    cfg = LdConfiguration(profile=ref)
    layout = profile.get("layout") or {}
    modes = layout.get("layoutModes") or []
    if not modes:
        conv.note("the profile has no layout")
        return cfg, conv.notes
    if len(modes) > 1:
        conv.note("only the first of %d application modes was imported" % len(modes))
    mode = modes[0]
    pages = {}
    for kind in ("touchPages", "encoderPages", "wheelPages"):
        for page in mode.get(kind) or []:
            pages[page.get("name")] = page

    # Workspaces go to the round button that selected them; any the round
    # buttons do not mention fill the remaining slots in order.
    workspaces = mode.get("workspaces") or []
    by_name = {w.get("name"): w for w in workspaces}
    slot_of = {}
    round_controls = (layout.get("roundPage") or {}).get("controls") or []
    for i, control in enumerate(round_controls[:len(WS_KEYS)]):
        ref_ = (control or {}).get("pressAction") or ""
        parsed = parse_ref(ref_)
        if parsed and parsed[:2] == ("generic", "changeworkspace"):
            target = ref_.rsplit("|", 1)[-1]
            if target in by_name and target not in slot_of:
                slot_of[target] = i
        elif parsed and parsed[:2] == ("generic", "none"):
            pass
        elif ref_:
            conv.note("round button %d did something other than switch workspace, "
                      "which those buttons always do here" % (i + 1))
    free = [i for i in range(len(WS_KEYS)) if i not in slot_of.values()]
    home = mode.get("homeWorkspaceName")
    order = sorted(workspaces, key=lambda w: w.get("name") != home)
    for w in order:
        if w.get("name") not in slot_of:
            if not free:
                conv.note("workspace %r did not fit: there are %d workspace buttons"
                          % (w.get("displayName"), len(WS_KEYS)))
                continue
            slot_of[w.get("name")] = free.pop(0)
    conv.workspace_keys = {name: WS_KEYS[i] for name, i in slot_of.items()}
    conv.page_names = {w.get("name"): list(w.get("touchPageNames") or []) for w in workspaces}

    square = (layout.get("squarePage") or {}).get("controls") or []
    os.makedirs(image_dir, exist_ok=True)
    written = {}

    def image_for(ref_):
        """Save the image that goes with an action, once; its path or ""."""
        if not ref_:
            return ""
        data = images.get(ref_.lower())
        if data is None:
            return ""
        if ref_ not in written:
            name = re.sub(r"[^A-Za-z0-9]+", "_", ref_.split("___")[-1]) + ".png"
            path = os.path.join(image_dir, name)
            with open(path, "wb") as f:
                f.write(data)
            written[ref_] = path
        return written[ref_]

    for w in workspaces:
        if w.get("name") not in slot_of:
            continue
        ws = cfg.workspaces[slot_of[w["name"]]]
        ws.name = (w.get("displayName") or "").strip()
        where = ws.name or "a workspace"
        conv.current_ws = w.get("name")
        # Pages of keys come across as pages (made below); knobs and the
        # wheel have one page here.
        for kind in ("encoderPageNames", "wheelPageNames"):
            if len(w.get(kind) or []) > 1:
                conv.note("%s has %d %s; only the first was imported" % (
                    where, len(w[kind]),
                    {"encoderPageNames": "pages of knobs",
                     "wheelPageNames": "wheel pages"}[kind]))

        touch = pages.get((w.get("touchPageNames") or [None])[0]) or {}
        for i, control in enumerate(touch.get("controls") or []):
            control = control or {}
            row, col = divmod(i, TOUCH_COLUMNS)
            slot = "tb%d%d" % (row + 1, col + 1)
            _bind_press(conv, ws, slot, control, where, image_for, with_image=True)

        enc = pages.get((w.get("encoderPageNames") or [None])[0]) or {}
        for i, control in enumerate((enc.get("controls") or [])[:len(ENCODERS)]):
            control = control or {}
            slot = ENCODERS[i]
            _bind_press(conv, ws, slot, control, where, image_for, with_image=False)
            rot = conv.adjustment(control.get("rotateAction"))
            if rot:
                left, right, label = rot
                ws.actions[slot + "-l"] = LdAction(action_type=left[0], action=left[1])
                ws.actions[slot + "-r"] = LdAction(action_type=right[0], action=right[1])
                # The CT's side strips sit beside the knobs, and the official
                # software names each knob there; the cell next to it does
                # the same here. A cell with its own action keeps its label.
                cell = "dis%s%s" % (slot[3], slot[4])
                bound = ws.actions.get(cell)
                if label and (bound is None or bound.a_type == "none"):
                    _label(ws, cell, label)

        wheel = pages.get((w.get("wheelPageNames") or [None])[0]) or {}
        params = wheel.get("parameters") or {}
        rot = conv.adjustment(params.get("adjustment"))
        if rot:
            left, right, label = rot
            ws.actions["dial-l"] = LdAction(action_type=left[0], action=left[1])
            ws.actions["dial-r"] = LdAction(action_type=right[0], action=right[1])
        if wheel.get("templateName"):
            tool = _nice(re.sub(r"^WheelTool", "", wheel["templateName"]))
            conv.note("the wheel screen's %s has no equivalent; the dial still "
                      "turns as it did" % (tool.lower() or "tool"))
        # The workspace's name on the wheel, so the round screen says where
        # you are rather than nothing.
        if ws.name:
            ws.labels[WHEEL_DISPLAY] = {"text": ws.name, "pos": "middle", "mode": "over"}

        for i, control in enumerate(square[:len(SQUARE)]):
            _bind_press(conv, ws, SQUARE[i], control or {}, "the square buttons",
                        image_for, with_image=False)

        # Further pages of keys, turned by swiping as in the official
        # software; each has this workspace's knobs and buttons.
        for page_name in (w.get("touchPageNames") or [])[1:]:
            page = ws.new_page()
            for i, control in enumerate((pages.get(page_name) or {}).get("controls") or []):
                row, col = divmod(i, TOUCH_COLUMNS)
                _bind_press(conv, page, "tb%d%d" % (row + 1, col + 1), control or {}, where,
                            image_for, with_image=True)
            ws.pages.append(page)

    for slot in ("fnL", "fnR"):
        for ws in cfg.workspaces:
            act = ws.actions.get(slot)
            if act is not None and act.a_type != "none":
                conv.note("the %s button had its own action, which replaces it "
                          "being a fn key here" % slot)
    return cfg, conv.notes


def _bind_press(conv, ws, slot, control, where, image_for, with_image):
    """Press, and fn+press, of one control."""
    ref_ = control.get("pressAction")
    got = conv.command(ref_)
    if got:
        a_type, value, label = got
        ws.actions[slot] = LdAction(action_type=a_type, action=value, summary=label)
        if with_image:
            path = image_for(ref_)
            if path:
                ws.images[slot] = path
            _label(ws, slot, label)
    fn = conv.command(control.get("fnPressAction"))
    if fn:
        ws.set_fn_action(slot, LdAction(action_type=fn[0], action=fn[1], summary=fn[2]))
    for extra, what in (("longPressAction", "long press"),
                        ("doublePressAction", "double press"),
                        ("fnLongPressAction", "fn long press"),
                        ("fnDoublePressAction", "fn double press")):
        if control.get(extra):
            conv.note("%s: a %s on %s was skipped (only presses are supported)"
                      % (where, what, slot))


def validate(cfg):
    """Every hotkey and macro is one this app accepts. Problems, as text."""
    problems = []
    for ws in cfg.workspaces:
        bound = list(ws.actions.items()) + list((ws.fn_actions or {}).items())
        for slot, act in bound:
            if act is None or act.a_type == "none":
                continue
            if act.a_type == "hotkey":
                try:
                    input_backend._parse_combo(act.action)
                except (KeyError, ValueError) as e:
                    problems.append("%s: %s (%s)" % (slot, act.action, e))
            elif act.a_type == "macro":
                _steps, errors = macro.parse(act.action)
                problems += ["%s: line %d %s" % (slot, n, msg) for n, msg in errors]
            elif act.a_type == "mouse":
                try:
                    input_backend.parse_mouse(act.action)
                except ValueError as e:
                    problems.append("%s: %s" % (slot, e))
    return problems


# -- installing ----------------------------------------------------------------
def _match_key(app):
    """The window class to switch on: the installed application's own when
    it is on this machine, else the process name the profile names."""
    wanted = {str(app.get(k) or "").lower()
              for k in ("name", "displayName", "processOrBundleName")} - {""}
    try:
        import installed_apps
        for entry in installed_apps.list_installed():
            if str(entry.get("name", "")).lower() in wanted:
                return entry.get("match") or ""
    except Exception:
        pass
    return app.get("processOrBundleName") or app.get("name") or ""


def import_lp5(path, app_name=None):
    """Install a .lp5 as an application. Returns (app, notes, error).

    An application of the same name gets the profile added (or replaced)
    rather than being overwritten wholesale, so importing into an app you
    already set up keeps its other profiles.
    """
    profile, app_info, images, error = read(path)
    if error:
        return "", [], error
    app = (app_name or app_info.get("displayName") or profile.get("displayName")
           or os.path.splitext(os.path.basename(path))[0]).strip()
    app = re.sub(r"[/\\]", "-", app)
    name = (profile.get("displayName") or app).strip()
    name = re.sub(r"[/\\]", "-", name) or app
    ref = app_paths.make_ref(app, name)
    image_dir = os.path.join(app_paths.ensure_user_app_dir(app), "images")
    cfg, notes = convert(profile, images, image_dir, ref)
    problems = validate(cfg)
    if problems:
        return "", notes, "the converted profile has bindings this app refuses:\n" + \
            "\n".join(problems)
    device = str(profile.get("deviceType") or "")
    if device and device != "Loupedeck20":
        notes.insert(0, "it was made for %s rather than the CT/Live family; the "
                     "layout may not line up" % device)
    with open(app_paths.profile_write_path(ref), "w") as f:
        json.dump(cfg.to_JSON(), f, indent=True, sort_keys=True)
        f.write("\n")
    meta = app_paths.read_app_meta(app)
    if not meta.get("match"):
        match = _match_key(app_info)
        if match:
            app_paths.set_app_matches(app, [match])
    if not meta.get("default_profile"):
        app_paths.set_app_default_profile(app, name)
    return app, notes, ""


def main(argv):
    if not argv:
        print("usage: lp5_import.py PROFILE.lp5 [APP NAME]")
        return 2
    app, notes, error = import_lp5(argv[0], argv[1] if len(argv) > 1 else None)
    if error:
        print(error)
        return 1
    print("imported into application %r (%s)" % (app, app_paths.user_app_dir(app)))
    for n in notes:
        print("  note: %s" % n)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
