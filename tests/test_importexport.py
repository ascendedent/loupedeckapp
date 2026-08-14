"""Profile import / export, including what must be rejected."""
import json
import os
import shutil
import sys
import tempfile

from _harness import Checks

tmp = tempfile.mkdtemp(prefix="ldio-")
os.environ["LOUPEDECKAPP_CONFIG_DIR"] = os.path.join(tmp, "config")

import app_paths                                    # noqa: E402

# Point the bundled side at an empty directory too, so the repo's own profiles
# do not appear in the listings these checks compare against.
app_paths.BUNDLED_DIR = os.path.join(tmp, "install")
os.makedirs(app_paths.bundled_profiles_dir())

from LdConfiguration import LdConfiguration, SCHEMA_VERSION   # noqa: E402

c = Checks()

from PySide6.QtGui import QGuiApplication           # noqa: E402
from PySide6.QtCore import QUrl                     # noqa: E402
app = QGuiApplication.instance() or QGuiApplication(["test"])
import profile_manager                              # noqa: E402
from qml_app import Backend                         # noqa: E402

b = Backend()
b._pm = profile_manager.ProfileManager(os.path.join(tmp, "dyn.json"))
get = lambda n: type(b).__dict__[n].fget(b)
url = lambda p: QUrl.fromLocalFile(p).toString()

# a profile with something identifiable in it
cfg = LdConfiguration(profile="source")
cfg.workspaces[0].labels["tb11"] = {"text": "marker"}
cfg.save("source")

# -- export --------------------------------------------------------------------
out = os.path.join(tmp, "exported.json")
c.eq("export succeeds", b.exportProfile("source", url(out)), "")
c.eq("the file exists", os.path.exists(out), True)
exported = json.load(open(out))
c.eq("it carries the schema version", exported["schema_version"], SCHEMA_VERSION)
c.eq("and the content", exported["workspaces"]["circle"]["labels"]["tb11"]["text"],
     "marker")

noext = os.path.join(tmp, "no-extension")
b.exportProfile("source", url(noext))
c.eq("a missing .json extension is added", os.path.exists(noext + ".json"), True)
c.eq("exporting nothing is refused", b.exportProfile("", url(out)) != "", True)

# Export reflects disk, not the draft: an unsaved edit must not leak into a file
# that is supposed to be reproducible.
b.loadProfile("source")
b.setActionSlot("tb11", "hotkey", "ctrl+j")
draft_out = os.path.join(tmp, "draft.json")
b.exportProfile("source", url(draft_out))
c.eq("an unsaved edit is not exported",
     json.load(open(draft_out))["workspaces"]["circle"]["actions"]["tb11"]["a_type"],
     "none")
b.revert()

# -- import --------------------------------------------------------------------
c.eq("importing the exported file works", b.importProfile(url(out)), "")
c.eq("it did not overwrite the original",
     sorted(app_paths.list_profiles()), ["source", "source 2"])
c.eq("and it became the active profile", get("activeProfile"), "source 2")
c.eq("the name inside the file was rewritten to match",
     json.load(open(app_paths.profile_read_path("source 2")))["profile"],
     "Default/source 2")

b.importProfile(url(out))
c.eq("importing again suffixes rather than clobbering",
     sorted(app_paths.list_profiles()), ["source", "source 2", "source 3"])

# -- rejections ----------------------------------------------------------------
bad = os.path.join(tmp, "bad.json")
open(bad, "w").write("{not json at all")
c.eq("invalid JSON is rejected", "not valid JSON" in b.importProfile(url(bad)), True)

wrong = os.path.join(tmp, "wrong.json")
json.dump({"hello": "world"}, open(wrong, "w"))
c.eq("a JSON file that is not a profile is rejected",
     "workspaces" in b.importProfile(url(wrong)), True)

future = os.path.join(tmp, "future.json")
data = json.load(open(out)); data["schema_version"] = SCHEMA_VERSION + 5
json.dump(data, open(future, "w"))
msg = b.importProfile(url(future))
c.eq("a newer schema is refused rather than half-read",
     ("schema v%d" % (SCHEMA_VERSION + 5)) in msg, True)

broken = os.path.join(tmp, "broken.json")
data = json.load(open(out)); data["workspaces"] = {"circle": {"profile": "x"}}
json.dump(data, open(broken, "w"))
c.eq("a profile that cannot be parsed is refused",
     b.importProfile(url(broken)) != "", True)

c.eq("nothing broken was added to the list",
     sorted(app_paths.list_profiles()), ["source", "source 2", "source 3"])
c.eq("importing no file is refused", b.importProfile("") != "", True)

# an older profile is still accepted: migration is the whole point of the schema
old = os.path.join(tmp, "old.json")
data = json.load(open(out))
data["schema_version"] = 2
data["profile"] = "ancient"
for w in data["workspaces"].values():
    w.pop("tuning", None); w.pop("bg_colors", None)
json.dump(data, open(old, "w"))
c.eq("an older schema imports fine", b.importProfile(url(old)), "")
c.eq("and lands under its own name", get("activeProfile"), "ancient")

b._ctl.close()
shutil.rmtree(tmp, ignore_errors=True)
sys.exit(c.done())
