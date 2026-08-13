"""Coalescing rotate dispatch: batching only under load, cancellation, teardown."""
import sys
import threading
import time

from _harness import Checks, controller, settle

from DeviceProfile import WS_KEYS
from LdConfiguration import LdAction, preset_to_tuning

c = Checks()
calls = []
gate = threading.Event()
gate.set()


def slow(key):
    """Blocks while `gate` is cleared, standing in for a slow subprocess."""
    class A(LdAction):
        def __init__(self):
            LdAction.__init__(self, action_type="hotkey", action="ctrl+c")

        def execute(self, repeat=1):
            gate.wait(5)
            calls.append((key, repeat))
    return A()


def build(tuning=None):
    return controller(tuning, slow, ("enc1L", "enc2L"))


def backlog(dc, control, direction, n):
    """Hold the first action, pile n more behind it, then release."""
    gate.clear()
    dc._enqueue_rotate(control, direction)
    time.sleep(0.3)
    for _ in range(n):
        dc._enqueue_rotate(control, direction)


# -- idle: no artificial batching ---------------------------------------------
del calls[:]
dc, _ = build()
for _ in range(4):
    dc._enqueue_rotate("enc1L", "r")
    time.sleep(0.08)
settle(dc)
c.eq("an idle control dispatches one detent at a time", calls, [("enc1L-r", 1)] * 4)
dc.close()

# -- backlog coalesces ---------------------------------------------------------
del calls[:]
dc, _ = build()
backlog(dc, "enc1L", "r", 9)
gate.set(); settle(dc)
c.eq("a backlog collapses into one batched action", len(calls), 2)
c.eq("the batch carries the whole detent count", calls[-1], ("enc1L-r", 9))
c.eq("no detent is lost", sum(n for _k, n in calls), 10)
dc.close()

# -- cancellation --------------------------------------------------------------
del calls[:]
dc, _ = build()
gate.clear()
dc._enqueue_rotate("enc1L", "r")
time.sleep(0.3)
for _ in range(5):
    dc._enqueue_rotate("enc1L", "r")
for _ in range(5):
    dc._enqueue_rotate("enc1L", "l")
gate.set(); settle(dc)
c.eq("equal opposite turns cancel out", calls, [("enc1L-r", 1)])
dc.close()

del calls[:]
dc, _ = build()
gate.clear()
dc._enqueue_rotate("enc1L", "r")
time.sleep(0.3)
for _ in range(2):
    dc._enqueue_rotate("enc1L", "r")
for _ in range(5):
    dc._enqueue_rotate("enc1L", "l")
gate.set(); settle(dc)
c.eq("the net direction wins", calls[-1], ("enc1L-l", 3))
dc.close()

# -- controls do not merge -----------------------------------------------------
del calls[:]
dc, _ = build()
gate.clear()
dc._enqueue_rotate("enc1L", "r")
time.sleep(0.3)
for _ in range(3):
    dc._enqueue_rotate("enc1L", "r")
for _ in range(4):
    dc._enqueue_rotate("enc2L", "l")
gate.set(); settle(dc)
c.eq("each control gets its own batch",
     sorted(x for x in calls if x[1] > 1), [("enc1L-r", 3), ("enc2L-l", 4)])
dc.close()

# -- tuning over a batch -------------------------------------------------------
del calls[:]
dc, _ = build({"enc1L": preset_to_tuning("slow3")})
backlog(dc, "enc1L", "r", 8)
gate.set(); settle(dc)
c.eq("slow3 over 9 detents yields 3 steps", sum(n for _k, n in calls), 3)
dc.close()

del calls[:]
dc, _ = build({"enc1L": preset_to_tuning("fast3")})
backlog(dc, "enc1L", "r", 4)
gate.set(); settle(dc)
# first detent dispatches alone (3), the batch of 4 wants 12 but a coalesced
# backlog is bounded by max_steps (10), which is what keeps drain short
c.eq("a coalesced fast batch is bounded by max_steps",
     sum(n for _k, n in calls), 13)
dc.close()

# -- state resets --------------------------------------------------------------
del calls[:]
dc, _ = build()
gate.clear()
dc._enqueue_rotate("enc1L", "r")
time.sleep(0.3)
for _ in range(6):
    dc._enqueue_rotate("enc1L", "r")
dc.render_workspace = lambda *a, **k: None     # no device to render to
dc.on_workspace_press(WS_KEYS[1])
gate.set(); settle(dc)
c.eq("switching workspace discards the backlog", len(calls), 1)
dc.close()

# -- teardown ------------------------------------------------------------------
dc, _ = build()
dc._enqueue_rotate("enc1L", "r")
settle(dc)
thread = dc._rot_thread
dc.close()
c.eq("close() joins the dispatch thread", thread.is_alive(), False)
c.eq("close() clears the thread handle", dc._rot_thread, None)

# -- a failing action must not kill the dispatcher -----------------------------
del calls[:]
dc, ws = build()


class Boom(LdAction):
    def execute(self, repeat=1):
        raise RuntimeError("boom")


ws.actions["enc1L-r"] = Boom(action_type="hotkey", action="x")
dc._enqueue_rotate("enc1L", "r")
settle(dc)
ws.actions["enc1L-r"] = slow("enc1L-r")
dc._enqueue_rotate("enc1L", "r")
settle(dc)
c.eq("the dispatcher survives a raising action", calls, [("enc1L-r", 1)])
dc.close()

sys.exit(c.done())
