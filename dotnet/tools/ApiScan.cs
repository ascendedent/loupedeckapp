// What a Loupedeck .NET plugin needs from PluginApi.
//
//   mono ApiScan.exe Plugin.dll [PluginApi.dll]
//
// Lists every PluginApi type and member the plugin references, and every
// virtual it overrides in a class derived from a PluginApi type. Given our
// PluginApi.dll as well, it marks each one we do not provide yet, which makes
// it the checklist for supporting a new plugin.
//
// Reads metadata with Mono.Cecil, which never resolves references, so it works
// on a plugin whose PluginApi is nowhere on this machine.
using System;
using System.Collections.Generic;
using System.Linq;
using Mono.Cecil;

static class ApiScan
{
    const string Api = "PluginApi";

    static bool FromApi(TypeReference t)
    {
        while (t is TypeSpecification)
            t = ((TypeSpecification)t).ElementType;
        if (t.IsNested)
            return FromApi(t.DeclaringType);
        var a = t.Scope as AssemblyNameReference;
        return a != null && a.Name == Api;
    }

    static string Key(MemberReference m)
    {
        var t = m.DeclaringType;
        while (t is TypeSpecification) t = ((TypeSpecification)t).ElementType;
        var owner = t.FullName;
        var mr = m as MethodReference;
        if (mr != null)
            return owner + "::" + mr.Name + "(" +
                string.Join(", ", mr.Parameters.Select(p => TypeKey(p.ParameterType))) + ")";
        return owner + "::" + m.Name;
    }

    // A generic method's parameter is "!!0" where it is referenced and "T"
    // where it is defined; both become !!<position> so they compare equal.
    static string TypeKey(TypeReference t)
    {
        var gp = t as GenericParameter;
        if (gp != null) return (gp.Type == GenericParameterType.Method ? "!!" : "!") + gp.Position;
        var spec = t as TypeSpecification;
        if (spec != null && !(t is GenericInstanceType))
            return TypeKey(spec.ElementType) + (t.IsByReference ? "&" : (t.IsArray ? "[]" : "*"));
        return t.Name;
    }

    // The full shape, for writing a matching declaration.
    static string Sig(MethodReference m)
    {
        return (m.HasThis ? "" : "static ") + m.ReturnType.FullName + " " + m.Name + "(" +
            string.Join(", ", m.Parameters.Select(p =>
                p.ParameterType.FullName + (string.IsNullOrEmpty(p.Name) ? "" : " " + p.Name))) + ")";
    }

    static int Main(string[] args)
    {
        if (args.Length < 1) {
            Console.Error.WriteLine("usage: ApiScan.exe Plugin.dll [PluginApi.dll]");
            return 2;
        }
        var module = ModuleDefinition.ReadModule(args[0]);
        HashSet<string> have = null;
        if (args.Length > 1 && args[1] != "" && args[1] != "--full") {
            var ours = ModuleDefinition.ReadModule(args[1]);
            have = new HashSet<string>();
            foreach (var t in ours.GetTypes()) {
                have.Add(t.FullName);
                foreach (var m in t.Methods) have.Add(Key(m));
                foreach (var f in t.Fields) have.Add(Key(f));
            }
        }
        Func<string, string> Mark = k => have == null ? "" : (have.Contains(k) ? "  " : "! ");

        var types = module.GetTypeReferences().Where(FromApi)
            .Select(t => t.FullName).Distinct().OrderBy(x => x).ToList();
        Console.WriteLine("# types ({0})", types.Count);
        foreach (var t in types) Console.WriteLine(Mark(t) + t);

        var refs = module.GetMemberReferences().Where(m => FromApi(m.DeclaringType)).ToList();
        var members = refs.Select(Key).Distinct().OrderBy(x => x).ToList();
        Console.WriteLine("# members called ({0})", members.Count);
        foreach (var m in members) Console.WriteLine(Mark(m) + m);
        if (args.Contains("--full")) {
            Console.WriteLine("# member signatures");
            foreach (var line in refs.Select(r => {
                    var o = r.DeclaringType; while (o is TypeSpecification) o = ((TypeSpecification)o).ElementType;
                    var mr = r as MethodReference;
                    return o.FullName + " :: " + (mr != null ? Sig(mr) : r.Name);
                }).Distinct().OrderBy(x => x))
                Console.WriteLine(line);
        }

        Console.WriteLine("# overrides");
        foreach (var t in module.GetTypes()) {
            var b = t.BaseType;
            if (b == null || !FromApi(b)) continue;
            Console.WriteLine("{0} : {1}", t.FullName, b.FullName);
            foreach (var m in t.Methods.Where(m => m.IsVirtual && !m.IsNewSlot).OrderBy(m => m.Name))
                Console.WriteLine("    {0}{1}", m.IsFamily ? "protected " : (m.IsPublic ? "public " : "internal "), Sig(m));
        }
        return 0;
    }
}
