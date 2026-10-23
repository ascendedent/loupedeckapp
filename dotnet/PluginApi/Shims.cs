// Stand-ins for what Windows and macOS plugins reach for that Linux does not
// have. A converted plugin calls these instead (plugin_port.py rewrites the
// call sites with dotnet/tools/PortPatch.cs), and stand-in libraries such as
// dotnet/shims/WindowsInput send their keys through Input.
//
// Nothing here is from Logitech's API: these are ours, public only so that
// patched plugins and stand-in libraries can reach them.
namespace Loupedeck.LinuxHost
{
    using System;
    using System.Collections.Generic;
    using System.Diagnostics;
    using System.IO;
    using System.Text;
    using System.Text.RegularExpressions;

    // Keys, text and the wheel, through the app's input backend.
    public static class Input
    {
        // The app's name for a Win32 virtual-key code ("ctrl", "a", "f5"), or
        // null when it has none.
        public static String KeyName(Int32 virtualKey) { return Keys.Name(virtualKey); }

        // "ctrl+shift+a", as the app writes a hotkey.
        public static void SendKeys(String combo)
        {
            if (!String.IsNullOrEmpty(combo)) Host.Service.SendKeys(combo);
        }

        public static void SendText(String text)
        {
            if (!String.IsNullOrEmpty(text)) Host.Service.SendText(text);
        }

        // Positive clicks scroll up, negative down.
        public static void Scroll(Int32 clicks) { Host.Service.SendScroll(clicks, false); }

        // Positive clicks scroll right, negative left.
        public static void ScrollHorizontally(Int32 clicks) { Host.Service.SendScroll(clicks, true); }

        public static void Log(String text) { Host.Service.Log(text); }
    }

    // Process.Start, for plugins that open a page or a file the Windows or
    // macOS way: "cmd /c start <url>", "explorer <url>", "rundll32
    // url.dll,FileProtocolHandler <url>", "open <url>", or a URL handed to
    // the shell. Those become xdg-open. Anything else runs as it would have.
    //
    // A plugin may also register a URL protocol of its own in the registry
    // (Weather registers "weather:", whose command is "cmd /c START
    // https://weather.com/") and then open "weather:...". Windows runs the
    // registered command; so does this, translated the same way. Mono keeps
    // the registry the plugin wrote to (MONO_REGISTRY_PATH, per plugin).
    public static class ProcessShim
    {
        public static Process Start(String fileName)
        {
            return Process.Start(Translate(new ProcessStartInfo(fileName) { UseShellExecute = true }));
        }

        public static Process Start(String fileName, String arguments)
        {
            return Process.Start(Translate(new ProcessStartInfo(fileName, arguments ?? "") { UseShellExecute = true }));
        }

        public static Process Start(ProcessStartInfo startInfo)
        {
            return Process.Start(Translate(startInfo));
        }

        // process.Start(), redirected here with the process first.
        public static Boolean Start(Process process)
        {
            Translate(process.StartInfo);
            return process.Start();
        }

        // Rewrites startInfo in place when it is one of the forms above, and
        // returns it.
        public static ProcessStartInfo Translate(ProcessStartInfo startInfo)
        {
            var target = Opens(startInfo.FileName ?? "", startInfo.Arguments ?? "", startInfo.UseShellExecute);
            if (target == null) return startInfo;
            Host.Service.Log("opening " + target + " with xdg-open (the plugin ran " +
                             (startInfo.FileName + " " + startInfo.Arguments).Trim() + ")");
            startInfo.FileName = "xdg-open";
            startInfo.Arguments = Quote(target);
            startInfo.UseShellExecute = false;
            return startInfo;
        }

        // What a command opens, or null when it is not a way of opening
        // something.
        internal static String Opens(String fileName, String arguments, Boolean shellExecute)
        {
            var file = fileName.Trim();
            var args = arguments.Trim();
            // A whole command line in the file name ("\"C:\\...\\cmd.exe\" /c ...").
            if (args.Length == 0 && (file.StartsWith("\"") || Regex.IsMatch(file, @"^\S+\.exe\s", RegexOptions.IgnoreCase)))
            {
                var whole = file;
                if (Split(whole).Count > 1)
                {
                    file = Split(whole)[0];
                    args = Rest(whole, 1);
                }
            }
            var name = Path.GetFileName(Unquote(file).Replace('\\', '/')).ToLowerInvariant();
            if (name.EndsWith(".exe")) name = name.Substring(0, name.Length - 4);
            var words = Split(args);

            if (name == "cmd" && words.Count > 1 && (Is(words[0], "/c") || Is(words[0], "/k")))
            {
                // cmd strips quotes around the whole command: /c "start x".
                var rest = Unquote(Rest(args, 1));
                var inner = Split(rest);
                if (inner.Count > 0 && Is(inner[0], "start"))
                {
                    // start ["title"] <target>: a quoted first word is a title
                    // when something follows it.
                    var skip = 1;
                    if (inner.Count > 2 && Rest(rest, 1).TrimStart().StartsWith("\"")) skip = 2;
                    return inner.Count > skip ? Unquote(Rest(rest, skip)) : null;
                }
                return inner.Count > 0 ? Opens(inner[0], Rest(rest, 1), false) : null;
            }
            if ((name == "explorer" || name == "open") && words.Count > 0 && !words[0].StartsWith("-"))
                return Unquote(args);
            if (name == "rundll32" && args.IndexOf("FileProtocolHandler", StringComparison.OrdinalIgnoreCase) >= 0)
                return Unquote(args.Substring(args.IndexOf("FileProtocolHandler", StringComparison.OrdinalIgnoreCase)
                                              + "FileProtocolHandler".Length).Trim());
            if ((name == "powershell" || name == "pwsh") && words.Count > 0)
            {
                var m = Regex.Match(args, @"Start-Process\s+(?:-FilePath\s+)?(['""]?)(\w+://[^'""\s]+)\1", RegexOptions.IgnoreCase);
                if (m.Success) return m.Groups[2].Value;
            }
            // A URL, or a document, handed to the shell to open.
            if (shellExecute && args.Length == 0)
            {
                var registered = Registered(file);
                if (registered != null)
                {
                    var target = Opens(registered, "", false);
                    if (target != null) return target;
                }
                if (IsUrl(file)) return file;
            }
            return null;
        }

        // The command a URL protocol is registered to run for url, with %1
        // filled in, or null.
        private static String Registered(String url)
        {
            var m = Regex.Match(url, @"^([A-Za-z][A-Za-z0-9+.-]+):");
            if (!m.Success || Regex.IsMatch(m.Groups[1].Value, "^(https?|file|mailto|ftp)$", RegexOptions.IgnoreCase))
                return null;
            try
            {
                using (var key = Microsoft.Win32.Registry.ClassesRoot.OpenSubKey(m.Groups[1].Value + @"\shell\open\command"))
                {
                    var command = key == null ? null : key.GetValue("") as String;
                    return command == null ? null : command.Replace("%1", url);
                }
            }
            catch (Exception)
            {
                return null;     // no registry here (.NET on Linux), or none readable
            }
        }

        private static Boolean IsUrl(String s) { return Regex.IsMatch(s, @"^[A-Za-z][A-Za-z0-9+.-]*://\S+$|^mailto:\S+$"); }

        private static Boolean Is(String word, String what) { return String.Equals(word, what, StringComparison.OrdinalIgnoreCase); }

        // Words, Windows-style: quotes group, and are kept.
        private static List<String> Split(String s)
        {
            var words = new List<String>();
            var current = new StringBuilder();
            var quoted = false;
            foreach (var ch in s)
            {
                if (ch == '"') { quoted = !quoted; current.Append(ch); continue; }
                if (Char.IsWhiteSpace(ch) && !quoted)
                {
                    if (current.Length > 0) { words.Add(current.ToString()); current.Clear(); }
                    continue;
                }
                current.Append(ch);
            }
            if (current.Length > 0) words.Add(current.ToString());
            return words;
        }

        // The text after the first n words, as it was written.
        private static String Rest(String s, Int32 n)
        {
            var i = 0;
            var quoted = false;
            for (var w = 0; w < n; w++)
            {
                while (i < s.Length && Char.IsWhiteSpace(s[i])) i++;
                while (i < s.Length && (quoted || !Char.IsWhiteSpace(s[i])))
                {
                    if (s[i] == '"') quoted = !quoted;
                    i++;
                }
            }
            return s.Substring(Math.Min(i, s.Length)).Trim();
        }

        private static String Unquote(String s)
        {
            s = s.Trim();
            return s.Length >= 2 && s[0] == '"' && s[s.Length - 1] == '"' ? s.Substring(1, s.Length - 2) : s;
        }

        private static String Quote(String s) { return "\"" + s.Replace("\"", "\\\"") + "\""; }
    }
}
