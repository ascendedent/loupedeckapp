"""Small persistent app preferences (not profile data).

Anything here is about the *app*, not about a profile: it survives switching
profiles and is not exported with one. Kept deliberately tiny; if this grows
past a handful of keys it wants a schema like LdConfiguration has.

Stored as JSON in the user config directory (see `app_paths`). Qt-free.
"""

import json
import os

import app_paths

# Device brightness, 0-100. The device quantises to steps of 10, so the slider
# moving without a visible change is expected at fine granularity.
DEFAULTS = {
    "brightness": 40,
    # Wire the CT's labelled buttons on any profile that leaves them empty.
    # Turn off to keep unbound buttons unbound.
    "auto_bind_ct_buttons": True,
    # "hold" (fn works while held) or "latch" (a press sticks until pressed
    # again, with the key lit while it is on).
    "fn_mode": "hold",
    # Colour of the fn keys while the layer is engaged.
    "fn_active_color": "#ffffff",
    # Colour when it is not. Blank means "whatever the workspace's LED colour
    # says", falling back to the same dim grey as the other buttons.
    "fn_inactive_color": "",
}


class Settings:
    def __init__(self, path=None):
        self.path = path or os.path.join(app_paths.user_dir(), "settings.json")
        self.values = dict(DEFAULTS)
        self.load()

    def load(self):
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path) as f:
                data = json.load(f)
        except (OSError, ValueError) as e:
            print("settings: could not read %s: %s" % (self.path, e))
            return
        if isinstance(data, dict):
            # Overlay rather than replace: a key this build does not know stays
            # in the file, and one it does know but the file lacks keeps its
            # default instead of vanishing.
            for key, value in data.items():
                self.values[key] = value

    def save(self):
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, "w") as f:
                json.dump(self.values, f, indent=2)
        except OSError as e:
            print("settings: could not write %s: %s" % (self.path, e))

    def get(self, key, default=None):
        return self.values.get(key, DEFAULTS.get(key, default))

    def set(self, key, value):
        self.values[key] = value

    # -- typed accessors ---------------------------------------------------
    @property
    def brightness(self):
        try:
            return max(0, min(100, int(self.get("brightness"))))
        except (TypeError, ValueError):
            return DEFAULTS["brightness"]

    @brightness.setter
    def brightness(self, value):
        try:
            self.set("brightness", max(0, min(100, int(value))))
        except (TypeError, ValueError):
            pass

    @property
    def auto_bind_ct_buttons(self):
        return bool(self.get("auto_bind_ct_buttons"))

    @property
    def fn_active_color(self):
        return str(self.get("fn_active_color") or DEFAULTS["fn_active_color"])

    @property
    def fn_inactive_color(self):
        return str(self.get("fn_inactive_color") or "")

    @property
    def fn_mode(self):
        mode = str(self.get("fn_mode") or "").strip().lower()
        return mode if mode in ("hold", "latch") else DEFAULTS["fn_mode"]
