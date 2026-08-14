"""The macOS adapters, exercised on Linux.

None of this has run on a Mac: there is not one here. What can be checked
without one is the part that is actually easy to get wrong, which is the
mapping from this app's vocabulary to AppleScript's, and the platform gates
that decide when the mac adapters are chosen at all. The osascript calls
themselves are stubbed.
"""
import os
import sys
import tempfile

from _harness import Checks

tmp = tempfile.mkdtemp()
os.environ["LOUPEDECKAPP_CONFIG_DIR"] = os.path.join(tmp, "config")

import input_backend                                             # noqa: E402
import platform_env                                              # noqa: E402
import setup_check                                               # noqa: E402
import window_watcher                                            # noqa: E402

c = Checks()

mac = input_backend.MacBackend()

# -- combo translation -------------------------------------------------------
cases = [
    ("ctrl+c", 'tell application "System Events" to keystroke "c" using {control down}'),
    ("cmd+s", 'tell application "System Events" to keystroke "s" using {command down}'),
    # Linux profiles say super; on a Mac that key is command.
    ("super+v", 'tell application "System Events" to keystroke "v" using {command down}'),
    ("alt+x", 'tell application "System Events" to keystroke "x" using {option down}'),
    ("c", 'tell application "System Events" to keystroke "c"'),
    ("return", 'tell application "System Events" to key code 36'),
    ("escape", 'tell application "System Events" to key code 53'),
    ("f5", 'tell application "System Events" to key code 96'),
    ("ctrl+shift+f12",
     'tell application "System Events" to key code 111 using {control down, shift down}'),
]
for combo, want in cases:
    c.eq("%-16s translates" % combo, mac._keystroke_script(combo), want)

c.eq("a lone modifier is not a keystroke", mac._keystroke_script("ctrl"), None)
c.eq("nor is an empty combo", mac._keystroke_script(""), None)
c.eq("an unknown multi-character key is refused, not guessed",
     mac._keystroke_script("ctrl+nonsense"), None)
c.eq("a repeated modifier is only sent once",
     mac._keystroke_script("ctrl+control+c"),
     'tell application "System Events" to keystroke "c" using {control down}')

# -- what actually gets run --------------------------------------------------
ran = []
mac._run = lambda script: ran.append(script)

mac.send_hotkey("cmd+c", repeat=3)
c.eq("a repeat sends the combo that many times", len(ran), 3)
c.eq("and sends the right one", ran[0].endswith("using {command down}"), True)

ran.clear()
mac.send_hotkey("ctrl+nonsense")
c.eq("an unmappable combo runs nothing rather than something wrong", ran, [])

ran.clear()
mac.type_text('say "hi"')
c.eq("typed text is escaped for AppleScript's string syntax",
     ran[0], 'tell application "System Events" to keystroke "say \\"hi\\""')

ran.clear()
mac.scroll("down", 2)
c.eq("scroll falls back to arrow keys", len(ran), 2)
c.eq("in the right direction", ran[0], 'tell application "System Events" to key code 125')
ran.clear()
mac.scroll("sideways")
c.eq("an unknown direction does nothing", ran, [])

# -- health ------------------------------------------------------------------
# There is no osascript on Linux, and health() checks for it first; the branch
# under test is what it says once the binary is there.
mac.bin = "/usr/bin/osascript"
mac.last_error = ""
c.eq("with no failures it reports itself usable", mac.health()[0], True)
mac.last_error = "execution error: not allowed to send keystrokes (1002)"
ok, detail = mac.health()
c.eq("a permission failure is not reported as usable", ok, False)
c.eq("and names Accessibility, because it looks like nothing happening",
     "Accessibility" in detail, True)
mac.last_error = "something else went wrong"
c.eq("any other failure is passed through", "something else" in mac.health()[1], True)

# -- platform gates ----------------------------------------------------------
real_os = platform_env.os_name
try:
    c.eq("the mac backend refuses to run on Linux", mac.available(), False)
    c.eq("and so does the mac watcher", window_watcher.MacWatcher().available(), False)

    platform_env.os_name = lambda: platform_env.MACOS
    c.eq("macOS reports no X11 or Wayland session",
         platform_env.session_type(), platform_env.NO_SESSION)
    c.eq("which is why the backend order for that case tries mac first",
         input_backend._ORDER[platform_env.NO_SESSION][0], input_backend.MacBackend)

    # Both mac adapters shell out to osascript, so on a machine without it they
    # have to decline rather than fail at the first keystroke.
    real_which = input_backend.shutil.which
    input_backend.shutil.which = lambda name: None
    try:
        c.eq("no osascript means the backend is unavailable",
             input_backend.MacBackend().available(), False)
        c.eq("and says why", input_backend.MacBackend().health()[1],
             "osascript not found (is this macOS?)")
    finally:
        input_backend.shutil.which = real_which

    # Setup advice on macOS is a permission, not a package: there is no command
    # to print, so printing one would be worse than useless.
    input_backend.reset_backend()
    check = setup_check.check_input()
    if not check["ok"]:
        c.eq("macOS input advice points at System Settings",
             "Accessibility" in check["detail"], True)
        c.eq("and offers no command to run, because there is none",
             check["fix"], "")
    perms = setup_check.check_device_permissions()
    c.eq("macOS needs no udev rule", perms["ok"], True)
    c.eq("and nothing to run for it", perms["fix"], "")
    media = setup_check.check_media()
    c.eq("macOS is told pyobjc is what media keys and scrolling need",
         "pyobjc" in media["fix"], True)
    c.eq("but the app works without it", media["optional"], True)
finally:
    platform_env.os_name = real_os
    input_backend.reset_backend()

# -- media keys and scrolling ------------------------------------------------
# AppleScript can reach neither: media keys are not in the key code System
# Events addresses, and there is no scroll verb at all. Both go through Quartz
# when pyobjc is installed, so what is checked here is the packing (which is
# where a wrong key comes from) and the fallbacks (which are what happens on a
# Mac without pyobjc).
c.eq("a media key packs into data1 as key and state",
     "0x%x" % mac.media_data1(16, mac.KEY_DOWN), "0x100a00")
c.eq("and the release is the same key, different state",
     "0x%x" % mac.media_data1(16, mac.KEY_UP), "0x100b00")
c.eq("next is its own key", "0x%x" % mac.media_data1(17, mac.KEY_DOWN), "0x110a00")

c.eq("every transport this app offers has a key",
     [a for a in ("play-pause", "next", "previous", "stop")
      if a not in mac.MEDIA_KEYS], [])
c.eq("an unknown action is not invented", mac.media("nonsense"), False)

# No pyobjc here, which is the case a Mac without the extra install is in.
c.eq("with no Quartz the backend says it could not", mac.media("play-pause"), False)
c.eq("and the answer is remembered rather than re-imported",
     mac.quartz(), False)

ran.clear()
mac.scroll("down", 3)
c.eq("scroll without Quartz falls back to arrow keys", len(ran), 3)
c.eq("in the right direction", ran[0], 'tell application "System Events" to key code 125')


class FakeQuartz:
    """Enough of the two pyobjc pieces to see what would be posted."""

    kCGHIDEventTap = 0
    kCGScrollEventUnitLine = 1

    def __init__(self):
        self.posted = []
        self.scrolls = []

    def CGEventCreateScrollWheelEvent(self, source, unit, count, *deltas):
        self.scrolls.append((unit, count, deltas))
        return ("scroll", deltas)

    def CGEventPost(self, tap, event):
        self.posted.append(event)


class FakeNSEvent:
    def __init__(self, quartz):
        self.quartz = quartz
        self.events = []

    def otherEventWithType_location_modifierFlags_timestamp_windowNumber_context_subtype_data1_data2_(
            self, kind, location, flags, ts, window, context, subtype, data1, data2):
        self.events.append((kind, subtype, data1))
        return self

    def CGEvent(self):
        return ("media", self.events[-1])


fake_q = FakeQuartz()
fake_ns = FakeNSEvent(fake_q)
mac._quartz = (fake_q, fake_ns)

c.eq("with Quartz a media key is posted", mac.media("next"), True)
c.eq("as a press and a release", len(fake_ns.events), 2)
c.eq("of the right key, down then up",
     ["0x%x" % e[2] for e in fake_ns.events], ["0x110a00", "0x110b00"])
c.eq("as system-defined events", [e[0] for e in fake_ns.events], [14, 14])
c.eq("and both reached the event tap", len(fake_q.posted), 2)

ran.clear()
mac.scroll("down", 4)
c.eq("with Quartz a scroll is a real scroll, not arrow keys", ran, [])
c.eq("of the magnitude asked for, downward",
     fake_q.scrolls[-1][2], (-4, 0))
mac.scroll("right", 2)
c.eq("and sideways scrolling uses the other axis",
     fake_q.scrolls[-1][2], (0, 2))
ran.clear()
mac.scroll("sideways")
c.eq("an unknown direction still does nothing",
     (fake_q.scrolls[-1][2], ran), ((0, 2), []))
mac._quartz = False

sys.exit(c.done())
