"""Reading the focused window on each desktop.

Dynamic switching is the point of applications and pages, and it does nothing at
all without one of these. Only the KDE one can run here, so what is checked is
the parsing (which is where a wrong answer comes from) and the choosing (which
is where "does nothing and says nothing" comes from).
"""
import os
import sys
import tempfile

from _harness import Checks

tmp = tempfile.mkdtemp()
os.environ["LOUPEDECKAPP_CONFIG_DIR"] = os.path.join(tmp, "config")

import platform_env                                               # noqa: E402
import setup_check                                                # noqa: E402
import window_watcher                                             # noqa: E402

c = Checks()

# -- X11: parsing xprop -------------------------------------------------------
X = window_watcher.XpropWatcher

c.eq("a window id is dug out of the property",
     X._window_id("_NET_ACTIVE_WINDOW(WINDOW): window id # 0x3400007"),
     "0x3400007")
c.eq("nothing focused reads as nothing",
     X._window_id("_NET_ACTIVE_WINDOW(WINDOW): window id # 0x0"), "")
c.eq("and so does an unparseable answer", X._window_id("no such property"), "")

# WM_CLASS carries the instance and the class. The class is what an application
# is known by, and what a desktop entry's StartupWMClass matches.
c.eq("the class is taken, not the instance",
     X._wm_class('WM_CLASS(STRING) = "navigator", "firefox"'), "firefox")
c.eq("one value alone is still usable",
     X._wm_class('WM_CLASS(STRING) = "code"'), "code")
c.eq("a missing property is empty", X._wm_class("not found."), "")

c.eq("a title is unquoted",
     X._string_value('_NET_WM_NAME(UTF8_STRING) = "Project - VS Code"'),
     "Project - VS Code")

watcher = X()
watcher.bin = None
c.eq("with no xprop there is nothing to poll", watcher.poll_once(), ("", ""))

# -- GNOME: parsing an extension's reply --------------------------------------
G = window_watcher.GnomeWatcher

c.eq("gdbus's wrapper is stripped off",
     G._payload('(\'{"wm_class": "firefox", "title": "Reddit"}\',)'),
     {"wm_class": "firefox", "title": "Reddit"})
c.eq("an empty reply is nothing", G._payload(""), None)
c.eq("and so is one that is not JSON", G._payload("('not json',)"), None)

c.eq("a single-window extension answers directly",
     G._focused({"wm_class": "firefox"}, False), {"wm_class": "firefox"})
c.eq("a listing extension is searched for the focused one",
     G._focused([{"wm_class": "a", "focus": False},
                 {"wm_class": "b", "focus": True}], True)["wm_class"], "b")
c.eq("a listing with nothing focused is nothing",
     G._focused([{"wm_class": "a", "focus": False}], True), None)
c.eq("and a reply of the wrong shape is nothing",
     G._focused({"wm_class": "a"}, True), None)


class FakeGnome(window_watcher.GnomeWatcher):
    """The extension's side of the conversation, without GNOME."""

    def __init__(self, reply):
        super().__init__()
        self.bin = "/usr/bin/gdbus"
        self.reply = reply
        self.calls = []

    def _call(self, path, method):
        self.calls.append(method)
        return self.reply.get(method, "")


single = ('org.gnome.shell.extensions.FocusedWindow.Get',
          '(\'{"wm_class": "Code", "title": "app.py - loupedeckapp", "pid": 42}\',)')
g = FakeGnome({single[0]: single[1]})
c.eq("the focused window is read", g.poll_once(),
     ("Code", "app.py - loupedeckapp"))
c.eq("with its pid, which is how the app recognises its own window",
     g.last_pid, 42)
before = len(g.calls)
g.poll_once()
c.eq("the interface that answered is remembered, not re-probed",
     len(g.calls) - before, 1)

listing = FakeGnome({
    "org.gnome.Shell.Extensions.Windows.List":
        '(\'[{"wm_class": "gedit", "title": "notes", "focus": true}]\',)'})
c.eq("the other extension works too", listing.poll_once(), ("gedit", "notes"))

c.eq("with no extension there is nothing to read",
     FakeGnome({}).poll_once(), ("", ""))

# -- choosing one -------------------------------------------------------------
real_desktop, real_session = platform_env.desktop, platform_env.session_type
WATCHERS = (window_watcher.KdotoolWatcher, window_watcher.GnomeWatcher,
            window_watcher.XpropWatcher, window_watcher.MacWatcher)
real_available = {cls: cls.available for cls in WATCHERS}
try:
    # Nothing available: dynamic mode must degrade to "never switches" rather
    # than failing, and the setup check has to say so.
    for cls in WATCHERS:
        cls.available = lambda self: False
    c.eq("with nothing available the watcher is a no-op",
         window_watcher.get_watcher().name, "none")
    c.eq("which polls nothing rather than raising",
         window_watcher.get_watcher().poll_once(), ("", ""))

    platform_env.desktop = lambda: platform_env.GNOME
    check = setup_check.check_window_watcher()
    c.eq("GNOME is told an extension is the only way", check["ok"], False)
    c.eq("and which ones", "extensions.gnome.org" in check["fix"], True)
    c.eq("but it is not called a blocker", check["optional"], True)

    platform_env.desktop = lambda: platform_env.KDE
    c.eq("KDE is told to install kdotool",
         "kdotool" in setup_check.check_window_watcher()["fix"], True)

    platform_env.desktop = lambda: platform_env.OTHER_DE
    platform_env.session_type = lambda: platform_env.X11
    c.eq("a plain X11 desktop is told about xprop",
         "xprop" in setup_check.check_window_watcher()["detail"], True)

    platform_env.session_type = lambda: platform_env.NO_SESSION
    check = setup_check.check_window_watcher()
    c.eq("and an unknown one is told plainly that it cannot",
         "will not switch by themselves" in check["detail"], True)
    c.eq("with nothing to run, because there is nothing", check["fix"], "")
finally:
    platform_env.desktop, platform_env.session_type = real_desktop, real_session
    for cls, fn in real_available.items():
        cls.available = fn

sys.exit(c.done())
