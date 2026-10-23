"""Builds the .NET side, twice over, from the same sources:

- with Mono's compiler: PluginApi.dll (our stand-in for Logitech's),
  LoupedeckHost.exe (runs one plugin under Mono) and ApiScan.exe (what a
  plugin needs from PluginApi, and what we lack), into dotnet/bin/;
- with the .NET SDK, when it is installed: the same PluginApi and host for
  .NET 10 (dotnet/core/*.csproj, drawing with SkiaSharp), into dotnet/bin/core/.
  Plugins built for .NET 8 and 10 need this one; Mono cannot run them.

    python3 dotnet/build.py          # whatever is out of date
    python3 dotnet/build.py --check  # exit 1 if a rebuild is needed

The Mono half needs only `mcs`: the C# here stays within what it compiles.
plugin_host.py calls build_mono() / build_core() before starting a plugin, so
a source change is picked up without anyone remembering to run this.

Qt-free.
"""
import glob
import hashlib
import io
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))


def _bin_dir():
    """Beside the sources in a checkout. An installed copy usually cannot
    write there, so it builds into the user's cache instead."""
    override = os.environ.get("LOUPEDECKAPP_DOTNET_BIN")
    if override:
        return override
    if os.access(HERE, os.W_OK):
        return os.path.join(HERE, "bin")
    cache = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    return os.path.join(cache, "loupedeckapp", "dotnet-bin")


BIN = _bin_dir()

# Mono.Cecil ships with Mono; ApiScan reads plugins with it.
CECIL_GLOB = "/usr/lib/mono/gac/Mono.Cecil/0.11*/Mono.Cecil.dll"

TARGETS = [
    # (output, sources, references, kind)
    ("PluginApi.dll", ["PluginApi/*.cs"],
     ["System.Drawing", "System.Web.Extensions", "System.Net.Http"], "library"),
    ("LoupedeckHost.exe", ["LoupedeckHost/*.cs"], ["@PluginApi.dll"], "exe"),
    ("ApiScan.exe", ["tools/ApiScan.cs"], ["@cecil"], "exe"),
    ("PortScan.exe", ["tools/PortScan.cs"], ["@cecil"], "exe"),
]

# Libraries the Loupedeck software ships beside its plugins, so plugins use
# them without bundling a copy (VLC's and the AI Assistant reference
# Newtonsoft.Json 13 and carry none). The Mono host gets them here; the .NET
# 10 host through its PackageReference. (NuGet id, version, file inside the
# package, sha256 of the .nupkg, as nuget.org's catalog lists it.)
SHARED = [
    ("newtonsoft.json", "13.0.3", "lib/net45/Newtonsoft.Json.dll",
     "872fc189e638ab1056555b03aaa38f68bcb54286e221aa646eb1129babf63c77"),
]


def _shared_libs():
    """Put SHARED beside the Mono host. From the NuGet cache when the SDK
    has filled it, else from nuget.org, checked against the pinned hash.
    Returns an error string, or ""."""
    for package, version, member, sha256 in SHARED:
        out = os.path.join(BIN, os.path.basename(member))
        if os.path.isfile(out):
            continue
        cached = os.path.expanduser(os.path.join("~/.nuget/packages", package, version, member))
        if os.path.isfile(cached):
            shutil.copy2(cached, out)
            continue
        url = "https://api.nuget.org/v3-flatcontainer/%s/%s/%s.%s.nupkg" % (package, version, package, version)
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                data = r.read()
        except OSError as e:
            return "could not fetch %s %s: %s" % (package, version, e)
        if hashlib.sha256(data).hexdigest() != sha256:
            return "%s %s from nuget.org does not match its pinned hash" % (package, version)
        with zipfile.ZipFile(io.BytesIO(data)) as z, open(out + ".part", "wb") as f:
            f.write(z.read(member))
        os.replace(out + ".part", out)
    return ""


def _sources(patterns):
    out = []
    for p in patterns:
        out += sorted(glob.glob(os.path.join(HERE, p)))
    return out


def _cecil():
    found = sorted(glob.glob(CECIL_GLOB))
    return found[-1] if found else ""


def _stale(output, sources, deps):
    path = os.path.join(BIN, output)
    if not os.path.isfile(path):
        return True
    built = os.path.getmtime(path)
    return any(os.path.getmtime(s) > built for s in sources + deps)


def compiler():
    return shutil.which("mcs") or ""


def needs_build():
    for output, patterns, refs, _kind in TARGETS:
        deps = [os.path.join(BIN, r[1:]) for r in refs if r.startswith("@") and r != "@cecil"]
        if _stale(output, _sources(patterns), deps):
            return True
    if any(not os.path.isfile(os.path.join(BIN, os.path.basename(m))) for _p, _v, m, _h in SHARED):
        return True
    return bool(dotnet_sdk()) and _core_stale()


# -- .NET 10 ---------------------------------------------------------------------
CORE_BIN = os.path.join(BIN, "core")
CORE_HOST = os.path.join(CORE_BIN, "LoupedeckHost.dll")


def dotnet_sdk():
    """The dotnet command, if it has an SDK (a runtime alone cannot build)."""
    dotnet = shutil.which("dotnet")
    if not dotnet:
        return ""
    try:
        out = subprocess.run([dotnet, "--list-sdks"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return dotnet if out.stdout.strip() else ""


def _core_sources():
    return (_sources(["PluginApi/*.cs", "LoupedeckHost/*.cs"])
            + _sources(["core/*.csproj", "core/Directory.Build.props"]))


def _core_stale():
    if not os.path.isfile(CORE_HOST):
        return True
    built = os.path.getmtime(CORE_HOST)
    return any(os.path.getmtime(s) > built for s in _core_sources())


def build_core(quiet=True):
    """The .NET 10 host. Returns an error string, or "". The first build
    fetches SkiaSharp from NuGet."""
    if not _core_stale():
        return ""
    dotnet = dotnet_sdk()
    if not dotnet:
        return "the .NET SDK is not installed (sudo dnf install dotnet-sdk-10.0)"
    p = subprocess.run([dotnet, "build", os.path.join(HERE, "core", "LoupedeckHost.csproj"),
                        "-c", "Release", "-o", CORE_BIN, "-nologo", "-v", "q"],
                       capture_output=True, text=True)
    if p.returncode != 0:
        return "building the .NET host failed:\n%s%s" % (p.stdout[-4000:], p.stderr[-2000:])
    # dotnet does not touch an output it considers current; make the stamp
    # this staleness check reads say "now".
    os.utime(CORE_HOST, None)
    if not quiet:
        print("built core/LoupedeckHost.dll")
    return ""


def build(quiet=True):
    """Everything this machine can build. Returns an error string, or ""
    when at least one host built and nothing that was attempted failed."""
    errors = []
    if compiler():
        errors.append(build_mono(quiet))
    if dotnet_sdk():
        errors.append(build_core(quiet))
    if not errors:
        return "neither Mono (mono-complete) nor the .NET SDK is installed"
    return "\n".join(e for e in errors if e)


def build_mono(quiet=True):
    """Compile whatever is out of date. Returns an error string, or ""."""
    mcs = compiler()
    if not mcs:
        return "Mono's C# compiler (mcs) is not installed; install mono-complete"
    os.makedirs(BIN, exist_ok=True)
    for output, patterns, refs, kind in TARGETS:
        sources = _sources(patterns)
        deps = [os.path.join(BIN, r[1:]) for r in refs if r.startswith("@") and r != "@cecil"]
        if not _stale(output, sources, deps):
            continue
        args = [mcs, "-nologo", "-debug-", "-optimize+", "-target:" + kind,
                "-out:" + os.path.join(BIN, output)]
        for r in refs:
            if r == "@cecil":
                cecil = _cecil()
                if not cecil:
                    if output in ("ApiScan.exe", "PortScan.exe"):
                        continue   # the scanners are tools, not something plugins need
                    return "Mono.Cecil not found"
                args.append("-r:" + cecil)
                shutil.copy2(cecil, BIN)
            elif r.startswith("@"):
                args.append("-r:" + os.path.join(BIN, r[1:]))
            else:
                args.append("-r:" + r)
        p = subprocess.run(args + sources, capture_output=True, text=True)
        if p.returncode != 0:
            return "building %s failed:\n%s%s" % (output, p.stdout, p.stderr)
        if not quiet:
            print("built %s" % output)
    return _shared_libs()


if __name__ == "__main__":
    if "--check" in sys.argv:
        sys.exit(1 if needs_build() else 0)
    err = build(quiet=False)
    if err:
        print(err)
        sys.exit(1)
