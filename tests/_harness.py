"""Shared helpers. Kept deliberately tiny: these are checks, not a framework."""
import os
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)


class Checks:
    def __init__(self):
        self.failed = []

    def eq(self, name, got, want):
        ok = got == want
        print("%-58s %s" % (name, "ok" if ok else "FAIL got=%r want=%r" % (got, want)))
        if not ok:
            self.failed.append(name)
        return ok

    def close(self, name, got, want, tol):
        ok = got is not None and abs(got - want) <= tol
        print("%-58s %s" % (name, "ok" if ok else "FAIL got=%r want~%r" % (got, want)))
        if not ok:
            self.failed.append(name)
        return ok

    def done(self):
        print("\n%d checks failed" % len(self.failed))
        for f in self.failed:
            print("  FAILED: %s" % f)
        return 1 if self.failed else 0


def controller(tuning=None, action_factory=None, controls=("enc1L", "enc2L")):
    """A DeviceController with no device attached, wired to fake actions."""
    from DeviceProfile import WS_KEYS
    from device_controller import DeviceController
    dc = DeviceController()
    dc.selected_ws = WS_KEYS[0]
    ws = dc.current_ws()
    if action_factory:
        for ctrl in controls:
            for d in ("l", "r"):
                ws.actions[ctrl + "-" + d] = action_factory(ctrl + "-" + d)
    for ctrl, t in (tuning or {}).items():
        ws.set_tuning(ctrl, t)
    return dc, ws


def settle(dc, timeout=5.0):
    """Wait for the dispatch queue to drain and the last action to finish."""
    end = time.time() + timeout
    while time.time() < end:
        if dc._rot_q.empty():
            time.sleep(0.15)
            if dc._rot_q.empty():
                return
        time.sleep(0.02)
