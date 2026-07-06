import json, os
import input_backend
from DeviceProfile import CT_EXTRA_BUTTONS, WHEEL_DISPLAY, WS_KEYS

SCHEMA_VERSION = 2

# Config action-key names for the CT dial (decoupled from the device id
# "knobCT"); these must match the lookups in LdApp (on_dial_press/rotate).
DIAL_KEY = "dial"
DIAL_KEY_L = "dial-l"
DIAL_KEY_R = "dial-r"


class LdConfiguration:
  """Profile data model. Qt-free so both the PyQt5 (`app.py`) and PySide6
  (`qml_app.py`) front-ends can share it."""

  def __init__(self, profile="default"):
    self.profile = profile
    self.workspaces = [LdWorkspace() for i in range(8)]
    # Optional callback invoked after a successful load() (set by the UI if it
    # wants to refresh); replaces the old Qt `config_loaded` signal.
    self.on_loaded = None

  def save(self, profile_name):
    if profile_name:
      self.profile = profile_name
      with open("./Profiles/" + profile_name + ".json", "w") as file:
        json.dump(self.to_JSON(), file, indent=True)

  def load(self, json_file):
    try:
      with open("./Profiles/" + json_file + ".json", "r") as file:
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
    action_keys = ["enc1L" , "enc1L-l", "enc1L-r",
                   "enc2L", "enc2L-l", "enc2L-r",
                   "enc3L", "enc3L-l", "enc3L-r",
                   "enc1R", "enc1R-l", "enc1R-r",
                   "enc2R", "enc2R-l", "enc2R-r",
                   "enc3R", "enc3R-l", "enc3R-r",
                   "dis1L", "dis2L", "dis3L",
                   "dis1R", "dis2R", "dis3R",
                   "tb11", "tb12", "tb13", "tb14",
                   "tb21", "tb22", "tb23", "tb24",
                   "tb31", "tb32", "tb33", "tb34"]
    # schema v2 — CT-only controls (harmless/unbound on the Live): the round
    # dial (press + rotate) and the CT's extra hardware buttons. Keys here match
    # what LdApp.device_callback looks up (see on_dial_*, on_wheel_press,
    # on_ct_button). Old (v1) profiles simply lack these and load as "none".
    ct_action_keys = [DIAL_KEY, DIAL_KEY_L, DIAL_KEY_R, WHEEL_DISPLAY] + list(CT_EXTRA_BUTTONS)
    self.actions = {key: LdAction() for key in action_keys + ct_action_keys}

    self.images =  {"dis1L": "", "dis2L": "", "dis3L": "",
                    "dis1R": "", "dis2R": "", "dis3R": "",
                    "tb11": "", "tb12": "", "tb13": "", "tb14": "",
                    "tb21": "", "tb22": "", "tb23": "", "tb24": "",
                    "tb31": "", "tb32": "", "tb33": "", "tb34": "",
                    WHEEL_DISPLAY: ""}  # CT round wheel screen image (v2)

  def save(self, profile_name):
    self.profile = profile_name
    with open("./Profiles/" + profile_name + ".json", "w") as file:
      json.dump(self.__dict__, file)

  def load(self, json_file):
    data = None
    with open("./Profiles/" + json_file + ".json", "r") as file:
      data = json.load(file)
    for key, value in data.items():
      setattr(self, key, value)
      
  def to_JSON(self):
    s = {"profile": self.profile,
          "actions": {key: action.to_JSON() for key, action in self.actions.items()},
          "images": {key: image for key, image in self.images.items()}}
    return s

  def from_JSON(json_data):
    ldw = LdWorkspace(ws_profile=json_data["profile"])
    for key, action in json_data["actions"].items():
      ldw.actions[key] = LdAction.from_JSON(action)
    for key, image in json_data["images"].items():
      ldw.images[key] = image
    return ldw


class LdAction:
  # Executable action types are routed through input_backend (Wayland-capable).
  # "command"/"launch" run a shell command (detached); "hotkey" sends a key
  # combo; "text" types a string; "media" controls playback. "submenu"/"back"
  # are navigation (handled in LdApp, not here); "none" is unbound.
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

  def execute(self):
    try:
      if self.a_type in ("command", "launch"):
        input_backend.launch_app(self.action)
      elif self.a_type == "hotkey":
        input_backend.send_hotkey(self.action)
      elif self.a_type == "text":
        input_backend.type_text(self.action)
      elif self.a_type == "media":
        input_backend.media(self.action)
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

