# tests

Plain-Python checks, no framework. Run them all:

```bash
.venv/bin/python tests/run_all.py
```

or one at a time, e.g. `.venv/bin/python tests/test_tuning.py`.

Each file prints one line per check and exits non-zero if any failed. They need
no Loupedeck device: `DeviceController` is constructed without connecting, and
the input backend is stubbed wherever a test would otherwise inject keystrokes.

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
