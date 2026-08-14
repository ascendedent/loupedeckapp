# AppImage

A single self-contained file: the app, its Python dependencies, a Python
interpreter and the parts of Qt it uses. Download it, `chmod +x`, run it.

```bash
./packaging/appimage/build.sh                    # -> dist/LoupedeckConfig-x86_64.AppImage
APPIMAGE_SKIP_PACK=1 ./packaging/appimage/build.sh   # AppDir only, runnable as build/appimage/loupedeckapp.AppDir/AppRun
```

`appimagetool` is downloaded on first run if it is not on PATH.

**This is the recommended single-file build.** An AppImage is a bundle, not a
sandbox, so the app has exactly the access the user running it has. That
matters here: typing needs `/dev/uinput` through ydotool, and the device is a
serial port. See [../flatpak/README.md](../flatpak/README.md) for why the
sandboxed format is a worse fit.

It does **not** remove the host setup: the udev rule for the device and a
running `ydotoold` are still needed, and the app's Setup dialog will say so
with the commands.

## Notes on the build

**Trimming.** Untrimmed, the bundle is ~800MB, of which 195MB is a web browser
engine PySide6 ships and this app never loads. The trim list names modules to
remove and matches both spellings, `QtWebEngine` (PySide's module) and
`libQt6WebEngineCore` (the library), because a list of only the first spelling
missed the largest file in the bundle. Result: ~325MB, ~120MB compressed.

**site-packages is not the standard library.** The interpreter's stdlib is
copied from the build machine, and on Fedora that directory also contains
whatever the machine has installed. Copying it wholesale swept 30MB of
unrelated packages into the bundle. It is explicitly removed; pip fills that
directory properly afterwards.

**`--ignore-installed` is not optional.** pip decides what is already satisfied
by looking at the environment it runs in, so building from a virtualenv that
has PySide6 in it produced a bundle with no PySide6 at all, which failed only
at runtime.

**Verified so far:** the AppDir builds, runs offscreen, and opens a real window
on Wayland with its own config directory, from outside the checkout. The final
`appimagetool` step (squashing the AppDir into one file) has **not** been run
here; it needs a download and has no offline substitute.
