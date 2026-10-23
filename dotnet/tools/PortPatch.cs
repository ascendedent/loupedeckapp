// Converts a Windows or macOS Loupedeck plugin to run here, in place.
//
//   mono PortPatch.exe <plugin folder> <our PluginApi.dll> [operations]
//
//   --process <file>          calls to Process.Start in <file> go to our
//                             ProcessShim, which opens URLs and files with
//                             xdg-open where the plugin used cmd, explorer,
//                             rundll32 or open
//   --swap <assembly> <dll>   every assembly in the folder that references
//                             <assembly> references the stand-in <dll>
//                             instead (its version, no strong name);
//                             plugin_port.py puts the stand-in in place
//
// Each file changed is first copied to <folder>/.orig/, once, so the
// original can be put back. Prints one line per change:
//
//   process  file  call-sites
//   swap     file  assembly
//   skip     file  why
//
// Plugin_port.py decides which operations a plugin needs. Mono.Cecil edits
// metadata and IL; nothing of the plugin runs.
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Mono.Cecil;
using Mono.Cecil.Cil;

static class PortPatch
{
    const string ShimType = "Loupedeck.LinuxHost.ProcessShim";

    static string _root;

    static void Backup(string path)
    {
        var rel = path.Substring(_root.Length).TrimStart(Path.DirectorySeparatorChar);
        var copy = Path.Combine(_root, ".orig", rel);
        if (File.Exists(copy)) return;
        Directory.CreateDirectory(Path.GetDirectoryName(copy));
        File.Copy(path, copy);
    }

    static string Rel(string path) { return path.Substring(_root.Length).TrimStart(Path.DirectorySeparatorChar); }

    static ModuleDefinition Read(string path)
    {
        var resolver = new DefaultAssemblyResolver();
        resolver.AddSearchDirectory(Path.GetDirectoryName(path));
        return ModuleDefinition.ReadModule(path, new ReaderParameters { InMemory = true, AssemblyResolver = resolver });
    }

    static void Write(ModuleDefinition module, string path)
    {
        Backup(path);
        module.Write(path);
    }

    static string Sig(MethodReference m)
    {
        return string.Join(",", m.Parameters.Select(p => p.ParameterType.FullName));
    }

    // The plugin's own reference to an assembly called name, made the scope
    // of a type we imported, so the plugin keeps one reference to it.
    static void Rescope(ModuleDefinition module, TypeReference imported, string name)
    {
        var refs = module.AssemblyReferences.Where(r => r.Name == name).ToList();
        if (refs.Count < 2) return;
        var keep = refs[0];
        foreach (var extra in refs.Skip(1))
        {
            foreach (var t in module.GetTypeReferences().Where(t => t.Scope == extra)) t.Scope = keep;
            if (imported.Scope == extra) imported.Scope = keep;
            module.AssemblyReferences.Remove(extra);
        }
    }

    static void Process(string path, ModuleDefinition api)
    {
        var shim = api.GetType(ShimType);
        if (shim == null) { Console.WriteLine("skip\t{0}\tour PluginApi has no {1}", Rel(path), ShimType); return; }
        var module = Read(path);
        var count = 0;
        foreach (var type in module.GetTypes())
            foreach (var method in type.Methods.Where(m => m.HasBody))
                foreach (var ins in method.Body.Instructions)
                {
                    var m = ins.Operand as MethodReference;
                    if (m == null || m.Name != "Start" || m.DeclaringType.FullName != "System.Diagnostics.Process")
                        continue;
                    // An instance Start() becomes a static Start(Process).
                    var wanted = m.HasThis ? "System.Diagnostics.Process" : Sig(m);
                    var target = shim.Methods.FirstOrDefault(x => x.Name == "Start" && x.IsStatic && Sig(x) == wanted);
                    if (target == null)
                    {
                        Console.WriteLine("skip\t{0}\tno stand-in for Process.Start({1})", Rel(path), Sig(m));
                        continue;
                    }
                    var imported = module.ImportReference(target);
                    Rescope(module, imported.DeclaringType, api.Assembly.Name.Name);
                    ins.OpCode = OpCodes.Call;
                    ins.Operand = imported;
                    count++;
                }
        if (count == 0) { Console.WriteLine("skip\t{0}\tno Process.Start to redirect", Rel(path)); return; }
        Write(module, path);
        Console.WriteLine("process\t{0}\t{1}", Rel(path), count);
    }

    static void Swap(string name, string shimPath)
    {
        var shim = ModuleDefinition.ReadModule(shimPath).Assembly.Name;
        var files = Directory.GetFiles(_root, "*.*", SearchOption.AllDirectories)
            .Where(f => (f.EndsWith(".dll", StringComparison.OrdinalIgnoreCase) || f.EndsWith(".exe", StringComparison.OrdinalIgnoreCase))
                        && !Rel(f).StartsWith(".orig" + Path.DirectorySeparatorChar)
                        && !string.Equals(Path.GetFileNameWithoutExtension(f), name, StringComparison.OrdinalIgnoreCase)
                        && !string.Equals(Path.GetFileName(f), "PluginApi.dll", StringComparison.OrdinalIgnoreCase));
        foreach (var f in files)
        {
            ModuleDefinition module;
            try { module = Read(f); }
            catch (BadImageFormatException) { continue; }   // a native library
            var refs = module.AssemblyReferences.Where(r => r.Name == name).ToList();
            if (refs.Count == 0) continue;
            foreach (var r in refs)
            {
                r.Version = shim.Version;
                r.PublicKeyToken = new byte[0];
                r.PublicKey = null;
                r.HasPublicKey = false;
            }
            Write(module, f);
            Console.WriteLine("swap\t{0}\t{1}", Rel(f), name);
        }
    }

    static int Main(string[] args)
    {
        if (args.Length < 2 || !Directory.Exists(args[0]))
        {
            Console.Error.WriteLine("usage: PortPatch.exe <plugin folder> <PluginApi.dll> [--process <file>] [--swap <assembly> <dll>]");
            return 2;
        }
        _root = Path.GetFullPath(args[0]).TrimEnd(Path.DirectorySeparatorChar);
        var api = ModuleDefinition.ReadModule(args[1]);
        for (var i = 2; i < args.Length; i++)
        {
            if (args[i] == "--process" && i + 1 < args.Length)
                Process(Path.Combine(_root, args[++i]), api);
            else if (args[i] == "--swap" && i + 2 < args.Length)
            {
                Swap(args[i + 1], args[i + 2]);
                i += 2;
            }
            else
            {
                Console.Error.WriteLine("unknown operation " + args[i]);
                return 2;
            }
        }
        return 0;
    }
}
