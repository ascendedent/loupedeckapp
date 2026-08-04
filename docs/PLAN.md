# loupedeckapp Build Plan

Roadmap for a robust, modern Loupedeck configuration app: **Linux first** (primary), then
**macOS** (minimum target **macOS 10.14 Mojave**). Full **Loupedeck CT** support, Live / Live S
kept working where practical. UI aims to approach the official Loupedeck desktop app.

> **Authorship.** Commits, tags, release notes, and public docs are authored by the human
> maintainer only. Do not add co-author trailers, “generated with …”, or similar attribution for
> tooling. The `commit-msg` hook rejects common automated-attribution patterns.

---

## 1. Vision

A native configuration app that lets you visually configure a Loupedeck device: assign images,
labels, colours, and actions to every touch key, side display, encoder, and (on the CT) the wheel
and dial; organise them into workspaces and nested submenus; and optionally auto-switch profiles
based on the focused desktop application. All with a modern, dark, responsive UI.

| Priority | Platform | Notes |
|----------|----------|--------|
| **P0** | Linux (KDE Wayland primary; X11 fallback) | Ship first (packaging + polish) |
| **P1** | macOS **10.14+** | After Linux ships; adapters + `.app` |
| Later | Other Linux DEs (GNOME, …) | Extra window/input backends |
| Out of scope for now | Windows | Same adapter pattern if demand appears |

Primary device: **Loupedeck CT**. Keep **Live / Live S** correct where practical.

**Product positioning on macOS:** open, scriptable, CT-focused, no account. Not a full clone of
the official plugin marketplace (which already covers Mac).

---

## 2. Current status (as of post-M4 feature work)

### Done (M0-M4 core)

| Area | Status |
|------|--------|
| CT / Live / Live S geometry + PID detect | ✅ `DeviceProfile` |
| Wheel screen, dial, CT buttons | ✅ `ct_support` + routing in `DeviceController` |
| Wayland input | ✅ `input_backend` (ydotool → xdotool → pyautogui) |
| Media / launch | ✅ playerctl + detached shell |
| Schema v2-v5 (dial/wheel/CT slots, labels, LEDs, bg colours, encoder tuning) | ✅ `LdConfiguration` |
| Dynamic mode (KDE) | ✅ `window_watcher` (kdotool) + `ProfileManager` |
| QML three-column shell + CT device mirror | ✅ `qml_app.py` + `qml/` |
| Inspector (actions, image, labels, LED, bg, encoder feel) | ✅ |
| Draft Save / Revert (mirror live, hardware on Save) | ✅ |
| Copy / paste control functions (type-checked) | ✅ |
| Action library + drag-drop onto controls | ✅ |
| Submenu create / enter / back from QML | ✅ |
| Labels, LED colours, backgrounds, image-fit | ✅ |
| Encoder feel (invert, speed presets, acceleration) | ✅ schema v5 + inspector |
| Scroll action + coalescing rotate dispatch | ✅ `input_backend` + `device_controller` |

### Dual UI (debt)

| Capability | QML (`qml_app.py`) | Legacy PyQt5 (`app.py` / `Ld*`) |
|------------|--------------------|----------------------------------|
| Device engine | `DeviceController` | Logic still in `LdApp` |
| Labels / LEDs / bg / draft / library | Yes | Limited / absent |
| Bind focused app → profile | **Missing** | Present |
| Product path | **Canonical** | **Deprecated**; freeze, then remove |

**DECIDED:** QML is the only product UI. No new features in the PyQt5 tree. Remove once QML has
parity on dynamic binding + profile lifecycle (Phase A).

### Known gaps (ordered by agreed priority)

1. **One UI**: finish QML parity; retire PyQt5.
2. **Platform adapters + paths**: explicit factories; no CWD-relative `./Profiles`.
3. **Ship Linux (M5)**: pin deps, packaging, udev/ydotool docs, starter profiles.
4. **Functionality**: dynamic UX, profile CRUD, real search library, device polish, Live S fidelity, macros.
5. **UI polish**: search, workspace chrome, dirty guards, inspector structure, empty categories.
6. **macOS (M6)**: adapters, Accessibility UX, `.app`, support **10.14+**.

---

## 3. Target experience (gap analysis vs. official app)

| Area | Official app | Us today (QML) | Remaining gap |
|------|--------------|----------------|---------------|
| **Top bar** | Device · app-profile · Dynamic · workspace · status | Device pill · profile name · Save/Revert · Dynamic | Profile picker depth, workspace name, reconnect status, input-backend health |
| **Left panel** | Searchable action library | Categorised library + drag-drop | **Search is UI-only (not wired)**; KDE-hardcoded apps |
| **Center** | Photorealistic device | Schematic CT mirror; live images/labels/LEDs | Optional photoreal polish; Live/Live S layout fidelity |
| **Right panel** | Profiles + pages tree | Profile list + rich inspector | Profile create/rename/delete/import; bind-app UI; pages hierarchy |
| **Profiles** | System + per-app + dynamic | Files on disk + `dynamic_profiles.json` | Full lifecycle; multi-key match (`wm_class` / `bundle_id`) |
| **Theme** | Dark, rounded | Dark themed QML | Toasts, first-run tips, inspector sections |

---

## 4. Architecture

### 4.1 UI stack (decided)

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
    { "match": { "title_contains": "Gmail" }, "profile": "optional" }
  ]
}
```

Exact match preferred; then case-insensitive substring (existing behaviour for `wm_class`).

### 4.5 Config schema

**Current:** schema **v5** (actions, images, labels, led_colors, bg_colors, tuning; CT
dial/wheel/buttons). Older profiles load with migration-by-overlay (missing keys default to
unbound).

**v5 (landed):** a per-workspace `tuning` map for rotary controls (§5.D.1), keyed like the existing
`labels` / `led_colors` / `bg_colors` maps so the same overlay migration applies. `LdAction` gained
only an optional `repeat` argument on `execute()`. Entries are keyed by *control* (`enc1L`,
`dial`), not by rotate slot, and pass through `normalize_tuning()` on load so a partial or
hand-edited entry can never reach dispatch.

Future schema bumps only when needed (e.g. macros, named workspaces, side-display mode).

---

## 5. Workstreams

### A. Consistency & single product UI ✅ direction locked

- [x] Qt-free core + QML front-end driving `DeviceController`
- [ ] **AppPaths**: user dir + bundled assets; fix all profile/image I/O
- [ ] **Platform factory stubs**: re-home existing Linux backends behind `get_input_backend()` /
      `get_window_watcher()` / OS action defaults (behaviour unchanged on KDE)
- [ ] QML: **bind focused app → profile**, list/edit/remove bindings, show current focus class
- [ ] QML: **profile lifecycle** (create, rename, duplicate, delete; set default)
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

**macOS (M6). Support floor: 10.14 Mojave**

- [ ] `MacQuartzBackend` (or equivalent) for hotkey + type; map `cmd`/`command`/`super`
- [ ] Media via AppleScript / system media keys (not MPRIS)
- [ ] Launch via `open -a` / bundle id-aware actions
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
- [ ] Encoder **adjustments** (relative steps: volume, scrub, …), see **D.1**
- [ ] Per-control rotation tuning: invert, sensitivity, acceleration curve (**D.1**)
- [ ] **Scroll / mouse-wheel** action type (`input_backend` has no scroll verb today) (**D.1**)
- [ ] Move action execution off the device reader thread (**D.1** prerequisite)
- [ ] Later: plugin registration (OBS, etc.)

#### D.1 Encoder feel: direction, sensitivity, acceleration *(community request)*

Rotary controls today fire **exactly one action per detent**, in whichever direction the hardware
reports. Nothing can slow a control down, speed it up, or reverse it short of manually swapping the
`-l` / `-r` bindings. The official app has the same limitation, so this is differentiator work
rather than parity work.

**What the hardware gives us.** `on_rotate` in the devleaks lib emits one message per detent
carrying a *direction only* (`left` / `right`, no magnitude) plus a `ts` timestamp. Every notion
of "speed" therefore has to be synthesised in our dispatch layer from tick **rate**; the device
will never report one.

**Do not build the curve on `ts`.** The lib stamps `ts` with `datetime.now()` inside `on_rotate`,
and `on_rotate` runs on the *consumer* thread: `_process_messages` dequeues a message, then calls
the handler. By that point the message has already waited behind the previous action's blocking
`subprocess.run`. So `ts` records dispatcher throughput, not knob speed, and it skews worst during
fast twists, which is the only time a curve matters. Feeding it into a multiplier would feed our
own latency back into itself.

**Coalescing supplies the magnitude the hardware withholds.** Drain the pending events per control
and the *batch depth* is the speed signal: six detents waiting on `enc1L` means the user is
spinning it. That reading is count-based, so it sidesteps the timestamp problem entirely, and it
collapses the async-dispatch prerequisite and the acceleration feature into one piece of work
rather than two.

**Model: per control, not per slot.** Invert spans both directions and speed is a physical
property of the encoder, so tuning is keyed by control (`enc1L`, `dial`), not by rotate slot.

**Feel inherits down the submenu stack.** A submenu is its own `LdWorkspace`, so a knob set to
Fast 3x on a workspace would otherwise snap back to 1:1 the moment a submenu opened. Resolution
walks workspace → open submenus and takes the *nearest explicit entry*; a submenu that says nothing
borrows from its parent. A submenu may still override deliberately, including back to Original:
`set_tuning` compares against the **inherited** value rather than `DEFAULT_TUNING` when deciding
whether an entry is redundant, so an explicit 1:1 under a Fast 3x workspace is stored instead of
being dropped and silently re-inheriting. The inspector marks a borrowed value "(inherited)".

Scope is still per workspace. Feel is arguably a property of the hardware and might belong at
profile level with per-workspace override; deferred until the presets have been used in anger.

| Knob | Meaning |
|------|---------|
| `invert` | Swap `-l` / `-r` at dispatch time |
| `detents_per_step` | Divide: fire once every N detents (slow a control down) |
| `steps_per_detent` | Multiply: fire N times per detent (speed a control up) |
| `curve` | `linear` (fixed multiplier) or `accel` (multiplier scales with tick rate, clamped by `max_steps`) |

**Presets are the UI surface.** The request asked for discrete choices, not raw integers. The
inspector shows an Invert checkbox plus a speed dropdown; the two integer knobs stay as the schema
v5 representation underneath.

| Preset | Meaning | Maps to |
|--------|---------|---------|
| Original | 1 detent = 1 step | both knobs 1 |
| Slow 1/2 | 2 detents = 1 step | `detents_per_step` 2 |
| Slow 1/3 | 3 detents = 1 step | `detents_per_step` 3 |
| Fast 2x | 1 detent = 2 steps | `steps_per_detent` 2 |
| Fast 3x | 1 detent = 3 steps | `steps_per_detent` 3 |

**Slow is free; fast is not.** Slow is *subtractive*: it drops detents, spawns fewer processes than
today, and depends on none of the queue work, so it can ship beside `invert`. Fast is *additive*:
it synthesises events the hardware never sent, which is where the repeat plumbing and the latency
budget actually land. Splitting them is why the sequencing below no longer treats "sensitivity" as
one unit. Accumulators are per control and **reset on direction change**, otherwise reversing a
Slow 1/3 control costs two dead detents.

**Backend work.** `send_hotkey` takes a `repeat` argument: `ydotool key` already accepts an
arbitrary list of `CODE:STATE` pairs, so the down/up pair is simply emitted N times in a single
invocation (`xdotool key --repeat N` on X11).

Note the original justification for this ("N steps cost one process spawn") does **not** survive
measurement: bare spawn is **0.3 ms**, so three spawns cost ~1 ms. Batching is still worth doing
for *atomicity* (one invocation cannot be interleaved with another control's events, and the
modifier is held down once across the run rather than re-pressed per step), but not for latency.
Anything in this plan that gates work on spawn cost needs re-reading in that light.

**This also unlocks the "mouse wheel" half of the request.** *(Built.)* `ydotool mousemove -w
<dx> <dy>` emits `REL_HWHEEL` / `REL_WHEEL`, a *magnitude* per call rather than a repeat, so a
`scroll` action takes its repeat count as distance in a single invocation rather than N calls. That
makes it the ideal control to prove the curve against, since accelerating it is a bigger number
rather than more work. Directions are `up` / `down` / `left` / `right`, and the four now fill the
previously empty **Adjustments** library category (§3). On X11 there is no magnitude at all, so
`xdotool click --repeat N` on buttons 4/5/6/7 stands in.

**Prerequisite: get action execution off the dispatch thread.** `DeviceController.device_callback`
runs on the devleaks *message* thread (`_process_messages`), not the serial reader; `_read_serial`
is a separate thread feeding an unbounded `Queue`. Serial reading is therefore never blocked and no
device message is ever lost. The failure mode is not a stall but **overshoot**: every action does a
blocking `subprocess.run`, so when the detent rate outruns the consumer the backlog drains *after*
the user's hand stops and the control keeps adjusting past where they left it. That is a bug in
today's 1:1 behaviour, not something acceleration introduces.

**How urgent that is depends entirely on the key delay, and it has now moved.** *(Measured.)*
Dispatch capacity is `1000 / ms-per-detent`; a brisk human twist is roughly 15-25 detents/sec:

| scenario | ms/detent | detents/sec capacity | vs a brisk twist |
|----------|-----------|----------------------|------------------|
| `hotkey` at `-d 12` (before) | 48.60 | 21 | **overshoots** |
| `hotkey` at `-d 0` (now) | 0.56 | 1786 | 71x headroom |
| Fast 3x, three separate spawns | 1.68 | 595 | 24x headroom |
| Fast 3x, batched into one spawn | 0.60 | 1667 | 67x headroom |
| `media` (playerctl) | 2.60 | 385 | 15x headroom |

At `-d 12` capacity sat at 21 detents/sec, *inside* the range of a brisk twist, so overshoot was
not hypothetical. At `-d 0` the backlog cannot build from keyboard actions at any speed a hand can
produce. Measured per action type: `hotkey` 0.56 ms, `text` 0.20 ms, `launch`/`command` 0.09 ms
(a detached `Popen` that never waits on the child, so even a slow shell command does not block),
`media` 2.60 ms.

The coalescing queue is therefore **no longer a prerequisite for encoder tuning**. It remains worth
building for its own reasons: it is the only thing that bounds a genuinely slow action, and batch
depth is still the cleanest speed signal for the accel curve. But it no longer gates the presets.

**Batch depth is a dead speed signal.** *(Measured on hardware.)* Probing the CT at slow, brisk and
maximum hand speed across three controls produced `depth == 1` for **every single batch**. The
cause is not the hardware: a batch only forms when events pile up behind a blocking action, and
after the `-d 0` fix a hotkey costs ~0.56 ms against a hand that manages perhaps 25 detents/sec.
Capacity outruns the hand by ~70x, so the backlog the curve wanted to measure essentially never
exists. This follows directly from the latency measurement above and should have been predicted
from it.

The queue keeps its value (it still bounds a genuinely slow action, and cancellation still works),
but acceleration was re-based on a different signal: **each detent is timestamped in
`_enqueue_rotate`**, on the message thread the instant the event arrives, before anything can
block. Inter-detent interval measured there is a true reading of hand speed, and it sidesteps the
original objection to the lib's `ts` (that `ts` is stamped only after waiting behind a blocking
action). Batch depth remains the right *quantity* of detents to act on; it is simply useless as a
measure of speed.

**Queue: built.** Rotate events go onto a `queue.Queue` consumed by one dispatch thread. The
consumer takes an event, then drains whatever else is *already* waiting without ever waiting
itself, so an idle control still fires one detent immediately and batching only happens when events
genuinely piled up behind a slow action. Within a batch, opposite detents cancel: the net is where
the knob ended up, which is the honest reading for a continuous control and is what actually
cures overshoot. Batches are per control, so two knobs turned together do not merge. Queued
detents are discarded on workspace switch and profile load, since they were aimed at a menu that is
no longer on screen. A raising action is caught and logged rather than killing the dispatcher.

**Latency: the 12 ms is a default, not a floor.** *(Measured, superseding two earlier estimates.)*
`ydotool key` sleeps its delay after **every** key event, not between them. Measured on this
machine, the cost is linear in event count at 12.1 ms/event:

| events | 1 | 2 | 4 | 6 | 8 |
|--------|---|---|---|---|---|
| median ms | 12.3 | 24.4 | 48.7 | 72.9 | 97.0 |

So a four-event combo costs **~48 ms**, not the ~36 ms a previous revision of this section claimed;
the original "~12 ms per key event" reading was the correct one. Passing `-d 0` takes a combo from
**48.6 ms to 0.6 ms** (99% of the cost). That is a one-line change to the existing `send_hotkey`,
it needs no architecture work, and it is worth doing independently of encoder tuning. Keep the
value tunable rather than hard-coding zero, in case an app misses a modifier that has not settled.

**Modifier safety at `-d 0`: no loss observed.** 640 `ctrl+shift+<key>` combos across `-d` 0/1/4/12,
both paced and back-to-back with no gap (the shape a fast twist produces), against a native Wayland
client and an XWayland one: zero dropped or unset modifiers in every cell. The settling risk is
real in principle but did not reproduce here. Caveat: this only exercises a **Qt** receiver; GTK,
Electron, and browser hosts are unverified.

**Target-app coalescing: real, and fixed by spacing the repeats.** *(Measured, both layers.)*

*Delivery* is 1:1 and never was the problem: 600 `ctrl+shift+a` presses at `-d 0` (repeat depths
1/2/3/5/10, both the batched single-invocation form and N separate spawns) arrived 1:1 in every
cell against a Qt client, modifiers intact, none flagged as auto-repeat. The batched form is
delivery-equivalent to N spawns, so `repeat` can use it freely.

*Semantics* were the problem, and a Qt event counter could never have caught it. Against KDE's
system volume handler, a repeat of 3 at `-d 0` moved the volume exactly **1 step on every trial**.
At `-d 1` and above it moved **3 of 3 on every trial** (4 trials per gap at 0/1/2/3/5/8 ms). The
handler receives all three presses and chooses to collapse presses that arrive with no gap at all.

So a repeat needs a gap even though a single press does not. `YdotoolBackend.repeat_delay_ms`
(default 3 ms, margin over the sub-millisecond threshold) applies **only when repeat > 1**, leaving
the ~0.6 ms single-press path untouched. Verified live afterwards: repeat 1/2/3 moves volume 1/2/3
steps.

The general lesson is worth keeping: **delivery tests cannot answer semantic questions.** The most
permissive possible receiver (a widget counting key events) reported perfect fidelity for a
mechanism that did not work at all in the field. Other hosts may need a larger gap than 3 ms; that
is now one tunable value rather than a redesign.

**Repeatability by action type.** `hotkey` / `scroll` repeat; `text` repeats (rarely wanted);
`command` / `launch` / `media` / `submenu` / `back` clamp to 1, never repeating a process spawn.
Combined with coalescing this is what stops a fast spin on a "next track" knob from queueing a
dozen skips: the batch collapses to one call.

**Acceleration: rebuilt on inter-detent interval.** Speed is the gap between consecutive detents
on one control, timed in `_enqueue_rotate` on the message thread the instant the event arrives, so
it measures the hand rather than our own dispatch. This is what batch depth was supposed to be and
was not.

Shape is a linear ramp between two thresholds: at or slower than `accel_from_ms` the multiplier is
1, at or faster than `accel_full_ms` it is `max_steps`, and it interpolates between. Details that
matter in use:

* The first detent of a turn has no interval to measure against, so it never accelerates. A turn
  therefore always starts at 1:1, which is what makes small corrections predictable.
* A pause longer than `IDLE_GAP_S` (0.4 s) ends the turn, so a fresh nudge does not inherit the
  speed of a spin that already finished.
* The interval is smoothed (EMA, alpha 0.5) because raw gaps are jittery: one laggy click mid-spin
  would otherwise collapse the multiplier to 1.
* State is per control, and cleared on workspace switch and profile load alongside the accumulator.
* `linear` ignores speed entirely. A single detent is never capped under any curve, so what one
  click asks for is never discarded.
* **A coalesced batch is capped at `max_steps` whatever the curve.** Measured: feeding 125
  detents/sec into Fast 3x produced one dispatch per ~35 detents carrying `repeat` of ~105, which
  blocked for over half a second and kept moving **1.56 s after the hand stopped**. Bounding the
  backlog case brought that to 0.34 s. The rule is narrow on purpose: a single detent is literal
  intent and is honoured, but a backlog is already asking for more than the rate can deliver.

**Calibrated against a measured hand** (`scratch/probe_rotate.py`, CT side encoder):

| turning | median gap | detents/sec | multiplier at from=40 / full=8 |
|---------|-----------|-------------|-------------------------------|
| deliberate | 189 ms | 5 | 1.0x |
| comfortable working pace | 58 ms | 17 | 1.0x |
| full spin | 8 ms | **126** | 10.0x |

A full spin is **125 detents/sec**, five times the ~25/sec assumed throughout the earlier analysis.
The probe's own suggested `from` was 151 ms, which would have put a comfortable working pace at
6.7x; that is the wrong end to calibrate from. Acceleration should be something you opt into by
spinning, not something ordinary turning triggers, so `from` sits just under the working pace.

**Where acceleration actually pays.** A hotkey step costs two events at `repeat_delay_ms`, so
keystroke output is ceilinged near 167 steps/sec, and a linear full spin already delivers ~124.
Acceleration on a *hotkey* is therefore throughput-bound and mostly buys headroom at mid speeds. On
a *scroll*, magnitude rides in a single call at any size, so the curve delivers in full. Scroll is
the action this feature is really for.

**Sequencing.** *(Revised after measurement: tier 3 was gated on a latency budget that no longer
exists.)*

1. **Done:** the `send_hotkey` key-delay fix (`-d 0`). Pure latency win, no schema, no queue.
2. **Engine done (schema v5):** `invert` and the Slow presets. The per-workspace `tuning` map is
   keyed by control, `normalize_tuning` guarantees dispatch never sees a partial entry, and older
   profiles load at 1:1 unchanged. Accumulators live in the controller (not the profile) and reset
   on reversal and on workspace switch. Wired in both `DeviceController.on_rotate` and
   `LdApp.on_rotate` so the two front-ends feel the same. The QML inspector shows an "Encoder feel"
   section for rotate controls only: a preset dropdown, an Invert checkbox, and a plain-language
   summary of the resulting feel. Edits stage through `DeviceController.set_tuning` like any other
   draft edit; unlike images and LEDs there is nothing to repaint, since tuning only changes how
   incoming events are read.
3. **Engine done, same change: the Fast presets.** `send_hotkey(combo, repeat=N)` emits the
   batched form on ydotool (`--repeat` on X11); `text` repeats; `command` / `launch` / `media`
   clamp to 1 so a fast twist cannot fan out into N process launches. **The scroll action is not
   built yet.** These were held behind the queue on
   the assumption that adding events would blow a latency budget. Measured, Fast 3x costs 1.68 ms
   per detent even *unbatched* (24x headroom), so coalescing buys it nothing. Fast now ships with
   the Slow presets in the same schema v5 change; the two are one feature. Scroll never needed the
   queue either, since `ydotool mousemove -w` takes a magnitude rather than a repeat. Delivery of
   repeats is measured 1:1 (below), so the only remaining gate on Fast is whether a given host
   *acts* on every repeat, which is a per-app semantic question no dispatch work resolves.
4. **Built:** the coalescing queue, the scroll action, and the accel *mechanism*. The curve takes
   batch depth as its speed signal, so it did genuinely depend on the queue landing first.
5. **Confirmed on hardware:** Original / Slow / Fast all behave as intended, and the Slow reversal
   reset takes a fresh N detents rather than spending banked ones. Fast initially moved KDE volume
   1 step instead of 3; fixed by `repeat_delay_ms` (above).
6. **Built and calibrated:** acceleration on inter-detent interval, after batch depth was measured
   dead (below). Thresholds come from a measured hand and are confirmed working on hardware.
   Remaining polish, none of it blocking: tuning is scoped per workspace rather than per profile,
   and the inspector exposes the presets but not the raw integers behind them.

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
10.14-current; CI or a manual checklist should include a 10.14 (or oldest available) smoke path
when hardware/VMs allow.

---

## 6. Phased roadmap (agreed)

Milestones stay independently valuable. **Do Phase A before M5/M6 packaging** so paths and
adapters are not reworked after installers exist.

| Phase / milestone | Goal | Contains | Exit criteria |
|-------------------|------|----------|---------------|
| **M0: Baseline** *(done)* | Runs on CT | Fork, deps, permissions | App drives CT without sudo |
| **M1: CT correctness** *(done)* | Correct geometry & I/O | DeviceProfile, ct_support | All CT controls decode; wheel renders |
| **M2: Input** *(done)* | Actions on Wayland | input_backend | Hotkey/text into native Wayland clients |
| **M3: Profiles** *(done)* | Per-app dynamic switch | schema, ProfileManager, kdotool | Live Chrome→blue / else→red verified |
| **M4: QML UI** *(feature-complete; polish remains)* | Modern editor | Shell, mirror, inspector, draft, copy/paste, library DnD, submenus, labels/LEDs/bg | ✅ listed features work on-device; remaining items → Phase A / F |
| **Phase A: Consistency** *(next)* | One product, portable core | AppPaths, platform factories, QML bind-app + profile CRUD, search, dirty guards, deprecate PyQt5 | QML alone is enough to use daily; no CWD-relative profiles; Linux behaviour unchanged |
| **M5: Ship Linux** | Installable by non-devs | Workstream G; starter profiles; udev/ydotool docs; optional defork | Flatpak and/or AppImage on clean KDE; pinned deps; smoke tests green |
| **Phase C depth** *(ongoing after M5)* | Product depth | Macros, adjustments, side-display modes, Live S view, GNOME watcher optional, UI polish (F) | Documented per feature |
| **M6: macOS** | Native Mac app, **10.14+** | M6a→M6d; Workstream C mac + I | CT configure + actions + optional dynamic mode from a 10.14-compatible `.app` |

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
- [ ] `send_hotkey` key-delay fix: standalone latency win (§5.D.1)
- [ ] Starter profiles with real defaults
- [ ] Live / Live S mirror fidelity

Medium-term (Phase C):

- [ ] Macro / multi-step actions
- [ ] Encoder adjustments: invert + Slow presets, no queue dependency (§5.D.1)
- [ ] Encoder adjustments: Fast presets, acceleration curve, scroll action (§5.D.1)
- [ ] Async action dispatch (off the message/callback thread) + rotate coalescing (§5.D.1)
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
- [ ] Rotary tuning row: Invert checkbox + speed preset dropdown (§5.D.1)
- [ ] Hide empty library categories
- [ ] Optional: thinner Backend bridge; richer device chrome

---

## 9. Risks & constraints

| Risk | Mitigation |
|------|------------|
| ydotool / uinput setup friction on Linux | Document + package; UI status when daemon down |
| KWin / kdotool API drift | Keep polling backend thin; optional DBus later |
| Fast encoder twists overshooting (backlog drains after the hand stops) | Async dispatch queue + per-control coalescing before shipping acceleration (§5.D.1) |
| Accel curve misreading its own latency as knob speed | Derive speed from coalesced batch depth, never from the lib's `ts` (§5.D.1) |
| Target apps debouncing repeated keys, so Fast 2x/3x under-delivers | Per-app testing before advertising the Fast presets (§5.D.1) |
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
5. Mark legacy PyQt5 deprecated in README; remove when 3-4 are solid.

**Then M5:** pyproject + pins, udev/ydotool packaging notes, Flatpak/AppImage, starter profiles,
smoke tests.

**Then M6:** macOS 10.14+ path as in §5.I / §6.

Historical probe notes and CT verification details live under `scratch/` (gitignored) and older
commit messages; device behaviour above is the source of truth for planning.
