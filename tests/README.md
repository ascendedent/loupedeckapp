# tests

Plain-Python checks, no framework. Run them all:

```bash
.venv/bin/python tests/run_all.py
```

or one at a time, e.g. `.venv/bin/python tests/test_tuning.py`.

Each file prints one line per check and exits non-zero if any failed. They need
no Loupedeck device: `DeviceController` is constructed without connecting, and
the input backend is stubbed wherever a test would otherwise inject keystrokes.

`test_ui.py` is the one exception to "no Qt": it loads `Main.qml` into an
offscreen window to check that a control is wired to the slot it claims to
call, which nothing below the UI can see. It forces `QT_QPA_PLATFORM=offscreen`
and drives keys through Qt, so it never puts a window on the desktop and no
other application can receive its input. Driving the UI by clicking at screen
coordinates is not an option: the keystrokes land wherever the pointer actually
went, which on a multi-monitor desktop is not where the arithmetic said.

| File | Covers |
|------|--------|
| `test_tuning.py` | schema v5 tuning: normalisation, presets, persistence, per-type repeat |
| `test_inheritance.py` | tuning inherited into submenus, unknown-key preservation |
| `test_queue.py` | coalescing rotate dispatch: batching, cancellation, teardown |
| `test_accel.py` | interval-based acceleration: curve shape, timing, backlog cap |
| `test_paths.py` | user vs bundled assets, copy-on-write, migration, installed layout |
| `test_platform.py` | session/desktop detection, factory selection, per-desktop library |
| `test_drafts.py` | unsaved-edit guards, including held dynamic switches |
| `test_importexport.py` | profile import/export, validation and name collisions |
| `test_reconnect.py` | connection supervision: connect, loss, reconnect, teardown |
| `test_settings.py` | app preferences: persistence, clamping, brightness on device |
| `test_inputhealth.py` | input backend health reporting and runtime failure capture |
| `test_buttons.py` | CT button defaults, workspace and keyboard action types |
| `test_fn.py` | the fn layer: hold vs latch, secondary dispatch, stuck-layer guards |
| `test_macro.py` | macro parsing, worker execution, serialisation, failure handling |
| `test_models.py` | per-model control inventory (CT / Live / Live S) and the model override |
| `test_workspaces.py` | schema v7 workspace names, switching, and the label fallback |
| `test_ui.py` | the real QML offscreen: control-to-slot wiring and keyboard shortcuts |
| `test_tray.py` | tray settings and the menu built from backend state |
| `test_packaging.py` | what a wheel would contain: module manifest, assets, desktop entry |
| `test_setup.py` | first-run checks: severity, the summary the top bar reads, failure isolation |
| `test_autostart.py` | the XDG autostart entry, including the stale-entry case |
| `test_macos.py` | the macOS adapters as far as they can be checked from Linux |
| `test_starter.py` | the shipped starter profile: every binding real, parseable and reachable |
| `test_startup.py` | which profile a launch opens, and what is remembered |
| `test_sidedisplay.py` | side strips as cells or one image: routing, rendering, size hint |
| `test_apps.py` | applications, their match rules, and the pages that switch inside them |
| `test_installed.py` | reading installed applications: desktop entries, bundles, match keys |
| `test_watchers.py` | reading the focused window per desktop, and choosing a watcher |
| `test_trash.py` | deleting keeps a copy, without growing without limit |
| `test_profilestore.py` | profile and application file handling, with no Qt involved |
