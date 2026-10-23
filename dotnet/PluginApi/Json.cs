// JSON for the host's messages and JsonHelpers: Mono's serializer there,
// System.Text.Json on .NET 8/10. Messages come out as plain dictionaries,
// lists, strings, numbers and booleans either way.
namespace Loupedeck.Host
{
    using System;
    using System.Collections.Generic;
#if NETCOREAPP
    using System.Text.Json;
#else
    using System.Web.Script.Serialization;
#endif

    internal static class Json
    {
#if NETCOREAPP
        private static readonly JsonSerializerOptions Options = new JsonSerializerOptions
        {
            PropertyNameCaseInsensitive = true,
            IncludeFields = true,
        };

        internal static String Serialize(Object value) { return JsonSerializer.Serialize(value, Options); }

        internal static T Deserialize<T>(String text) { return JsonSerializer.Deserialize<T>(text, Options); }

        internal static Dictionary<String, Object> Object(String text)
        {
            using (var doc = JsonDocument.Parse(text))
                return Plain(doc.RootElement) as Dictionary<String, Object>;
        }

        private static Object Plain(JsonElement e)
        {
            switch (e.ValueKind)
            {
                case JsonValueKind.Object:
                    var d = new Dictionary<String, Object>();
                    foreach (var p in e.EnumerateObject()) d[p.Name] = Plain(p.Value);
                    return d;
                case JsonValueKind.Array:
                    var l = new List<Object>();
                    foreach (var x in e.EnumerateArray()) l.Add(Plain(x));
                    return l;
                case JsonValueKind.String: return e.GetString();
                case JsonValueKind.Number:
                    Int64 n;
                    if (e.TryGetInt64(out n)) return n >= Int32.MinValue && n <= Int32.MaxValue ? (Object)(Int32)n : n;
                    return e.GetDouble();
                case JsonValueKind.True: return true;
                case JsonValueKind.False: return false;
                default: return null;
            }
        }
#else
        private static readonly JavaScriptSerializer Serializer = new JavaScriptSerializer { MaxJsonLength = Int32.MaxValue };

        internal static String Serialize(Object value) { return Serializer.Serialize(value); }

        internal static T Deserialize<T>(String text) { return Serializer.Deserialize<T>(text); }

        internal static Dictionary<String, Object> Object(String text)
        {
            return Serializer.Deserialize<Dictionary<String, Object>>(text);
        }
#endif
    }
}
