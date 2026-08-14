"""Record what the device sends when you touch each control.

This is how the identifiers in `DeviceProfile` were confirmed for the CT, and
it is what a Live or Live S report needs (see docs/LIVE-TESTING.md). It prompts
for one group of controls at a time, records every event, and prints a summary
you can paste into an issue.

Safe: it binds nothing and injects nothing. Every event is recorded and thrown
away, so pressing keys here cannot reach your desktop.

    .venv/bin/python scripts/verify/capture_events.py

Close the main app first, or it will already have the serial port open.
"""
import os
import sys
import time
from collections import OrderedDict

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))

import ct_support                                                 # noqa: E402
import device_lib                                                 # noqa: E402
from DeviceProfile import DeviceProfile                           # noqa: E402

SECONDS = 12


class LoggingHandlers(dict):
    """Surfaces headers the library has no handler for.

    The lib silently drops messages whose 2-byte header it does not know, which
    is exactly where an unsupported model's controls disappear. Forcing every
    lookup through __missing__ turns a dropped message into a printed one.
    """

    def __init__(self, wrapped, unknown):
        super().__init__(wrapped)
        self._unknown = unknown

    def __contains__(self, key):
        return True

    def __missing__(self, key):
        def log(buff, _h=key):
            raw = bytes(buff).hex()
            self._unknown.setdefault(_h, []).append(raw)
            print("    UNKNOWN header=0x%04x raw=%s" % (_h, raw), flush=True)
            return buff
        return log


# (title, what to do). Groups a tester can work through without knowing the
# codebase; skip any the device does not have.
STEPS = [
    ("Touch keys",
     "Tap every key on the main screen, left to right, top row first."),
    ("Round buttons",
     "Press each round button below the screen, left to right."),
    ("Encoders: turn",
     "Turn each knob a few clicks one way, then the other. Say which is which "
     "when you report."),
    ("Encoders: press",
     "Press each knob in, in the same order."),
    ("Side screens",
     "Touch the left strip top to bottom, then the right strip. Skip if this "
     "model has none."),
    ("Wheel and dial (CT only)",
     "Touch the round screen, press it, and turn the outer ring. Skip if this "
     "model has none."),
    ("Extra buttons (CT only)",
     "Press the labelled buttons either side of the wheel. Skip if this model "
     "has none."),
]


def summarise(events):
    """Identifier -> what came back with it, in first-seen order."""
    seen = OrderedDict()
    for msg in events:
        ident = msg.get("id") or msg.get("screen") or "(no identifier)"
        entry = seen.setdefault(ident, {"count": 0, "actions": set(),
                                        "keys": set(), "states": set()})
        entry["count"] += 1
        if msg.get("action"):
            entry["actions"].add(str(msg["action"]))
        if msg.get("key") is not None:
            entry["keys"].add(str(msg["key"]))
        state = msg.get("state")
        if state is not None:
            entry["states"].add(str(state)[:24])
    return seen


def main():
    if not device_lib.available():
        print(device_lib.health()[1])
        return 1

    devs = []
    for attempt in range(10):
        devs = device_lib.DeviceManager().enumerate()
        if devs:
            break
        time.sleep(0.5 + attempt / 10.0)
    if not devs:
        print("No device found. Close the main app first: it holds the port.")
        return 1

    device = devs[0]
    profile, pid = DeviceProfile.detect(device)
    print("Device: %s, USB %s -> %s\n" % (
        device.DECK_TYPE, ("0x%04x" % pid) if pid else "?", profile.describe()))

    # The CT patches add the dial, the wheel screen and the extra buttons. On
    # another model they are harmless, and installing them anyway means an
    # unknown control shows up as an event rather than as silence.
    ct_support.install_ct_handlers(device)
    unknown = {}
    device.handlers = LoggingHandlers(device.handlers, unknown)

    captured = []
    recording = [False]

    def on_event(_ld, msg):
        if not recording[0]:
            return
        clean = {k: v for k, v in msg.items() if k != "ts"}
        captured.append(clean)
        print("    %s" % clean, flush=True)

    device.set_callback(on_event)

    all_events = []
    per_step = OrderedDict()
    try:
        for title, instruction in STEPS:
            print("== %s ==" % title)
            print("  %s" % instruction)
            try:
                input("  Press Enter to record for %d seconds (or Ctrl-C to "
                      "stop): " % SECONDS)
            except (EOFError, KeyboardInterrupt):
                print()
                break
            captured.clear()
            recording[0] = True
            time.sleep(SECONDS)
            recording[0] = False
            per_step[title] = list(captured)
            all_events.extend(captured)
            print("  recorded %d events\n" % len(captured))
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        try:
            device.stop()
        except Exception:
            pass

    print("\n" + "=" * 68)
    print("PASTE EVERYTHING BELOW INTO YOUR REPORT")
    print("=" * 68)
    print("device: %s  USB %s  model detected: %s" % (
        device.DECK_TYPE, ("0x%04x" % pid) if pid else "?", profile.model))
    for title, events in per_step.items():
        print("\n-- %s (%d events)" % (title, len(events)))
        for ident, info in summarise(events).items():
            print("   %-12s x%-3d actions=%s keys=%s states=%s" % (
                ident, info["count"],
                sorted(info["actions"]) or "-",
                sorted(info["keys"]) or "-",
                sorted(info["states"]) or "-"))
    if unknown:
        print("\n-- headers the library does not decode")
        for header, raws in unknown.items():
            print("   0x%04x x%d  e.g. %s" % (header, len(raws), raws[0]))
    else:
        print("\n-- no undecoded headers")
    return 0


if __name__ == "__main__":
    sys.exit(main())
