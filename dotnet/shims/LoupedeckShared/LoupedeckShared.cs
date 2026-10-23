// LoupedeckShared, as the host provides it here. Loupedeck's software ships
// a library of that name beside its plugins, and some of Loupedeck's own
// plugins reference it (the AI Assistant: AesString.Decrypt, on the
// configuration it fetched from Loupedeck's servers). Written from the one
// signature plugins reference; nothing of Loupedeck's library is in it.
//
// The configuration such plugins read comes from the app here instead, written
// in plain text (plugin_port.write_settings), so Decrypt hands it back as it
// is. The OpenAI model a converted plugin asks for is the one set in the app
// (plugin_port redirects OpenAI_API's fixed ChatGPTTurbo here).
using System;
using System.IO;
using System.Reflection;
using System.Text.RegularExpressions;

[assembly: AssemblyVersion("99.0.0.0")]
[assembly: AssemblyTitle("LoupedeckShared (Linux host)")]

namespace Loupedeck
{
    public static class AesString
    {
        public static String Decrypt(String text, String password) { return text; }

        public static String Encrypt(String text, String password) { return text; }
    }
}

namespace Loupedeck.LinuxShared
{
    public static class OpenAi
    {
        public const String DefaultModel = "gpt-4o-mini";

        // The model set in the app for this plugin ("Model" in the access
        // file it reads), or DefaultModel.
        public static String ChatModel()
        {
            try
            {
                var dir = Environment.GetEnvironmentVariable("LPS_PLUGIN_DATA_DIRECTORY") ?? "";
                var path = Path.Combine(Path.Combine(dir, "online-files"), "gpt-openai-access.json");
                if (File.Exists(path))
                {
                    var m = Regex.Match(File.ReadAllText(path), "\"Model\"\\s*:\\s*\"([^\"]+)\"");
                    if (m.Success && m.Groups[1].Value.Trim().Length > 0) return m.Groups[1].Value.Trim();
                }
            }
            catch (Exception)
            {
            }
            return DefaultModel;
        }
    }
}
