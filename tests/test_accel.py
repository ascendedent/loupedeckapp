"""Interval-based acceleration: curve shape, speed timing, backlog cap."""
import sys
import time

from _harness import Checks, controller, settle

from LdConfiguration import (LdAction, DEFAULT_TUNING, accel_multiplier,
                             accel_steps, normalize_tuning, preset_to_tuning)

c = Checks()

LIN = normalize_tuning({})
ACC = normalize_tuning({"curve": "accel"})     # from 40ms, full 8ms, max 10

# -- shape ---------------------------------------------------------------------
c.eq("linear never accelerates", accel_multiplier(10, LIN), 1.0)
c.eq("the first detent of a turn has no interval, so no boost",
     accel_multiplier(None, ACC), 1.0)
c.eq("at from_ms the multiplier is still 1", accel_multiplier(40, ACC), 1.0)
c.eq("slower than from_ms is untouched", accel_multiplier(200, ACC), 1.0)
c.eq("at full_ms it reaches max_steps", accel_multiplier(8, ACC), 10.0)
c.eq("faster than full_ms stays capped", accel_multiplier(2, ACC), 10.0)
c.close("the midpoint ramps halfway", accel_multiplier(24, ACC), 5.5, 0.01)

print("\n  interval(ms) -> multiplier")
for ms in (189, 58, 40, 32, 20, 12, 8, 4):
    print("    %4d -> %.2f" % (ms, accel_multiplier(ms, ACC)))
print()

c.eq("linear passes steps through", accel_steps(7, 30, LIN), 7)
c.eq("linear is never capped", accel_steps(25, 10, LIN), 25)
c.eq("deliberate turning is left alone", accel_steps(1, 189, ACC), 1)
c.eq("a full spin hits the cap", accel_steps(1, 6, ACC), 10)
c.eq("the accel result is capped", accel_steps(5, 6, ACC), 10)
c.eq("an unknown interval never accelerates", accel_steps(3, None, ACC), 3)

# -- validation ----------------------------------------------------------------
t = normalize_tuning({"accel_from_ms": 5, "accel_full_ms": 200})
c.eq("an inverted from/full pair falls back",
     (t["accel_from_ms"], t["accel_full_ms"]), (40, 8))
c.eq("a garbage threshold falls back",
     normalize_tuning({"accel_from_ms": "x"})["accel_from_ms"], 40)
c.eq("the Original preset still equals the default",
     normalize_tuning(preset_to_tuning("original")), DEFAULT_TUNING)

# -- speed measurement ---------------------------------------------------------
dc, _ = controller()
c.eq("no interval before any detent", dc.detent_interval_ms("enc1L"), None)
dc._note_detent("enc1L")
c.eq("still none after a single detent", dc.detent_interval_ms("enc1L"), None)
time.sleep(0.05)
dc._note_detent("enc1L")
c.close("an interval appears after two detents", dc.detent_interval_ms("enc1L"), 50, 25)
time.sleep(dc.IDLE_GAP_S + 0.15)
dc._note_detent("enc1L")
c.eq("a pause ends the turn", dc.detent_interval_ms("enc1L"), None)
dc.close()

dc, _ = controller()
for _ in range(6):
    dc._note_detent("enc1L")
    time.sleep(0.03)
fast = dc.detent_interval_ms("enc1L")
time.sleep(0.12)                      # one laggy click, still within IDLE_GAP_S
dc._note_detent("enc1L")
after = dc.detent_interval_ms("enc1L")
c.eq("smoothing damps a single slow click", after < 120, True)
print("    spin=%.0fms, after one 120ms gap=%.0fms" % (fast, after))
dc.close()

dc, _ = controller()
for _ in range(4):
    dc._note_detent("enc1L")
    time.sleep(0.03)
c.eq("speed is tracked per control", dc.detent_interval_ms("enc2R"), None)
dc.close()

# -- end to end ----------------------------------------------------------------
calls = []


def rec(key):
    class A(LdAction):
        def __init__(self):
            LdAction.__init__(self, action_type="hotkey", action="ctrl+c")

        def execute(self, repeat=1):
            calls.append(repeat)
    return A()


del calls[:]
dc, _ = controller({"enc1L": dict(preset_to_tuning("original"), curve="accel")},
                   rec, ("enc1L",))
for _ in range(8):                    # ~8ms apart: a measured full spin
    dc._enqueue_rotate("enc1L", "r")
    time.sleep(0.008)
settle(dc)
c.eq("a fast spin multiplies", max(calls) > 1, True)
print("    repeats issued: %s" % calls)
dc.close()

del calls[:]
dc, _ = controller({"enc1L": dict(preset_to_tuning("original"), curve="accel")},
                   rec, ("enc1L",))
for _ in range(4):                    # 300ms apart: deliberate turning
    dc._enqueue_rotate("enc1L", "r")
    time.sleep(0.3)
settle(dc)
c.eq("deliberate turning is untouched", calls, [1, 1, 1, 1])
dc.close()

del calls[:]
dc, _ = controller({"enc1L": preset_to_tuning("original")}, rec, ("enc1L",))
for _ in range(6):
    dc._enqueue_rotate("enc1L", "r")
    time.sleep(0.03)
settle(dc)
c.eq("linear ignores speed entirely", set(calls), {1})
dc.close()

# -- backlog cap ---------------------------------------------------------------
del calls[:]
dc, _ = controller({"enc1L": dict(preset_to_tuning("fast3"), max_steps=2)},
                   rec, ("enc1L",))
dc.on_rotate("enc1L", "r", count=1)
c.eq("a single detent keeps full intent despite a low cap", calls[-1], 3)
dc.on_rotate("enc1L", "r", count=20)
c.eq("a coalesced backlog is bounded", calls[-1], 2)
dc.close()

sys.exit(c.done())
