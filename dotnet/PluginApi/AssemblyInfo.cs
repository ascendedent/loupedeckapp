// Plugins ask for PluginApi by name with whatever version they were built
// against (2.0.0.0 for the Loupedeck 5 generation, 5.x and 6.x since). A
// version above all of them satisfies .NET's "at least this version" check.
using System.Reflection;

[assembly: AssemblyTitle("PluginApi (loupedeckapp)")]
[assembly: AssemblyVersion("99.0.0.0")]
