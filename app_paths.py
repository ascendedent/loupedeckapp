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
import json
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


# -- applications --------------------------------------------------------------
# Profiles belong to an application, the way the official software arranges
# them: one folder per app, holding its profiles and an app.json saying which
# of them is its default. The folder layout is the hierarchy, so it is legible
# from a file manager and an app's whole setup is one directory to copy.
#
#   Profiles/
#     Default/       app.json, Starter.json, ...
#     Chrome/        app.json, Browsing.json, ...
#
# A profile is addressed as "App/Profile" (a *reference*). Neither an app nor a
# profile name may contain a slash, which is what makes that unambiguous.
DEFAULT_APP = "Default"
APP_META = "app.json"
REF_SEP = "/"


def split_ref(ref):
    """"Chrome/Browsing" -> ("Chrome", "Browsing").

    A bare name is read as belonging to the default app, so references written
    before apps existed still resolve.
    """
    text = str(ref or "")
    if REF_SEP in text:
        app, _, name = text.partition(REF_SEP)
        return (app.strip() or DEFAULT_APP, name.strip())
    return (DEFAULT_APP, text.strip())


def make_ref(app, name):
    return "%s%s%s" % (app or DEFAULT_APP, REF_SEP, name)


def user_app_dir(app):
    return os.path.join(user_profiles_dir(), str(app))


def bundled_app_dir(app):
    return os.path.join(bundled_profiles_dir(), str(app))


def ensure_user_app_dir(app):
    path = user_app_dir(app)
    os.makedirs(path, exist_ok=True)
    return path


def list_apps():
    """Every app available, user and bundled merged, sorted.

    The default app is always present even with nothing in it: the app list is
    the primary navigation and an empty one would leave nowhere to start.
    """
    names = {DEFAULT_APP}
    for base in (user_profiles_dir(), bundled_profiles_dir()):
        if not os.path.isdir(base):
            continue
        for entry in os.listdir(base):
            if os.path.isdir(os.path.join(base, entry)):
                names.add(entry)
    return sorted(names, key=lambda n: (n != DEFAULT_APP, n.lower()))


def app_meta_path(app, for_write=False):
    if for_write:
        return os.path.join(ensure_user_app_dir(app), APP_META)
    user = os.path.join(user_app_dir(app), APP_META)
    if os.path.exists(user):
        return user
    bundled = os.path.join(bundled_app_dir(app), APP_META)
    return bundled if os.path.exists(bundled) else user


def app_matches(app):
    """The window classes that mean this app is in focus.

    An app is what dynamic mode switches on: focus something whose wm_class (or
    bundle id on macOS) matches one of these, and this app's profile is what
    goes on the device.
    """
    raw = read_app_meta(app).get("match") or []
    if isinstance(raw, str):
        raw = [raw]
    return [str(m).strip() for m in raw if str(m).strip()]


def set_app_matches(app, matches):
    meta = dict(read_app_meta(app))
    meta["match"] = [str(m).strip() for m in (matches or []) if str(m).strip()]
    write_app_meta(app, meta)


def app_pages(app):
    """An app's pages, in the order they should be tried.

    A page is a second level of dynamic switching *inside* an application:
    Premiere Pro is one app, but Cut, Edit and Sound each want a different
    profile. The window class says which app is in front; the window title is
    the only finer signal a compositor gives us, so a page matches on that.

    Each entry is {"name", "match", "profile"}. Entries without a name or a
    profile are dropped rather than half-applied.
    """
    raw = read_app_meta(app).get("pages") or []
    pages = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "").strip()
        profile = str(entry.get("profile") or "").strip()
        if not name or not profile:
            continue
        pages.append({"name": name,
                      "match": str(entry.get("match") or "").strip(),
                      "profile": profile})
    return pages


def set_app_pages(app, pages):
    meta = dict(read_app_meta(app))
    meta["pages"] = [
        {"name": str(p.get("name") or "").strip(),
         "match": str(p.get("match") or "").strip(),
         "profile": str(p.get("profile") or "").strip()}
        for p in (pages or [])
        if str(p.get("name") or "").strip() and str(p.get("profile") or "").strip()
    ]
    write_app_meta(app, meta)


def app_default_profile(app):
    """Which of the app's profiles dynamic mode should load for it.

    Its recorded default if that still exists, otherwise its first profile:
    an app that matches a window but resolves to nothing would switch the
    device to a blank deck.
    """
    profiles = list_profiles(app)
    if not profiles:
        return ""
    recorded = read_app_meta(app).get("default_profile")
    if recorded in profiles:
        return recorded
    return profiles[0]


def set_app_default_profile(app, name):
    meta = dict(read_app_meta(app))
    meta["default_profile"] = str(name or "")
    write_app_meta(app, meta)


def read_app_meta(app):
    """{"match": [...], "default_profile": ...} for an app, or {} if it has
    none."""
    path = app_meta_path(app)
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        print("app_paths: could not read %s: %s" % (path, e))
        return {}
    return data if isinstance(data, dict) else {}


def write_app_meta(app, data):
    path = app_meta_path(app, for_write=True)
    try:
        with open(path, "w") as f:
            json.dump(data, f, indent=True)
    except OSError as e:
        print("app_paths: could not write %s: %s" % (path, e))


def is_user_app(app):
    """True when the app has a writable directory, i.e. is not purely bundled."""
    return os.path.isdir(user_app_dir(app))


def profile_read_path(ref, name=None):
    """Where a profile is read from: the user's copy if there is one, else the
    bundled original. Returns the user path when neither exists, so callers
    report a missing file in the place it would have been written.

    Takes either a reference ("Chrome/Browsing") or an (app, name) pair.
    """
    app, profile = (ref, name) if name is not None else split_ref(ref)
    user = os.path.join(user_app_dir(app), str(profile) + ".json")
    if os.path.exists(user):
        return user
    bundled = os.path.join(bundled_app_dir(app), str(profile) + ".json")
    if os.path.exists(bundled):
        return bundled
    return user


def profile_write_path(ref, name=None):
    """Always the user directory: the bundled copy is never modified."""
    app, profile = (ref, name) if name is not None else split_ref(ref)
    return os.path.join(ensure_user_app_dir(app), str(profile) + ".json")


def list_profiles(app=None):
    """Profile names in one app, user and bundled merged, sorted. A user copy
    and a bundled original with the same name appear once."""
    app = app or DEFAULT_APP
    names = set()
    for d in (user_app_dir(app), bundled_app_dir(app)):
        for f in glob.glob(os.path.join(d, "*.json")):
            base = os.path.splitext(os.path.basename(f))[0]
            if os.path.basename(f) != APP_META:
                names.add(base)
    return sorted(names)


def list_all_profiles():
    """Every profile everywhere, as references, for anything that has to look
    one up without knowing which app owns it."""
    return [make_ref(app, name)
            for app in list_apps() for name in list_profiles(app)]


def is_user_profile(ref, name=None):
    """True when a writable copy exists. Deleting is only meaningful for these:
    removing a user copy reveals the bundled original again."""
    app, profile = (ref, name) if name is not None else split_ref(ref)
    return os.path.exists(os.path.join(user_app_dir(app), str(profile) + ".json"))


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
    if not list_all_profiles_on_disk(user_profiles_dir()):
        legacy = glob.glob(os.path.join(
            bundled_app_dir(DEFAULT_APP), "*.json"))
        if legacy:
            ensure_user_app_dir(DEFAULT_APP)
            for src in legacy:
                shutil.copy2(src, os.path.join(user_app_dir(DEFAULT_APP),
                                               os.path.basename(src)))
                copied.append(os.path.basename(src))
    return copied


def list_all_profiles_on_disk(base):
    """Every profile file under a Profiles directory, flat or in app folders.

    Used by the migration, which has to see both layouts at once.
    """
    if not os.path.isdir(base):
        return []
    found = glob.glob(os.path.join(base, "*.json"))
    found += [f for f in glob.glob(os.path.join(base, "*", "*.json"))
              if os.path.basename(f) != APP_META]
    return sorted(found)


def migrate_to_apps():
    """Move a flat Profiles/ into Profiles/Default/.

    Profiles used to sit loose in one directory. Now they belong to an
    application, so the ones that predate that belong to the default app: they
    were not written with any application in mind, which is exactly what the
    default app means.

    Moves rather than copies. A copy would leave the old file where the app no
    longer looks, so an edit would silently go to one and a read to the other.
    """
    base = user_profiles_dir()
    loose = glob.glob(os.path.join(base, "*.json"))
    if not loose:
        return []
    target = ensure_user_app_dir(DEFAULT_APP)
    moved = []
    for src in loose:
        name = os.path.basename(src)
        dest = os.path.join(target, name)
        if os.path.exists(dest):
            # Already migrated once and written again since; the app folder is
            # the live one, so the loose file is stale.
            os.remove(src)
            continue
        shutil.move(src, dest)
        moved.append(os.path.splitext(name)[0])
    return sorted(moved)


def describe():
    return "assets: %s | user data: %s" % (BUNDLED_DIR, user_dir())
