"""Applications, their profiles, and the pages inside them.

The hierarchy the official software uses: an application owns profiles and the
window classes that mean it is in front, and pages inside it switch profile on
a finer signal. Premiere Pro is one app; Cut, Edit and Sound are pages of it.
"""
import json
import os
import sys
import tempfile

from _harness import Checks

tmp = tempfile.mkdtemp()
os.environ["LOUPEDECKAPP_CONFIG_DIR"] = os.path.join(tmp, "config")

import app_paths                                                  # noqa: E402
import profile_manager                                            # noqa: E402
from LdConfiguration import LdConfiguration                       # noqa: E402

c = Checks()

# The repo's own Profiles/ would otherwise show through as bundled apps.
app_paths.BUNDLED_DIR = os.path.join(tmp, "install")
os.makedirs(os.path.join(app_paths.BUNDLED_DIR, "Profiles"))

DEFAULT = app_paths.DEFAULT_APP


def write(app, name):
    ref = app_paths.make_ref(app, name)
    cfg = LdConfiguration(profile=ref)
    with open(app_paths.profile_write_path(ref), "w") as f:
        json.dump(cfg.to_JSON(), f)
    return ref


# -- references --------------------------------------------------------------
c.eq("a reference splits", app_paths.split_ref("Premiere/Cut"), ("Premiere", "Cut"))
c.eq("a bare name means the default app",
     app_paths.split_ref("Starter"), (DEFAULT, "Starter"))
c.eq("and one is built the same way",
     app_paths.make_ref("Premiere", "Cut"), "Premiere/Cut")
c.eq("an empty app in a reference still means the default",
     app_paths.split_ref("/Cut"), (DEFAULT, "Cut"))

# -- apps hold their own profiles --------------------------------------------
c.eq("the default app exists even with nothing in it",
     app_paths.list_apps(), [DEFAULT])

write(DEFAULT, "Starter")
write("Premiere", "Cut")
write("Premiere", "Sound")
c.eq("apps are listed, default first",
     app_paths.list_apps(), [DEFAULT, "Premiere"])
c.eq("each app lists only its own profiles",
     (app_paths.list_profiles(DEFAULT), app_paths.list_profiles("Premiere")),
     (["Starter"], ["Cut", "Sound"]))
c.eq("and everything can be listed at once",
     app_paths.list_all_profiles(),
     ["Default/Starter", "Premiere/Cut", "Premiere/Sound"])

# Same profile name in two apps is not a collision: that is the point of apps.
write("OBS", "Cut")
c.eq("the same name in two apps is two profiles",
     app_paths.profile_read_path("Premiere/Cut") !=
     app_paths.profile_read_path("OBS/Cut"), True)

cfg = LdConfiguration()
cfg.load("Premiere/Cut")
c.eq("a profile knows the app it was loaded from", cfg.profile, "Premiere/Cut")

# -- matching ----------------------------------------------------------------
app_paths.set_app_matches("Premiere", ["Adobe Premiere Pro", "premiere"])
c.eq("matches are stored", app_paths.app_matches("Premiere"),
     ["Adobe Premiere Pro", "premiere"])
c.eq("blank entries are dropped",
     (app_paths.set_app_matches("OBS", ["obs", "  ", ""]),
      app_paths.app_matches("OBS"))[1], ["obs"])

pm = profile_manager.ProfileManager(os.path.join(tmp, "dyn.json"))
c.eq("an exact window class finds its app",
     pm.resolve_app("premiere"), "Premiere")
c.eq("so does a substring, so one rule covers a family",
     pm.resolve_app("Adobe Premiere Pro 2024"), "Premiere")
c.eq("case does not matter", pm.resolve_app("OBS"), "OBS")
c.eq("an unclaimed window belongs to no app",
     pm.resolve_app("inkscape"), None)
c.eq("and nothing focused is not a window", pm.resolve_app(""), None)

# -- an app resolves to a profile --------------------------------------------
c.eq("an app with no recorded default uses its first profile",
     pm.resolve("premiere"), "Premiere/Cut")
app_paths.set_app_default_profile("Premiere", "Sound")
c.eq("a recorded default is used", pm.resolve("premiere"), "Premiere/Sound")
app_paths.set_app_default_profile("Premiere", "deleted")
c.eq("a default that no longer exists falls back to the first",
     pm.resolve("premiere"), "Premiere/Cut")
app_paths.set_app_default_profile("Premiere", "Sound")

# -- pages -------------------------------------------------------------------
app_paths.set_app_pages("Premiere", [
    {"name": "Cutting", "match": "Editing", "profile": "Cut"},
    {"name": "Audio", "match": "Audio", "profile": "Sound"},
])
c.eq("pages are stored in order",
     [p["name"] for p in app_paths.app_pages("Premiere")], ["Cutting", "Audio"])

c.eq("a title picks the page",
     pm.resolve("premiere", "Project.prproj - Adobe Premiere Pro - Editing"),
     "Premiere/Cut")
c.eq("a different title picks a different page",
     pm.resolve("premiere", "Project.prproj - Adobe Premiere Pro - Audio"),
     "Premiere/Sound")
c.eq("a title matching nothing falls back to the app's own default",
     pm.resolve("premiere", "Project.prproj - Colour"), "Premiere/Sound")
c.eq("and no title at all does the same",
     pm.resolve("premiere", ""), "Premiere/Sound")
c.eq("pages of one app do not apply to another",
     pm.resolve("obs", "Editing"), "OBS/Cut")

# First match wins, so order is precedence and the user controls it.
app_paths.set_app_pages("Premiere", [
    {"name": "Audio", "match": "Audio", "profile": "Sound"},
    {"name": "Anything", "match": "Adobe", "profile": "Cut"},
])
c.eq("the first matching page wins",
     pm.resolve("premiere", "Adobe Premiere Pro - Audio"), "Premiere/Sound")

# A page pointing at a profile that has gone must not switch to nothing.
app_paths.set_app_pages("Premiere", [
    {"name": "Gone", "match": "Adobe", "profile": "deleted"}])
c.eq("a page pointing at a missing profile falls through to the default",
     pm.resolve("premiere", "Adobe Premiere Pro"), "Premiere/Sound")

# Half-written pages are dropped rather than half-applied.
app_paths.set_app_pages("Premiere", [
    {"name": "", "match": "x", "profile": "Cut"},
    {"name": "NoProfile", "match": "x", "profile": ""},
    {"name": "Good", "match": "x", "profile": "Cut"},
])
c.eq("only complete pages survive",
     [p["name"] for p in app_paths.app_pages("Premiere")], ["Good"])

# -- older bindings still work -----------------------------------------------
# They were written before apps existed; dropping them would silently change
# what a focus change does.
pm.set_binding("inkscape", "Starter")
c.eq("a bare binding is qualified to the default app",
     pm.app_profiles[-1]["profile"], "Default/Starter")
c.eq("and still resolves", pm.resolve("inkscape"), "Default/Starter")
c.eq("but an app that claims the window wins over one",
     (pm.set_binding("premiere", "Default/Starter"),
      pm.resolve("premiere", ""))[1], "Premiere/Sound")

pm.default_profile = "Default/Starter"
c.eq("an unclaimed window gets the fallback",
     pm.resolve("gimp"), "Default/Starter")

sys.exit(c.done())
