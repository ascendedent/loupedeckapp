"""test_port_convert on a machine without Mono: the porting tools and
stand-ins built with the .NET SDK (dotnet/core/Linux.slnx), and plugins run
on the .NET 10 host. LOUPEDECKAPP_NO_MONO makes this machine one without
Mono for the length of the run. Skipped where the .NET SDK is not here."""
import os
import runpy
import shutil
import sys

if not shutil.which("dotnet"):
    print("%-58s %s" % ("converting without Mono (no .NET SDK)", "skipped"))
    print("\n0 checks failed")
    raise SystemExit(0)

os.environ["LOUPEDECKAPP_NO_MONO"] = "1"
sys.argv = [os.path.join(os.path.dirname(__file__), "test_port_convert.py")]
runpy.run_path(sys.argv[0], run_name="__main__")
