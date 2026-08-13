"""What a wheel would actually contain.

The flat module layout means `py-modules` in pyproject.toml is a hand-kept
list, and a module missing from it does not fail the build. It fails at first
import, on someone else's machine: the first wheel shipped no assets at all for
the same reason. These checks compare the manifest against what the app really
imports.
"""
import ast
import os
import sys
import tomllib

from _harness import Checks

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

c = Checks()

with open(os.path.join(REPO, "pyproject.toml"), "rb") as f:
    proj = tomllib.load(f)

listed = set(proj["tool"]["setuptools"]["py-modules"])
data_files = proj["tool"]["setuptools"]["data-files"]

# Every local module reachable from the entry point, found by walking imports
# rather than by listing the directory: scratch files and tests do not ship.
local = {os.path.splitext(f)[0] for f in os.listdir(REPO) if f.endswith(".py")}


def imports_of(module):
    path = os.path.join(REPO, module + ".py")
    tree = ast.parse(open(path).read())
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.add(node.module.split(".")[0])
    return found & local


reachable, queue = set(), ["qml_app"]
while queue:
    mod = queue.pop()
    if mod in reachable:
        continue
    reachable.add(mod)
    queue.extend(imports_of(mod))

missing = sorted(reachable - listed)
c.eq("every module the app imports is in py-modules", missing, [])

stale = sorted(listed - local)
c.eq("py-modules lists nothing that does not exist", stale, [])

c.eq("the entry point module is packaged", "qml_app" in listed, True)

# -- assets ------------------------------------------------------------------
qml_target = data_files.get("share/loupedeckapp/qml", [])
c.eq("the QML ships", any("qml/" in p for p in qml_target), True)
c.eq("the desktop entry ships",
     "share/applications" in data_files, True)
c.eq("an icon ships, so the desktop entry's Icon= resolves",
     any("icons" in k for k in data_files), True)

# Every shipped asset must be a tracked file. Globbing here once put a
# developer's local profiles into the wheel, including one pointing at an image
# outside the repo: what ships has to be what is committed, not what happens to
# be in the working directory.
import subprocess                                                 # noqa: E402

tracked = set(subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True,
                             text=True).stdout.split())
shipped = [p for paths in data_files.values() for p in paths]
c.eq("nothing is shipped by glob", [p for p in shipped if "*" in p], [])
c.eq("every shipped file exists",
     [p for p in shipped if not os.path.exists(os.path.join(REPO, p))], [])
c.eq("and every one of them is committed",
     sorted(p for p in shipped if p not in tracked), [])

# The QML is loaded by name at runtime, so a new file that is not listed fails
# only when something imports it.
qml_on_disk = {os.path.join("qml", f) for f in os.listdir(os.path.join(REPO, "qml"))
               if f.endswith(".qml")}
c.eq("every QML file ships", sorted(qml_on_disk - set(shipped)), [])

# The desktop entry names an icon and a command; both have to exist for an
# install to be more than a checkout with a menu item.
entry = {}
for line in open(os.path.join(REPO, "packaging", "loupedeckapp.desktop")):
    if "=" in line and not line.startswith("["):
        k, v = line.split("=", 1)
        entry[k.strip()] = v.strip()

c.eq("the desktop entry runs the console script",
     entry.get("Exec"), "loupedeckapp")
c.eq("and the entry point exists in pyproject",
     proj["project"]["gui-scripts"]["loupedeckapp"], "qml_app:main")
c.eq("the icon it names is the one that ships",
     entry.get("Icon") + ".svg",
     os.path.basename(data_files["share/icons/hicolor/scalable/apps"][0]))

# The tray icon is found by file path from a checkout and by theme name once
# installed, because the icon ships into hicolor rather than beside the code.
import tray                                                       # noqa: E402

c.eq("the icon tray.py looks for exists in a checkout",
     os.path.exists(os.path.join(REPO, "packaging", "icons", "loupedeckapp.svg")),
     True)
c.eq("and the themed name it falls back to matches the installed file",
     "loupedeckapp.svg",
     os.path.basename(data_files["share/icons/hicolor/scalable/apps"][0]))
c.eq("asking whether a tray exists never raises",
     isinstance(tray.available(), bool), True)

sys.exit(c.done())
