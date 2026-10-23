// Action editor actions: an action with a small form the user fills in when
// binding it (a message to send, a scene to pick, a key to press). The values
// are kept with the binding and handed to RunCommand each time.
//
// Shapes are the ones compiled plugins reference (Twitch, YTMDesktop, Home
// Assistant, AdvancedCommands, VLC, Discord): controls are generic over
// their own type so their setters chain, AddControlEx returns the control,
// SetValues takes doubles. Behaviour is from Logitech's documentation.
//
// Here the form is drawn by the app's inspector. The host describes each
// action's controls in the action list ("editor"), answers the app's
// GetEditorItems / EditorValueChanged requests by raising the plugin's own
// events, and a binding's values travel as JSON after the action's name:
// "Name|{\"control\":\"value\"}".
namespace Loupedeck
{
    using System;
    using System.Collections.Generic;
    using System.Linq;

    public enum ActionEditorTextboxFormat
    {
        Text = 0,
        Integer = 1,
        Number = 2,
    }

    public enum ActionEditorKeyboardKeyBehavior
    {
        KeyboardKey = 0,
        KeyboardShortcut = 1,
    }

    // What the app needs to draw a control.
    public abstract class ActionEditorControl
    {
        protected ActionEditorControl(String name, String labelText, String description)
        {
            this.Name = name;
            this.LabelText = labelText;
            this.Description = description;
        }

        public String Name { get; private set; }
        public String LabelText { get; private set; }
        public String Description { get; private set; }
        public Boolean IsRequired { get; protected set; }
        internal String DefaultValue { get; set; }

        internal abstract String Kind { get; }

        internal virtual Dictionary<String, Object> Describe()
        {
            var d = new Dictionary<String, Object> {
                { "name", this.Name }, { "kind", this.Kind }, { "label", this.LabelText ?? this.Name },
                { "description", this.Description ?? "" }, { "required", this.IsRequired } };
            if (this.DefaultValue != null) d["default"] = this.DefaultValue;
            return d;
        }
    }

    public abstract class ActionEditorControl<T> : ActionEditorControl where T : ActionEditorControl<T>
    {
        protected ActionEditorControl(String name, String labelText, String description)
            : base(name, labelText, description) { }

        public T SetRequired() { this.IsRequired = true; return (T)this; }

        public T SetRequired(Boolean required) { this.IsRequired = required; return (T)this; }
    }

    public abstract class ActionEditorTextboxBase<T> : ActionEditorControl<T> where T : ActionEditorTextboxBase<T>
    {
        protected ActionEditorTextboxBase(String name, String labelText, String description)
            : base(name, labelText, description) { }

        internal String Placeholder { get; private set; }
        internal String Regex { get; private set; }

        public T SetPlaceholder(String placeholder) { this.Placeholder = placeholder; return (T)this; }

        public T SetRegex(String regex) { this.Regex = regex; return (T)this; }

        internal override Dictionary<String, Object> Describe()
        {
            var d = base.Describe();
            if (this.Placeholder != null) d["placeholder"] = this.Placeholder;
            if (this.Regex != null) d["regex"] = this.Regex;
            return d;
        }
    }

    public class ActionEditorTextbox : ActionEditorTextboxBase<ActionEditorTextbox>
    {
        public ActionEditorTextbox(String name, String labelText) : base(name, labelText, null) { }

        public ActionEditorTextbox(String name, String labelText, String description) : base(name, labelText, description) { }

        internal ActionEditorTextboxFormat Format { get; private set; }

        internal override String Kind { get { return "text"; } }

        public ActionEditorTextbox SetFormat(ActionEditorTextboxFormat format) { this.Format = format; return this; }

        internal override Dictionary<String, Object> Describe()
        {
            var d = base.Describe();
            d["format"] = this.Format.ToString().ToLowerInvariant();
            return d;
        }
    }

    public class ActionEditorListbox : ActionEditorControl<ActionEditorListbox>
    {
        public ActionEditorListbox(String name, String labelText) : base(name, labelText, null) { }

        public ActionEditorListbox(String name, String labelText, String description) : base(name, labelText, description) { }

        internal override String Kind { get { return "list"; } }
    }

    public class ActionEditorCheckbox : ActionEditorControl<ActionEditorCheckbox>
    {
        public ActionEditorCheckbox(String name, String labelText) : base(name, labelText, null) { }

        public ActionEditorCheckbox(String name, String labelText, String description) : base(name, labelText, description) { }

        internal override String Kind { get { return "check"; } }

        public ActionEditorCheckbox SetDefaultValue(Boolean value) { this.DefaultValue = value ? "true" : "false"; return this; }
    }

    public class ActionEditorNumberSelector : ActionEditorControl<ActionEditorNumberSelector>
    {
        public ActionEditorNumberSelector(String name, String labelText) : base(name, labelText, null) { }

        public ActionEditorNumberSelector(String name, String labelText, String description) : base(name, labelText, description) { }

        internal Double Min { get; private set; }
        internal Double Max { get; private set; }
        internal Double Step { get; private set; }
        internal String FormatString { get; private set; }

        internal override String Kind { get { return "number"; } }

        public ActionEditorNumberSelector SetValues(Double minimumValue, Double maximumValue, Double defaultValue, Double step)
        {
            this.Min = minimumValue;
            this.Max = maximumValue;
            this.Step = step;
            this.DefaultValue = defaultValue.ToString(System.Globalization.CultureInfo.InvariantCulture);
            return this;
        }

        public ActionEditorNumberSelector SetFormatString(String format) { this.FormatString = format; return this; }

        internal override Dictionary<String, Object> Describe()
        {
            var d = base.Describe();
            d["min"] = this.Min;
            d["max"] = this.Max;
            d["step"] = this.Step <= 0 ? 1 : this.Step;
            if (this.FormatString != null) d["format"] = this.FormatString;
            return d;
        }
    }

    public class ActionEditorSlider : ActionEditorNumberSelector
    {
        public ActionEditorSlider(String name, String labelText) : base(name, labelText, null) { }

        public ActionEditorSlider(String name, String labelText, String description) : base(name, labelText, description) { }

        internal override String Kind { get { return "slider"; } }
    }

    public class ActionEditorKeyboardKey : ActionEditorControl<ActionEditorKeyboardKey>
    {
        public ActionEditorKeyboardKey(String name, String labelText) : base(name, labelText, null) { }

        public ActionEditorKeyboardKey(String name, String labelText, String description) : base(name, labelText, description) { }

        internal override String Kind { get { return "key"; } }

        public ActionEditorKeyboardKey SetBehavior(ActionEditorKeyboardKeyBehavior behavior) { return this; }
    }

    public class ActionEditorFileSelector : ActionEditorTextboxBase<ActionEditorFileSelector>
    {
        public ActionEditorFileSelector(String name, String labelText) : base(name, labelText, null) { }

        public ActionEditorFileSelector(String name, String labelText, String description) : base(name, labelText, description) { }

        internal override String Kind { get { return "file"; } }

        public ActionEditorFileSelector SetInitialDirectory(String directory) { return this; }
    }

    public class ActionEditorDirectorySelector : ActionEditorTextboxBase<ActionEditorDirectorySelector>
    {
        public ActionEditorDirectorySelector(String name, String labelText) : base(name, labelText, null) { }

        public ActionEditorDirectorySelector(String name, String labelText, String description) : base(name, labelText, description) { }

        internal override String Kind { get { return "directory"; } }
    }

    public class ActionEditorButton : ActionEditorControl<ActionEditorButton>
    {
        public ActionEditorButton(String name, String labelText) : base(name, labelText, null) { }

        public ActionEditorButton(String name, String labelText, String description) : base(name, labelText, description) { }

        internal override String Kind { get { return "button"; } }
    }

    // -- the values -----------------------------------------------------------------
    public class ActionEditorActionParameters
    {
        public ActionEditorActionParameters(IReadOnlyDictionary<String, String> parameters)
        {
            this.Parameters = new StringDictionaryNoCase();
            if (parameters != null)
                foreach (var kv in parameters) this.Parameters[kv.Key] = kv.Value;
        }

        public StringDictionaryNoCase Parameters { get; private set; }

        public Boolean TryGetString(String controlName, out String value)
        {
            return this.Parameters.TryGetValue(controlName, out value) && value != null;
        }

        public String GetString(String controlName) { return this.GetString(controlName, null); }

        public String GetString(String controlName, String defaultValue)
        {
            String v;
            return this.TryGetString(controlName, out v) ? v : defaultValue;
        }

        public Boolean TryGetBoolean(String controlName, out Boolean value)
        {
            String s;
            value = false;
            return this.TryGetString(controlName, out s) && Boolean.TryParse(s, out value);
        }

        public Boolean GetBoolean(String controlName)
        {
            Boolean b;
            return this.TryGetBoolean(controlName, out b) && b;
        }

        public Boolean TryGetInt32(String controlName, out Int32 value)
        {
            String s;
            value = 0;
            if (!this.TryGetString(controlName, out s)) return false;
            Double d;
            if (Int32.TryParse(s, out value)) return true;
            if (Double.TryParse(s, System.Globalization.NumberStyles.Float,
                                System.Globalization.CultureInfo.InvariantCulture, out d))
            {
                value = (Int32)Math.Round(d);
                return true;
            }
            return false;
        }

        public Boolean TryGetDouble(String controlName, out Double value)
        {
            String s;
            value = 0;
            return this.TryGetString(controlName, out s)
                && Double.TryParse(s, System.Globalization.NumberStyles.Float,
                                   System.Globalization.CultureInfo.InvariantCulture, out value);
        }

        internal String Key()
        {
            return String.Join("\u0001", this.Parameters.OrderBy(kv => kv.Key, StringComparer.OrdinalIgnoreCase)
                                                        .Select(kv => kv.Key + "=" + kv.Value));
        }
    }

    // The form as it stands while the user edits it.
    public class ActionEditorState
    {
        internal readonly StringDictionaryNoCase Values = new StringDictionaryNoCase();
        internal readonly Dictionary<String, Boolean> Enabled = new Dictionary<String, Boolean>(StringComparer.OrdinalIgnoreCase);
        internal String DisplayName;

        internal ActionEditorState(IDictionary<String, String> values)
        {
            if (values != null)
                foreach (var kv in values) this.Values[kv.Key] = kv.Value;
        }

        public String GetControlValue(String controlName)
        {
            String v;
            return this.Values.TryGetValue(controlName, out v) ? v : null;
        }

        public void SetValue(String controlName, String value) { this.Values[controlName] = value; }

        public void SetEnabled(String controlName, Boolean enabled) { this.Enabled[controlName] = enabled; }

        public void SetDisplayName(String displayName) { this.DisplayName = displayName; }
    }

    public class ActionEditorListboxItem
    {
        public ActionEditorListboxItem(String name, String displayName, String description)
        {
            this.Name = name;
            this.DisplayName = displayName;
            this.Description = description;
        }

        public String Name { get; private set; }
        public String DisplayName { get; private set; }
        public String Description { get; private set; }
    }

    public class ActionEditorStateEventArgs : EventArgs
    {
        public ActionEditorStateEventArgs(ActionEditorState state) { this.ActionEditorState = state; }

        public ActionEditorState ActionEditorState { get; private set; }
    }

    public class ActionEditorControlEventArgs : ActionEditorStateEventArgs
    {
        public ActionEditorControlEventArgs(ActionEditorState state, String controlName) : base(state)
        {
            this.ControlName = controlName;
        }

        public String ControlName { get; private set; }
    }

    public class ActionEditorControlValueChangedEventArgs : ActionEditorControlEventArgs
    {
        public ActionEditorControlValueChangedEventArgs(ActionEditorState state, String controlName)
            : base(state, controlName) { }
    }

    public class ActionEditorListboxItemsRequestedEventArgs : ActionEditorControlEventArgs
    {
        private readonly List<ActionEditorListboxItem> _items = new List<ActionEditorListboxItem>();

        public ActionEditorListboxItemsRequestedEventArgs(ActionEditorState state, String controlName)
            : base(state, controlName) { }

        public List<ActionEditorListboxItem> Items { get { return this._items; } }

        internal String SelectedItemName { get; private set; }

        public void AddItem(String name, String displayName, String description)
        {
            this._items.Add(new ActionEditorListboxItem(name, displayName, description));
        }

        public void SetSelectedItemName(String name) { this.SelectedItemName = name; }
    }

    public class ActionEditorStartedEventArgs : ActionEditorStateEventArgs
    {
        public ActionEditorStartedEventArgs(ActionEditorState state) : base(state) { }
    }

    public class ActionEditorFinishedEventArgs : ActionEditorStateEventArgs
    {
        public ActionEditorFinishedEventArgs(ActionEditorState state) : base(state) { }
    }

    // -- the editor and the actions ---------------------------------------------------
    public class ActionEditor
    {
        private readonly List<ActionEditorControl> _controls = new List<ActionEditorControl>();

        internal ActionEditor(ActionEditorAction owner) { this.Owner = owner; }

        internal ActionEditorAction Owner { get; private set; }

        internal IReadOnlyList<ActionEditorControl> Controls { get { return this._controls; } }

        public event EventHandler<ActionEditorListboxItemsRequestedEventArgs> ListboxItemsRequested;

        public event EventHandler<ActionEditorControlValueChangedEventArgs> ControlValueChanged;

        public event EventHandler<ActionEditorStartedEventArgs> Started;

        public event EventHandler<ActionEditorFinishedEventArgs> Finished;

        public void AddControl<T>(ActionEditorControl<T> control) where T : ActionEditorControl<T>
        {
            this._controls.Add(control);
        }

        public T AddControlEx<T>(ActionEditorControl<T> control) where T : ActionEditorControl<T>
        {
            this._controls.Add(control);
            return (T)control;
        }

        // The plugin's word that a list's items changed: the app asks again.
        public void ListboxItemsChanged(String controlName) { Host.Service.EditorChanged(this.Owner, controlName); }

        internal ActionEditorListboxItemsRequestedEventArgs RequestItems(ActionEditorState state, String control)
        {
            var e = new ActionEditorListboxItemsRequestedEventArgs(state, control);
            var h = this.ListboxItemsRequested;
            if (h != null) h(this, e);
            return e;
        }

        internal void ValueChanged(ActionEditorState state, String control)
        {
            var h = this.ControlValueChanged;
            if (h != null) h(this, new ActionEditorControlValueChangedEventArgs(state, control));
        }

        internal void Start(ActionEditorState state)
        {
            var h = this.Started;
            if (h != null) h(this, new ActionEditorStartedEventArgs(state));
        }
    }

    public abstract class ActionEditorAction : PluginAction
    {
        protected ActionEditorAction()
        {
            this.ActionEditor = new ActionEditor(this);
            this.IsEnabled = true;
        }

        public ActionEditor ActionEditor { get; private set; }

        public Plugin Plugin { get; private set; }

        public Boolean IsEnabled { get; set; }

        internal override void Attach(Plugin plugin) { this.Plugin = plugin; }

        internal override Boolean Enabled { get { return this.IsEnabled; } }

        protected internal override Boolean OnLoad() { return base.OnLoad(); }

        protected internal override Boolean OnUnload() { return base.OnUnload(); }

        protected internal virtual Boolean RunCommand(ActionEditorActionParameters actionParameters) { return false; }

        protected internal virtual String GetCommandDisplayName(ActionEditorActionParameters actionParameters) { return null; }

        public void ActionImageChanged() { Host.Service.ImageChanged(this, null); }
    }

    public abstract class ActionEditorCommand : ActionEditorAction
    {
        protected ActionEditorCommand() { }

        protected ActionEditorCommand(DeviceType supportedDevices) { }

        internal override Boolean IsAdjustment { get { return false; } }

        protected internal virtual BitmapImage GetCommandImage(ActionEditorActionParameters actionParameters,
                                                               Int32 imageWidth, Int32 imageHeight)
        {
            return null;
        }
    }

    public abstract class ActionEditorAdjustment : ActionEditorAction
    {
        protected ActionEditorAdjustment(Boolean hasReset) { this.HasReset = hasReset; }

        protected ActionEditorAdjustment(Boolean hasReset, DeviceType supportedDevices) : this(hasReset) { }

        public Boolean HasReset { get; private set; }

        internal override Boolean IsAdjustment { get { return true; } }

        protected internal virtual Boolean ApplyAdjustment(ActionEditorActionParameters actionParameters, Int32 diff)
        {
            return false;
        }

        protected internal virtual String GetAdjustmentValue(ActionEditorActionParameters actionParameters) { return null; }

        protected internal virtual String GetAdjustmentDisplayName(ActionEditorActionParameters actionParameters) { return null; }

        protected internal virtual BitmapImage GetAdjustmentImage(ActionEditorActionParameters actionParameters,
                                                                  Int32 imageWidth, Int32 imageHeight)
        {
            return null;
        }

        public void AdjustmentValueChanged() { Host.Service.ImageChanged(this, null); }
    }

    // Several states, kept per set of values (each binding is its own).
    public abstract class MultistateActionEditorCommand : ActionEditorCommand
    {
        private readonly List<String> _states = new List<String>();
        private readonly Dictionary<String, Int32> _current = new Dictionary<String, Int32>();

        protected MultistateActionEditorCommand() { }

        protected MultistateActionEditorCommand(DeviceType supportedDevices) { }

        public String AddState(String name, String displayName) { this._states.Add(displayName ?? name); return name; }

        public String AddState(String name, String displayName, String description) { return this.AddState(name, displayName); }

        public Int32 GetCurrentState(ActionEditorActionParameters actionParameters)
        {
            Int32 i;
            return this._current.TryGetValue(actionParameters.Key(), out i) ? i : 0;
        }

        public Int32 SetCurrentState(ActionEditorActionParameters actionParameters, Int32 stateIndex)
        {
            var n = Math.Max(1, this._states.Count);
            var i = ((stateIndex % n) + n) % n;
            this._current[actionParameters.Key()] = i;
            this.ActionImageChanged();
            return i;
        }

        public Int32 ToggleCurrentState(ActionEditorActionParameters actionParameters)
        {
            return this.SetCurrentState(actionParameters, this.GetCurrentState(actionParameters) + 1);
        }

        protected internal override BitmapImage GetCommandImage(ActionEditorActionParameters actionParameters,
                                                                Int32 imageWidth, Int32 imageHeight)
        {
            return this.GetCommandImage(actionParameters, this.GetCurrentState(actionParameters), imageWidth, imageHeight);
        }

        protected internal virtual BitmapImage GetCommandImage(ActionEditorActionParameters actionParameters,
                                                               Int32 stateIndex, Int32 imageWidth, Int32 imageHeight)
        {
            return null;
        }

        protected internal override String GetCommandDisplayName(ActionEditorActionParameters actionParameters)
        {
            var i = this.GetCurrentState(actionParameters);
            return i < this._states.Count ? this._states[i] : null;
        }
    }
}
