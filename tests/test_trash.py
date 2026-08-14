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

sys.exit(c.done())
