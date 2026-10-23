// The host: loads one plugin and serves it to the app.
//
// The app's plugin_host.py starts this program the way it starts a Node.js
// plugin, with the same four LPS_* variables, and this connects back over the
// same WebSocket protocol (see plugin_host.py). So to the app a .NET plugin is
// just another plugin; everything it does for those (icons, live labels,
// restarts) applies here too.
//
// On top of the Node SDK's messages this sends events the app understands:
//   ActionImageChanged {actionName}   redraw it (text and image)
//   ActionListChanged                 ask for the list again
//   PluginStatusChanged {status, message, supportUrl, supportUrlTitle}
//   PreferencesChanged                ask for the preferences again
// and answers GetPreferences and PreferenceAction (an account's sign in/out).
//
// Action names: a command is its class's full name; one offered per
// parameter is "<class>|<parameter>"; an adjustment's reset is "<name>_RESET".
namespace Loupedeck.Host
{
    using System;
    using System.Collections.Concurrent;
    using System.Collections.Generic;
    using System.IO;
    using System.Linq;
    using System.Net.WebSockets;
    using System.Reflection;
    using System.Text;
    using System.Threading;

    internal static class Service
    {
        internal static String PluginName;
        internal static String DataDirectory;
        internal static Assembly PluginAssembly;
        internal static SettingsStore Settings = new SettingsStore(null);

        private static Plugin _plugin;
        private static readonly List<PluginAction> Actions = new List<PluginAction>();
        private static Connection _conn;

        // Set while the host constructs the plugin. Some plugins construct
        // spare instances of themselves inside actions; those are not ours.
        [ThreadStatic] private static Boolean _constructing;

        internal static void Register(Plugin plugin)
        {
            if (_constructing && _plugin == null) _plugin = plugin;
        }

        internal static void SendKeys(String combo)
        {
            Send(Event("SendKeyboardShortcut", new Dictionary<String, Object> { { "combo", combo } }));
        }

        internal static void SendText(String text)
        {
            Send(Event("SendText", new Dictionary<String, Object> { { "text", text } }));
        }

        // One key held down ("ctrl", "a") or let go, as the app names keys.
        internal static void SendKeyState(String key, Boolean down)
        {
            Send(Event("KeyState", new Dictionary<String, Object> { { "key", key }, { "down", down } }));
        }

        // Positive clicks scroll up (or right), negative down (or left), as
        // Windows' wheels do.
        internal static void SendScroll(Int32 clicks, Boolean horizontal)
        {
            if (clicks != 0)
                Send(Event("Scroll", new Dictionary<String, Object> { { "clicks", clicks }, { "horizontal", horizontal } }));
        }

        internal static void Log(String text)
        {
            Console.Out.WriteLine("{0:HH:mm:ss} host {1}", DateTime.Now, text);
            Console.Out.Flush();
        }

        // -- notifications from the plugin --
        internal static void ImageChanged(PluginAction action, String parameter)
        {
            var names = parameter != null
                ? new[] { ActionName(action, parameter) }
                : NamesOf(action).ToArray();
            foreach (var n in names)
                Send(Event("ActionImageChanged", new Dictionary<String, Object> { { "actionName", n } }));
        }

        internal static void ParametersChanged(PluginAction action) { Send(Event("ActionListChanged", null)); }

        // Kept, because a plugin usually reports its status from Load(),
        // before there is a connection to send it on.
        private static Dictionary<String, Object> _status;

        internal static void StatusChanged(PluginStatus status, String message, String url, String urlTitle)
        {
            _status = new Dictionary<String, Object> {
                { "status", status.ToString() }, { "message", message ?? "" },
                { "supportUrl", url ?? "" }, { "supportUrlTitle", urlTitle ?? "" } };
            Send(Event("PluginStatusChanged", _status));
        }

        internal static void PreferencesChanged() { Send(Event("PreferencesChanged", null)); }

        // -- folders --
        internal static void FolderChanged(PluginDynamicFolder folder)
        {
            Send(Event("FolderChanged", new Dictionary<String, Object> { { "folder", folder.Name } }));
        }

        internal static void FolderClose(PluginDynamicFolder folder)
        {
            Send(Event("FolderClose", new Dictionary<String, Object> { { "folder", folder.Name } }));
        }

        internal static void ItemChanged(String actionName)
        {
            Send(Event("ActionImageChanged", new Dictionary<String, Object> { { "actionName", actionName } }));
        }

        // "<folder>/cmd/<x>" or "<folder>/adj/<x>": the folder and the raw x.
        private static PluginDynamicFolder FolderItem(String name, out String parameter, out Boolean isAdjustment)
        {
            parameter = null;
            isAdjustment = false;
            if (name == null) return null;
            List<PluginDynamicFolder> folders;
            lock (Actions) folders = Actions.OfType<PluginDynamicFolder>().ToList();
            foreach (var f in folders)
            {
                if (name.StartsWith(f.Name + PluginDynamicFolder.CommandTag, StringComparison.Ordinal))
                {
                    parameter = name.Substring(f.Name.Length + PluginDynamicFolder.CommandTag.Length);
                    return f;
                }
                if (name.StartsWith(f.Name + PluginDynamicFolder.AdjustmentTag, StringComparison.Ordinal))
                {
                    parameter = name.Substring(f.Name.Length + PluginDynamicFolder.AdjustmentTag.Length);
                    isAdjustment = true;
                    return f;
                }
            }
            return null;
        }

        private static readonly HashSet<String> ActiveFolders = new HashSet<String>();

        // What goes on the device while a folder is open.
        private static Object FolderLayout(Dictionary<String, Object> p, Boolean open, Boolean close)
        {
            var name = p.ContainsKey("folder") ? p["folder"] as String : null;
            PluginDynamicFolder f;
            lock (Actions) f = Actions.OfType<PluginDynamicFolder>().FirstOrDefault(x => x.Name == name);
            if (f == null) return null;
            try
            {
                if (close)
                {
                    if (ActiveFolders.Remove(f.Name)) f.Deactivate();
                    return true;
                }
                if (open && ActiveFolders.Add(f.Name)) f.Activate();
                var device = DeviceType.All;
                return new Dictionary<String, Object> {
                    { "navigation", f.GetNavigationArea(device).ToString() },
                    { "buttons", (f.GetButtonPressActionNames(device) ?? Enumerable.Empty<String>()).Cast<Object>().ToList() },
                    { "rotate", (f.GetEncoderRotateActionNames(device) ?? Enumerable.Empty<String>()).Cast<Object>().ToList() },
                    { "press", (f.GetEncoderPressActionNames(device) ?? Enumerable.Empty<String>()).Cast<Object>().ToList() } };
            }
            catch (Exception ex)
            {
                Log("folder " + name + ": " + Inner(ex));
                return null;
            }
        }

        // -- names --
        internal static String ActionName(PluginAction action, String parameter)
        {
            return parameter == null ? action.Name : action.Name + "|" + parameter;
        }

        private static IEnumerable<String> NamesOf(PluginAction action)
        {
            var dyn = action as PluginDynamicAction;
            var ps = dyn != null ? dyn.AllParameters() : new PluginActionParameter[0];
            if (ps.Length == 0) yield return ActionName(action, null);
            foreach (var p in ps) yield return ActionName(action, p.Name);
        }

        // "<class>|<parameter>" or "<class>" -> the action and its parameter.
        private static PluginAction Find(String name, out String parameter, out Boolean reset)
        {
            parameter = null;
            reset = false;
            if (name == null) return null;
            if (name.EndsWith("_RESET"))
            {
                reset = true;
                name = name.Substring(0, name.Length - "_RESET".Length);
            }
            var bar = name.IndexOf('|');
            var cls = bar < 0 ? name : name.Substring(0, bar);
            if (bar >= 0) parameter = name.Substring(bar + 1);
            PluginAction found;
            lock (Actions)
            {
                found = Actions.FirstOrDefault(a => a.Name == cls);
            }
            // A profile action bound before its value was filled in. The
            // official software never runs one without a value, so plugins
            // assume a string (Weather splits it); an empty one is the
            // nearest thing.
            var dynamic = found as PluginDynamicAction;
            if (parameter == null && dynamic != null && dynamic.ProfileActionType != null) parameter = "";
            return found;
        }

        // -- loading --
        internal static Int32 Run(String[] args)
        {
            if (args.Length < 1)
            {
                Console.Error.WriteLine("usage: LoupedeckHost.exe Plugin.dll");
                return 2;
            }
            var dll = Path.GetFullPath(args[0]);
            var folder = Path.GetDirectoryName(dll);
            PluginName = Environment.GetEnvironmentVariable("LPS_PLUGIN_NAME") ?? Path.GetFileNameWithoutExtension(dll);
            DataDirectory = Environment.GetEnvironmentVariable("LPS_PLUGIN_DATA_DIRECTORY")
                ?? Path.Combine(folder, ".data");
            Directory.CreateDirectory(DataDirectory);
            Settings = new SettingsStore(Path.Combine(DataDirectory, "settings.json"));

            // The plugin asks for PluginApi by name: that is this assembly.
            // Anything else it brings sits beside it.
            var api = typeof(Plugin).Assembly;
            AppDomain.CurrentDomain.AssemblyResolve += (s, e) =>
            {
                var n = new AssemblyName(e.Name).Name;
                if (n == "PluginApi") return api;
                var path = Path.Combine(folder, n + ".dll");
                if (File.Exists(path)) return Assembly.LoadFrom(path);
                // What the host provides beside itself (LoupedeckShared).
                var provided = Path.Combine(Path.GetDirectoryName(api.Location), n + ".dll");
                return File.Exists(provided) ? Assembly.LoadFrom(provided) : null;
            };

            try
            {
                PluginAssembly = Assembly.LoadFrom(dll);
                Load();
            }
            catch (Exception ex)
            {
                var inner = ex is TargetInvocationException && ex.InnerException != null ? ex.InnerException : ex;
                Log("the plugin failed to load: " + inner);
                return 3;
            }

            var url = Environment.GetEnvironmentVariable("LPS_SERVER_URL");
            if (String.IsNullOrEmpty(url))
            {
                // Run by hand: say what loaded and stop.
                foreach (var a in Actions)
                    foreach (var n in NamesOf(a))
                        Console.WriteLine("{0}  {1}", a.IsAdjustment ? "adjustment" : "command   ", n);
                return 0;
            }
            _conn = new Connection(url);
            _conn.Run(Handle);
            Unload();
            return 0;
        }

        private static IEnumerable<Type> SafeTypes(Assembly a)
        {
            try { return a.GetTypes(); }
            catch (ReflectionTypeLoadException ex) { return ex.Types.Where(t => t != null); }
        }

        // Whether `t` derives from `baseType`, without letting one type the
        // runtime cannot load (it uses something we lack) take the rest down.
        private static Boolean Is(Type t, Type baseType)
        {
            try { return baseType.IsAssignableFrom(t); }
            catch (Exception ex)
            {
                Log("skipping " + t.FullName + ": " + Inner(ex).Message);
                return false;
            }
        }

        private static void Load()
        {
            var types = SafeTypes(PluginAssembly).Where(t =>
            {
                try { return !t.IsAbstract && t.IsClass; } catch (Exception) { return false; }
            }).ToList();
            var pluginType = types.FirstOrDefault(t => Is(t, typeof(Plugin)));
            if (pluginType == null) throw new InvalidOperationException("no class derives from Loupedeck.Plugin");
            // The application first: a plugin may use it from its constructor
            // or from Load().
            ClientApplication app = null;
            var appType = types.FirstOrDefault(t => Is(t, typeof(ClientApplication)));
            if (appType != null)
            {
                try { app = (ClientApplication)Activator.CreateInstance(appType, true); }
                catch (Exception ex) { Log("the plugin's application failed to start: " + Inner(ex).Message); }
            }

            _constructing = true;
            Plugin plugin;
            try { plugin = (Plugin)Activator.CreateInstance(pluginType, true); }
            finally { _constructing = false; }
            _plugin = plugin;
            plugin.ClientApplication = app;

            // Once per installation, as the official service does after copying
            // the package in.
            String installed;
            if (!Settings.TryGet("__installed", out installed))
            {
                try { plugin.Install(); } catch (Exception ex) { Log("Install() failed: " + Inner(ex).Message); }
                Settings.Set("__installed", "1");
            }

            plugin.Load();

            foreach (var t in types.Where(t => Is(t, typeof(PluginAction))))
            {
                try
                {
                    if (t.GetConstructor(BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic,
                                         null, Type.EmptyTypes, null) == null)
                        continue;   // made by the plugin itself, not discovered
                    var action = (PluginAction)Activator.CreateInstance(t, true);
                    action.Attach(plugin);
                    if (!action.OnLoad())
                    {
                        Log("action " + t.FullName + " declined to load");
                        continue;
                    }
                    var folder = action as PluginDynamicFolder;
                    if (folder != null && !folder.Load())
                    {
                        Log("folder " + t.FullName + " declined to load");
                        continue;
                    }
                    lock (Actions) Actions.Add(action);
                }
                catch (Exception ex)
                {
                    Log("action " + t.FullName + " failed to load: " + Inner(ex).Message);
                }
            }
            Log(String.Format("loaded {0} with {1} actions", pluginType.FullName, Actions.Count));
        }

        private static void Unload()
        {
            lock (Actions)
            {
                foreach (var a in Actions)
                {
                    try
                    {
                        var folder = a as PluginDynamicFolder;
                        if (folder != null) folder.Unload();
                        a.OnUnload();
                    }
                    catch (Exception) { }
                }
            }
            try { if (_plugin != null) _plugin.Unload(); } catch (Exception) { }
        }

        private static Exception Inner(Exception ex)
        {
            return ex is TargetInvocationException && ex.InnerException != null ? ex.InnerException : ex;
        }

        // -- the protocol --
        private static Dictionary<String, Object> Event(String name, Dictionary<String, Object> parameters)
        {
            return new Dictionary<String, Object> {
                { "id", Connection.NextId() }, { "name", name }, { "messageType", "Event" },
                { "parameters", parameters ?? new Dictionary<String, Object>() } };
        }

        private static Dictionary<String, Object> Reply(Dictionary<String, Object> req, Object data, String error)
        {
            return new Dictionary<String, Object> {
                { "id", req["id"] }, { "name", req["name"] }, { "messageType", "Response" },
                { "data", data }, { "failed", error != null }, { "errorCode", error != null ? 10004 : 0 },
                { "errorMessage", error ?? "" } };
        }

        private static void Send(Dictionary<String, Object> msg)
        {
            var c = _conn;
            if (c != null) c.Send(msg);
        }

        // Returns false to disconnect.
        private static Boolean Handle(Dictionary<String, Object> msg)
        {
            var name = msg.ContainsKey("name") ? msg["name"] as String : null;
            var kind = msg.ContainsKey("messageType") ? msg["messageType"] as String : null;
            var p = msg.ContainsKey("parameters") ? msg["parameters"] as Dictionary<String, Object> : null;
            if (p == null) p = new Dictionary<String, Object>();
            if (name == "StopPlugin") return false;
            if (name == "UrlCallback" && kind == "Event")
            {
                // A loupedeck: link for this plugin (a sign-in coming back).
                var url = p.ContainsKey("url") ? p["url"] as String : null;
                Uri uri;
                if (url != null && Uri.TryCreate(url, UriKind.Absolute, out uri) && _plugin != null)
                    Worker.Post(() => _plugin.ServiceEvents.RaiseUrlCallback(uri));
                return true;
            }
            if (kind != "Request") return true;
            switch (name)
            {
                case "GetActionList":
                    Send(Reply(msg, ActionList(), null));
                    if (_status != null) Send(Event("PluginStatusChanged", _status));
                    break;
                case "ExecuteCommand":
                case "ExecuteAdjustment":
                    // On the worker, so a slow press (a web request, say) does
                    // not hold up the images and text other keys are asking for.
                    Worker.Post(() => Send(Reply(msg, true, Execute(name, p))));
                    break;
                case "GetActionText":
                    Send(Reply(msg, new Dictionary<String, Object> { { "text", Text(p) } }, null));
                    break;
                case "GetActionImage":
                    Send(Reply(msg, Image(p), null));
                    break;
                case "GetPreferences":
                    Send(Reply(msg, Preferences(), null));
                    break;
                case "OpenFolder":
                    Send(Reply(msg, FolderLayout(p, true, false), null));
                    break;
                case "GetFolder":
                    Send(Reply(msg, FolderLayout(p, false, false), null));
                    break;
                case "CloseFolder":
                    Send(Reply(msg, FolderLayout(p, false, true), null));
                    break;
                case "GetEditor":
                    Send(Reply(msg, GetEditor(p), null));
                    break;
                case "EditorValueChanged":
                    Send(Reply(msg, EditorValueChanged(p), null));
                    break;
                case "PreferenceAction":
                    Worker.Post(() => Send(Reply(msg, true, PreferenceAction(p))));
                    break;
                default:
                    Send(Reply(msg, null, "unknown request " + name));
                    break;
            }
            return true;
        }

        private static Object ActionList()
        {
            var commands = new List<Object>();
            var adjustments = new List<Object>();
            List<PluginAction> all;
            lock (Actions) all = Actions.ToList();
            foreach (var a in all)
            {
                if (!a.Enabled) continue;
                var dyn = a as PluginDynamicAction;
                var editor = Editor(a);
                // A profile action or an action editor action is one entry:
                // its parameters are what the user picks, not separate actions.
                var ps = dyn != null && editor == null ? dyn.AllParameters() : new PluginActionParameter[0];
                var entries = ps.Length == 0
                    ? new[] { Entry(a, null, a.DisplayName, a.GroupName, a.Description) }
                    : ps.Select(x => Entry(a, x.Name, x.DisplayName ?? a.DisplayName,
                                           x.GroupName ?? a.GroupName, x.Description ?? a.Description)).ToArray();
                if (editor != null) entries[0]["editor"] = editor;
                if (a is PluginDynamicFolder) entries[0]["folder"] = true;
                Boolean? reset = null;
                var adj = a as PluginDynamicAdjustment;
                var eadj = a as ActionEditorAdjustment;
                if (adj != null) reset = adj.HasReset;
                if (eadj != null) reset = eadj.HasReset;
                if (reset == null)
                {
                    commands.AddRange(entries);
                    continue;
                }
                foreach (var e in entries)
                {
                    e["hasReset"] = reset.Value;
                    e["resetCommandName"] = (String)e["name"] + "_RESET";
                    adjustments.Add(e);
                }
            }
            return new Dictionary<String, Object> { { "commands", commands }, { "adjustments", adjustments } };
        }

        private static Dictionary<String, Object> Entry(PluginAction a, String parameter, String display,
                                                        String group, String description)
        {
            return new Dictionary<String, Object> {
                { "name", ActionName(a, parameter) },
                { "displayName", String.IsNullOrEmpty(display) ? a.GetType().Name : display },
                { "groupName", group ?? "" }, { "description", description ?? "" },
                { "actionType", a.IsAdjustment ? 0 : 1 } };
        }

        // What the app draws when the action is bound: the form of an action
        // editor action, or the prompt of a profile action. Null for neither.
        private static Dictionary<String, Object> Editor(PluginAction a)
        {
            var ea = a as ActionEditorAction;
            if (ea != null)
                return new Dictionary<String, Object> {
                    { "kind", "editor" },
                    { "controls", ea.ActionEditor.Controls.Select(c => (Object)c.Describe()).ToList() } };
            var dyn = a as PluginDynamicAction;
            if (dyn == null || String.IsNullOrEmpty(dyn.ProfileActionType)) return null;
            var type = dyn.ProfileActionType;
            var semi = type.IndexOf(';');
            return new Dictionary<String, Object> {
                { "kind", "profile" },
                { "type", (semi < 0 ? type : type.Substring(0, semi)).Trim().ToLowerInvariant() },
                { "prompt", semi < 0 ? "" : type.Substring(semi + 1).Trim() } };
        }

        // A binding's values, from the JSON after the action's name.
        private static ActionEditorActionParameters Values(String parameter)
        {
            var d = new Dictionary<String, String>(StringComparer.OrdinalIgnoreCase);
            if (!String.IsNullOrEmpty(parameter))
            {
                try
                {
                    var o = Json.Object(parameter);
                    if (o != null)
                        foreach (var kv in o)
                            d[kv.Key] = kv.Value == null ? null : (kv.Value is Boolean
                                ? ((Boolean)kv.Value ? "true" : "false") : Convert.ToString(kv.Value,
                                    System.Globalization.CultureInfo.InvariantCulture));
                }
                catch (Exception) { }
            }
            return new ActionEditorActionParameters(d);
        }

        private static String Execute(String request, Dictionary<String, Object> p)
        {
            String parameter;
            Boolean reset;
            var actionName = p.ContainsKey("actionName") ? p["actionName"] as String : null;
            Boolean folderAdjustment;
            var owner = FolderItem(actionName, out parameter, out folderAdjustment);
            if (owner != null)
            {
                try
                {
                    Int32 diff;
                    Int32.TryParse(Convert.ToString(p.ContainsKey("clicks") ? p["clicks"] : "0"), out diff);
                    if (request == "ExecuteAdjustment") owner.ApplyAdjustment(parameter, diff);
                    else owner.RunCommand(parameter);
                    return null;
                }
                catch (Exception ex)
                {
                    Log(actionName + " failed: " + Inner(ex));
                    return Inner(ex).Message;
                }
            }
            var action = Find(actionName, out parameter, out reset);
            if (action == null) return "no such action";
            if (action is PluginDynamicFolder) return null;     // opening is the app's to do
            try
            {
                Int32 clicks;
                Int32.TryParse(Convert.ToString(p.ContainsKey("clicks") ? p["clicks"] : "0"), out clicks);
                var adj = action as PluginDynamicAdjustment;
                var cmd = action as PluginDynamicCommand;
                var ea = action as ActionEditorAction;
                var eadj = action as ActionEditorAdjustment;
                if (eadj != null && request == "ExecuteAdjustment")
                    eadj.ApplyAdjustment(Values(parameter), clicks);
                else if (ea != null)
                    ea.RunCommand(Values(parameter));     // a press, or an adjustment's reset
                else if (request == "ExecuteAdjustment" && adj != null)
                    adj.ApplyAdjustment(parameter, clicks);
                else if (adj != null)
                    adj.RunCommand(parameter);          // the knob's press: reset
                else if (cmd != null)
                    cmd.RunCommand(parameter);
                else
                    return "this kind of action cannot be run here yet";
                return null;
            }
            catch (Exception ex)
            {
                Log(action.Name + " failed: " + Inner(ex));
                return Inner(ex).Message;
            }
        }

        private static String Text(Dictionary<String, Object> p)
        {
            String parameter;
            Boolean reset;
            var actionName = p.ContainsKey("actionName") ? p["actionName"] as String : null;
            Boolean folderAdjustment;
            var owner = FolderItem(actionName, out parameter, out folderAdjustment);
            if (owner != null)
            {
                try
                {
                    if (!folderAdjustment) return owner.GetCommandDisplayName(parameter, PluginImageSize.Width90) ?? parameter;
                    var name = owner.GetAdjustmentDisplayName(parameter, PluginImageSize.Width90) ?? parameter;
                    var value = owner.GetAdjustmentValue(parameter);
                    return String.IsNullOrEmpty(value) ? name : name + "\n" + value;
                }
                catch (Exception ex)
                {
                    Log(actionName + " text failed: " + Inner(ex).Message);
                    return parameter;
                }
            }
            var action = Find(actionName, out parameter, out reset);
            if (action == null) return null;
            try
            {
                String text = null;
                var folderItself = action as PluginDynamicFolder;
                if (folderItself != null) return folderItself.GetButtonDisplayName(PluginImageSize.Width90) ?? action.DisplayName;
                var cmd = action as PluginDynamicCommand;
                var adj = action as PluginDynamicAdjustment;
                var ea = action as ActionEditorAction;
                if (ea != null)
                {
                    var values = Values(parameter);
                    text = ea.GetCommandDisplayName(values);
                    var eadj = ea as ActionEditorAdjustment;
                    if (eadj != null)
                    {
                        text = eadj.GetAdjustmentDisplayName(values) ?? text;
                        var value = eadj.GetAdjustmentValue(values);
                        if (!String.IsNullOrEmpty(value)) text = (text ?? action.DisplayName) + "\n" + value;
                    }
                    // The name the user gave this binding in the form, if any.
                    if (text == null) text = values.GetString("__displayName");
                }
                else if (cmd != null) text = cmd.GetCommandDisplayName(parameter, PluginImageSize.Width90);
                else if (adj != null)
                {
                    text = adj.GetAdjustmentDisplayName(parameter, PluginImageSize.Width90);
                    var value = adj.GetAdjustmentValue(parameter);
                    if (!String.IsNullOrEmpty(value))
                        text = (text ?? Listed(action, parameter)) + "\n" + value;
                }
                return text ?? Listed(action, parameter);
            }
            catch (Exception ex)
            {
                Log(action.Name + " text failed: " + Inner(ex).Message);
                return Listed(action, parameter);
            }
        }

        private static String Listed(PluginAction action, String parameter)
        {
            var dyn = action as PluginDynamicAction;
            PluginActionParameter ap;
            if (parameter != null && dyn != null && dyn.TryGetParameter(parameter, out ap) && ap.DisplayName != null)
                return ap.DisplayName;
            return action.DisplayName;
        }

        private static Object Image(Dictionary<String, Object> p)
        {
            String parameter;
            Boolean reset;
            var actionName = p.ContainsKey("actionName") ? p["actionName"] as String : null;
            Boolean folderAdjustment;
            var owner = FolderItem(actionName, out parameter, out folderAdjustment);
            if (owner != null)
            {
                try
                {
                    var img = folderAdjustment ? owner.GetAdjustmentImage(parameter, PluginImageSize.Width90)
                                               : owner.GetCommandImage(parameter, PluginImageSize.Width90);
                    return img == null ? null : img.ToDataUrl();
                }
                catch (Exception ex)
                {
                    Log(actionName + " image failed: " + Inner(ex).Message);
                    return null;
                }
            }
            var action = Find(actionName, out parameter, out reset);
            if (action == null) return null;
            try
            {
                BitmapImage image = null;
                var folderItself = action as PluginDynamicFolder;
                if (folderItself != null)
                {
                    var b = folderItself.GetButtonImage(PluginImageSize.Width90);
                    return b == null ? null : b.ToDataUrl();
                }
                var cmd = action as PluginDynamicCommand;
                var adj = action as PluginDynamicAdjustment;
                var ec = action as ActionEditorCommand;
                var eadj = action as ActionEditorAdjustment;
                if (ec != null) image = ec.GetCommandImage(Values(parameter), 90, 90);
                else if (eadj != null) image = eadj.GetAdjustmentImage(Values(parameter), 90, 90);
                else if (cmd != null) image = cmd.GetCommandImage(parameter, PluginImageSize.Width90);
                else if (adj != null) image = adj.GetAdjustmentImage(parameter, PluginImageSize.Width90)
                                           ?? adj.GetCommandImage(parameter, PluginImageSize.Width90);
                return image == null ? null : image.ToDataUrl();
            }
            catch (Exception ex)
            {
                Log(action.Name + " image failed: " + Inner(ex).Message);
                return null;
            }
        }

        // -- the form, while the user fills it in --
        private static Dictionary<String, String> Strings(Object o)
        {
            var d = new Dictionary<String, String>(StringComparer.OrdinalIgnoreCase);
            var m = o as Dictionary<String, Object>;
            if (m != null)
                foreach (var kv in m)
                    d[kv.Key] = kv.Value == null ? null : (kv.Value is Boolean
                        ? ((Boolean)kv.Value ? "true" : "false")
                        : Convert.ToString(kv.Value, System.Globalization.CultureInfo.InvariantCulture));
            return d;
        }

        // The items of every list in a form (or a profile action's choices),
        // for the values entered so far.
        private static Object GetEditor(Dictionary<String, Object> p)
        {
            String parameter;
            Boolean reset;
            var action = Find(p.ContainsKey("actionName") ? p["actionName"] as String : null, out parameter, out reset);
            if (action == null) return null;
            var result = Editor(action) ?? new Dictionary<String, Object>();
            var ea = action as ActionEditorAction;
            if (ea != null)
            {
                var state = new ActionEditorState(Strings(p.ContainsKey("values") ? p["values"] : null));
                try { ea.ActionEditor.Start(state); } catch (Exception ex) { Log("editor start: " + Inner(ex).Message); }
                var lists = new Dictionary<String, Object>();
                foreach (var c in ea.ActionEditor.Controls.Where(c => c.Kind == "list"))
                {
                    try
                    {
                        var e = ea.ActionEditor.RequestItems(state, c.Name);
                        lists[c.Name] = new Dictionary<String, Object> {
                            { "items", e.Items.Select(i => (Object)new Dictionary<String, Object> {
                                { "value", i.Name }, { "label", i.DisplayName ?? i.Name } }).ToList() },
                            { "selected", e.SelectedItemName ?? "" } };
                    }
                    catch (Exception ex) { Log("listbox " + c.Name + ": " + Inner(ex).Message); }
                }
                result["lists"] = lists;
                result["values"] = state.Values;
                return result;
            }
            var dyn = action as PluginDynamicAction;
            if (dyn != null)
            {
                var items = new List<Object>();
                PluginProfileActionData data = null;
                try { data = dyn.GetProfileActionData(); } catch (Exception ex) { Log("profile data: " + Inner(ex).Message); }
                var tree = data as PluginProfileActionTree;
                if (tree != null) Flatten(tree.Root, "", items);
                else
                    foreach (var x in dyn.AllParameters())
                        items.Add(new Dictionary<String, Object> { { "value", x.Name }, { "label", x.DisplayName ?? x.Name } });
                result["items"] = items;
            }
            return result;
        }

        private static void Flatten(PluginProfileActionTreeNode node, String path, List<Object> into)
        {
            foreach (var i in node.Items)
                into.Add(new Dictionary<String, Object> {
                    { "value", i.ActionParameter }, { "label", path + (i.DisplayName ?? i.ActionParameter) } });
            foreach (var n in node.Nodes)
                Flatten(n, path + n.DisplayName + " \u203a ", into);
        }

        // The user changed a control: the plugin may change others in turn.
        private static Object EditorValueChanged(Dictionary<String, Object> p)
        {
            String parameter;
            Boolean reset;
            var ea = Find(p.ContainsKey("actionName") ? p["actionName"] as String : null, out parameter, out reset)
                     as ActionEditorAction;
            if (ea == null) return null;
            var state = new ActionEditorState(Strings(p.ContainsKey("values") ? p["values"] : null));
            try { ea.ActionEditor.ValueChanged(state, p.ContainsKey("control") ? p["control"] as String : null); }
            catch (Exception ex) { Log("editor value changed: " + Inner(ex).Message); }
            return new Dictionary<String, Object> {
                { "values", state.Values }, { "displayName", state.DisplayName ?? "" },
                { "enabled", state.Enabled } };
        }

        internal static void EditorChanged(PluginAction action, String control)
        {
            Send(Event("EditorChanged", new Dictionary<String, Object> {
                { "actionName", action.Name }, { "control", control ?? "" } }));
        }


        private static Object Preferences()
        {
            var list = new List<Object>();
            if (_plugin == null) return list;
            foreach (var pref in _plugin.PluginPreferences)
            {
                var d = new Dictionary<String, Object> {
                    { "name", pref.Name }, { "displayName", pref.DisplayName ?? pref.Name },
                    { "kind", pref.Kind }, { "isRequired", pref.IsRequired } };
                var acc = pref as PluginPreferenceAccount;
                if (acc != null)
                {
                    d["isLoggedIn"] = acc.IsLoggedIn;
                    d["userName"] = acc.UserName ?? "";
                    d["loginTitle"] = acc.LoginUrlTitle ?? "Log in";
                    d["logoutTitle"] = acc.LogoutUrlTitle ?? "Log out";
                }
                list.Add(d);
            }
            return list;
        }

        private static String PreferenceAction(Dictionary<String, Object> p)
        {
            var name = p.ContainsKey("name") ? p["name"] as String : null;
            var what = p.ContainsKey("action") ? p["action"] as String : null;
            if (_plugin == null) return "no plugin";
            var acc = _plugin.PluginPreferences.OfType<PluginPreferenceAccount>().FirstOrDefault(a => a.Name == name);
            if (acc == null) return "no such account";
            try
            {
                if (what == "login") acc.RequestLogin();
                else if (what == "logout") acc.RequestLogout();
                else return "unknown action " + what;
                return null;
            }
            catch (Exception ex)
            {
                Log("account " + name + " " + what + " failed: " + Inner(ex));
                return Inner(ex).Message;
            }
        }
    }

    // One background thread for presses and sign-ins, in order.
    internal static class Worker
    {
        private static readonly BlockingCollection<Action> Queue = new BlockingCollection<Action>();
        private static Thread _thread;

        internal static void Post(Action work)
        {
            lock (Queue)
            {
                if (_thread == null)
                {
                    _thread = new Thread(() =>
                    {
                        foreach (var w in Queue.GetConsumingEnumerable())
                        {
                            try { w(); } catch (Exception ex) { Service.Log("worker: " + ex.Message); }
                        }
                    }) { IsBackground = true, Name = "plugin-worker" };
                    _thread.Start();
                }
            }
            Queue.Add(work);
        }
    }

    internal class Connection
    {
        private static Int32 _nextId = 1000;
        private readonly ClientWebSocket _ws = new ClientWebSocket();
        private readonly Object _sendLock = new Object();
        private readonly Uri _url;

        internal Connection(String url) { this._url = new Uri(url); }

        internal static Int32 NextId() { return Interlocked.Increment(ref _nextId); }

        internal void Run(Func<Dictionary<String, Object>, Boolean> handle)
        {
            this._ws.ConnectAsync(this._url, CancellationToken.None).Wait();
            this.Send(new Dictionary<String, Object> {
                { "id", NextId() }, { "name", "InitConnection" }, { "messageType", "Request" },
                { "parameters", new Dictionary<String, Object> {
                    { "pluginName", Service.PluginName },
                    { "sessionToken", Environment.GetEnvironmentVariable("LPS_SESSION_TOKEN") ?? "" } } } });
            var buffer = new Byte[64 * 1024];
            var message = new MemoryStream();
            while (this._ws.State == WebSocketState.Open)
            {
                WebSocketReceiveResult r;
                try
                {
                    r = this._ws.ReceiveAsync(new ArraySegment<Byte>(buffer), CancellationToken.None).Result;
                }
                catch (Exception)
                {
                    break;
                }
                if (r.MessageType == WebSocketMessageType.Close) break;
                message.Write(buffer, 0, r.Count);
                if (!r.EndOfMessage) continue;
                var text = Encoding.UTF8.GetString(message.ToArray());
                message.SetLength(0);
                Dictionary<String, Object> msg;
                try { msg = Json.Object(text); }
                catch (Exception) { continue; }
                if (msg != null && !handle(msg)) break;
            }
            try { this._ws.CloseAsync(WebSocketCloseStatus.NormalClosure, "", CancellationToken.None).Wait(1000); }
            catch (Exception) { }
        }

        internal void Send(Dictionary<String, Object> msg)
        {
            var bytes = Encoding.UTF8.GetBytes(Json.Serialize(msg));
            lock (this._sendLock)
            {
                if (this._ws.State != WebSocketState.Open) return;
                try
                {
                    this._ws.SendAsync(new ArraySegment<Byte>(bytes), WebSocketMessageType.Text, true,
                                       CancellationToken.None).Wait();
                }
                catch (Exception ex) { Service.Log("send failed: " + ex.Message); }
            }
        }
    }

    // Settings as one JSON object on disk, written on every change.
    internal class SettingsStore
    {
        private readonly String _path;
        private readonly Dictionary<String, String> _values = new Dictionary<String, String>();

        internal SettingsStore(String path)
        {
            this._path = path;
            if (path == null || !File.Exists(path)) return;
            try
            {
                var loaded = Json.Deserialize<Dictionary<String, String>>(File.ReadAllText(path));
                if (loaded != null) this._values = loaded;
            }
            catch (Exception ex) { Service.Log("settings unreadable, starting empty: " + ex.Message); }
        }

        internal void Set(String name, String value)
        {
            lock (this._values) { this._values[name] = value; this.Save(); }
        }

        internal Boolean TryGet(String name, out String value)
        {
            lock (this._values) { return this._values.TryGetValue(name, out value); }
        }

        internal void Delete(String name)
        {
            lock (this._values) { if (this._values.Remove(name)) this.Save(); }
        }

        internal String[] Names()
        {
            lock (this._values) { return this._values.Keys.ToArray(); }
        }

        private void Save()
        {
            if (this._path == null) return;
            var tmp = this._path + ".tmp";
            File.WriteAllText(tmp, Json.Serialize(this._values));
            if (File.Exists(this._path)) File.Delete(this._path);
            File.Move(tmp, this._path);
        }
    }
}

namespace Loupedeck.LinuxHost
{
    using System;

    // The one public way in, for LoupedeckHost.exe.
    public static class Runner
    {
        public static Int32 Run(String[] args) { return Loupedeck.Host.Service.Run(args); }
    }
}
