"""Applications installed on this machine, for the app picker.

Adding an application means naming it and saying which windows belong to it.
Typing a window class from memory is the worst way to do that, so this reads
what the system already knows: XDG desktop entries on Linux, `.app` bundles on
macOS.

The match key is the important part, and each platform has a good one:

* **Linux**: `StartupWMClass` from the desktop entry, which exists precisely so
  a launcher can tie a window to the thing that launched it. Where an entry
  omits it, the executable's own name is the usual answer and is what
  compositors report for most toolkits.
* **macOS**: the bundle identifier (`com.apple.Safari`), which is what
  `MacWatcher` reports.

Qt-free, like everything else below the UI. Nothing here executes anything it
finds; the files are parsed as text and data.
"""

import glob
import os
import plistlib
import re
import shlex

import platform_env

# Where each platform keeps the things it has installed. User locations last:
# they win a name collision, which is what a user-installed override is for.
LINUX_DIRS = [
    "/usr/share/applications",
    "/usr/local/share/applications",
    "/var/lib/snapd/desktop/applications",
    "/var/lib/flatpak/exports/share/applications",
    "~/.local/share/flatpak/exports/share/applications",
    "~/.local/share/applications",
]

MAC_DIRS = [
    "/Applications",
    "/System/Applications",
    "/System/Applications/Utilities",
    "~/Applications",
]

# Entries that exist to handle a URL or a file type rather than to be launched.
# Listing them would bury the applications a user recognises.
_SKIP_SUFFIXES = ("-url-handler", "-uri-handler")


def _entry_dirs():
    dirs = LINUX_DIRS if platform_env.os_name() != platform_env.MACOS else MAC_DIRS
    extra = os.environ.get("XDG_DATA_DIRS", "")
    if extra and platform_env.os_name() != platform_env.MACOS:
        dirs = [os.path.join(d, "applications")
                for d in extra.split(":") if d] + dirs
    seen, out = set(), []
    for d in dirs:
        path = os.path.abspath(os.path.expanduser(d))
        if path not in seen:
            seen.add(path)
            out.append(path)
    return out


# -- Linux: XDG desktop entries -----------------------------------------------

def parse_desktop_entry(text):
    """The [Desktop Entry] group as a dict, ignoring the rest.

    A desktop file also carries per-action groups and translated keys; only the
    main group and the untranslated keys are wanted, so `Name[de]` does not
    overwrite `Name`.
    """
    fields = {}
    in_main = False
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("[") and line.endswith("]"):
            in_main = line == "[Desktop Entry]"
            continue
        if not in_main or "=" not in line or line.startswith("#"):
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if "[" in key:            # a translation of a key we already have
            continue
        fields.setdefault(key, value.strip())
    return fields


def _exec_binary(exec_line):
    """The program a desktop entry runs, without its arguments.

    Exec carries field codes (%U, %F) and may be wrapped in env or flatpak;
    what is wanted is the last path-looking token's basename, which is what a
    compositor usually reports as the window class.
    """
    if not exec_line:
        return ""
    try:
        parts = shlex.split(exec_line)
    except ValueError:
        parts = exec_line.split()
    # Wrappers are skipped by *basename*: an entry says "/usr/bin/flatpak run
    # ... org.gimp.GIMP", and matching the bare word "flatpak" against the full
    # path missed it, so every flatpak came back as "flatpak".
    WRAPPERS = {"env", "sh", "bash", "-c", "flatpak", "run", "snap",
                "systemd-run", "gtk-launch", "dbus-run-session"}
    for part in parts:
        if part.startswith("%") or part.startswith("-") or "=" in part:
            continue                       # field code, flag, or an env var
        base = os.path.basename(part)
        if base in WRAPPERS:
            continue
        return base
    return ""


def _linux_apps():
    found = {}
    for directory in _entry_dirs():
        for path in sorted(glob.glob(os.path.join(directory, "*.desktop"))):
            try:
                with open(path, encoding="utf-8", errors="replace") as f:
                    fields = parse_desktop_entry(f.read())
            except OSError:
                continue
            if fields.get("Type", "Application") != "Application":
                continue
            if fields.get("NoDisplay", "").lower() == "true":
                continue
            if fields.get("Hidden", "").lower() == "true":
                continue
            name = fields.get("Name", "").strip()
            if not name:
                continue
            stem = os.path.splitext(os.path.basename(path))[0]
            if stem.endswith(_SKIP_SUFFIXES):
                continue
            match = (fields.get("StartupWMClass", "").strip()
                     or _exec_binary(fields.get("Exec", "")))
            if not match:
                continue
            found[name] = {"name": name, "match": match, "source": path}
    return found


# -- macOS: application bundles -----------------------------------------------

def _mac_apps():
    found = {}
    for directory in _entry_dirs():
        if not os.path.isdir(directory):
            continue
        for path in sorted(glob.glob(os.path.join(directory, "*.app"))):
            info = os.path.join(path, "Contents", "Info.plist")
            name = os.path.splitext(os.path.basename(path))[0]
            bundle_id = ""
            try:
                with open(info, "rb") as f:
                    data = plistlib.load(f)
                bundle_id = str(data.get("CFBundleIdentifier") or "")
                name = str(data.get("CFBundleDisplayName")
                           or data.get("CFBundleName") or name)
            except (OSError, ValueError, plistlib.InvalidFileException):
                # A bundle with an unreadable Info.plist is still an app the
                # user can see; the folder name is a usable answer for both.
                pass
            match = bundle_id or name
            found[name] = {"name": name, "match": match, "source": path}
    return found


# -- public --------------------------------------------------------------------

def list_installed():
    """Every application this machine can see, sorted by name.

    Each entry is {"name", "match", "source"}. Returns [] rather than raising
    on a platform with no implementation: an empty picker is a picker with
    nothing in it, not a broken dialog.
    """
    try:
        if platform_env.os_name() == platform_env.MACOS:
            found = _mac_apps()
        elif platform_env.os_name() == platform_env.LINUX:
            found = _linux_apps()
        else:
            return []
    except Exception as e:              # never take the dialog down with it
        print("installed_apps: could not read installed applications: %s" % e)
        return []
    return sorted(found.values(), key=lambda a: a["name"].lower())


def search(query, entries=None):
    """Installed applications matching `query`, name or match key."""
    entries = list_installed() if entries is None else entries
    q = (query or "").strip().lower()
    if not q:
        return entries
    return [e for e in entries
            if q in e["name"].lower() or q in e["match"].lower()]
