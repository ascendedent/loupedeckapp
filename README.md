# loupedeckapp

A native **Linux** configuration app for the **Loupedeck CT** (and Loupedeck Live / Live S): an
open-source stand-in for the official Loupedeck software, which is Windows/macOS only.

Assign images, background colours, text labels, LED colours and actions to every touch key, side
display, encoder, and (on the CT) the rotary dial and round wheel screen; organise them into
workspaces and nested submenus; and optionally auto-switch profiles based on the focused desktop
application. All from a modern, dark PySide6/QML interface.

> **Origin.** This project began as a fork of
> [flowernert/loupedeckapp](https://github.com/flowernert/loupedeckapp) (which targets the Loupedeck
> Live) and has grown into a standalone app focused on the **Loupedeck CT** with full Wayland
> support. Thanks to flowernert for the original groundwork.

---

## Supported hardware

| Device            | USB PID     | Status                                                                                   |
|-------------------|-------------|------------------------------------------------------------------------------------------|
| Loupedeck **CT**  | `2ec2:0003` | Primary target; full support incl. the 240×240 wheel screen, rotary dial, and CT buttons |
| Loupedeck **Live**| `2ec2:0004` | Supported, never tested on hardware ([help wanted](docs/LIVE-TESTING.md))                |
| Loupedeck **Live S** | `2ec2:0006` | Geometry from published specs, never tested ([help wanted](docs/LIVE-TESTING.md))      |

The model is detected from the USB product id. The vendored device library reports every model as
`LoupedeckLive`, so CT-specific behaviour is enabled only when a wheel/dial is present. The device
view draws only the controls the detected model has, so a Live shows no wheel and a Live S shows a
5-column grid with two dials and no side strips.

Set `LOUPEDECKAPP_MODEL` to `ct`, `live`, or `live-s` to override the detected model. That is there
for two cases: a device whose product id is not in the table above, and checking the device view for
a model you do not own. Profiles always store the widest grid (5 columns) and all eight workspaces,
so a file written on one model opens on another.

## Features

### Device control
- 4×3 touch-key grid, left/right side displays, and 6 side encoders (press + rotate).
- On the **CT**: the round **wheel screen** (renders big-endian 240×240), the rotary **dial**
  (press + rotate), and the CT function buttons (`home`, `undo`, `keyboard`, `enter`, `save`,
  `fn`, `a`-`e`).
- 8 workspaces on the physical buttons (`circle` + `1`-`7`), each with its own layout, plus nested
  **submenus**.

### Per-control styling
- **Images**: fit to the control (aspect preserved, never cropped or stretched). The inspector
  shows the exact target size for a pixel-perfect fill (90×90 keys, 60×90 side cells, 240×240 wheel).
- **Text labels**: on by default, auto-derived from the assigned action's name (e.g. `Copy`), with
  a per-control show/hide toggle so a label is never lost when you add an image. Placement
  top / middle / bottom, and three modes: **over** the image, on a **bar**, or **shrink** (image
  resized so the label sits beside it). Custom bar colour.
- **Background colour** behind an image, and **RGB LED colours** for the physical workspace and CT
  buttons.
- Everything renders both in the on-screen mirror and on the physical device.

### Actions
- `command`/launch, `hotkey`, `text`, `scroll`, `media` (MPRIS), `macro` (a sequence),
  `keyboard` (the desktop's on-screen keyboard), `workspace` (jump to a workspace), and
  `submenu` / `back` navigation.
- **Hotkey recorder** that captures a key combination when you press it, plus a **presets** picker
  that includes your machine's configured KDE global shortcuts.
- A searchable **action library** you drag onto controls, including scroll and volume. Search
  matches the action's value and type as well as its name, so `ctrl`, `scroll` or `vol up` all
  narrow the list. Dropping onto an encoder, the dial, or the wheel lets you pick the
  **press / rotate / touch** slot.

### Macros

Bind a sequence to one control. A macro is written a step per line:

```
hotkey ctrl+c
wait 200
hotkey alt+tab
text hello world
```

Steps are `hotkey`, `text`, `wait <ms>`, `scroll <direction> [count]`, `media`, `keyboard` and
`command`. Lines starting with `#` are comments.

The inspector offers **both** a step list (add, reorder, delete, with a dropdown per step) and the
raw text, switchable with one button. They edit the same value, so use whichever suits: the list
for building a macro, the text for pasting or editing one quickly. The text view reports the step
count and points at any line it cannot read, so a typo is visible without pressing the button and
wondering.

Macros run on their own worker: pressing a button never blocks the device while a macro with waits
in it plays out, and two macros run one after the other rather than interleaving.

### The fn layer

Every control can carry a **secondary binding**. Hold `fn` and controls fire that instead of their
usual one; a control with no secondary keeps its normal behaviour, so `fn` never makes anything go
dead.

`fn` is **hold** by default, which is how a modifier behaves. Click the `fn:` pill in the top bar
to switch it to **latch**, where a press sticks until you press it again and the key lights up to
show the layer is on. Either fn key drives the same layer. Changing workspace releases it, since
the key-up would otherwise land on a different page and leave it stuck.

Set a secondary from the inspector: each slot has an `fn` row under its normal binding.

Click the `fn:` pill in the top bar to choose the mode and the two key colours: one for while the
layer is on, one for while it is off. Leaving the off colour unset makes the fn keys behave like
any other button, taking the LED colour from the workspace.

### CT function buttons

New profiles start with the CT's labelled buttons wired to what they say: **home** goes to
workspace 1, **undo** and **save** send `ctrl+z` / `ctrl+s`, **enter** sends Enter, and **kbd**
toggles the desktop's on-screen keyboard (KDE's own, over DBus; `squeekboard` / `wvkbd` /
`onboard` elsewhere). `fn` is left unbound, being a modifier rather than an action.

This applies to **every** profile as it loads, not only new ones, and only to slots that are still
empty: anything you have bound yourself is left exactly as it is, and loading does not mark the
profile as changed. Set `"auto_bind_ct_buttons": false` in `~/.config/loupedeckapp/settings.json`
to leave unbound buttons unbound.

### Encoder feel

Per-control tuning for the six encoders and the CT dial, none of which the official app offers.
Set from the inspector when a rotate control is selected; stored per workspace and inherited into
submenus unless a submenu overrides it.

- **Invert** direction.
- **Speed presets**: Original, Slow 1/2, Slow 1/3, Fast 2x, Fast 3x. Slow banks detents and fires
  once per N (resetting if you reverse); Fast makes one detent worth N steps.
- **Acceleration**: optional, off by default. Turning at a normal pace behaves exactly as usual;
  spinning the control ramps up to 10x. Speed is measured from the gap between detents, so the
  first click of a turn is never accelerated and small corrections stay predictable.

Defaults are calibrated against measured hand speeds on a CT side encoder (deliberate turning
~189 ms between detents, a comfortable pace ~58 ms, a full spin ~8 ms). `scratch/probe_rotate.py`
re-measures this and suggests thresholds if the defaults do not suit you.

Acceleration pays off most on **scroll**, where the whole magnitude rides in one call. On a
**hotkey** it is limited by how fast keystrokes can be delivered (see below), so it mainly helps at
middling speeds.

### Workflow
- Three-column dark UI (PySide6 + QML): action library · live device mirror · inspector.
- **Draft editing**: edits update the on-screen mirror live and are pushed to the hardware only on
  **Save**; **Revert** discards the draft. Nothing throws a draft away without asking, and if
  dynamic mode wants to switch profile mid-edit it waits (shown in the top bar) rather than
  interrupting with a dialog or losing the work.
- **Copy / paste** a control's entire function onto another compatible control.
- **A starter profile** with Media, Editing and Browser workspaces, labelled and colour-coded,
  opened on a first run. After that the app reopens whatever profile you had last.
- **Inspector in collapsible sections** (Action, Appearance, Advanced), remembered as you move
  between controls.
- **Says what to do when there is nothing to see**: an unbound workspace, a search that matched
  nothing, and an empty profile list each explain themselves rather than looking broken.
- **Name your workspaces**. The header shows the name of the one on the device and falls back to
  "Workspace 3"; eight numbered keys say nothing about what is on them.
- **Switch workspace from the app** by clicking a round key or pressing `Ctrl+1`..`Ctrl+8`, rather
  than reaching over to the device.
- **Keyboard shortcuts**: `Ctrl+S` save, `Ctrl+R` revert, `Ctrl+F` search actions, `Ctrl+C` /
  `Ctrl+V` copy and paste a control, `Esc` leave a submenu or clear the selection. They stay out of
  the way while you are typing in a field.
- **Import / export** profiles as JSON. Importing checks the file before adding it, and never
  overwrites an existing profile: a name that is taken gets a numbered suffix.
- **Dynamic mode**: switches the active profile when the focused desktop app changes (KDE Wayland,
  via KWin scripting).
- **Brightness** control, remembered between runs and re-applied on reconnect.
- **Tells you when input is broken** rather than silently doing nothing, with the reason and a
  re-check button.
- **Survives unplugging**: the app connects when the device appears and reconnects when it comes
  back, returning to the workspace you were on. No restart needed.
- JSON profiles (schema v7, backward compatible with older profiles; unknown fields
  written by a newer build survive a load/save round-trip).

### Where your data lives

| | |
|---|---|
| Profiles you edit, app bindings, preferences | `~/.config/loupedeckapp/` (`$XDG_CONFIG_HOME` is respected) |
| Profiles and images shipped with the app | beside the code, never written to |

Profiles resolve **your copy first, then the bundled one**, so anything shipped with the app
appears in the list and editing it writes a copy rather than modifying the installation. Delete
that copy and the original comes back. Profiles left in the source tree by earlier versions are
copied across on first run, and the originals are left alone.

Set `LOUPEDECKAPP_CONFIG_DIR` to put user data somewhere else.

## Requirements

- **Linux**; Python 3 (developed on Fedora 44 / Python 3.14, KDE Plasma on **Wayland**).
- The device on `/dev/ttyACM0`, readable by your user (see [Device permissions](#device-permissions)).

**Python packages**
- `PySide6` (QML UI), `pyserial`, `pillow`, and the devleaks
  [`python-loupedeck-live`](https://github.com/devleaks/python-loupedeck-live) device library.
- Optional: `pyautogui` + `python-xlib`, only as an X11 input fallback.

**System tools**
- **`ydotool`** + the `ydotoold` daemon: injects hotkeys/text on **Wayland** via kernel uinput
  (required for actions to fire in native Wayland sessions).
- `playerctl`: media transport via MPRIS.
- `kdotool`: active-window detection for dynamic mode on KDE Wayland.

## Setup

```bash
git clone https://github.com/ascendedent/loupedeckapp
cd loupedeckapp

python3 -m venv .venv
.venv/bin/pip install -e ".[device]"

# optional: X11 input fallback (unnecessary on Wayland)
.venv/bin/pip install -e ".[x11]"
```

The `device` extra pulls the device library from git, since it is not on PyPI.
Installing normally (`pip install ".[device]"`) puts a `loupedeckapp` command on your PATH, the
assets under `<prefix>/share/loupedeckapp`, and a desktop entry and icon where your menu will find
them; the app finds its own files either way.

Leave the `device` extra off and the app still runs: it opens, edits and saves profiles, and says
in the top bar that the device library is missing along with the command to install it. It just
cannot find a device until you do.

### First run

The app checks the machine when it starts and shows what is still missing: the udev rule and group
for device access, the input backend, and the optional helpers (`kdotool` for dynamic mode,
`playerctl` for media). Each one comes with the exact commands, which you copy and run yourself,
because they need root and an app that asks for your password to run something you cannot read
first is not one to trust with it.

It opens once on a first run. After that a **Setup** chip appears in the top bar only when
something is wrong, and it is always under the gear.

### System tray

The app sits in the tray by default, because it is only useful while it is running. Closing the
window hides it rather than quitting; the tray menu has the live profile, a profile switcher,
dynamic mode, show/hide and quit. Quitting from the tray with unsaved edits brings the window back
and asks first.

All of that is under the gear in the top bar, along with brightness. If your desktop has no tray,
the toggles are disabled and closing the window quits, since hiding it would leave no way back.

### A single file (AppImage)

```bash
./packaging/appimage/build.sh      # -> dist/LoupedeckConfig-x86_64.AppImage
```

Self-contained: the app, its dependencies, a Python interpreter and the parts of Qt it uses. It
still needs the udev rule and `ydotoold` on the host, and the Setup dialog will tell you so.

There is a Flatpak manifest in [`packaging/flatpak/`](packaging/flatpak/), but read its README
first: typing into other applications is precisely what a sandbox exists to prevent, and working
around that leaves little sandbox behind.

### Starting with your session

**Start with the session** writes an XDG autostart entry (`~/.config/autostart/loupedeckapp.desktop`),
which KDE and GNOME both read. Combine it with **Start hidden** and the app comes up in the tray
with your profile already on the device.

From a checkout the entry has to name the interpreter and the script by absolute path, because a
login session has neither your virtualenv nor the directory you launched from. If the app moves or
its virtualenv is rebuilt elsewhere the entry goes stale, which is otherwise silent: the session
still runs it and nothing starts. The preferences panel says so when that happens; turn the switch
off and on again to repoint it.

### Device permissions

Let your user reach the device without `sudo`. The rule covers all three models:

```bash
sudo cp packaging/99-loupedeck.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger
sudo usermod -aG dialout "$USER"     # some distros use `plugdev`; match the rule
```

Log back in for the group change to apply.

### Wayland input (ydotool)

```bash
sudo dnf install ydotool playerctl        # or your distro's package manager

# ydotoold stays root to open /dev/uinput, but its socket has to be reachable
# by you. This drop-in puts it somewhere predictable and hands it over:
sudo mkdir -p /etc/systemd/system/ydotool.service.d
sudo cp packaging/ydotool-user-socket.conf /etc/systemd/system/ydotool.service.d/override.conf
sudo systemctl daemon-reload && sudo systemctl enable --now ydotool
```

`input_backend` discovers that socket automatically, and falls back to `xdotool` / `pyautogui` on
X11. See [`packaging/`](packaging/) for the files and what each one is for.

## Running

```bash
loupedeckapp                  # if installed
.venv/bin/python qml_app.py   # from a checkout

# If Qt doesn't pick a platform on your session, set one explicitly:
#   QT_QPA_PLATFORM=wayland .venv/bin/python qml_app.py     # or =xcb for XWayland
```

Run the checks with `.venv/bin/python tests/run_all.py` (no device needed). Checks that do need
hardware live in [`scripts/verify/`](scripts/verify/).

**On macOS?** The adapters are written and have never run on a Mac. See
[docs/MACOS.md](docs/MACOS.md) for what exists and what to check.

**Have a Live or Live S?** Those models are supported from the library's source and published
specs, and have never been run on real hardware. [docs/LIVE-TESTING.md](docs/LIVE-TESTING.md) says
what is guesswork and how to report what your device actually does.

## Troubleshooting

### An app only responds once to Fast 2x/3x or acceleration

You turn one detent expecting 3 steps and the app moves 1. The keystrokes *are* all being
delivered; some receivers deliberately collapse identical keypresses that arrive with no gap
between them, treating the burst as a single press.

We send repeats with a small gap for exactly this reason. If an app still under-delivers, that gap
is too short for it. Raise `repeat_delay_ms` in [`input_backend.py`](input_backend.py):

```python
class YdotoolBackend(InputBackend):
    repeat_delay_ms = 3      # try 8, then 15
```

It applies **only** when a repeat is sent, so raising it costs nothing on ordinary single presses.
Measured against KDE's volume handler, 0 ms delivered 1 step of 3 every time and 1 ms delivered
3 of 3 every time, so the threshold can be very small; other handlers may want more.

The trade-off is throughput: a repeat costs two events at this delay, so 3 ms ceilings keystroke
output near 167 steps/sec. Raising it lowers that ceiling, which matters only when spinning a
control fast with Fast 3x or acceleration.

### Actions do nothing in a Wayland session

The app shows a **⚠ input** warning in the top bar when it cannot inject keystrokes; click it for
the reason and a re-check button. Usually `ydotoold` is not running, or its socket is not readable
by your user:

```bash
systemctl status ydotool
ls -l /run/.ydotool_socket        # should be owned by you
```

See the ydotool setup above for the drop-in that fixes socket ownership. `input_backend` picks
ydotool automatically on Wayland; `xdotool`/`pyautogui` are X11-only and cannot inject into native
Wayland clients.

### The device is not found

Another instance may be holding `/dev/ttyACM0` (including a `scratch/` probe script). Otherwise
check the udev rule and group membership under [Device permissions](#device-permissions).

## Architecture

The core is Qt-free and layered, so the UI sits on top of reusable services:

| Module | Role |
|--------|------|
| `DeviceProfile` | Per-model geometry (screens, key maps) + USB-PID model detection. |
| `ct_support` | Runtime support for the CT wheel / dial / buttons over the vendored library. |
| `input_backend` | OS input: ydotool → xdotool → pyautogui, auto-selected. |
| `window_watcher` / `profile_manager` | Focused-app detection + per-app profile bindings (dynamic mode). |
| `device_controller` | Connect, render a profile to the device, route events to actions, and dispatch rotate events through a coalescing queue. |
| `LdConfiguration` | Profile data model + JSON persistence (schema v5), incl. encoder tuning. |
| `platform_env` | The only module that reads `sys.platform` / `XDG_*` / `DISPLAY`. |
| `action_library` | Ready-to-use actions, with per-desktop application entries. |
| `app_paths` | Bundled assets vs. user data; profile resolution and legacy migration. |
| `settings` | Small persistent app preferences (brightness), separate from profile data. |
| `virtual_keyboard` | Toggles the desktop's on-screen keyboard (KDE via DBus, else a keyboard binary). |
| `qml_app.py` + `qml/` | The PySide6 / QML front-end. |

See [`docs/PLAN.md`](docs/PLAN.md) for the full design notes and roadmap.

## Roadmap

Agreed direction (detail in [`docs/PLAN.md`](docs/PLAN.md)):

1. **Ship Linux**: pinned deps; Flatpak and/or AppImage; udev + ydotool docs; starter profiles.
2. **Product depth**: Live/Live S mirror fidelity, macros, and UI polish.
3. **macOS**: native build targeting **macOS 10.14+**: device I/O first, then Quartz input,
   frontmost-app dynamic mode, then `.app` packaging. The core is already Qt-free; this is mostly
   adapters, permissions UX, and paths.

**Done recently:** per-control encoder feel (invert, speed presets, acceleration on inter-detent
interval), a scroll action, and a coalescing dispatch queue that keeps a fast spin from running on
after your hand stops. Plus the QML UI reaching parity and the legacy PyQt5 tree being
removed: binding a focused app to a profile, profile
create/duplicate/rename/delete, and a working library search.

Plus a user-writable config location, so the app no longer stores your profiles inside its own
source tree.

Smaller known gaps: encoder tuning is scoped per workspace rather than per profile, and the
inspector exposes the speed presets but not the raw integers behind them.

## Credits & license

Original project by [flowernert](https://github.com/flowernert/loupedeckapp). CT support, the
Wayland-capable input backend, dynamic per-app profiles, and the PySide6/QML UI were added here.
Device I/O uses devleaks' [`python-loupedeck-live`](https://github.com/devleaks/python-loupedeck-live).

See [`LICENSE`](LICENSE).
