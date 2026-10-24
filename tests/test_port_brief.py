"""The brief for what no conversion rule covers (plugin_port.brief).

A plugin that runs PowerShell (which no rule covers) is installed and
converted; its brief names what is left and the house rules. Nothing is run.
Skipped where Mono is not installed.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

from _harness import Checks

tmp = tempfile.mkdtemp()
os.environ["LOUPEDECKAPP_CONFIG_DIR"] = os.path.join(tmp, "config")
os.environ["XDG_CACHE_HOME"] = os.path.join(tmp, "cache")

import plugin_host as ph                                          # noqa: E402
import plugin_port as pp                                          # noqa: E402

c = Checks()

if not (shutil.which("mono") and shutil.which("mcs")):
    print("%-58s %s" % ("a brief for Claude Code (Mono is not installed)", "skipped"))
    raise SystemExit(c.done())

# -- a plugin with something no rule covers -----------------------------------------
src = os.path.join(tmp, "Shell.cs")
dll = os.path.join(tmp, "ShellPlugin.dll")
with open(src, "w") as f:
    f.write('namespace S { public class C { public void Run() { '
            'System.Diagnostics.Process.Start("powershell.exe", "-Command Set-Volume"); } } }')
subprocess.run(["mcs", "-nologo", "-target:library", "-out:" + dll, src], check=True)
package = os.path.join(tmp, "Shell.lplug4")
with zipfile.ZipFile(package, "w") as zf:
    zf.writestr("metadata/LoupedeckPackage.yaml",
                "type: plugin4\nname: Shell\nversion: 1.0\npluginFileName: ShellPlugin.dll\npluginFolderWin: win\n")
    zf.write(dll, "win/ShellPlugin.dll")
c.eq("it installs", ph.install(package), ("Shell", ""))
c.eq("with PowerShell left over", (pp.conversion("Shell") or {}).get("remaining"), ["shell: powershell.exe"])

text, error = pp.brief("Shell")
c.eq("it has a brief", (error, bool(text)), ("", True))
c.eq("naming what is left", "powershell.exe" in text, True)
c.eq("and where the plugin is", os.path.join(ph.plugins_dir(), "Shell") in text, True)
c.eq("and the house rules", ("CLAUDE.md" in text, "no AI is credited" in text), (True, True))
c.eq("a plugin with nothing left has none", "nothing left" in pp.brief("Nope")[1], True)
out = subprocess.run([sys.executable, "plugin_port.py", "brief", "Shell"], capture_output=True, text=True,
                     cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
c.eq("the command prints it", (out.returncode, out.stdout.strip() == text.strip()), (0, True))

shutil.rmtree(tmp, ignore_errors=True)
raise SystemExit(c.done())
