// Runs one Loupedeck .NET plugin for the app: `mono LoupedeckHost.exe Plugin.dll`.
// Everything happens in PluginApi.dll (Loupedeck.Host); this is the door.
static class Program
{
    static int Main(string[] args)
    {
        return Loupedeck.LinuxHost.Runner.Run(args);
    }
}
