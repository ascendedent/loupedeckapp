# loupedeckapp — Build Plan

Roadmap for a robust, modern Loupedeck configuration app: **Linux first** (primary), then
**macOS** (minimum target **macOS 10.14 Mojave**). Full **Loupedeck CT** support, Live / Live S
kept working where practical. UI aims to approach the official Loupedeck desktop app.

> **Authorship.** Commits, tags, release notes, and public docs are authored by the human
> maintainer only. Do not add co-author trailers, “generated with …”, or similar attribution for
> tooling. The `commit-msg` hook rejects common automated-attribution patterns.

---

## 1. Vision

A native configuration app that lets you visually configure a Loupedeck device — assign images,
labels, colours, and actions to every touch key, side display, encoder, and (on the CT) the wheel
and dial; organise them into workspaces and nested submenus; and optionally auto-switch profiles
based on the focused desktop application — with a modern, dark, responsive UI.

| Priority | Platform | Notes |
|----------|----------|--------|
| **P0** | Linux (KDE Wayland primary; X11 fallback) | Ship first (packaging + polish) |
| **P1** | macOS **10.14+** | After Linux ships; adapters + `.app` |
| Later | Other Linux DEs (GNOME, …) | Extra window/input backends |
| Out of scope for now | Windows | Same adapter pattern if demand appears |

Primary device: **Loupedeck CT**. Keep **Live / Live S** correct where practical.

**Product positioning on macOS:** open, scriptable, CT-focused, no account — not a full clone of
the official plugin marketplace (which already covers Mac).

---

## 2. Current status (as of post-M4 feature work)

### Done (M0–M4 core)

| Area | Status |
|------|--------|
| CT / Live / Live S geometry + PID detect | ✅ `DeviceProfile` |
| Wheel screen, dial, CT buttons | ✅ `ct_support` + routing in `DeviceController` |
| Wayland input | ✅ `input_backend` (ydotool → xdotool → pyautogui) |
| Media / launch | ✅ playerctl + detached shell |
| Schema v2–v4 (dial/wheel/CT slots, labels, LEDs, bg colours) | ✅ `LdConfiguration` |
| Dynamic mode (KDE) | ✅ `window_watcher` (kdotool) + `ProfileManager` |
| QML three-column shell + CT device mirror | ✅ `qml_app.py` + `qml/` |
| Inspector (actions, image, labels, LED, bg) | ✅ |
| Draft Save / Revert (mirror live, hardware on Save) | ✅ |
| Copy / paste control functions (type-checked) | ✅ |
| Action library + drag-drop onto controls | ✅ |
| Submenu create / enter / back from QML | ✅ |
| Labels, LED colours, backgrounds, image-fit | ✅ |

### Dual UI (debt)

| Capability | QML (`qml_app.py`) | Legacy PyQt5 (`app.py` / `Ld*`) |
|------------|--------------------|----------------------------------|
| Device engine | `DeviceController` | Logic still in `LdApp` |
| Labels / LEDs / bg / draft / library | Yes | Limited / absent |
| Bind focused app → profile | **Missing** | Present |
| Product path | **Canonical** | **Deprecated** — freeze, then remove |

**DECIDED:** QML is the only product UI. No new features in the PyQt5 tree. Remove once QML has
parity on dynamic binding + profile lifecycle (Phase A).

### Known gaps (ordered by agreed priority)

1. **One UI** — finish QML parity; retire PyQt5.
2. **Platform adapters + paths** — explicit factories; no CWD-relative `./Profiles`.
3. **Ship Linux (M5)** — pin deps, packaging, udev/ydotool docs, starter profiles.
4. **Functionality** — dynamic UX, profile CRUD, real search library, device polish, Live S fidelity, macros/adjustments.
5. **UI polish** — search, workspace chrome, dirty guards, inspector structure, empty categories.
6. **macOS (M6)** — adapters, Accessibility UX, `.app`, support **10.14+**.

---

## 3. Target experience (gap analysis vs. official app)

| Area | Official app | Us today (QML) | Remaining gap |
|------|--------------|----------------|---------------|
| **Top bar** | Device · app-profile · Dynamic · workspace · status | Device pill · profile name · Save/Revert · Dynamic | Profile picker depth, workspace name, reconnect status, input-backend health |
| **Left panel** | Searchable action library | Categorised library + drag-drop | **Search is UI-only (not wired)**; Adjustments empty; KDE-hardcoded apps |
| **Center** | Photorealistic device | Schematic CT mirror; live images/labels/LEDs | Optional photoreal polish; Live/Live S layout fidelity |
| **Right panel** | Profiles + pages tree | Profile list + rich inspector | Profile create/rename/delete/import; bind-app UI; pages hierarchy |
| **Profiles** | System + per-app + dynamic | Files on disk + `dynamic_profiles.json` | Full lifecycle; multi-key match (`wm_class` / `bundle_id`) |
| **Theme** | Dark, rounded | Dark themed QML | Toasts, first-run tips, inspector sections |

---

## 4. Architecture

### 4.1 UI stack — decided

**PySide6 + QML only.** Core stays Qt-free. Legacy PyQt5 is migration residue, not a second product.

### 4.2 Layered architecture (target)

```
┌──────────────────────────────────────────────────────────┐
│ UI layer  (PySide6 + QML)                                  │
│  device view · action library · profiles · inspector       │
├──────────────────────────────────────────────────────────┤
│ Application services                                       │
│  · AppPaths (bundled assets + user writable dir)           │
│  · ProfileManager (default + app bindings + dynamic flag)  │
│  · DeviceController (connect, render, route, draft edit)   │
│  · LdConfiguration (schema v4+)                            │
├──────────────────────────────────────────────────────────┤
│ Platform adapters (pluggable factories)                    │
│  · InputBackend:  linux_ydotool | linux_xdotool | mac_quartz | null
│  · WindowWatcher: kde_kdotool | mac_frontmost | (gnome/x11 later) | null
│  · ShortcutsCatalog: kde | mac_common | static
│  · ActionLibraryDefaults: per-OS app commands / hotkeys
├──────────────────────────────────────────────────────────┤
│ Device layer                                               │
│  · DeviceProfile · label_render · ct_support               │
│  · devleaks python-loupedeck-live (pyserial; cross-platform)
└──────────────────────────────────────────────────────────┘
```

**Design rules**

- No Qt imports below the UI layer.
- All geometry via `DeviceProfile` (no hardcoded Live/CT layout in logic).
- Input / focus / shortcut catalogs selected by **factory** (`sys.platform` + session), never by
  scattering `XDG_*` checks through the app.
- Paths never depend on process CWD.

### 4.3 Paths (`AppPaths`)

| Role | Dev (repo) | Linux install | macOS |
|------|------------|---------------|--------|
| Bundled assets (starter profiles, default images) | repo `Profiles/`, `Images/` | package share dir | `.app` Resources |
| User profiles + dynamic bindings | `~/.config/loupedeckapp/` (migrate from repo-local when present) | same | `~/Library/Application Support/LoupedeckApp/` |

`LdConfiguration` must stop using `./Profiles/...`.

### 4.4 Profile match schema (cross-platform)

Extend dynamic bindings so the same file can work on Linux and macOS:

```jsonc
{
  "dynamic_mode": true,
  "default_profile": "default",
  "app_profiles": [
    { "match": { "wm_class": "google-chrome" }, "profile": "browser" },
    { "match": { "bundle_id": "com.google.Chrome" }, "profile": "browser" },
    { "match": { "title_contains": "—" }, "profile": "optional" }
  ]
}
```

Exact match preferred; then case-insensitive substring (existing behaviour for `wm_class`).

### 4.5 Config schema

**Current:** schema **v4** (actions, images, labels, led_colors, bg_colors; CT dial/wheel/buttons).
Older profiles load with migration-by-overlay (missing keys default to unbound).

**Planned v5:** a per-workspace `tuning` map for rotary controls (§5.D.1), keyed like the existing
`labels` / `led_colors` / `bg_colors` maps so the same overlay migration applies and `LdAction`
stays unchanged.

Future schema bumps only when needed (e.g. macros, named workspaces, side-display mode).

---

## 5. Workstreams

### A. Consistency & single product UI ✅ direction locked

- [x] Qt-free core + QML front-end driving `DeviceController`
- [ ] **AppPaths** — user dir + bundled assets; fix all profile/image I/O
- [ ] **Platform factory stubs** — re-home existing Linux backends behind `get_input_backend()` /
      `get_window_watcher()` / OS action defaults (behaviour unchanged on KDE)
- [ ] QML: **bind focused app → profile**, list/edit/remove bindings, show current focus class
- [ ] QML: **profile lifecycle** — create, rename, duplicate, delete; set default
- [ ] Wire action **search**; hide empty library categories
- [ ] Dirty guards: warn on profile switch / quit if unsaved
- [ ] **Deprecate then remove** PyQt5 entry (`app.py`, `LdApp.py`, `LdWidget.py`, `LdDialog.py`)

### B. Device correctness *(mostly done)*

- [x] CT/Live/Live S profiles, PID detect, wheel/dial/CT buttons
- [ ] Live S / Live **device view** fidelity (hide wheel/dial when absent; 5-col Live S)
- [ ] Brightness control in UI
- [ ] Reconnect / hot-plug
- [ ] Side displays: full-height single image **vs** 3 cells (configurable)

### C. Platform adapters

**Linux (now)**

- [x] ydotool / xdotool / pyautogui; playerctl media
- [x] KDE `kdotool` watcher
- [ ] Surface “input backend unavailable” in UI (not only console)
- [ ] Optional later: GNOME / X11 `_NET_ACTIVE_WINDOW` watchers

**macOS (M6) — support floor: 10.14 Mojave**

- [ ] `MacQuartzBackend` (or equivalent) for hotkey + type; map `cmd`/`command`/`super`
- [ ] Media via AppleScript / system media keys (not MPRIS)
- [ ] Launch via `open -a` / bundle id–aware actions
- [ ] `MacFrontmostWatcher` (`NSWorkspace` + optional Accessibility)
- [ ] Match on `bundle_id` (+ name fallback)
- [ ] First-run: **Accessibility** (and any serial) permission copy
- [ ] Build/test matrix must keep **10.14** viable: pin PySide6 / Python / packaging so the
      shipped app does not require a newer macOS than 10.14 unless a hard dependency forces a
      bump (document if that ever happens)

### D. Action system & library

- [x] Types: `command`/`launch`, `hotkey`, `text`, `media`, `submenu`, `back`, `none`
- [x] Library + drag-drop; hotkey recorder; common + KDE shortcut pick-lists
- [ ] Real search/filter; platform-neutral defaults (no hard-coded `konsole`/`dolphin` only)
- [ ] Macros (`multi` sequence)
- [ ] Encoder **adjustments** (relative steps: volume, scrub, …) — see **D.1**
- [ ] Per-control rotation tuning: invert, sensitivity, acceleration curve (**D.1**)
- [ ] **Scroll / mouse-wheel** action type (`input_backend` has no scroll verb today) (**D.1**)
- [ ] Move action execution off the device reader thread (**D.1** prerequisite)
- [ ] Later: plugin registration (OBS, etc.)

#### D.1 Encoder feel — direction, sensitivity, acceleration *(community request)*

Rotary controls today fire **exactly one action per detent**, in whichever direction the hardware
reports. Nothing can slow a control down, speed it up, or reverse it short of manually swapping the
`-l` / `-r` bindings. The official app has the same limitation, so this is differentiator work
rather than parity work.

**What the hardware gives us.** `on_rotate` in the devleaks lib emits one message per detent
carrying a *direction only* (`left` / `right`) — no magnitude — plus a `ts` timestamp. Every notion
of "speed" therefore has to be synthesised in our dispatch layer from tick **rate**; the device
will never report one.

**Model — per control, not per slot.** Invert spans both directions and speed is a physical
property of the encoder, so tuning is keyed by control (`enc1L`, `dial`), not by rotate slot.

| Knob | Meaning |
|------|---------|
| `invert` | Swap `-l` / `-r` at dispatch time |
| `detents_per_step` | Divide — fire once every N detents (slow a control down) |
| `steps_per_detent` | Multiply — fire N times per detent (speed a control up) |
| `curve` | `linear` (fixed multiplier) or `accel` (multiplier scales with tick rate, clamped by `max_steps`) |

**Backend work.** `send_hotkey` needs a `repeat` argument so N steps cost one process spawn:
`ydotool key` already accepts an arbitrary list of `CODE:STATE` pairs, so the down/up pair is
simply emitted N times in a single invocation (`xdotool key --repeat N` on X11).

**This also unlocks the "mouse wheel" half of the request.** There is no scroll action at all
today. `ydotool mousemove -w <dx> <dy>` emits `REL_HWHEEL` / `REL_WHEEL` — a *magnitude* per call,
not a repeat — which makes scroll both the cheapest new action to add and the ideal one to prove
the curve against, since accelerating it is a bigger number rather than more calls. Also fills the
empty **Adjustments** library category (§3).

**Prerequisite — get action execution off the reader thread.** `DeviceController.device_callback`
runs on the devleaks serial reader thread, and every action does a blocking `subprocess.run`.
That is already a latency risk at one action per detent; with acceleration it becomes a guaranteed
stall (`ydotool key` alone spends ~12 ms *per key event* by default, so a 5× repeat is ~120 ms of
blocked reader). Needs a single-consumer dispatch queue that **coalesces** pending rotate steps per
control instead of queueing unboundedly. Do this before, or alongside, the curve work.

**Repeatability by action type.** `hotkey` / `scroll` repeat; `text` repeats (rarely wanted);
`command` / `launch` / `media` / `submenu` / `back` clamp to 1 — never repeat a process spawn.

**Sequencing.** Async dispatch and `invert` are small and independent — invert is usable
immediately since both rotate slots already exist. Sensitivity, the accel curve, and the scroll
action land together with schema v5 in **Phase C**.

### E. Profiles & dynamic mode

- [x] Schema + ProfileManager + KDE live switch verified
- [ ] Full QML management UI (bindings + default + CRUD)
- [ ] Import / export profile JSON
- [ ] Ship **starter profiles** (media, system, browser, empty scratch) with icons
- [ ] Cross-platform match keys (§4.4)

### F. UI polish

- [x] Dark theme, three columns, inspector, Save/Revert, copy/paste, submenus
- [ ] Functional search; workspace name in header
- [ ] Keyboard shortcuts (Ctrl/Cmd+S, copy/paste control, Esc)
- [ ] Toasts / empty states / first-run drag-drop tip
- [ ] Inspector collapsible sections (Action / Appearance / Advanced)
- [ ] Optional later: split fat `Backend` QObject; photoreal device chrome

### G. Packaging & distribution (M5 Linux first)

- [ ] `pyproject.toml` + pinned deps (replace ad-hoc pip lines)
- [ ] Ship udev rule snippet; document dialout/plugdev + ydotool
- [ ] **Flatpak** and/or **AppImage**
- [ ] Minimal automated tests: schema load/migrate, profile resolve, label compose
- [ ] Promote useful `scratch/` probes to `scripts/verify/` smoke checks

### H. Project independence

- [x] README rewritten as standalone CT-focused project (origin credit to flowernert)
- [ ] Detach GitHub fork relationship if still marked as fork (Support ticket or rename/recreate)
- [ ] Keep `upstream` remote optional for cherry-picks

### I. macOS release (M6)

Sub-milestones:

| Slice | Goal | Exit |
|-------|------|------|
| **M6a** | Device + mirror + edit/save on Mac | CT enumerates; profile renders; official app not holding the port |
| **M6b** | Input works | Hotkey/text/media/launch; Accessibility documented |
| **M6c** | Dynamic mode | Frontmost app → profile via bundle id |
| **M6d** | Ship `.app` | PyInstaller/Briefcase (or equivalent); Resources + App Support paths; optional notarization for distribution outside dev machines |

**Compatibility:** minimum **macOS 10.14**. Prefer APIs and dependency pins that remain runnable on
10.14–current; CI or a manual checklist should include a 10.14 (or oldest available) smoke path
when hardware/VMs allow.

---

## 6. Phased roadmap (agreed)

Milestones stay independently valuable. **Do Phase A before M5/M6 packaging** so paths and
adapters are not reworked after installers exist.

| Phase / milestone | Goal | Contains | Exit criteria |
|-------------------|------|----------|---------------|
| **M0 — Baseline** *(done)* | Runs on CT | Fork, deps, permissions | App drives CT without sudo |
| **M1 — CT correctness** *(done)* | Correct geometry & I/O | DeviceProfile, ct_support | All CT controls decode; wheel renders |
| **M2 — Input** *(done)* | Actions on Wayland | input_backend | Hotkey/text into native Wayland clients |
| **M3 — Profiles** *(done)* | Per-app dynamic switch | schema, ProfileManager, kdotool | Live Chrome→blue / else→red verified |
| **M4 — QML UI** *(feature-complete; polish remains)* | Modern editor | Shell, mirror, inspector, draft, copy/paste, library DnD, submenus, labels/LEDs/bg | ✅ listed features work on-device; remaining items → Phase A / F |
| **Phase A — Consistency** *(next)* | One product, portable core | AppPaths, platform factories, QML bind-app + profile CRUD, search, dirty guards, deprecate PyQt5 | QML alone is enough to use daily; no CWD-relative profiles; Linux behaviour unchanged |
| **M5 — Ship Linux** | Installable by non-devs | Workstream G; starter profiles; udev/ydotool docs; optional defork | Flatpak and/or AppImage on clean KDE; pinned deps; smoke tests green |
| **Phase C depth** *(ongoing after M5)* | Product depth | Macros, adjustments, side-display modes, Live S view, GNOME watcher optional, UI polish (F) | Documented per feature |
| **M6 — macOS** | Native Mac app, **10.14+** | M6a→M6d; Workstream C mac + I | CT configure + actions + optional dynamic mode from a 10.14-compatible `.app` |

```
Phase A (consistency)
    → M5 (ship Linux)
        → Phase C depth (parallel OK)
        → M6 macOS (M6a device → M6b input → M6c dynamic → M6d package)
```

---

## 7. Functionality checklist (agreed)

Near-term (Phase A / M5):

- [ ] Dynamic-mode full UX in QML (bind / list / remove / default)
- [ ] Profile create / rename / duplicate / delete / import / export
- [ ] Action library search + non-empty categories + OS-aware defaults
- [ ] Brightness, reconnect, backend health in UI
- [ ] Starter profiles with real defaults
- [ ] Live / Live S mirror fidelity

Medium-term (Phase C):

- [ ] Macro / multi-step actions
- [ ] Encoder adjustments — invert, sensitivity, acceleration curve, scroll action (§5.D.1)
- [ ] Async action dispatch (off the device reader thread) + rotate coalescing (§5.D.1)
- [ ] Configurable side-display layout
- [ ] Optional tray / autostart / always-on runtime split
- [ ] Plugin hooks (later)

---

## 8. UI checklist (agreed)

- [ ] Wire action search; filter chips optional
- [ ] Workspace indicator / name in header
- [ ] Dirty-state safety on switch / quit
- [ ] Keyboard shortcuts (platform-native modifier)
- [ ] Empty states, error toasts, first-run tip
- [ ] Inspector sections (Action / Appearance / Advanced)
- [ ] Hide empty library categories
- [ ] Optional: thinner Backend bridge; richer device chrome

---

## 9. Risks & constraints

| Risk | Mitigation |
|------|------------|
| ydotool / uinput setup friction on Linux | Document + package; UI status when daemon down |
| KWin / kdotool API drift | Keep polling backend thin; optional DBus later |
| Fast encoder twists stalling the device reader thread | Async dispatch queue + per-control coalescing before shipping acceleration (§5.D.1) |
| Dual UI divergence | Phase A: freeze/remove PyQt5 |
| CWD-relative profiles break packaging | AppPaths first |
| Official Loupedeck app holds USB on Mac | Document quit-official-app; exclusive serial |
| macOS Accessibility prompts | First-run UX; NullBackend with clear disable message until granted |
| **macOS 10.14 floor** vs modern Qt/Python wheels | Pin toolchain early in M6a; verify on 10.14 before promising in README; if upstream drops 10.14, document the new floor |
| Python 3.14 / bleeding-edge wheels | Pin supported ranges in pyproject for release builds |
| Competing with official Mac plugins | Don’t; ship open CT config + actions |

---

## 10. Status & next actions

**Completed milestones:** M0, M1, M2, M3, M4 feature slices (shell → device → mirror → inspector →
draft/copy-paste → submenus → library DnD → labels/LEDs/bg).

**Immediate next (Phase A):**

1. Introduce `AppPaths`; migrate profile + dynamic binding I/O off CWD.
2. Introduce platform factories; move existing Linux backends behind them (no behaviour change).
3. QML: bind focused app, manage bindings, profile CRUD.
4. Wire action search; dirty quit/switch guards.
5. Mark legacy PyQt5 deprecated in README; remove when 3–4 are solid.

**Then M5:** pyproject + pins, udev/ydotool packaging notes, Flatpak/AppImage, starter profiles,
smoke tests.

**Then M6:** macOS 10.14+ path as in §5.I / §6.

Historical probe notes and CT verification details live under `scratch/` (gitignored) and older
commit messages; device behaviour above is the source of truth for planning.
