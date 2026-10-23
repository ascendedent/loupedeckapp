// A Linux stand-in for AudioSwitcher.AudioApi.CoreAudio, which reaches
// Windows' audio endpoints through COM. Here the devices are PipeWire's (or
// PulseAudio's) sinks and sources, read and set with pactl: playback devices
// are sinks, capture devices are sources other than sinks' monitors.
//
// pactl runs with LC_ALL=C so its labels ("Description:", "Mute:") read the
// same in every language. Volume is 0-100 as in the original. Linux has one
// default device per direction, so "default communications device" is the
// same one.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
using Loupedeck.LinuxHost;

[assembly: AssemblyVersion("4.0.0.308")]
[assembly: AssemblyTitle("AudioSwitcher.AudioApi.CoreAudio (Linux stand-in, pactl)")]

namespace AudioSwitcher.AudioApi.CoreAudio
{
    internal static class Pactl
    {
        internal static String Run(params String[] args)
        {
            try
            {
                var info = new ProcessStartInfo("pactl", String.Join(" ", args.Select(Quote)))
                {
                    UseShellExecute = false,
                    RedirectStandardOutput = true,
                    RedirectStandardError = true,
                };
                info.EnvironmentVariables["LC_ALL"] = "C";
                using (var p = Process.Start(info))
                {
                    var output = p.StandardOutput.ReadToEnd();
                    p.WaitForExit(5000);
                    return p.ExitCode == 0 ? output : null;
                }
            }
            catch (Exception ex)
            {
                Input.Log("AudioSwitcher: pactl failed: " + ex.Message);
                return null;
            }
        }

        private static String Quote(String a) { return a.IndexOf(' ') < 0 ? a : "\"" + a + "\""; }

        // "Sink #3" / "Source #5" blocks, as name -> field -> value.
        internal static List<Dictionary<String, String>> List(String kind)
        {
            var blocks = new List<Dictionary<String, String>>();
            var text = Run("list", kind);
            if (text == null) return blocks;
            Dictionary<String, String> current = null;
            foreach (var raw in text.Split('\n'))
            {
                if (raw.Length > 0 && !Char.IsWhiteSpace(raw[0]))
                {
                    current = new Dictionary<String, String>();
                    blocks.Add(current);
                    continue;
                }
                var line = raw.Trim();
                var colon = line.IndexOf(':');
                if (current == null || colon <= 0 || raw.StartsWith("\t\t")) continue;
                var key = line.Substring(0, colon);
                if (!current.ContainsKey(key)) current[key] = line.Substring(colon + 1).Trim();
            }
            return blocks;
        }

        internal static Double Percent(String volumeLine)
        {
            var m = Regex.Match(volumeLine ?? "", @"(\d+)%");
            return m.Success ? Double.Parse(m.Groups[1].Value) : 0;
        }
    }

    public class CoreAudioDevice : Device
    {
        private readonly String _kind;      // "sink" or "source"
        private readonly String _name;
        private readonly String _description;
        private readonly Guid _id;
        private Double _volume;
        private Boolean _muted;
        private DateTime _read = DateTime.MinValue;

        internal CoreAudioDevice(String kind, Dictionary<String, String> fields)
        {
            this._kind = kind;
            this._name = fields.ContainsKey("Name") ? fields["Name"] : "";
            this._description = fields.ContainsKey("Description") ? fields["Description"] : this._name;
            this._volume = Pactl.Percent(fields.ContainsKey("Volume") ? fields["Volume"] : "");
            this._muted = fields.ContainsKey("Mute") && fields["Mute"] == "yes";
            this._read = DateTime.UtcNow;
            using (var md5 = MD5.Create())
                this._id = new Guid(md5.ComputeHash(Encoding.UTF8.GetBytes(kind + ":" + this._name)));
        }

        // PipeWire's name for it ("alsa_output.usb-...analog-stereo").
        public String RealId { get { return this._name; } }

        public override Guid Id { get { return this._id; } }

        public override String Name { get { return this._description; } }

        public override String InterfaceName { get { return this._description; } }

        public override String FullName { get { return this._description; } }

        public override DeviceType DeviceType { get { return this._kind == "sink" ? DeviceType.Playback : DeviceType.Capture; } }

        public override DeviceState State { get { return DeviceState.Active; } }

        public override Boolean IsDefaultDevice
        {
            get
            {
                var d = Pactl.Run("get-default-" + this._kind);
                return d != null && d.Trim() == this._name;
            }
        }

        public override Boolean IsDefaultCommunicationsDevice { get { return this.IsDefaultDevice; } }

        // Read again when asked, at most a few times a second: plugins keep
        // device objects and poll them.
        private void Refresh()
        {
            if ((DateTime.UtcNow - this._read).TotalMilliseconds < 250) return;
            this._read = DateTime.UtcNow;
            var v = Pactl.Run("get-" + this._kind + "-volume", this._name);
            if (v != null) this._volume = Pactl.Percent(v);
            var m = Pactl.Run("get-" + this._kind + "-mute", this._name);
            if (m != null) this._muted = m.Contains("yes");
        }

        public override Boolean IsMuted
        {
            get
            {
                this.Refresh();
                return this._muted;
            }
        }

        public override Double Volume
        {
            get
            {
                this.Refresh();
                return this._volume;
            }
            set { this.SetVolumeAsync(value).Wait(); }
        }

        public override Task<Double> SetVolumeAsync(Double volume)
        {
            var v = Math.Max(0, Math.Min(100, volume));
            if (Pactl.Run("set-" + this._kind + "-volume", this._name, ((Int32)Math.Round(v)) + "%") != null)
            {
                this._volume = v;
                this._read = DateTime.UtcNow;
            }
            return Task.FromResult(this._volume);
        }

        public override Task<Boolean> SetMuteAsync(Boolean mute)
        {
            if (Pactl.Run("set-" + this._kind + "-mute", this._name, mute ? "1" : "0") != null)
            {
                this._muted = mute;
                this._read = DateTime.UtcNow;
            }
            return Task.FromResult(this._muted);
        }

        public override Boolean SetAsDefault()
        {
            return Pactl.Run("set-default-" + this._kind, this._name) != null;
        }

        public override Boolean SetAsDefaultCommunications() { return this.SetAsDefault(); }
    }

    public class CoreAudioController : AudioController<CoreAudioDevice>, IDisposable
    {
        public CoreAudioController() { }

        public override IEnumerable<CoreAudioDevice> GetDevices(DeviceType deviceType, DeviceState state)
        {
            var devices = new List<CoreAudioDevice>();
            if ((state & DeviceState.Active) == 0) return devices;     // only present devices are listed
            if ((deviceType & DeviceType.Playback) != 0)
                devices.AddRange(Pactl.List("sinks").Select(f => new CoreAudioDevice("sink", f)));
            if ((deviceType & DeviceType.Capture) != 0)
                devices.AddRange(Pactl.List("sources")
                    .Where(f => !(f.ContainsKey("Monitor of Sink") && f["Monitor of Sink"] != "n/a"))
                    .Select(f => new CoreAudioDevice("source", f)));
            Input.Log("AudioSwitcher: " + devices.Count + " " + deviceType + " devices from pactl");
            return devices;
        }

        private CoreAudioDevice Default(String kind)
        {
            var name = Pactl.Run("get-default-" + kind);
            if (name == null) return null;
            return this.GetDevices(kind == "sink" ? DeviceType.Playback : DeviceType.Capture, DeviceState.Active)
                .FirstOrDefault(d => d.RealId == name.Trim());
        }

        public override IDevice DefaultPlaybackDevice { get { return this.Default("sink"); } }

        public override IDevice DefaultCaptureDevice { get { return this.Default("source"); } }

        public CoreAudioDevice DefaultPlaybackCommunicationsDevice { get { return this.Default("sink"); } }

        public CoreAudioDevice DefaultCaptureCommunicationsDevice { get { return this.Default("source"); } }

        public void Dispose() { }
    }
}
