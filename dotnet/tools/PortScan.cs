// What ties a Loupedeck .NET plugin to Windows or macOS.
//
//   mono PortScan.exe <unpacked package folder>
//
// Reads every assembly in the folder (the plugin and whatever it bundles) and
// prints one tab-separated record per finding, for plugin_port.py to judge:
//
//   asm      file  target-framework
//   bad      file  why it could not be read (a native library, usually)
//   ref      file  assembly  version            what it references
//   pinvoke  file  module  entry  call-sites  namespace   calls into native code
//   api      file  Type::Member  call-sites  namespace    platform-bound framework APIs
//   com      file  Type  guid                   COM interfaces it declares
//   string   file  Type::Method  literal        commands, paths, registry keys
//   app      file  Type::Method  literal        the application it controls
//
// The namespace is the declaring one for a P/Invoke and the caller's for an
// API: a plugin that merged libraries into itself (ILMerge, Costura) still
// shows whose code it is.
//
// Metadata only, through Mono.Cecil: nothing of the plugin runs. A bundled
// PluginApi.dll is Logitech's and is skipped, never opened.
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.RegularExpressions;
using Mono.Cecil;
using Mono.Cecil.Cil;

static class PortScan
{
    // Namespaces whose use binds a plugin to one platform, or is worth
    // knowing about when porting (processes, the registry, COM).
    static readonly string[] Watched = {
        "System.Windows.Forms", "System.Windows", "System.Management", "System.Speech",
        "Microsoft.Win32", "Microsoft.VisualBasic", "Windows.", "AppKit", "Foundation",
        "ObjCRuntime", "CoreGraphics", "System.Runtime.InteropServices.ComTypes",
    };

    // Members outside those namespaces that matter just as much.
    static readonly string[] WatchedMembers = {
        "System.Diagnostics.Process::Start", "System.Diagnostics.ProcessStartInfo::.ctor",
        "System.Diagnostics.Process::GetProcessesByName",
        "System.Runtime.InteropServices.Marshal::GetActiveObject",
        "System.Environment::GetFolderPath", "System.Environment::ExpandEnvironmentVariables",
        "System.Type::GetTypeFromCLSID", "System.Type::GetTypeFromProgID",
        // A fixed OpenAI model, which OpenAI retires in time (plugin_port
        // points it at the one set in the app).
        "OpenAI_API.Models.Model::get_ChatGPTTurbo", "OpenAI_API.Models.Model::get_ChatGPTTurbo0301",
        "OpenAI_API.Models.Model::get_DavinciText",
    };

    // Literals worth showing: executables, shells, scripting, paths, keys.
    static readonly Regex Interesting = new Regex(
        @"\.exe\b|\.bat\b|\.ps1\b|powershell|\bcmd\b|osascript|AppleScript|tell application|" +
        @"[A-Za-z]:\\|%[A-Za-z]+%|\\\\|HKEY_|SOFTWARE\\|/Applications/|/Library/|/System/|" +
        @"~/|\bopen -a\b|\.app\b|\bwmic\b|\bnircmd\b|^/[ck]\s",
        RegexOptions.IgnoreCase);

    static string Clean(string s)
    {
        return s.Replace("\\", "\\\\").Replace("\t", "\\t").Replace("\r", "\\r").Replace("\n", "\\n");
    }

    static void Emit(params object[] fields)
    {
        Console.WriteLine(string.Join("\t", fields.Select(f => Clean(Convert.ToString(f)))));
    }

    static string Owner(TypeReference t)
    {
        while (t is TypeSpecification) t = ((TypeSpecification)t).ElementType;
        return t.FullName;
    }

    // A nested type has no namespace of its own; its outermost one does.
    static string Namespace(TypeReference t)
    {
        while (t.IsNested) t = t.DeclaringType;
        return t.Namespace;
    }

    static bool IsWatched(MemberReference m)
    {
        var owner = Owner(m.DeclaringType);
        var key = owner + "::" + m.Name;
        if (WatchedMembers.Any(w => key == w)) return true;
        var ns = owner;
        return Watched.Any(w => ns.StartsWith(w.EndsWith(".") ? w : w + ".", StringComparison.Ordinal)
                                || (ns.LastIndexOf('.') > 0 && ns.Substring(0, ns.LastIndexOf('.')) == w));
    }

    static void Scan(string root, string path)
    {
        var rel = path.Substring(root.Length).TrimStart(Path.DirectorySeparatorChar);
        ModuleDefinition module;
        try { module = ModuleDefinition.ReadModule(path); }
        catch (Exception ex) { Emit("bad", rel, ex.GetType().Name); return; }

        var tfm = module.Assembly == null ? "" : module.Assembly.CustomAttributes
            .Where(a => a.AttributeType.Name == "TargetFrameworkAttribute" && a.ConstructorArguments.Count > 0)
            .Select(a => (string)a.ConstructorArguments[0].Value).FirstOrDefault();
        Emit("asm", rel, tfm ?? "");

        foreach (var r in module.AssemblyReferences)
            Emit("ref", rel, r.Name, r.Version);

        var calls = new Dictionary<string, int>();
        var types = module.GetTypes().ToList();
        foreach (var t in types)
        {
            foreach (var md in t.Methods)
            {
                if (!md.HasBody) continue;
                var where = t.FullName + "::" + md.Name;
                var app = md.Name == "GetProcessName" || md.Name == "GetBundleName"
                          || md.Name == "GetProcessNames" || md.Name == "GetBundleNames";
                foreach (var ins in md.Body.Instructions)
                {
                    var s = ins.Operand as string;
                    if (s != null && ins.OpCode == OpCodes.Ldstr)
                    {
                        if (app && s.Length > 0) Emit("app", rel, where, s);
                        else if (Interesting.IsMatch(s)) Emit("string", rel, where, s);
                        continue;
                    }
                    var m = ins.Operand as MethodReference;
                    if (m == null) continue;
                    var resolved = m as MethodDefinition;
                    string key = null;
                    if (resolved != null && resolved.IsPInvokeImpl && resolved.PInvokeInfo != null)
                        key = "pinvoke\t" + resolved.PInvokeInfo.Module.Name + "\t" +
                              (resolved.PInvokeInfo.EntryPoint ?? resolved.Name) + "\t" +
                              Namespace(resolved.DeclaringType);
                    else if (resolved == null && IsWatched(m))
                        key = "api\t" + Owner(m.DeclaringType) + "::" + m.Name + "\t" + Namespace(t);
                    if (key == null) continue;
                    int n;
                    calls[key] = calls.TryGetValue(key, out n) ? n + 1 : 1;
                }
            }
            // [ComImport], or an interface given a COM identity (Guid plus
            // InterfaceType), which is how AudioSwitcher declares Windows'.
            var attrs = t.CustomAttributes.Select(a => a.AttributeType.Name).ToList();
            if (t.IsImport || attrs.Contains("ComImportAttribute")
                || (t.IsInterface && attrs.Contains("GuidAttribute") && attrs.Contains("InterfaceTypeAttribute")))
            {
                var guid = t.CustomAttributes.Where(a => a.AttributeType.Name == "GuidAttribute")
                    .Select(a => a.ConstructorArguments[0].Value as string).FirstOrDefault();
                Emit("com", rel, t.FullName, guid ?? "");
            }
        }

        // Declared but never called still counts: it may be called through a
        // delegate, and it says what the library was written against.
        foreach (var t in types)
            foreach (var md in t.Methods.Where(x => x.IsPInvokeImpl && x.PInvokeInfo != null))
            {
                var key = "pinvoke\t" + md.PInvokeInfo.Module.Name + "\t" + (md.PInvokeInfo.EntryPoint ?? md.Name) +
                          "\t" + Namespace(t);
                if (!calls.ContainsKey(key)) calls[key] = 0;
            }

        foreach (var kv in calls.OrderBy(k => k.Key))
        {
            var parts = kv.Key.Split('\t');
            if (parts[0] == "pinvoke") Emit("pinvoke", rel, parts[1], parts[2], kv.Value, parts[3]);
            else Emit("api", rel, parts[1], kv.Value, parts[2]);
        }
    }

    static int Main(string[] args)
    {
        if (args.Length != 1 || !Directory.Exists(args[0]))
        {
            Console.Error.WriteLine("usage: PortScan.exe <unpacked package folder>");
            return 2;
        }
        var root = Path.GetFullPath(args[0]).TrimEnd(Path.DirectorySeparatorChar);
        var files = Directory.GetFiles(root, "*.*", SearchOption.AllDirectories)
            .Where(f => f.EndsWith(".dll", StringComparison.OrdinalIgnoreCase)
                        || f.EndsWith(".exe", StringComparison.OrdinalIgnoreCase))
            .Where(f => !f.Contains(Path.DirectorySeparatorChar + "__MACOSX" + Path.DirectorySeparatorChar))
            // Originals kept by PortPatch: the plugin as it was, not as it runs.
            .Where(f => !f.Substring(root.Length).StartsWith(Path.DirectorySeparatorChar + ".orig" + Path.DirectorySeparatorChar))
            .Where(f => !string.Equals(Path.GetFileName(f), "PluginApi.dll", StringComparison.OrdinalIgnoreCase))
            .OrderBy(f => f, StringComparer.Ordinal);
        foreach (var f in files) Scan(root, f);
        return 0;
    }
}
