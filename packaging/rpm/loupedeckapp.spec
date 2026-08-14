# RPM package for loupedeckapp.
#
# The reason this exists when there is already a wheel and an AppImage: a
# distribution package is the only format that can do the setup for you. It
# installs the udev rule so the device is reachable without root, and it can
# depend on ydotool, kdotool and playerctl rather than printing instructions
# for them.
#
# Build:
#   rpmdev-setuptree
#   spectool -g -R packaging/rpm/loupedeckapp.spec     # or copy a tarball in
#   rpmbuild -ba packaging/rpm/loupedeckapp.spec
#
# The device library is not on PyPI and is not packaged anywhere, so it is a
# weak dependency: the app starts without it and says what is missing.

%global appname loupedeckapp
%global appid   loupedeckapp

Name:           %{appname}
Version:        0.5.0
Release:        1%{?dist}
Summary:        Configuration app for Loupedeck CT, Live and Live S

License:        GPL-3.0-or-later
URL:            https://github.com/ascendedent/loupedeckapp
Source0:        %{url}/archive/v%{version}/%{appname}-%{version}.tar.gz

BuildArch:      noarch
BuildRequires:  python3-devel
BuildRequires:  pyproject-rpm-macros
BuildRequires:  systemd-rpm-macros

Requires:       python3-pyside6
Requires:       python3-pyserial
Requires:       python3-pillow
# Typing into other applications on Wayland goes through uinput; this is the
# only part of the app that cannot be made to work without a helper.
Requires:       ydotool
# Focus detection for dynamic profile switching, and media keys. Neither is
# needed to configure a device, so they are recommendations rather than hard
# requirements.
Recommends:     kdotool
Recommends:     playerctl
# Not packaged anywhere: see the note at the top.
Suggests:       python3-loupedeck

%description
A configuration app for Loupedeck devices on Linux, where the official software
does not exist. Assign images, labels and actions to keys, encoders, side
screens and the CT wheel; organise them into workspaces and submenus; and have
profiles switch automatically as you change application.

Wayland input is delivered through ydotool; X11 through xdotool. After
installing, log out and back in once so the dialout group applies.

%prep
%autosetup -n %{appname}-%{version}

%generate_buildrequires
# -R: do not turn the runtime dependencies into build dependencies. This is a
# noarch pure-Python package that runs no tests at build time, so building it
# does not need PySide6 installed, and requiring it would mean pulling ~200MB
# of Qt onto a build host to copy some .py files. The runtime dependencies are
# declared explicitly below instead.
%pyproject_buildrequires -R

%build
%pyproject_wheel

%install
%pyproject_install
# The modules, not the distribution: this project has a flat layout, so there
# is no package named after it for the files to travel inside.
%pyproject_save_files -l qml_app device_controller LdConfiguration \
    DeviceProfile ct_support label_render input_backend window_watcher \
    profile_manager system_shortcuts platform_env action_library app_paths \
    autostart device_lib installed_apps macro settings setup_check tray \
    virtual_keyboard

# udev rule: lets a desktop user open the device without root.
install -Dpm 0644 packaging/99-loupedeck.rules \
    %{buildroot}%{_udevrulesdir}/99-loupedeck.rules

# ydotoold's socket has to be reachable by the user running the app, and the
# daemon has to stay root to open /dev/uinput.
install -Dpm 0644 packaging/ydotool-user-socket.conf \
    %{buildroot}%{_unitdir}/ydotool.service.d/override.conf

%files -f %{pyproject_files}
%doc README.md docs/HOW-TO-BUILD.md
%{_bindir}/%{appname}
%{_datadir}/%{appname}/
%{_datadir}/applications/%{appid}.desktop
%{_datadir}/icons/hicolor/scalable/apps/%{appid}.svg
%{_udevrulesdir}/99-loupedeck.rules
%{_unitdir}/ydotool.service.d/override.conf

%post
# The rule only takes effect for a device that is already plugged in after a
# reload, and the group only after the user logs back in.
/usr/bin/udevadm control --reload-rules >/dev/null 2>&1 || :
/usr/bin/udevadm trigger --subsystem-match=tty >/dev/null 2>&1 || :
%systemd_post ydotool.service

%postun
/usr/bin/udevadm control --reload-rules >/dev/null 2>&1 || :

%changelog
* Fri Aug 14 2026 JM <jm@gtmbrands.com> - 0.5.0-1
- First packaged release.
