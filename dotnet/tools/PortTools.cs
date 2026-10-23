// The three tools in one program, for machines with the .NET SDK and no
// Mono: `dotnet PortTools.dll api|scan|patch <their arguments>`. Mono builds
// each as its own .exe instead (dotnet/build.py); the sources are the same.
using System;
using System.Linq;

static class PortTools
{
    static int Main(string[] args)
    {
        var rest = args.Skip(1).ToArray();
        switch (args.Length > 0 ? args[0] : "")
        {
            case "api": return ApiScan.Main(rest);
            case "scan": return PortScan.Main(rest);
            case "patch": return PortPatch.Main(rest);
            default:
                Console.Error.WriteLine("usage: PortTools.dll api|scan|patch <arguments>");
                return 2;
        }
    }
}
