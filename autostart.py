"""Start with the session, by way of an XDG autostart entry.

A desktop entry in `~/.config/autostart/` is what every Linux desktop reads,
KDE and GNOME included, so this writes one rather than reaching for a
per-desktop mechanism.

The awkward part is `Exec=`. Installed, that is the `loupedeckapp` command on
PATH. From a checkout it has to be the interpreter and the script by absolute
path, because a login session has neither the virtualenv nor the working
directory the app was started from. Either way the line is recorded and can be
checked later: a venv rebuilt somewhere else leaves an entry that silently does
nothing, and an autostart that silently does nothing is worse than none.

Qt-free.
"""

import os
import shlex
import shutil
import sys

APP_NAME = "loupedeckapp"
ENTRY_NAME = APP_NAME + ".desktop"

# The console script installed by pyproject's [project.gui-scripts].
CONSOLE_SCRIPT = APP_NAME


def autostart_dir():
    """`$XDG_CONFIG_HOME/autostart`, or the spec's default."""
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser(
        os.path.join("~", ".config"))
    return os.path.join(base, "autostart")


def entry_path():
    return os.path.join(autostart_dir(), ENTRY_NAME)


def exec_line():
    """How to start this app from a session with no venv and no cwd.

    Prefers the installed command: it survives the checkout moving, and it is
    what a packaged install should be using. Falls back to the running
    interpreter plus the script, both absolute and quoted.
    """
    installed = shutil.which(CONSOLE_SCRIPT)
    if installed:
        return shlex.quote(installed)
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "qml_app.py")
    return "%s %s" % (shlex.quote(os.path.abspath(sys.executable)),
                      shlex.quote(script))


def _entry_text(command):
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=Loupedeck Config\n"
        "Comment=Configure a Loupedeck CT, Live or Live S\n"
        "Exec=%s\n"
        "Icon=%s\n"
        "Terminal=false\n"
        "X-GNOME-Autostart-enabled=true\n"
        # Written by the app: editing it by hand works, but the app will
        # overwrite it if you ever toggle the setting again.
        "X-Loupedeckapp-Generated=true\n" % (command, APP_NAME))


def current_exec():
    """The Exec= line in the installed entry, or None if there is no entry."""
    path = entry_path()
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            for line in f:
                if line.startswith("Exec="):
                    return line[len("Exec="):].strip()
    except OSError:
        return None
    return ""


def enabled():
    return os.path.exists(entry_path())


def is_current():
    """Does the entry point at *this* copy of the app?

    False when it names something else: a venv that was rebuilt elsewhere, or a
    checkout that moved. The entry is still there and the session still runs
    it, so nothing looks wrong until you notice the app never started.
    """
    existing = current_exec()
    return existing is not None and existing == exec_line()


def enable():
    """Write the entry. Returns "" on success or a message to show the user."""
    try:
        os.makedirs(autostart_dir(), exist_ok=True)
        with open(entry_path(), "w") as f:
            f.write(_entry_text(exec_line()))
    except OSError as e:
        return "Could not write %s: %s" % (entry_path(), e)
    return ""


def disable():
    """Remove the entry. Returns "" on success or a message to show the user."""
    path = entry_path()
    if not os.path.exists(path):
        return ""
    try:
        os.remove(path)
    except OSError as e:
        return "Could not remove %s: %s" % (path, e)
    return ""


def status():
    """(enabled, current, detail) for the UI."""
    if not enabled():
        return False, True, "The app will not start with your session."
    if is_current():
        return True, True, "Starts with your session, running: %s" % exec_line()
    return True, False, (
        "An autostart entry exists but starts something else:\n%s\n\n"
        "That usually means the app moved, or its virtualenv was rebuilt "
        "elsewhere. Turn this off and on again to point it here."
        % (current_exec() or "(no Exec line)"))
