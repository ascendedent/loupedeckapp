// Static helpers plugins call: embedded resources, small utilities, JSON.
namespace Loupedeck
{
    using System;
    using System.Collections.Generic;
    using System.IO;
    using System.Linq;
    using System.Net;
    using System.Net.Sockets;
    using System.Reflection;
    using System.Text;
    using System.Text.RegularExpressions;

    // Resources compiled into the plugin. Names are the manifest names
    // ("Loupedeck.MyPlugin.Images.Icon.png"); a bare file name finds the one
    // resource that ends with it.
    public static class AssemblyExtensions
    {
        public static String[] GetFilesInFolder(this Assembly assembly, String folderName)
        {
            var prefix = "." + folderName.Trim('.', '/', '\\').Replace('/', '.').Replace('\\', '.') + ".";
            return assembly.GetManifestResourceNames().Where(n => n.Contains(prefix)).ToArray();
        }

        public static String FindFile(this Assembly assembly, String fileName)
        {
            var names = assembly.GetManifestResourceNames();
            if (names.Contains(fileName)) return fileName;
            var suffix = "." + fileName.Replace('/', '.').Replace('\\', '.');
            return names.FirstOrDefault(n => n.EndsWith(suffix, StringComparison.OrdinalIgnoreCase));
        }

        public static String FindFileOrThrow(this Assembly assembly, String fileName)
        {
            var name = assembly.FindFile(fileName);
            if (name == null) throw new FileNotFoundException("Embedded resource not found", fileName);
            return name;
        }

        public static String[] FindFiles(this Assembly assembly, String regexPattern)
        {
            var re = new Regex(regexPattern);
            return assembly.GetManifestResourceNames().Where(n => re.IsMatch(n)).ToArray();
        }

        public static Stream GetStream(this Assembly assembly, String resourceName)
        {
            var name = assembly.FindFile(resourceName) ?? resourceName;
            return assembly.GetManifestResourceStream(name);
        }

        public static Byte[] ReadBinaryFile(this Assembly assembly, String resourceName)
        {
            using (var s = assembly.GetStream(resourceName))
            {
                if (s == null) return null;
                using (var ms = new MemoryStream())
                {
                    s.CopyTo(ms);
                    return ms.ToArray();
                }
            }
        }

        public static String ReadTextFile(this Assembly assembly, String resourceName)
        {
            var bytes = assembly.ReadBinaryFile(resourceName);
            return bytes == null ? null : Encoding.UTF8.GetString(bytes);
        }

        public static BitmapImage ReadImage(this Assembly assembly, String resourceName)
        {
            return BitmapImage.FromArray(assembly.ReadBinaryFile(resourceName));
        }

        public static void ExtractFile(this Assembly assembly, String resourceName, String filePathName)
        {
            File.WriteAllBytes(filePathName, assembly.ReadBinaryFile(resourceName));
        }

        // Every resource under a folder, as files in a directory. Returns the
        // directory (inferred: Krita uses it and the result's shape is not
        // documented).
        public static String ExtractFileToDirectory(this Assembly assembly, String resourceName, String directory)
        {
            Directory.CreateDirectory(directory);
            var name = assembly.FindFile(resourceName) ?? resourceName;
            var fileName = Path.GetFileName(resourceName.Replace('/', Path.DirectorySeparatorChar));
            var path = Path.Combine(directory, fileName);
            assembly.ExtractFile(name, path);
            return path;
        }
    }

    // The same, for the plugin being hosted, without naming its assembly.
    public static class EmbeddedResources
    {
        private static Assembly Plugin { get { return Host.Service.PluginAssembly; } }

        public static String[] GetFilesInFolder(String folderName) { return Plugin.GetFilesInFolder(folderName); }
        public static String FindFile(String fileName) { return Plugin.FindFile(fileName); }
        public static String FindFileOrThrow(String fileName) { return Plugin.FindFileOrThrow(fileName); }
        public static String[] FindFiles(String regexPattern) { return Plugin.FindFiles(regexPattern); }
        public static Stream GetStream(String resourceName) { return Plugin.GetStream(resourceName); }
        public static Byte[] ReadBinaryFile(String resourceName) { return Plugin.ReadBinaryFile(resourceName); }
        public static String ReadTextFile(String resourceName) { return Plugin.ReadTextFile(resourceName); }
        public static BitmapImage ReadImage(String resourceName) { return Plugin.ReadImage(resourceName); }
        public static void ExtractFile(String resourceName, String filePathName) { Plugin.ExtractFile(resourceName, filePathName); }
    }

    public static class Helpers
    {
        public static Boolean IsWindows() { return Environment.OSVersion.Platform == PlatformID.Win32NT; }

        public static Boolean IsMacintosh() { return false; }

        public static Boolean IsLinux() { return !IsWindows(); }

        // Plugins check this against the version they need; this host means
        // to be current.
        public static Version LoupedeckSoftwareVersion { get { return new Version(6, 0, 0); } }

        public static Boolean IsDebugBuild() { return false; }

        // Run something and report whether it threw, rather than throwing.
        public static Boolean TryExecuteAction(Action action)
        {
            try { action(); return true; }
            catch (Exception ex) { Host.Service.Log("action failed: " + ex.Message); return false; }
        }

        public static Boolean TryExecuteSafe(Action action) { return TryExecuteAction(action); }

        public static Boolean TryExecuteFunc<T>(Func<T> func, out T result)
        {
            try { result = func(); return true; }
            catch (Exception ex) { Host.Service.Log("function failed: " + ex.Message); result = default(T); return false; }
        }

        // Raise an event on the thread pool, so the caller does not wait on
        // whoever is listening.
        public static void BeginInvoke<T>(EventHandler<T> handler, Object sender, T args)
        {
            if (handler == null) return;
            System.Threading.ThreadPool.QueueUserWorkItem(_ =>
            {
                try { handler(sender, args); }
                catch (Exception ex) { Host.Service.Log("event handler failed: " + ex.Message); }
            });
        }

        public static String GetPluginDataDirectory() { return Host.Service.DataDirectory; }

        public static Boolean IsMac() { return false; }

        // Plugins take their non-Windows branch here, which is usually the
        // macOS one: "open -b <bundle>" and the like. Start what can be
        // started; xdg-open stands in for open.
        public static Boolean StartProcess(String fileName, String arguments, Boolean waitForExit)
        {
            if (!StartProcess(fileName, arguments)) return false;
            return true;
        }

        public static Boolean StartProcess(String fileName, String arguments)
        {
            try
            {
                if (fileName == "open") fileName = "xdg-open";
                System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo(fileName, arguments ?? "")
                {
                    UseShellExecute = false,
                });
                return true;
            }
            catch (Exception ex)
            {
                Host.Service.Log("could not start " + fileName + ": " + ex.Message);
                return false;
            }
        }
    }

    public static class ObjectExtensions
    {
        // Returns its argument, so it can be used inline.
        public static T CheckNullArgument<T>(this T argument, String argumentName)
        {
            if (argument == null) throw new ArgumentNullException(argumentName);
            return argument;
        }
    }

    public static class IoHelpers
    {
        public static Boolean EnsureDirectoryExists(String path)
        {
            try { Directory.CreateDirectory(path); return true; }
            catch (Exception) { return false; }
        }

        public static Boolean EnsureFileDirectoryExists(String filePath)
        {
            var dir = Path.GetDirectoryName(filePath);
            return String.IsNullOrEmpty(dir) || EnsureDirectoryExists(dir);
        }

        public static Boolean FileExists(String path) { return File.Exists(path); }

        public static Boolean DirectoryExists(String path) { return Directory.Exists(path); }
    }

    // Diagnostic traces, message first (unlike PluginLogFile).
    public static class Tracer
    {
        public static void Trace(String text) { Host.Service.Log("trace " + text); }
        public static void Trace(String text, Exception ex) { Host.Service.Log("trace " + text + " | " + ex.Message); }
        public static void Warning(String text) { Host.Service.Log("warning " + text); }
        public static void Warning(String text, Exception ex) { Host.Service.Log("warning " + text + " | " + ex.Message); }
        public static void Error(String text) { Host.Service.Log("error " + text); }
        public static void Error(String text, Exception ex) { Host.Service.Log("error " + text + " | " + ex.Message); }
    }

    public static class StringExtensions
    {
        public static Boolean EqualsNoCase(this String a, String b)
        {
            return String.Equals(a, b, StringComparison.OrdinalIgnoreCase);
        }

        public static Boolean ContainsNoCase(this String a, String b)
        {
            return a != null && b != null && a.IndexOf(b, StringComparison.OrdinalIgnoreCase) >= 0;
        }

        public static Boolean StartsWithNoCase(this String a, String b)
        {
            return a != null && b != null && a.StartsWith(b, StringComparison.OrdinalIgnoreCase);
        }

        public static Boolean EndsWithNoCase(this String a, String b)
        {
            return a != null && b != null && a.EndsWith(b, StringComparison.OrdinalIgnoreCase);
        }

        public static Boolean IsNullOrEmpty(this String s) { return String.IsNullOrEmpty(s); }

        public static readonly StringComparer StringComparerNoCase = StringComparer.OrdinalIgnoreCase;

        public static Boolean TryGetEnumValue<T>(this String s, out T value) where T : struct
        {
            return Enum.TryParse(s, true, out value);
        }

        public static String[] Split(this String s, String separator)
        {
            return s == null ? new String[0] : s.Split(new[] { separator }, StringSplitOptions.None);
        }

        public static Double ParseDouble(this String s)
        {
            return Double.Parse(s, System.Globalization.CultureInfo.InvariantCulture);
        }

        public static Int32 ParseInt32(this String s)
        {
            return Int32.Parse(s, System.Globalization.CultureInfo.InvariantCulture);
        }

        public static Boolean IsNullOrWhiteSpace(this String s) { return String.IsNullOrWhiteSpace(s); }
    }

    // JSON through the runtime's own serializer. Plugins that need
    // Newtonsoft's attributes bring Newtonsoft with them, as Twitch does.
    public static class JsonHelpers
    {
        public static String SerializeObject(Object obj) { return Host.Json.Serialize(obj); }

        public static T DeserializeObject<T>(String json) { return Host.Json.Deserialize<T>(json); }

        public static T DeserializeAnyObject<T>(String json) { return Host.Json.Deserialize<T>(json); }

        public static T DeserializeAnyObjectFromFile<T>(String filePath)
        {
            return Host.Json.Deserialize<T>(File.ReadAllText(filePath));
        }

        public static void SerializeAnyObjectToFile(Object obj, String filePath)
        {
            File.WriteAllText(filePath, Host.Json.Serialize(obj));
        }

        public static Boolean TryDeserializeAnyObject<T>(String json, out T obj)
        {
            try { obj = Host.Json.Deserialize<T>(json); return obj != null; }
            catch (Exception) { obj = default(T); return false; }
        }

        public static Boolean TrySerializeAnyObject(Object obj, out String json)
        {
            try { json = Host.Json.Serialize(obj); return true; }
            catch (Exception) { json = null; return false; }
        }
    }

    public static class NetworkHelpers
    {
        // The first port in the list nothing is listening on.
        public static Boolean TryGetFreeTcpPort(IEnumerable<Int32> ports, out Int32 port)
        {
            foreach (var p in ports)
            {
                TcpListener l = null;
                try
                {
                    l = new TcpListener(IPAddress.Loopback, p);
                    l.Start();
                    port = p;
                    return true;
                }
                catch (SocketException) { }
                finally { if (l != null) l.Stop(); }
            }
            port = 0;
            return false;
        }

        public static Boolean TryGetFreeTcpPort(out Int32 port)
        {
            var l = new TcpListener(IPAddress.Loopback, 0);
            l.Start();
            port = ((IPEndPoint)l.LocalEndpoint).Port;
            l.Stop();
            return true;
        }
    }
}

namespace Loupedeck
{
    using System;
    using System.Collections.Generic;

    // Dictionaries keyed by strings that ignore case.
    public class DictionaryNoCase<T> : Dictionary<String, T>
    {
        public DictionaryNoCase() : base(StringComparer.OrdinalIgnoreCase) { }

        public DictionaryNoCase(IDictionary<String, T> values)
            : base(values ?? new Dictionary<String, T>(), StringComparer.OrdinalIgnoreCase) { }

        public T GetValue(String key, T defaultValue)
        {
            T v;
            return key != null && this.TryGetValue(key, out v) ? v : defaultValue;
        }
    }

    public class StringDictionaryNoCase : DictionaryNoCase<String>
    {
        public StringDictionaryNoCase() { }

        public StringDictionaryNoCase(IDictionary<String, String> values) : base(values) { }
    }

    // Keys through the app's input backend, as ClientApplication sends them.
    public class KeyboardApi
    {
        internal KeyboardApi() { }

        public Boolean SendShortcut(VirtualKeyCode virtualKeyCode, ModifierKey modifiers)
        {
            return this.SendShortcut(virtualKeyCode, modifiers, 0);
        }

        // The last argument is a delay; keys go out at once here.
        public Boolean SendShortcut(VirtualKeyCode virtualKeyCode, ModifierKey modifiers, Int32 delay)
        {
            var combo = Keys.Combo(virtualKeyCode, modifiers);
            if (combo == null) return false;
            Host.Service.SendKeys(combo);
            return true;
        }
    }

    public static class LinqExtensions
    {
        public static Int32 IndexOf<T>(this IEnumerable<T> items, Func<T, Boolean> predicate)
        {
            var i = 0;
            foreach (var item in items)
            {
                if (predicate(item)) return i;
                i++;
            }
            return -1;
        }
    }

    // A key and its modifiers, as written in a setting: "Control+Shift+KeyM".
    public class KeyboardKey
    {
        public KeyboardKey(VirtualKeyCode virtualKeyCode, ModifierKey modifierKey)
        {
            this.VirtualKeyCode = virtualKeyCode;
            this.ModifierKey = modifierKey;
        }

        public VirtualKeyCode VirtualKeyCode { get; private set; }

        public ModifierKey ModifierKey { get; private set; }

        public override String ToString()
        {
            var parts = new List<String>();
            foreach (ModifierKey m in new[] { ModifierKey.Control, ModifierKey.Alt, ModifierKey.Shift, ModifierKey.Windows })
                if ((this.ModifierKey & m) != 0) parts.Add(m.ToString());
            parts.Add(this.VirtualKeyCode.ToString());
            return String.Join("+", parts);
        }
    }

    public static class KeyboardExtensions
    {
        public static ModifierKey GetModifierKey(this String name)
        {
            switch ((name ?? "").Trim().ToLowerInvariant())
            {
                case "control": case "ctrl": case "controlorcommand": return ModifierKey.Control;
                case "alt": case "altoroption": case "option": return ModifierKey.Alt;
                case "shift": return ModifierKey.Shift;
                case "windows": case "win": case "command": case "cmd": return ModifierKey.Windows;
                default: return ModifierKey.None;
            }
        }

        public static KeyboardKey GetKeyboardKey(this String text)
        {
            KeyboardKey key;
            return text.TryParseKeyboardKey(out key) ? key : null;
        }

        public static Boolean TryParseKeyboardKey(this String text, out KeyboardKey key)
        {
            key = null;
            if (String.IsNullOrWhiteSpace(text)) return false;
            var modifiers = ModifierKey.None;
            VirtualKeyCode code = VirtualKeyCode.None;
            foreach (var raw in text.Split('+'))
            {
                var part = raw.Trim();
                var m = part.GetModifierKey();
                if (m != ModifierKey.None) { modifiers |= m; continue; }
                VirtualKeyCode parsed;
                if (Enum.TryParse(part, true, out parsed)) { code = parsed; continue; }
                if (part.Length == 1 && Char.IsLetterOrDigit(part[0])
                    && Enum.TryParse("Key" + Char.ToUpperInvariant(part[0]), out parsed)) { code = parsed; continue; }
                return false;
            }
            if (code == VirtualKeyCode.None) return false;
            key = new KeyboardKey(code, modifiers);
            return true;
        }
    }
}
