# Testing on macOS

This app is developed on Linux, against a Loupedeck CT. It has macOS support
written into it and **none of that has ever run on a Mac**, because there is no
Mac here. If you have one and a Loupedeck of any kind, an hour of your time
would turn a pile of educated guesses into something known.

You do not need to read any code. Run through the steps below and send back what
happened, including the parts that went fine.

- **Report an issue:** https://github.com/ascendedent/loupedeckapp/issues
- Title it `macOS report:` so it is easy to find.
- [docs/MACOS.md](MACOS.md) is the same material aimed at someone changing the
  code. This one is for testing.

---

## What this app is

An open-source configuration app for Loupedeck devices: assign images, labels
and actions to the keys, encoders, side screens and (on a CT) the wheel,
organise them into workspaces, and have profiles switch automatically as you
change application. It exists because the official software is Windows and macOS
only, so the Linux side of it is well tested and the Mac side is a promise.

## What is expected to work, and what is not

Everything except the four platform seams is shared, and that part has a test
suite and daily use behind it: profiles, the editor, actions, macros, encoder
tuning, the tray, workspaces, dynamic switching logic.

| Area | Expectation | Why |
|---|---|---|
| Starting up, editing profiles, saving | Should work | No platform code involved |
| Finding the device | Should work | pyserial is cross-platform; macOS names ports `/dev/cu.usbmodem*` |
| Drawing to the device | Should work | Same protocol on every platform |
| Sending keystrokes | **Untested** | AppleScript through `osascript`; needs Accessibility permission |
| Detecting the focused app | **Untested** | AppleScript; needs the same permission |
| Where files are stored | Untested but simple | `~/Library/Application Support/LoupedeckApp` |
| Menu bar item (the "tray") | Untested | Qt turns a tray icon into a menu bar item |
| Media keys | **Not implemented** | Linux uses playerctl, which does not exist on macOS |
| Scrolling on a knob | Partly | Falls back to arrow keys; AppleScript has no scroll verb |
| Start with the session | **Not implemented** | Writes a Linux autostart file macOS does not read |
| A double-clickable `.app` | Does not exist | Run it from a terminal for now |

The most likely outcome is that it starts, finds your device, draws to it, and
then does nothing when you press a key until you grant Accessibility permission.
That is the interesting part.

---

## Setting it up

You need Python 3.9 or newer and git.

```bash
git clone https://github.com/ascendedent/loupedeckapp
cd loupedeckapp
python3 -m venv .venv
.venv/bin/pip install -e ".[device]"
.venv/bin/python qml_app.py
```

If it will not start at all, that is a report on its own: send the whole error.

---

## What to check

Work down the list. Stop wherever it breaks and say where.

### 1. It starts

Does a window appear? What does the device pill in the top left say: a model
name, and a green or grey dot?

### 2. The Setup dialog

It opens by itself on a first run. Five checks, two of which take a macOS
branch that has never run. **A screenshot of this is the single most useful
thing you can send.**

### 3. The device is found

```bash
.venv/bin/python scripts/verify/probe_device.py
```

Prints the USB port, what the firmware says about itself, and what the app made
of it. Paste all of it. macOS names serial ports `/dev/cu.usbmodem*`; if nothing
is found, that is the first thing to check.

Close the main app before running this: it holds the port.

### 4. Images land on the device

```bash
.venv/bin/python scripts/verify/render_test.py
```

Draws numbered, coloured patterns to the keys and screens and asks what you
actually see after each one. Be literal. Photographs are very welcome.

### 5. Keystrokes work

This is the one. In the app, drag **Copy** onto a key, press **Save**, then
press that key on the device with a text editor focused.

- Nothing happened? Expected on a first run. Open **System Settings > Privacy &
  Security > Accessibility** and allow either the app or the Terminal you
  started it from, then use **Check again** in the Setup dialog and try once
  more.
- Say **which** of the two you had to allow. That is a real question we cannot
  answer from here.
- Then try a few more: `cmd+c`, typing text, a function key.

### 6. The focused app is detected

Turn on **Dynamic** in the top bar. Switch to another application and back. The
right-hand panel names what it thinks is focused; on macOS that should be a
bundle id like `com.apple.Safari`. Add an app from the picker and see whether
the list of installed applications is right.

### 7. Everything else

Poke at whatever you like: workspaces, the menu bar item, macros, encoder feel,
the on-screen keyboard action. Anything that looks wrong is worth a line.

---

## What to send back

Copy this and fill it in. A partial report is worth sending; steps 1 and 2
alone are more than we know now.

```
macOS version:        e.g. 14.5 Sonoma, Apple silicon / Intel
Loupedeck model:      CT / Live / Live S
How you started it:   terminal / something else
Python version:       .venv/bin/python --version

1. Starts:            yes / no + error
   Device pill says:
2. Setup dialog:      (screenshot, or what each of the five checks said)
3. probe_device.py:
   (paste)
4. render_test.py:
   (paste, plus photos if you can)
5. Keystrokes:        worked / did nothing / worked after granting Accessibility
   Granted to:        the app / Terminal / other
   Which ones worked:
6. Focused app:       what the panel showed, and whether switching worked
   Installed apps:    did the picker list your applications correctly?
7. Anything else:
```

If you have a Live or Live S rather than a CT, please also read
[LIVE-TESTING.md](LIVE-TESTING.md): those models are unverified on every
platform, and your report would cover both at once.

---

## What happens with it

Reports go into the four adapter files, which is where every platform difference
lives. Where a report contradicts anything written here or in
[MACOS.md](MACOS.md), the report wins: it is the only source with a Mac behind
it.

The parts that do not touch the platform have their own checks, which you can
run without a device and which should pass on your machine too:

```bash
.venv/bin/python tests/run_all.py
```

If those fail on macOS, that is a bug worth reporting on its own.
