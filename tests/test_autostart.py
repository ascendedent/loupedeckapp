"""Starting with the session.

The failure mode worth guarding is the quiet one: an entry that exists and runs
something that is no longer there. The session obeys it, the app never starts,
and nothing says why.
"""
import os
import sys
import tempfile

from _harness import Checks

tmp = tempfile.mkdtemp()
os.environ["XDG_CONFIG_HOME"] = os.path.join(tmp, "config")
os.environ["LOUPEDECKAPP_CONFIG_DIR"] = os.path.join(tmp, "config", "loupedeckapp")

import autostart                                                  # noqa: E402

c = Checks()

c.eq("the entry goes where XDG says", autostart.autostart_dir(),
     os.path.join(tmp, "config", "autostart"))
c.eq("named for the app", os.path.basename(autostart.entry_path()),
     "loupedeckapp.desktop")
c.eq("nothing is enabled to begin with", autostart.enabled(), False)
c.eq("and there is no Exec to read", autostart.current_exec(), None)

on, current, detail = autostart.status()
c.eq("status says so", (on, current), (False, True))
c.eq("in words", "will not start" in detail, True)

# -- enabling ----------------------------------------------------------------
c.eq("enabling reports no error", autostart.enable(), "")
c.eq("the entry exists", os.path.exists(autostart.entry_path()), True)
c.eq("and it is enabled", autostart.enabled(), True)

text = open(autostart.entry_path()).read()
c.eq("it is a desktop entry", text.startswith("[Desktop Entry]"), True)
c.eq("of the right type", "Type=Application" in text, True)
c.eq("that GNOME will honour", "X-GNOME-Autostart-enabled=true" in text, True)
c.eq("marked as ours, so a hand-edit is not mistaken for one",
     "X-Loupedeckapp-Generated=true" in text, True)
c.eq("it names the icon that ships", "Icon=loupedeckapp" in text, True)

c.eq("the Exec is what we would write now",
     autostart.current_exec(), autostart.exec_line())
c.eq("and it is recognised as current", autostart.is_current(), True)

# A login session has neither the virtualenv nor the working directory the app
# was started from, so nothing in the command may be relative.
command = autostart.exec_line()
first = command.split()[0].strip("'\"")
c.eq("the command starts with an absolute path", os.path.isabs(first), True)
c.eq("and every part of it exists",
     all(os.path.exists(part.strip("'\""))
         for part in command.split() if part.startswith(("/", "'/"))), True)

on, current, detail = autostart.status()
c.eq("status now reads enabled", (on, current), (True, True))
c.eq("and shows the command", autostart.exec_line() in detail, True)

# -- a stale entry -----------------------------------------------------------
# The case that made this worth writing: the app moved, or its venv was rebuilt
# somewhere else. The entry still exists, so nothing looks wrong.
with open(autostart.entry_path(), "w") as f:
    f.write("[Desktop Entry]\nType=Application\nExec=/gone/python /gone/qml_app.py\n")

c.eq("a stale entry still counts as enabled", autostart.enabled(), True)
c.eq("but not as current", autostart.is_current(), False)
on, current, detail = autostart.status()
c.eq("status separates the two", (on, current), (True, False))
c.eq("and says what it points at instead", "/gone/python" in detail, True)
c.eq("with what to do about it", "off and on again" in detail, True)

c.eq("re-enabling repoints it", autostart.enable(), "")
c.eq("and it is current again", autostart.is_current(), True)

# -- an entry with no Exec ---------------------------------------------------
with open(autostart.entry_path(), "w") as f:
    f.write("[Desktop Entry]\nType=Application\n")
c.eq("an entry with no Exec reads as empty, not missing",
     autostart.current_exec(), "")
c.eq("and is not current", autostart.is_current(), False)

# -- disabling ---------------------------------------------------------------
c.eq("disabling reports no error", autostart.disable(), "")
c.eq("the entry is gone", autostart.enabled(), False)
c.eq("disabling again is not an error", autostart.disable(), "")

# -- writing where we cannot ------------------------------------------------
os.environ["XDG_CONFIG_HOME"] = "/proc/nonexistent/nope"
err = autostart.enable()
c.eq("a write that fails says so rather than silently not sticking",
     err != "" and "Could not write" in err, True)
c.eq("and it is not reported as enabled", autostart.enabled(), False)
os.environ["XDG_CONFIG_HOME"] = os.path.join(tmp, "config")

sys.exit(c.done())
