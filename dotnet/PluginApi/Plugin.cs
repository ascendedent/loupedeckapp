// The plugin itself, the application it belongs to, and the services the
// plugin service gives it: a log, settings, status, preferences and accounts.
namespace Loupedeck
{
    using System;
    using System.Collections;
    using System.Collections.Generic;
    using System.Reflection;

    public enum PluginStatus
    {
        Unknown = 0,
        Normal = 1,
        Warning = 2,
        Error = 3,
    }

    public abstract class Plugin
    {
        protected Plugin()
        {
            this.Assembly = this.GetType().Assembly;
            this.Name = Host.Service.PluginName ?? this.GetType().Name;
            this.Log = new PluginLogFile(this.Name);
            this.Info = new PluginInfo();
            this.PluginPreferences = new PluginPreferenceCollection(this);
            this.ServiceEvents = new PluginServiceEvents();
            this.PluginEvents = new PluginEvents();
            this.KeyboardApi = new KeyboardApi();
            this.Localization = new PluginLocalization();
            Host.Service.Register(this);
        }

        public String Name { get; private set; }

        public Assembly Assembly { get; private set; }

        public PluginLogFile Log { get; private set; }

        public PluginInfo Info { get; private set; }

        public PluginPreferenceCollection PluginPreferences { get; private set; }

        public PluginServiceEvents ServiceEvents { get; private set; }

        public ClientApplication ClientApplication { get; internal set; }

        // A plugin that only drives an application through its API, or has no
        // application at all, is loaded regardless of what is focused.
        public virtual Boolean UsesApplicationApiOnly { get { return false; } }

        public virtual Boolean HasNoApplication { get { return false; } }

        public virtual void Load() { }

        public virtual void Unload() { }

        // After the package is copied in, and before it is removed. The host
        // calls Install() once, on the first run of an installation.
        public virtual Boolean Install() { return true; }

        public virtual Boolean Uninstall() { return true; }

        public virtual Boolean InstallAdmin() { return true; }

        public virtual Boolean UninstallAdmin() { return true; }

        public PluginEvents PluginEvents { get; private set; }

        public KeyboardApi KeyboardApi { get; private set; }

        public PluginLocalization Localization { get; private set; }

        // For actions declared in a configuration file rather than as classes.
        public virtual PluginActionParameter[] GetActionParameterValues(String actionName) { return null; }

        // Commands and adjustments declared by the plugin itself rather than
        // as classes. Most plugins leave these empty.
        public virtual void RunCommand(String commandName, String parameter) { }

        public virtual void ApplyAdjustment(String adjustmentName, String parameter, Int32 diff) { }

        // -- settings: plain strings, kept by the host across restarts --
        public void SetPluginSetting(String settingName, String settingValue)
        {
            Host.Service.Settings.Set(settingName, settingValue);
        }

        public void SetPluginSetting(String settingName, String settingValue, Boolean backupOnline)
        {
            Host.Service.Settings.Set(settingName, settingValue);
        }

        public Boolean TryGetPluginSetting(String settingName, out String settingValue)
        {
            return Host.Service.Settings.TryGet(settingName, out settingValue);
        }

        public void DeletePluginSetting(String settingName) { Host.Service.Settings.Delete(settingName); }

        public String[] ListPluginSettings() { return Host.Service.Settings.Names(); }

        public String GetPluginDataDirectory() { return Host.Service.DataDirectory; }

        // -- status: shown by the app beside the plugin's name --
        public PluginStatus PluginStatus { get; private set; }

        public void OnPluginStatusChanged(PluginStatus status, String message)
        {
            this.OnPluginStatusChanged(status, message, null, null);
        }

        public void OnPluginStatusChanged(PluginStatus status, String message, String supportUrl)
        {
            this.OnPluginStatusChanged(status, message, supportUrl, null);
        }

        public void OnPluginStatusChanged(PluginStatus status, String message, String supportUrl, String supportUrlTitle)
        {
            this.PluginStatus = status;
            Host.Service.StatusChanged(status, message, supportUrl, supportUrlTitle);
        }
    }

    public enum ClientApplicationStatus
    {
        Unknown = 0,
        Installed = 1,
        NotInstalled = 2,
    }

    public abstract class ClientApplication
    {
        protected ClientApplication() { }

        protected internal virtual String GetProcessName() { return ""; }

        protected internal virtual String[] GetProcessNames() { return null; }

        protected internal virtual Boolean IsProcessNameSupported(String processName) { return false; }

        protected internal virtual String GetBundleName() { return ""; }

        protected internal virtual String[] GetBundleNames() { return null; }

        protected internal virtual Boolean IsBundleNameSupported(String bundleName) { return false; }

        protected internal virtual String GetExecutablePath() { return null; }

        public virtual String[] GetProcessOrBundleNames() { return null; }

        public virtual ClientApplicationStatus GetApplicationStatus() { return ClientApplicationStatus.Unknown; }

        public virtual Boolean IsInstalled() { return true; }

        // Whether the application is running is not tracked here; plugins
        // that ask are told it is, so they try to talk to it.
        public Boolean IsRunning() { return true; }

        public Boolean IsActive() { return true; }

        public String GetRunningProcessName() { return this.GetProcessName(); }

        public event EventHandler<ClientApplicationChangedEventArgs> ApplicationStarted;

        public event EventHandler<ClientApplicationChangedEventArgs> ApplicationStopped;

        internal void RaiseStarted()
        {
            var h = this.ApplicationStarted;
            if (h != null) h(this, new ClientApplicationChangedEventArgs(this.GetProcessName()));
        }

        internal void RaiseStopped()
        {
            var h = this.ApplicationStopped;
            if (h != null) h(this, new ClientApplicationChangedEventArgs(this.GetProcessName()));
        }

        public void Start() { }

        public void Activate() { }

        // Keys go through the app's own input backend (ydotool on Wayland).
        public void SendKeyboardShortcut(VirtualKeyCode virtualKeyCode)
        {
            this.SendKeyboardShortcut(virtualKeyCode, ModifierKey.None);
        }

        public void SendKeyboardShortcut(VirtualKeyCode virtualKeyCode, ModifierKey modifiers)
        {
            var combo = Keys.Combo(virtualKeyCode, modifiers);
            if (combo == null)
                Host.Service.Log("no key here for " + virtualKeyCode + " (" + (Int32)virtualKeyCode + ")");
            else
                Host.Service.SendKeys(combo);
        }
    }

    // Haptics: only one mouse has them, and not on Linux. Accepted, ignored.
    public class PluginEvents
    {
        internal PluginEvents() { }

        public void AddEvent(String name, String displayName, String description) { }

        public void RaiseEvent(String name) { }
    }

    public class PluginLocalization
    {
        internal PluginLocalization() { }

        public String CurrentLanguage { get; private set; }

        public Boolean SetCurrentLanguage(String languageId) { this.CurrentLanguage = languageId; return true; }
    }

    public static class LocalizationEngine
    {
        public static String DefaultLanguage = "en-US";
    }

    public class PluginInfo
    {
        public BitmapImage Icon16x16 { get; set; }
        public BitmapImage Icon32x32 { get; set; }
        public BitmapImage Icon48x48 { get; set; }
        public BitmapImage Icon256x256 { get; set; }
    }

    // Lines go to standard output, which the app keeps as the plugin's log.
    public class PluginLogFile
    {
        private readonly String _name;

        internal PluginLogFile(String name) { this._name = name; }

        public Boolean Verbose(String text) { return this.Write("verbose", null, text); }
        public Boolean Verbose(Exception ex, String text) { return this.Write("verbose", ex, text); }
        public Boolean Info(String text) { return this.Write("info", null, text); }
        public Boolean Info(Exception ex, String text) { return this.Write("info", ex, text); }
        public Boolean Warning(String text) { return this.Write("warning", null, text); }
        public Boolean Warning(Exception ex, String text) { return this.Write("warning", ex, text); }
        public Boolean Error(String text) { return this.Write("error", null, text); }
        public Boolean Error(Exception ex, String text) { return this.Write("error", ex, text); }

        public void WriteOpenLine() { }

        public void WriteCloseLine() { }

        private Boolean Write(String level, Exception ex, String text)
        {
            var line = String.Format("{0:HH:mm:ss} {1} {2}", DateTime.Now, level, text);
            if (ex != null) line += " | " + ex.GetType().Name + ": " + ex.Message;
            Console.Out.WriteLine(line);
            Console.Out.Flush();
            return true;
        }
    }

    // -- preferences: what the official software shows on the plugin's page --
    public abstract class PluginPreference
    {
        protected PluginPreference(String name) { this.Name = name; this.DisplayName = name; }

        public String Name { get; private set; }

        public String DisplayName { get; set; }

        public String Description { get; set; }

        public Boolean IsRequired { get; set; }

        internal Plugin Plugin { get; set; }

        internal abstract String Kind { get; }
    }

    // A sign-in to an outside service. The app shows its button; the plugin
    // does the signing in when asked and reports how it went.
    public class PluginPreferenceAccount : PluginPreference
    {
        public PluginPreferenceAccount(String name) : base(name) { }

        internal override String Kind { get { return "account"; } }

        public String LoginUrlTitle { get; set; }

        public String LogoutUrlTitle { get; set; }

        public Boolean IsLoggedIn { get; private set; }

        public String UserName { get; private set; }

        public String AccessToken
        {
            get { return this.Setting("AccessToken"); }
            set { this.Setting("AccessToken", value); }
        }

        public String RefreshToken
        {
            get { return this.Setting("RefreshToken"); }
            set { this.Setting("RefreshToken", value); }
        }

        public event EventHandler<EventArgs> LoginRequested;

        public event EventHandler<EventArgs> LogoutRequested;

        public void ReportLogin(String userName, String accessToken, String refreshToken)
        {
            this.UserName = userName;
            this.AccessToken = accessToken;
            this.RefreshToken = refreshToken;
            this.IsLoggedIn = true;
            this.Setting("UserName", userName);
            Host.Service.PreferencesChanged();
        }

        public void ReportLogout()
        {
            this.UserName = null;
            this.AccessToken = null;
            this.RefreshToken = null;
            this.IsLoggedIn = false;
            this.Setting("UserName", null);
            Host.Service.PreferencesChanged();
        }

        internal void Restore()
        {
            var user = this.Setting("UserName");
            if (!String.IsNullOrEmpty(user) && !String.IsNullOrEmpty(this.AccessToken))
            {
                this.UserName = user;
                this.IsLoggedIn = true;
            }
        }

        internal void RequestLogin()
        {
            var h = this.LoginRequested;
            if (h != null) h(this, EventArgs.Empty);
        }

        internal void RequestLogout()
        {
            var h = this.LogoutRequested;
            if (h != null) h(this, EventArgs.Empty);
        }

        private String Key(String what) { return "PluginPreferenceAccount." + this.Name + "." + what; }

        private String Setting(String what)
        {
            String v;
            return Host.Service.Settings.TryGet(this.Key(what), out v) ? v : null;
        }

        private void Setting(String what, String value)
        {
            if (value == null) Host.Service.Settings.Delete(this.Key(what));
            else Host.Service.Settings.Set(this.Key(what), value);
        }
    }

    public class PluginPreferenceCollection : IEnumerable<PluginPreference>
    {
        private readonly Plugin _plugin;
        private readonly List<PluginPreference> _items = new List<PluginPreference>();

        internal PluginPreferenceCollection(Plugin plugin) { this._plugin = plugin; }

        public void Add(PluginPreference preference)
        {
            preference.Plugin = this._plugin;
            this._items.Add(preference);
            var account = preference as PluginPreferenceAccount;
            if (account != null) account.Restore();
            Host.Service.PreferencesChanged();
        }

        public Int32 Count { get { return this._items.Count; } }

        public IEnumerator<PluginPreference> GetEnumerator() { return this._items.GetEnumerator(); }

        IEnumerator IEnumerable.GetEnumerator() { return this._items.GetEnumerator(); }
    }

    // Files the official service fetched for a plugin from Loupedeck's own
    // servers (a plugin's configuration, typically: which app ID to sign in
    // with). There is no such server here. A copy placed in the plugin's data
    // folder under online-files/ is served instead; otherwise the answer is
    // nothing, which plugins already have to cope with when offline.
    public class PluginServiceEvents
    {
        internal PluginServiceEvents() { }

        // loupedeck:plugin/<Name>/callback/... links, as an OAuth redirect.
        public event EventHandler<UrlCallbackReceivedEventArgs> UrlCallbackReceived;

        internal void RaiseUrlCallback(Uri uri)
        {
            var h = this.UrlCallbackReceived;
            if (h != null) h(this, new UrlCallbackReceivedEventArgs(uri));
        }

        public event EventHandler<OnlineFileContentReceivedEventArgs> OnlineFileContentReceived;

        public void GetOnlineFileContent(String fileName)
        {
            Byte[] content = null;
            var local = System.IO.Path.Combine(Host.Service.DataDirectory ?? ".", "online-files",
                                               System.IO.Path.GetFileName(fileName ?? ""));
            if (System.IO.File.Exists(local))
                content = System.IO.File.ReadAllBytes(local);
            else
                Host.Service.Log("online file " + fileName + " is not available; a copy at " + local +
                                 " would be used");
            var h = this.OnlineFileContentReceived;
            if (h != null) h(this, new OnlineFileContentReceivedEventArgs(fileName, content));
        }
    }

    public class GetOnlineFileContentEventArgs : EventArgs
    {
        public GetOnlineFileContentEventArgs(String fileName) { this.FileName = fileName; }

        public String FileName { get; private set; }
    }

    public class OnlineFileContentReceivedEventArgs : GetOnlineFileContentEventArgs
    {
        private readonly Byte[] _content;

        public OnlineFileContentReceivedEventArgs(String fileName, Byte[] content) : base(fileName)
        {
            this._content = content;
        }

        public Byte[] GetFileContent() { return this._content; }
    }
}

namespace Loupedeck
{
    using System;

    public class ClientApplicationChangedEventArgs : EventArgs
    {
        public ClientApplicationChangedEventArgs(String processName) { this.ProcessName = processName; }

        public String ProcessName { get; private set; }
    }

    public class UrlCallbackReceivedEventArgs : EventArgs
    {
        public UrlCallbackReceivedEventArgs(Uri uri) { this.Uri = uri; }

        public Uri Uri { get; private set; }
    }
}
