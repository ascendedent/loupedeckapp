# loupedeckapp

A native **Linux** configuration app for the **Loupedeck CT** (and Loupedeck Live / Live S) — an
open-source stand-in for the official Loupedeck software, which is Windows/macOS only.

Assign images, background colours, text labels, LED colours and actions to every touch key, side
display, encoder, and — on the CT — the rotary dial and round wheel screen; organise them into
workspaces and nested submenus; and optionally auto-switch profiles based on the focused desktop
application — all from a modern, dark PySide6/QML interface.

> **Origin.** This project began as a fork of
> [flowernert/loupedeckapp](https://github.com/flowernert/loupedeckapp) (which targets the Loupedeck
> Live) and has grown into a standalone app focused on the **Loupedeck CT** with full Wayland
> support. Thanks to flowernert for the original groundwork.

---

## Supported hardware

| Device            | USB PID     | Status                                                                                   |
|-------------------|-------------|------------------------------------------------------------------------------------------|
| Loupedeck **CT**  | `2ec2:0003` | Primary target — full support incl. the 240×240 wheel screen, rotary dial, and CT buttons |
| Loupedeck **Live**| `2ec2:0004` | Supported (upstream's original target)                                                   |
| Loupedeck **Live S** | `2ec2:0006` | Supported (5-column geometry, no side screens)                                        |

The model is detected from the USB product id — the vendored device library reports every model as
`LoupedeckLive`, so CT-specific behaviour is enabled only when a wheel/dial is present.

## Features

### Device control
- 4×3 touch-key grid, left/right side displays, and 6 side encoders (press + rotate).
- On the **CT**: the round **wheel screen** (renders big-endian 240×240), the rotary **dial**
  (press + rotate), and the CT function buttons (`home`, `undo`, `keyboard`, `enter`, `save`,
  `fn`, `a`–`e`).
- 8 workspaces on the physical buttons (`circle` + `1`–`7`), each with its own layout, plus nested
  **submenus**.

### Per-control styling
- **Images** — fit to the control (aspect preserved, never cropped or stretched). The inspector
  shows the exact target size for a pixel-perfect fill (90×90 keys, 60×90 side cells, 240×240 wheel).
- **Text labels** — on by default, auto-derived from the assigned action's name (e.g. `Copy`), with
  a per-control show/hide toggle so a label is never lost when you add an image. Placement
  top / middle / bottom, and three modes: **over** the image, on a **bar**, or **shrink** (image
  resized so the label sits beside it). Custom bar colour.
- **Background colour** behind an image, and **RGB LED colours** for the physical workspace and CT
  buttons.
- Everything renders both in the on-screen mirror and on the physical device.

### Actions
- `command`/launch, `hotkey`, `text`, `media` (MPRIS), and `submenu` / `back` navigation.
- **Hotkey recorder** — press a key combination to capture it — plus a **presets** picker that
  includes your machine's configured KDE global shortcuts.
- A searchable **action library** you drag onto controls. Dropping onto an encoder, the dial, or the
  wheel lets you pick the **press / rotate / touch** slot.

### Workflow
- Three-column dark UI (PySide6 + QML): action library · live device mirror · inspector.
- **Draft editing** — edits update the on-screen mirror live and are pushed to the hardware only on
  **Save**; **Revert** discards the draft.
- **Copy / paste** a control's entire function onto another compatible control.
- **Dynamic mode** — switches the active profile when the focused desktop app changes (KDE Wayland,
  via KWin scripting).
- JSON profiles (schema v4, backward compatible with older profiles).

## Requirements

- **Linux**; Python 3 (developed on Fedora 44 / Python 3.14, KDE Plasma on **Wayland**).
- The device on `/dev/ttyACM0`, readable by your user (see [Device permissions](#device-permissions)).

**Python packages**
- `PySide6` (QML UI), `pyserial`, `pillow`, and the devleaks
  [`python-loupedeck-live`](https://github.com/devleaks/python-loupedeck-live) device library.
- Optional / legacy: `PyQt5` (the older `app.py` UI), `pyautogui` + `python-xlib` (X11 input fallback).

**System tools**
- **`ydotool`** + the `ydotoold` daemon — injects hotkeys/text on **Wayland** via kernel uinput
  (required for actions to fire in native Wayland sessions).
- `playerctl` — media transport via MPRIS.
- `kdotool` — active-window detection for dynamic mode on KDE Wayland.

## Setup

```bash
git clone https://github.com/ascendedent/loupedeckapp
cd loupedeckapp

python3 -m venv .venv
.venv/bin/pip install pyserial pillow pyside6
.venv/bin/pip install "git+https://github.com/devleaks/python-loupedeck-live.git"

# optional: legacy Qt5 UI + X11 input fallback
.venv/bin/pip install pyqt5 pyautogui python-xlib
```

### Device permissions

Let your user reach the device without `sudo`. Create `/etc/udev/rules.d/99-loupedeck.rules`:

```
# Loupedeck CT (0003); use 0004 for the Live, 0006 for the Live S
SUBSYSTEM=="tty", ATTRS{idProduct}=="0003", ATTRS{idVendor}=="2ec2", GROUP="dialout", MODE="0660"
```

Then add yourself to the group and re-login:

```bash
sudo usermod -aG dialout "$USER"     # some distros use `plugdev` — match GROUP= above
```

### Wayland input (ydotool)

```bash
sudo dnf install ydotool playerctl        # or your distro's package manager
sudo systemctl enable --now ydotool       # runs ydotoold with access to /dev/uinput
```

`input_backend` auto-discovers the ydotool socket and falls back to `xdotool` / `pyautogui` on X11.

## Running

```bash
# New PySide6 + QML UI (recommended)
.venv/bin/python qml_app.py
# If Qt doesn't pick a platform on your session, set one explicitly:
#   QT_QPA_PLATFORM=wayland .venv/bin/python qml_app.py     # or =xcb for XWayland

# Legacy PyQt5 UI
.venv/bin/python app.py
```

## Architecture

The core is Qt-free and layered, so the UI sits on top of reusable services:

| Module | Role |
|--------|------|
| `DeviceProfile` | Per-model geometry (screens, key maps) + USB-PID model detection. |
| `ct_support` | Runtime support for the CT wheel / dial / buttons over the vendored library. |
| `input_backend` | OS input: ydotool → xdotool → pyautogui, auto-selected. |
| `window_watcher` / `profile_manager` | Focused-app detection + per-app profile bindings (dynamic mode). |
| `device_controller` | Connect, render a profile to the device, route events to actions. |
| `LdConfiguration` | Profile data model + JSON persistence (schema v4). |
| `qml_app.py` + `qml/` | The PySide6 / QML front-end. |
| `app.py` + `Ld*.py` | The legacy PyQt5 UI (kept during the migration). |

See [`docs/PLAN.md`](docs/PLAN.md) for the full design notes and roadmap.

## Roadmap

- Ready-to-use starter profiles and nicer defaults.
- Configurable side displays (single image vs. split into cells).
- Packaging (Flatpak / AppImage) with the udev + ydotool setup bundled.
- An eventual **macOS** build — the core is already platform-agnostic; it needs macOS input and
  active-window adapters and app packaging.

## Credits & license

Original project by [flowernert](https://github.com/flowernert/loupedeckapp). CT support, the
Wayland-capable input backend, dynamic per-app profiles, and the PySide6/QML UI were added here.
Device I/O uses devleaks' [`python-loupedeck-live`](https://github.com/devleaks/python-loupedeck-live).

See [`LICENSE`](LICENSE).
