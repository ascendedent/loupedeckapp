"""Connection supervision: connect when the device appears, notice it leave."""
import os
import shutil
import sys
import tempfile
import threading
import time

from _harness import Checks

tmp = tempfile.mkdtemp(prefix="ldconn-")
os.environ["LOUPEDECKAPP_CONFIG_DIR"] = os.path.join(tmp, "config")

import device_controller                            # noqa: E402
from DeviceProfile import DeviceProfile             # noqa: E402

c = Checks()

# A stand-in device: a real serial node is represented by a file on disk, so
# "unplugging" is deleting it, which is exactly the signal the supervisor uses.
node = os.path.join(tmp, "ttyFAKE")


class FakeThread:
    def __init__(self, alive=True):
        self._alive = alive

    def is_alive(self):
        return self._alive


class FakeDevice:
    DECK_TYPE = "LoupedeckLive"

    def __init__(self):
        self.path = node
        self.reading_thread = FakeThread()
        self.stopped = False
        self.reset_count = 0
        self.callback = None

    def set_callback(self, cb):
        self.callback = cb

    def reset(self):
        self.reset_count += 1

    def set_button_color(self, *a):
        pass

    def set_brightness(self, *a):
        pass

    def draw_image(self, *a, **k):
        pass

    def stop(self):
        self.stopped = True


present = {"device": None}


class FakeManager:
    def enumerate(self):
        d = present["device"]
        return [d] if d is not None else []


device_controller.DeviceManager = FakeManager
real_detect = DeviceProfile.detect
DeviceProfile.detect = staticmethod(
    lambda dev: (DeviceProfile.for_model("LoupedeckLive"), 0x0004))

dc = device_controller.DeviceController()
dc.WATCH_INTERVAL_S = 0.1          # keep the test quick
dc.render_workspace = lambda *a, **k: None


def wait_for(fn, timeout=4.0):
    end = time.time() + timeout
    while time.time() < end:
        if fn():
            return True
        time.sleep(0.05)
    return False


try:
    # -- nothing plugged in --------------------------------------------------
    dc.start()
    time.sleep(0.3)
    c.eq("with no device it stays disconnected and keeps looking",
         dc.connected, False)
    c.eq("the supervisor is running", dc._watch_thread.is_alive(), True)

    # -- device appears ------------------------------------------------------
    open(node, "w").close()
    dev = FakeDevice()
    present["device"] = dev
    c.eq("it connects on its own once the device appears",
         wait_for(lambda: dc.connected), True)
    c.eq("the callback was installed", dev.callback is not None, True)

    # -- device goes away ----------------------------------------------------
    os.remove(node)                 # the serial node vanishing is the real signal
    c.eq("it notices the device leaving",
         wait_for(lambda: not dc.connected), True)
    c.eq("the old device was stopped", dev.stopped, True)
    c.eq("and released", dc.device, None)

    # -- and comes back ------------------------------------------------------
    open(node, "w").close()
    dev2 = FakeDevice()
    present["device"] = dev2
    c.eq("it reconnects by itself", wait_for(lambda: dc.connected), True)
    c.eq("using the new device object", dc.device is dev2, True)
    c.eq("which was initialised", dev2.reset_count > 0, True)

    # -- a dead reader thread counts as gone too -----------------------------
    dev2.reading_thread = FakeThread(alive=False)
    c.eq("a dead reader thread is treated as a disconnect",
         wait_for(lambda: not dc.connected), True)

    # -- the workspace is restored, not reset to the first --------------------
    present["device"] = None
    time.sleep(0.2)
    from DeviceProfile import WS_KEYS
    dc.selected_ws = WS_KEYS[2]
    dev3 = FakeDevice()
    present["device"] = dev3
    c.eq("reconnect restores the workspace you were on",
         wait_for(lambda: dc.connected and dc.selected_ws == WS_KEYS[2]), True)

    # -- teardown ------------------------------------------------------------
    watcher = dc._watch_thread
    dc.close()
    c.eq("close() stops the supervisor", watcher.is_alive(), False)
    c.eq("and clears the handle", dc._watch_thread, None)
finally:
    DeviceProfile.detect = real_detect
    try:
        dc.close()
    except Exception:
        pass
    shutil.rmtree(tmp, ignore_errors=True)

sys.exit(c.done())
