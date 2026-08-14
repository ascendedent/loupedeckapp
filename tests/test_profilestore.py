"""Profile and application file handling, with no Qt anywhere.

This was a quarter of a 2000-line Qt object, and none of it could be exercised
without standing up a QGuiApplication first. It is a plain module now, so these
checks are about the file handling itself: what it refuses, what it never
overwrites, and what it leaves behind when it fails.
"""
import json
import os
import sys
import tempfile

from _harness import Checks

tmp = tempfile.mkdtemp()
os.environ["LOUPEDECKAPP_CONFIG_DIR"] = os.path.join(tmp, "config")

import app_paths                                                  # noqa: E402

# An empty bundled side, so the repo's own profiles stay out of the listings.
app_paths.BUNDLED_DIR = os.path.join(tmp, "install")
os.makedirs(app_paths.bundled_profiles_dir())

import profile_store as ps                                        # noqa: E402
from LdConfiguration import LdConfiguration, SCHEMA_VERSION       # noqa: E402

c = Checks()
DEFAULT = app_paths.DEFAULT_APP

# -- names ---------------------------------------------------------------------
c.eq("a plain name is fine", ps.clean_name(" Media "), "Media")
c.eq("path separators are refused", ps.clean_name("a/b"), "")
c.eq("so are the shell-hostile characters", ps.clean_name('a?b'), "")
c.eq("and the ones that would climb out of the directory",
     [ps.clean_name(n) for n in ("..", ".", "")], ["", "", ""])

# -- profiles ------------------------------------------------------------------
ref, error = ps.create_profile(DEFAULT, "Media")
c.eq("creating one reports no error", error, "")
c.eq("and returns a reference", ref, "Default/Media")
c.eq("the file is there", os.path.exists(app_paths.profile_read_path(ref)), True)
fresh = LdConfiguration()
fresh.load(ref)
c.eq("with the CT's labelled buttons already wired, so they are not dead keys",
     any(a.a_type != "none" for a in fresh.workspaces[0].actions.values()), True)

c.eq("a name already taken is refused", ps.create_profile(DEFAULT, "Media")[1] != "",
     True)
c.eq("and validate says so up front",
     ps.validate_profile(DEFAULT, "Media") != "", True)
c.eq("while a free name validates clean", ps.validate_profile(DEFAULT, "Other"), "")

dup, error = ps.duplicate_profile(DEFAULT, "Media", "Media copy")
c.eq("duplicating works", (error, dup), ("", "Default/Media copy"))
c.eq("the copy knows its own name",
     json.load(open(app_paths.profile_read_path(dup)))["profile"],
     "Default/Media copy")
c.eq("duplicating something that is not there is refused",
     ps.duplicate_profile(DEFAULT, "ghost", "x")[1] != "", True)

new_ref, old_ref, error = ps.rename_profile(DEFAULT, "Media copy", "Renamed")
c.eq("renaming works", (error, new_ref, old_ref),
     ("", "Default/Renamed", "Default/Media copy"))
c.eq("the old one is gone",
     os.path.exists(app_paths.profile_write_path(old_ref)), False)
c.eq("renaming onto a name in use is refused",
     ps.rename_profile(DEFAULT, "Renamed", "Media")[2] != "", True)
c.eq("and renaming to the same name is a no-op with a reason",
     ps.rename_profile(DEFAULT, "Renamed", "Renamed")[2] != "", True)

ref, kept, error = ps.delete_profile(DEFAULT, "Renamed")
c.eq("deleting works", error, "")
c.eq("and keeps a copy", os.path.exists(kept), True)
c.eq("deleting something that is not there is refused",
     ps.delete_profile(DEFAULT, "ghost")[2] != "", True)

# -- applications ---------------------------------------------------------------
app, error = ps.create_app("Premiere", "premiere")
c.eq("creating an app works", (error, app), ("", "Premiere"))
c.eq("it starts with a profile, not as an empty shell",
     app_paths.list_profiles(app), ["Premiere"])
c.eq("and with the rule that makes it switch",
     app_paths.app_matches(app), ["premiere"])
c.eq("a name already taken is refused", ps.create_app("Premiere")[1] != "", True)

c.eq("renaming works", ps.rename_app("Premiere", "Premiere Pro"), "")
c.eq("its profiles came with it",
     app_paths.list_profiles("Premiere Pro"), ["Premiere"])
c.eq("the default app cannot be renamed",
     ps.rename_app(DEFAULT, "Something") != "", True)
c.eq("nor deleted", ps.delete_app(DEFAULT)[1] != "", True)

# -- export and import ----------------------------------------------------------
out = os.path.join(tmp, "one.json")
c.eq("exporting a profile works", ps.export_profile(DEFAULT, "Media", out), "")
c.eq("a missing extension is added",
     os.path.exists(os.path.join(tmp, "noext.json")) if
     ps.export_profile(DEFAULT, "Media", os.path.join(tmp, "noext")) == "" else False,
     True)

name, error = ps.import_profile(DEFAULT, out)
c.eq("importing it back works", error, "")
c.eq("without overwriting the original", name, "Media 2")

app_out = os.path.join(tmp, "app.json")
c.eq("exporting an application works", ps.export_app("Premiere Pro", app_out), "")
imported, error = ps.import_app(app_out)
c.eq("importing it works", error, "")
c.eq("as a new application", imported, "Premiere Pro 2")

# Right file, wrong button: say which button rather than "not valid".
c.eq("a profile fed to the app importer says which button",
     "Import in the profile list" in ps.import_app(out)[1], True)
c.eq("and an application fed to the profile importer does too",
     "Import app" in ps.import_profile(DEFAULT, app_out)[1], True)

backup = os.path.join(tmp, "backup.json")
count, error = ps.export_backup(backup, {"brightness": 40}, {"dynamic_mode": True})
c.eq("backing up works", error, "")
c.eq("and counts what it wrote", count > 0, True)
c.eq("a backup fed to the app importer says which button",
     "Use Restore" in ps.import_app(backup)[1], True)

before = len(app_paths.list_apps())
apps, profiles, error = ps.import_backup(backup)
c.eq("restoring works", error, "")
c.eq("adding rather than replacing",
     len(app_paths.list_apps()) > before, True)
c.eq("and reporting what it restored", (len(apps) > 0, profiles > 0), (True, True))
c.eq("an application fed to Restore says which button",
     "Import app" in ps.import_backup(app_out)[2], True)

# -- refusing bad files ---------------------------------------------------------
bad = os.path.join(tmp, "bad.json")
open(bad, "w").write("{not json")
c.eq("invalid JSON is refused", "not valid JSON" in ps.import_profile(DEFAULT, bad)[1],
     True)
c.eq("a file that is not there is refused",
     ps.import_profile(DEFAULT, os.path.join(tmp, "ghost.json"))[1] != "", True)

future = os.path.join(tmp, "future.json")
data = json.load(open(out)); data["schema_version"] = SCHEMA_VERSION + 5
json.dump(data, open(future, "w"))
c.eq("a newer schema is refused rather than half-read",
     ("schema v%d" % (SCHEMA_VERSION + 5)) in ps.import_profile(DEFAULT, future)[1],
     True)

unloadable = os.path.join(tmp, "unloadable.json")
data = json.load(open(out)); data["workspaces"] = {"circle": {"profile": "x"}}
json.dump(data, open(unloadable, "w"))
listed_before = app_paths.list_profiles(DEFAULT)
c.eq("a profile that cannot be loaded is refused",
     ps.import_profile(DEFAULT, unloadable)[1] != "", True)
c.eq("and nothing of it was written",
     app_paths.list_profiles(DEFAULT), listed_before)

sys.exit(c.done())
