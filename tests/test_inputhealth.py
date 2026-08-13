"""Input backend health: a backend that cannot inject must say so."""
import os
import subprocess
import sys

from _harness import Checks

import input_backend as ib

c = Checks()

real_which = ib.shutil.which
real_run = ib.subprocess.run
real_exists = ib.os.path.exists


def restore():
    ib.shutil.which = real_which
    ib.subprocess.run = real_run
    ib.os.path.exists = real_exists


try:
    # -- ydotool not installed -------------------------------------------------
    ib.shutil.which = lambda name: None
    ok, detail = ib.YdotoolBackend().health()
    c.eq("missing ydotool is not healthy", ok, False)
    c.eq("and says why", "not installed" in detail, True)

    # -- installed, but the daemon is not running ------------------------------
    ib.shutil.which = lambda name: "/usr/bin/" + name
    ib.os.path.exists = lambda p: False          # no socket anywhere
    env_saved = os.environ.pop("YDOTOOL_SOCKET", None)
    try:
        ok, detail = ib.YdotoolBackend().health()
        c.eq("no socket is not healthy", ok, False)
        c.eq("the message names the daemon", "ydotoold" in detail, True)
        c.eq("and lists where it looked", "/run/" in detail, True)
    finally:
        if env_saved is not None:
            os.environ["YDOTOOL_SOCKET"] = env_saved

    # -- installed and running -------------------------------------------------
    ib.os.path.exists = lambda p: True
    b = ib.YdotoolBackend()
    ok, detail = b.health()
    c.eq("with a socket present it is healthy", ok, True)
    c.eq("and reports which socket", "socket" in detail or "/run" in detail, True)

    # -- a runtime failure is remembered ---------------------------------------
    # The daemon can be running yet refuse the connection. The action layer
    # catches the exception, so without recording it the failure is invisible.
    def failing_run(cmd, **kw):
        raise subprocess.CalledProcessError(
            1, cmd, stderr=b"failed to connect socket: Permission denied\n")

    ib.subprocess.run = failing_run
    try:
        b.send_hotkey("ctrl+c")
        c.eq("the failure still raises to the caller", False, True)
    except subprocess.CalledProcessError:
        c.eq("the failure still raises to the caller", True, True)
    ok, detail = b.health()
    c.eq("a failed injection makes it unhealthy", ok, False)
    c.eq("and surfaces the daemon's own message",
         "Permission denied" in detail, True)

    # -- and cleared by a success ----------------------------------------------
    ib.subprocess.run = lambda cmd, **kw: type("R", (), {"returncode": 0})
    b.send_hotkey("ctrl+c")
    ok, detail = b.health()
    c.eq("a later success clears the error", ok, True)

    # scroll and type report failures too, not just hotkeys
    ib.subprocess.run = failing_run
    for verb, call in (("type_text", lambda: b.type_text("hi")),
                       ("scroll", lambda: b.scroll("up", 2))):
        b.last_error = ""
        try:
            call()
        except subprocess.CalledProcessError:
            pass
        c.eq("%s records a failure too" % verb, b.health()[0], False)

    # -- the null backend explains itself --------------------------------------
    ok, detail = ib.NullBackend().health()
    c.eq("the null backend is not healthy", ok, False)
    c.eq("and suggests what to install",
         "ydotool" in detail and "xdotool" in detail, True)

    # -- module-level accessor -------------------------------------------------
    ib.shutil.which = lambda name: None
    ib.reset_backend()
    ok, name, detail = ib.health()
    c.eq("with nothing installed the app reports the null backend", name, "null")
    c.eq("as unhealthy", ok, False)
finally:
    restore()
    ib.reset_backend()

sys.exit(c.done())
