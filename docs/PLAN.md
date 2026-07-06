# loupedeckapp — Build Plan

A roadmap to grow this fork from a working Loupedeck **Live** proof-of-concept into a robust,
good-looking Loupedeck configuration app for Linux, with **full Loupedeck CT support** and a UI
that approaches the official Loupedeck desktop app.

> Attribution rule (see `CLAUDE.md`): Claude/AI is never listed as a contributor. All commits are
> authored by the human user; the `commit-msg` hook enforces this.

---

## 1. Vision

A native Linux app that lets you visually configure a Loupedeck device — assign images and actions
to every touch key, side display, and encoder; organize them into pages/folders and per-application
profiles; and (optionally) auto-switch profiles based on the focused desktop application — with a
modern, dark, responsive UI comparable to the official Loupedeck software.

Primary target device: **Loupedeck CT** (this machine's hardware). Keep **Live / Live S** working
where practical.

---

## 2. Where we are today (baseline)

Verified working on the CT (see `scratch/probe_ct.py`, `scratch/render_test.py`):

- Device connects via devleaks `python-loupedeck-live` (v1.5.1); enumerate, info, and **all render
  ops** (brightness, button RGB, key images, side displays) succeed on the CT.
- PyQt5 GUI launches on KDE/Wayland (via XWayland/xcb) and runs without root after the udev +
  `dialout` fix.
- Existing features: touch-button images, actions (`shell`, `hotkey`, `submenu`, `back`), workspaces
  on buttons `circle`+`1..7`, submenu navigation, and JSON profile save/load.

Existing modules: `app.py` (entry), `LdApp.py` (device + navigation + event routing),
`LdConfiguration.py` (model + persistence), `LdWidget.py` (on-screen device mirror), `LdDialog.py`
(config dialogs).

### Known limitations
- Geometry is hardcoded for the **Live** (480-wide center); the CT differs and its round **wheel
  screen** + rotary **dial** are unsupported.
- `hotkey` actions use `pyautogui` (X11-only) — they won't fire on Wayland.
- No per-application profiles / dynamic (focus-based) switching.
- UI is functional but far from the official app's polish; limited action library.
- Tightly coupled: device I/O, navigation, and Qt widgets are interwoven in `LdApp.py`.

---

## 3. Target experience (gap analysis vs. official app)

From the reference screenshots, the official app is a **three-column dark layout**:

| Area | Official app | Us today | Gap |
|------|--------------|----------|-----|
| **Top bar** | Device selector · Application-profile selector · **Dynamic Mode** toggle · Workspace selector · connection status | Profile text field + Save/Load buttons | Rebuild as a proper header with selectors + status |
| **Left panel** | Searchable **Action Library** — categorized tree (General, Adjustments, Navigation, plugin actions…) drag-drop onto keys | Per-key config dialog only | Add a real action catalog + search + drag-drop |
| **Center** | Photorealistic, **interactive device render**; keys show icons/labels; encoders + round buttons with colored rings | Flat widget grid mirroring the device | Richer, device-accurate, animated visualization (esp. CT wheel) |
| **Right panel** | **Profile / pages hierarchy** — system profile + app profiles, touch-screen pages, dial pages, folders; add/remove/settings per row | Implicit workspaces + submenu stack | Explicit pages/profiles tree UI |
| **Profiles** | System profile + **per-application profiles**, importable, "dynamic mode" auto-switch | Single flat profile file | New profile model + app binding + switcher |
| **Theme** | Dark, rounded, animated toggles/cards | Default Qt look | Full theming pass |

---

## 4. Proposed architecture

### 4.1 Key decision — UI stack

To approach the official app's look (dark, rounded, animated, GPU-smooth device render) we have
three options:

| Option | Pros | Cons |
|--------|------|------|
| **A. Evolve PyQt5 QWidgets + QSS** | Least churn; reuse current code | QWidgets look dated; custom rounded/animated rendering is painful; polish ceiling is low |
| **B. PySide6 + Qt Quick (QML)** ✅ *recommended* | QML is built for modern animated UIs — closest to official look; still Python backend; PySide6 is LGPL (friendlier than PyQt's GPL) | UI-layer rewrite; QML learning curve; Python↔QML bridging |
| **C. Web UI (Electron/Tauri) + Python device service** | Easiest to make beautiful; huge ecosystem | Two-language stack + IPC; heavier runtime; device lib is Python so needs a bridge process |

**DECIDED: B — migrate the UI to PySide6 + QML.** We extract a framework-agnostic core (model +
device service + action engine) so the UI can be rebuilt without touching device logic. The
PyQt5→PySide6 move is largely mechanical. Phase 1 work (M1–M3, below) is UI-independent and delivers
value regardless, so the QML build formally begins at M4 — but from M1 onward, keep all new code Qt-
binding-agnostic (no direct `PyQt5` imports in core/services) to avoid rework at migration time.

> Low-risk fallback if QML slips: a heavy QSS restyle of the current PyQt5 widgets (Option A).
> Not the chosen path, but kept as a contingency for M4.

### 4.2 Layered architecture (target)

```
┌─────────────────────────────────────────────┐
│ UI layer  (PySide6 + QML)                     │  device view · action library · pages/profiles
├─────────────────────────────────────────────┤
│ Application services                          │
│  · ProfileManager (system + app profiles)     │
│  · NavigationController (pages/folders)        │
│  · ActionEngine (resolve + execute actions)    │
│  · FocusWatcher (dynamic mode)                 │
├─────────────────────────────────────────────┤
│ Platform adapters (OS-specific, pluggable)    │
│  · InputBackend: ydotool | pyautogui | dbus    │
│  · WindowWatcher: KWin(dbus) | X11 | GNOME     │
├─────────────────────────────────────────────┤
│ Device layer                                  │
│  · DeviceProfile (geometry per model: CT/Live) │
│  · Renderer (image→device screens)             │
│  · devleaks python-loupedeck-live              │
└─────────────────────────────────────────────┘
```

Design rules: no Qt imports below the UI layer; all device geometry lives in `DeviceProfile`
(no hardcoded 480/x=0/x=480 in logic); actions and window/input backends are pluggable interfaces.

### 4.3 Profile/config data model v2

Evolve `LdConfiguration` JSON to a versioned schema that supports profiles, pages, and the CT:

```jsonc
{
  "schema_version": 2,
  "device": "LoupedeckCT",
  "system_profile": { "buttons": { "circle": {...}, "1": {...} } },
  "app_profiles": [
    { "id": "firefox", "match": { "wm_class": "firefox" }, "workspaces": [ ... ] }
  ],
  "dynamic_mode": true,
  "workspaces": [
    { "name": "Daily", "pages": [
      { "keys":  { "tb11": { "image": "...", "action": {...} } },
        "left":  [ ... ], "right": [ ... ],
        "wheel": { "image": "...", "action": {...} },      // CT-only
        "dial":  { "action_cw": {...}, "action_ccw": {...}, "press": {...} },
        "encoders": { "enc1L": { "cw": {...}, "ccw": {...}, "press": {...} } }
      }
    ] }
  ]
}
```

Provide a **v1→v2 migration** so existing `Profiles/*.json` load cleanly.

---

## 5. Workstreams

### A. Core refactor & data model
- Extract `DeviceProfile` (per-model geometry, key maps, screen list) — remove hardcoded Live layout
  from `LdApp.py` (`set_img_to_touchdisplay`, `tb_name_to_keycode`, coordinate math).
- Introduce `ProfileManager`, `NavigationController`, `ActionEngine` as plain-Python services with no
  Qt dependency.
- Versioned config schema + v1→v2 migration; round-trip tests.

### B. Full CT device support
- Add a CT device profile: center **360×270**, left/right **60×270** at correct offsets, round
  **wheel 240×240**, rotary **dial** (`knobCT`), and the CT button map
  (`knobTL/CL/BL/TR/CR/BR`, `home/undo/keyboard/enter/save/fnL/fnR/a/b/c/d/e`, touch keys `0..11`).
  (Cross-check IDs against foxxyz `loupedeck` `constants.js`, which documents the CT map.)
- Render support for the **wheel screen** and handling of **dial** rotate/press events.
- Correct touch-key ↔ grid mapping for the CT; verify with the device.
- Guard: detect model from USB PID (`0003`=CT, `0004`=Live) since the devleaks lib reports both as
  `LoupedeckLive`.

### C. Platform / input layer (Wayland-first)
- `InputBackend` interface with implementations:
  - **ydotool** (uinput; works on Wayland) — primary for `hotkey` actions here. Requires `ydotoold`
    daemon + uinput access; document setup.
  - `pyautogui`/xdotool (X11) — fallback.
  - DBus/MPRIS for media keys and app launching on KDE (no synthetic input needed).
- `WindowWatcher` interface for **dynamic mode**:
  - **KWin (KDE Wayland)**: active window via KWin scripting / DBus (`org.kde.KWin`) — primary here.
  - X11 (`_NET_ACTIVE_WINDOW`) and GNOME (extension) as alternates.

### D. Action system & library
- Formalize action types: `shell`, `hotkey`, `text`, `open_url`, `launch_app`, `media` (MPRIS),
  `dbus`, `submenu/folder`, `back`, `page_switch`, `multi` (macro sequence), `adjustment`
  (encoder-driven value).
- Build a **searchable Action Library** (left panel) grouped by category, including OS/KDE built-ins.
- Plugin interface (later) so integrations (OBS, media, etc.) can register actions.

### E. Profiles, application profiles, dynamic mode
- System profile + multiple **application profiles** with match rules (`wm_class`/title/exec).
- **Dynamic mode** toggle: `FocusWatcher` switches the active profile on focus change.
- Import/export profiles; ship a few ready-to-use starter profiles.

### F. UI overhaul (PySide6 + QML, per §4.1)
- Three-column shell: top bar (device · app-profile · dynamic toggle · workspace · status),
  left Action Library, center device view, right pages/profiles tree.
- Dark theme, rounded cards, animated toggles; drag-drop actions onto keys.
- **CT-accurate device view** incl. wheel + dial; live preview mirrors what's on the device.
- Keep a thin PyQt5 restyle available as interim (Option A) if QML slips.

### G. Packaging & distribution
- Ship the udev rule + `dialout`/`plugdev` group setup in an installer/postinstall.
- Bundle: **Flatpak** (preferred for KDE) and/or **AppImage**; document `ydotoold` requirement.
- Pin Python deps; handle new-Python wheel gaps (e.g. PyQt/PySide, `canvas`-style native builds).

---

## 6. Phased roadmap

| Milestone | Goal | Contains | Exit criteria |
|-----------|------|----------|---------------|
| **M0 — Baseline** *(done)* | Fork runs on CT | Fork, deps, permissions, app launches & connects | App drives the CT without sudo |
| **M1 — CT correctness** *(done)* | The current UI is *correct* for the CT | Workstream A (partial) + B; PID-based model detect; wheel/dial events read; geometry fixed | ✅ Every CT key/encoder/side-display/dial/wheel decodes; wheel renders; right-display placement fixed |
| **M2 — Input that works** *(done)* | Actions actually fire on Wayland | Workstream C (ydotool + KDE dbus); media/launch actions | ✅ `input_backend` (ydotool→xdotool→pyautogui); hotkey/text/launch/media; verified typing into native Wayland windows |
| **M3 — Profiles & dynamic mode** *(done)* | Per-app profiles | Workstreams D + E; schema v2 + migration; FocusWatcher via KWin | ✅ schema v2 + migration; WindowWatcher (kdotool); ProfileManager + dynamic-mode toggle; **verified live on-device** (focus Chrome→blue / other→red profile switch). Action *library* UI deferred to M4. |
| **M4 — UI overhaul** | Looks/feels close to official | Workstream F (PySide6+QML), action library, pages tree, theming | Three-column dark UI; drag-drop; CT device view w/ wheel |
| **M5 — Ship it** | Installable by non-devs | Workstream G; docs; starter profiles | Flatpak/AppImage installs & runs on a clean KDE machine |

Milestones are independently valuable; M1–M3 don't depend on the UI-stack decision.

---

## 7. Risks & open questions

- **devleaks lib CT coverage**: connection + render verified, but wheel-screen draw and dial-event
  decoding are unproven — may need patches to the lib (or borrow from foxxyz's JS implementation).
- **ydotool setup friction**: needs a daemon + uinput permissions; must be packaged/documented well.
- **PySide6 vs PyQt5**: migration cost vs. license/UX benefit — confirm before M4.
- **KWin API stability**: active-window retrieval on KDE Wayland relies on KWin scripting/DBus, which
  can change across Plasma versions.
- **Python 3.14**: some GUI/native wheels lag new Python; may need distro packages or pins.
- **Upstream divergence**: decide what to contribute back to `flowernert/loupedeckapp` vs. keep in
  the fork.

---

## 8. Status & next actions

**M1 — done** (commits pending):
1. ~~Commit the scaffolding baseline (CLAUDE.md, hooks, .gitignore, this plan).~~ ✅
2. ~~PID-based model detection (CT vs Live) + a `DeviceProfile`.~~ ✅ `DeviceProfile.py`
3. ~~Replace hardcoded Live geometry in `LdApp.py` with `DeviceProfile` lookups.~~ ✅ (right-display
   x=480→relative-0 bug fixed; key/side/grid geometry all profile-driven)
4. ~~Probe + wire the CT **wheel screen** and **dial** events.~~ ✅ `ct_support.py` (wheel renders
   big-endian; dial/wheel-touch/CT-buttons decode — verified live via `scratch/ct_capture.py`)

**M2 — done:** ✅ `input_backend` (ydotool→xdotool→pyautogui); verified typing/hotkeys into native
Wayland windows via `ydotoold`.

**M3 — mostly done:**
- ✅ Schema v2 + v1→v2 migration; dial/wheel/CT-button action slots + wheel image slot (bindable and
  persisted; events already routed in `LdApp`).
- ✅ `WindowWatcher` (kdotool, KWin scripting) + `ProfileManager` (app→profile bindings, default
  profile, dynamic-mode flag in `dynamic_profiles.json`) + a dynamic-mode toggle & "bind app" button
  wired into `LdApp`.
- ✅ **Live on-device test passed**: with dynamic mode on, focusing Chrome switched the CT to the
  bound profile (blue) and focusing another app returned it to the default (red).
- Deferred to M4: a proper action-config UI for the new action types + the action *library*.

**M4 kickoff (next):** PySide6 + QML UI overhaul (three-column shell, CT-accurate device view incl.
wheel, action library, pages/profiles tree, theming).
