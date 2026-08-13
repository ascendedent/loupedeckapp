"""The setup checks: what a fresh machine still needs.

These decide what the setup dialog says, so what matters is that each one is
honest about severity (a missing udev rule stops the app working; a missing
playerctl loses one feature) and that a check that blows up cannot take the
dialog, or the app's startup, down with it.
"""
import os
import sys
import tempfile

from _harness import Checks

tmp = tempfile.mkdtemp()
os.environ["LOUPEDECKAPP_CONFIG_DIR"] = os.path.join(tmp, "config")

import platform_env                                              # noqa: E402
import setup_check                                               # noqa: E402

c = Checks()

results = setup_check.run()
by_id = {r["id"]: r for r in results}

c.eq("every check reports", sorted(by_id),
     ["device_library", "device_permissions", "input", "media",
      "window_watcher"])
c.eq("every check has the fields the dialog reads",
     all(set(r) == {"id", "title", "ok", "optional", "detail", "fix"}
         for r in results), True)
c.eq("a passing check has nothing to run",
     all(r["fix"] == "" for r in results if r["ok"]), True)
c.eq("a failing required check says what to run",
     all(r["fix"] != "" for r in results
         if not r["ok"] and not r["optional"]), True)

# Severity is the point: getting these backwards would either nag about
# nothing or hide something that stops the app working.
c.eq("the device library is required", by_id["device_library"]["optional"], False)
c.eq("device permissions are required", by_id["device_permissions"]["optional"], False)
c.eq("input is required", by_id["input"]["optional"], False)
c.eq("focused-app detection is optional", by_id["window_watcher"]["optional"], True)
c.eq("media keys are optional", by_id["media"]["optional"], True)

# -- the summary the top bar uses --------------------------------------------
def fake(ok, optional):
    return {"id": "x", "title": "t", "ok": ok, "optional": optional,
            "detail": "", "fix": ""}


all_ok, problems, optional = setup_check.summary([fake(True, False)])
c.eq("all green means nothing to show", (all_ok, problems, optional),
     (True, [], []))

all_ok, problems, optional = setup_check.summary(
    [fake(True, False), fake(False, True)])
c.eq("an optional problem is not all-ok", all_ok, False)
c.eq("but it is not blocking", (len(problems), len(optional)), (0, 1))

all_ok, problems, optional = setup_check.summary([fake(False, False)])
c.eq("a required problem blocks", (len(problems), len(optional)), (1, 0))

# -- a check that raises ------------------------------------------------------
# This runs during startup. A setup hint is the last thing that should be able
# to stop the app opening.
def explode():
    raise RuntimeError("no")


real = setup_check.CHECKS
setup_check.CHECKS = real + (explode,)
try:
    results = setup_check.run()
    c.eq("a check that raises does not take the run down",
         len(results), len(real) + 1)
    bad = results[-1]
    c.eq("it is reported as a failure", bad["ok"], False)
    c.eq("but not as a blocking one", bad["optional"], True)
    c.eq("and says what went wrong", "RuntimeError: no" in bad["detail"], True)
finally:
    setup_check.CHECKS = real

# -- port scan ---------------------------------------------------------------
ports = setup_check.loupedeck_ports()
c.eq("the port scan returns (path, pid) pairs",
     all(len(p) == 2 and isinstance(p[0], str) for p in ports), True)
c.eq("and finds only Loupedeck vendor devices", setup_check.VENDOR_ID, 0x2EC2)

# On anything but Linux there is no udev to talk about.
real_os = platform_env.os_name
platform_env.os_name = lambda: platform_env.MACOS
try:
    mac = setup_check.check_device_permissions()
    c.eq("permissions are a non-issue off Linux", mac["ok"], True)
    c.eq("and there is nothing to run there", mac["fix"], "")
finally:
    platform_env.os_name = real_os

sys.exit(c.done())
