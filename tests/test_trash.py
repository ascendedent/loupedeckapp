"""Deleting keeps a copy.

A profile is an evening's work and an application is a folder of them, so the
delete buttons move rather than remove. What is checked is that the copy is
really there, that a second delete of the same name does not quietly replace
the first, and that the safety net cannot grow without limit.
"""
import json
import os
import sys
import tempfile

from _harness import Checks

tmp = tempfile.mkdtemp()
os.environ["LOUPEDECKAPP_CONFIG_DIR"] = os.path.join(tmp, "config")

import app_paths                                                  # noqa: E402

c = Checks()

c.eq("the trash lives beside the profiles",
     os.path.dirname(app_paths.trash_dir()), app_paths.user_dir())
c.eq("and starts empty", app_paths.list_trash(), [])

# -- a file --------------------------------------------------------------------
work = os.path.join(tmp, "work")
os.makedirs(work)


def make(name, content="x"):
    path = os.path.join(work, name)
    with open(path, "w") as f:
        f.write(content)
    return path


kept = app_paths.trash(make("profile.json", "first"))
c.eq("trashing reports where it went", os.path.exists(kept), True)
c.eq("and the original is gone",
     os.path.exists(os.path.join(work, "profile.json")), False)
c.eq("the contents came with it", open(kept).read(), "first")
c.eq("it is listed", [e["name"] for e in app_paths.list_trash()], ["profile.json"])

# Delete, remake, delete: the second must not replace the first.
second = app_paths.trash(make("profile.json", "second"))
c.eq("a second copy of the same name does not overwrite the first",
     sorted(e["name"] for e in app_paths.list_trash()),
     ["profile.json", "profile.json (2)"])
c.eq("and each keeps its own contents",
     (open(kept).read(), open(second).read()), ("first", "second"))

# -- a folder ------------------------------------------------------------------
app_dir = os.path.join(work, "Premiere")
os.makedirs(app_dir)
with open(os.path.join(app_dir, "Cut.json"), "w") as f:
    json.dump({"profile": "Premiere/Cut"}, f)
kept_dir = app_paths.trash(app_dir, "app Premiere")
c.eq("a whole application can be kept", os.path.isdir(kept_dir), True)
c.eq("with its profiles inside",
     os.path.exists(os.path.join(kept_dir, "Cut.json")), True)
c.eq("and it is labelled as an app",
     "app Premiere" in [e["name"] for e in app_paths.list_trash()], True)

# -- things that are not there --------------------------------------------------
c.eq("trashing something that does not exist is not an error",
     app_paths.trash(os.path.join(work, "nope.json")), "")

# -- it cannot grow forever ------------------------------------------------------
for i in range(app_paths.TRASH_KEEP + 5):
    app_paths.trash(make("filler%d.json" % i))
c.eq("the trash is pruned to a bounded size",
     len(app_paths.list_trash()) <= app_paths.TRASH_KEEP, True)
c.eq("keeping the most recent",
     app_paths.list_trash()[0]["name"].startswith("filler"), True)

# -- putting things back -------------------------------------------------------
# Keeping a copy is only half of it. Without a recorded origin, restoring means
# parsing a display name, which is a guess dressed up as a restore.
os.makedirs(os.path.join(tmp, "config"), exist_ok=True)
app_paths.ensure_user_app_dir("Premiere")
profile = app_paths.profile_write_path("Premiere", "Cut")
with open(profile, "w") as f:
    json.dump({"profile": "Premiere/Cut"}, f)

held = app_paths.trash(profile, "Premiere Cut.json",
                       {"kind": "profile", "app": "Premiere", "name": "Cut"})
c.eq("the profile is gone from its app",
     app_paths.list_profiles("Premiere"), [])
c.eq("the origin is recorded",
     app_paths.read_origin(held),
     {"kind": "profile", "app": "Premiere", "name": "Cut"})
c.eq("and the listing says what kind of thing it was",
     [e["kind"] for e in app_paths.list_trash() if e["path"] == held], ["profile"])
c.eq("the sidecar is not itself listed as an item",
     [e for e in app_paths.list_trash() if e["name"].endswith(".origin.json")], [])

where, error = app_paths.restore(held)
c.eq("restoring reports no error", error, "")
c.eq("it went back into its own app",
     app_paths.list_profiles("Premiere"), ["Cut"])
c.eq("and left the trash", os.path.exists(held), False)
c.eq("taking its sidecar with it",
     os.path.exists(held + app_paths.ORIGIN_SUFFIX), False)

# A restore that lands on something made since is a second deletion.
held2 = app_paths.trash(where, "Premiere Cut.json",
                        {"kind": "profile", "app": "Premiere", "name": "Cut"})
with open(app_paths.profile_write_path("Premiere", "Cut"), "w") as f:
    json.dump({"profile": "Premiere/Cut", "remade": True}, f)
again, error = app_paths.restore(held2)
c.eq("restoring onto a name in use is suffixed, not overwritten", error, "")
c.eq("so the newer one survives",
     json.load(open(app_paths.profile_write_path("Premiere", "Cut")))
     .get("remade"), True)
c.eq("and the restored one is beside it",
     sorted(app_paths.list_profiles("Premiere")), ["Cut", "Cut 2"])

# -- a whole application --------------------------------------------------------
app_dir = app_paths.user_app_dir("Premiere")
held_app = app_paths.trash(app_dir, "app Premiere",
                           {"kind": "app", "app": "Premiere"})
c.eq("the app is gone", os.path.isdir(app_dir), False)
_, error = app_paths.restore(held_app)
c.eq("and comes back whole", (error, os.path.isdir(app_dir)), ("", True))
c.eq("with its profiles",
     sorted(app_paths.list_profiles("Premiere")), ["Cut", "Cut 2"])

# -- things that cannot be put back ---------------------------------------------
orphan = app_paths.trash(make("orphan.json"))          # no origin recorded
_, error = app_paths.restore(orphan)
c.eq("something deleted by an older build says so rather than guessing",
     "cannot be put back automatically" in error, True)
c.eq("and is left where it is", os.path.exists(orphan), True)

_, error = app_paths.restore(os.path.join(tmp, "never-existed"))
c.eq("restoring something that is not there is an error, not a crash",
     error != "", True)

sys.exit(c.done())
