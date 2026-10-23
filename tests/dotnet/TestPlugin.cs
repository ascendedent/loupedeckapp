// A .NET plugin written the way Logitech's samples are, compiled against our
// PluginApi.dll by tests/test_dotnet_plugins.py and run through the real host.
// Each action exercises one part of the contract, and writes what it was
// asked to do to TEST_PLUGIN_OUT so the test can check it happened.
namespace Loupedeck.TestPlugin
{
    using System;
    using System.Collections.Generic;
    using System.IO;
    using System.Linq;

    public class TestPlugin : Plugin
    {
        public override Boolean HasNoApplication { get { return true; } }

        public override Boolean UsesApplicationApiOnly { get { return true; } }

        internal static void Out(String line)
        {
            File.AppendAllText(Environment.GetEnvironmentVariable("TEST_PLUGIN_OUT"), line + "\n");
        }

        public override void Load()
        {
            // Settings survive a restart: count how many times we loaded.
            String n;
            var loads = this.TryGetPluginSetting("loads", out n) ? Int32.Parse(n) + 1 : 1;
            this.SetPluginSetting("loads", loads.ToString());
            Out("load " + loads);

            var account = new PluginPreferenceAccount("service") { DisplayName = "Test service" };
            account.LoginUrlTitle = "Sign in to Test";
            account.LoginRequested += (s, e) => { account.ReportLogin("tester", "token-1", "refresh-1"); Out("login"); };
            account.LogoutRequested += (s, e) => { account.ReportLogout(); Out("logout"); };
            this.PluginPreferences.Add(account);

            this.OnPluginStatusChanged(PluginStatus.Warning, "not signed in yet");

            // A browser sign-in coming back on a loupedeck: link.
            this.ServiceEvents.UrlCallbackReceived += (s, e) => Out("url " + e.Uri.Query + " " + e.PathAndQuery);
        }

        public override void Unload() { Out("unload"); }

        public override Boolean Install()
        {
            IoHelpers.EnsureDirectoryExists(System.IO.Path.Combine(this.GetPluginDataDirectory(), "cache"));
            Tracer.Trace("installing");
            Out("install");
            return true;
        }
    }

    public class TestApplication : ClientApplication
    {
        protected override String GetProcessName() { return ""; }

        public override ClientApplicationStatus GetApplicationStatus() { return ClientApplicationStatus.Unknown; }
    }

    // Keys go to the focused application through the app's input backend.
    public class ShortcutCommand : PluginDynamicCommand
    {
        public ShortcutCommand() : base("Mute in call", "", "Test") { }

        protected override void RunCommand(String actionParameter)
        {
            this.Plugin.ClientApplication.SendKeyboardShortcut(VirtualKeyCode.KeyM, ModifierKey.Control | ModifierKey.Shift);
        }
    }

    public class ModeCommand : PluginMultistateDynamicCommand
    {
        public ModeCommand() : base("Mode", "", "Test")
        {
            this.AddState("Low", "low");
            this.AddState("Mid", "mid");
            this.AddState("High", "high");
        }
    }

    // A counter: its name says how many times it was pressed.
    public class CounterCommand : PluginDynamicCommand
    {
        private Int32 _count;

        public CounterCommand() : base("Counter", "Counts presses", "Test") { }

        protected override void RunCommand(String actionParameter)
        {
            this._count++;
            TestPlugin.Out("counter " + this._count);
            this.ActionImageChanged();
        }

        protected override String GetCommandDisplayName(String actionParameter, PluginImageSize imageSize)
        {
            return "Count " + this._count;
        }

        // Drawn, not loaded: green when even, red when odd.
        protected override BitmapImage GetCommandImage(String actionParameter, PluginImageSize imageSize)
        {
            using (var b = new BitmapBuilder(imageSize))
            {
                b.Clear(this._count % 2 == 0 ? new BitmapColor(0, 255, 0) : new BitmapColor(255, 0, 0));
                b.DrawText(this._count.ToString());
                return b.ToImage();
            }
        }
    }

    // One action per parameter, as Logitech's ButtonSwitchesCommand does.
    public class SwitchesCommand : PluginDynamicCommand
    {
        public SwitchesCommand() : base()
        {
            for (var i = 0; i < 2; i++)
                this.AddParameter(i.ToString(), "Switch " + i, "Switches");
        }

        protected override void RunCommand(String actionParameter)
        {
            TestPlugin.Out("switch " + actionParameter);
        }
    }

    public class VolumeAdjustment : PluginDynamicAdjustment
    {
        private Int32 _value = 50;

        public VolumeAdjustment() : base("Volume", "A knob", "Test", true) { }

        protected override void ApplyAdjustment(String actionParameter, Int32 diff)
        {
            this._value += diff;
            TestPlugin.Out("adjust " + diff + " -> " + this._value);
            this.AdjustmentValueChanged();
        }

        protected override void RunCommand(String actionParameter)
        {
            this._value = 50;
            TestPlugin.Out("reset");
        }

        protected override String GetAdjustmentValue(String actionParameter) { return this._value.ToString(); }
    }

    public class PowerSwitch : PluginTwoStateDynamicCommand
    {
        public PowerSwitch() : base("Power", "On and off", "Test")
        {
            this.SetOffStateDisplayName("Power off");
            this.SetOnStateDisplayName("Power on");
            this.AddToggleCommand("Power", null, null);
        }

        protected override void OnStateChanged(Boolean isTurnedOn) { TestPlugin.Out("power " + isTurnedOn); }
    }

    // Uses an embedded resource, as most plugins do for their icons.
    public class IconCommand : PluginDynamicCommand
    {
        public IconCommand() : base("Icon", "", "Test") { }

        protected override BitmapImage GetCommandImage(String actionParameter, PluginImageSize imageSize)
        {
            return EmbeddedResources.ReadImage(EmbeddedResources.FindFile("blue.png"));
        }
    }

    // An SVG, as Logitech's docs suggest for crisp icons. The app renders it.
    public class SvgCommand : PluginDynamicCommand
    {
        public SvgCommand() : base("Vector", "", "Test") { }

        protected override BitmapImage GetCommandImage(String actionParameter, PluginImageSize imageSize)
        {
            return BitmapImage.FromResource(this.Plugin.Assembly, "Loupedeck.TestPlugin.Images.icon.svg");
        }
    }

    // Profile actions: the user supplies the parameter when binding.
    public class SayCommand : PluginDynamicCommand
    {
        public SayCommand() : base("Say", "", "Test") { this.MakeProfileAction("text;Message to send:"); }

        protected override void RunCommand(String actionParameter) { TestPlugin.Out("say " + actionParameter); }

        protected override String GetCommandDisplayName(String actionParameter, PluginImageSize imageSize)
        {
            return "Say: " + actionParameter;
        }
    }

    public class PickCommand : PluginDynamicCommand
    {
        public PickCommand() : base("Pick", "", "Test")
        {
            this.AddParameter("a", "Alpha", "Test");
            this.AddParameter("b", "Beta", "Test");
            this.MakeProfileAction("list;Pick one:");
        }

        protected override void RunCommand(String actionParameter) { TestPlugin.Out("pick " + actionParameter); }
    }

    public class FruitCommand : PluginDynamicCommand
    {
        public FruitCommand() : base("Fruit", "", "Test") { this.MakeProfileAction("tree"); }

        protected override PluginProfileActionData GetProfileActionData()
        {
            var tree = new PluginProfileActionTree("Pick a fruit");
            tree.AddLevel("Kind");
            var node = tree.Root.AddNode("Fruit");
            node.AddItem("apple", "Apple", null);
            node.AddItem("pear", "Pear", null);
            return tree;
        }

        protected override void RunCommand(String actionParameter) { TestPlugin.Out("fruit " + actionParameter); }
    }

    // An action editor: a form per binding, its list filled by the plugin.
    public class SendMessageCommand : ActionEditorCommand
    {
        public SendMessageCommand()
        {
            this.Name = "SendMessage";
            this.DisplayName = "Send message";
            this.GroupName = "Test";
            this.ActionEditor.AddControlEx(new ActionEditorTextbox("message", "Message").SetRequired().SetPlaceholder("Hello"));
            this.ActionEditor.AddControlEx(new ActionEditorListbox("channel", "Channel", null));
            this.ActionEditor.AddControlEx(new ActionEditorCheckbox("loud", "Loudly").SetDefaultValue(false));
            this.ActionEditor.ListboxItemsRequested += (s, e) =>
            {
                if (e.ControlName == "channel")
                {
                    e.AddItem("general", "General", null);
                    e.AddItem("random", "Random", null);
                }
            };
            this.ActionEditor.ControlValueChanged += (s, e) =>
            {
                if (e.ControlName == "channel")
                    e.ActionEditorState.SetDisplayName("To #" + e.ActionEditorState.GetControlValue("channel"));
            };
        }

        protected override Boolean RunCommand(ActionEditorActionParameters actionParameters)
        {
            String message, channel;
            actionParameters.TryGetString("message", out message);
            actionParameters.TryGetString("channel", out channel);
            TestPlugin.Out("send " + channel + " " + message + " " + actionParameters.GetBoolean("loud"));
            return true;
        }

        protected override String GetCommandDisplayName(ActionEditorActionParameters actionParameters)
        {
            return "#" + actionParameters.GetString("channel", "?");
        }
    }

    public class NudgeAdjustment : ActionEditorAdjustment
    {
        public NudgeAdjustment() : base(false)
        {
            this.Name = "Nudge";
            this.DisplayName = "Nudge";
            this.ActionEditor.AddControlEx(new ActionEditorSlider("step", "Step", null)).SetValues(1, 10, 2, 1);
        }

        protected override Boolean ApplyAdjustment(ActionEditorActionParameters actionParameters, Int32 diff)
        {
            Int32 step;
            if (!actionParameters.TryGetInt32("step", out step)) step = 2;
            TestPlugin.Out("nudge " + (diff * step));
            return true;
        }
    }

    // A folder: a page the plugin fills. 14 numbers do not fit on one page of
    // a CT (12 keys, one of them Back), so it pages. Pressing 0 shrinks it to
    // three; pressing 1 closes it from the plugin's side.
    public class NumbersFolder : PluginDynamicFolder
    {
        private Int32 _count = 14;

        public NumbersFolder()
        {
            this.DisplayName = "Numbers";
            this.GroupName = "Test";
        }

        public override IEnumerable<String> GetButtonPressActionNames(DeviceType deviceType)
        {
            return Enumerable.Range(0, this._count).Select(i => this.CreateCommandName(i.ToString()));
        }

        public override IEnumerable<String> GetEncoderRotateActionNames(DeviceType deviceType)
        {
            return new[] { this.CreateAdjustmentName("level") };
        }

        public override String GetCommandDisplayName(String actionParameter, PluginImageSize imageSize)
        {
            return "N" + actionParameter;
        }

        public override void RunCommand(String actionParameter)
        {
            TestPlugin.Out("folder press " + actionParameter);
            if (actionParameter == "0")
            {
                this._count = 3;
                this.ButtonActionNamesChanged();
            }
            else if (actionParameter == "1")
            {
                this.Close();
            }
        }

        public override void ApplyAdjustment(String actionParameter, Int32 diff)
        {
            TestPlugin.Out("folder adjust " + actionParameter + " " + diff);
        }

        public override Boolean Activate() { TestPlugin.Out("activate"); return true; }

        public override Boolean Deactivate() { TestPlugin.Out("deactivate"); return true; }
    }

    // Throws, to show one bad action does not take the plugin down.
    public class BrokenCommand : PluginDynamicCommand
    {
        public BrokenCommand() : base("Broken", "", "Test") { }

        protected override void RunCommand(String actionParameter) { throw new InvalidOperationException("broken on purpose"); }
    }
}
