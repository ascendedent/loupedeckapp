"""Workspace names and switching (schema v7)."""
import json
import os
import sys
import tempfile

from _harness import Checks, controller

# app_paths reads this once at import, so it has to be set before anything that
# imports it. Without this the test writes into the user's real profiles.
tmp = tempfile.mkdtemp()
os.environ["LOUPEDECKAPP_CONFIG_DIR"] = os.path.join(tmp, "config")

import app_paths                                              # noqa: E402
from LdConfiguration import (LdConfiguration, LdWorkspace,     # noqa: E402
                             SCHEMA_VERSION)
from DeviceProfile import WS_KEYS                              # noqa: E402

c = Checks()

# -- the model ---------------------------------------------------------------
ws = LdWorkspace()
c.eq("a new workspace has no name", ws.name, "")
ws.name = "Streaming"
c.eq("a name round-trips through JSON",
     LdWorkspace.from_JSON(ws.to_JSON()).name, "Streaming")
c.eq("a pre-v7 workspace loads with no name",
     LdWorkspace.from_JSON({k: v for k, v in ws.to_JSON().items() if k != "name"}).name, "")
c.eq("naming bumped the schema", SCHEMA_VERSION >= 7, True)

# -- through a saved profile -------------------------------------------------
cfg = LdConfiguration()
cfg.workspaces[2].name = "Editing"
cfg.save("named")
blob = json.load(open(app_paths.profile_write_path("named")))
c.eq("the name is in the file", blob["workspaces"][WS_KEYS[2]]["name"], "Editing")

again = LdConfiguration()
again.load("named")
c.eq("and comes back on load", again.workspaces[2].name, "Editing")
c.eq("the others stay unnamed",
     [w.name for i, w in enumerate(again.workspaces) if i != 2], [""] * 7)

# -- the controller ----------------------------------------------------------
dc, _ws = controller()
c.eq("an unnamed workspace falls back to its number",
     dc.workspace_label(WS_KEYS[0]), "Workspace 1")
c.eq("and numbering starts at one even though the key is 'circle'",
     dc.workspace_label(WS_KEYS[4]), "Workspace 5")

dc.dirty = False
dc.set_workspace_name(WS_KEYS[4], "  Editing  ")
c.eq("naming strips whitespace", dc.workspace_name(WS_KEYS[4]), "Editing")
c.eq("naming stages an unsaved change", dc.dirty, True)
c.eq("the label prefers the name", dc.workspace_label(WS_KEYS[4]), "Editing")

dc.set_workspace_name(WS_KEYS[4], "")
c.eq("clearing goes back to the number",
     dc.workspace_label(WS_KEYS[4]), "Workspace 5")

dc.set_workspace_name("not-a-workspace", "x")
c.eq("a key that is not a workspace is ignored",
     [w.name for w in dc.config.workspaces], [""] * 8)

# -- switching ---------------------------------------------------------------
dc.on_workspace_press(WS_KEYS[3])
c.eq("switching moves the current workspace", dc.selected_ws, WS_KEYS[3])
c.eq("and current_ws follows it",
     dc.current_ws() is dc.config.workspaces[3], True)
dc.set_workspace_name(WS_KEYS[3], "Fourth")
c.eq("the current label reads without a key argument",
     dc.workspace_label(), "Fourth")

# Switching is reachable from the UI now, and the UI stays usable while the
# device is unplugged, so this must not need a device attached.
c.eq("switching with no device attached does not raise", dc.device, None)

# -- copying a whole workspace -----------------------------------------------
# Building a second page that is mostly like the first was twelve single-control
# copies before this.
from LdConfiguration import LdAction                               # noqa: E402

source = dc.get_ws(WS_KEYS[0])
source.name = "Media"
source.actions["tb11"] = LdAction(action_type="hotkey", action="ctrl+c")
source.labels["tb11"] = {"text": "Copy", "pos": "bottom", "mode": "bar"}
source.bg_colors["tb11"] = "#1e3a8a"

copied = dc.copy_workspace(WS_KEYS[0])
c.eq("a workspace copies as data, not as a reference",
     isinstance(copied, dict), True)

# The clipboard must not follow later edits, or pasting gives you the current
# page rather than the one you copied.
source.actions["tb12"] = LdAction(action_type="text", action="after")
c.eq("editing the source afterwards does not change the copy",
     copied["actions"]["tb12"]["a_type"], "none")

dc.dirty = False
c.eq("pasting reports success", dc.paste_workspace(WS_KEYS[5], copied), True)
pasted = dc.get_ws(WS_KEYS[5])
c.eq("the actions came across",
     (pasted.actions["tb11"].a_type, pasted.actions["tb11"].action),
     ("hotkey", "ctrl+c"))
c.eq("so did the labels", pasted.labels["tb11"]["text"], "Copy")
c.eq("and the colours", pasted.bg_colors["tb11"], "#1e3a8a")
c.eq("and the name, because a copy of Media that is not called Media is a "
     "puzzle", pasted.name, "Media")
c.eq("pasting stages an unsaved change", dc.dirty, True)
c.eq("the source is untouched", source.actions["tb12"].action, "after")

c.eq("pasting onto something that is not a workspace is refused",
     dc.paste_workspace("tb11", copied), False)
c.eq("and pasting nonsense is too",
     dc.paste_workspace(WS_KEYS[4], "not a workspace"), False)

# -- clearing -----------------------------------------------------------------
dc.set_workspace_name(WS_KEYS[5], "Keep this name")
dc.dirty = False
c.eq("clearing reports success", dc.clear_workspace(WS_KEYS[5]), True)
cleared = dc.get_ws(WS_KEYS[5])
c.eq("every control is empty",
     [k for k, a in cleared.actions.items() if a.a_type != "none"], [])
c.eq("the labels went too", cleared.labels, {})
c.eq("but the name stayed: emptying a page is not renaming it",
     cleared.name, "Keep this name")
c.eq("clearing stages an unsaved change", dc.dirty, True)
c.eq("clearing something that is not a workspace is refused",
     dc.clear_workspace("nope"), False)

sys.exit(c.done())
