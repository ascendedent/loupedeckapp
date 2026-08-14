# macOS

The app has macOS adapters and **none of them have run on a Mac**. There is no
Mac on the machine this was written on. This file says what exists, what it is
based on, and what someone with a Mac would need to check.

The same arrangement as [LIVE-TESTING.md](LIVE-TESTING.md), for the same
reason: guesses are more useful when they are labelled.

**Testing it rather than changing it?** [MACOS-TESTING.md](MACOS-TESTING.md) is
the same ground aimed at someone with a Mac and a device, with the steps to run
and a template for what to send back.

---

## What exists

The core has no Qt or platform code in it, and every platform difference goes
through one of three seams, so "supporting macOS" means filling in three
adapters rather than changing the app.

| Seam | Linux | macOS | Confidence |
|---|---|---|---|
| Input (`input_backend.py`) | ydotool / xdotool | `MacBackend`, AppleScript via `osascript` | Untested; the combo translation is unit-tested |
| Focused app (`window_watcher.py`) | kdotool, KWin | `MacWatcher`, frontmost bundle id | Untested |
| Paths (`app_paths.py`) | `~/.config/loupedeckapp` | `~/Library/Application Support/LoupedeckApp` | Untested but simple |
| Action library (`action_library.py`) | ctrl-based | command-based, `open -a Terminal` | Untested |
| Device (`Loupedeck` lib, pyserial) | `/dev/ttyACM*` | `/dev/cu.usbmodem*` | Should work; pyserial is cross-platform |

`tests/test_macos.py` covers what can be covered from here: the combo
translation, the escaping, the platform gates, and the setup advice. It cannot
tell you whether AppleScript actually does what its documentation says.

## The permission

macOS does not let one application send keystrokes to another without
**Accessibility** rights, granted in *System Settings > Privacy & Security >
Accessibility*. Until it is granted, every action silently does nothing, which
is exactly the failure this app tries hardest to make visible: the Setup dialog
names it, and `MacBackend.health()` recognises the `1002` error macOS returns.

Reading the frontmost application needs the same permission, so dynamic mode
fails the same way.

Whether the permission attaches to the app or to the terminal that launched it
depends on how it was started, and that is one of the things a report should
say.

## What to check, in order

Install and run:

```bash
git clone https://github.com/ascendedent/loupedeckapp
cd loupedeckapp
python3 -m venv .venv
.venv/bin/pip install -e ".[device]"
.venv/bin/python qml_app.py
```

1. **Does it start?** PySide6 and the QML have no reason not to work, but this
   has never been seen.
2. **What does the Setup dialog say?** It runs five checks; on a Mac two of
   them take a macOS-specific branch that has never run.
3. **Is the device found?** `.venv/bin/python scripts/verify/probe_device.py`
   prints the USB port and what the app makes of it. macOS names serial ports
   `/dev/cu.usbmodem*`; if nothing is found, that name is the first thing to
   check.
4. **Do keystrokes work?** Bind `cmd+c` to a key and press it. If nothing
   happens, grant Accessibility and use Check again in the Setup dialog.
5. **Does the frontmost app get detected?** Turn on Dynamic mode and switch
   applications. The app bindings panel shows what it thinks is focused; on
   macOS it should be a bundle id like `com.apple.Safari`.
6. **Where does it store things?** `~/Library/Application Support/LoupedeckApp`.

## Known gaps

- **Scrolling and media keys** go through Quartz, from pyobjc, installed with
  the `[macos]` extra. Neither is reachable from AppleScript: media keys are not
  in the key code System Events addresses, and there is no scroll verb at all.
  Without pyobjc a media action does nothing and a scroll bound to a knob sends
  arrow keys instead; the setup checks say so and name the install. **The Quartz
  paths have never run**, only their packing and their fallbacks are tested.
- **The tray** uses `QSystemTrayIcon`, which becomes a menu bar item on macOS.
  It should work; it has not been seen.
- **Autostart** writes an XDG entry, which macOS does not read. The equivalent
  is a `LaunchAgent` plist in `~/Library/LaunchAgents`. `autostart.py` is the
  only file that would need to change.
- **No `.app` bundle.** Running from a checkout is the only tested path, and
  packaging with py2app or briefcase has not been attempted. Note that a
  bundled app and a terminal-launched one are treated as different subjects by
  the Accessibility permission.
- **Minimum version.** The project targets 10.14 Mojave, which is a statement
  of intent rather than a tested claim. PySide6 6.5+ generally wants a newer
  macOS than that, and if that turns out to be incompatible the target moves,
  not the dependency.

## Reporting

[MACOS-TESTING.md](MACOS-TESTING.md) has the steps and the template. Corrections
to this file are more valuable than anything else, since everything in it is a
guess until someone says otherwise.
