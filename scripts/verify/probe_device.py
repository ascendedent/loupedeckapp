"""Report what device is attached and what this app makes of it.

Reads only: it enumerates, asks the device for its identity, and prints what
`DeviceProfile` decides from that. Nothing is drawn, nothing is bound, no input
is injected.

    .venv/bin/python scripts/verify/probe_device.py

Paste the whole output into a report (see docs/LIVE-TESTING.md).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))

import device_lib                                                 # noqa: E402
from DeviceProfile import DeviceProfile, pid_for_path             # noqa: E402


def usb_ports():
    try:
        import serial.tools.list_ports
    except ImportError:
        print("pyserial is not installed; cannot list USB ports")
        return []
    return list(serial.tools.list_ports.comports())


def main():
    print("== USB serial ports ==")
    ports = usb_ports()
    usb = [p for p in ports if p.vid]
    for p in usb:
        mark = "  <- Loupedeck vendor" if p.vid == 0x2EC2 else ""
        print("  %-14s %04x:%04x  %s%s"
              % (p.device, p.vid, p.pid or 0, p.description, mark))
    if not usb:
        print("  (none: no USB serial device is attached)")
    hidden = len(ports) - len(usb)
    if hidden:
        print("  (%d built-in serial ports not shown)" % hidden)

    if not device_lib.available():
        print("\n%s" % device_lib.health()[1])
        return 1

    print("\n== Enumeration ==")
    devs = device_lib.DeviceManager().enumerate()
    print("  devices found: %d" % len(devs))
    if not devs:
        print("\nNothing enumerated. If a port above shows vendor 2ec2, it is one")
        print("of two things: the app (or another copy of this script) already has")
        print("the port open, or this user cannot open it. Close the app and try")
        print("again; if it still fails, see the Setup dialog or")
        print("packaging/99-loupedeck.rules.")
        return 1

    for d in devs:
        print("\n== Device ==")
        for attr in ("DECK_TYPE", "path", "serial", "version"):
            print("  %-12s %s" % (attr, getattr(d, attr, "(n/a)")))
        try:
            print("  is_loupedeck %s" % d.is_loupedeck())
        except Exception as e:
            print("  is_loupedeck raised %s: %s" % (type(e).__name__, e))
        try:
            print("  get_info     %s" % d.get_info())
        except Exception as e:
            print("  get_info raised %s: %s" % (type(e).__name__, e))

        pid = pid_for_path(getattr(d, "path", None))
        print("  USB PID      %s" % (("0x%04x" % pid) if pid else "unknown"))

        profile, _ = DeviceProfile.detect(d)
        print("\n== What this app decides ==")
        print("  model            %s" % profile.model)
        print("  %s" % profile.describe())
        print("  grid             %d x %d  (%s ... %s)" % (
            profile.columns, profile.rows,
            profile.touch_keys[0], profile.touch_keys[-1]))
        print("  encoders left    %s" % (profile.encoders_left or "(none)"))
        print("  encoders right   %s" % (profile.encoders_right or "(none)"))
        print("  side displays    %s" % (
            "%s | %s" % (profile.side_cell_keys("L"), profile.side_cell_keys("R"))
            if profile.has_side_displays else "(none)"))
        print("  round buttons    %s" % profile.visible_workspace_keys)
        print("  wheel / dial     %s / %s" % (profile.has_wheel, profile.has_dial))
        print("  extra buttons    %s" % (profile.extra_buttons or "(none)"))

        print("\n== The library's own view ==")
        mod = device_lib.module
        print("  BUTTONS   %s" % sorted(mod.BUTTONS.items()))
        print("  DISPLAYS  %s" % {k: dict(v) for k, v in mod.DISPLAYS.items()})

        try:
            d.stop()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
