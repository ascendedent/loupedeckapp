"""plugin_port: what ties a plugin to Windows or macOS, read without running it.

A small assembly written the way Windows-only plugins are (keys sent through
user32, the registry, a PowerShell command, a COM audio interface, a library
merged in) is compiled with Mono's mcs and packaged as a Windows-only .lplug4;
a Node plugin carries a native addon built for Windows and an osascript
command. Each finding has to land in the right area, and a plugin with nothing
platform-bound has to come out as running as it is. Skipped where Mono is not
installed.
"""
import os
import shutil
import subprocess
import tempfile
import zipfile

from _harness import Checks

tmp = tempfile.mkdtemp()
os.environ["LOUPEDECKAPP_CONFIG_DIR"] = os.path.join(tmp, "config")

import plugin_port as pp                                          # noqa: E402

c = Checks()

c.eq("a library is judged by name", pp.library("Newtonsoft.Json"), ("any", ""))
c.eq("or by its family", pp.library("Microsoft.Extensions.Logging"), ("any", ""))
c.eq("Windows audio is Windows audio", pp.library("AudioSwitcher.AudioApi.CoreAudio"), ("windows", "audio"))
c.eq("an unknown one is not guessed at", pp.library("SomethingElse"), None)
c.eq("merged code is known by its namespace",
     pp.library_of_namespace("WindowsInput.Native"), ("WindowsInput", ("windows", "input")))
c.eq("but not every System namespace", pp.library_of_namespace("System.Collections"), None)
c.eq("SendInput is input", pp._area("SendInput", "user32.dll"), "input")
c.eq("GetForegroundWindow is windows", pp._area("GetForegroundWindow", "user32.dll"), "windows")
c.eq("an unnamed gdi32 function is drawing", pp._area("Rectangle", "gdi32.dll"), "drawing")
c.eq("user32 is Windows", pp._platform_of_module("user32.dll", set()), "windows")
c.eq("a framework path is the Mac",
     pp._platform_of_module("/System/Library/Frameworks/AppKit.framework/AppKit", set()), "mac")
c.eq("gdiplus is mapped to libgdiplus here", pp._platform_of_module("gdiplus.dll", set()), "linux")
c.eq("a sentence that names a tool is not a command", pp._prose("Path to svcl.exe is not set; enter it below"), True)
c.eq("a command line is", pp._prose("powershell.exe -Command Get-Process"), False)

if not (shutil.which("mono") and shutil.which("mcs")):
    print("%-58s %s" % ("scanning .NET plugins (Mono is not installed)", "skipped"))
    raise SystemExit(c.done())

SOURCE = r"""
using System;
using System.Diagnostics;
using System.Runtime.InteropServices;

namespace Loupedeck.WinOnlyPlugin
{
    public class Native
    {
        [DllImport("user32.dll")] public static extern uint SendInput(uint n, IntPtr inputs, int size);
        [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
        [DllImport("user32.dll")] public static extern void keybd_event(byte vk, byte scan, uint flags, IntPtr extra);
        [DllImport("kernel32.dll")] public static extern IntPtr LoadLibrary(string name);
    }

    [Guid("5CDF2C82-841E-4546-9722-0CF74078229A"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IAudioEndpointVolume { int SetMasterVolumeLevelScalar(float level, Guid context); }

    public class Actions
    {
        public void Mute() { Native.SendInput(0, IntPtr.Zero, 0); Native.LoadLibrary("x"); }
        public IntPtr Focused() { return Native.GetForegroundWindow(); }
        public void Shell() { Process.Start("powershell.exe", "-Command Get-Process"); }
        public object Setting() { return Microsoft.Win32.Registry.GetValue(@"HKEY_CURRENT_USER\Software\Foo", "x", null); }
        public bool Found() { return Process.GetProcessesByName("foo.exe").Length > 0; }
    }

    public class App
    {
        protected string GetProcessName() { return "FooApp"; }
    }
}

// A library merged into the plugin (ILMerge, Costura): its own native calls
// are the library's business, judged as the library.
namespace Newtonsoft.Json.Merged
{
    public class Inside
    {
        [DllImport("kernel32.dll")] public static extern int GetTickCount();
        public int Now() { return GetTickCount(); }
    }
}
"""

src = os.path.join(tmp, "WinOnly.cs")
dll = os.path.join(tmp, "WinOnlyPlugin.dll")
with open(src, "w") as f:
    f.write(SOURCE)
p = subprocess.run(["mcs", "-nologo", "-target:library", "-out:" + dll, src], capture_output=True, text=True)
c.eq("the Windows-style plugin compiles", p.returncode, 0)
if p.returncode != 0:
    print(p.stdout, p.stderr)
    raise SystemExit(c.done())

package = os.path.join(tmp, "WinOnly.lplug4")
with zipfile.ZipFile(package, "w") as zf:
    zf.writestr("metadata/LoupedeckPackage.yaml",
                "type: plugin4\nname: WinOnly\ndisplayName: Win Only\nversion: 1.0\n"
                "pluginFileName: WinOnlyPlugin.dll\npluginFolderWin: ./bin/win/\n")
    zf.write(dll, "bin/win/WinOnlyPlugin.dll")
    # Logitech's PluginApi.dll, bundled as some packages do: never opened.
    zf.writestr("bin/win/PluginApi.dll", b"not to be read")

unpacked = os.path.join(tmp, "unpacked")
with zipfile.ZipFile(package) as zf:
    zf.extractall(unpacked)
rows = pp._scan_dotnet(os.path.join(unpacked, "bin", "win"))
c.eq("a bundled PluginApi.dll is never opened",
     [r for r in rows if "PluginApi" in r[1]], [])

r = pp.analyze(package)
c.eq("it is read", r["error"], "")
c.eq("it is a .NET plugin with a Windows build only", (r["runtime"], r["builds"]), ("dotnet", ["win"]))
c.eq("it needs stand-ins", r["verdict"], "convertible")
found = {(f["area"], f["kind"], f["what"]) for f in r["findings"]}
c.eq("sending keys is input", ("input", "native", "user32!SendInput") in found, True)
c.eq("even declared and never called", ("input", "native", "user32!keybd_event") in found, True)
c.eq("the focused window is windows", ("windows", "native", "user32!GetForegroundWindow") in found, True)
c.eq("COM audio is audio", ("audio", "com", "IAudioEndpointVolume") in found, True)
c.eq("the registry is registry",
     any(a == "registry" and k == "framework" and "Registry" in w for a, k, w in found), True)
c.eq("PowerShell is a shell command", ("shell", "command", "powershell.exe") in found, True)
c.eq("a program name is only noted", ("processes", "program", "foo.exe") in found, True)
c.eq("loading a library needs nothing",
     all(f["what"] != "kernel32!LoadLibrary" for f in pp.blocking(r)), True)
c.eq("merged library code is judged as the library",
     any("GetTickCount" in w for _a, _k, w in found), False)
c.eq("the application it controls is known", r["apps"], ["FooApp"])
blocking_areas = sorted({f["area"] for f in pp.blocking(r)})
c.eq("what it needs, by area", blocking_areas, ["audio", "input", "registry", "shell", "windows"])

# -- a Node plugin --------------------------------------------------------------------
node = os.path.join(tmp, "NodeMac.lplug4")
with zipfile.ZipFile(node, "w") as zf:
    zf.writestr("metadata/LoupedeckPackage.yaml",
                "type: plugin4\nname: NodeMac\ndisplayName: Node Mac\nversion: 1.0\n"
                "pluginRuntime: nodejs\nentryPoint: bin/index.js\n")
    zf.writestr("bin/index.js",
                "const { exec } = require('child_process');\n"
                "const robot = require('robotjs');\n"
                "exec('osascript -e \"set volume 3\"');\n")
    zf.writestr("bin/node_modules/addon/build/Release/addon.node", b"MZ\x90\x00windows addon")
r = pp.analyze(node)
found = {(f["area"], f["kind"], f["what"], f["platform"]) for f in r["findings"]}
c.eq("a Node plugin is read", (r["error"], r["runtime"]), ("", "nodejs"))
c.eq("an addon built for Windows is found",
     ("addon", "native", "bin/node_modules/addon/build/Release/addon.node", "windows") in found, True)
c.eq("so is a Windows-only npm module", ("node", "library", "robotjs", "windows") in found, True)
c.eq("and the osascript it runs", any(a == "shell" and "osascript" in w for a, _k, w, _p in found), True)

# -- one that runs as it is ------------------------------------------------------------
plain = os.path.join(tmp, "Plain.cs")
with open(plain, "w") as f:
    f.write("namespace P { public class C { public int N() { return 1; } } }")
plain_dll = os.path.join(tmp, "PlainPlugin.dll")
subprocess.run(["mcs", "-nologo", "-target:library", "-out:" + plain_dll, plain], check=True)
plain_pkg = os.path.join(tmp, "Plain.lplug4")
with zipfile.ZipFile(plain_pkg, "w") as zf:
    zf.writestr("metadata/LoupedeckPackage.yaml",
                "type: plugin4\nname: Plain\nversion: 1.0\npluginFileName: PlainPlugin.dll\n"
                "pluginFolderWin: win\npluginFolderMac: mac\n")
    zf.write(plain_dll, "win/PlainPlugin.dll")
    zf.write(plain_dll, "mac/PlainPlugin.dll")
r = pp.analyze(plain_pkg)
c.eq("a plugin with nothing platform-bound runs as it is", r["verdict"], "runs")

# -- across many -------------------------------------------------------------------
s = pp.summarize([pp.analyze(package), pp.analyze(node), r])
c.eq("the summary counts verdicts", s["verdicts"], {"convertible": 2, "runs": 1})
c.eq("and ranks areas by how many plugins need them", s["areas"][0][1], 2)
c.eq("shell is needed by both", [a for a, n, _ in s["areas"] if n == 2], ["shell"])
c.eq("an unreadable file says so", pp.analyze(os.path.join(tmp, "nope.lplug4"))["verdict"], "unreadable")

raise SystemExit(c.done())
