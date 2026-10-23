"""Loupedeck .NET plugins, run for real under Mono through our PluginApi.

tests/dotnet/TestPlugin.cs is compiled against dotnet/bin/PluginApi.dll,
packaged the way the marketplace packages a .NET plugin (a .lplug4 naming the
assembly in pluginFileName and a folder per platform), installed, and run by
plugin_host exactly as the app runs one. Each of its actions exercises one
part of the contract. Skipped where Mono is not installed.
"""
import io
import json
import os
import shutil
import subprocess
import tempfile
import time
import zipfile

from _harness import Checks, REPO

tmp = tempfile.mkdtemp()
os.environ["LOUPEDECKAPP_CONFIG_DIR"] = os.path.join(tmp, "config")
# A running host listens for loupedeck: links on a socket under here; the
# app's own must not be disturbed, nor the desktop's handler settings.
os.environ["XDG_RUNTIME_DIR"] = tmp
os.environ["XDG_DATA_HOME"] = os.path.join(tmp, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(tmp, "xdgconfig")

import plugin_host as ph                                         # noqa: E402

# SVG images are rendered with Qt, as the app does.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtGui import QGuiApplication                         # noqa: E402
qt_app = QGuiApplication.instance() or QGuiApplication(["dotnet-check"])

c = Checks()

if not (shutil.which("mono") and shutil.which("mcs")):
    print("%-58s %s" % (".NET plugins (Mono is not installed)", "skipped"))
    raise SystemExit(c.done())

host, error = ph.dotnet_host()
c.eq("the host builds", error, "")
if error:
    raise SystemExit(c.done())
api = os.path.join(os.path.dirname(host), "PluginApi.dll")

# -- the plugin ------------------------------------------------------------------
from PIL import Image                                             # noqa: E402

icon = os.path.join(tmp, "blue.png")
Image.new("RGBA", (90, 90), (0, 0, 255, 255)).save(icon)
svg = os.path.join(tmp, "icon.svg")
with open(svg, "w") as f:
    f.write('<svg xmlns="http://www.w3.org/2000/svg" width="80" height="80">'
            '<rect width="80" height="80" fill="#ff00ff"/></svg>')
dll = os.path.join(tmp, "TestPlugin.dll")
p = subprocess.run(["mcs", "-nologo", "-target:library", "-out:" + dll, "-r:" + api,
                    "-resource:%s,Loupedeck.TestPlugin.Images.blue.png" % icon,
                    "-resource:%s,Loupedeck.TestPlugin.Images.icon.svg" % svg,
                    os.path.join(REPO, "tests", "dotnet", "TestPlugin.cs")],
                   capture_output=True, text=True)
c.eq("the test plugin compiles against our PluginApi", p.returncode, 0)
if p.returncode:
    print(p.stdout, p.stderr)
    raise SystemExit(c.done())

META = """type: plugin4
name: TestPlugin
displayName: Test Plugin
pluginFileName: TestPlugin.dll
version: 1.0.0
pluginFolderWin: win
pluginFolderMac: mac
supportedDevices:
    - LoupedeckCtFamily
"""
package = os.path.join(tmp, "TestPlugin.lplug4")
with zipfile.ZipFile(package, "w") as zf:
    zf.writestr(ph.METADATA, META)
    zf.write(dll, "mac/TestPlugin.dll")
    zf.write(dll, "win/TestPlugin.dll")

meta, err = ph.inspect_package(package)
c.eq("a .NET package is accepted", err, "")
c.eq("and recognised as .NET", ph.runtime_of(meta), "dotnet")
c.eq("the macOS build is the one run", ph.package_entry(meta, {"mac/TestPlugin.dll", "win/TestPlugin.dll"}),
     "mac/TestPlugin.dll")
no_dll = os.path.join(tmp, "nodll.lplug4")
with zipfile.ZipFile(no_dll, "w") as zf:
    zf.writestr(ph.METADATA, META)
c.eq("one missing its assembly is refused", "not in the package" in ph.inspect_package(no_dll)[1], True)
c.eq("it installs", ph.install(package), ("TestPlugin", ""))
entry = next(i["entry"] for i in ph.installed() if i["name"] == "TestPlugin")
c.eq("it is known to sign in through links", ph.uses_url_callbacks(entry), True)
if shutil.which("xdg-mime"):
    c.eq("loupedeck: links can be registered", ph.register_url_handler(), "")
    desktop = os.path.join(os.environ["XDG_DATA_HOME"], "applications", ph.URL_HANDLER_DESKTOP)
    c.eq("with a handler that runs plugin_host's url command",
         " url %u" in open(desktop).read() and "x-scheme-handler/loupedeck" in open(desktop).read(), True)

def scenario(runtime):
    """The whole run, on one host: "mono" or "core" (.NET 10)."""
    global host_, out
    c.prefix = "[%s] " % runtime
    if ph.installed() == []:
        ph.install(package)
    if os.path.exists(os.path.join(tmp, "calls.txt")):
        os.remove(os.path.join(tmp, "calls.txt"))
    # -- running it ------------------------------------------------------------------
    out = os.path.join(tmp, "calls.txt")
    os.environ["TEST_PLUGIN_OUT"] = out
    ph.TEXT_POLL_S = 0.2
    host_ = ph.PluginHost(mono=None if runtime == "mono" else "")
    if runtime == "core":
        c.eq("the .NET host builds", ph.dotnet_core_host()[1], "")
    ph.set_host(host_)
    host_.start()


    def wait_for(pred, timeout=20.0):
        end = time.time() + timeout
        while time.time() < end:
            if pred():
                return True
            time.sleep(0.05)
        return False


    def status():
        return next((s for s in host_.status() if s["name"] == "TestPlugin"), {})


    def calls():
        try:
            with open(out) as f:
                return [l.strip() for l in f if l.strip()]
        except OSError:
            return []


    c.eq("it starts and connects", wait_for(lambda: status().get("state") == "running"), True)
    proc = host_._plugins["TestPlugin"].proc
    c.eq("on the host asked for", os.path.basename(proc.args[0]) if proc else None,
         "mono" if runtime == "mono" else "dotnet")
    if status().get("state") != "running":
        print(open(ph.log_path("TestPlugin")).read())
        return
    c.eq("Install ran once, before Load", calls()[:2], ["install", "load 1"])
    c.eq("and could use the data folder", os.path.isdir(os.path.join(ph.data_dir("TestPlugin"), "cache")), True)

    actions = {a[2]: (a[1], a[3]) for a in host_.actions()}
    NS = "TestPlugin/Loupedeck.TestPlugin."
    c.eq("a command is offered by its class", actions.get(NS + "CounterCommand"), ("Counter", "command"))
    c.eq("a command with parameters is offered once per parameter",
         (actions.get(NS + "SwitchesCommand|0"), actions.get(NS + "SwitchesCommand|1"),
          NS + "SwitchesCommand" in actions),
         (("Switch 0", "command"), ("Switch 1", "command"), False))
    c.eq("an adjustment, both ways", (actions.get(NS + "VolumeAdjustment:+"), actions.get(NS + "VolumeAdjustment:-")),
         (("Volume ▶", "adjustment"), ("Volume ◀", "adjustment")))
    c.eq("and its reset, as a press", actions.get(NS + "VolumeAdjustment_RESET"), ("Volume reset", "command"))

    from LdConfiguration import LdAction                              # noqa: E402

    LdAction("plugin", NS + "CounterCommand").execute()
    LdAction("plugin", NS + "SwitchesCommand|1").execute()
    LdAction("plugin", NS + "VolumeAdjustment:+").execute(repeat=3)
    LdAction("plugin", NS + "VolumeAdjustment:-").execute()
    LdAction("plugin", NS + "VolumeAdjustment_RESET").execute()
    LdAction("plugin", NS + "PowerSwitch|toggle").execute()
    LdAction("plugin", NS + "BrokenCommand").execute()
    LdAction("plugin", NS + "CounterCommand").execute()
    c.eq("presses, parameters, turns and resets all reach the plugin, in order",
         wait_for(lambda: len(calls()) >= 9) and calls()[2:9],
         ["counter 1", "switch 1", "adjust 3 -> 53", "adjust -1 -> 52", "reset", "power True", "counter 2"])
    c.eq("an action that throws leaves the plugin running", status().get("state"), "running")

    # -- keys and states ------------------------------------------------------------------
    import input_backend                                              # noqa: E402

    sent = []
    real_send = input_backend.send_hotkey
    input_backend.send_hotkey = lambda combo, repeat=1: sent.append(combo)
    try:
        LdAction("plugin", NS + "ShortcutCommand").execute()
        c.eq("a plugin's keyboard shortcut goes through the app's input backend",
             wait_for(lambda: sent == ["ctrl+shift+m"]) or sent, True)
    finally:
        input_backend.send_hotkey = real_send

    host_.watch([NS + "ModeCommand"])
    c.eq("a multistate command starts in its first state",
         wait_for(lambda: ph.label_for(NS + "ModeCommand") == "Low"), True)
    LdAction("plugin", NS + "ModeCommand").execute()
    LdAction("plugin", NS + "ModeCommand").execute()
    c.eq("and a press moves it on", wait_for(lambda: ph.label_for(NS + "ModeCommand") == "High"), True)
    LdAction("plugin", NS + "ModeCommand").execute()
    c.eq("round to the start", wait_for(lambda: ph.label_for(NS + "ModeCommand") == "Low"), True)

    # -- per-binding values: profile actions and action editors -------------------------
    PNS = "TestPlugin/"
    c.eq("a profile action is offered once, with its prompt",
         host_.editor(NS + "SayCommand"), {"kind": "profile", "type": "text", "prompt": "Message to send:"})
    c.eq("and a list profile action is not split into its parameters",
         (NS + "PickCommand|a" in actions, (host_.editor(NS + "PickCommand") or {}).get("type")), (False, "list"))
    pick_state = host_.editor_state(NS + "PickCommand") or {}
    c.eq("its choices are the parameters", [i["label"] for i in pick_state.get("items", [])], ["Alpha", "Beta"])
    fruit_state = host_.editor_state(NS + "FruitCommand") or {}
    c.eq("a tree is offered flattened, path first",
         [(i["value"], i["label"]) for i in fruit_state.get("items", [])],
         [("apple", "Fruit \u203a Apple"), ("pear", "Fruit \u203a Pear")])

    send = PNS + "SendMessage"
    form = host_.editor(send) or {}
    c.eq("an action editor's form is described",
         [(x["name"], x["kind"], x.get("required")) for x in form.get("controls", [])],
         [("message", "text", True), ("channel", "list", False), ("loud", "check", False)])
    c.eq("with the plugin's placeholder", form["controls"][0].get("placeholder"), "Hello")
    st = host_.editor_state(send) or {}
    c.eq("its list's items come from the plugin",
         [i["value"] for i in st.get("lists", {}).get("channel", {}).get("items", [])], ["general", "random"])
    answer = host_.editor_changed(send, "channel", {"message": "hi", "channel": "random"})
    c.eq("a change reaches the plugin, which may rename the binding",
         (answer or {}).get("displayName"), "To #random")

    bound_say = ph.with_values(NS + "SayCommand", "hello there")
    bound_pick = ph.with_values(NS + "PickCommand", "b")
    bound_send = ph.with_values(send, {"message": "hi", "channel": "random", "loud": "true"})
    bound_nudge = ph.with_values(PNS + "Nudge:+", {"step": "3"})
    c.eq("a binding carries its values in the stored string",
         (bound_say, bound_send),
         (NS + "SayCommand|hello there",
          PNS + 'SendMessage|{"channel":"random","loud":"true","message":"hi"}'))
    before = len(calls())
    for v in (bound_say, bound_pick, ph.with_values(NS + "FruitCommand", "pear"), bound_send):
        LdAction("plugin", v).execute()
    LdAction("plugin", bound_nudge).execute(repeat=2)
    c.eq("each runs with its own values",
         wait_for(lambda: len(calls()) >= before + 5) and calls()[before:before + 5],
         ["say hello there", "pick b", "fruit pear", "send random hi True", "nudge 6"])
    host_.watch([bound_say, bound_send])
    c.eq("and is labelled for them",
         wait_for(lambda: (ph.label_for(bound_say), ph.label_for(bound_send)) == ("Say: hello there", "#random"))
         or (ph.label_for(bound_say), ph.label_for(bound_send)), True)

    # -- folders ---------------------------------------------------------------------
    from device_controller import DeviceController
    from DeviceProfile import WS_KEYS

    class FakeDevice:
        def set_key_image(self, keycode, image): pass
        def draw_image(self, *a, **k): pass
        def reset(self): pass
        def set_button_color(self, *a, **k): pass

    dc = DeviceController()
    dc.selected_ws = WS_KEYS[0]
    dc.device = FakeDevice()
    folder = NS + "NumbersFolder"
    host_.on_folder = lambda kind, value: (dc.close_plugin_folder(value) if kind == "close"
                                           else dc.refresh_plugin_folder(value))
    c.eq("a folder is offered as an action, and known to be one", host_.is_folder(folder), True)
    dc.current_ws().actions["tb11"] = LdAction("plugin", folder)
    dc.on_touch_press("tb11")

    def page():
        menu = dc.current_menu()
        return [(k, menu.actions[k].a_type, dc._auto_label_text(menu.actions[k]))
                for k in ("tb11", "tb12", "tb13", "tb33", "tb34")]
    c.eq("pressing it opens the plugin's page, and the plugin is told",
         (len(dc.submenu_stack), wait_for(lambda: "activate" in calls())), (1, True))
    c.eq("Back first, the plugin's keys after, page keys last",
         wait_for(lambda: page() == [("tb11", "back", "Back"), ("tb12", "plugin", "N0"),
                                     ("tb13", "plugin", "N1"), ("tb33", "folderpage", "\u25c0"),
                                     ("tb34", "folderpage", "\u25b6")]) or page(), True)
    dc.on_touch_press("tb34")
    c.eq("the next page carries on where the first stopped",
         wait_for(lambda: dc._auto_label_text(dc.current_menu().actions["tb12"]) == "N9")
         or dc._auto_label_text(dc.current_menu().actions["tb12"]), True)
    dc.run_bound_action("enc1L-r", repeat=2)
    c.eq("its adjustment is on the first knob", wait_for(lambda: "folder adjust level 2" in calls()), True)
    dc.on_touch_press("tb33")
    dc.on_touch_press("tb12")
    c.eq("a press inside reaches the plugin with its own parameter",
         wait_for(lambda: "folder press 0" in calls()), True)
    c.eq("and when the plugin changes the folder, the page follows",
         wait_for(lambda: [dc.current_menu().actions[k].a_type for k in ("tb12", "tb14", "tb21")]
                  == ["plugin", "plugin", "none"]), True)
    dc.on_touch_press("tb13")
    c.eq("and when the plugin closes it, it closes",
         wait_for(lambda: dc.submenu_stack == [] and "deactivate" in calls()), True)
    dc.on_touch_press("tb11")
    wait_for(lambda: len(dc.submenu_stack) == 1)
    dc.on_touch_press("tb11")     # Back
    c.eq("Back closes it too, and the plugin is told",
         wait_for(lambda: dc.submenu_stack == [] and calls().count("deactivate") == 2), True)
    host_.on_folder = None

    # -- text and images ---------------------------------------------------------------
    host_.watch([NS + "CounterCommand", NS + "VolumeAdjustment:+", NS + "PowerSwitch|toggle"])
    c.eq("the label is the plugin's own, live",
         wait_for(lambda: ph.label_for(NS + "CounterCommand") == "Count 2"), True)
    c.eq("an adjustment's label carries its value",
         wait_for(lambda: ph.label_for(NS + "VolumeAdjustment:+") == "Volume\n50") or
         ph.label_for(NS + "VolumeAdjustment:+"), True)
    c.eq("a two-state command names its state",
         wait_for(lambda: ph.label_for(NS + "PowerSwitch|toggle") == "Power on"), True)


    def pixel(value):
        path = ph.image_for(value)
        if not path:
            return None
        with Image.open(path) as im:
            return im.convert("RGB").getpixel((2, 2))


    c.eq("an image the plugin draws reaches the app, and follows its state",
         wait_for(lambda: pixel(NS + "CounterCommand") == (0, 255, 0)), True)
    c.eq("an embedded resource image too", wait_for(lambda: pixel(NS + "IconCommand") == (0, 0, 255)), True)

    def rendered_svg():
        host_.render_icons()           # the app does this on its Qt thread
        return pixel(NS + "SvgCommand") == (255, 0, 255)
    c.eq("an SVG image is rendered by the app", wait_for(rendered_svg), True)

    # -- status, accounts ----------------------------------------------------------------
    c.eq("the plugin's status shows", status().get("detail"), "not signed in yet")
    c.eq("its account is listed",
         wait_for(lambda: [(a["name"], a["isLoggedIn"], a["loginTitle"]) for a in status().get("accounts", [])]
                  == [("service", False, "Sign in to Test")]), True)
    host_.account("TestPlugin", "service", "login")
    c.eq("signing in reaches the plugin, and it reports back",
         wait_for(lambda: [(a["isLoggedIn"], a["userName"]) for a in status().get("accounts", [])]
                  == [(True, "tester")]), True)

    # -- loupedeck: links -------------------------------------------------------------------
    c.eq("a link reaches the plugin it names",
         (ph.send_url("loupedeck:plugin/TestPlugin/callback/login?code=abc"),
          wait_for(lambda: "url ?code=abc" in calls())), ("ok", True))
    c.eq("the other spelling too",
         ph.parse_link("loupedeck://plugin/TestPlugin/callback/x"), ("TestPlugin", "callback/x"))
    c.eq("a link for a plugin that is not here says so",
         "no plugin" in ph.send_url("loupedeck:plugin/Nope/callback"), True)

    # -- restarts keep settings and the sign-in ----------------------------------------------
    host_.reload("TestPlugin")
    c.eq("after a restart", wait_for(lambda: status().get("state") == "running"), True)
    c.eq("its settings were kept", "load 2" in calls(), True)
    c.eq("and Install did not run again", calls().count("install"), 1)
    c.eq("and so was the sign-in",
         wait_for(lambda: [(a["isLoggedIn"], a["userName"]) for a in status().get("accounts", [])]
                  == [(True, "tester")]), True)

    host_.stop()
    c.eq("stopping unloads it", wait_for(lambda: "unload" in calls(), timeout=5), True)
    ph.set_host(None)
    c.eq("uninstalling removes its data too",
         (ph.uninstall("TestPlugin"), os.path.exists(ph.data_dir("TestPlugin"))), ("", False))



RUNTIMES = [r for r, tool in (("mono", "mono"), ("core", "dotnet")) if shutil.which(tool)]
for runtime in RUNTIMES:
    scenario(runtime)
c.prefix = ""
shutil.rmtree(tmp, ignore_errors=True)
raise SystemExit(c.done())
