// Actions: the commands and adjustments a plugin offers.
//
// The service finds every non-abstract PluginDynamicCommand and
// PluginDynamicAdjustment in the plugin's assembly, creates one of each, and
// asks it for its name, text and image. A command that adds parameters is
// offered as one action per parameter instead of as itself ("Switch 0",
// "Switch 1"...); the parameter's name comes back as `actionParameter`.
//
// Members the plugin overrides are `protected internal`: a plugin's override
// is `protected` as it always was, and the host, which lives in this assembly,
// can still call them.
namespace Loupedeck
{
    using System;
    using System.Collections.Generic;
    using System.Linq;

    // Name, display name, description, group: shared by actions and their
    // parameters. The type argument is the concrete kind, as in the original.
    public abstract class PluginActionBase<T> where T : PluginActionBase<T>
    {
        public String Name { get; set; }
        public String DisplayName { get; set; }
        public String Description { get; set; }
        public String GroupName { get; set; }
        // A group above GroupName, and the name of an adjustment's reset.
        public String SuperGroupName { get; set; }
        public String ResetDisplayName { get; set; }
    }

    public class PluginActionParameter : PluginActionBase<PluginActionParameter>
    {
        public PluginActionParameter(String name, String displayName, String groupName)
        {
            this.Name = name;
            this.DisplayName = displayName;
            this.GroupName = groupName;
        }

        public PluginActionParameter(String name, String displayName, String groupName, String description)
            : this(name, displayName, groupName)
        {
            this.Description = description;
        }
    }

    public abstract class PluginAction : PluginActionBase<PluginAction>
    {
        protected PluginAction()
        {
            this.Name = this.GetType().FullName;
        }

        // Plugin and IsEnabled are declared on each kind of action rather
        // than here: compiled plugins reference them there.
        internal abstract void Attach(Plugin plugin);

        internal virtual Boolean Enabled { get { return true; } }

        public PluginAction MakeProfileAction(String profileActionType)
        {
            var dyn = this as PluginDynamicAction;
            return dyn != null ? dyn.MakeProfileAction(profileActionType) : this;
        }

        protected internal virtual Boolean OnLoad() { return true; }

        protected internal virtual Boolean OnUnload() { return true; }

        // The host's view: what to call this action and what it does.
        internal abstract Boolean IsAdjustment { get; }
    }

    [Flags]
    public enum DeviceType
    {
        None = 0,
        All = -1,
    }

    public abstract class PluginDynamicAction : PluginAction
    {
        private readonly List<PluginActionParameter> _parameters = new List<PluginActionParameter>();

        public Plugin Plugin { get; private set; }

        public Boolean IsEnabled { get; set; }

        internal override void Attach(Plugin plugin) { this.Plugin = plugin; }

        internal override Boolean Enabled { get { return this.IsEnabled; } }

        protected PluginDynamicAction()
        {
            this.IsEnabled = true;
        }

        // Declared here as well as on the base: compiled plugins call
        // base.OnLoad() and friends through this class.
        protected internal override Boolean OnLoad() { return base.OnLoad(); }

        protected internal override Boolean OnUnload() { return base.OnUnload(); }

        protected internal virtual void RunCommand(String actionParameter) { }

        protected internal virtual String GetCommandDisplayName(String actionParameter, PluginImageSize imageSize)
        {
            return null;
        }

        protected internal virtual BitmapImage GetCommandImage(String actionParameter, PluginImageSize imageSize)
        {
            return null;
        }

        protected PluginDynamicAction(String displayName, String description, String groupName) : this()
        {
            this.DisplayName = displayName;
            this.Description = description;
            this.GroupName = groupName;
        }

        // Overridable (some plugins compute their parameters); the host reads
        // them through AllParameters.
        protected internal virtual PluginActionParameter[] GetParameters()
        {
            lock (this._parameters) return this._parameters.ToArray();
        }

        internal PluginActionParameter[] AllParameters() { return this.GetParameters() ?? new PluginActionParameter[0]; }

        public PluginActionParameter AddParameter(String name, String displayName, String groupName)
        {
            return this.AddParameter(new PluginActionParameter(name, displayName, groupName));
        }

        public PluginActionParameter AddParameter(String name, String displayName, String groupName, String description)
        {
            return this.AddParameter(new PluginActionParameter(name, displayName, groupName, description));
        }

        public PluginActionParameter AddParameter(PluginActionParameter parameter)
        {
            lock (this._parameters)
            {
                this._parameters.RemoveAll(p => p.Name == parameter.Name);
                this._parameters.Add(parameter);
            }
            return parameter;
        }

        public Boolean RemoveParameter(String name)
        {
            lock (this._parameters)
            {
                return this._parameters.RemoveAll(p => p.Name == name) > 0;
            }
        }

        public void RemoveAllParameters()
        {
            lock (this._parameters)
            {
                this._parameters.Clear();
            }
        }

        public Boolean TryGetParameter(String name, out PluginActionParameter parameter)
        {
            lock (this._parameters)
            {
                parameter = this._parameters.FirstOrDefault(p => p.Name == name);
            }
            return parameter != null;
        }

        // The plugin's way of saying something visible changed.
        public void ParametersChanged() { Host.Service.ParametersChanged(this); }

        public void ActionImageChanged() { Host.Service.ImageChanged(this, null); }

        public void ActionImageChanged(String actionParameter) { Host.Service.ImageChanged(this, actionParameter); }

        // Declared here, not on the adjustment: compiled plugins reference it here.
        public void AdjustmentValueChanged() { Host.Service.ImageChanged(this, null); }

        public void AdjustmentValueChanged(String actionParameter) { Host.Service.ImageChanged(this, actionParameter); }

        public void CommandImageChanged(String actionParameter) { Host.Service.ImageChanged(this, actionParameter); }

        public void AdjustmentImageChanged(String actionParameter) { Host.Service.ImageChanged(this, actionParameter); }

        // Localisation is not done here; these are accepted and ignored.
        public PluginDynamicAction SetLocalize(Boolean localize) { return this; }

        public PluginDynamicAction SetLocalizeParameters(Boolean localize) { return this; }

        // A profile action: the user supplies the parameter when binding it
        // ("text;Prompt", "list;Prompt", "tree"). See Host.cs for how the app
        // is told.
        internal String ProfileActionType { get; private set; }

        public new PluginAction MakeProfileAction(String profileActionType)
        {
            this.ProfileActionType = profileActionType;
            return this;
        }

        protected internal virtual PluginProfileActionData GetProfileActionData() { return null; }

        // Low-level events. Return true if handled; nothing sends them yet.
        protected internal virtual Boolean ProcessButtonEvent(String actionParameter, DeviceButtonEvent buttonEvent) { return false; }

        protected internal virtual Boolean ProcessEncoderEvent(String actionParameter, DeviceEncoderEvent encoderEvent) { return false; }

        protected internal virtual Boolean ProcessButtonEvent2(String actionParameter, DeviceButtonEvent2 buttonEvent) { return false; }

        protected internal virtual Boolean ProcessTouchEvent(String actionParameter, DeviceTouchEvent touchEvent) { return false; }
    }

    public abstract class PluginDynamicCommand : PluginDynamicAction
    {
        protected PluginDynamicCommand() { }

        protected PluginDynamicCommand(String displayName, String description, String groupName)
            : base(displayName, description, groupName) { }

        protected PluginDynamicCommand(String displayName, String description, String groupName, DeviceType supportedDevices)
            : base(displayName, description, groupName) { }

        protected PluginDynamicCommand(DeviceType supportedDevices) { }

        internal override Boolean IsAdjustment { get { return false; } }

        protected internal override void RunCommand(String actionParameter) { }

        protected internal override String GetCommandDisplayName(String actionParameter, PluginImageSize imageSize)
        {
            return base.GetCommandDisplayName(actionParameter, imageSize);
        }

        protected internal override BitmapImage GetCommandImage(String actionParameter, PluginImageSize imageSize)
        {
            return base.GetCommandImage(actionParameter, imageSize);
        }

    }

    public abstract class PluginDynamicAdjustment : PluginDynamicAction
    {
        protected PluginDynamicAdjustment(Boolean hasReset)
        {
            this.HasReset = hasReset;
        }

        protected PluginDynamicAdjustment(String displayName, String description, String groupName, Boolean hasReset)
            : base(displayName, description, groupName)
        {
            this.HasReset = hasReset;
        }

        protected PluginDynamicAdjustment(String displayName, String description, String groupName, Boolean hasReset,
                                          DeviceType supportedDevices)
            : this(displayName, description, groupName, hasReset) { }

        protected PluginDynamicAdjustment(Boolean hasReset, DeviceType supportedDevices) : this(hasReset) { }

        public Boolean HasReset { get; private set; }

        internal override Boolean IsAdjustment { get { return true; } }

        protected internal virtual void ApplyAdjustment(String actionParameter, Int32 diff) { }

        // Pressing the knob: the reset.
        protected internal override void RunCommand(String actionParameter) { }

        protected internal virtual String GetAdjustmentValue(String actionParameter) { return null; }

        protected internal virtual String GetAdjustmentDisplayName(String actionParameter, PluginImageSize imageSize)
        {
            return null;
        }

        protected internal virtual BitmapImage GetAdjustmentImage(String actionParameter, PluginImageSize imageSize)
        {
            return null;
        }

        protected internal override String GetCommandDisplayName(String actionParameter, PluginImageSize imageSize)
        {
            return base.GetCommandDisplayName(actionParameter, imageSize);
        }

        protected internal override BitmapImage GetCommandImage(String actionParameter, PluginImageSize imageSize)
        {
            return base.GetCommandImage(actionParameter, imageSize);
        }
    }

    // On/off, with a name and an image per state.
    public abstract class PluginTwoStateDynamicCommand : PluginDynamicCommand
    {
        // A value type in compiled plugins, so an enum.
        public enum TwoStateCommand
        {
            TurnOff = 0,
            TurnOn = 1,
            Toggle = 2,
        }

        private String _onName;
        private String _offName;
        private readonly Dictionary<String, TwoStateCommand> _toggles = new Dictionary<String, TwoStateCommand>();
        private readonly Dictionary<String, BitmapImage> _onImages = new Dictionary<String, BitmapImage>();
        private readonly Dictionary<String, BitmapImage> _offImages = new Dictionary<String, BitmapImage>();

        protected PluginTwoStateDynamicCommand() { }

        protected PluginTwoStateDynamicCommand(String displayName, String description, String groupName)
            : base(displayName, description, groupName) { }

        protected PluginTwoStateDynamicCommand(String displayName, String description, String groupName,
                                               DeviceType supportedDevices)
            : base(displayName, description, groupName) { }

        public Boolean IsTurnedOn { get; private set; }

        public void SetOnStateDisplayName(String name) { this._onName = name; }

        public void SetOffStateDisplayName(String name) { this._offName = name; }

        public PluginActionParameter AddToggleCommand(String displayName, BitmapImage onImage, BitmapImage offImage)
        {
            return this.AddCommand("toggle", displayName, TwoStateCommand.Toggle, onImage, offImage);
        }

        public PluginActionParameter AddTurnOnCommand(String displayName, BitmapImage image)
        {
            return this.AddCommand("on", displayName, TwoStateCommand.TurnOn, image, image);
        }

        public PluginActionParameter AddTurnOffCommand(String displayName, BitmapImage image)
        {
            return this.AddCommand("off", displayName, TwoStateCommand.TurnOff, image, image);
        }

        private PluginActionParameter AddCommand(String name, String displayName, TwoStateCommand command,
                                                 BitmapImage onImage, BitmapImage offImage)
        {
            this._toggles[name] = command;
            if (onImage != null) this._onImages[name] = onImage;
            if (offImage != null) this._offImages[name] = offImage;
            return this.AddParameter(name, displayName ?? this.DisplayName, this.GroupName);
        }

        public void TurnOn() { this.SetState(true); }

        public void TurnOff() { this.SetState(false); }

        public void ToggleState() { this.SetState(!this.IsTurnedOn); }

        private void SetState(Boolean on)
        {
            if (this.IsTurnedOn == on) return;
            this.IsTurnedOn = on;
            this.OnStateChanged(on);
            this.ActionImageChanged();
        }

        protected internal virtual void OnStateChanged(Boolean isTurnedOn) { }

        // What a press does by default: run the parameter's own command.
        protected internal override void RunCommand(String actionParameter)
        {
            TwoStateCommand command;
            if (actionParameter != null && this._toggles.TryGetValue(actionParameter, out command))
                this.RunCommand(command);
        }

        protected internal virtual void RunCommand(TwoStateCommand command)
        {
            switch (command)
            {
                case TwoStateCommand.TurnOn: this.SetState(true); break;
                case TwoStateCommand.TurnOff: this.SetState(false); break;
                default: this.ToggleState(); break;
            }
        }

        protected internal override String GetCommandDisplayName(String actionParameter, PluginImageSize imageSize)
        {
            var name = this.IsTurnedOn ? this._onName : this._offName;
            return name ?? base.GetCommandDisplayName(actionParameter, imageSize);
        }

        protected internal override BitmapImage GetCommandImage(String actionParameter, PluginImageSize imageSize)
        {
            BitmapImage image;
            var images = this.IsTurnedOn ? this._onImages : this._offImages;
            if (actionParameter != null && images.TryGetValue(actionParameter, out image))
                return image;
            return base.GetCommandImage(actionParameter, imageSize);
        }
    }

    public class PluginMultistateDynamicCommandState
    {
        internal PluginMultistateDynamicCommandState(String name, String displayName, String description)
        {
            this.Name = name;
            this.DisplayName = displayName;
            this.Description = description;
        }

        public String Name { get; private set; }
        public String DisplayName { get; private set; }
        public String Description { get; private set; }
    }

    // Several states, one current per parameter; each press usually moves on.
    public abstract class PluginMultistateDynamicCommand : PluginDynamicCommand
    {
        private List<PluginMultistateDynamicCommandState> _states;
        private readonly Dictionary<String, Int32> _current = new Dictionary<String, Int32>();

        protected PluginMultistateDynamicCommand() { }

        protected PluginMultistateDynamicCommand(String displayName, String description, String groupName)
            : base(displayName, description, groupName) { }

        protected PluginMultistateDynamicCommand(String displayName, String description, String groupName,
                                                 DeviceType supportedDevices)
            : base(displayName, description, groupName) { }

        protected PluginMultistateDynamicCommand(DeviceType supportedDevices) { }

        // Null until the first AddState, as documented.
        public IReadOnlyList<PluginMultistateDynamicCommandState> States { get { return this._states; } }

        public Int32 StatesCount { get { return this._states == null ? 0 : this._states.Count; } }

        // Returns the state's name. Return types here are what compiled
        // plugins (VLC, Home Assistant, YTMDesktop) bind to.
        protected String AddState(String displayName, String description)
        {
            return this.AddState(displayName, displayName, description);
        }

        protected String AddState(String name, String displayName, String description)
        {
            if (this._states == null) this._states = new List<PluginMultistateDynamicCommandState>();
            this._states.Add(new PluginMultistateDynamicCommandState(name, displayName, description));
            return name;
        }

        private Int32 Current(String actionParameter)
        {
            Int32 i;
            return this._current.TryGetValue(actionParameter ?? "", out i) ? i : 0;
        }

        public PluginMultistateDynamicCommandState GetCurrentState() { return this.GetCurrentState(null); }

        public PluginMultistateDynamicCommandState GetCurrentState(String actionParameter)
        {
            return this.StatesCount == 0 ? null : this._states[this.Current(actionParameter)];
        }

        public Boolean TryGetCurrentState(out Int32 currentState) { return this.TryGetCurrentState(null, out currentState); }

        public Boolean TryGetCurrentState(String actionParameter, out Int32 currentState)
        {
            currentState = this.Current(actionParameter);
            return this.StatesCount > 0;
        }

        public Boolean TryGetCurrentStateIndex(String actionParameter, out Int32 currentStateIndex)
        {
            return this.TryGetCurrentState(actionParameter, out currentStateIndex);
        }

        // Returns the state now current.
        protected Int32 SetCurrentState(Int32 newStateIndex) { return this.SetCurrentState(null, newStateIndex); }

        protected Int32 SetCurrentState(String actionParameter, Int32 newStateIndex)
        {
            if (this.StatesCount == 0) return 0;
            var i = ((newStateIndex % this.StatesCount) + this.StatesCount) % this.StatesCount;
            this._current[actionParameter ?? ""] = i;
            this.ActionImageChanged(actionParameter);
            return i;
        }

        protected void IncrementCurrentState() { this.IncrementCurrentState(null); }

        protected void IncrementCurrentState(String actionParameter)
        {
            this.SetCurrentState(actionParameter, this.Current(actionParameter) + 1);
        }

        protected void DecrementCurrentState() { this.DecrementCurrentState(null); }

        protected void DecrementCurrentState(String actionParameter)
        {
            this.SetCurrentState(actionParameter, this.Current(actionParameter) - 1);
        }

        protected Int32 ToggleCurrentState()
        {
            this.ToggleCurrentState(null);
            return this.Current(null);
        }

        // Two states only, as in the original.
        protected void ToggleCurrentState(String actionParameter)
        {
            if (this.StatesCount != 2) throw new InvalidOperationException("ToggleCurrentState needs exactly two states");
            this.IncrementCurrentState(actionParameter);
        }

        protected internal override void RunCommand(String actionParameter)
        {
            if (this.StatesCount > 0) this.IncrementCurrentState(actionParameter);
        }

        protected internal override String GetCommandDisplayName(String actionParameter, PluginImageSize imageSize)
        {
            return this.GetCommandDisplayName(actionParameter, this.Current(actionParameter), imageSize);
        }

        protected internal virtual String GetCommandDisplayName(String actionParameter, Int32 stateIndex, PluginImageSize imageSize)
        {
            return stateIndex >= 0 && stateIndex < this.StatesCount ? this._states[stateIndex].DisplayName : null;
        }

        protected internal override BitmapImage GetCommandImage(String actionParameter, PluginImageSize imageSize)
        {
            return this.GetCommandImage(actionParameter, this.Current(actionParameter), imageSize);
        }

        protected internal virtual BitmapImage GetCommandImage(String actionParameter, Int32 stateIndex, PluginImageSize imageSize)
        {
            return null;
        }
    }

    // Press and release, and touch, for the plugins that read them.
    public enum DeviceButtonEventType
    {
        None = 0,
        Press = 1,
        Release = 2,
        LongPress = 3,
    }

    public class DeviceButtonEvent2
    {
        public DeviceButtonEventType EventType { get; internal set; }
        public Boolean IsPressed { get { return this.EventType == DeviceButtonEventType.Press; } }
    }

    public enum DeviceTouchEventType
    {
        None = 0,
        TouchDown = 1,
        TouchUp = 2,
        Tap = 3,
        DoubleTap = 4,
        LongPress = 5,
        LongRelease = 6,
        Move = 7,
        HorizontalSwipe = 8,
        VerticalSwipe = 9,
        TwoFingerTap = 10,
        Press = 11,
    }

    public class DeviceTouchEvent
    {
        public DeviceTouchEventType EventType { get; internal set; }
        public Int32 X { get; internal set; }
        public Int32 Y { get; internal set; }
        public Int32 DeltaX { get; internal set; }
        public Int32 DeltaY { get; internal set; }
        public Boolean IsTouchUp { get { return this.EventType == DeviceTouchEventType.TouchUp; } }
    }

    public static class DeviceTouchEventExtensions
    {
        public static Boolean IsLongPress(this DeviceTouchEvent e) { return e.EventType == DeviceTouchEventType.LongPress; }

        public static Boolean IsTap(this DeviceTouchEvent e) { return e.EventType == DeviceTouchEventType.Tap; }

        public static Boolean IsFnPressed(this DeviceTouchEvent e) { return false; }
    }

    public class DeviceButtonEvent
    {
        public Boolean IsPressed { get; internal set; }
    }

    public class DeviceEncoderEvent
    {
        public Int32 Clicks { get; internal set; }
    }

    // Data behind a "list" or "tree" profile action.
    public abstract class PluginProfileActionData { }

    public class PluginProfileActionTreeItem
    {
        internal PluginProfileActionTreeItem(String actionParameter, String displayName, String description)
        {
            this.ActionParameter = actionParameter;
            this.DisplayName = displayName;
            this.Description = description;
        }

        public String ActionParameter { get; private set; }
        public String DisplayName { get; private set; }
        public String Description { get; private set; }
    }

    public class PluginProfileActionTreeNode
    {
        private readonly List<PluginProfileActionTreeNode> _nodes = new List<PluginProfileActionTreeNode>();
        private readonly List<PluginProfileActionTreeItem> _items = new List<PluginProfileActionTreeItem>();

        internal PluginProfileActionTreeNode(String displayName) { this.DisplayName = displayName; }

        public String DisplayName { get; private set; }

        public IReadOnlyList<PluginProfileActionTreeNode> Nodes { get { return this._nodes; } }

        public IReadOnlyList<PluginProfileActionTreeItem> Items { get { return this._items; } }

        public PluginProfileActionTreeNode AddNode(String displayName)
        {
            var n = new PluginProfileActionTreeNode(displayName);
            this._nodes.Add(n);
            return n;
        }

        public PluginProfileActionTreeItem AddItem(String actionParameter, String displayName, String description)
        {
            var i = new PluginProfileActionTreeItem(actionParameter, displayName, description);
            this._items.Add(i);
            return i;
        }
    }

    public class PluginProfileActionTree : PluginProfileActionData
    {
        private readonly List<String> _levels = new List<String>();

        public PluginProfileActionTree(String displayName)
        {
            this.DisplayName = displayName;
            this.Root = new PluginProfileActionTreeNode(displayName);
        }

        public String DisplayName { get; private set; }

        public PluginProfileActionTreeNode Root { get; private set; }

        public IReadOnlyList<String> Levels { get { return this._levels; } }

        public void AddLevel(String levelDisplayName) { this._levels.Add(levelDisplayName); }
    }
}
