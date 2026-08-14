# Distribution packages

A wheel installs the app. An AppImage bundles it. Neither can do the part that
actually trips people up: the udev rule that makes the device reachable without
root, and the `ydotool` daemon that lets the app type. A distribution package
can, which is the only reason these exist.

| | |
|---|---|
| [`loupedeckapp.spec`](loupedeckapp.spec) | Fedora / RHEL |
| [`../arch/PKGBUILD`](../arch/PKGBUILD) | Arch, AUR |

Both install:

- the app and a `loupedeckapp` command
- the desktop entry and icon
- `packaging/99-loupedeck.rules` into the system udev rules
- the `ydotool` service drop-in that puts its socket somewhere the user can
  reach

and depend on `ydotool`, with `kdotool` and `playerctl` as recommendations
because neither is needed to configure a device.

The device library is a **weak** dependency in both. It is not on PyPI and not
packaged anywhere, so a hard dependency would make the package uninstallable.
The app starts without it and says what is missing.

## Building the RPM

```bash
sudo dnf install rpm-build rpmdevtools python3-devel pyproject-rpm-macros
rpmdev-setuptree
git archive --format=tar.gz --prefix=loupedeckapp-0.5.0/ \
    -o ~/rpmbuild/SOURCES/loupedeckapp-0.5.0.tar.gz HEAD
rpmbuild -ba packaging/rpm/loupedeckapp.spec
```

## What has actually been verified

The spec **parses** (`rpmspec -P`) and its sources, layout and scriptlets have
been reviewed against the Fedora Python packaging guidelines. It has **not been
built**: `python3-devel` and `pyproject-rpm-macros` are not installed on the
machine it was written on, and installing them is not something to do on
somebody's behalf.

The `PKGBUILD` has not been built either. There is no Arch machine here.

So treat both as drafts that are close rather than as tested packages. If you
build one, a pull request correcting it is worth more than the file is.

## After installing

Two things a package cannot do for you, because neither survives an
installation script:

```bash
sudo usermod -aG dialout "$USER"     # then log out and back in
sudo systemctl enable --now ydotool
```

The app's Setup dialog checks both and prints the commands, so you do not have
to remember this page.
