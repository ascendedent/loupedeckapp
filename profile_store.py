"""Creating, copying, deleting and moving profiles and applications on disk.

This is everything the profile and application buttons do, minus the buttons.
It was living inside the QML Backend, which meant a quarter of a 2000-line Qt
object was file handling that has nothing to do with Qt, and none of it could
be tested without standing up a QGuiApplication first.

Every function returns its result alongside an error string rather than
raising: each one is driven by a button, every failure has to end up in front
of a person, and an empty error means it worked. Qt-free, like everything else
below the UI.
"""

import glob
import json
import os
import shutil

import app_paths
from LdConfiguration import LdConfiguration, SCHEMA_VERSION, apply_default_bindings

# What a name may not contain: it becomes a filename, and a profile called
# "../x" would be a way out of the profiles directory.
BAD_CHARS = set('/\\:*?"<>|')
NAME_RULES = ["Cannot be empty", "No / \\ : * ? \" < > |"]

# Marks a file as what it claims to be. Feeding an application to the profile
# importer should say so rather than fail on a missing key.
APP_KIND = "loupedeckapp.application"
BACKUP_KIND = "loupedeckapp.backup"


def clean_name(name):
    """A usable profile or application name, or "" if it is not one."""
    name = (name or "").strip()
    if not name:
        return ""
    if any(ch in BAD_CHARS for ch in name) or name in (".", ".."):
        return ""
    return name


def validate_profile(app, name):
    """"" when `name` can be created in `app`, otherwise why not."""
    clean = clean_name(name)
    if not clean:
        return "Enter a name without / \\ : * ? \" < > |"
    if os.path.exists(app_paths.profile_read_path(app, clean)):
        return "A profile called '%s' already exists" % clean
    return ""


def validate_app(name):
    clean = clean_name(name)
    if not clean:
        return "Enter a name without / \\ : * ? \" < > |"
    if clean in app_paths.list_apps():
        return "An app called '%s' already exists" % clean
    return ""


def _unused_profile_name(app, base):
    """`base`, or `base 2`, `base 3`... until one is free."""
    name, n = base, 2
    while os.path.exists(app_paths.profile_read_path(app, name)):
        name, n = "%s %d" % (base, n), n + 1
    return name


def _unused_app_name(base):
    name, n = base, 2
    while name in app_paths.list_apps():
        name, n = "%s %d" % (base, n), n + 1
    return name


def _write(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=True)


# -- profiles -----------------------------------------------------------------

def create_profile(app, name):
    """A new empty profile in `app`. Returns (reference, error)."""
    clean = clean_name(name)
    if not clean or os.path.exists(app_paths.profile_read_path(app, clean)):
        return ("", "A profile called '%s' already exists" % name)
    ref = app_paths.make_ref(app, clean)
    cfg = apply_default_bindings(LdConfiguration(profile=ref))
    try:
        _write(app_paths.profile_write_path(ref), cfg.to_JSON())
    except OSError as e:
        return ("", "Could not create it: %s" % e)
    return (ref, "")


def duplicate_profile(app, source, name):
    """Copy `source` to `name` within `app`. Returns (reference, error).

    Copies the file, not any in-memory draft: what you duplicate is what is on
    disk, so an unsaved edit is deliberately not carried over.
    """
    clean = clean_name(name)
    if not clean or not source:
        return ("", "Enter a name")
    if os.path.exists(app_paths.profile_read_path(app, clean)):
        return ("", "A profile called '%s' already exists" % clean)
    src = app_paths.profile_read_path(app, source)
    if not os.path.exists(src):
        return ("", "'%s' no longer exists" % source)
    ref = app_paths.make_ref(app, clean)
    try:
        with open(src) as f:
            data = json.load(f)
        data["profile"] = ref
        _write(app_paths.profile_write_path(ref), data)
    except (OSError, ValueError) as e:
        return ("", "Could not duplicate it: %s" % e)
    return (ref, "")


def rename_profile(app, old, name):
    """Returns (new reference, old reference, error).

    A profile that ships with the app leaves its original in place: renaming
    writes a user copy under the new name, and the bundled one stays available.
    """
    clean = clean_name(name)
    if not clean or not old or clean == old:
        return ("", "", "Enter a different name")
    src = app_paths.profile_read_path(app, old)
    if not os.path.exists(src):
        return ("", "", "'%s' no longer exists" % old)
    if os.path.exists(app_paths.profile_read_path(app, clean)):
        return ("", "", "A profile called '%s' already exists" % clean)
    ref, old_ref = app_paths.make_ref(app, clean), app_paths.make_ref(app, old)
    try:
        with open(src) as f:
            data = json.load(f)
        data["profile"] = ref
        _write(app_paths.profile_write_path(ref), data)
        if app_paths.is_user_profile(old_ref):
            os.remove(app_paths.profile_write_path(old_ref))
    except (OSError, ValueError) as e:
        return ("", "", "Could not rename it: %s" % e)
    return (ref, old_ref, "")


def delete_profile(app, name):
    """Returns (reference, where a copy was kept, error).

    A bundled profile is refused rather than deleted: the app must not remove
    files from its own installation.
    """
    if not name:
        return ("", "", "Nothing to delete")
    ref = app_paths.make_ref(app, name)
    if not app_paths.is_user_profile(ref):
        return ("", "", "'%s' ships with the app and cannot be deleted" % name)
    path = app_paths.profile_write_path(ref)
    kept = app_paths.trash(path, "%s %s.json" % (app, name),
                           {"kind": "profile", "app": app, "name": name})
    if not kept and os.path.exists(path):
        try:
            os.remove(path)
        except OSError as e:
            return ("", "", "Could not delete it: %s" % e)
    return (ref, kept, "")


def export_profile(app, name, path):
    """Write one profile to `path`. Returns an error, or "".

    Exports what is on disk rather than any draft, so an export is always
    something that can be re-imported and reproduced.
    """
    if not name or not path:
        return "Nothing to export"
    path = _with_json(path)
    try:
        with open(app_paths.profile_read_path(app, name)) as f:
            data = json.load(f)
        _write(path, data)
    except (OSError, ValueError) as e:
        return "Could not export: %s" % e
    return ""


def import_profile(app, path):
    """Read a profile file into `app`. Returns (name, error).

    Validated before it is written: a file that only fails when loaded would
    appear in the profile list as something that breaks when clicked.
    """
    if not path:
        return ("", "No file chosen")
    data, error = _read_json(path)
    if error:
        return ("", error)
    if not isinstance(data, dict) or "workspaces" not in data:
        if isinstance(data, dict) and data.get("kind") in (APP_KIND, BACKUP_KIND):
            return ("", "That is a whole application. Use Import app.")
        return ("", "That does not look like a profile (no workspaces)")
    error = _check_version(data.get("schema_version", 1), "Profile")
    if error:
        return ("", error)
    error = _check_loads(data)
    if error:
        return ("", "Profile could not be read: %s" % error)

    base = clean_name(data.get("profile")
                      and app_paths.split_ref(data["profile"])[1]
                      or os.path.splitext(os.path.basename(path))[0])
    if not base:
        return ("", "Profile has no usable name")
    name = _unused_profile_name(app, base)
    data["profile"] = app_paths.make_ref(app, name)
    try:
        _write(app_paths.profile_write_path(app, name), data)
    except OSError as e:
        return ("", "Could not write it: %s" % e)
    return (name, "")


# -- applications --------------------------------------------------------------

def create_app(name, match=""):
    """A new application with one empty profile. Returns (app, error).

    Empty applications are a trap: the list would show something that cannot be
    put on the device, so it starts with a profile.
    """
    clean = clean_name(name)
    if not clean or clean in app_paths.list_apps():
        return ("", "An app called '%s' already exists" % name)
    app_paths.ensure_user_app_dir(clean)
    ref, error = create_profile(clean, clean)
    if error:
        return ("", error)
    app_paths.set_app_default_profile(clean, clean)
    if match:
        app_paths.set_app_matches(clean, [match])
    return (clean, "")


def rename_app(old, name):
    """Returns an error, or "". The default application cannot be renamed."""
    clean = clean_name(name)
    if not clean or not old or clean == old:
        return "Enter a different name"
    if old == app_paths.DEFAULT_APP:
        return "The default app cannot be renamed"
    if clean in app_paths.list_apps():
        return "An app called '%s' already exists" % clean
    src = app_paths.user_app_dir(old)
    if not os.path.isdir(src):
        return "'%s' no longer exists" % old
    try:
        os.rename(src, app_paths.user_app_dir(clean))
    except OSError as e:
        return "Could not rename it: %s" % e
    return ""


def delete_app(name):
    """Returns (where a copy was kept, error)."""
    if not name:
        return ("", "Nothing to delete")
    if name == app_paths.DEFAULT_APP:
        return ("", "The default app cannot be deleted")
    path = app_paths.user_app_dir(name)
    if not os.path.isdir(path):
        return ("", "'%s' no longer exists" % name)
    kept = app_paths.trash(path, "app %s" % name, {"kind": "app", "app": name})
    if not kept and os.path.isdir(path):
        try:
            shutil.rmtree(path)
        except OSError as e:
            return ("", "Could not delete it: %s" % e)
    return (kept, "")


def app_bundle(app):
    """One application as data: its profiles, rules and pages."""
    bundle = {
        "app": app,
        "match": app_paths.app_matches(app),
        "default_profile": app_paths.app_default_profile(app),
        "pages": app_paths.app_pages(app),
        "profiles": {},
    }
    for name in app_paths.list_profiles(app):
        with open(app_paths.profile_read_path(app, name)) as f:
            bundle["profiles"][name] = json.load(f)
    return bundle


def export_app(app, path):
    """Write a whole application to one file. Returns an error, or ""."""
    if not path:
        return "Nothing to export"
    if not app_paths.list_profiles(app):
        return "'%s' has no profiles to export" % app
    try:
        bundle = dict(app_bundle(app), kind=APP_KIND,
                      schema_version=SCHEMA_VERSION)
        _write(_with_json(path), bundle)
    except (OSError, ValueError) as e:
        return "Could not export: %s" % e
    return ""


def import_app(path):
    """Read an exported application in as a new one. Returns (app, error)."""
    if not path:
        return ("", "No file chosen")
    bundle, error = _read_json(path)
    if error:
        return ("", error)
    if not isinstance(bundle, dict) or bundle.get("kind") != APP_KIND:
        if isinstance(bundle, dict) and bundle.get("kind") == BACKUP_KIND:
            return ("", "That is a backup of everything. Use Restore.")
        return ("", "That is not an exported application. A single profile "
                    "imports with Import in the profile list.")
    error = _check_version(bundle.get("schema_version", 1), "Application")
    if error:
        return ("", error)
    return write_bundle(bundle)


def write_bundle(bundle):
    """Write an application bundle in as a new app. Returns (app, error).

    Always a new one. A restore or an import that overwrites is one you cannot
    undo, and a duplicate to tidy up is the cheaper of the two problems.
    """
    profiles = bundle.get("profiles")
    if not isinstance(profiles, dict) or not profiles:
        return ("", "That application has no profiles in it")
    for name, data in profiles.items():
        if not clean_name(name):
            return ("", "Profile name '%s' cannot be used" % name)
        error = _check_loads(data)
        if error:
            return ("", "Profile '%s' could not be read: %s" % (name, error))

    base = clean_name(bundle.get("app") or "")
    if not base:
        return ("", "Application has no usable name")
    app = _unused_app_name(base)
    try:
        app_paths.ensure_user_app_dir(app)
        for name, data in profiles.items():
            data["profile"] = app_paths.make_ref(app, name)
            _write(app_paths.profile_write_path(app, name), data)
    except OSError as e:
        return ("", "Could not write it: %s" % e)
    app_paths.set_app_matches(app, bundle.get("match") or [])
    app_paths.set_app_pages(app, bundle.get("pages") or [])
    default = bundle.get("default_profile")
    if default in profiles:
        app_paths.set_app_default_profile(app, default)
    return (app, "")


# -- everything ----------------------------------------------------------------

def export_backup(path, settings, dynamic):
    """Every application, plus preferences and bindings. (profiles, error).

    Bundled profiles are included: a backup you have to reconstruct from two
    sources is not a backup.
    """
    if not path:
        return (0, "Nothing to export")
    backup = {
        "kind": BACKUP_KIND,
        "schema_version": SCHEMA_VERSION,
        "apps": [],
        "settings": dict(settings or {}),
        "dynamic": dict(dynamic or {}),
    }
    try:
        for app in app_paths.list_apps():
            bundle = app_bundle(app)
            if bundle["profiles"]:
                backup["apps"].append(bundle)
        _write(_with_json(path), backup)
    except (OSError, ValueError) as e:
        return (0, "Could not export: %s" % e)
    return (sum(len(a["profiles"]) for a in backup["apps"]), "")


def import_backup(path):
    """Restore a backup, adding rather than replacing. (apps, profiles, error).

    Preferences and dynamic bindings are read but deliberately not applied:
    they name profiles, and once names have been suffixed those names no longer
    mean what the file said.
    """
    if not path:
        return ([], 0, "No file chosen")
    backup, error = _read_json(path)
    if error:
        return ([], 0, error)
    if not isinstance(backup, dict) or backup.get("kind") != BACKUP_KIND:
        if isinstance(backup, dict) and backup.get("kind") == APP_KIND:
            return ([], 0, "That is a single application. Use Import app.")
        return ([], 0, "That is not a backup. A single application imports "
                       "with Import app, a single profile with Import.")
    apps = backup.get("apps")
    if not isinstance(apps, list) or not apps:
        return ([], 0, "That backup has nothing in it")
    error = _check_version(backup.get("schema_version", 1), "Backup")
    if error:
        return ([], 0, error)

    restored, profiles = [], 0
    for bundle in apps:
        if not isinstance(bundle, dict):
            continue
        name, error = write_bundle(dict(bundle))
        if error:
            return (restored, profiles,
                    "Could not restore '%s': %s" % (bundle.get("app"), error))
        restored.append(name)
        profiles += len(bundle.get("profiles") or {})
    return (restored, profiles, "")


# -- shared helpers ------------------------------------------------------------

def _with_json(path):
    return path if path.lower().endswith(".json") else path + ".json"


def _read_json(path):
    try:
        with open(path) as f:
            return (json.load(f), "")
    except OSError as e:
        return (None, "Could not read the file: %s" % e)
    except ValueError:
        return (None, "That file is not valid JSON")


def _check_version(version, noun):
    try:
        if int(version) > SCHEMA_VERSION:
            return ("%s is schema v%s; this build understands v%s"
                    % (noun, version, SCHEMA_VERSION))
    except (TypeError, ValueError):
        return "%s has an unreadable schema_version" % noun
    return ""


def _check_loads(data):
    """"" if this really is a loadable profile, otherwise why not.

    Proving it before writing is the difference between a bad file being
    refused and a bad file sitting in the list until someone clicks it.
    """
    try:
        LdConfiguration().from_JSON(data)
    except Exception as e:
        return "%s: %s" % (type(e).__name__, e)
    return ""
