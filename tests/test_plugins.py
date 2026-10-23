"""Loupedeck plugins: packages, the stored value, and a plugin run for real.

The run uses a stand-in plugin that speaks the same protocol as Logitech's
Node.js SDK (read out of its bundled source), written against Node's built-in
WebSocket so the suite needs nothing installed beyond node itself. Without
node, those checks are skipped and the rest still run.
"""
import json
import os
import shutil
import tempfile
import time
import zipfile

from _harness import Checks

tmp = tempfile.mkdtemp()
os.environ["LOUPEDECKAPP_CONFIG_DIR"] = os.path.join(tmp, "config")
# A running host listens for loupedeck: links on a socket under here; the
# app's own must not be disturbed, nor the desktop's handler settings.
os.environ["XDG_RUNTIME_DIR"] = tmp
os.environ["XDG_DATA_HOME"] = os.path.join(tmp, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(tmp, "xdgconfig")

import plugin_host as ph

c = Checks()

META = """type: plugin4
name: {name}
version: 1.2.0
displayName: "Fake Plugin"   # quoted, with a comment
description: test
pluginType: remote
pluginRuntime: {runtime}
entryPoint: index.mjs

pluginCapabilities:
  - Something
"""

# Answers like the SDK: InitConnection first, then GetActionList and the two
# execute requests. Each execute is written to OUT so the test can see it.
# Like the SDK, GetActionText answers with the action's displayName as it is
# now, and pressing "ping" changes it, which is how a real plugin would show a
# count. "knob" answers GetActionImage with a PNG (the SDK answers null; this
# is the case the host is ready for), and "crash" exits the process.
PLUGIN_JS = r"""
import { appendFileSync } from "node:fs";
const OUT = process.env.FAKE_PLUGIN_OUT;
const NAME = process.env.LPS_PLUGIN_NAME;
let id = 19;
const ws = new WebSocket(process.env.LPS_SERVER_URL);
const send = (m) => ws.send(JSON.stringify(m));
const reply = (req, data) => send({ id: req.id, name: req.name,
  messageType: "Response", data, failed: false, errorCode: 0, errorMessage: "" });
ws.onopen = () => send({ id: ++id, name: "InitConnection", messageType: "Request",
  parameters: { pluginName: NAME, sessionToken: process.env.LPS_SESSION_TOKEN } });
let pings = 0;
const text = { ping: "Ping", knob: "Knob", crash: "Crash" };
ws.onmessage = (ev) => {
  const m = JSON.parse(ev.data);
  if (m.name === "GetActionList") reply(m, {
    commands: [{ name: "ping", actionType: 1, displayName: "Ping",
                 description: "", groupName: "Fake" },
               { name: "crash", actionType: 1, displayName: "Crash",
                 description: "", groupName: "Fake" }],
    adjustments: [{ name: "knob", actionType: 0, displayName: "Knob",
                    description: "", groupName: "Fake", resetCommandName: "knob_RESET" }] });
  else if (m.name === "GetActionText") reply(m, { text: text[m.parameters.actionName] });
  else if (m.name === "GetActionImage")
    reply(m, m.parameters.actionName === "knob" ? "data:image/png;base64,PNG_B64" : null);
  else if (m.name === "ExecuteCommand") {
    appendFileSync(OUT, JSON.stringify(["cmd", m.parameters.actionName]) + "\n");
    if (m.parameters.actionName === "crash") process.exit(3);
    if (m.parameters.actionName === "ping") text.ping = "Ping " + (++pings);
    reply(m, true);
  } else if (m.name === "ExecuteAdjustment") {
    appendFileSync(OUT, JSON.stringify(["adj", m.parameters.actionName,
      parseInt(m.parameters.clicks, 10)]) + "\n");
    reply(m, true);
  } else if (m.name === "StopPlugin") ws.close();
};
"""


def _png_b64():
    import base64
    import io
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGBA", (8, 8), (255, 0, 0, 255)).save(buf, "PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


ICON_SVG = ('<svg xmlns="http://www.w3.org/2000/svg" width="80" height="80">'
            '<rect width="80" height="80" fill="#00ff00"/></svg>')


def make_package(path, name="FakePlugin", runtime="nodejs", entry=True, extra=None,
                 code=None):
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(ph.METADATA, META.format(name=name, runtime=runtime))
        if entry:
            zf.writestr("index.mjs", code or PLUGIN_JS.replace("PNG_B64", _png_b64()))
            zf.writestr("actionicons/ping.svg", ICON_SVG)
        for member, data in (extra or {}).items():
            zf.writestr(member, data)
    return path


def wait_for(pred, timeout=10.0):
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.05)
    return False


# -- metadata ------------------------------------------------------------------
meta = ph.parse_metadata(META.format(name="X", runtime="nodejs"))
c.eq("flat keys are read", meta["entryPoint"], "index.mjs")
c.eq("quotes and trailing comments are stripped", meta["displayName"], "Fake Plugin")
c.eq("nested lines are skipped, not read as keys", "- Something" in meta, False)

# -- values --------------------------------------------------------------------
c.eq("a command value", ph.make_value("P", "go"), "P/go")
c.eq("an adjustment value carries its direction", ph.make_value("P", "dial", "-"), "P/dial:-")
c.eq("and parses back", ph.parse_value("P/dial:-"), ("P", "dial", "-"))
c.eq("a command parses with no direction", ph.parse_value("P/go"), ("P", "go", ""))
c.eq("a colon that is not a direction stays in the name",
     ph.parse_value("P/a:b"), ("P", "a:b", ""))

# -- packages ------------------------------------------------------------------
pkgs = os.path.join(tmp, "pkgs")
os.makedirs(pkgs)

_, err = ph.inspect_package(make_package(os.path.join(pkgs, "neither.lplug4"),
                                         runtime="", entry=True))
c.eq("a package that is neither Node.js nor .NET is refused",
     "not in the package" in err, True)

_, err = ph.inspect_package(make_package(os.path.join(pkgs, "noentry.lplug4"), entry=False))
c.eq("a package missing its entry point is refused", "not in the package" in err, True)

_, err = ph.inspect_package(make_package(os.path.join(pkgs, "badname.lplug4"),
                                         name="../evil"))
c.eq("a name that would escape the folder is refused",
     "not one that can be installed" in err, True)

with open(os.path.join(pkgs, "junk.lplug4"), "w") as f:
    f.write("not a zip")
_, err = ph.inspect_package(os.path.join(pkgs, "junk.lplug4"))
c.eq("a file that is not a zip is refused", "not a Loupedeck plugin" in err, True)

slip = make_package(os.path.join(pkgs, "slip.lplug4"),
                    extra={"../../outside.txt": "x"})
name, err = ph.install(slip)
c.eq("a member pointing outside the package fails the install", name, "")
c.eq("and writes nothing outside",
     os.path.exists(os.path.join(os.environ["LOUPEDECKAPP_CONFIG_DIR"], "outside.txt")), False)
c.eq("nor leaves a half-installed plugin", [i["name"] for i in ph.installed()], [])

good = make_package(os.path.join(pkgs, "good.lplug4"))
name, err = ph.install(good)
c.eq("a Node.js package installs", (name, err), ("FakePlugin", ""))
c.eq("and is listed with its display name",
     [(i["name"], i["displayName"], i["version"]) for i in ph.installed()],
     [("FakePlugin", "Fake Plugin", "1.2.0")])
name, err = ph.install(good)
c.eq("installing it again replaces it (an update)", (name, err), ("FakePlugin", ""))
c.eq("no staging folders are left behind",
     [d for d in os.listdir(ph.plugins_dir()) if d.startswith(".")], [])

# -- no host -------------------------------------------------------------------
c.eq("with no host, executing does nothing and says so",
     ph.execute("FakePlugin/ping"), False)
c.eq("and the label falls back to the action name",
     ph.label_for("FakePlugin/ping"), "ping")

# -- a real run ----------------------------------------------------------------
node = shutil.which("node")
if not node:
    print("%-58s %s" % ("plugin run (node is not installed)", "skipped"))
else:
    # Restarts are quick here; the real delays would make this a slow test.
    ph.RESTART_DELAYS_S = (0.2, 0.2, 0.2, 0.2, 0.2)
    ph.TEXT_POLL_S = 0.2
    # A Qt application, so SVG icons can be rendered the way the app does.
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtGui import QGuiApplication
        qt_app = QGuiApplication.instance() or QGuiApplication(["plugin-check"])
    except ImportError:
        qt_app = None

    out = os.path.join(tmp, "calls.jsonl")
    os.environ["FAKE_PLUGIN_OUT"] = out
    changes = []
    host = ph.PluginHost(on_change=lambda: changes.append(1))
    ph.set_host(host)
    host.start()

    def running():
        return [s["state"] for s in host.status()] == ["running"]
    c.eq("the plugin starts and connects", wait_for(running), True)
    c.eq("the host was told about it", len(changes) > 0, True)
    c.eq("its actions arrive, an adjustment once per direction",
         [(a[1], a[2]) for a in host.actions()],
         [("Ping", "FakePlugin/ping"), ("Crash", "FakePlugin/crash"),
          ("Knob ◀", "FakePlugin/knob:-"), ("Knob ▶", "FakePlugin/knob:+")])
    c.eq("the label is the plugin's own name for it", ph.label_for("FakePlugin/knob:+"), "Knob")

    # -- icons and images --
    if qt_app is not None:
        c.eq("the package's SVG icon is rendered", host.render_icons(), True)
        icon = ph.image_for("FakePlugin/ping")
        c.eq("and becomes the action's image", icon.endswith("ping.png"), True)
        from PIL import Image
        with Image.open(icon) as im:
            c.eq("rendered at full size, from the SVG",
                 (im.size, im.convert("RGB").getpixel((120, 120))),
                 ((ph.ICON_PX, ph.ICON_PX), (0, 255, 0)))
        c.eq("and not rendered again while it is current", host.render_icons(), False)
    c.eq("an image the plugin supplies is used",
         wait_for(lambda: ph.image_for("FakePlugin/knob:+").endswith(".supplied.png")), True)
    c.eq("an action with neither has none", ph.image_for("FakePlugin/crash"), "")

    from LdConfiguration import LdAction
    LdAction("plugin", "FakePlugin/ping").execute(repeat=5)
    LdAction("plugin", "FakePlugin/knob:-").execute(repeat=3)
    LdAction("plugin", "FakePlugin/knob:+").execute()

    def calls():
        try:
            with open(out) as f:
                return [json.loads(l) for l in f if l.strip()]
        except OSError:
            return []
    wait_for(lambda: len(calls()) >= 3)
    c.eq("a command runs once however fast the knob turned, and adjustments "
         "send signed clicks", calls(),
         [["cmd", "ping"], ["adj", "knob", -3], ["adj", "knob", 1]])

    # -- live text --
    c.eq("text the plugin changes reaches the label",
         wait_for(lambda: ph.label_for("FakePlugin/ping") == "Ping 1"), True)
    c.eq("and the library", any(a[1] == "Ping 1" for a in host.actions()), True)

    # -- the device side: only plugin-bound keys are redrawn --
    from DeviceProfile import WS_KEYS
    from device_controller import DeviceController

    class FakeDevice:
        def __init__(self):
            self.keys = []

        def set_key_image(self, keycode, image):
            self.keys.append((keycode, image.convert("RGB").getpixel((45, 20))))

        def draw_image(self, *a, **k):
            pass

        def reset(self):
            pass

        def set_button_color(self, *a, **k):
            pass

    dc = DeviceController()
    dc.selected_ws = WS_KEYS[0]
    ws = dc.current_ws()
    ws.actions["tb11"] = LdAction("plugin", "FakePlugin/ping")
    ws.actions["tb12"] = LdAction("hotkey", "ctrl+c")
    c.eq("a key bound to a plugin action takes its icon",
         dc.effective_image(ws, "tb11"), ph.image_for("FakePlugin/ping"))
    c.eq("a key with its own image keeps it",
         (ws.images.__setitem__("tb11", "/x.png"), dc.effective_image(ws, "tb11"))[1], "/x.png")
    ws.images["tb11"] = ""
    dc.device = FakeDevice()
    dc.redraw_plugin_controls()
    c.eq("a redraw touches only the plugin's key",
         [k for k, _ in dc.device.keys], [dc.tb_name_to_keycode("tb11")])
    if qt_app is not None:
        c.eq("and draws its icon", dc.device.keys[0][1], (0, 255, 0))
    c.eq("and what is on screen is what gets watched",
         host._watched, {("FakePlugin", "ping")})

    c.eq("an action of a plugin that is not there does nothing",
         host.execute("Nope/ping"), False)

    # -- crashes --
    first = host._plugins["FakePlugin"].proc
    host.execute("FakePlugin/crash")
    c.eq("a plugin that exits on its own is restarted",
         wait_for(lambda: running() and host._plugins["FakePlugin"].proc is not first), True)
    c.eq("and works again", host.execute("FakePlugin/ping"), True)

    host.reload("FakePlugin")
    c.eq("a reload brings it back up", wait_for(running), True)

    # One that dies on every start is given up on rather than restarted forever.
    crashy = make_package(os.path.join(pkgs, "crashy.lplug4"), name="Crashy",
                          code="process.exit(1);")
    ph.install(crashy)
    host.reload("Crashy")
    gave_up = wait_for(lambda: any(s["name"] == "Crashy" and s["state"] == "failed"
                                   for s in host.status()), timeout=20)
    c.eq("a plugin that keeps crashing is left stopped", gave_up, True)
    detail = next(s["detail"] for s in host.status() if s["name"] == "Crashy")
    c.eq("and says so", "left stopped" in detail, True)
    host.remove("Crashy")
    ph.uninstall("Crashy")

    procs = [p.proc for p in host._plugins.values()]
    host.stop()
    c.eq("stopping ends the node process",
         all(p is not None and p.poll() is not None for p in procs), True)
    c.eq("and the plugin reads as stopped",
         [s["state"] for s in host.status()], ["stopped"])
    time.sleep(0.5)
    c.eq("and nothing restarts it", [s["state"] for s in host.status()], ["stopped"])
    ph.set_host(None)

c.eq("uninstall removes it", (ph.uninstall("FakePlugin"), ph.installed()), ("", []))
c.eq("uninstalling it twice says it is not there",
     "no plugin" in ph.uninstall("FakePlugin"), True)

shutil.rmtree(tmp, ignore_errors=True)
raise SystemExit(c.done())
