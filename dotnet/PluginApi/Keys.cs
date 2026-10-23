// Keys a plugin can send through ClientApplication.SendKeyboardShortcut.
//
// The values are Windows virtual-key codes and the modifier flags are
// Control 1, Alt 2, Shift 4: both read from compiled plugins (Microsoft Teams:
// Ctrl+Shift+M compiles to (77, 5); Affinity Photo: Alt+[ to (219, 2),
// Ctrl+Alt+R to (82, 3)), not guessed. Names follow what plugin sources use
// (KeyA, Key0, Oem4, Back, RMENU...), with the usual aliases beside them.
namespace Loupedeck
{
    using System;
    using System.Collections.Generic;

    [Flags]
    public enum ModifierKey
    {
        None = 0,
        Control = 1,
        Alt = 2,
        Shift = 4,
        Windows = 8,
    }

    public enum VirtualKeyCode
    {
        None = 0,
        Back = 0x08, Tab = 0x09, Clear = 0x0C, Return = 0x0D, Enter = 0x0D,
        Shift = 0x10, Control = 0x11, Menu = 0x12, Pause = 0x13, CapsLock = 0x14,
        Escape = 0x1B, Space = 0x20, Prior = 0x21, PageUp = 0x21, Next = 0x22, PageDown = 0x22,
        End = 0x23, Home = 0x24, Left = 0x25, Up = 0x26, Right = 0x27, Down = 0x28,
        Select = 0x29, Print = 0x2A, Execute = 0x2B, Snapshot = 0x2C, PrintScreen = 0x2C,
        Insert = 0x2D, Delete = 0x2E, Help = 0x2F,
        Key0 = 0x30, Key1, Key2, Key3, Key4, Key5, Key6, Key7, Key8, Key9,
        KeyA = 0x41, KeyB, KeyC, KeyD, KeyE, KeyF, KeyG, KeyH, KeyI, KeyJ, KeyK, KeyL, KeyM,
        KeyN, KeyO, KeyP, KeyQ, KeyR, KeyS, KeyT, KeyU, KeyV, KeyW, KeyX, KeyY, KeyZ,
        LWIN = 0x5B, RWIN = 0x5C, Apps = 0x5D, Sleep = 0x5F,
        Numpad0 = 0x60, Numpad1, Numpad2, Numpad3, Numpad4, Numpad5, Numpad6, Numpad7, Numpad8, Numpad9,
        Multiply = 0x6A, Add = 0x6B, Separator = 0x6C, Subtract = 0x6D, Decimal = 0x6E, Divide = 0x6F,
        F1 = 0x70, F2, F3, F4, F5, F6, F7, F8, F9, F10, F11, F12,
        F13, F14, F15, F16, F17, F18, F19, F20, F21, F22, F23, F24,
        NumLock = 0x90, ScrollLock = 0x91,
        LSHIFT = 0xA0, RSHIFT = 0xA1, LCONTROL = 0xA2, RCONTROL = 0xA3, LMENU = 0xA4, RMENU = 0xA5,
        BrowserBack = 0xA6, BrowserForward = 0xA7, BrowserRefresh = 0xA8, BrowserStop = 0xA9,
        BrowserSearch = 0xAA, BrowserFavorites = 0xAB, BrowserHome = 0xAC,
        VolumeMute = 0xAD, VolumeDown = 0xAE, VolumeUp = 0xAF,
        MediaNextTrack = 0xB0, MediaPrevTrack = 0xB1, MediaStop = 0xB2, MediaPlayPause = 0xB3,
        Oem1 = 0xBA, OemPlus = 0xBB, Plus = 0xBB, OemComma = 0xBC, Comma = 0xBC,
        OemMinus = 0xBD, Minus = 0xBD, OemPeriod = 0xBE, Period = 0xBE,
        Oem2 = 0xBF, Oem3 = 0xC0, Oem4 = 0xDB, Oem5 = 0xDC, Oem6 = 0xDD, Oem7 = 0xDE, Oem8 = 0xDF,
        Oem102 = 0xE2,
    }

    // A key code and modifiers as the app's hotkey text ("ctrl+shift+m").
    internal static class Keys
    {
        private static readonly Dictionary<Int32, String> Names = Build();

        private static Dictionary<Int32, String> Build()
        {
            var d = new Dictionary<Int32, String>
            {
                { 0x08, "backspace" }, { 0x09, "tab" }, { 0x0D, "enter" }, { 0x13, "pause" },
                { 0x14, "capslock" }, { 0x1B, "escape" }, { 0x20, "space" }, { 0x21, "pageup" },
                { 0x22, "pagedown" }, { 0x23, "end" }, { 0x24, "home" }, { 0x25, "left" }, { 0x26, "up" },
                { 0x27, "right" }, { 0x28, "down" }, { 0x2C, "printscreen" }, { 0x2D, "insert" },
                { 0x2E, "delete" }, { 0x5B, "super" }, { 0x5C, "super" }, { 0x5D, "menu" },
                // The keypad has no names in the app; the main-row keys do the same in most applications.
                { 0x6B, "equal" }, { 0x6D, "minus" }, { 0x6E, "period" }, { 0x6F, "slash" },
                { 0xA0, "shift" }, { 0xA1, "shift" }, { 0xA2, "ctrl" }, { 0xA3, "ctrl" },
                { 0xA4, "alt" }, { 0xA5, "alt" },
                { 0xAD, "mute" }, { 0xAE, "volumedown" }, { 0xAF, "volumeup" },
                { 0xB0, "nextsong" }, { 0xB1, "previoussong" }, { 0xB2, "stop" }, { 0xB3, "playpause" },
                { 0xBA, "semicolon" }, { 0xBB, "equal" }, { 0xBC, "comma" }, { 0xBD, "minus" },
                { 0xBE, "period" }, { 0xBF, "slash" }, { 0xC0, "grave" }, { 0xDB, "bracketleft" },
                { 0xDC, "backslash" }, { 0xDD, "bracketright" }, { 0xDE, "apostrophe" },
            };
            for (var i = 0; i < 10; i++)
            {
                d[0x30 + i] = i.ToString();
                d[0x60 + i] = i.ToString();
            }
            for (var c = 'a'; c <= 'z'; c++) d[0x41 + (c - 'a')] = c.ToString();
            for (var f = 1; f <= 24; f++) d[0x6F + f] = "f" + f;
            return d;
        }

        internal static String Combo(VirtualKeyCode key, ModifierKey modifiers)
        {
            String name;
            if (!Names.TryGetValue((Int32)key, out name)) return null;
            var parts = new List<String>();
            if ((modifiers & ModifierKey.Control) != 0) parts.Add("ctrl");
            if ((modifiers & ModifierKey.Alt) != 0) parts.Add("alt");
            if ((modifiers & ModifierKey.Shift) != 0) parts.Add("shift");
            if ((modifiers & ModifierKey.Windows) != 0) parts.Add("super");
            if (!parts.Contains(name)) parts.Add(name);
            return String.Join("+", parts);
        }
    }
}
