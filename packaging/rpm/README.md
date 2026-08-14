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
sudo dnf install rpm-build rpmdevtools python3-devel pyproject-rpm-macros \
                 python3-setuptools
rpmdev-setuptree
git archive --format=tar.gz --prefix=loupedeckapp-0.5.0/ \
    -o ~/rpmbuild/SOURCES/loupedeckapp-0.5.0.tar.gz HEAD
rpmbuild -ba packaging/rpm/loupedeckapp.spec
```

## What has actually been verified

**The RPM builds.** `rpmbuild -ba` produces
`loupedeckapp-0.5.0-1.fc44.noarch.rpm` on Fedora 44, and the result was
unpacked and checked:

- every module listed in `pyproject.toml` is in the package
- `/usr/bin/loupedeckapp`, the desktop entry, the icon, the udev rule and the
  ydotool drop-in all land where they should
- the assets resolve from `/usr/share/loupedeckapp`, both shipped applications
  are visible, and the setup advice points at a udev rule that exists
- dependencies come out as `ydotool` plus the Python three, with `kdotool`,
  `playerctl` and the device library as weak ones

What has **not** been done is installing it, which would pull Qt in system-wide
on a machine that runs the app from a checkout. And it has not been through
`rpmlint` or a Fedora review, so treat it as a working package rather than a
compliant one.

Three things the build itself turned up, all fixed:

- `%pyproject_buildrequires` turns the runtime dependencies into build
  dependencies by default, so building a package of pure Python files wanted
  ~200MB of Qt on the build host. `-R` and an explicit `Requires:` list instead.
- `%pyproject_save_files` was given the distribution name. This project has a
  flat module layout, so there is no package named after it and the macro
  correctly refused.
- `pyproject.toml` declared its licence as a TOML table, which setuptools has
  deprecated and warned about on every build. It is an SPDX string now.

The `PKGBUILD` has **not** been built. There is no Arch machine here, so treat
it as a draft; if you build one, a pull request correcting it is worth more
than the file is.

## After installing

Two things a package cannot do for you, because neither survives an
installation script:

```bash
sudo usermod -aG dialout "$USER"     # then log out and back in
sudo systemctl enable --now ydotool
```

The app's Setup dialog checks both and prints the commands, so you do not have
to remember this page.
