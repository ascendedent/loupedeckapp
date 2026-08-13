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

sys.exit(c.done())
