"""The profile a fresh install opens with.

It ships, so a broken one is broken for every new user and nothing else in the
suite would notice: it is data, not code. These checks are the difference
between "the file parses" and "every binding in it would actually do
something".
"""
import json
import os
import sys
import tempfile

from _harness import Checks

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
tmp = tempfile.mkdtemp()
os.environ["LOUPEDECKAPP_CONFIG_DIR"] = os.path.join(tmp, "config")

import app_paths                                                  # noqa: E402
import input_backend                                              # noqa: E402
from LdConfiguration import (LdConfiguration, SCHEMA_VERSION,     # noqa: E402
                             TOUCH_KEYS, ROTATE_CONTROLS)
from DeviceProfile import DeviceProfile, MODEL_CT, MODEL_LIVE_S   # noqa: E402

c = Checks()

NAME = "Starter"
path = os.path.join(REPO, "Profiles", NAME + ".json")
c.eq("the starter profile ships", os.path.exists(path), True)

with open(path) as f:
    raw = json.load(f)

c.eq("it is written at the current schema",
     raw.get("schema_version"), SCHEMA_VERSION)
c.eq("and knows its own name", raw.get("profile"), NAME)

cfg = LdConfiguration()
cfg.load(NAME)
c.eq("it loads through the normal path", cfg.profile, NAME)

# -- what is in it -----------------------------------------------------------
named = [ws.name for ws in cfg.workspaces if ws.name]
c.eq("the workspaces that are used are named", named, ["Media", "Editing", "Browser"])

bound = {}
for i, ws in enumerate(cfg.workspaces):
    bound[i] = [k for k, a in ws.actions.items() if a.a_type != "none"]

c.eq("the first three workspaces have bindings",
     all(len(bound[i]) >= 10 for i in range(3)), True)
c.eq("and the rest are left empty for the user",
     [len(bound[i]) for i in range(3, 8)], [0] * 5)

# -- would any of it actually work -------------------------------------------
EXECUTABLE = {"hotkey", "text", "command", "launch", "media", "scroll",
              "keyboard", "macro", "workspace", "submenu", "back"}
bad_types = set()
for ws in cfg.workspaces:
    for slot, action in ws.actions.items():
        if action.a_type != "none" and action.a_type not in EXECUTABLE:
            bad_types.add((slot, action.a_type))
c.eq("every action is of a type the app can run", sorted(bad_types), [])

empty = [(i, slot) for i, ws in enumerate(cfg.workspaces)
         for slot, a in ws.actions.items()
         if a.a_type in ("hotkey", "text", "command", "media", "scroll")
         and not a.action]
c.eq("nothing is bound to a blank value", empty, [])

# Every hotkey has to survive the parser the input backend uses, or it does
# nothing at all when pressed and says so only on stderr.
unparseable = []
for ws in cfg.workspaces:
    for slot, action in ws.actions.items():
        if action.a_type != "hotkey":
            continue
        try:
            keys = input_backend._parse_combo(action.action)
        except Exception as e:
            unparseable.append((slot, action.action, str(e)))
            continue
        if not keys:
            unparseable.append((slot, action.action, "parsed to nothing"))
c.eq("every hotkey in it parses", unparseable, [])

directions = {"up", "down", "left", "right"}
bad_scroll = [(slot, a.action) for ws in cfg.workspaces
              for slot, a in ws.actions.items()
              if a.a_type == "scroll" and a.action not in directions]
c.eq("every scroll names a direction", bad_scroll, [])

MEDIA = {"play-pause", "next", "previous", "stop"}
bad_media = [(slot, a.action) for ws in cfg.workspaces
             for slot, a in ws.actions.items()
             if a.a_type == "media" and a.action not in MEDIA]
c.eq("every media action names a transport", bad_media, [])

# -- does it fit the hardware ------------------------------------------------
ct = DeviceProfile.for_model(MODEL_CT)
live_s = DeviceProfile.for_model(MODEL_LIVE_S)
valid_slots = set(TOUCH_KEYS)
for control in ROTATE_CONTROLS:
    valid_slots.update({control, control + "-l", control + "-r"})
valid_slots.update(["dis%d%s" % (i, s) for i in (1, 2, 3) for s in "LR"])
valid_slots.update(ct.extra_buttons)
valid_slots.update(ct.workspace_keys)
valid_slots.add("wheel")

unknown = sorted({slot for ws in cfg.workspaces
                  for slot, a in ws.actions.items()
                  if a.a_type != "none" and slot not in valid_slots})
c.eq("every bound slot is a real control", unknown, [])

# A Live S has no side screens and its two knobs are both on the right; a
# starter profile that only works on the author's device is not much of a
# starter.
smallest_keys = set(live_s.touch_keys)
smallest_knobs = set(live_s.encoders_left + live_s.encoders_right)

off_grid = sorted({slot for ws in cfg.workspaces[:3]
                   for slot, a in ws.actions.items()
                   if a.a_type != "none" and slot.startswith("tb")
                   and slot not in smallest_keys})
c.eq("every key it binds exists on the smallest model", off_grid, [])

knobs_used = {slot.split("-")[0] for ws in cfg.workspaces[:3]
              for slot, a in ws.actions.items()
              if a.a_type != "none" and slot.split("-")[0] in smallest_knobs}
c.eq("and at least one knob does too", len(knobs_used) >= 1, True)

for i, ws in enumerate(cfg.workspaces[:3]):
    used = {slot.split("-")[0] for slot, a in ws.actions.items()
            if a.a_type != "none" and slot.split("-")[0] in smallest_knobs}
    c.eq("workspace %d gives a Live S a working knob" % (i + 1),
         len(used) >= 1, True)

# -- appearance --------------------------------------------------------------
for i, ws in enumerate(cfg.workspaces[:3]):
    keys_with_action = [k for k in bound[i] if k.startswith("tb")]
    unlabelled = [k for k in keys_with_action if k not in ws.labels]
    c.eq("workspace %d labels every key it binds" % (i + 1), unlabelled, [])

bad_colors = [v for ws in cfg.workspaces for v in
              list(ws.bg_colors.values()) + list(ws.led_colors.values())
              if not (isinstance(v, str) and v.startswith("#") and len(v) == 7)]
c.eq("every colour is a #rrggbb string", bad_colors, [])

# -- regenerating it is reproducible -----------------------------------------
# The generator is the source of truth; a hand-edited profile nobody dares
# regenerate is how this file rots.
sys.path.insert(0, os.path.join(REPO, "scripts"))
import make_starter_profiles                                      # noqa: E402

regenerated = make_starter_profiles.build().to_JSON()
c.eq("the generator reproduces the shipped file exactly",
     json.loads(json.dumps(regenerated, sort_keys=True)),
     json.loads(json.dumps(raw, sort_keys=True)))

# -- it is the first-run default --------------------------------------------
c.eq("it is visible to the profile list", NAME in app_paths.list_profiles(), True)

sys.exit(c.done())
