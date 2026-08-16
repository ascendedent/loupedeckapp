# macOS

The app runs on a Mac. A Loupedeck CT has been driven from one, the suite is
green there against two Qt generations, and the dependency floor now reaches
Mojave. What has not been proven is everything sitting behind the Accessibility
permission, and 10.14 and 10.15 themselves, which nobody has run this on.

Verified on macOS 26.4, Apple Silicon, with a Loupedeck CT attached, against
both PySide6 6.2.4 / Python 3.10 and PySide6 6.11 / Python 3.14.

The same arrangement as [LIVE-TESTING.md](LIVE-TESTING.md), for the same
reason: guesses are more useful when they are labelled, so the confidence
column below still says which is which.

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
| Input (`input_backend.py`) | ydotool / xdotool | `MacBackend`, AppleScript via `osascript` | Selected and reported healthy on a Mac; no keystroke has been seen landing, because that needs Accessibility |
| Focused app (`window_watcher.py`) | kdotool, KWin | `MacWatcher`, frontmost bundle id | Same: chosen correctly, gated behind the same permission |
| Paths (`app_paths.py`) | `~/.config/loupedeckapp` | `~/Library/Application Support/LoupedeckApp` | **Verified**; the directory is created there |
| Action library (`action_library.py`) | ctrl-based | command-based, `open -a Terminal` | Unit-tested both ways; the commands themselves have not been fired |
| Device (`Loupedeck` lib, pyserial) | `/dev/ttyACM*` | `/dev/cu.usbmodem*` | **Verified** on a CT: enumeration, handshake, serial, version and model all correct |

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
.venv/bin/pip install -e ".[device,macos]"
# on 10.14 or 10.15 only, and note it needs a 3.10 interpreter:
# .venv/bin/pip install -e ".[legacy-macos]"
.venv/bin/python qml_app.py
```

1. **Does it start?** It does on 26.4. On 10.14 or 10.15 this is the step most
   likely to fail, and if it does, check which PySide6 pip actually chose
   before anything else.
2. **What does the Setup dialog say?** It runs five checks; all five pass on
   26.4 with the `macos` extra installed. Without pyobjc the media one turns
   into advice rather than a failure.
3. **Is the device found?** `.venv/bin/python scripts/verify/probe_device.py`
   prints the USB port and what the app makes of it. A CT comes up as
   `/dev/cu.usbmodem*` with vendor `2ec2:0003`; if nothing is found, that name
   is the first thing to check.
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
- **Minimum version.** 10.14 was a statement of intent; it is now reachable,
  though still not run there. PySide6 6.2.4 is the last release with a
  `macosx_10_14` wheel, and Qt 6.2 is the last Qt that lists 10.14 as
  supported, so that is the ceiling for Mojave and it caps Python at 3.10. The
  `legacy-macos` extra pins it. Asking for it explicitly is not optional on
  those releases: 6.3 through 6.5.2 ship wheels tagged `macosx_10_9` while
  actually needing 10.15 or 11, so pip installs them on Mojave without
  complaint and the app then fails to start.

  Two QML spellings had to change to make one codebase span both. `MultiEffect`
  (`QtQuick.Effects`) arrived in 6.5 and `ColorDialog` in `QtQuick.Dialogs`
  arrived in 6.4; they are now `OpacityMask` from `Qt5Compat.GraphicalEffects`
  and `ColorDialog` from `Qt.labs.platform`, both of which exist in 6.2 and in
  current Qt. Anything added to the QML wants checking against 6.2 before it
  lands, because the failure is a dialog that silently is not a type rather
  than a build error.

## Reporting

[MACOS-TESTING.md](MACOS-TESTING.md) has the steps and the template. Corrections
to this file are more valuable than anything else, since everything in it is a
guess until someone says otherwise.
