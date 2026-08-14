"""Dynamic-mode resolution (Qt-agnostic application service).

An *application* owns a folder of profiles and the window classes that mean it
is in front (`app_paths`). This manager turns a focused window into the profile
reference that should go on the device: the app that claims the window, then
the older per-window bindings, then a default. It does not load anything
itself; the QML Backend performs the switch. Pairs with
`window_watcher.WindowWatcher`.

Persisted to ``dynamic_profiles.json`` in the user config directory
(see ``app_paths``). Profiles are named by reference now that they live inside
an application; a bare name written by an older build reads as belonging to the
default app:

    {
      "dynamic_mode": true,
      "default_profile": "Default/system",
      "app_profiles": [
        {"match": {"wm_class": "google-chrome"}, "profile": "Chrome/browsing"}
      ]
    }
"""

import json
import os

import app_paths

# Callers normally pass app_paths.dynamic_profiles_path(); this bare default is
# only a fallback for a ProfileManager built without one.
DEFAULT_PATH = "dynamic_profiles.json"


def _qualify(ref):
    """A profile reference, filling in the default app for a bare name."""
    if not ref:
        return ref
    app, name = app_paths.split_ref(ref)
    return app_paths.make_ref(app, name) if name else None


class ProfileManager:
    def __init__(self, path=DEFAULT_PATH):
        self.path = path
        self.dynamic_mode = False
        self.default_profile = None
        self.app_profiles = []  # list of {"match": {"wm_class": str}, "profile": str}
        self.load()

    # -- persistence -------------------------------------------------------
    def load(self):
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path) as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            print("profile_manager: could not read %s: %s" % (self.path, e))
            return
        self.dynamic_mode = bool(data.get("dynamic_mode", False))
        # Bare names predate applications and mean the default app. Qualifying
        # them on the way in means everything downstream deals in references
        # only, rather than each caller guessing.
        self.default_profile = _qualify(data.get("default_profile"))
        self.app_profiles = [dict(p, profile=_qualify(p["profile"]))
                             for p in data.get("app_profiles", [])
                             if p.get("profile") and p.get("match", {}).get("wm_class")]

    def save(self):
        data = {
            "dynamic_mode": self.dynamic_mode,
            "default_profile": self.default_profile,
            "app_profiles": self.app_profiles,
        }
        with open(self.path, "w") as f:
            json.dump(data, f, indent=2)

    # -- resolution --------------------------------------------------------
    def resolve_app(self, wm_class):
        """Which application a focused window belongs to, or None.

        Apps are the unit dynamic mode switches on: each carries the window
        classes that mean it is in front. Exact match wins, then a
        case-insensitive substring match, so an app matching "chrome" claims
        "google-chrome".
        """
        if not wm_class:
            return None
        wm_l = str(wm_class).lower()
        apps = [(name, app_paths.app_matches(name))
                for name in app_paths.list_apps()]
        for name, matches in apps:
            if any(m.lower() == wm_l for m in matches):
                return name
        for name, matches in apps:
            if any(m.lower() in wm_l for m in matches):
                return name
        return None

    def resolve_page(self, app, title):
        """Which of an app's pages the window title indicates, or None.

        Premiere Pro is one application with Cut, Edit and Sound inside it, and
        the title is the only signal a compositor gives us that is finer than
        the window class. Pages are tried in order, so the first match wins and
        the user controls precedence by arranging them.
        """
        if not app or not title:
            return None
        low = str(title).lower()
        for page in app_paths.app_pages(app):
            pattern = page["match"].lower()
            if pattern and pattern in low:
                return page
        return None

    def resolve(self, wm_class, title=""):
        """The profile reference to activate for a focused window.

        An application that claims the window decides first, because that is
        what an app is for, and a page inside it refines that. The older
        per-window bindings are still honoured after that: they were written
        before apps existed and throwing them away would silently change what a
        profile switch does. Failing all of it, the default profile.
        """
        if not wm_class:
            return self.default_profile
        app = self.resolve_app(wm_class)
        if app:
            page = self.resolve_page(app, title)
            if page and page["profile"] in app_paths.list_profiles(app):
                return app_paths.make_ref(app, page["profile"])
            name = app_paths.app_default_profile(app)
            if name:
                return app_paths.make_ref(app, name)
        wm_l = str(wm_class).lower()
        # exact first
        for p in self.app_profiles:
            if p["match"]["wm_class"].lower() == wm_l:
                return p["profile"]
        # then substring (binding pattern contained in the class)
        for p in self.app_profiles:
            if p["match"]["wm_class"].lower() in wm_l:
                return p["profile"]
        return self.default_profile

    # -- editing -----------------------------------------------------------
    def set_binding(self, wm_class, profile_name):
        ref = _qualify(profile_name)
        for p in self.app_profiles:
            if p["match"]["wm_class"].lower() == wm_class.lower():
                p["profile"] = ref
                return
        self.app_profiles.append({"match": {"wm_class": wm_class}, "profile": ref})

    def remove_binding(self, wm_class):
        self.app_profiles = [p for p in self.app_profiles
                             if p["match"]["wm_class"].lower() != wm_class.lower()]

    def set_dynamic_mode(self, enabled):
        self.dynamic_mode = bool(enabled)
