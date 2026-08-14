import json, os
import app_paths
import input_backend
import macro
import virtual_keyboard
from DeviceProfile import CT_EXTRA_BUTTONS, WHEEL_DISPLAY, WS_KEYS

SCHEMA_VERSION = 8

# Profile locations come from app_paths: reads prefer the user's copy and fall
# back to the bundled one, writes always go to the user directory. This was once
# the literal "./Profiles/", which broke whenever the app was launched from
# anywhere but the repo root.

# Config action-key names for the CT dial (decoupled from the device id
# "knobCT"); these must match the lookups in DeviceController.device_callback.
# Center touch keys. Three rows, and five columns because that is the widest
# model (the Live S); a CT or Live profile simply never binds columns 5. Storing
# the superset means a profile written on one model still opens on the other.
MAX_TOUCH_COLUMNS = 5
TOUCH_ROWS = 3
TOUCH_KEYS = ["tb%d%d" % (r, c)
              for r in range(1, TOUCH_ROWS + 1)
              for c in range(1, MAX_TOUCH_COLUMNS + 1)]

# Side-display layout (schema v8). "cells" splits a strip into three buttons,
# the way it has always worked; "single" makes it one image and one action.
SIDE_LAYOUTS = ("cells", "single")
DEFAULT_SIDE_LAYOUT = {"L": "cells", "R": "cells"}

DIAL_KEY = "dial"
DIAL_KEY_L = "dial-l"
DIAL_KEY_R = "dial-r"

# -- schema v5: encoder feel ---------------------------------------------------
# Tuning is keyed by *control* (the physical knob), not by rotate slot: invert
# spans both directions and speed is a property of the encoder itself.
ROTATE_CONTROLS = ("enc1L", "enc2L", "enc3L", "enc1R", "enc2R", "enc3R", DIAL_KEY)

# `curve` picks how a *fast* twist is treated. "linear" keeps one detent worth
# of action per detent however fast you turn. "accel" scales the output by the
# *interval between detents*, measured when each event arrives (see
# DeviceController._enqueue_rotate).
#
# The earlier design used coalesced batch depth instead. That was measured dead
# on real hardware: with no action bound, every batch is depth 1 at every hand
# speed, because dispatch outruns even a 125 detent/sec spin (docs/PLAN.md
# 5.D.1).
CURVES = ("linear", "accel")

# Interval thresholds, in milliseconds between consecutive detents on one
# control. At or above `from_ms` the control is turning slowly and there is no
# acceleration; at or below `full_ms` it is turning as fast as it usefully gets
# and the multiplier is at `max_steps`; between them it ramps linearly.
#
# Calibrated against a measured hand on a CT side encoder (probe_rotate.py):
# deliberate turning ~189 ms between detents, a comfortable working pace ~58 ms,
# and a full spin ~8 ms (125 detents/sec, far faster than the 25/sec assumed
# earlier). `from` sits just under the working pace so normal use is never
# amplified; `full` sits at the spin rate.
#
# Note the probe's own suggestion was from=151, which would put a comfortable
# pace at 6.7x. That is the wrong end to calibrate from: acceleration should be
# something you opt into by spinning, not something normal turning triggers.
DEFAULT_ACCEL_FROM_MS = 40
DEFAULT_ACCEL_FULL_MS = 8
DEFAULT_MAX_STEPS = 10

# Single source of truth: built from the constants rather than repeating them,
# which had already drifted once (the literal said 150/30 while normalisation
# used 40/8, so a default entry never compared equal to a normalised one and
# stopped being dropped).
DEFAULT_TUNING = {"invert": False, "detents_per_step": 1, "steps_per_detent": 1,
                  "curve": "linear",
                  "accel_from_ms": DEFAULT_ACCEL_FROM_MS,
                  "accel_full_ms": DEFAULT_ACCEL_FULL_MS,
                  "max_steps": DEFAULT_MAX_STEPS}

# The device reports direction only, never magnitude, so "sensitivity" is
# synthesised in dispatch: detents_per_step divides (drop events), and
# steps_per_detent multiplies (repeat the bound action). Presets are the UI
# surface; the two integers are the stored representation.
TUNING_PRESETS = [
    ("original", "Original",  1, 1),   # 1 detent = 1 step
    ("slow2",    "Slow 1/2",  2, 1),   # 2 detents = 1 step
    ("slow3",    "Slow 1/3",  3, 1),   # 3 detents = 1 step
    ("fast2",    "Fast 2x",   1, 2),   # 1 detent = 2 steps
    ("fast3",    "Fast 3x",   1, 3),   # 1 detent = 3 steps
]


def normalize_tuning(raw):
    """Coerce a stored tuning entry into a complete, sane dict.

    Keys we do not recognise are carried through untouched. A profile written
    by a newer build would otherwise be silently stripped by loading and
    re-saving it here, which is data loss rather than graceful degradation.
    Unknown keys are ignored by dispatch but survive the round-trip.
    """
    t = dict(DEFAULT_TUNING)
    if isinstance(raw, dict):
        for key, val in raw.items():
            if key not in DEFAULT_TUNING:
                t[key] = val
        t["invert"] = bool(raw.get("invert", False))
        for key in ("detents_per_step", "steps_per_detent"):
            try:
                t[key] = max(1, int(raw.get(key, 1)))
            except (TypeError, ValueError):
                t[key] = 1
        curve = str(raw.get("curve", "linear")).strip().lower()
        t["curve"] = curve if curve in CURVES else "linear"
        for key, default in (("accel_from_ms", DEFAULT_ACCEL_FROM_MS),
                             ("accel_full_ms", DEFAULT_ACCEL_FULL_MS),
                             ("max_steps", DEFAULT_MAX_STEPS)):
            try:
                t[key] = max(1, int(raw.get(key, default)))
            except (TypeError, ValueError):
                t[key] = default
        # A ramp needs from > full; an inverted or degenerate pair would make the
        # interpolation meaningless, so fall back rather than compute nonsense.
        if t["accel_from_ms"] <= t["accel_full_ms"]:
            t["accel_from_ms"] = DEFAULT_ACCEL_FROM_MS
            t["accel_full_ms"] = DEFAULT_ACCEL_FULL_MS
    return t


def accel_multiplier(interval_ms, tuning):
    """How much to multiply one detent's worth of action by, from speed alone.

    `interval_ms` is the gap between consecutive detents on this control, or
    None when there is no previous detent to measure against (the first click
    of a fresh turn). Returns 1.0 when not accelerating.
    """
    t = normalize_tuning(tuning)
    if t["curve"] != "accel" or interval_ms is None:
        return 1.0
    hi, lo = float(t["accel_from_ms"]), float(t["accel_full_ms"])
    if interval_ms >= hi:
        return 1.0                      # turning slowly: leave it alone
    if interval_ms <= lo:
        return float(t["max_steps"])    # as fast as it usefully gets
    ramp = (hi - interval_ms) / (hi - lo)
    return 1.0 + ramp * (t["max_steps"] - 1)


def accel_steps(steps, interval_ms, tuning):
    """Scale `steps` by how fast the control is turning.

    Speed comes from the interval between detents, timed when each event
    arrives, so it measures the hand rather than our own dispatch latency.

    The result is capped by `max_steps`. Without a cap a long fast spin turns
    into an unbounded burst the target app has to absorb, with no way to take
    it back.

    The cap deliberately does *not* apply to a linear curve here: `steps` is
    then exactly the number of detents the user turned, and clamping it would
    silently discard input they physically performed. (A *coalesced* linear
    batch is capped separately in DeviceController.on_rotate, where being
    behind the hand is already established.)
    """
    t = normalize_tuning(tuning)
    if t["curve"] != "accel":
        return max(1, steps)
    scaled = steps * accel_multiplier(interval_ms, t)
    return max(1, min(int(round(scaled)), t["max_steps"]))


def preset_to_tuning(preset_id, invert=False):
    """'fast3' -> a complete tuning dict with steps_per_detent 3.

    Always complete (the unknown-preset fallback was already returning a full
    dict, so a hit returning a sparse one made the return shape depend on the
    argument). Callers that want a non-default curve set it on the result.
    """
    for pid, _label, dps, spd in TUNING_PRESETS:
        if pid == preset_id:
            return normalize_tuning({"invert": bool(invert),
                                     "detents_per_step": dps,
                                     "steps_per_detent": spd})
    return dict(DEFAULT_TUNING, invert=bool(invert))


def tuning_to_preset(tuning):
    """Reverse lookup for the inspector. Returns None for a combination the
    presets do not cover (the integers remain authoritative)."""
    t = normalize_tuning(tuning)
    for pid, _label, dps, spd in TUNING_PRESETS:
        if t["detents_per_step"] == dps and t["steps_per_detent"] == spd:
            return pid
    return None


# The CT's labelled buttons have obvious meanings, so a new profile starts with
# them wired rather than dead. Applied only to newly created profiles:
# back-filling an existing one would silently change something already set up.
#
# fn is deliberately absent. It is a modifier, not an action, and wiring it to
# something would get in the way of that.
DEFAULT_BUTTON_BINDINGS = {
    "home": ("workspace", WS_KEYS[0], "Workspace 1"),
    "undo": ("hotkey", "ctrl+z", "Undo"),
    "save": ("hotkey", "ctrl+s", "Save"),
    "enter": ("hotkey", "enter", "Enter"),
    "keyboard": ("keyboard", "toggle", "Keyboard"),
}


def apply_default_bindings(config):
    """Wire the CT's labelled buttons on every workspace of a new profile."""
    for ws in config.workspaces:
        for key, (a_type, value, summary) in DEFAULT_BUTTON_BINDINGS.items():
            if key in ws.actions and ws.actions[key].a_type == "none":
                ws.actions[key] = LdAction(action_type=a_type, action=value,
                                           summary=summary)
    return config


class LdConfiguration:
  """Profile data model and JSON persistence.

  Deliberately Qt-free: the UI sits on top of this, never the other way round,
  which is what let the PyQt5 front-end be removed without touching it."""

  def __init__(self, profile="default"):
    self.profile = profile
    self.workspaces = [LdWorkspace() for i in range(8)]
    # Optional callback invoked after a successful load() (set by the UI if it
    # wants to refresh); replaces the old Qt `config_loaded` signal.
    self.on_loaded = None

  def save(self, profile_name):
    if profile_name:
      self.profile = profile_name
      with open(app_paths.profile_write_path(profile_name), "w") as file:
        json.dump(self.to_JSON(), file, indent=True)

  def load(self, json_file):
    try:
      with open(app_paths.profile_read_path(json_file), "r") as file:
        data = json.load(file)
        self.from_JSON(data)
        if self.on_loaded:
          self.on_loaded()
    except FileNotFoundError:
      print("File %s not found" % json_file)
    except json.decoder.JSONDecodeError:
      print("Can't read JSON in file %s" % json_file)

  def to_JSON(self):
    s = {"schema_version": SCHEMA_VERSION,
         "profile": self.profile,
         "workspaces": {i: ws.to_JSON() for i, ws in zip(WS_KEYS, self.workspaces)}}
    return s

  def from_JSON(self, json_str):
    # v1 profiles have no "schema_version". Migration is automatic: LdWorkspace's
    # constructor seeds every current key (incl. the v2 dial/wheel/CT-button
    # slots), and from_JSON only overlays the keys the file actually contains, so
    # missing controls default to "none".
    version = json_str.get("schema_version", 1)
    if version > SCHEMA_VERSION:
      print("warning: profile schema_version %s is newer than supported %s; "
            "loading best-effort" % (version, SCHEMA_VERSION))
    self.profile = json_str["profile"]
    for i, ws_key in enumerate(WS_KEYS):
      self.workspaces[i] = LdWorkspace.from_JSON(json_str["workspaces"][ws_key])


class LdWorkspace:

  def __init__(self, ws_profile="default"):
    self.profile = ws_profile
    # schema v7: an optional name for this workspace. Eight numbered buttons
    # give no clue what is on them; the header shows this when it is set and
    # falls back to "Workspace <n>" when it is not.
    self.name = ""

    # schema v8: how each side display is used. "cells" is the original three
    # separate buttons; "single" makes the whole strip one image and one
    # action, which is what you want for a tall label or artwork. Keyed "L"/"R";
    # the per-cell data stays in place either way, so switching back and forth
    # loses nothing.
    self.side_layout = dict(DEFAULT_SIDE_LAYOUT)
    action_keys = ["enc1L" , "enc1L-l", "enc1L-r",
                   "enc2L", "enc2L-l", "enc2L-r",
                   "enc3L", "enc3L-l", "enc3L-r",
                   "enc1R", "enc1R-l", "enc1R-r",
                   "enc2R", "enc2R-l", "enc2R-r",
                   "enc3R", "enc3R-l", "enc3R-r",
                   "dis1L", "dis2L", "dis3L",
                   "dis1R", "dis2R", "dis3R"] + TOUCH_KEYS
    # schema v2: CT-only controls (harmless/unbound on the Live). The round
    # dial (press + rotate) and the CT's extra hardware buttons. Keys here match
    # what DeviceController.device_callback looks up for the dial, the wheel
    # touch and the CT buttons. Old (v1) profiles lack these and load as "none".
    ct_action_keys = [DIAL_KEY, DIAL_KEY_L, DIAL_KEY_R, WHEEL_DISPLAY] + list(CT_EXTRA_BUTTONS)
    self.actions = {key: LdAction() for key in action_keys + ct_action_keys}

    image_keys = ["dis1L", "dis2L", "dis3L",
                  "dis1R", "dis2R", "dis3R"] + TOUCH_KEYS
    self.images = {key: "" for key in image_keys}
    self.images[WHEEL_DISPLAY] = ""  # CT round wheel screen image (v2)

    # schema v3: per-control text labels for image-bearing controls, keyed the
    # same as images. Each value is {"text", "pos": top|middle|bottom, "mode":
    # over|bar|shrink, "bar_color"?: "#rrggbb"}. In "shrink" mode the image is
    # resized so the label sits in a band above/below it (no overlap); "bar" and
    # "shrink" draw a band whose colour is bar_color (default translucent black).
    # Absent key = no explicit label (an auto-label may still be derived from the
    # bound action when there is no image). Old profiles lack this and load empty.
    self.labels = {}

    # schema v3: RGB LED colours for physical buttons (workspace buttons
    # 'circle'+'1'..'7' and the CT's extra buttons), keyed by button name to a
    # "#rrggbb" string. Absent = default (grey / selected-workspace green).
    self.led_colors = {}

    # schema v4: background fill colour ("#rrggbb") for image-bearing controls,
    # keyed the same as images. Drawn beneath the image (visible in shrink mode
    # or when there is no image), letting a control show a colour + an image
    # together. Absent = no background (black fallback).
    self.bg_colors = {}

    # schema v6: the fn layer. Holding fn (or latching it) makes a control fire
    # this binding instead of its usual one, which is what the CT's fn keys are
    # for. Sparse: only controls with a secondary function appear, and a control
    # with no entry here simply keeps its primary behaviour under fn.
    self.fn_actions = {}

    # schema v5: per-control encoder feel, keyed by control name (see
    # ROTATE_CONTROLS) to {"invert", "detents_per_step", "steps_per_detent"}.
    # Absent key = DEFAULT_TUNING (1:1, not inverted), so older profiles load
    # with today's behaviour unchanged.
    self.tuning = {}

  def fn_action(self, key):
    """The control's fn binding, or None when it has no secondary function."""
    a = self.fn_actions.get(key)
    return a if a is not None and a.a_type != "none" else None

  def set_fn_action(self, key, action):
    """Store or clear a secondary binding. Clearing removes the entry rather
    than storing a 'none', so the map stays sparse and to_JSON stays small."""
    if action is None or getattr(action, "a_type", "none") == "none":
      self.fn_actions.pop(key, None)
    else:
      self.fn_actions[key] = action

  def tuning_for(self, control):
    """Effective tuning for a rotate control; always a complete dict."""
    return normalize_tuning(self.tuning.get(control))

  def set_tuning(self, control, tuning, inherited=None):
    """Store tuning for a control, dropping the entry when it would say nothing
    the surrounding context does not already say.

    `inherited` is what this control resolves to *without* an entry here (the
    parent workspace's setting, for a submenu). Dropping is keyed to that, not
    to DEFAULT_TUNING: inside a submenu under a Fast 3x workspace, an explicit
    "Original" is a real override and has to be stored, or setting it back to
    1:1 would silently re-inherit Fast 3x.
    """
    base = normalize_tuning(inherited)
    t = normalize_tuning(tuning)
    if t == base:
      self.tuning.pop(control, None)
    else:
      self.tuning[control] = t

  def save(self, profile_name):
    self.profile = profile_name
    with open(app_paths.profile_write_path(profile_name), "w") as file:
      json.dump(self.__dict__, file)

  def load(self, json_file):
    data = None
    with open(app_paths.profile_read_path(json_file), "r") as file:
      data = json.load(file)
    for key, value in data.items():
      setattr(self, key, value)
      
  def to_JSON(self):
    s = {"profile": self.profile,
          "name": self.name,
          "side_layout": dict(self.side_layout),
          "actions": {key: action.to_JSON() for key, action in self.actions.items()},
          "images": {key: image for key, image in self.images.items()},
          "labels": {key: dict(v) for key, v in self.labels.items()},
          "led_colors": dict(self.led_colors),
          "bg_colors": dict(self.bg_colors),
          "tuning": {key: dict(v) for key, v in self.tuning.items()},
          "fn_actions": {key: a.to_JSON() for key, a in self.fn_actions.items()}}
    return s

  def from_JSON(json_data):
    ldw = LdWorkspace(ws_profile=json_data["profile"])
    ldw.name = json_data.get("name", "")                    # v7
    # v8; absent in older profiles, which used cells everywhere.
    for side, mode in (json_data.get("side_layout") or {}).items():
      if side in ldw.side_layout and mode in SIDE_LAYOUTS:
        ldw.side_layout[side] = mode
    for key, action in json_data["actions"].items():
      ldw.actions[key] = LdAction.from_JSON(action)
    for key, image in json_data["images"].items():
      ldw.images[key] = image
    ldw.labels = dict(json_data.get("labels", {}))          # v3; absent in older profiles
    ldw.led_colors = dict(json_data.get("led_colors", {}))  # v3
    ldw.bg_colors = dict(json_data.get("bg_colors", {}))    # v4
    # v5; absent in older profiles, and normalised so a hand-edited or truncated
    # entry cannot reach dispatch as a partial dict.
    ldw.tuning = {key: normalize_tuning(val)
                  for key, val in json_data.get("tuning", {}).items()}
    # v6; absent in older profiles, which simply have no fn layer.
    for key, action in json_data.get("fn_actions", {}).items():
        ldw.fn_actions[key] = LdAction.from_JSON(action)
    return ldw


class LdAction:
  # Executable action types are routed through input_backend (Wayland-capable).
  # "command"/"launch" run a shell command (detached); "hotkey" sends a key
  # combo; "text" types a string; "media" controls playback. "submenu"/"back"
  # are navigation (handled by the controller, not here); "none" is unbound.
  type ActionType = Literal["command", "launch", "hotkey", "text", "media", "submenu", "back", "none"]

  EXECUTABLE = ("command", "launch", "hotkey", "text", "media", "back")

  def __init__(self, action_type: ActionType ="none", action="", summary=""):
    self.a_type = action_type
    self.action = action
    if summary:
      self.summary = summary
    elif action_type in self.EXECUTABLE:
      self.summary = self.action
    else:
      self.summary = "none"

  def execute(self, repeat=1):
    """Run the action. `repeat` comes from the encoder Fast presets.

    Only keystroke-like types repeat: `command`/`launch`/`media` clamp to 1, so
    a fast twist can never fan out into N process launches or N transport
    commands (docs/PLAN.md 5.D.1, "repeatability by action type").
    """
    n = max(1, int(repeat))
    try:
      if self.a_type in ("command", "launch"):
        input_backend.launch_app(self.action)
      elif self.a_type == "hotkey":
        input_backend.send_hotkey(self.action, repeat=n)
      elif self.a_type == "text":
        for _ in range(n):
          input_backend.type_text(self.action)
      elif self.a_type == "scroll":
        # Magnitude, not repetition: the wheel takes a distance per call, so a
        # fast twist becomes a bigger number rather than more invocations.
        input_backend.scroll(self.action, amount=n)
      elif self.a_type == "media":
        input_backend.media(self.action)
      elif self.a_type == "macro":
        # Runs on the macro worker, not here: a macro with waits in it would
        # otherwise block the device's message thread for its whole duration.
        # Never repeats, since a repeat would interleave copies of itself.
        macro.run_text(self.action)
      elif self.a_type == "keyboard":
        # The desktop's own on-screen keyboard, not one we draw. Never
        # repeats: toggling N times would just flap it.
        if self.action == "show":
          virtual_keyboard.set_active(True)
        elif self.action == "hide":
          virtual_keyboard.set_active(False)
        else:
          virtual_keyboard.toggle()
      elif self.a_type == "workspace":
        # Handled by the controller, which owns workspace state; reaching here
        # means it was dispatched down the wrong path.
        print("workspace action reached execute(); this is a bug")
      else:
        print("no action to execute for action type %s" % self.a_type)
    except Exception as e:
      # Never let a failing action (e.g. ydotoold not running) crash the
      # device callback thread.
      print("action %r (%r) failed: %s: %s" % (self.a_type, self.action, type(e).__name__, e))

  def to_JSON(self):
    if isinstance(self.action, str):
      s = {"a_type": str(self.a_type), "action": self.action}
    else:
      print("this shouldn't happen, please report the bug to the developer'")
    return s

  def from_JSON(json_str):
    if json_str["a_type"] != "submenu":
      lda = LdAction(action_type=json_str["a_type"], action=json_str["action"])
      return lda
    else:
      lds = LdSubmenu.from_json(json_str)
      return lds

  def __str__(self):
    return "%s : %s" % (self.a_type, self.action)


class LdSubmenu (LdAction):
  def __init__(self, name, action_type="submenu", action=None, summary=""):
    super().__init__(action_type, action, summary)
    self.a_type = "submenu"
    if action:
      self.action = action
    else:
      self.action = LdWorkspace()
    self.action.ws_profile = name
    self.summary = ""
    self.name = ""
    self.setName(name)

  def execute(self):
    print("submenu %s execute, this is a bug and shouldn't happen" % self.summary)

  def to_JSON(self):
    s = {"a_type" : self.a_type, "action": self.action.to_JSON()}
    return s

  def from_json(json_str):
    ws = LdWorkspace.from_JSON(json_str["action"])
    name = json_str["action"]["profile"]
    lds = LdSubmenu(name=name, action=ws)
    return lds

  def setName(self, s):
    self.name = s
    self.summary = "%s %s" % (self.a_type, self.name)
    self.action.profile = self.name

