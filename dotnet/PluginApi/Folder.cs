// Dynamic folders: a page of the device the plugin fills itself (Krita's
// tool pages, a playlist). A key bound to the folder opens it; the plugin
// says which commands go on the keys and which adjustments on the knobs, and
// can change them while it is open.
//
// Shapes from compiled plugins (Krita, VLC): overrides are public, and
// DisplayName/GroupName/Description are referenced on the folder itself.
// Inside the folder, CreateCommandName(x) and CreateAdjustmentName(x) name an
// item; callbacks get the raw x back. Here those names are
// "<folder>/cmd/<x>" and "<folder>/adj/<x>", which the app binds like any
// other plugin action.
namespace Loupedeck
{
    using System;
    using System.Collections.Generic;
    using System.Linq;

    public enum PluginDynamicFolderNavigation
    {
        None = 0,
        ButtonArea = 1,
        EncoderArea = 2,
    }

    public abstract class PluginDynamicFolder : PluginAction
    {
        internal const String CommandTag = "/cmd/";
        internal const String AdjustmentTag = "/adj/";

        // Plugins put these in their lists to place the navigation keys
        // themselves (with Navigation = None).
        public static readonly String NavigateUpActionName = "__folder_up__";
        public static readonly String NavigateLeftActionName = "__folder_left__";
        public static readonly String NavigateRightActionName = "__folder_right__";

        protected PluginDynamicFolder()
        {
            this.Navigation = PluginDynamicFolderNavigation.ButtonArea;
        }

        public new String DisplayName { get { return base.DisplayName; } set { base.DisplayName = value; } }

        public new String GroupName { get { return base.GroupName; } set { base.GroupName = value; } }

        public new String Description { get { return base.Description; } set { base.Description = value; } }

        public Plugin Plugin { get; private set; }

        public PluginDynamicFolderNavigation Navigation { get; set; }

        internal override void Attach(Plugin plugin) { this.Plugin = plugin; }

        internal override Boolean IsAdjustment { get { return false; } }

        // During plugin load and unload.
        public virtual Boolean Load() { return true; }

        public virtual Boolean Unload() { return true; }

        // When the first device opens it, and when the last one leaves.
        public virtual Boolean Activate() { return true; }

        public virtual Boolean Deactivate() { return true; }

        public virtual PluginDynamicFolderNavigation GetNavigationArea(DeviceType deviceType) { return this.Navigation; }

        // The key that opens the folder.
        public virtual String GetButtonDisplayName(PluginImageSize imageSize) { return null; }

        public virtual BitmapImage GetButtonImage(PluginImageSize imageSize) { return null; }

        public virtual IEnumerable<String> GetButtonPressActionNames(DeviceType deviceType)
        {
            return this.GetButtonPressActionNames();
        }

        public virtual IEnumerable<String> GetButtonPressActionNames() { return Enumerable.Empty<String>(); }

        public virtual IEnumerable<String> GetEncoderRotateActionNames(DeviceType deviceType)
        {
            return this.GetEncoderRotateActionNames();
        }

        public virtual IEnumerable<String> GetEncoderRotateActionNames() { return Enumerable.Empty<String>(); }

        public virtual IEnumerable<String> GetEncoderPressActionNames(DeviceType deviceType)
        {
            return this.GetEncoderPressActionNames();
        }

        public virtual IEnumerable<String> GetEncoderPressActionNames() { return Enumerable.Empty<String>(); }

        public String CreateCommandName(String actionParameter) { return this.Name + CommandTag + actionParameter; }

        public String CreateAdjustmentName(String actionParameter) { return this.Name + AdjustmentTag + actionParameter; }

        public virtual void RunCommand(String actionParameter) { }

        public virtual void ApplyAdjustment(String actionParameter, Int32 diff) { }

        public virtual String GetCommandDisplayName(String actionParameter, PluginImageSize imageSize) { return null; }

        public virtual BitmapImage GetCommandImage(String actionParameter, PluginImageSize imageSize) { return null; }

        public virtual String GetAdjustmentDisplayName(String actionParameter, PluginImageSize imageSize) { return null; }

        public virtual BitmapImage GetAdjustmentImage(String actionParameter, PluginImageSize imageSize) { return null; }

        public virtual String GetAdjustmentValue(String actionParameter) { return null; }

        public virtual Boolean ProcessButtonEvent(String actionParameter, DeviceButtonEvent buttonEvent) { return false; }

        public virtual Boolean ProcessEncoderEvent(String actionParameter, DeviceEncoderEvent encoderEvent) { return false; }

        public virtual Boolean ProcessTouchEvent(String actionParameter, DeviceTouchEvent touchEvent) { return false; }

        // -- telling the device --
        public void ButtonActionNamesChanged() { Host.Service.FolderChanged(this); }

        public void EncoderActionNamesChanged() { Host.Service.FolderChanged(this); }

        public void CommandImageChanged(String actionParameter)
        {
            Host.Service.ItemChanged(this.CreateCommandName(actionParameter));
        }

        public void AdjustmentValueChanged(String actionParameter)
        {
            Host.Service.ItemChanged(this.CreateAdjustmentName(actionParameter));
        }

        public void ActionImageChanged() { Host.Service.ImageChanged(this, null); }

        public void Close() { Host.Service.FolderClose(this); }
    }
}
