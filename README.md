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
| Loupedeck **Live**| `2ec2:0004` | Supported (upstream's original target)                                                   |
| Loupedeck **Live S** | `2ec2:0006` | Supported (5-column geometry, no side screens)                                        |

The model is detected from the USB product id. The vendored device library reports every model as
`LoupedeckLive`, so CT-specific behaviour is enabled only when a wheel/dial is present.

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
- `command`/launch, `hotkey`, `text`, `scroll`, `media` (MPRIS), and `submenu` / `back` navigation.
- **Hotkey recorder** that captures a key combination when you press it, plus a **presets** picker
  that includes your machine's configured KDE global shortcuts.
- A searchable **action library** you drag onto controls, including scroll and volume. Search
  matches the action's value and type as well as its name, so `ctrl`, `scroll` or `vol up` all
  narrow the list. Dropping onto an encoder, the dial, or the wheel lets you pick the
  **press / rotate / touch** slot.

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
- **Import / export** profiles as JSON. Importing checks the file before adding it, and never
  overwrites an existing profile: a name that is taken gets a numbered suffix.
- **Dynamic mode**: switches the active profile when the focused desktop app changes (KDE Wayland,
  via KWin scripting).
- JSON profiles (schema v5, backward compatible with older profiles; unknown fields
  written by a newer build survive a load/save round-trip).

### Where your data lives

| | |
|---|---|
| Profiles you edit, and app bindings | `~/.config/loupedeckapp/` (`$XDG_CONFIG_HOME` is respected) |
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
Installing normally (`pip install ".[device]"`) puts a `loupedeckapp` command on your PATH and the
assets under `<prefix>/share/loupedeckapp`; the app finds them either way.

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

Run the checks with `.venv/bin/python tests/run_all.py` (no device needed).

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

Check `ydotoold` is running (`systemctl status ydotool`) and that the socket is reachable by your
user. `input_backend` picks ydotool automatically on Wayland; `xdotool`/`pyautogui` are X11-only
and cannot inject into native Wayland clients.

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
| `qml_app.py` + `qml/` | The PySide6 / QML front-end. |

See [`docs/PLAN.md`](docs/PLAN.md) for the full design notes and roadmap.

## Roadmap

Agreed direction (detail in [`docs/PLAN.md`](docs/PLAN.md)):

1. **Ship Linux**: pinned deps; Flatpak and/or AppImage; udev + ydotool docs; starter profiles.
2. **Product depth**: brightness and reconnect handling, Live/Live S mirror fidelity, macros,
   and UI polish.
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
