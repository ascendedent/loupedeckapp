"""What stands between a Windows or macOS Loupedeck plugin and running here,
and converting what has a Linux stand-in.

Reading: a package's platform-bound parts, without running any of it. A .NET plugin's assemblies are read by
dotnet/tools/PortScan.cs (metadata, through Mono.Cecil); a Node plugin's
JavaScript and native addons are read here. The findings are grouped by what
a Linux stand-in would have to do (send keys, find the focused window, set
the volume...), which is what decides which stand-ins to write first:

    python3 plugin_port.py Some.lplug4            one plugin, in detail
    python3 plugin_port.py ~/Downloads            every package there, ranked
    python3 plugin_port.py ... --json             the same, for a program
    python3 plugin_port.py convert <name>         convert an installed plugin
    python3 plugin_port.py revert <name>          put it back as installed
    python3 plugin_port.py refresh <name>         convert again if the rules or stand-ins changed

A plugin's own code is reported in full. Libraries it bundles are judged as a
whole when they are known (Newtonsoft.Json runs anywhere; AudioSwitcher's
CoreAudio is Windows audio), so their internals do not drown the report.

Converting (plugin_host.install does it for every .NET plugin): findings a
rule covers are fixed in the installed copy by dotnet/tools/PortPatch.cs,
originals kept in .orig/ and what was done recorded in .port.json:

  - Process.Start calls that open things the Windows or macOS way (cmd /c
    start, explorer, rundll32 url.dll, open, a URL protocol the plugin
    registered) go to ProcessShim (dotnet/PluginApi/Shims.cs): xdg-open;
  - bundled libraries with a stand-in (STAND_INS, dotnet/shims/) are
    replaced by it and the plugin's references pointed at it.

Each new rule is written once and covers every later plugin that needs it.

Qt-free.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

import plugin_host

# -- what is known about bundled libraries ------------------------------------------
# Assembly name (or a prefix ending in ".") -> (platform, area). Platform is
# "any" for libraries that run here as they are (they guard their own
# platform code), "native" for ones that need a native library the host can
# supply, "check" for ones that may or may not work here (listed, not
# counted against the plugin), or the one platform they are bound to.
LIBRARIES = {
    "Newtonsoft.Json": ("any", ""), "YamlDotNet": ("any", ""), "DotNetZip": ("any", ""),
    "Ionic.Zip": ("any", ""), "websocket-sharp": ("any", ""), "RestSharp": ("any", ""),
    "OpenAI_API": ("any", ""), "Polly": ("any", ""), "LoupedeckShared": ("any", ""), "NLog": ("any", ""), "Serilog": ("any", ""),
    "Serilog.": ("any", ""), "HtmlAgilityPack": ("any", ""), "MQTTnet": ("any", ""),
    "Websocket.Client": ("any", ""), "Octokit": ("any", ""), "Google.Protobuf": ("any", ""),
    "BouncyCastle.Crypto": ("any", ""), "Microsoft.Bcl.": ("any", ""), "Microsoft.Extensions.": ("any", ""),
    "Microsoft.CSharp": ("any", ""), "Microsoft.IdentityModel.": ("any", ""), "System.": ("any", ""),
    "TwitchLib.": ("any", ""), "Discord.": ("any", ""), "SocketIOClient": ("any", ""),
    "SocketIO.": ("any", ""), "Jint": ("any", ""), "ICSharpCode.SharpZipLib": ("any", ""),
    "CommandLine": ("any", ""), "Humanizer": ("any", ""), "AngleSharp": ("any", ""),
    "SkiaSharp": ("native", "drawing"), "HarfBuzzSharp": ("native", "drawing"),
    "SQLitePCLRaw.": ("native", "storage"), "Microsoft.Data.Sqlite": ("native", "storage"),
    "LibVLCSharp": ("native", "media"),
    # Microsoft's System.Drawing, when merged into a plugin: its drawing goes
    # through gdiplus (libgdiplus here), but it also calls gdi32 and user32.
    # Referenced normally, it is Mono's own and fine.
    "System.Drawing": ("check", "drawing"),
    # Logitech's telemetry, in plugins built from the current template. Its
    # native half is not there; Krita and VLC run without it.
    "LogiEventTracing": ("any", "tracing"),
    # svg-net itself draws through System.Drawing, which .NET 8+ does not
    # support off Windows; Svg.Custom is the fork Svg.Skia renders with Skia.
    "Svg": ("check", "drawing"), "Svg.Custom": ("any", ""), "Svg.Skia": ("any", ""),
    "Svg.Model": ("any", ""), "ShimSkiaSharp": ("any", ""), "ExCSS": ("any", ""),
    "AudioSwitcher.AudioApi": ("any", ""),
    "AudioSwitcher.AudioApi.CoreAudio": ("windows", "audio"), "NAudio.Wasapi": ("windows", "audio"),
    "NAudio.WinMM": ("windows", "audio"), "NAudio.WinForms": ("windows", "audio"),
    "CSCore": ("windows", "audio"), "InputSimulator": ("windows", "input"),
    "WindowsInput": ("windows", "input"), "H.InputSimulator": ("windows", "input"),
    "AutoHotkey.Interop": ("windows", "input"), "Interop.": ("windows", "com"),
    "Microsoft.Toolkit.Uwp.Notifications": ("windows", "notifications"),
    "Microsoft.Windows.SDK.NET": ("windows", "winrt"), "Microsoft.WindowsAPICodePack": ("windows", "shell"),
    "Vanara.": ("windows", "win32"), "PInvoke.": ("windows", "win32"),
    "LibreHardwareMonitorLib": ("windows", "hardware"), "OpenHardwareMonitorLib": ("windows", "hardware"),
    "Hardcodet.NotifyIcon.Wpf": ("windows", "ui"),
    "System.Windows.Forms": ("windows", "ui"), "PresentationFramework": ("windows", "ui"),
    "PresentationCore": ("windows", "ui"), "WindowsBase": ("windows", "ui"),
    "System.Management": ("windows", "wmi"), "System.Speech": ("windows", "speech"),
    "Xamarin.Mac": ("mac", "cocoa"), "Microsoft.macOS": ("mac", "cocoa"),
}
# Overrides the "System." prefix above for the Windows-only ones it covers.
for _n in ("System.Windows.Forms", "System.Management", "System.Speech"):
    assert LIBRARIES[_n][0] == "windows"


def library_of_namespace(ns):
    """(name, (platform, area)) for code in a namespace that belongs to a
    known library (merged into a plugin), or None. The catch-all "System."
    does not count: plugins' own namespaces never start with it, and
    framework code merged in is judged by what it calls."""
    best = ""
    for key in LIBRARIES:
        k = key.rstrip(".")
        if key == "System.":
            continue
        if (ns == k or ns.startswith(k + ".")) and len(k) > len(best):
            best = key
    return (best.rstrip("."), LIBRARIES[best]) if best else None


def library(name):
    """(platform, area) for an assembly name, or None when unknown."""
    if name in LIBRARIES:
        return LIBRARIES[name]
    best = ""
    for key in LIBRARIES:
        if key.endswith(".") and name.startswith(key) and len(key) > len(best):
            best = key
    return LIBRARIES[best] if best else None


# -- native calls ---------------------------------------------------------------------
WINDOWS_MODULES = {
    "user32", "kernel32", "ole32", "oleaut32", "shell32", "advapi32", "gdi32", "winmm",
    "dwmapi", "psapi", "ntdll", "shcore", "setupapi", "hid", "winhttp", "wininet",
    "iphlpapi", "powrprof", "uxtheme", "comctl32", "avrt", "mmdevapi", "dxva2", "wtsapi32",
    "secur32", "crypt32", "bcrypt", "ws2_32", "version", "msvcrt", "shlwapi", "winspool.drv",
    "comdlg32", "imm32", "netapi32", "userenv", "wlanapi", "kernelbase", "dbghelp",
    "audioses", "propsys", "combase", "api-ms-win-core-winrt-l1-1-0",
}
# Native libraries the hosts already have on Linux. Mono maps gdiplus to
# libgdiplus itself.
PORTABLE_MODULES = {"libc", "libdl", "libskiasharp", "libharfbuzzsharp", "e_sqlite3", "libvlc",
                    "gdiplus", "libgdiplus"}

# A module's own area, for functions no pattern below names.
MODULE_AREAS = {"gdi32": "drawing", "winspool.drv": "printing", "comdlg32": "ui", "comctl32": "ui",
                "uxtheme": "ui", "dwmapi": "windows", "winmm": "audio", "avrt": "audio",
                "mmdevapi": "audio", "audioses": "audio", "dxva2": "display", "shcore": "display",
                "advapi32": "registry", "shell32": "shell", "powrprof": "power", "hid": "devices",
                "setupapi": "devices", "wlanapi": "network", "iphlpapi": "network", "ws2_32": "network",
                "winhttp": "network", "wininet": "network", "psapi": "processes", "imm32": "input"}

# What a Linux stand-in for a function would do. First match wins.
AREAS = [
    ("input", r"^(SendInput|keybd_event|mouse_event|MapVirtualKey\w*|VkKeyScan\w*|GetAsyncKeyState|"
              r"GetKeyState|GetKeyboardState|ToUnicode\w*|GetKeyboardLayout\w*|ActivateKeyboardLayout|"
              r"RegisterHotKey|UnregisterHotKey|SetWindowsHookEx\w*|CallNextHookEx|UnhookWindowsHookEx|"
              r"GetCursorPos|SetCursorPos|BlockInput)$"),
    ("windows", r"^(GetForegroundWindow|SetForegroundWindow|FindWindow\w*|GetWindowText\w*|"
                r"GetWindowThreadProcessId|ShowWindow\w*|EnumWindows|EnumChildWindows|IsWindow\w*|"
                r"IsIconic|IsZoomed|SetWindowPos|GetWindowRect|MoveWindow|PostMessage\w*|"
                r"SendMessage\w*|GetClassName\w*|GetWindowLong\w*|SetWindowLong\w*|BringWindowToTop|"
                r"SetActiveWindow|GetActiveWindow|GetDesktopWindow|GetShellWindow|GetParent|GetWindow|"
                r"AttachThreadInput|AllowSetForegroundWindow|SwitchToThisWindow|DwmGetWindowAttribute)$"),
    ("clipboard", r"^(OpenClipboard|CloseClipboard|EmptyClipboard|GetClipboardData|"
                  r"SetClipboardData|IsClipboardFormatAvailable|RegisterClipboardFormat\w*)$"),
    ("audio", r"^(waveOut\w*|waveIn\w*|mixer\w*|PlaySound\w*|midiOut\w*|midiIn\w*|"
              r"AvSetMmThreadCharacteristics\w*|PropVariantClear|timeBeginPeriod|timeEndPeriod)$"),
    ("display", r"^(EnumDisplayMonitors|GetMonitorInfo\w*|MonitorFrom\w*|EnumDisplayDevices\w*|"
                r"EnumDisplaySettings\w*|ChangeDisplaySettings\w*|\w*MonitorBrightness\w*|"
                r"GetPhysicalMonitors\w*|\w*PhysicalMonitor\w*|GetDpiForMonitor|GetDeviceCaps|"
                r"SystemParametersInfo\w*|GetSystemMetrics)$"),
    ("processes", r"^(OpenProcess|CreateToolhelp32Snapshot|Process32\w*|QueryFullProcessImageName\w*|"
                  r"GetModuleFileNameEx\w*|EnumProcesses|TerminateProcess|GetProcessImageFileName\w*|"
                  r"NtQueryInformationProcess)$"),
    ("power", r"^(SetSuspendState|LockWorkStation|ExitWindowsEx|SetThreadExecutionState|"
              r"GetSystemPowerStatus|InitiateSystemShutdown\w*)$"),
    ("shell", r"^(ShellExecute\w*|SHGetKnownFolderPath|SHGetFolderPath\w*|SHAppBarMessage|"
              r"SHFileOperation\w*|ExtractIcon\w*|SHGetFileInfo\w*|DestroyIcon)$"),
    ("registry", r"^Reg\w+$"),
    ("loader", r"^(LoadLibrary\w*|GetProcAddress|FreeLibrary|GetModuleHandle\w*|SetDllDirectory\w*)$"),
    ("plumbing", r"^(GetLastError|CloseHandle|GetCurrentProcess\w*|GetCurrentThread\w*|"
                 r"CoInitialize\w*|CoUninitialize|CoCreateInstance|CoTaskMem\w*|"
                 r"GlobalAlloc|GlobalFree|GlobalLock|GlobalUnlock|LocalFree|RtlMoveMemory|"
                 r"FormatMessage\w*|Sleep|QueryPerformance\w*|GetTickCount\w*)$"),
]
_AREA_RES = [(a, re.compile(p, re.IGNORECASE)) for a, p in AREAS]

# COM interfaces, by the name a library gives them.
COM_AREAS = [
    ("audio", r"Audio|MMDevice|Endpoint|Volume|Session|Topology|IPart$|IConnector|ISubunit|"
              r"IControl|IPropertyStore|IKsControl|IPolicyConfig"),
    ("shell", r"Shell|ITaskbar|IFileDialog|IKnownFolder|IVirtualDesktop|IApplicationView|IServiceProvider"),
    ("ui", r"IAccessible|IUIAutomation"),
]

# Framework APIs, by namespace -> area.
FRAMEWORK_AREAS = [
    ("System.Windows.Forms.SendKeys", "input"), ("System.Windows.Forms.Clipboard", "clipboard"),
    ("System.Windows.Clipboard", "clipboard"), ("System.Windows.Forms.Screen", "display"),
    ("System.Windows.Forms", "ui"), ("System.Windows", "ui"), ("Microsoft.Win32.Registry", "registry"),
    ("Microsoft.Win32", "registry"), ("System.Management", "wmi"), ("System.Speech", "speech"),
    ("Microsoft.VisualBasic", "vb"), ("Windows.", "winrt"), ("AppKit", "cocoa"), ("Foundation", "cocoa"),
    ("ObjCRuntime", "cocoa"), ("CoreGraphics", "cocoa"),
    ("System.Type::GetTypeFrom", "com"), ("System.Runtime.InteropServices.Marshal::GetActiveObject", "com"),
    ("System.Diagnostics.Process", "processes"), ("System.Environment", "paths"),
    ("OpenAI_API.Models.Model", "ai"),
]

# A shell or a platform's own tool: an action that runs one does nothing here.
SHELLS = re.compile(r"powershell|\bcmd(\.exe)?\b|\bexplorer(\.exe)?\b|rundll32|^/[ck]\s|osascript|AppleScript|tell application|"
                    r"\bopen -a\b|\bwmic\b|\bnircmd|\breg(\.exe)? (add|query)|taskkill|\.bat\b|\.ps1\b|"
                    r"\bsvcl\b|\bsoundvolumeview\b",
                    re.IGNORECASE)
# Any of those, or a bare program name, which plugins mostly use to find a
# running application (GetProcessesByName("vlc")) rather than to start one.
COMMANDS = re.compile(SHELLS.pattern + r"|\.exe\b", re.IGNORECASE)

# What Mono provides itself, for .NET Framework plugins (which run on it):
# a registry of its own (files under ~/.mono/registry), Windows Forms (shown
# through XWayland) and WindowsBase. Not WPF, not System.Speech. A plugin
# built for .NET 8/10 runs on dotnet, which has none of these off Windows.
MONO_COVERS = [
    (lambda f: f["area"] == "registry" and f["kind"] == "framework", "Mono keeps a registry of its own"),
    (lambda f: f["what"].startswith("System.Windows.Forms") or f["what"].startswith("System.Windows.Threading"),
     "Mono has Windows Forms; windows show through XWayland"),
    (lambda f: f["kind"] == "library" and f["what"] in ("System.Windows.Forms", "WindowsBase"),
     "Mono has this library"),
]
PATHS = re.compile(r"^[A-Za-z]:\\|%[A-Za-z_]+%|\\AppData\\|Program Files|HKEY_|SOFTWARE\\|"
                   r"/Applications/|/Library/|~/Library|/System/Library", re.IGNORECASE)


def _prose(text):
    """A message to the user that mentions a tool ("Path to svcl.exe is not
    set"), rather than a command line."""
    return len(text.split()) > 6 and not SHELLS.match(text.strip())


def _module(name):
    n = name.lower().replace("\\", "/").rsplit("/", 1)[-1]
    return n[:-4] if n.endswith(".dll") else n


def _platform_of_module(name, natives):
    """Which platform a native module belongs to: "windows", "mac", "linux"
    (a native library the host has), "bundled" (shipped in the package) or
    "unknown"."""
    raw = name.lower()
    m = _module(name)
    if m in WINDOWS_MODULES or m.startswith("api-ms-win-"):
        return "windows"
    if raw.startswith("/system/library/") or raw.startswith("/usr/lib/") or m in ("libobjc", "__internal") \
            or m.endswith(".dylib") or "framework" in raw:
        return "mac"
    if m in PORTABLE_MODULES:
        return "linux"
    if m in natives:
        return "bundled"
    return "unknown"


def _area(function, module=""):
    for area, rx in _AREA_RES:
        if rx.match(function):
            return area
    return MODULE_AREAS.get(_module(module), "other")


def _com_area(type_name):
    short = type_name.rsplit(".", 1)[-1]
    for area, rx in COM_AREAS:
        if re.search(rx, short):
            return area
    return "other"


def _framework_area(member):
    for prefix, area in FRAMEWORK_AREAS:
        if member.startswith(prefix):
            return area
    return "other"


# -- reading a package --------------------------------------------------------------
def _scanner():
    """(mono, PortScan.exe, bin dir), or an error string."""
    host, error = plugin_host.dotnet_host()
    if error:
        return error
    mono = shutil.which("mono")
    scan = os.path.join(os.path.dirname(host), "PortScan.exe")
    if not mono or not os.path.isfile(scan):
        return "the scanner needs Mono (mono-complete) and Mono.Cecil"
    return mono, scan, os.path.dirname(host)


def _scan_dotnet(folder):
    """PortScan's records for a folder, as lists of fields."""
    found = _scanner()
    if isinstance(found, str):
        raise RuntimeError(found)
    mono, scan, bin_dir = found
    out = subprocess.run([mono, scan, folder], capture_output=True, text=True, timeout=300,
                         env=dict(os.environ, MONO_PATH=bin_dir))
    if out.returncode != 0:
        raise RuntimeError("PortScan failed: %s" % out.stderr.strip()[-500:])
    rows = []
    for line in out.stdout.splitlines():
        rows.append([f.replace("\\t", "\t").replace("\\n", "\n").replace("\\r", "\r").replace("\\\\", "\\")
                     for f in line.split("\t")])
    return rows


def _binary_kind(path):
    """"pe", "elf", "macho" or "" from a file's first bytes."""
    try:
        with open(path, "rb") as f:
            head = f.read(4)
    except OSError:
        return ""
    if head[:2] == b"MZ":
        return "pe"
    if head == b"\x7fELF":
        return "elf"
    if head in (b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe", b"\xca\xfe\xba\xbe", b"\xfe\xed\xfa\xcf"):
        return "macho"
    return ""


def _finding(kind, area, what, platform, where="", count=1, detail=""):
    return {"kind": kind, "area": area, "what": what, "platform": platform,
            "where": where, "count": count, "detail": detail}


def _analyze_dotnet(root, entry):
    """Findings for a .NET package unpacked at root, whose plugin is entry
    (a path inside it)."""
    folder = os.path.dirname(os.path.join(root, entry))
    rows = _scan_dotnet(folder)
    entry_file = os.path.basename(entry)
    managed = {r[1] for r in rows if r[0] == "asm"}
    natives = set()
    for dirpath, _dirs, files in os.walk(folder):
        for f in files:
            rel = os.path.relpath(os.path.join(dirpath, f), folder).replace(os.sep, "/")
            if rel in managed or "__MACOSX" in rel:
                continue
            kind = _binary_kind(os.path.join(dirpath, f))
            if kind:
                natives.add(_module(f).rsplit(".", 1)[0] if kind != "pe" else _module(f))
                natives.add(_module(f))

    def lib_of(rel):
        return os.path.splitext(os.path.basename(rel))[0]

    def judged(rel):
        """A bundled library judged as a whole (None for the plugin itself
        and for libraries nobody has looked at yet)."""
        if os.path.basename(rel) == entry_file:
            return None
        return library(lib_of(rel))

    findings = []
    framework = ""
    referenced = set()
    merged = {}           # library name -> (platform, area), merged into the plugin

    def merged_into(rel, ns):
        """A known library's code inside the plugin's own file: judged as
        that library, once, instead of call by call."""
        if os.path.basename(rel) != entry_file or not ns:
            return False
        found = library_of_namespace(ns)
        if not found:
            return False
        merged[found[0]] = found[1]
        return True

    for r in rows:
        kind, rel = r[0], r[1]
        if kind == "asm" and os.path.basename(rel) == entry_file:
            framework = r[2]
        if kind == "ref":
            referenced.add(r[2])
        if kind == "bad" and os.path.basename(rel) == entry_file:
            raise RuntimeError("%s could not be read (%s)" % (entry_file, r[2]))
        known = judged(rel) if kind not in ("asm", "ref", "bad") else None
        if known is not None:
            continue          # judged below, as a library
        if kind == "pinvoke":
            module, function, calls = r[2], r[3], int(r[4])
            if merged_into(rel, r[5] if len(r) > 5 else ""):
                continue
            platform = _platform_of_module(module, natives)
            if platform == "linux":
                continue
            if platform in ("unknown", "bundled"):
                # Someone else's library (a device driver, an app's remote
                # control API): one finding for the library, not one per
                # function. Whether it exists for Linux is that vendor's.
                findings.append(_finding("vendor", "vendor", _module(module), platform, rel, calls,
                                         detail="shipped in the package" if platform == "bundled"
                                         else "expected to be installed on the machine"))
                continue
            findings.append(_finding("native", _area(function, module), "%s!%s" % (_module(module), function),
                                     platform, rel, calls))
        elif kind == "com":
            if merged_into(rel, r[2].rsplit(".", 1)[0] if "." in r[2] else ""):
                continue
            findings.append(_finding("com", _com_area(r[2]), r[2].rsplit(".", 1)[-1], "windows", rel,
                                     detail=r[3]))
        elif kind == "api":
            if merged_into(rel, r[4] if len(r) > 4 else ""):
                continue
            area = _framework_area(r[2])
            if area in ("processes", "paths"):
                continue      # portable by themselves; the strings say what they run
            if area == "ai":
                # Not tied to a platform, but to a model OpenAI retires.
                findings.append(_finding("model", "ai", r[2], "", rel, int(r[3])))
                continue
            findings.append(_finding("framework", area, r[2], "windows" if area != "cocoa" else "mac",
                                     rel, int(r[3])))
        elif kind == "string":
            if merged_into(rel, r[2].split("::")[0].rsplit(".", 1)[0]):
                continue
            text = r[3]
            if SHELLS.search(text) and not _prose(text):
                findings.append(_finding("command", "shell", text, "", rel, detail=r[2]))
            elif COMMANDS.search(text):
                findings.append(_finding("program", "processes", text, "", rel, detail=r[2]))
            elif PATHS.search(text):
                findings.append(_finding("path", "paths", text, "", rel, detail=r[2]))

    # Bundled libraries that are known, and framework assemblies referenced.
    bundled = {lib_of(r[1]) for r in rows if r[0] == "asm"} - {lib_of(entry_file)}
    for name in sorted(bundled | referenced):
        known = library(name)
        if known and known[0] not in ("any",):
            platform, area = known
            if platform == "native":
                continue      # the host supplies these (SkiaSharp and the like)
            findings.append(_finding("library", area, name, platform,
                                     "bundled" if name in bundled else "referenced"))

    for name, (platform, area) in sorted(merged.items()):
        if platform not in ("any", "native"):
            findings.append(_finding("library", area, name, platform, "merged into " + entry_file))

    # The host runs anything not built for .NET (Core) on Mono, including an
    # assembly that does not say what it was built for.
    if not framework.startswith(".NETCoreApp"):
        for f in findings:
            for covered, why in MONO_COVERS:
                if covered(f):
                    f["platform"], f["detail"] = "check", why
                    break

    apps = sorted({r[3] for r in rows if r[0] == "app" and os.path.basename(r[1]) == entry_file})
    unknown_libs = sorted(n for n in bundled if library(n) is None)
    return findings, framework, apps, unknown_libs


_NODE_HINTS = [
    (re.compile(r"""require\(\s*['"](ffi-napi|ffi|ref-napi|edge-js|winax|node-windows|windows-registry|"""
                r"""regedit|winreg|node-powershell|applescript|run-applescript|osascript|robotjs|"""
                r"""@nut-tree/nut-js|node-window-manager|active-win|loudness|win-audio|"""
                r"""node-audio-windows|macos-audio-devices)['"]"""), "library"),
    (re.compile(r"process\.platform\s*===?\s*['\"](win32|darwin)['\"]"), "platform-check"),
]


def _analyze_node(root, entry):
    """Findings for a Node plugin: platform-bound npm modules, native addons
    built for another system, and the commands it runs."""
    findings = []
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            path = os.path.join(dirpath, f)
            rel = os.path.relpath(path, root).replace(os.sep, "/")
            if "__MACOSX" in rel:
                continue
            if f.endswith(".node"):
                kind = _binary_kind(path)
                if kind in ("pe", "macho"):
                    findings.append(_finding("native", "addon", rel, "windows" if kind == "pe" else "mac", rel))
                continue
            if not f.endswith((".js", ".mjs", ".cjs")) or os.path.getsize(path) > 8 * 1024 * 1024:
                continue
            try:
                text = open(path, encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            for rx, what in _NODE_HINTS:
                for m in rx.finditer(text):
                    if what == "library":
                        mod = m.group(1)
                        mac = mod in ("applescript", "run-applescript", "osascript", "macos-audio-devices")
                        findings.append(_finding("library", "node", mod, "mac" if mac else "windows", rel))
            for m in re.finditer(r"""['"`]([^'"`\n]{0,200})['"`]""", text):
                s = m.group(1)
                if s.startswith(("http", "./", "../")):
                    continue
                if SHELLS.search(s) and not _prose(s):
                    findings.append(_finding("command", "shell", s, "", rel))
                elif COMMANDS.search(s):
                    findings.append(_finding("program", "processes", s, "", rel))
    return findings


def _merge(findings):
    """One finding per distinct thing, counts summed and places listed."""
    merged = {}
    for f in findings:
        key = (f["kind"], f["what"], f["platform"])
        if key in merged:
            m = merged[key]
            m["count"] += f["count"]
            if f["where"] and f["where"] not in m["where"].split(", "):
                m["where"] += ", " + f["where"]
        else:
            merged[key] = dict(f)
    return sorted(merged.values(), key=lambda f: (f["area"], f["kind"], f["what"]))


def _report(label, meta=None, error=""):
    meta = meta or {}
    return {"package": label, "name": meta.get("name", ""),
            "displayName": meta.get("displayName") or meta.get("name", ""),
            "version": meta.get("version", ""),
            "runtime": plugin_host.runtime_of(meta) if meta else "",
            "builds": [k[len("pluginFolder"):].lower() for k in plugin_host._DOTNET_FOLDERS if meta.get(k)],
            "framework": "", "entry": "", "apps": [], "unknownLibraries": [], "findings": [],
            "verdict": "unreadable", "error": error}


def analyze_folder(root, meta, label=""):
    """A report on a package already unpacked at root (an installed plugin,
    say): as analyze() gives for the .lplug4."""
    report = _report(label or root, meta)
    names = set()
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d != ".orig"]
        for f in files:
            names.add(os.path.relpath(os.path.join(dirpath, f), root).replace(os.sep, "/"))
    entry = plugin_host.package_entry(meta, names)
    report["entry"] = entry
    try:
        if not entry:
            raise RuntimeError("the package does not have the file it names to start")
        if report["runtime"] == "dotnet":
            findings, framework, apps, unknown = _analyze_dotnet(root, entry)
            report.update(framework=framework, apps=apps, unknownLibraries=unknown)
        else:
            findings = _analyze_node(root, entry)
        report["findings"] = _merge(findings)
    except (RuntimeError, OSError, ValueError, subprocess.TimeoutExpired) as e:
        report["error"] = str(e)
        return report
    report["verdict"] = verdict(report)
    return report


def analyze(package):
    """A report on one .lplug4: what it is, which builds it ships, what in the
    build that would run here is bound to Windows or macOS, what the rules
    below would convert, and a verdict."""
    meta, error = plugin_host.inspect_package(package)
    if error:
        return _report(package, error=error)
    tmp = tempfile.mkdtemp(prefix="plugin-port-")
    try:
        with zipfile.ZipFile(package) as zf:
            plugin_host.extract(zf, tmp)
        report = analyze_folder(tmp, meta, package)
    except (OSError, ValueError, zipfile.BadZipFile) as e:
        return _report(package, meta, str(e))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return report


# Areas that need nothing: the hosts cover them, or they are how a library
# loads its own native half.
_HARMLESS = {"loader", "plumbing"}


def blocking(report):
    """The findings that would stop the plugin or one of its actions here."""
    out = []
    for f in report["findings"]:
        if f["kind"] in ("native", "vendor", "com", "library", "framework", "command") and f["area"] not in _HARMLESS \
                and f["platform"] != "check":
            out.append(f)
    return out


# -- converting ------------------------------------------------------------------
# Stand-ins for Windows-only libraries plugins bundle: assembly name -> the
# stand-in, as dotnet/build.py builds it (under dotnet/bin/).
STAND_INS = {
    "WindowsInput": "shims/WindowsInput.dll",
    "AudioSwitcher.AudioApi.CoreAudio": "shims/AudioSwitcher.AudioApi.CoreAudio.dll",
    "AudioSwitcher.AudioApi": "shims/AudioSwitcher.AudioApi.dll",
}
# Stand-ins built on another stand-in: replacing the first replaces these
# too (the stand-in CoreAudio derives from the stand-in AudioApi's types).
COMPANIONS = {
    "AudioSwitcher.AudioApi.CoreAudio": ["AudioSwitcher.AudioApi"],
}

# Commands that only open something (a page, a folder, a file), the Windows
# or macOS way. ProcessShim (dotnet/PluginApi/Shims.cs) runs xdg-open for
# them; a plugin's Process.Start calls are pointed at it.
OPENERS = re.compile(
    r"""^\s*"?(?:[A-Za-z]:\\[^"]*\\)?cmd(?:\.exe)?"?\s+/[ck]\s+"?start\b"""
    r"""|^/[ck]\s+"?start\b"""
    r"""|^\s*"?(?:[A-Za-z]:\\[^"]*\\)?explorer(?:\.exe)?"?(?:\s+\S|$)"""
    r"""|rundll32(?:\.exe)?"?\s+url\.dll,\s*FileProtocolHandler"""
    r"""|Start-Process\s+(?:-FilePath\s+)?['"]?\w+://"""
    r"""|^open\s+(?!-a\b)\S""",
    re.IGNORECASE)

# OpenAI_API's fixed models: the request asks for the one set in the app
# instead (LoupedeckShared's OpenAi.ChatModel), so a retired model does not
# leave the plugin with nothing to talk to.
MODEL_GETTERS = ("OpenAI_API.Models.Model::get_ChatGPTTurbo", "OpenAI_API.Models.Model::get_ChatGPTTurbo0301",
                 "OpenAI_API.Models.Model::get_DavinciText")
MODEL_SOURCE = "Loupedeck.LinuxShared.OpenAi::ChatModel"

# What the app asks for, for a plugin converted that way. Written to the
# files the plugin reads when it starts (write_setting).
OPENAI_SETTINGS = [
    {"name": "openai_key", "label": "OpenAI API key", "secret": True, "placeholder": "sk-..."},
    {"name": "openai_model", "label": "OpenAI model", "secret": False, "placeholder": "gpt-4o-mini"},
]

BARE_CMD = re.compile(r"""^\s*"?(?:[A-Za-z]:\\[^"]*\\)?cmd(?:\.exe)?"?\s*$""", re.IGNORECASE)

# Where a conversion records what it did, beside the plugin.
PORT_STATE = ".port.json"


def _rule(f, report):
    """The rule that covers a finding, or ""."""
    if report.get("runtime") != "dotnet":
        return ""
    if f["kind"] == "library" and f["what"] in STAND_INS and f["where"] == "bundled":
        return "swap"
    if f["kind"] == "command" and OPENERS.search(f["what"]):
        return "process"
    if f["kind"] == "model" and f["what"] in MODEL_GETTERS:
        return "model"
    # "cmd.exe" alone, its arguments in another string ("/c start <url>"):
    # covered where the same file is seen opening things that way.
    if f["kind"] == "command" and BARE_CMD.match(f["what"]):
        files = set(f["where"].split(", "))
        if any(g["kind"] == "command" and OPENERS.search(g["what"]) and files & set(g["where"].split(", "))
               for g in report["findings"]):
            return "process"
    return ""


def remaining(report):
    """The blocking findings no rule covers yet."""
    return [f for f in blocking(report) if not _rule(f, report)]


def plan(report):
    """What converting the plugin would do: {"process": [files whose
    Process.Start calls go to ProcessShim], "swap": [libraries replaced by
    stand-ins]}."""
    out = {"process": [], "swap": [], "value": []}
    for f in report["findings"]:
        if _rule(f, report) == "model":
            for where in f["where"].split(", "):
                if where and (where, f["what"]) not in out["value"]:
                    out["value"].append((where, f["what"]))
    for f in blocking(report):
        rule = _rule(f, report)
        if rule == "process":
            for where in f["where"].split(", "):
                if where and where not in out["process"]:
                    out["process"].append(where)
        elif rule == "swap":
            for lib in [f["what"]] + COMPANIONS.get(f["what"], []):
                if lib not in out["swap"]:
                    out["swap"].append(lib)
    return out


def verdict(report):
    """"runs" (nothing bound to another platform was found), "converts"
    (bound, but every part of it is covered by a rule here), "needs"
    (stand-ins not written yet) or "unreadable"."""
    if report.get("error"):
        return "unreadable"
    if not blocking(report):
        return "runs"
    return "needs" if remaining(report) else "converts"


# -- reporting ---------------------------------------------------------------------
VERDICTS = {"runs": "runs as it is", "converts": "converts: every part listed is covered",
            "needs": "needs Linux stand-ins for what is not marked converted",
            "unreadable": "could not be read"}
RULE_NAMES = {"process": "opens with xdg-open", "swap": "Linux stand-in library",
              "model": "asks for the model set in the app"}
def describe(report):
    """A report as text, for one plugin."""
    lines = ["%s (%s)" % (report["displayName"] or os.path.basename(report["package"]), report["name"])]
    if report["error"]:
        return "\n".join(lines + ["  could not be read: %s" % report["error"]])
    lines.append("  %s plugin%s; builds: %s" % (
        report["runtime"], (", " + report["framework"]) if report["framework"] else "",
        ", ".join(report["builds"]) or "one"))
    if report["apps"]:
        lines.append("  controls: %s (it only does something where that application runs)"
                     % ", ".join(report["apps"]))
    lines.append("  verdict: %s" % VERDICTS[report["verdict"]])
    blocked = blocking(report)
    for f in blocked:
        rule = _rule(f, report)
        lines.append("    %-10s %-9s %s%s%s" % (f["area"], f["kind"], f["what"][:100],
                                                "  (x%d)" % f["count"] if f["count"] > 1 else "",
                                                "  -> converted: " + RULE_NAMES[rule] if rule else ""))
    other = [f for f in report["findings"] if f not in blocked]
    if other:
        lines.append("  also seen:")
        for f in other[:15]:
            why = ("  -- " + f["detail"]) if f["platform"] == "check" and f["detail"] else ""
            if _rule(f, report):
                why = "  -> converted: " + RULE_NAMES[_rule(f, report)]
            lines.append("    %-10s %-9s %s%s" % (f["area"], f["kind"], f["what"][:100], why))
        if len(other) > 15:
            lines.append("    ... and %d more" % (len(other) - 15))
    if report["unknownLibraries"]:
        lines.append("  libraries not judged yet: %s" % ", ".join(report["unknownLibraries"]))
    return "\n".join(lines)


def summarize(reports):
    """Across many plugins: how many each area, function and library would
    unlock. The order to write stand-ins in."""
    areas, things, verdicts = {}, {}, {}
    for r in reports:
        verdicts[r["verdict"]] = verdicts.get(r["verdict"], 0) + 1
        seen_areas, seen_things = set(), set()
        for f in remaining(r):
            seen_areas.add(f["area"])
            seen_things.add((f["area"], f["kind"], f["what"]))
        for a in seen_areas:
            areas.setdefault(a, []).append(r["name"])
        for t in seen_things:
            things.setdefault(t, []).append(r["name"])
    return {
        "plugins": len(reports),
        "verdicts": verdicts,
        "areas": sorted(([a, len(n), sorted(n)] for a, n in areas.items()), key=lambda x: -x[1]),
        "things": sorted(([a, k, w, len(n), sorted(n)] for (a, k, w), n in things.items()),
                         key=lambda x: (-x[3], x[0], x[2])),
        # What each plugin still needs, by area: a plugin is unlocked when
        # all of its areas are covered.
        "needs": sorted(([r["name"], sorted({f["area"] for f in remaining(r)})] for r in reports
                         if r["verdict"] == "needs"), key=lambda x: (len(x[1]), x[0])),
    }


def describe_summary(s):
    lines = ["%d plugins: %s" % (s["plugins"], ", ".join("%d %s" % (n, v) for v, n in sorted(s["verdicts"].items())))]
    lines.append("")
    lines.append("still to write, by how many plugins need it:")
    for area, n, names in s["areas"]:
        lines.append("  %-12s %3d  %s" % (area, n, ", ".join(names)[:110]))
    lines.append("")
    lines.append("most needed:")
    for area, kind, what, n, _names in s["things"][:40]:
        lines.append("  %3d  %-10s %-9s %s" % (n, area, kind, what))
    lines.append("")
    lines.append("what each plugin still needs:")
    for name, need in s["needs"]:
        lines.append("  %-28s %s" % (name, ", ".join(need)))
    return "\n".join(lines)


def _tools():
    """(mono, bin dir) with PortPatch and the stand-ins built, or an error."""
    found = _scanner()
    if isinstance(found, str):
        return found
    mono, _scan, bin_dir = found
    if not os.path.isfile(os.path.join(bin_dir, "PortPatch.exe")):
        return "PortPatch was not built (it needs Mono.Cecil)"
    return mono, bin_dir


def _api_for(entry_path, bin_dir):
    """Our PluginApi.dll for the runtime the plugin runs on: the .NET 10
    build for plugins built for .NET 8/10, the Mono one otherwise."""
    if plugin_host.target_framework(entry_path) == "core":
        core, error = plugin_host.dotnet_core_host()
        if not error:
            return os.path.join(os.path.dirname(core), "PluginApi.dll")
    return os.path.join(bin_dir, "PluginApi.dll")


def _keep_original(folder, rel):
    """Copy folder/rel to folder/.orig/rel, once."""
    src = os.path.join(folder, rel)
    dst = os.path.join(folder, ".orig", rel)
    if os.path.isfile(src) and not os.path.exists(dst):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)


_fingerprint = None


def fingerprint():
    """What a conversion depends on: the rules (this file) and the stand-ins
    as built. A plugin converted under another fingerprint is converted
    again (refresh), so improving a stand-in reaches plugins installed
    before. "" when the tools are not here to convert with."""
    global _fingerprint
    if _fingerprint is None:
        tools = _tools()
        if isinstance(tools, str):
            return ""
        _mono, bin_dir = tools
        h = hashlib.sha256()
        with open(os.path.abspath(__file__), "rb") as f:
            h.update(f.read())
        for name in sorted(STAND_INS):
            h.update(name.encode())
            try:
                with open(os.path.join(bin_dir, STAND_INS[name]), "rb") as f:
                    h.update(f.read())
            except OSError:
                pass
        _fingerprint = h.hexdigest()
    return _fingerprint


def stale(name):
    """Whether an installed .NET plugin needs converting (again): never
    converted (installed before conversion existed), or converted under
    other rules or stand-ins than these."""
    folder = os.path.join(plugin_host.plugins_dir(), name)
    try:
        with open(plugin_host.metadata_path(folder), encoding="utf-8") as f:
            if plugin_host.runtime_of(plugin_host.parse_metadata(f.read())) != "dotnet":
                return False
    except OSError:
        return False
    current = fingerprint()
    if not current:
        return False            # nothing to convert with; do not retry forever
    state = conversion(name)
    return state is None or state.get("fingerprint") != current


def refresh(name):
    """Convert an installed plugin again if it is stale: back to what was
    installed, then converted as it would be now. Returns its state."""
    if not stale(name):
        return conversion(name)
    if conversion(name) is not None:
        revert(name)
    return convert_installed(name)


def conversion(name):
    """What converting an installed plugin did, as convert_installed()
    recorded it, or None if it has not been converted."""
    try:
        with open(os.path.join(plugin_host.plugins_dir(), name, PORT_STATE), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def convert_installed(name):
    """Convert an installed plugin to run here, once: Process.Start calls
    that open things go to ProcessShim, bundled Windows-only libraries that
    have a stand-in are replaced by it. Originals are kept in .orig/.

    Returns {"converted": [what was done], "remaining": [what is still bound
    to Windows or macOS], "verdict": ..., "error": ""}, also saved beside the
    plugin. A plugin that needs nothing is recorded as such."""
    folder = os.path.join(plugin_host.plugins_dir(), name)
    done = conversion(name)
    if done is not None:
        return done
    state = {"converted": [], "remaining": [], "verdict": "", "error": "", "fingerprint": fingerprint()}
    try:
        with open(plugin_host.metadata_path(folder), encoding="utf-8") as f:
            meta = plugin_host.parse_metadata(f.read())
    except OSError as e:
        state["error"] = str(e)
        return state
    report = analyze_folder(folder, meta, name)
    state["verdict"] = report["verdict"]
    state["error"] = report["error"]
    if report["error"]:
        return state            # not saved: a later attempt may manage
    todo = plan(report)
    if todo["process"] or todo["swap"] or todo["value"]:
        tools = _tools()
        if isinstance(tools, str):
            state["error"] = tools
            return state
        mono, bin_dir = tools
        entry_dir = os.path.dirname(os.path.join(folder, report["entry"]))
        args = [mono, os.path.join(bin_dir, "PortPatch.exe"), folder,
                _api_for(os.path.join(folder, report["entry"]), bin_dir)]
        for rel in todo["process"]:
            args += ["--process", os.path.relpath(os.path.join(entry_dir, rel), folder)]
        for lib in todo["swap"]:
            args += ["--swap", lib, os.path.join(bin_dir, STAND_INS[lib])]
        for rel, getter in todo["value"]:
            args += ["--value", os.path.relpath(os.path.join(entry_dir, rel), folder), getter,
                     os.path.join(bin_dir, "LoupedeckShared.dll"), MODEL_SOURCE]
        out = subprocess.run(args, capture_output=True, text=True, timeout=300,
                             env=dict(os.environ, MONO_PATH=bin_dir))
        if out.returncode != 0:
            state["error"] = "PortPatch failed: %s" % out.stderr.strip()[-500:]
            return state
        for line in out.stdout.splitlines():
            kind, _, rest = line.partition("\t")
            what, _, detail = rest.partition("\t")
            if kind == "process":
                state["converted"].append("%s opens pages and files with xdg-open (%s calls)" % (what, detail))
            elif kind == "value":
                state["converted"].append("%s asks OpenAI for the model set in the app" % what)
                state["settings"] = OPENAI_SETTINGS
            elif kind == "skip":
                state["converted"].append("%s: %s" % (what, detail))
        for lib in todo["swap"]:
            for dirpath, dirs, files in os.walk(folder):
                dirs[:] = [d for d in dirs if d != ".orig"]
                for f in files:
                    if f.lower() == lib.lower() + ".dll":
                        rel = os.path.relpath(os.path.join(dirpath, f), folder)
                        _keep_original(folder, rel)
                        shutil.copy2(os.path.join(bin_dir, STAND_INS[lib]), os.path.join(folder, rel))
            state["converted"].append("%s is replaced by a Linux stand-in" % lib)
    state["remaining"] = ["%s: %s" % (f["area"], f["what"]) for f in remaining(report)]
    with open(os.path.join(folder, PORT_STATE), "w", encoding="utf-8") as f:
        json.dump(state, f, indent=1)
    return state


# -- settings a conversion asks for ------------------------------------------------
_ACCESS_FILE = "gpt-openai-access.json"
_ACTIONS_FILE = "gpt-openai-actions.json"

# What the AI Assistant offers when nothing else is set: its configuration
# came from Loupedeck's servers, which are not here. Each prompt is followed
# by the selected text.
DEFAULT_PROMPTS = [
    ("Writing", "Fix spelling and grammar",
     "Correct the spelling and grammar of the following text. Reply with the corrected text only.\n\n"),
    ("Writing", "Make it shorter",
     "Rewrite the following text to be shorter, keeping its meaning. Reply with the rewritten text only.\n\n"),
    ("Writing", "Make it formal",
     "Rewrite the following text in a formal, professional tone. Reply with the rewritten text only.\n\n"),
    ("Writing", "Make it friendly",
     "Rewrite the following text in a warm, friendly tone. Reply with the rewritten text only.\n\n"),
    ("Explain", "Summarize",
     "Summarize the following text in a few sentences.\n\n"),
    ("Explain", "Explain simply",
     "Explain the following in plain words, briefly.\n\n"),
    ("Translate", "Translate to English",
     "Translate the following text to English. Reply with the translation only.\n\n"),
    ("Code", "Explain code",
     "Explain what the following code does, briefly.\n\n"),
]


def _online_files(name):
    return os.path.join(plugin_host.data_dir(name), "online-files")


def settings(name):
    """The settings a converted plugin needs from the app, with their
    current values: [{"name", "label", "secret", "placeholder", "value"}]."""
    state = conversion(name) or {}
    wanted = state.get("settings") or []
    if not wanted:
        return []
    try:
        with open(os.path.join(_online_files(name), _ACCESS_FILE), encoding="utf-8") as f:
            access = json.load(f)
    except (OSError, ValueError):
        access = {}
    values = {"openai_key": access.get("APIKey", ""), "openai_model": access.get("Model", "")}
    return [dict(s, value=values.get(s["name"], "")) for s in wanted]


def write_setting(name, key, value):
    """Set one of settings(name), in the files the plugin reads when it
    starts (restart it after). Returns an error, or ""."""
    if key not in {s["name"] for s in OPENAI_SETTINGS}:
        return "%s has no setting %r" % (name, key)
    folder = _online_files(name)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, _ACCESS_FILE)
    try:
        with open(path, encoding="utf-8") as f:
            access = json.load(f)
    except (OSError, ValueError):
        access = {"APIKey": "", "Organization": ""}
    access["APIKey" if key == "openai_key" else "Model"] = str(value or "").strip()
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        json.dump(access, f)
    os.chmod(path + ".tmp", 0o600)        # it holds the key
    os.replace(path + ".tmp", path)
    actions = os.path.join(folder, _ACTIONS_FILE)
    if not os.path.exists(actions):
        with open(actions, "w", encoding="utf-8") as f:
            json.dump({"Actions": [{"ActionPath": group, "DisplayName": label, "Description": label,
                                    "Prompt": prompt, "Parameter": []}
                                   for group, label, prompt in DEFAULT_PROMPTS]}, f, indent=1)
    return ""


def revert(name):
    """Put a converted plugin back as it was installed. Returns an error, or ""."""
    folder = os.path.join(plugin_host.plugins_dir(), name)
    orig = os.path.join(folder, ".orig")
    if os.path.isdir(orig):
        for dirpath, _dirs, files in os.walk(orig):
            for f in files:
                src = os.path.join(dirpath, f)
                shutil.copy2(src, os.path.join(folder, os.path.relpath(src, orig)))
        shutil.rmtree(orig, ignore_errors=True)
    try:
        os.remove(os.path.join(folder, PORT_STATE))
    except OSError:
        pass
    return ""


def _packages(paths):
    for p in paths:
        if os.path.isdir(p):
            for dirpath, _dirs, files in os.walk(p):
                for f in sorted(files):
                    if f.lower().endswith(".lplug4"):
                        yield os.path.join(dirpath, f)
        else:
            yield p


def _main(argv):
    if argv[:1] in (["convert"], ["revert"], ["refresh"]) and len(argv) == 2:
        if argv[0] == "revert":
            return 1 if revert(argv[1]) else 0
        state = refresh(argv[1]) if argv[0] == "refresh" else convert_installed(argv[1])
        print(json.dumps(state, indent=1))
        return 1 if state["error"] else 0
    as_json = "--json" in argv
    paths = [a for a in argv if not a.startswith("--")]
    if not paths:
        print(__doc__.strip().split("\n\n")[1])
        return 2
    reports, seen = [], set()
    for p in _packages(paths):
        r = analyze(p)
        key = (r["name"], r.get("version", ""), r["framework"]) if r["name"] else p
        if key in seen:
            continue      # the same plugin twice (downloaded again, renamed)
        seen.add(key)
        reports.append(r)
    if as_json:
        print(json.dumps({"reports": reports, "summary": summarize(reports)}, indent=1))
        return 0
    for r in reports:
        print(describe(r))
        print()
    if len(reports) > 1:
        print(describe_summary(summarize(reports)))
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
