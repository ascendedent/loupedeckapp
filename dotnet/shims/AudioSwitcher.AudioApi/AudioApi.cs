// A Linux stand-in for AudioSwitcher.AudioApi, the device model under the
// AudioSwitcher library (AudioSwitcher.AudioApi.CoreAudio is its Windows
// implementation). Plugins that control volume bundle both; plugin_port.py
// replaces both, so the stand-in CoreAudio (backed by PipeWire through
// pactl) can derive from this.
//
// Written from the library's public shape as plugins reference it (VolumeControl:
// devices by type and state; name, volume and mute; set volume, mute and the
// default device). The enums keep the original's values, which plugins
// compile in as numbers.
using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Threading.Tasks;

[assembly: AssemblyVersion("4.0.0.308")]
[assembly: AssemblyTitle("AudioSwitcher.AudioApi (Linux stand-in)")]

namespace AudioSwitcher.AudioApi
{
    [Flags]
    public enum DeviceType
    {
        Playback = 1,
        Capture = 2,
        All = 3,
    }

    [Flags]
    public enum DeviceState
    {
        Active = 1,
        Disabled = 2,
        NotPresent = 4,
        Unplugged = 8,
        All = 15,
    }

    public interface IDevice
    {
        Guid Id { get; }
        String Name { get; }
        String InterfaceName { get; }
        String FullName { get; }
        DeviceType DeviceType { get; }
        DeviceState State { get; }
        Boolean IsDefaultDevice { get; }
        Boolean IsDefaultCommunicationsDevice { get; }
        Boolean IsPlaybackDevice { get; }
        Boolean IsCaptureDevice { get; }
        Boolean IsMuted { get; }
        Double Volume { get; set; }
        Task<Double> SetVolumeAsync(Double volume);
        Task<Boolean> SetMuteAsync(Boolean mute);
        Task<Boolean> ToggleMuteAsync();
        Boolean SetAsDefault();
        Task<Boolean> SetAsDefaultAsync();
        Boolean SetAsDefaultCommunications();
        Task<Boolean> SetAsDefaultCommunicationsAsync();
    }

    public abstract class Device : IDevice
    {
        public abstract Guid Id { get; }
        public abstract String Name { get; }
        public abstract String InterfaceName { get; }
        public abstract String FullName { get; }
        public abstract DeviceType DeviceType { get; }
        public abstract DeviceState State { get; }
        public abstract Boolean IsDefaultDevice { get; }
        public abstract Boolean IsDefaultCommunicationsDevice { get; }
        public abstract Boolean IsMuted { get; }
        public abstract Double Volume { get; set; }

        public virtual Boolean IsPlaybackDevice { get { return (this.DeviceType & DeviceType.Playback) != 0; } }

        public virtual Boolean IsCaptureDevice { get { return (this.DeviceType & DeviceType.Capture) != 0; } }

        public abstract Task<Double> SetVolumeAsync(Double volume);

        public abstract Task<Boolean> SetMuteAsync(Boolean mute);

        public virtual Task<Boolean> ToggleMuteAsync() { return this.SetMuteAsync(!this.IsMuted); }

        public abstract Boolean SetAsDefault();

        public virtual Task<Boolean> SetAsDefaultAsync() { return Task.FromResult(this.SetAsDefault()); }

        public abstract Boolean SetAsDefaultCommunications();

        public virtual Task<Boolean> SetAsDefaultCommunicationsAsync() { return Task.FromResult(this.SetAsDefaultCommunications()); }

        public override String ToString() { return this.FullName; }
    }

    public abstract class AudioController
    {
        public abstract IDevice DefaultPlaybackDevice { get; }

        public abstract IDevice DefaultCaptureDevice { get; }
    }

    public abstract class AudioController<T> : AudioController where T : IDevice
    {
        public virtual IEnumerable<T> GetDevices() { return this.GetDevices(DeviceType.All, DeviceState.All); }

        public virtual IEnumerable<T> GetDevices(DeviceType deviceType) { return this.GetDevices(deviceType, DeviceState.All); }

        public virtual IEnumerable<T> GetDevices(DeviceState state) { return this.GetDevices(DeviceType.All, state); }

        public abstract IEnumerable<T> GetDevices(DeviceType deviceType, DeviceState state);

        public virtual IEnumerable<T> GetPlaybackDevices() { return this.GetDevices(DeviceType.Playback, DeviceState.All); }

        public virtual IEnumerable<T> GetPlaybackDevices(DeviceState state) { return this.GetDevices(DeviceType.Playback, state); }

        public virtual IEnumerable<T> GetCaptureDevices() { return this.GetDevices(DeviceType.Capture, DeviceState.All); }

        public virtual IEnumerable<T> GetCaptureDevices(DeviceState state) { return this.GetDevices(DeviceType.Capture, state); }

        public virtual T GetDevice(Guid id) { return this.GetDevices().FirstOrDefault(d => d.Id == id); }
    }
}
