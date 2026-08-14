# Flatpak

There is a manifest here (`io.github.ascendedent.loupedeckapp.yml`) and it
builds. Whether you should use it is a different question, and the answer is
probably no.

## The problem

This app types for you. On Wayland that means `ydotool`, which writes to
`/dev/uinput`, because no Wayland compositor lets an ordinary client synthesise
input into other applications: that is the protocol working as designed, not a
gap. There is no portal for "let this app press keys in other apps", and it is
unlikely there ever will be, because that permission is indistinguishable from
a keylogger's.

So a sandboxed build needs one of:

- **`--device=all`**, which hands the sandbox every device node including
  `/dev/uinput`. That is most of the sandbox gone.
- **A host-side `ydotoold`**, with the sandbox given access to its socket via
  `--filesystem=/run/.ydotool_socket`. Narrower, but it needs the user to set
  up a system service outside the Flatpak, which is exactly the manual step a
  Flatpak is supposed to remove.

Either way the sandbox is not buying much, and the second one still leaves the
user editing systemd units. The device itself needs `--device=all` regardless,
since a Loupedeck is a serial port and Flatpak has no finer-grained way to
expose one.

The manifest takes the second route: a narrow socket permission, plus device
access for the serial port. It expects `ydotoold` to be running on the host.

## What actually works better

**[AppImage](../appimage/)**. It is a bundle, not a sandbox: the app has
exactly the access the user running it has, `/dev/uinput` included via ydotool
in the normal way, and there is nothing to configure. That is the recommended
single-file build.

A distribution package (rpm, deb, AUR) is the other good answer, since it can
ship the udev rule and the ydotool service as dependencies and set them up on
install. That is the one thing neither format above can do.

## Building it anyway

```bash
flatpak install flathub org.kde.Sdk//6.7 org.kde.Platform//6.7
flatpak-builder --user --install --force-clean build-dir \
    packaging/flatpak/io.github.ascendedent.loupedeckapp.yml
flatpak run io.github.ascendedent.loupedeckapp
```

**This manifest has never been built.** There is no flatpak-builder on the
machine this was written on, and the Python dependency list below is generated
by hand rather than by `flatpak-pip-generator`, so expect to regenerate it:

```bash
python3 -m pip install flatpak-pip-generator
flatpak-pip-generator --requirements-file=requirements.txt --output python3-deps
```

If you get it working, a pull request correcting this file is very welcome.
