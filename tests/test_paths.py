"""AppPaths: user/bundled resolution, copy-on-write, and legacy migration."""
import glob
import json
import os
import shutil
import sys
import tempfile

from _harness import Checks

c = Checks()
tmp = tempfile.mkdtemp(prefix="ldpaths-")
os.environ["LOUPEDECKAPP_CONFIG_DIR"] = os.path.join(tmp, "config")

import app_paths                                   # noqa: E402  (after the env var)
from LdConfiguration import LdConfiguration        # noqa: E402

# Pretend a different install directory so the repo's own Profiles/ are not
# involved and the bundled side can be controlled.
bundled = os.path.join(tmp, "install")
os.makedirs(os.path.join(bundled, "Profiles"))
app_paths.BUNDLED_DIR = bundled


def write_profile(directory, name, marker):
    os.makedirs(directory, exist_ok=True)
    cfg = LdConfiguration(profile=name)
    cfg.workspaces[0].labels["tb11"] = {"text": marker}
    with open(os.path.join(directory, name + ".json"), "w") as f:
        json.dump(cfg.to_JSON(), f)


# -- resolution ----------------------------------------------------------------
write_profile(app_paths.bundled_profiles_dir(), "starter", "bundled")
c.eq("a bundled profile is listed", app_paths.list_profiles(), ["starter"])
c.eq("it reads from the bundled directory",
     app_paths.profile_read_path("starter").startswith(bundled), True)
c.eq("but it is not a user profile", app_paths.is_user_profile("starter"), False)
c.eq("writes are directed at the user directory",
     app_paths.profile_write_path("starter").startswith(app_paths.user_dir()), True)

# -- copy on write -------------------------------------------------------------
cfg = LdConfiguration(); cfg.load("starter")
c.eq("loading a bundled profile works",
     cfg.workspaces[0].labels.get("tb11", {}).get("text"), "bundled")
cfg.workspaces[0].labels["tb11"] = {"text": "edited"}
cfg.save("starter")
c.eq("saving created a user copy", app_paths.is_user_profile("starter"), True)
c.eq("the bundled original is untouched",
     json.load(open(os.path.join(app_paths.bundled_profiles_dir(), "starter.json")))
     ["workspaces"]["circle"]["labels"]["tb11"]["text"], "bundled")
c.eq("the name is still listed once", app_paths.list_profiles(), ["starter"])
again = LdConfiguration(); again.load("starter")
c.eq("the user copy now shadows the original",
     again.workspaces[0].labels["tb11"]["text"], "edited")

os.remove(app_paths.profile_write_path("starter"))
restored = LdConfiguration(); restored.load("starter")
c.eq("deleting the user copy reveals the original again",
     restored.workspaces[0].labels["tb11"]["text"], "bundled")

# -- a user-only profile -------------------------------------------------------
write_profile(app_paths.user_profiles_dir(), "mine", "user")
c.eq("user and bundled profiles merge in the listing",
     app_paths.list_profiles(), ["mine", "starter"])
c.eq("a user-only profile is writable", app_paths.is_user_profile("mine"), True)

# -- missing profile -----------------------------------------------------------
c.eq("an unknown name resolves to where it would be written",
     app_paths.profile_read_path("nope").startswith(app_paths.user_dir()), True)

# -- migration -----------------------------------------------------------------
mig = os.path.join(tmp, "config2")
os.environ["LOUPEDECKAPP_CONFIG_DIR"] = mig
legacy = os.path.join(tmp, "legacy")
os.makedirs(os.path.join(legacy, "Profiles"))
app_paths.BUNDLED_DIR = legacy
write_profile(os.path.join(legacy, "Profiles"), "old", "legacy")
with open(os.path.join(legacy, "dynamic_profiles.json"), "w") as f:
    json.dump({"dynamic_mode": True, "default_profile": "old",
               "app_profiles": []}, f)

moved = app_paths.migrate_legacy()
c.eq("migration copies the profile and the bindings",
     sorted(moved), ["dynamic_profiles.json", "old.json"])
c.eq("the profile landed in the user directory",
     os.path.exists(os.path.join(mig, "Profiles", "old.json")), True)
c.eq("the bindings landed too",
     os.path.exists(os.path.join(mig, "dynamic_profiles.json")), True)
c.eq("the legacy copies are left in place (copy, not move)",
     os.path.exists(os.path.join(legacy, "Profiles", "old.json")), True)

c.eq("running it again copies nothing", app_paths.migrate_legacy(), [])

# A user who deleted a shipped profile must not have it resurrected.
os.remove(os.path.join(mig, "Profiles", "old.json"))
write_profile(os.path.join(mig, "Profiles"), "kept", "user")
c.eq("migration does not re-seed once the user has any profile",
     app_paths.migrate_legacy(), [])
c.eq("the deleted one stays deleted",
     os.path.exists(os.path.join(mig, "Profiles", "old.json")), False)

# -- installed layout ----------------------------------------------------------
# From a checkout the assets sit beside the module; installed from a wheel the
# modules land in site-packages and the assets under <prefix>/share. The finder
# looks for qml/ rather than trusting either location.
saved_prefix = sys.prefix
try:
    beside = os.path.join(tmp, "checkout")
    os.makedirs(os.path.join(beside, "qml"))
    app_paths.__file__ = os.path.join(beside, "app_paths.py")
    c.eq("assets beside the module win", app_paths._find_bundled_dir(), beside)

    bare = os.path.join(tmp, "sitepackages")
    os.makedirs(bare)
    app_paths.__file__ = os.path.join(bare, "app_paths.py")
    prefix = os.path.join(tmp, "prefix")
    os.makedirs(os.path.join(prefix, "share", "loupedeckapp", "qml"))
    sys.prefix = prefix
    c.eq("otherwise the install prefix is used", app_paths._find_bundled_dir(),
         os.path.join(prefix, "share", "loupedeckapp"))

    sys.prefix = os.path.join(tmp, "nowhere")
    c.eq("with neither present it reports where it looked",
         app_paths._find_bundled_dir(), bare)
finally:
    sys.prefix = saved_prefix

shutil.rmtree(tmp, ignore_errors=True)
# A relocatable bundle mounts somewhere different on every run, so it cannot
# use sys.prefix: its AppRun points at the payload with this instead.
mounted = os.path.join(tmp, "mnt", "usr")
os.makedirs(os.path.join(mounted, "share", "loupedeckapp", "qml"), exist_ok=True)
os.environ[app_paths.PREFIX_OVERRIDE] = mounted
try:
    c.eq("a bundle prefix is honoured over sys.prefix",
         app_paths._find_bundled_dir(),
         os.path.join(mounted, "share", "loupedeckapp"))
    os.environ[app_paths.PREFIX_OVERRIDE] = os.path.join(tmp, "nowhere")
    c.eq("a prefix with no assets in it is ignored",
         app_paths._find_bundled_dir().startswith(os.path.join(tmp, "nowhere")),
         False)
finally:
    os.environ.pop(app_paths.PREFIX_OVERRIDE, None)

sys.exit(c.done())
