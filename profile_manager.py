"""Profile binding + dynamic-mode state (Qt-agnostic application service).

A *profile* is one saved `Profiles/<name>.json` (a full LdConfiguration). This
manager records which profile to activate for which focused app, plus a default
(system) profile used when nothing matches. It does not load profiles itself —
it just *resolves* a focused window's ``wm_class`` to a profile name; the app
(LdApp) performs the actual switch. Pairs with `window_watcher.WindowWatcher`.

Persisted to ``dynamic_profiles.json`` at the repo root:

    {
      "dynamic_mode": true,
      "default_profile": "system",
      "app_profiles": [
        {"match": {"wm_class": "google-chrome"}, "profile": "browser"}
      ]
    }
"""

import json
import os

DEFAULT_PATH = "dynamic_profiles.json"


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
        self.default_profile = data.get("default_profile")
        self.app_profiles = [p for p in data.get("app_profiles", [])
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
    def resolve(self, wm_class):
        """Return the profile name to activate for a focused window's wm_class.

        Exact match wins; otherwise a case-insensitive substring match (so
        'chrome' binds 'google-chrome'); otherwise the default profile (or None).
        """
        if not wm_class:
            return self.default_profile
        wm_l = wm_class.lower()
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
        for p in self.app_profiles:
            if p["match"]["wm_class"].lower() == wm_class.lower():
                p["profile"] = profile_name
                return
        self.app_profiles.append({"match": {"wm_class": wm_class}, "profile": profile_name})

    def remove_binding(self, wm_class):
        self.app_profiles = [p for p in self.app_profiles
                             if p["match"]["wm_class"].lower() != wm_class.lower()]

    def set_dynamic_mode(self, enabled):
        self.dynamic_mode = bool(enabled)
