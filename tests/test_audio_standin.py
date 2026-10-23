"""The AudioSwitcher stand-in (dotnet/shims/AudioSwitcher.*): Windows' audio
endpoints, as plugins like VolumeControl use them, backed by PipeWire through
pactl.

A small program is compiled against the stand-ins and run with a fake pactl
on PATH (tests/fake_pactl.py: two speakers, a microphone and a monitor), so
nothing touches the real audio. Listing, volume, mute and default devices
have to come back right, and every change has to reach pactl as the command
that makes it. Skipped where Mono is not installed.
"""
import os
import shutil
import subprocess
import sys
import tempfile

from _harness import Checks, REPO

tmp = tempfile.mkdtemp()
os.environ["LOUPEDECKAPP_CONFIG_DIR"] = os.path.join(tmp, "config")

import plugin_host as ph                                          # noqa: E402
import plugin_port as pp                                          # noqa: E402

c = Checks()

# -- the analyzer replaces both halves together --------------------------------------
report = {"runtime": "dotnet", "error": "", "findings": [
    {"kind": "library", "area": "audio", "what": "AudioSwitcher.AudioApi.CoreAudio",
     "platform": "windows", "where": "bundled", "count": 1, "detail": ""}]}
c.eq("CoreAudio is covered", pp.verdict(report), "converts")
c.eq("and replacing it replaces the AudioApi it builds on",
     pp.plan(report)["swap"], ["AudioSwitcher.AudioApi.CoreAudio", "AudioSwitcher.AudioApi"])

if not (shutil.which("mono") and shutil.which("mcs")):
    print("%-58s %s" % ("the audio stand-in (Mono is not installed)", "skipped"))
    raise SystemExit(c.done())

host, error = ph.dotnet_host()
c.eq("the stand-ins build", error, "")
if error:
    raise SystemExit(c.done())
bin_dir = os.path.dirname(host)
shims = os.path.join(bin_dir, "shims")

fake_bin = os.path.join(tmp, "bin")
os.makedirs(fake_bin)
with open(os.path.join(fake_bin, "pactl"), "w") as f:
    f.write("#!/bin/sh\nexec '%s' '%s' \"$@\"\n" % (sys.executable, os.path.join(REPO, "tests", "fake_pactl.py")))
os.chmod(os.path.join(fake_bin, "pactl"), 0o755)
state = os.path.join(tmp, "pactl.json")
log = os.path.join(tmp, "pactl.log")

PROBE = r"""
using System;
using System.Linq;
using AudioSwitcher.AudioApi;
using AudioSwitcher.AudioApi.CoreAudio;

class Probe
{
    static void Main()
    {
        var c = new CoreAudioController();
        foreach (var d in c.GetDevices(DeviceType.All, DeviceState.Active))
            Console.WriteLine("device|" + d.DeviceType + "|" + d.FullName + "|" + d.RealId + "|" + d.Volume + "|" + d.IsMuted
                              + "|" + d.IsDefaultDevice + "|" + d.IsPlaybackDevice + "|" + d.IsCaptureDevice);
        Console.WriteLine("disabled|" + c.GetDevices(DeviceType.All, DeviceState.Disabled).Count());
        var headset = c.GetDevices(DeviceType.Playback, DeviceState.Active).First(d => d.Name == "Headset");
        Console.WriteLine("setvolume|" + headset.SetVolumeAsync(42).Result + "|" + headset.Volume);
        Console.WriteLine("setmute|" + headset.SetMuteAsync(false).Result + "|" + headset.IsMuted);
        Console.WriteLine("default|" + headset.SetAsDefaultAsync().Result + "|" + headset.IsDefaultDevice
                          + "|" + c.DefaultPlaybackDevice.Name);
        var mic = c.GetDevices(DeviceType.Capture, DeviceState.Active).First();
        Console.WriteLine("comms|" + mic.SetAsDefaultCommunicationsAsync().Result + "|" + mic.IsDefaultCommunicationsDevice);
        Console.WriteLine("clamp|" + headset.SetVolumeAsync(150).Result);
    }
}
"""
src = os.path.join(tmp, "Probe.cs")
exe = os.path.join(tmp, "Probe.exe")
with open(src, "w") as f:
    f.write(PROBE)
p = subprocess.run(["mcs", "-nologo", "-out:" + exe,
                    "-r:" + os.path.join(shims, "AudioSwitcher.AudioApi.dll"),
                    "-r:" + os.path.join(shims, "AudioSwitcher.AudioApi.CoreAudio.dll"),
                    "-r:" + os.path.join(bin_dir, "PluginApi.dll"), src], capture_output=True, text=True)
c.eq("a program using the stand-ins compiles", p.returncode, 0)
if p.returncode:
    print(p.stdout, p.stderr)
    raise SystemExit(c.done())

env = dict(os.environ, PATH=fake_bin + os.pathsep + os.environ["PATH"],
           MONO_PATH=os.pathsep.join([bin_dir, shims]), FAKE_PACTL_STATE=state, FAKE_PACTL_LOG=log)
run = subprocess.run(["mono", exe], capture_output=True, text=True, env=env, timeout=60)
c.eq("it runs", run.returncode, 0)
if run.returncode:
    print(run.stdout, run.stderr)
lines = {}
for line in run.stdout.splitlines():
    kind, _, rest = line.partition("|")
    lines.setdefault(kind, []).append(rest.split("|"))

c.eq("playback devices are the sinks, capture the sources but not monitors",
     [(d[0], d[1], d[2]) for d in lines.get("device", [])],
     [("Playback", "Speakers", "alsa_output.speakers"), ("Playback", "Headset", "alsa_output.headset"),
      ("Capture", "Microphone", "alsa_input.mic")])
c.eq("with their volume, mute and default as pactl says",
     [(d[3], d[4], d[5]) for d in lines.get("device", [])],
     [("65", "False", "True"), ("30", "True", "False"), ("80", "False", "True")])
c.eq("and which way they go", [(d[6], d[7]) for d in lines.get("device", [])],
     [("True", "False"), ("True", "False"), ("False", "True")])
c.eq("devices that are not present are not invented", lines.get("disabled"), [["0"]])
c.eq("volume is set, and reads back", lines.get("setvolume"), [["42", "42"]])
c.eq("mute is set", lines.get("setmute"), [["False", "False"]])
c.eq("the default device is set", lines.get("default"), [["True", "True", "Headset"]])
c.eq("communications default is the default here", lines.get("comms"), [["True", "True"]])
c.eq("volume is kept within 0-100", lines.get("clamp"), [["100"]])
with open(log) as f:
    changes = f.read().splitlines()
c.eq("each change reached pactl as the command that makes it", changes,
     ["set-sink-volume alsa_output.headset 42%", "set-sink-mute alsa_output.headset 0",
      "set-default-sink alsa_output.headset", "set-default-source alsa_input.mic",
      "set-sink-volume alsa_output.headset 100%"])

shutil.rmtree(tmp, ignore_errors=True)
raise SystemExit(c.done())
