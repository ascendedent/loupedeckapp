"""Schema v5 encoder tuning: normalisation, presets, persistence, dispatch."""
import json
import sys

from _harness import Checks, controller

import LdConfiguration as LC
from LdConfiguration import (LdConfiguration, LdWorkspace, LdAction,
                             DEFAULT_TUNING, SCHEMA_VERSION, normalize_tuning,
                             preset_to_tuning, tuning_to_preset)

c = Checks()

# -- normalisation ------------------------------------------------------------
c.eq("schema version is 5", SCHEMA_VERSION, 5)
c.eq("DEFAULT_TUNING is what normalisation produces",
     normalize_tuning({}), DEFAULT_TUNING)
c.eq("None normalises to the default", normalize_tuning(None), DEFAULT_TUNING)
c.eq("zero clamps to 1", normalize_tuning({"detents_per_step": 0})["detents_per_step"], 1)
c.eq("negatives clamp to 1", normalize_tuning({"steps_per_detent": -5})["steps_per_detent"], 1)
c.eq("garbage falls back", normalize_tuning({"detents_per_step": "x"})["detents_per_step"], 1)
c.eq("a partial dict is filled out",
     normalize_tuning({"invert": True}), dict(DEFAULT_TUNING, invert=True))

# -- presets ------------------------------------------------------------------
c.eq("fast3", preset_to_tuning("fast3"), dict(DEFAULT_TUNING, steps_per_detent=3))
c.eq("slow2 keeps invert", preset_to_tuning("slow2", invert=True),
     dict(DEFAULT_TUNING, invert=True, detents_per_step=2))
c.eq("round-trips", tuning_to_preset(preset_to_tuning("slow3")), "slow3")
c.eq("default is the Original preset", tuning_to_preset(DEFAULT_TUNING), "original")
c.eq("an uncovered combination has no preset",
     tuning_to_preset({"detents_per_step": 2, "steps_per_detent": 2}), None)

# -- storage ------------------------------------------------------------------
ws = LdWorkspace()
c.eq("a fresh workspace is at defaults", ws.tuning_for("enc1L"), DEFAULT_TUNING)
ws.set_tuning("enc1L", preset_to_tuning("fast2", invert=True))
c.eq("set_tuning stores", ws.tuning_for("enc1L"),
     dict(DEFAULT_TUNING, invert=True, steps_per_detent=2))
ws.set_tuning("enc2L", DEFAULT_TUNING)
c.eq("a pure-default entry is dropped", "enc2L" in ws.tuning, False)

cfg = LdConfiguration(profile="tuningtest")
cfg.workspaces[0].set_tuning("enc1L", preset_to_tuning("slow3", invert=True))
cfg.workspaces[0].set_tuning(LC.DIAL_KEY, preset_to_tuning("fast3"))
blob = json.loads(json.dumps(cfg.to_JSON()))
c.eq("to_JSON records the schema version", blob["schema_version"], 5)
cfg2 = LdConfiguration(); cfg2.from_JSON(blob)
c.eq("tuning survives a round-trip", cfg2.workspaces[0].tuning_for("enc1L"),
     dict(DEFAULT_TUNING, invert=True, detents_per_step=3))
c.eq("the dial is stored like any other control",
     cfg2.workspaces[0].tuning_for(LC.DIAL_KEY),
     dict(DEFAULT_TUNING, steps_per_detent=3))

legacy = json.loads(json.dumps(cfg.to_JSON()))
for w in legacy["workspaces"].values():
    w.pop("tuning", None)
legacy["schema_version"] = 4
cfg3 = LdConfiguration(); cfg3.from_JSON(legacy)
c.eq("a v4 profile loads at 1:1", cfg3.workspaces[0].tuning_for("enc1L"), DEFAULT_TUNING)

mangled = json.loads(json.dumps(cfg.to_JSON()))
mangled["workspaces"]["circle"]["tuning"]["enc1L"] = {"invert": True}
cfg4 = LdConfiguration(); cfg4.from_JSON(mangled)
c.eq("a partial stored entry is normalised on load",
     cfg4.workspaces[0].tuning_for("enc1L"), dict(DEFAULT_TUNING, invert=True))

# -- dispatch -----------------------------------------------------------------
calls = []


def fake_action(key):
    class A(LdAction):
        def __init__(self):
            LdAction.__init__(self, action_type="hotkey", action="ctrl+c")

        def execute(self, repeat=1):
            calls.append((key, repeat))
    return A()


def turn(dc, control, direction, n=1):
    for _ in range(n):
        dc.on_rotate(control, direction)


del calls[:]
dc, _ = controller(action_factory=fake_action, controls=("enc1L", LC.DIAL_KEY))
turn(dc, "enc1L", "r", 4)
c.eq("default: one action per detent", calls, [("enc1L-r", 1)] * 4)
dc.close()

del calls[:]
dc, _ = controller({"enc1L": preset_to_tuning("original", invert=True)},
                   fake_action, ("enc1L",))
turn(dc, "enc1L", "r", 2); turn(dc, "enc1L", "l", 1)
c.eq("invert swaps both directions", calls,
     [("enc1L-l", 1), ("enc1L-l", 1), ("enc1L-r", 1)])
dc.close()

del calls[:]
dc, _ = controller({"enc1L": preset_to_tuning("slow3")}, fake_action, ("enc1L",))
turn(dc, "enc1L", "r", 8)
c.eq("slow3: 8 detents give 2 actions", calls, [("enc1L-r", 1)] * 2)
dc.close()

del calls[:]
dc, _ = controller({"enc1L": preset_to_tuning("slow3")}, fake_action, ("enc1L",))
turn(dc, "enc1L", "r", 2); turn(dc, "enc1L", "l", 3)
c.eq("reversing resets the bank rather than spending it", calls, [("enc1L-l", 1)])
dc.close()

del calls[:]
dc, _ = controller({"enc1L": preset_to_tuning("fast3")}, fake_action, ("enc1L",))
turn(dc, "enc1L", "r", 2)
c.eq("fast3 carries a repeat count", calls, [("enc1L-r", 3), ("enc1L-r", 3)])
dc.close()

del calls[:]
dc, _ = controller({"enc1L": preset_to_tuning("slow3")}, fake_action,
                   ("enc1L", LC.DIAL_KEY))
turn(dc, LC.DIAL_KEY, "r", 2)
c.eq("tuning is per control: the dial is unaffected", calls,
     [(LC.DIAL_KEY + "-r", 1)] * 2)
dc.close()

# -- repeatability by action type ---------------------------------------------
sent = []


class FakeBackend:
    @staticmethod
    def send_hotkey(combo, repeat=1): sent.append(("hotkey", combo, repeat))
    @staticmethod
    def type_text(text): sent.append(("text", text, 1))
    @staticmethod
    def scroll(direction, amount=1): sent.append(("scroll", direction, amount))
    @staticmethod
    def launch_app(cmd): sent.append(("launch", cmd, 1))
    @staticmethod
    def media(action): sent.append(("media", action, 1))


real = LC.input_backend
LC.input_backend = FakeBackend
try:
    del sent[:]; LdAction(action_type="hotkey", action="ctrl+c").execute(repeat=3)
    c.eq("hotkey passes repeat through", sent, [("hotkey", "ctrl+c", 3)])
    del sent[:]; LdAction(action_type="text", action="hi").execute(repeat=3)
    c.eq("text repeats", len(sent), 3)
    del sent[:]; LdAction(action_type="scroll", action="down").execute(repeat=5)
    c.eq("scroll takes magnitude in one call", sent, [("scroll", "down", 5)])
    del sent[:]; LdAction(action_type="launch", action="xterm").execute(repeat=5)
    c.eq("launch clamps to 1", sent, [("launch", "xterm", 1)])
    del sent[:]; LdAction(action_type="media", action="next").execute(repeat=5)
    c.eq("media clamps to 1", sent, [("media", "next", 1)])
    del sent[:]; LdAction(action_type="hotkey", action="ctrl+c").execute()
    c.eq("execute() defaults to repeat 1", sent, [("hotkey", "ctrl+c", 1)])
finally:
    LC.input_backend = real

# -- ydotool argument shape (no injection) ------------------------------------
import input_backend as ib

yb = ib.YdotoolBackend(); yb.bin = "/usr/bin/ydotool"
rec = {}
orig_run = ib.subprocess.run
ib.subprocess.run = lambda cmd, **kw: rec.update(cmd=cmd) or type("R", (), {"returncode": 0})
try:
    yb.send_hotkey("ctrl+shift+c", repeat=1)
    c.eq("a single combo is unchanged", rec["cmd"][4:],
         ["29:1", "42:1", "46:1", "46:0", "42:0", "29:0"])
    c.eq("a single press uses no delay", rec["cmd"][2:4], ["-d", "0"])
    yb.send_hotkey("ctrl+shift+c", repeat=3)
    c.eq("a repeat holds modifiers once and repeats the key", rec["cmd"][4:],
         ["29:1", "42:1", "46:1", "46:0", "46:1", "46:0", "46:1", "46:0",
          "42:0", "29:0"])
    c.eq("a repeat is spaced so the receiver sees separate presses",
         rec["cmd"][2:4], ["-d", str(yb.repeat_delay_ms)])
    c.eq("that spacing is non-zero", yb.repeat_delay_ms > 0, True)
    yb.send_hotkey("volumeup", repeat=2)
    c.eq("a modifier-less combo repeats correctly", rec["cmd"][4:],
         ["115:1", "115:0", "115:1", "115:0"])
    for d, want in (("up", ["0", "3"]), ("down", ["0", "-3"]),
                    ("left", ["-3", "0"]), ("right", ["3", "0"])):
        yb.scroll(d, amount=3)
        c.eq("scroll %s maps to a wheel vector" % d,
             [rec["cmd"][4], rec["cmd"][6]], want)
    rec.clear(); yb.scroll("sideways", amount=3)
    c.eq("an unknown scroll direction does nothing", rec.get("cmd"), None)
finally:
    ib.subprocess.run = orig_run

sys.exit(c.done())
