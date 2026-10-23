// A Linux stand-in for the WindowsInput library (InputSimulator), which
// plugins bundle to send keys and scroll on Windows through SendInput.
// Written from that library's public shape alone, as plugins reference it:
// the same types and members, the keys going through the app's input
// backend instead (Loupedeck.LinuxHost.Input in our PluginApi).
//
// KeyDown and KeyUp hold and release keys on the desktop, so a modifier held
// while the wheel turns (Ctrl+scroll to zoom) works as it does on Windows;
// the app lets go of anything still held if the plugin exits. Mouse buttons
// and moves are not supported yet; they are logged.
using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Threading;
using Loupedeck.LinuxHost;
using WindowsInput.Native;

[assembly: AssemblyVersion("1.0.6.0")]
[assembly: AssemblyTitle("WindowsInput (Linux stand-in)")]

namespace WindowsInput
{
    public enum MouseButton
    {
        LeftButton,
        MiddleButton,
        RightButton,
    }

    public interface IInputDeviceStateAdaptor
    {
        Boolean IsKeyDown(VirtualKeyCode keyCode);
        Boolean IsKeyUp(VirtualKeyCode keyCode);
        Boolean IsHardwareKeyDown(VirtualKeyCode keyCode);
        Boolean IsHardwareKeyUp(VirtualKeyCode keyCode);
        Boolean IsTogglingKeyInEffect(VirtualKeyCode keyCode);
    }

    public interface IKeyboardSimulator
    {
        IMouseSimulator Mouse { get; }
        IKeyboardSimulator KeyDown(VirtualKeyCode keyCode);
        IKeyboardSimulator KeyPress(VirtualKeyCode keyCode);
        IKeyboardSimulator KeyPress(params VirtualKeyCode[] keyCodes);
        IKeyboardSimulator KeyUp(VirtualKeyCode keyCode);
        IKeyboardSimulator ModifiedKeyStroke(IEnumerable<VirtualKeyCode> modifierKeyCodes, IEnumerable<VirtualKeyCode> keyCodes);
        IKeyboardSimulator ModifiedKeyStroke(IEnumerable<VirtualKeyCode> modifierKeyCodes, VirtualKeyCode keyCode);
        IKeyboardSimulator ModifiedKeyStroke(VirtualKeyCode modifierKey, IEnumerable<VirtualKeyCode> keyCodes);
        IKeyboardSimulator ModifiedKeyStroke(VirtualKeyCode modifierKeyCode, VirtualKeyCode keyCode);
        IKeyboardSimulator TextEntry(String text);
        IKeyboardSimulator TextEntry(Char character);
        IKeyboardSimulator Sleep(Int32 millsecondsTimeout);
        IKeyboardSimulator Sleep(TimeSpan timeout);
    }

    public interface IMouseSimulator
    {
        Int32 MouseWheelClickSize { get; set; }
        IKeyboardSimulator Keyboard { get; }
        IMouseSimulator MoveMouseBy(Int32 pixelDeltaX, Int32 pixelDeltaY);
        IMouseSimulator MoveMouseTo(Double absoluteX, Double absoluteY);
        IMouseSimulator MoveMouseToPositionOnVirtualDesktop(Double absoluteX, Double absoluteY);
        IMouseSimulator LeftButtonDown();
        IMouseSimulator LeftButtonUp();
        IMouseSimulator LeftButtonClick();
        IMouseSimulator LeftButtonDoubleClick();
        IMouseSimulator MiddleButtonDown();
        IMouseSimulator MiddleButtonUp();
        IMouseSimulator MiddleButtonClick();
        IMouseSimulator MiddleButtonDoubleClick();
        IMouseSimulator RightButtonDown();
        IMouseSimulator RightButtonUp();
        IMouseSimulator RightButtonClick();
        IMouseSimulator RightButtonDoubleClick();
        IMouseSimulator XButtonDown(Int32 buttonId);
        IMouseSimulator XButtonUp(Int32 buttonId);
        IMouseSimulator XButtonClick(Int32 buttonId);
        IMouseSimulator XButtonDoubleClick(Int32 buttonId);
        IMouseSimulator VerticalScroll(Int32 scrollAmountInClicks);
        IMouseSimulator HorizontalScroll(Int32 scrollAmountInClicks);
        IMouseSimulator Sleep(Int32 millsecondsTimeout);
        IMouseSimulator Sleep(TimeSpan timeout);
    }

    public interface IInputSimulator
    {
        IKeyboardSimulator Keyboard { get; }
        IMouseSimulator Mouse { get; }
        IInputDeviceStateAdaptor InputDeviceState { get; }
    }

    public class InputSimulator : IInputSimulator
    {
        private readonly IKeyboardSimulator _keyboard;
        private readonly IMouseSimulator _mouse;
        private readonly IInputDeviceStateAdaptor _state;

        public InputSimulator(IKeyboardSimulator keyboardSimulator, IMouseSimulator mouseSimulator,
                              IInputDeviceStateAdaptor inputDeviceStateAdaptor)
        {
            this._keyboard = keyboardSimulator;
            this._mouse = mouseSimulator;
            this._state = inputDeviceStateAdaptor;
        }

        public InputSimulator()
        {
            this._keyboard = new KeyboardSimulator(this);
            this._mouse = new MouseSimulator(this);
            this._state = new WindowsInputDeviceStateAdaptor();
        }

        public IKeyboardSimulator Keyboard { get { return this._keyboard; } }

        public IMouseSimulator Mouse { get { return this._mouse; } }

        public IInputDeviceStateAdaptor InputDeviceState { get { return this._state; } }
    }

    public class KeyboardSimulator : IKeyboardSimulator
    {
        // Keys held with KeyDown, shared by every simulator (the keyboard is
        // one keyboard), for IsKeyDown and so a key is not held twice.
        internal static readonly HashSet<String> Held = new HashSet<String>();
        private static readonly String[] ModifierOrder = { "ctrl", "alt", "shift", "super" };

        private readonly IInputSimulator _parent;

        public KeyboardSimulator(IInputSimulator inputSimulator) { this._parent = inputSimulator; }

        public IMouseSimulator Mouse { get { return this._parent.Mouse; } }

        private static String Name(VirtualKeyCode key)
        {
            var name = Input.KeyName((Int32)key);
            if (name == null) Input.Log("WindowsInput: no key here for " + key + " (" + (Int32)key + ")");
            return name;
        }

        // Presses key with the given modifiers (held keys are held already).
        private void Press(IEnumerable<String> modifiers, String key)
        {
            if (key == null) return;
            var mods = new HashSet<String>(modifiers.Where(m => m != null));
            var parts = ModifierOrder.Where(mods.Contains).ToList();
            if (!parts.Contains(key)) parts.Add(key);
            Input.SendKeys(String.Join("+", parts));
        }

        public IKeyboardSimulator KeyDown(VirtualKeyCode keyCode)
        {
            var name = Name(keyCode);
            if (name == null) return this;
            lock (Held)
                if (Held.Add(name)) Input.KeyDown(name);
            return this;
        }

        public IKeyboardSimulator KeyUp(VirtualKeyCode keyCode)
        {
            var name = Name(keyCode);
            if (name == null) return this;
            lock (Held)
                if (Held.Remove(name)) Input.KeyUp(name);
            return this;
        }

        public IKeyboardSimulator KeyPress(VirtualKeyCode keyCode)
        {
            this.Press(new String[0], Name(keyCode));
            return this;
        }

        public IKeyboardSimulator KeyPress(params VirtualKeyCode[] keyCodes)
        {
            foreach (var k in keyCodes ?? new VirtualKeyCode[0]) this.KeyPress(k);
            return this;
        }

        public IKeyboardSimulator ModifiedKeyStroke(IEnumerable<VirtualKeyCode> modifierKeyCodes, IEnumerable<VirtualKeyCode> keyCodes)
        {
            var mods = (modifierKeyCodes ?? new VirtualKeyCode[0]).Select(Name).ToList();
            foreach (var k in keyCodes ?? new VirtualKeyCode[0]) this.Press(mods, Name(k));
            return this;
        }

        public IKeyboardSimulator ModifiedKeyStroke(IEnumerable<VirtualKeyCode> modifierKeyCodes, VirtualKeyCode keyCode)
        {
            return this.ModifiedKeyStroke(modifierKeyCodes, new[] { keyCode });
        }

        public IKeyboardSimulator ModifiedKeyStroke(VirtualKeyCode modifierKey, IEnumerable<VirtualKeyCode> keyCodes)
        {
            return this.ModifiedKeyStroke(new[] { modifierKey }, keyCodes);
        }

        public IKeyboardSimulator ModifiedKeyStroke(VirtualKeyCode modifierKeyCode, VirtualKeyCode keyCode)
        {
            return this.ModifiedKeyStroke(new[] { modifierKeyCode }, new[] { keyCode });
        }

        public IKeyboardSimulator TextEntry(String text)
        {
            Input.SendText(text);
            return this;
        }

        public IKeyboardSimulator TextEntry(Char character) { return this.TextEntry(character.ToString()); }

        public IKeyboardSimulator Sleep(Int32 millsecondsTimeout)
        {
            Thread.Sleep(millsecondsTimeout);
            return this;
        }

        public IKeyboardSimulator Sleep(TimeSpan timeout)
        {
            Thread.Sleep(timeout);
            return this;
        }
    }

    public class MouseSimulator : IMouseSimulator
    {
        private readonly IInputSimulator _parent;

        public MouseSimulator(IInputSimulator inputSimulator)
        {
            this._parent = inputSimulator;
            this.MouseWheelClickSize = 120;
        }

        public Int32 MouseWheelClickSize { get; set; }

        public IKeyboardSimulator Keyboard { get { return this._parent.Keyboard; } }

        private IMouseSimulator Unsupported(String what)
        {
            Input.Log("WindowsInput: " + what + " is not supported here yet");
            return this;
        }

        public IMouseSimulator MoveMouseBy(Int32 pixelDeltaX, Int32 pixelDeltaY) { return this.Unsupported("moving the mouse"); }
        public IMouseSimulator MoveMouseTo(Double absoluteX, Double absoluteY) { return this.Unsupported("moving the mouse"); }
        public IMouseSimulator MoveMouseToPositionOnVirtualDesktop(Double absoluteX, Double absoluteY) { return this.Unsupported("moving the mouse"); }
        public IMouseSimulator LeftButtonDown() { return this.Unsupported("mouse buttons"); }
        public IMouseSimulator LeftButtonUp() { return this.Unsupported("mouse buttons"); }
        public IMouseSimulator LeftButtonClick() { return this.Unsupported("mouse buttons"); }
        public IMouseSimulator LeftButtonDoubleClick() { return this.Unsupported("mouse buttons"); }
        public IMouseSimulator MiddleButtonDown() { return this.Unsupported("mouse buttons"); }
        public IMouseSimulator MiddleButtonUp() { return this.Unsupported("mouse buttons"); }
        public IMouseSimulator MiddleButtonClick() { return this.Unsupported("mouse buttons"); }
        public IMouseSimulator MiddleButtonDoubleClick() { return this.Unsupported("mouse buttons"); }
        public IMouseSimulator RightButtonDown() { return this.Unsupported("mouse buttons"); }
        public IMouseSimulator RightButtonUp() { return this.Unsupported("mouse buttons"); }
        public IMouseSimulator RightButtonClick() { return this.Unsupported("mouse buttons"); }
        public IMouseSimulator RightButtonDoubleClick() { return this.Unsupported("mouse buttons"); }
        public IMouseSimulator XButtonDown(Int32 buttonId) { return this.Unsupported("mouse buttons"); }
        public IMouseSimulator XButtonUp(Int32 buttonId) { return this.Unsupported("mouse buttons"); }
        public IMouseSimulator XButtonClick(Int32 buttonId) { return this.Unsupported("mouse buttons"); }
        public IMouseSimulator XButtonDoubleClick(Int32 buttonId) { return this.Unsupported("mouse buttons"); }

        public IMouseSimulator VerticalScroll(Int32 scrollAmountInClicks)
        {
            Input.Scroll(scrollAmountInClicks);
            return this;
        }

        public IMouseSimulator HorizontalScroll(Int32 scrollAmountInClicks)
        {
            Input.ScrollHorizontally(scrollAmountInClicks);
            return this;
        }

        public IMouseSimulator Sleep(Int32 millsecondsTimeout)
        {
            Thread.Sleep(millsecondsTimeout);
            return this;
        }

        public IMouseSimulator Sleep(TimeSpan timeout)
        {
            Thread.Sleep(timeout);
            return this;
        }
    }

    public class WindowsInputDeviceStateAdaptor : IInputDeviceStateAdaptor
    {
        // Only what this library holds is known; the real keyboard is not
        // readable from here.
        public Boolean IsKeyDown(VirtualKeyCode keyCode)
        {
            var name = Input.KeyName((Int32)keyCode);
            lock (KeyboardSimulator.Held) return name != null && KeyboardSimulator.Held.Contains(name);
        }

        public Boolean IsKeyUp(VirtualKeyCode keyCode) { return !this.IsKeyDown(keyCode); }

        public Boolean IsHardwareKeyDown(VirtualKeyCode keyCode) { return this.IsKeyDown(keyCode); }

        public Boolean IsHardwareKeyUp(VirtualKeyCode keyCode) { return !this.IsKeyDown(keyCode); }

        public Boolean IsTogglingKeyInEffect(VirtualKeyCode keyCode) { return false; }
    }
}
