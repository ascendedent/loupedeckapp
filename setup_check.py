"""What still needs setting up on this machine.

Everything here was previously a paragraph in the README that you had to know
to look for: the udev rule, the group membership, the ydotool socket, kdotool
for dynamic mode. A first run that silently does nothing is the worst version
of all of them, so the app asks these questions itself and says what to run.

Qt-free, like everything else below the UI. Each check returns a plain dict:

    id       stable key, for the UI and for tests
    title    one line, what is being checked
    ok       True when there is nothing to do
    optional True when the app works without it (a feature is lost, not the app).
             A property of the check, not of the outcome: it says the same
             whether the check passed or failed.
    detail   what is wrong, or what is fine
    fix      shell commands to fix it, or "" when there is nothing to run
"""

import os
import shutil

import app_paths
import device_lib
import input_backend
import platform_env

# The vendor the udev rule and the port scan both look for.
VENDOR_ID = 0x2EC2

UDEV_RULE = "/etc/udev/rules.d/99-loupedeck.rules"


def _check(id, title, ok, detail, fix="", optional=False):
    return {"id": id, "title": title, "ok": bool(ok), "optional": bool(optional),
            "detail": detail, "fix": fix.strip()}


def _packaged(name):
    """A file from packaging/, wherever the app is installed."""
    return app_paths.asset_path(os.path.join("packaging", name))


# -- individual checks --------------------------------------------------------

def check_device_library():
    ok, detail = device_lib.health()
    return _check(
        "device_library", "Device library",
        ok,
        "Installed." if ok else detail.split("\n\n")[0],
        "" if ok else device_lib.INSTALL_HINT)


def loupedeck_ports():
    """Serial ports that belong to a Loupedeck, as (path, pid) pairs."""
    try:
        import serial.tools.list_ports
    except ImportError:
        return []
    return [(p.device, p.pid) for p in serial.tools.list_ports.comports()
            if p.vid == VENDOR_ID]


def check_device_permissions():
    """Can we open the device without root?

    This is the one that bites hardest: the port exists, the app looks like it
    is working, and nothing connects. The rule and the group are both needed
    and neither is obvious.
    """
    if platform_env.os_name() == platform_env.MACOS:
        # macOS opens USB serial devices without any of this: no udev, no
        # group. Report what was found rather than a bare "fine".
        ports = loupedeck_ports()
        return _check("device_permissions", "Device permissions", True,
                      "%s is available." % ports[0][0] if ports else
                      "No Loupedeck is plugged in. macOS needs no udev rule or "
                      "group membership for one.")
    if platform_env.os_name() != platform_env.LINUX:
        return _check("device_permissions", "Device permissions", True,
                      "Not a Linux session; no udev rule needed.")
    ports = loupedeck_ports()
    rule_present = os.path.exists(UDEV_RULE)
    fix = (
        "sudo cp %s /etc/udev/rules.d/\n"
        "sudo udevadm control --reload-rules && sudo udevadm trigger\n"
        "sudo usermod -aG dialout \"$USER\"      # then log back in"
        % _packaged("99-loupedeck.rules"))

    if not ports:
        # Nothing plugged in: the rule can still be checked, and installing it
        # now beats discovering the problem when the device is in hand.
        return _check(
            "device_permissions", "Device permissions",
            rule_present,
            "No Loupedeck is plugged in. The udev rule is installed."
            if rule_present else
            "No Loupedeck is plugged in, and the udev rule is not installed "
            "yet. Install it now and the device will work when you plug it in.",
            "" if rule_present else fix)

    unreadable = [path for path, _ in ports
                  if not os.access(path, os.R_OK | os.W_OK)]
    if not unreadable:
        return _check("device_permissions", "Device permissions", True,
                      "%s is readable and writable." % ports[0][0])
    return _check(
        "device_permissions", "Device permissions", False,
        "%s exists but this user cannot open it, so no device will be found. "
        "%s" % (unreadable[0],
                "The udev rule is installed, so this is probably the group: a "
                "group change only applies after you log back in."
                if rule_present else "The udev rule is not installed."),
        fix)


def check_input():
    ok, name, detail = input_backend.health()
    if ok:
        return _check("input", "Keyboard and mouse input", True,
                      "Using %s." % name)
    fix = ""
    if platform_env.os_name() == platform_env.MACOS:
        # Nothing to install: the permission is the whole problem, and it is
        # granted in System Settings rather than from a command.
        return _check(
            "input", "Keyboard and mouse input", False,
            detail + "\n\nOn macOS this is almost always the Accessibility "
            "permission. Open System Settings > Privacy & Security > "
            "Accessibility and allow this app (or the terminal you started it "
            "from), then use Check again.")
    if platform_env.session_type() == platform_env.WAYLAND:
        fix = ("sudo dnf install ydotool        # or your package manager\n"
               "sudo mkdir -p /etc/systemd/system/ydotool.service.d\n"
               "sudo cp %s \\\n"
               "     /etc/systemd/system/ydotool.service.d/override.conf\n"
               "sudo systemctl daemon-reload && sudo systemctl enable --now ydotool"
               % _packaged("ydotool-user-socket.conf"))
    elif platform_env.session_type() == platform_env.X11:
        fix = "sudo dnf install xdotool        # or your package manager"
    return _check("input", "Keyboard and mouse input", False, detail, fix)


def check_window_watcher():
    """Only dynamic mode needs this, so it is optional."""
    if platform_env.os_name() == platform_env.MACOS:
        import window_watcher
        watcher = window_watcher.get_watcher()
        return _check(
            "window_watcher", "Focused-app detection",
            watcher.name != "none",
            "Reading the frontmost app needs the same Accessibility permission "
            "as sending keystrokes.", optional=True)
    import window_watcher
    watcher = window_watcher.get_watcher()
    if watcher.name != "none":
        return _check(
            "window_watcher", "Focused-app detection", True,
            "Using %s; dynamic mode can switch profiles." % watcher.name,
            optional=True)

    desktop, session = platform_env.desktop(), platform_env.session_type()
    if desktop == platform_env.KDE:
        return _check(
            "window_watcher", "Focused-app detection", False,
            "kdotool is not installed, so dynamic mode cannot tell which app "
            "you are in and will not switch profiles.",
            "sudo dnf install kdotool        # or your package manager",
            optional=True)
    if desktop == platform_env.GNOME:
        # Not something this app can fix from outside: GNOME closed off Eval in
        # 41 and offers no portal for it, so an extension is the only route.
        return _check(
            "window_watcher", "Focused-app detection", False,
            "GNOME does not let an application ask which window has focus, so "
            "dynamic mode needs an extension to expose it. Install either "
            "\"Focused Window D-Bus\" or \"Window Calls\" from "
            "extensions.gnome.org, enable it, and use Check again.\n\n"
            "Everything else works; profiles just will not switch by "
            "themselves.",
            "https://extensions.gnome.org/extension/5592/focused-window-d-bus/\n"
            "https://extensions.gnome.org/extension/4724/window-calls/",
            optional=True)
    if session == platform_env.X11:
        return _check(
            "window_watcher", "Focused-app detection", False,
            "Reading the focused window on X11 needs xprop, which usually "
            "comes with the X11 tools.",
            "sudo dnf install xorg-x11-utils        # or your package manager",
            optional=True)
    return _check(
        "window_watcher", "Focused-app detection", False,
        "No way to read the focused window on this desktop, so profiles will "
        "not switch by themselves. Everything else works.", optional=True)


def check_media():
    """Media actions go through playerctl (MPRIS) when it is there."""
    if platform_env.os_name() == platform_env.MACOS:
        return _check("media", "Media keys", True,
                      "macOS handles media keys itself; playerctl is a Linux "
                      "thing and is not needed here.", optional=True)
    if platform_env.has_tool("playerctl"):
        return _check("media", "Media keys", True,
                      "playerctl is installed.", optional=True)
    return _check(
        "media", "Media keys", False,
        "playerctl is not installed. Play/pause and track actions fall back to "
        "media keys, which not every player listens for.",
        "sudo dnf install playerctl        # or your package manager",
        optional=True)


CHECKS = (check_device_library, check_device_permissions, check_input,
          check_window_watcher, check_media)


def run():
    """Every check, in the order the UI should show them.

    A check that raises is reported as a failure rather than taking the dialog
    down with it: this runs at startup, and setup advice is the last thing that
    should be able to stop the app opening.
    """
    results = []
    for fn in CHECKS:
        try:
            results.append(fn())
        except Exception as e:
            results.append(_check(
                getattr(fn, "__name__", "check"), "Check failed", False,
                "%s: %s" % (type(e).__name__, e), optional=True))
    return results


def summary(results=None):
    """(all_ok, problems, optional_problems) for the top bar."""
    results = run() if results is None else results
    problems = [r for r in results if not r["ok"] and not r["optional"]]
    optional = [r for r in results if not r["ok"] and r["optional"]]
    return (not problems and not optional), problems, optional
