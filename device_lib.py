"""Access to the devleaks device library, which may not be installed.

`python-loupedeck-live` is not on PyPI, so `pip install loupedeckapp` on its own
leaves it out and the app died with a ModuleNotFoundError before its window ever
appeared. Everything except talking to the hardware still works without it, so
this reports the absence rather than raising, and both modules that touch the
library import through here.

Qt-free, like everything else below the UI.
"""

INSTALL_HINT = (
    "pip install 'loupedeckapp[device]'\n"
    "or: pip install "
    "git+https://github.com/devleaks/python-loupedeck-live.git")

try:
    import importlib

    from Loupedeck import DeviceManager
    from Loupedeck.Devices import LoupedeckLive
    from Loupedeck.Devices.LoupedeckLive import CALLBACK_KEYWORD as CBC
    # BUTTONS / DISPLAYS are module-level globals in this submodule, and the
    # package binds the *class* of the same name, so ct_support needs the module
    # object rather than the attribute.
    module = importlib.import_module("Loupedeck.Devices.LoupedeckLive")
    IMPORT_ERROR = None
except ImportError as e:
    DeviceManager = None
    LoupedeckLive = None
    CBC = None
    module = None
    IMPORT_ERROR = str(e)


def available():
    return DeviceManager is not None


def health():
    """(ok, detail). Detail is what to do about it, not just what is wrong."""
    if available():
        return True, ""
    return False, ("The Loupedeck device library is not installed, so no device "
                   "can be found. Everything else works; profiles you edit are "
                   "saved and will be applied once it is there.\n\n"
                   "Install it with:\n%s" % INSTALL_HINT)
