"""Reading the applications a machine has installed.

This feeds the app picker, and the match key is the part that matters: an
entry offering the wrong window class produces an app that never switches, and
the user has no way to tell why.
"""
import os
import sys
import tempfile

from _harness import Checks

tmp = tempfile.mkdtemp()
os.environ["LOUPEDECKAPP_CONFIG_DIR"] = os.path.join(tmp, "config")

import installed_apps                                             # noqa: E402
import platform_env                                               # noqa: E402

c = Checks()

# -- parsing a desktop entry -------------------------------------------------
ENTRY = """[Desktop Entry]
Name=Visual Studio Code
Name[de]=Visual Studio Code auf Deutsch
Comment=Code Editing. Redefined.
Exec=/usr/share/code/code %F
Icon=vscode
Type=Application
StartupWMClass=Code

[Desktop Action new-empty-window]
Name=New Empty Window
Exec=/usr/share/code/code --new-window %F
"""

fields = installed_apps.parse_desktop_entry(ENTRY)
c.eq("the main group is read", fields.get("Name"), "Visual Studio Code")
c.eq("a translation does not overwrite the untranslated key",
     fields.get("Name"), "Visual Studio Code")
c.eq("the window class is read", fields.get("StartupWMClass"), "Code")
c.eq("an action group is not mixed in",
     "--new-window" in fields.get("Exec", ""), False)

# -- deriving a match from Exec ----------------------------------------------
cases = [
    ("/usr/share/code/code %F", "code"),
    ("firefox %u", "firefox"),
    ("env GDK_BACKEND=x11 /usr/bin/inkscape %F", "inkscape"),
    ("/usr/bin/flatpak run --branch=stable org.gimp.GIMP", "org.gimp.GIMP"),
    ("", ""),
]
for exec_line, want in cases:
    c.eq("Exec %-46r -> %s" % (exec_line[:46], want or "(nothing)"),
         installed_apps._exec_binary(exec_line), want)

# -- a directory of entries ---------------------------------------------------
apps_dir = os.path.join(tmp, "applications")
os.makedirs(apps_dir)


def entry(filename, body):
    with open(os.path.join(apps_dir, filename), "w") as f:
        f.write(body)


entry("code.desktop", ENTRY)
entry("firefox.desktop", "[Desktop Entry]\nName=Firefox\nExec=firefox %u\n"
                         "Type=Application\n")
entry("hidden.desktop", "[Desktop Entry]\nName=Secret\nExec=secret\n"
                        "Type=Application\nNoDisplay=true\n")
entry("also-hidden.desktop", "[Desktop Entry]\nName=Gone\nExec=gone\n"
                             "Type=Application\nHidden=true\n")
entry("link.desktop", "[Desktop Entry]\nName=A link\nType=Link\nURL=http://x\n")
entry("noname.desktop", "[Desktop Entry]\nExec=nameless\nType=Application\n")
entry("nomatch.desktop", "[Desktop Entry]\nName=No exec\nType=Application\n")
entry("code-url-handler.desktop",
      "[Desktop Entry]\nName=Visual Studio Code URL Handler\n"
      "Exec=/usr/share/code/code --open-url\nType=Application\n")

real_dirs = installed_apps.LINUX_DIRS
real_os = platform_env.os_name
saved_xdg = os.environ.get("XDG_DATA_DIRS")
os.environ.pop("XDG_DATA_DIRS", None)
platform_env.os_name = lambda: platform_env.LINUX
installed_apps.LINUX_DIRS = [apps_dir]
try:
    found = installed_apps.list_installed()
    names = [a["name"] for a in found]
    c.eq("only launchable, visible applications are offered",
         names, ["Firefox", "Visual Studio Code"])
    c.eq("and they come back sorted by name", names, sorted(names))

    by_name = {a["name"]: a for a in found}
    c.eq("StartupWMClass is preferred when the entry has one",
         by_name["Visual Studio Code"]["match"], "Code")
    c.eq("otherwise the executable's name is used",
         by_name["Firefox"]["match"], "firefox")
    c.eq("each entry says where it came from",
         by_name["Firefox"]["source"].endswith("firefox.desktop"), True)

    # A URL handler is an entry for a file type, not an application to add.
    c.eq("url handlers are not offered",
         any("URL Handler" in n for n in names), False)

    # -- search ---------------------------------------------------------------
    c.eq("search matches the name",
         [a["name"] for a in installed_apps.search("fire", found)], ["Firefox"])
    c.eq("and the window class, which is what you may know it by",
         [a["name"] for a in installed_apps.search("Code", found)],
         ["Visual Studio Code"])
    c.eq("case does not matter",
         len(installed_apps.search("FIREFOX", found)), 1)
    c.eq("an empty query is everything", len(installed_apps.search("", found)), 2)
    c.eq("a query matching nothing returns nothing",
         installed_apps.search("zzz", found), [])

    # A directory that is not there is normal, not an error: most machines
    # have only some of the locations this looks in.
    installed_apps.LINUX_DIRS = [os.path.join(tmp, "nope")]
    c.eq("a missing directory is skipped quietly",
         installed_apps.list_installed(), [])

    # The picker must never take the dialog down with it.
    installed_apps.LINUX_DIRS = [apps_dir]
    real_parse = installed_apps.parse_desktop_entry

    def explode(_text):
        raise RuntimeError("bad entry")

    installed_apps.parse_desktop_entry = explode
    try:
        c.eq("a parser that raises gives an empty list, not a traceback",
             installed_apps.list_installed(), [])
    finally:
        installed_apps.parse_desktop_entry = real_parse

    # -- an unsupported platform ---------------------------------------------
    platform_env.os_name = lambda: platform_env.OTHER
    c.eq("a platform with no implementation offers nothing",
         installed_apps.list_installed(), [])
finally:
    installed_apps.LINUX_DIRS = real_dirs
    platform_env.os_name = real_os
    if saved_xdg is not None:
        os.environ["XDG_DATA_DIRS"] = saved_xdg

# -- macOS bundles ------------------------------------------------------------
import plistlib                                                   # noqa: E402

mac_dir = os.path.join(tmp, "Applications")
os.makedirs(os.path.join(mac_dir, "Safari.app", "Contents"))
with open(os.path.join(mac_dir, "Safari.app", "Contents", "Info.plist"), "wb") as f:
    plistlib.dump({"CFBundleIdentifier": "com.apple.Safari",
                   "CFBundleName": "Safari"}, f)
# A bundle whose plist cannot be read is still an application the user sees.
os.makedirs(os.path.join(mac_dir, "Broken.app", "Contents"))
with open(os.path.join(mac_dir, "Broken.app", "Contents", "Info.plist"), "w") as f:
    f.write("not a plist")

real_mac_dirs = installed_apps.MAC_DIRS
platform_env.os_name = lambda: platform_env.MACOS
installed_apps.MAC_DIRS = [mac_dir]
try:
    found = installed_apps.list_installed()
    by_name = {a["name"]: a for a in found}
    c.eq("bundles are found", sorted(by_name), ["Broken", "Safari"])
    c.eq("the bundle id is the match, which is what the watcher reports",
         by_name["Safari"]["match"], "com.apple.Safari")
    c.eq("an unreadable plist falls back to the bundle's own name",
         by_name["Broken"]["match"], "Broken")
finally:
    installed_apps.MAC_DIRS = real_mac_dirs
    platform_env.os_name = real_os

sys.exit(c.done())
