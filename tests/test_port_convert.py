"""Converting a Windows plugin at install: plugin_port + dotnet/tools/PortPatch.

A plugin written the Windows way is compiled with Mono's mcs: it opens a page
with "cmd /c start", registers a URL protocol of its own and opens that (as
the Weather plugin does), and sends keys through a bundled, strong-named
WindowsInput.dll (a small fake of that library that only records it was
used). Installing it converts it; run through the real host, each action has
to arrive here the Linux way: pages through xdg-open (a fake one on PATH that
logs), keys through the input backend (recorded, not sent). Reverting puts the
plugin back byte for byte. Skipped where Mono is not installed.
"""
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
import zipfile

from _harness import Checks

tmp = tempfile.mkdtemp()
os.environ["LOUPEDECKAPP_CONFIG_DIR"] = os.path.join(tmp, "config")
os.environ["XDG_RUNTIME_DIR"] = tmp
os.environ["XDG_DATA_HOME"] = os.path.join(tmp, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(tmp, "xdgconfig")

# xdg-open, as the host will find it: logs what it was asked to open.
fake_bin = os.path.join(tmp, "bin")
os.makedirs(fake_bin)
opened_log = os.path.join(tmp, "opened.txt")
with open(os.path.join(fake_bin, "xdg-open"), "w") as f:
    f.write("#!/bin/sh\necho \"$@\" >> '%s'\n" % opened_log)
os.chmod(os.path.join(fake_bin, "xdg-open"), 0o755)
os.environ["PATH"] = fake_bin + os.pathsep + os.environ["PATH"]

import input_backend                                              # noqa: E402

sent = []
input_backend.send_hotkey = lambda combo, repeat=1: sent.append(("keys", combo))
input_backend.type_text = lambda text: sent.append(("text", text))
input_backend.scroll = lambda direction, amount=1: sent.append(("scroll", direction, amount))
input_backend.key_down = lambda key: sent.append(("down", key))
input_backend.key_up = lambda key: sent.append(("up", key))

import plugin_host as ph                                          # noqa: E402
import plugin_port as pp                                          # noqa: E402

c = Checks()

if not (shutil.which("mono") and shutil.which("mcs") and shutil.which("sn")):
    print("%-58s %s" % ("converting plugins (Mono is not installed)", "skipped"))
    raise SystemExit(c.done())

host, error = ph.dotnet_host()
c.eq("the host and the converters build", error, "")
if error:
    raise SystemExit(c.done())
bin_dir = os.path.dirname(host)
api = os.path.join(bin_dir, "PluginApi.dll")

# -- the "original" WindowsInput, strong-named as the real one is --------------------
FAKE_WINDOWSINPUT = r"""
using System;
using System.Reflection;
[assembly: AssemblyVersion("1.0.4.0")]
namespace WindowsInput.Native { public enum VirtualKeyCode { CONTROL = 0x11, SHIFT = 0x10, VK_K = 0x4B } }
namespace WindowsInput
{
    using WindowsInput.Native;
    public interface IKeyboardSimulator
    {
        IKeyboardSimulator ModifiedKeyStroke(VirtualKeyCode modifierKeyCode, VirtualKeyCode keyCode);
        IKeyboardSimulator TextEntry(string text);
        IKeyboardSimulator KeyDown(VirtualKeyCode keyCode);
        IKeyboardSimulator KeyUp(VirtualKeyCode keyCode);
    }
    public interface IMouseSimulator { IMouseSimulator VerticalScroll(int clicks); }
    class Recorder : IKeyboardSimulator, IMouseSimulator
    {
        static void Out() { System.IO.File.AppendAllText(Environment.GetEnvironmentVariable("TEST_OUT"), "original\n"); }
        public IKeyboardSimulator ModifiedKeyStroke(VirtualKeyCode m, VirtualKeyCode k) { Out(); return this; }
        public IKeyboardSimulator TextEntry(string text) { Out(); return this; }
        public IKeyboardSimulator KeyDown(VirtualKeyCode k) { Out(); return this; }
        public IKeyboardSimulator KeyUp(VirtualKeyCode k) { Out(); return this; }
        public IMouseSimulator VerticalScroll(int clicks) { Out(); return this; }
    }
    public class InputSimulator
    {
        readonly Recorder _r = new Recorder();
        public IKeyboardSimulator Keyboard { get { return _r; } }
        public IMouseSimulator Mouse { get { return _r; } }
    }
}
"""

# OpenAI_API's shape where it matters: a fixed model, made from a name.
FAKE_OPENAI = r"""
namespace OpenAI_API.Models
{
    public class Model
    {
        public string ModelID;
        public Model(string name) { ModelID = name; }
        public static Model ChatGPTTurbo { get { return new Model("gpt-3.5-turbo"); } }
        public static implicit operator Model(string name) { return new Model(name); }
        public static implicit operator string(Model model) { return model.ModelID; }
    }
}
"""

PLUGIN = r"""
using System;
using System.Diagnostics;
using Microsoft.Win32;
using WindowsInput;
using WindowsInput.Native;

namespace Loupedeck.WinPlugin
{
    public class WinPlugin : Plugin
    {
        public override bool HasNoApplication { get { return true; } }
        public override bool UsesApplicationApiOnly { get { return true; } }

        // As Weather does: a URL protocol whose command opens a page.
        public override void Load()
        {
            using (var key = Registry.ClassesRoot.CreateSubKey(@"winplugin\shell\open\command"))
                key.SetValue("", "\"C:\\Windows\\System32\\cmd.exe\" /c \"START https://example.org/%1\"");
        }
    }

    public class OpenPage : PluginDynamicCommand
    {
        public OpenPage() : base("Open page", "", "Win") { }
        protected override void RunCommand(string p) { Process.Start("cmd.exe", "/c start https://example.com/page"); }
    }

    public class OpenProtocol : PluginDynamicCommand
    {
        public OpenProtocol() : base("Open protocol", "", "Win") { }
        protected override void RunCommand(string p) { Process.Start("winplugin:42"); }
    }

    public class OpenWithInfo : PluginDynamicCommand
    {
        public OpenWithInfo() : base("Open with info", "", "Win") { }
        protected override void RunCommand(string p)
        {
            var proc = new Process { StartInfo = new ProcessStartInfo("explorer.exe", "https://example.net/") };
            proc.Start();
        }
    }

    public class Keys : PluginDynamicCommand
    {
        public Keys() : base("Keys", "", "Win") { }
        protected override void RunCommand(string p)
        {
            var sim = new InputSimulator();
            sim.Keyboard.ModifiedKeyStroke(WindowsInput.Native.VirtualKeyCode.CONTROL, WindowsInput.Native.VirtualKeyCode.VK_K);
            sim.Keyboard.TextEntry("hi");
            sim.Mouse.VerticalScroll(-2);
        }
    }

    // Ctrl held while the wheel turns, as AdvancedCommands' wheel does.
    public class Zoom : PluginDynamicCommand
    {
        public Zoom() : base("Zoom", "", "Win") { }
        protected override void RunCommand(string p)
        {
            var sim = new InputSimulator();
            sim.Keyboard.KeyDown(WindowsInput.Native.VirtualKeyCode.CONTROL);
            sim.Mouse.VerticalScroll(3);
            sim.Keyboard.KeyUp(WindowsInput.Native.VirtualKeyCode.CONTROL);
        }
    }

    // Which model it would ask OpenAI for.
    public class AskModel : PluginDynamicCommand
    {
        public AskModel() : base("Ask model", "", "Win") { }
        protected override void RunCommand(string p)
        {
            string model = OpenAI_API.Models.Model.ChatGPTTurbo;
            System.IO.File.WriteAllText(Environment.GetEnvironmentVariable("TEST_MODEL_OUT"), model);
        }
    }

    // Holds Shift and dies: the app must let go of it.
    public class HoldAndDie : PluginDynamicCommand
    {
        public HoldAndDie() : base("Hold and die", "", "Win") { }
        protected override void RunCommand(string p)
        {
            new InputSimulator().Keyboard.KeyDown(WindowsInput.Native.VirtualKeyCode.SHIFT);
            System.Threading.Thread.Sleep(300);
            Environment.Exit(3);
        }
    }
}
"""

openai_src = os.path.join(tmp, "OpenAI.cs")
openai_dll = os.path.join(tmp, "OpenAI_API.dll")
with open(openai_src, "w") as f:
    f.write(FAKE_OPENAI)
subprocess.run(["mcs", "-nologo", "-target:library", "-out:" + openai_dll, openai_src], check=True)
wi_src = os.path.join(tmp, "WindowsInput.cs")
plugin_src = os.path.join(tmp, "WinPlugin.cs")
with open(wi_src, "w") as f:
    f.write(FAKE_WINDOWSINPUT)
with open(plugin_src, "w") as f:
    f.write(PLUGIN)
snk = os.path.join(tmp, "key.snk")
subprocess.run(["sn", "-q", "-k", snk], check=True, capture_output=True)
wi_dll = os.path.join(tmp, "WindowsInput.dll")
p = subprocess.run(["mcs", "-nologo", "-target:library", "-keyfile:" + snk, "-out:" + wi_dll, wi_src],
                   capture_output=True, text=True)
c.eq("the fake WindowsInput compiles, strong-named", p.returncode, 0)
plugin_dll = os.path.join(tmp, "WinPluginPlugin.dll")
p2 = subprocess.run(["mcs", "-nologo", "-target:library", "-out:" + plugin_dll, "-r:" + api, "-r:" + wi_dll,
                     "-r:" + openai_dll,
                     plugin_src], capture_output=True, text=True)
c.eq("the Windows-style plugin compiles", p2.returncode, 0)
if p.returncode or p2.returncode:
    print(p.stdout, p.stderr, p2.stdout, p2.stderr)
    raise SystemExit(c.done())

package = os.path.join(tmp, "WinPlugin.lplug4")
with zipfile.ZipFile(package, "w") as zf:
    zf.writestr("metadata/LoupedeckPackage.yaml",
                "type: plugin4\nname: WinPlugin\ndisplayName: Win Plugin\nversion: 1.0\n"
                "pluginFileName: WinPluginPlugin.dll\npluginFolderWin: bin\\win\n")
    zf.write(plugin_dll, "bin\\win\\WinPluginPlugin.dll")
    zf.write(wi_dll, "bin\\win\\WindowsInput.dll")
    zf.write(openai_dll, "bin\\win\\OpenAI_API.dll")

report = pp.analyze(package)
c.eq("the analyzer says it converts", report["verdict"], "converts")
c.eq("by pointing Process.Start at the shim, swapping WindowsInput and asking for the set model",
     pp.plan(report), {"process": ["WinPluginPlugin.dll"], "swap": ["WindowsInput"],
                       "value": [("WinPluginPlugin.dll", "OpenAI_API.Models.Model::get_ChatGPTTurbo")]})

# -- install converts it ------------------------------------------------------------
name, err = ph.install(package)
c.eq("it installs", (name, err), ("WinPlugin", ""))
folder = os.path.join(ph.plugins_dir(), "WinPlugin")
state = pp.conversion("WinPlugin")
c.eq("and was converted on the way in",
     (state and state["verdict"], state and state["error"], state and len(state["converted"])), ("converts", "", 3))
c.eq("and asks the app for an OpenAI key and model",
     [x["name"] for x in pp.settings("WinPlugin")], ["openai_key", "openai_model"])
c.eq("a setting is saved where the plugin reads it", pp.write_setting("WinPlugin", "openai_model", "my-model"), "")
c.eq("and reads back", [x["value"] for x in pp.settings("WinPlugin")], ["", "my-model"])
c.eq("the key is kept private",
     oct(os.stat(os.path.join(ph.data_dir("WinPlugin"), "online-files", "gpt-openai-access.json")).st_mode & 0o777),
     "0o600")
c.eq("an unknown setting is refused", pp.write_setting("WinPlugin", "nope", "x") != "", True)
c.eq("with nothing left over", state and state["remaining"], [])
c.eq("the originals are kept",
     sorted(os.listdir(os.path.join(folder, ".orig", "bin", "win"))), ["WinPluginPlugin.dll", "WindowsInput.dll"])
c.eq("converting again does nothing new", pp.convert_installed("WinPlugin"), state)


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


c.eq("WindowsInput is now the stand-in",
     sha(os.path.join(folder, "bin", "win", "WindowsInput.dll")),
     sha(os.path.join(bin_dir, pp.STAND_INS["WindowsInput"])))

c.eq("the conversion records what it was made with", state and state["fingerprint"], pp.fingerprint())
c.eq("so it is not stale", pp.stale("WinPlugin"), False)

# -- converted under an older stand-in: redone when the host starts ----------------------
state_path = os.path.join(folder, pp.PORT_STATE)
with open(state_path) as f:
    older = json.load(f)
older["fingerprint"] = "an older one"
with open(state_path, "w") as f:
    json.dump(older, f)
shutil.copy2(wi_dll, os.path.join(folder, "bin", "win", "WindowsInput.dll"))   # as an older stand-in
c.eq("a conversion made with other stand-ins is stale", pp.stale("WinPlugin"), True)

# -- and it runs the Linux way ---------------------------------------------------------
out = os.path.join(tmp, "out.txt")
os.environ["TEST_OUT"] = out
model_out = os.path.join(tmp, "model.txt")
os.environ["TEST_MODEL_OUT"] = model_out
host_ = ph.PluginHost()
ph.set_host(host_)
host_.start()


def wait_for(pred, timeout=20.0):
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.1)
    return False


def opened():
    try:
        with open(opened_log) as f:
            return f.read().split()
    except OSError:
        return []


try:
    c.eq("it starts", wait_for(lambda: any(s["state"] == "running" for s in host_.status())), True)
    c.eq("after being converted again with what is here now",
         ((pp.conversion("WinPlugin") or {}).get("fingerprint") == pp.fingerprint(),
          sha(os.path.join(folder, "bin", "win", "WindowsInput.dll")) == sha(os.path.join(bin_dir, pp.STAND_INS["WindowsInput"])),
          sorted(os.listdir(os.path.join(folder, ".orig", "bin", "win")))),
         (True, True, ["WinPluginPlugin.dll", "WindowsInput.dll"]))
    values = {label: value for _g, label, value, _k in host_.actions()}
    ph.execute(values["Open page"])
    c.eq("cmd /c start opens the page with xdg-open",
         wait_for(lambda: "https://example.com/page" in opened()), True)
    ph.execute(values["Open protocol"])
    c.eq("its own protocol runs the command it registered, translated",
         wait_for(lambda: "https://example.org/winplugin:42" in opened()), True)
    ph.execute(values["Open with info"])
    c.eq("process.Start() with explorer is translated too",
         wait_for(lambda: "https://example.net/" in opened()), True)
    ph.execute(values["Keys"])
    c.eq("WindowsInput's keys, text and wheel go through the input backend",
         wait_for(lambda: sent == [("keys", "ctrl+k"), ("text", "hi"), ("scroll", "down", 2)]), True)
    c.eq("and the original library was never used", os.path.exists(out), False)
    ph.execute(values["Ask model"])
    c.eq("the plugin asks OpenAI for the model set in the app, not its fixed one",
         wait_for(lambda: os.path.exists(model_out) and open(model_out).read() == "my-model"), True)
    del sent[:]
    ph.execute(values["Zoom"])
    c.eq("a key held while the wheel turns is held, in order",
         wait_for(lambda: sent == [("down", "ctrl"), ("scroll", "up", 3), ("up", "ctrl")]), True)
    del sent[:]
    ph.execute(values["Hold and die"])
    c.eq("a plugin that exits holding a key has it let go",
         wait_for(lambda: sent == [("down", "shift"), ("up", "shift")]), True)
finally:
    host_.stop()

# -- a backend that cannot hold keys ---------------------------------------------------
def cannot(_key):
    raise NotImplementedError


input_backend.key_down = input_backend.key_up = cannot
del sent[:]
kb = ph._Keyboard("fallback")
for step in ((kb.down, "ctrl"), (kb.down, "z"), (kb.keys, "a"), (kb.up, "ctrl"), (kb.keys, "b")):
    kb.post(*step)
kb.wait()
c.eq("where keys cannot be held, held modifiers go with the next keys",
     sent, [("keys", "ctrl+z"), ("keys", "ctrl+a"), ("keys", "b")])

# -- reverting ----------------------------------------------------------------------
before = sha(os.path.join(tmp, "WindowsInput.dll")), sha(plugin_dll)
c.eq("reverting succeeds", pp.revert("WinPlugin"), "")
c.eq("and puts both files back as they were",
     (sha(os.path.join(folder, "bin", "win", "WindowsInput.dll")),
      sha(os.path.join(folder, "bin", "win", "WinPluginPlugin.dll"))), before)
c.eq("forgetting the conversion", (pp.conversion("WinPlugin"), os.path.exists(os.path.join(folder, ".orig"))),
     (None, False))
c.eq("a plugin never converted (installed before conversion existed) is stale too",
     pp.stale("WinPlugin"), True)

shutil.rmtree(tmp, ignore_errors=True)
raise SystemExit(c.done())
