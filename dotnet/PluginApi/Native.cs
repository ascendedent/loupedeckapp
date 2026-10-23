// The "native" side a plugin can reach: the clipboard, typing a string,
// sending keys. Shapes from a compiled plugin (Loupedeck's AI Assistant):
// Plugin.NativeApi.GetNativeMethods() hands back the methods.
//
// The clipboard is read and written here, in the host process, through
// wl-copy/wl-paste on Wayland or xclip on X11. Typing and keys go to the app,
// which sends them through its input backend (ydotool on Wayland).
namespace Loupedeck
{
    using System;
    using System.Collections.Generic;
    using System.Diagnostics;

    public interface INativeMethods
    {
        String ClipboardGetText();

        void ClipboardSetText(String text);

        void SendKeyboardShortcut(VirtualKeyCode virtualKeyCode, ModifierKey modifiers);

        void SendString(String text);
    }

    public interface INativeApi
    {
        INativeMethods GetNativeMethods();
    }

    internal class NativeApi : INativeApi, INativeMethods
    {
        public INativeMethods GetNativeMethods() { return this; }

        public String ClipboardGetText()
        {
            var wayland = Wayland();
            return Run(wayland ? "wl-paste" : "xclip", wayland ? "--no-newline" : "-selection clipboard -o", null);
        }

        public void ClipboardSetText(String text)
        {
            var wayland = Wayland();
            Run(wayland ? "wl-copy" : "xclip", wayland ? "" : "-selection clipboard", text ?? "");
        }

        public void SendKeyboardShortcut(VirtualKeyCode virtualKeyCode, ModifierKey modifiers)
        {
            var combo = Keys.Combo(virtualKeyCode, modifiers);
            if (combo != null) Host.Service.SendKeys(combo);
        }

        public void SendString(String text)
        {
            if (!String.IsNullOrEmpty(text)) Host.Service.SendText(text);
        }

        private static Boolean Wayland()
        {
            return !String.IsNullOrEmpty(Environment.GetEnvironmentVariable("WAYLAND_DISPLAY"));
        }

        // The tool's output, or "" when it is missing or fails. Input, when
        // given, is written to it; wl-copy stays behind to serve the
        // clipboard, so it is not waited on.
        private static String Run(String file, String arguments, String input)
        {
            try
            {
                var info = new ProcessStartInfo(file, arguments)
                {
                    UseShellExecute = false,
                    RedirectStandardInput = input != null,
                    RedirectStandardOutput = input == null,
                };
                using (var p = Process.Start(info))
                {
                    if (input != null)
                    {
                        p.StandardInput.Write(input);
                        p.StandardInput.Close();
                        p.WaitForExit(2000);
                        return "";
                    }
                    var text = p.StandardOutput.ReadToEnd();
                    p.WaitForExit(2000);
                    return text;
                }
            }
            catch (Exception ex)
            {
                Host.Service.Log("clipboard: " + file + ": " + ex.Message);
                return "";
            }
        }
    }

    public static class CommonStrings
    {
        // Between a group and its subgroup in an action's GroupName.
        public static readonly String SubgroupSeparator = "###";
    }

    public static class GenericCollectionExtensions
    {
        public static Boolean IsNullOrEmpty<T>(this List<T> list) { return list == null || list.Count == 0; }
    }
}
