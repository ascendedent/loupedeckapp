"""Where the app reads assets from and writes user data to.

Two locations, deliberately separate:

* **bundled** - the code and the assets shipped with it (`Profiles/`, `Images/`,
  `qml/`). Read-only in spirit: once this is packaged it may literally be, so
  nothing here may ever write to it.
* **user** - per-OS config directory holding the profiles you edit and the
  dynamic-mode bindings. Created on demand.

Profiles resolve **user first, then bundled**, so the profiles shipped with the
app show up in the list without being writable in place: saving one writes a
copy into the user directory, which then shadows the bundled original. That
gives starter profiles for free and makes a bad edit recoverable by deleting
the user copy.

Qt-free, like everything below the UI layer.
"""

import glob
import os
import shutil
import sys

# Set by a relocatable bundle to say where its payload is mounted; see
# packaging/appimage/build.sh.
PREFIX_OVERRIDE = "LOUPEDECKAPP_PREFIX"


def _find_bundled_dir():
    """Where the shipped assets (`qml/`, `Images/`, `Profiles/`) actually are.

    Running from a checkout they sit beside this module. Installed from a
    wheel, the modules land in site-packages while the assets go to
    `<prefix>/share/loupedeckapp`, because a flat module layout has no package
    for them to travel inside. Checking for `qml/` rather than trusting either
    location means the same code works both ways.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    if os.path.isdir(os.path.join(here, "qml")):
        return here
    # A bundle (AppImage) mounts somewhere different on every run, so it cannot
    # rely on sys.prefix: its AppRun says where the payload is.
    for base in (os.environ.get(PREFIX_OVERRIDE), sys.prefix):
        if not base:
            continue
        installed = os.path.join(base, "share", "loupedeckapp")
        if os.path.isdir(os.path.join(installed, "qml")):
            return installed
    return here          # let the caller fail with a path that says where it looked


BUNDLED_DIR = _find_bundled_dir()

# Set LOUPEDECKAPP_CONFIG_DIR to relocate user data (tests use it, and it gives
# anyone an escape hatch from the per-OS default).
ENV_OVERRIDE = "LOUPEDECKAPP_CONFIG_DIR"

APP_NAME = "loupedeckapp"
MAC_APP_NAME = "LoupedeckApp"


def user_dir():
    """Per-OS directory for data the user owns. Not created by this call."""
    override = os.environ.get(ENV_OVERRIDE)
    if override:
        return os.path.abspath(os.path.expanduser(override))
    if sys.platform == "darwin":
        return os.path.expanduser(os.path.join(
            "~", "Library", "Application Support", MAC_APP_NAME))
    # Linux and friends: respect XDG_CONFIG_HOME when it is set.
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser(
        os.path.join("~", ".config"))
    return os.path.join(base, APP_NAME)


def ensure_user_dir():
    path = user_dir()
    os.makedirs(path, exist_ok=True)
    return path


def user_profiles_dir():
    return os.path.join(user_dir(), "Profiles")


def bundled_profiles_dir():
    return os.path.join(BUNDLED_DIR, "Profiles")


def ensure_user_profiles_dir():
    path = user_profiles_dir()
    os.makedirs(path, exist_ok=True)
    return path


def dynamic_profiles_path():
    return os.path.join(user_dir(), "dynamic_profiles.json")


def asset_path(relative):
    """Resolve a bundled asset ('Images/foo.png'). Absolute paths pass through,
    since a user's own image can live anywhere."""
    if not relative:
        return relative
    if os.path.isabs(relative):
        return relative
    return os.path.join(BUNDLED_DIR, relative)


def profile_read_path(name):
    """Where `name` is read from: the user's copy if there is one, else the
    bundled original. Returns the user path when neither exists, so callers
    report a missing file in the place it would have been written."""
    user = os.path.join(user_profiles_dir(), str(name) + ".json")
    if os.path.exists(user):
        return user
    bundled = os.path.join(bundled_profiles_dir(), str(name) + ".json")
    if os.path.exists(bundled):
        return bundled
    return user


def profile_write_path(name):
    """Always the user directory: the bundled copy is never modified."""
    return os.path.join(ensure_user_profiles_dir(), str(name) + ".json")


def list_profiles():
    """Every profile name available, user and bundled merged, sorted. A user
    copy and a bundled original with the same name appear once."""
    names = set()
    for d in (user_profiles_dir(), bundled_profiles_dir()):
        for f in glob.glob(os.path.join(d, "*.json")):
            names.add(os.path.splitext(os.path.basename(f))[0])
    return sorted(names)


def is_user_profile(name):
    """True when a writable copy exists. Deleting is only meaningful for these:
    removing a user copy reveals the bundled original again."""
    return os.path.exists(os.path.join(user_profiles_dir(), str(name) + ".json"))


def migrate_legacy():
    """Move pre-AppPaths data out of the source tree, once.

    Earlier versions wrote profiles into the repo's own `Profiles/` and
    `dynamic_profiles.json` beside the code. Those are *copied* (not moved) into
    the user directory the first time this runs, so an existing checkout keeps
    working and nothing is lost if the copy turns out to be unwanted.

    Returns a list of what was copied, for logging.
    """
    copied = []
    legacy_dyn = os.path.join(BUNDLED_DIR, "dynamic_profiles.json")
    target_dyn = dynamic_profiles_path()
    if os.path.exists(legacy_dyn) and not os.path.exists(target_dyn):
        ensure_user_dir()
        shutil.copy2(legacy_dyn, target_dyn)
        copied.append("dynamic_profiles.json")

    # Only seed profiles when the user has none at all. Copying individually
    # would resurrect a profile the user had deliberately deleted.
    if not glob.glob(os.path.join(user_profiles_dir(), "*.json")):
        legacy = glob.glob(os.path.join(bundled_profiles_dir(), "*.json"))
        if legacy:
            ensure_user_profiles_dir()
            for src in legacy:
                shutil.copy2(src, os.path.join(user_profiles_dir(),
                                               os.path.basename(src)))
                copied.append(os.path.basename(src))
    return copied


def describe():
    return "assets: %s | user data: %s" % (BUNDLED_DIR, user_dir())
