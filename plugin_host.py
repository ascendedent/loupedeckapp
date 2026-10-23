"""Runs Loupedeck plugins written for Logitech's Node.js SDK.

A `.lplug4` file is a zip: icons, `metadata/LoupedeckPackage.yaml`, and the
plugin's code. Plugins built with `@logitech/plugin-sdk` say
`pluginRuntime: nodejs` there and ship one bundled `.mjs` entry point. Those
are the ones this can run. The older kind are .NET assemblies compiled against
Logitech's own PluginApi.dll, which does not ship with the plugin, so they are
refused at install with a message saying so rather than failing later.

The protocol is the SDK's, read out of its bundled source. The host starts
`node <entryPoint>` with four environment variables:

    LPS_SERVER_URL                     ws:// address to connect to
    LPS_SESSION_TOKEN                  proves which process this is
    LPS_PLUGIN_NAME                    the package's `name`
    LPS_PLUGIN_PACKAGE_DIRECTORY_PATH  where the package was unpacked

and the plugin connects as a WebSocket client. Every message is a JSON object
with `id`, `name` and `messageType` (Request, Response or Event); requests and
events carry `parameters`, responses carry `data`, `failed`, `errorCode` and
`errorMessage`. The plugin opens with an InitConnection request. After that
the host asks:

    GetActionList      -> {commands: [...], adjustments: [...]}
    ExecuteCommand     {pluginName, actionName}            a key press
    ExecuteAdjustment  {pluginName, actionName, clicks}    a dial turn, signed
    GetActionText      {pluginName, actionName} -> {text}
    GetActionImage     {pluginName, actionName} -> image, or null
    StopPlugin         (event) the plugin disconnects

Each action is {name, actionType, displayName, description, groupName}.

Live text: the SDK reads an action's `displayName` when asked for its text,
and a plugin may change it at any time, so the host asks every second about
the actions on the page being shown, and after each press, and a changed
answer redraws the controls bound to it.
Images: the SDK answers GetActionImage with null today; the host asks anyway
and uses an answer if one comes (see _decode_image). Until then a control
shows the package's own icon, `actionicons/<action>.svg`, rendered once.

The WebSocket side is written here rather than pulled in as a dependency: the
server end of RFC 6455 for one local client per plugin is a page of code, and
the app has kept its dependency list to what it cannot do without.

On a control, a plugin action is stored as an ordinary string, so profiles
need no schema change: `Plugin/action` for a command, and `Plugin/action:+` or
`Plugin/action:-` for an adjustment turned right or left.

Qt-free.
"""

import base64
import hashlib
import io
import json
import os
import posixpath
import re
import secrets
import shutil
import socket
import struct
import subprocess
import tempfile
import threading
import time
import zipfile

from PIL import Image

import app_paths

METADATA = "metadata/LoupedeckPackage.yaml"
# Older packages keep it at the top instead.
METADATA_TOP = "LoupedeckPackage.yaml"
SUFFIX = ".lplug4"

# Package names become directory names, so they are held to a safe set.
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")

# A plugin's JSON messages are small. Anything this large is not one.
MAX_MESSAGE = 16 * 1024 * 1024

# How long a plugin gets to leave on its own before it is made to.
STOP_GRACE_S = 1.5


# -- packages ------------------------------------------------------------------
def plugins_dir():
    return os.path.join(app_paths.user_dir(), "Plugins")


def parse_metadata(text):
    """The top-level `key: value` pairs of LoupedeckPackage.yaml.

    Not a YAML parser: the fields that matter here are flat scalars, and the
    nested ones (pluginCapabilities and the like) are skipped. Quotes around a
    value are removed; comments and blank lines are ignored.
    """
    out = {}
    for raw in str(text or "").splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if raw[0] in " \t-":
            continue        # nested under the previous key
        key, sep, value = raw.partition(":")
        if not sep:
            continue
        value = value.strip()
        if " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        out[key.strip()] = value
    return out


def inspect_package(path):
    """(metadata, error) for a .lplug4 file, without unpacking it."""
    try:
        zf = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as e:
        return None, "%s is not a Loupedeck plugin package (%s)" % (
            os.path.basename(path), e)
    with zf:
        members = _members(zf)
        info = members.get(METADATA) or members.get(METADATA_TOP)
        if info is None:
            return None, "%s has no %s, so it is not a Loupedeck plugin" % (
                os.path.basename(path), METADATA)
        meta = parse_metadata(zf.read(info).decode("utf-8", "replace"))
        names = set(members)
    name = meta.get("name", "")
    if not _NAME_RE.match(name):
        return None, "the package's name %r is not one that can be installed" % name
    entry = package_entry(meta, names)
    if not entry:
        if runtime_of(meta) == "dotnet":
            return None, "%s names %r, which is not in the package" % (
                name, meta.get("pluginFileName", ""))
        return None, "%s names entry point %r, which is not in the package" % (
            name, meta.get("entryPoint", ""))
    return meta, ""


def runtime_of(meta):
    """"nodejs" or "dotnet". A .NET package names its assembly in
    pluginFileName and says no runtime at all."""
    if meta.get("pluginRuntime", "").lower() == "nodejs":
        return "nodejs"
    return "dotnet" if meta.get("pluginFileName") else ""


# Which build of a .NET plugin to run, in order. The macOS folder holds the
# cross-platform build (the official service on macOS runs it on Mono); the
# Windows one is the fallback, and for many plugins is the same files.
_DOTNET_FOLDERS = ("pluginFolderLinux", "pluginFolderMac", "pluginFolderWin")


def package_entry(meta, names):
    """The file that starts the plugin, as a path inside the package, or ""."""
    runtime = runtime_of(meta)
    if runtime == "nodejs":
        entry = meta.get("entryPoint", "")
        return entry if entry in names else ""
    if runtime == "dotnet":
        dll = meta.get("pluginFileName", "")
        for key in _DOTNET_FOLDERS:
            # Written every way: "bin", "./bin/win/", ".\bin\win", ".".
            folder = meta.get(key, "").strip().replace("\\", "/")
            folder = posixpath.normpath(folder).strip("/") if folder else ""
            if folder and folder != "." and "%s/%s" % (folder, dll) in names:
                return "%s/%s" % (folder, dll)
        return dll if dll in names else ""
    return ""


def windows_only(meta):
    """Whether a .NET package ships a Windows build and nothing else. Most
    such plugins call into Windows itself (audio, windows, COM) and cannot
    work here, though some are only packaged that way."""
    return (runtime_of(meta) == "dotnet" and bool(meta.get("pluginFolderWin"))
            and not meta.get("pluginFolderMac") and not meta.get("pluginFolderLinux"))


def _member_name(info):
    """A member's path with "/" between folders. Packages zipped on Windows
    write "bin\\win\\Plugin.dll", which unpacked as it is would be one file
    with backslashes in its name."""
    return info.filename.replace("\\", "/")


def _members(zf):
    """{path: ZipInfo}, paths as _member_name gives them."""
    return {_member_name(i): i for i in zf.infolist()}


def extract(zf, dest):
    """Unpack a package into dest, every path made to stay inside it (a zip
    can name ../../anything) and written with "/" whichever way it was
    zipped. Raises ValueError for a path that points outside."""
    root = os.path.realpath(dest)
    for name, info in _members(zf).items():
        target = os.path.realpath(os.path.join(root, name))
        if target != root and not target.startswith(root + os.sep):
            raise ValueError("%r points outside the package" % info.filename)
        if name.endswith("/"):
            os.makedirs(target, exist_ok=True)
            continue
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with zf.open(info) as src, open(target, "wb") as out:
            shutil.copyfileobj(src, out)


def metadata_path(folder):
    """The metadata file of an unpacked package, wherever it keeps it."""
    path = os.path.join(folder, METADATA)
    return path if os.path.isfile(path) else os.path.join(folder, METADATA_TOP)


def install(path):
    """Unpack a .lplug4 into the plugins folder. (name, error).

    Installing a plugin that is already there replaces it, which is how an
    update is installed. The new copy is unpacked beside the old one and
    swapped in, so a broken package never leaves half a plugin behind.
    """
    meta, error = inspect_package(path)
    if error:
        return "", error
    name = meta["name"]
    base = plugins_dir()
    os.makedirs(base, exist_ok=True)
    staging = tempfile.mkdtemp(prefix=".install-", dir=base)
    try:
        with zipfile.ZipFile(path) as zf:
            extract(zf, staging)
        dest = os.path.join(base, name)
        if os.path.isdir(dest):
            shutil.rmtree(dest)
        os.rename(staging, dest)
    except (OSError, ValueError, zipfile.BadZipFile) as e:
        shutil.rmtree(staging, ignore_errors=True)
        return "", "could not install %s: %s" % (name, e)
    if runtime_of(meta) == "dotnet":
        # Windows and macOS plugins: what has a Linux stand-in is converted
        # now (plugin_port.py), and recorded beside the plugin. A conversion
        # that fails leaves the plugin as it came, installed.
        try:
            import plugin_port
            plugin_port.convert_installed(name)
        except Exception as e:                       # noqa: BLE001
            print("plugin %s: not converted: %s" % (name, e))
    return name, ""


def uninstall(name):
    """Remove an installed plugin. Returns an error string, or ""."""
    if not _NAME_RE.match(name or ""):
        return "no plugin called %r" % name
    dest = os.path.join(plugins_dir(), name)
    if not os.path.isdir(dest):
        return "no plugin called %r" % name
    shutil.rmtree(dest, ignore_errors=True)
    shutil.rmtree(data_dir(name), ignore_errors=True)
    try:
        os.remove(log_path(name))
    except OSError:
        pass
    return ""


def log_path(name):
    """Where a plugin's console output goes. Beside the plugin, not in it, so
    reinstalling does not throw away the log of what went wrong."""
    return os.path.join(plugins_dir(), name + ".log")


def installed():
    """Installed plugins as dicts: name, displayName, version, dir, entry."""
    base = plugins_dir()
    out = []
    try:
        entries = sorted(os.listdir(base))
    except OSError:
        return out
    for name in entries:
        d = os.path.join(base, name)
        if name.startswith(".") or not os.path.isdir(d):
            continue
        try:
            with open(metadata_path(d), encoding="utf-8") as f:
                meta = parse_metadata(f.read())
        except OSError:
            continue
        files = set()
        for root, _dirs, fnames in os.walk(d):
            rel = os.path.relpath(root, d)
            for f in fnames:
                files.add(f if rel == "." else "%s/%s" % (rel.replace(os.sep, "/"), f))
        entry = package_entry(meta, files)
        out.append({
            "name": name,
            "displayName": meta.get("displayName") or name,
            "version": meta.get("version", ""),
            "description": meta.get("description", ""),
            "runtime": runtime_of(meta),
            "windowsOnly": windows_only(meta),
            "dir": d,
            "entry": os.path.join(d, entry) if entry else "",
        })
    return out


# Beside the code in a checkout, under share/loupedeckapp once installed.
_DOTNET = os.path.join(app_paths.BUNDLED_DIR, "dotnet")


def _build_module():
    """dotnet/build.py, loaded as a module (it is a script, not a package)."""
    import importlib.util
    script = os.path.join(_DOTNET, "build.py")
    if not os.path.isfile(script):
        return None
    spec = importlib.util.spec_from_file_location("_dotnet_build", script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def dotnet_host():
    """(path to the Mono LoupedeckHost.exe, error), building it first if its
    sources changed."""
    mod = _build_module()
    if mod is None:
        return "", "the .NET plugin host is not part of this installation"
    error = mod.build_mono()
    if error:
        return "", error
    return os.path.join(mod.BIN, "LoupedeckHost.exe"), ""


def dotnet_core_host():
    """(path to the .NET 10 LoupedeckHost.dll, error), building it first if
    its sources changed."""
    mod = _build_module()
    if mod is None:
        return "", "the .NET plugin host is not part of this installation"
    error = mod.build_core()
    if error:
        return "", error
    return mod.CORE_HOST, ""


def target_framework(dll_path):
    """"core" for a plugin built for .NET (Core) 5 and later, "framework"
    for .NET Framework, "" if it does not say. Read from the assembly's
    TargetFramework attribute, which is stored as plain text."""
    try:
        with open(dll_path, "rb") as f:
            data = f.read()
    except OSError:
        return ""
    if b".NETCoreApp,Version=" in data:
        return "core"
    if b".NETFramework,Version=" in data:
        return "framework"
    return ""


def missing_api(dll_path):
    """What a .NET plugin uses from Logitech's PluginApi that ours does not
    provide yet, as "Type::Member(...)" lines; [] when nothing is missing, or
    None when the check could not run. dotnet/tools/ApiScan.cs does the
    reading, from metadata alone: nothing of the plugin is executed."""
    host, error = dotnet_host()
    mono = shutil.which("mono")
    if error or not mono:
        return None
    bin_dir = os.path.dirname(host)
    scan = os.path.join(bin_dir, "ApiScan.exe")
    if not os.path.isfile(scan):
        return None
    env = dict(os.environ, MONO_PATH=bin_dir)
    try:
        out = subprocess.run([mono, scan, dll_path, os.path.join(bin_dir, "PluginApi.dll")],
                             capture_output=True, text=True, timeout=60, env=env)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    return [line[2:].strip() for line in out.stdout.splitlines() if line.startswith("! ")]


# -- loupedeck: links -----------------------------------------------------------
# A plugin that signs in through the browser sends it to a page that redirects
# to loupedeck:plugin/<Name>/callback/..., which the official service catches.
# Here the desktop hands such links to `plugin_host.py url <link>` (registered
# below), which passes them to the running app over a local socket.
URL_SCHEME = "loupedeck"
URL_HANDLER_DESKTOP = "loupedeckapp-url.desktop"


def url_socket_path():
    base = os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir()
    return os.path.join(base, "loupedeckapp-%d.sock" % os.getuid())


def send_url(url, timeout=5.0):
    """Hand a loupedeck: link to the running app. Returns an error, or ""."""
    path = url_socket_path()
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect(path)
            s.sendall(url.strip().encode("utf-8") + b"\n")
            return s.recv(1024).decode("utf-8", "replace").strip()
    except OSError as e:
        return "the app is not running (%s)" % e


def parse_link(url):
    """("plugin name", "rest") from loupedeck:plugin/<Name>/<rest>, either
    spelling (loupedeck:plugin/... or loupedeck://plugin/...)."""
    rest = str(url or "")
    if not rest.lower().startswith(URL_SCHEME + ":"):
        return "", ""
    rest = rest[len(URL_SCHEME) + 1:].lstrip("/")
    head, _, rest = rest.partition("/")
    if head.lower() != "plugin":
        return "", ""
    name, _, rest = rest.partition("/")
    return name, rest


def uses_url_callbacks(dll_path):
    """Whether a .NET plugin listens for loupedeck: links (it subscribes to
    ServiceEvents.UrlCallbackReceived). Read from its metadata's names."""
    try:
        with open(dll_path, "rb") as f:
            return b"add_UrlCallbackReceived" in f.read()
    except OSError:
        return False


def register_url_handler():
    """Make loupedeck: links open here: a .desktop entry that forwards them,
    set as the handler with xdg-mime. Idempotent; returns an error or ""."""
    apps = os.path.join(os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share"),
                        "applications")
    try:
        os.makedirs(apps, exist_ok=True)
        desktop = os.path.join(apps, URL_HANDLER_DESKTOP)
        import sys
        entry = ("[Desktop Entry]\nType=Application\nName=Loupedeck plugin sign-in\n"
                 "Comment=Passes loupedeck: links to Loupedeck plugins running in loupedeckapp\n"
                 "Exec=%s %s url %%u\nNoDisplay=true\nTerminal=false\n"
                 "MimeType=x-scheme-handler/%s;\n" % (
                     sys.executable, os.path.abspath(__file__), URL_SCHEME))
        current = ""
        if os.path.isfile(desktop):
            with open(desktop, encoding="utf-8") as f:
                current = f.read()
        if current != entry:
            with open(desktop, "w", encoding="utf-8") as f:
                f.write(entry)
        xdg = shutil.which("xdg-mime")
        if not xdg:
            return "xdg-mime is not installed, so loupedeck: links cannot be registered"
        subprocess.run([xdg, "default", URL_HANDLER_DESKTOP, "x-scheme-handler/" + URL_SCHEME],
                       capture_output=True, timeout=30)
        return ""
    except (OSError, subprocess.TimeoutExpired) as e:
        return "could not register loupedeck: links: %s" % e


def data_dir(name):
    """Where a plugin keeps its settings and sign-ins: beside it, not in it,
    so an update does not sign you out."""
    return os.path.join(plugins_dir(), name + ".data")


# -- action values -------------------------------------------------------------
def make_value(plugin, action, direction=""):
    """The string stored on a control. `direction` is "+" or "-" for an
    adjustment, "" for a command."""
    value = "%s/%s" % (plugin, action)
    return value + ":" + direction if direction else value


def parse_value(value):
    """(plugin, action, direction) from a stored value. direction is "+", "-"
    or "" (a command)."""
    plugin, _, rest = str(value or "").partition("/")
    action, direction = rest, ""
    head, sep, tail = rest.rpartition(":")
    if sep and tail in ("+", "-"):
        action, direction = head, tail
    return plugin, action, direction


def editor_values(rest):
    """The values of an action editor binding, from the text after "|"."""
    if not rest:
        return {}
    try:
        values = json.loads(rest)
    except ValueError:
        return {}
    return {str(k): ("" if v is None else str(v)) for k, v in values.items()} \
        if isinstance(values, dict) else {}


def with_values(value, values):
    """A binding with these per-binding values: a dict for an action editor,
    a string for a profile action (the text typed, the item picked)."""
    plugin, action, direction = parse_value(value)
    base = action.partition("|")[0]
    if isinstance(values, dict):
        rest = json.dumps({k: v for k, v in values.items() if v not in (None, "")},
                          separators=(",", ":"), sort_keys=True)
    else:
        rest = str(values or "")
    action = base + "|" + rest if rest and rest != "{}" else base
    return make_value(plugin, action, direction)


# -- the WebSocket end ---------------------------------------------------------
_WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


class _Connection:
    """One plugin's socket, after the handshake. Sends are locked because they
    come from the device thread and the host's own threads alike."""

    def __init__(self, sock):
        self.sock = sock
        self._send_lock = threading.Lock()
        self.closed = False

    def _recv_exact(self, n):
        buf = b""
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("closed")
            buf += chunk
        return buf

    def _send_frame(self, opcode, payload=b""):
        n = len(payload)
        if n < 126:
            header = struct.pack("!BB", 0x80 | opcode, n)
        elif n < 1 << 16:
            header = struct.pack("!BBH", 0x80 | opcode, 126, n)
        else:
            header = struct.pack("!BBQ", 0x80 | opcode, 127, n)
        with self._send_lock:
            if self.closed:
                raise ConnectionError("closed")
            self.sock.sendall(header + payload)

    def send_json(self, obj):
        self._send_frame(0x1, json.dumps(obj).encode("utf-8"))

    def messages(self):
        """Yield each text message until the socket closes. Answers pings and
        honours a close as it goes."""
        parts, kind = [], None
        while True:
            b0, b1 = self._recv_exact(2)
            fin, opcode = b0 & 0x80, b0 & 0x0F
            length = b1 & 0x7F
            if length == 126:
                length = struct.unpack("!H", self._recv_exact(2))[0]
            elif length == 127:
                length = struct.unpack("!Q", self._recv_exact(8))[0]
            if length > MAX_MESSAGE:
                raise ConnectionError("message too large")
            mask = self._recv_exact(4) if b1 & 0x80 else b""
            payload = self._recv_exact(length) if length else b""
            if mask:
                payload = bytes(c ^ mask[i % 4] for i, c in enumerate(payload))
            if opcode == 0x8:
                try:
                    self._send_frame(0x8, payload[:2])
                except (OSError, ConnectionError):
                    pass
                return
            if opcode == 0x9:
                self._send_frame(0xA, payload)
                continue
            if opcode == 0xA:
                continue
            if opcode in (0x1, 0x2):
                parts, kind = [payload], opcode
            elif opcode == 0x0 and kind is not None:
                parts.append(payload)
                if sum(map(len, parts)) > MAX_MESSAGE:
                    raise ConnectionError("message too large")
            else:
                continue
            if fin:
                data = b"".join(parts)
                parts, kind = [], None
                yield data.decode("utf-8", "replace")

    def close(self):
        try:
            self._send_frame(0x8, struct.pack("!H", 1000))
        except (OSError, ConnectionError):
            pass
        with self._send_lock:
            self.closed = True
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.sock.close()


def _handshake(sock):
    """Read the HTTP upgrade request and accept it. Returns True on success."""
    data = b""
    while b"\r\n\r\n" not in data:
        chunk = sock.recv(4096)
        if not chunk or len(data) > 65536:
            return False
        data += chunk
    lines = data.split(b"\r\n\r\n", 1)[0].decode("latin-1").split("\r\n")
    headers = {}
    for line in lines[1:]:
        k, sep, v = line.partition(":")
        if sep:
            headers[k.strip().lower()] = v.strip()
    key = headers.get("sec-websocket-key")
    if "websocket" not in headers.get("upgrade", "").lower() or not key:
        sock.sendall(b"HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\n\r\n")
        return False
    accept = base64.b64encode(
        hashlib.sha1((key + _WS_GUID).encode("ascii")).digest()).decode("ascii")
    # No extensions are accepted, so the client's offer of compression is
    # declined by omission and every frame arrives plain.
    sock.sendall(("HTTP/1.1 101 Switching Protocols\r\n"
                  "Upgrade: websocket\r\nConnection: Upgrade\r\n"
                  "Sec-WebSocket-Accept: %s\r\n\r\n" % accept).encode("ascii"))
    return True


# -- the host ------------------------------------------------------------------
# How often the actions on the page being shown are asked for their current
# text. The SDK has no message for "my text changed": an action changes its
# displayName and the next GetActionText returns the new one. Asking is a few
# hundred bytes over loopback, and a label that lags by a second is fine. Only
# what is on screen is asked, so a plugin logging every message it gets does
# not fill its log with questions about actions nobody can see.
TEXT_POLL_S = 1.0

# A plugin that exits on its own is started again after 1, 2, 4, 8, 16 s. Five
# exits inside CRASH_WINDOW_S means it is not going to work, and it is left
# down rather than restarted forever.
RESTART_DELAYS_S = (1, 2, 4, 8, 16)
CRASH_WINDOW_S = 120

# A plugin that is running but has not connected after this long is reported,
# since otherwise it would sit at "starting" with no hint why.
CONNECT_TIMEOUT_S = 20

# Rendered icon size: the largest thing a plugin action can be drawn on is the
# CT's 240px wheel screen; keys scale it down.
ICON_PX = 240

# Where a package keeps an action's icon, by the toolkit's convention: one file
# per action, named after the action's `name`. actionicons is the coloured
# icon; actionsymbols the monochrome one, used when there is no icon.
_ICON_DIRS = ("actionicons", "actionsymbols")


class _Plugin:
    def __init__(self, info):
        self.name = info["name"]
        self.display_name = info["displayName"]
        self.version = info["version"]
        self.dir = info["dir"]
        self.entry = info["entry"]
        self.runtime = info.get("runtime") or "nodejs"
        # account sign-ins and the like (.NET plugins), as the host reports them
        self.preferences = []
        self.token = secrets.token_hex(16)
        self.proc = None
        self.conn = None
        self.commands = []
        self.adjustments = []
        # action name -> path of an image the plugin itself supplied, and the
        # bytes it came from, so an unchanged answer is not redrawn
        self.images = {}
        self.image_data = {}
        # starting, running, stopped or failed; `detail` says why
        self.state = "stopped"
        self.detail = ""
        self.stopping = False
        # what the plugin last said about itself (.NET: PluginStatus)
        self.status = ""
        # text for bound names that are not in the action list: a .NET
        # action with per-binding values ("Name|{...}")
        self.texts = {}
        # when it exited on its own, for the restart backoff
        self.crashes = []

    def action(self, name):
        for a in self.commands + self.adjustments:
            if a.get("name") == name:
                return a
        return None

    def cache_dir(self):
        # Inside the plugin's folder, so reinstalling (which can change the
        # icons) throws the old renders away with everything else.
        return os.path.join(self.dir, ".rendered")


def _icon_source(plugin_dir, action):
    """The package's own icon file for an action, or "".

    Named after the action: its `name` for a Node.js plugin, its class's full
    name for a .NET one, where one variant of a command ("Class|param" here)
    is "Class___param", falling back to the class's own icon."""
    cls, bar, param = action.partition("|")
    names = [action] if not bar else [cls + "___" + param, cls]
    for name in names:
        for folder in _ICON_DIRS:
            for ext in (".svg", ".png"):
                path = os.path.join(plugin_dir, folder, name + ext)
                if os.path.isfile(path):
                    return path
    return ""


def _cache_name(action, suffix=".png"):
    """A file name for an action's rendered image. Action names can carry a
    .NET parameter after "|"; keep the file name plain."""
    return re.sub(r"[^A-Za-z0-9_.-]", "_", action.replace("|", "___")) + suffix


def rasterize_svg(svg_path, png_path, px=ICON_PX):
    """Render an SVG to a PNG with Qt, if Qt is there and has an application
    to render text with. Returns True on success.

    Qt is imported here, not at the top: the rest of this module runs without
    it (the terminal installer, the tests' fake host), and Pillow cannot read
    SVG at all. The caller has to be on the Qt main thread.
    """
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QGuiApplication, QImage, QPainter
        from PySide6.QtSvg import QSvgRenderer
    except ImportError:
        return False
    if QGuiApplication.instance() is None:
        return False
    renderer = QSvgRenderer(svg_path)
    if not renderer.isValid():
        return False
    image = QImage(px, px, QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    renderer.render(painter)
    painter.end()
    os.makedirs(os.path.dirname(png_path), exist_ok=True)
    return image.save(png_path, "PNG")


def _decode_image(data):
    """Image bytes from a GetActionImage answer, or None.

    The SDK this was written against always answers null, so the shape of a
    real answer is not known. Accepted: base64 (optionally a data: URL), or an
    object carrying it under image/data/base64. Anything Pillow then cannot
    open is ignored rather than shown broken.
    """
    if isinstance(data, dict):
        data = data.get("image") or data.get("data") or data.get("base64")
    if not isinstance(data, str) or not data:
        return None
    if data.startswith("data:"):
        data = data.partition(",")[2]
    try:
        raw = base64.b64decode(data, validate=False)
    except (ValueError, TypeError):
        return None
    try:
        Image.open(io.BytesIO(raw)).verify()
    except Exception:
        return None
    return raw


class PluginHost:
    """Starts every installed plugin, keeps their connections, and runs their
    actions. `on_change` is called (from a host thread) whenever a plugin's
    state, action list, an action's text or its image changes."""

    def __init__(self, node=None, on_change=None, mono=None, on_folder=None):
        self.node = node if node is not None else shutil.which("node")
        self.mono = mono if mono is not None else shutil.which("mono")
        self.dotnet = shutil.which("dotnet")
        self.on_change = on_change
        # (event, value) when a plugin's folder changes ("changed") or the
        # plugin closes it ("close"); value is the folder's stored value.
        self.on_folder = on_folder
        self._plugins = {}
        self._lock = threading.Lock()
        self._server = None
        self._port = 0
        self._next_id = 0
        # message id -> (plugin name, action name) for requests whose answer
        # does not say which action it is about
        self._pending = {}
        # message id -> [threading.Event, answer] for request()
        self._waiting = {}
        self._poller = None
        self._closing = False
        # stored values of the plugin actions on the page being shown
        self._watched = set()

    # -- lifecycle --
    def start(self):
        """Open the server and launch whatever is installed."""
        infos = installed()
        if not infos:
            return      # no server and no port until there is a plugin
        self._open_server()
        self._open_url_server()
        for info in infos:
            self._launch(info)

    def _open_url_server(self):
        """Listen for loupedeck: links the desktop passes on (send_url)."""
        if getattr(self, "_url_server", None) is not None:
            return
        path = url_socket_path()
        try:
            if os.path.exists(path):
                os.remove(path)
            srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            srv.bind(path)
            os.chmod(path, 0o600)
            srv.listen(4)
        except OSError as e:
            print("loupedeck: links will not reach plugins: %s" % e)
            self._url_server = None
            return
        self._url_server = srv
        threading.Thread(target=self._url_loop, args=(srv,), name="plugin-host-links",
                         daemon=True).start()

    def _url_loop(self, srv):
        while True:
            try:
                conn, _ = srv.accept()
            except OSError:
                return
            with conn:
                try:
                    conn.settimeout(5)
                    data = b""
                    while not data.endswith(b"\n") and len(data) < 65536:
                        chunk = conn.recv(4096)
                        if not chunk:
                            break
                        data += chunk
                    answer = self.deliver_link(data.decode("utf-8", "replace").strip())
                    conn.sendall((answer or "ok").encode("utf-8") + b"\n")
                except OSError:
                    pass

    def deliver_link(self, url):
        """Route a loupedeck:plugin/<Name>/... link. "reload" restarts the
        plugin (the official service's own deep link); anything else goes to
        the plugin as a URL callback. Returns an error, or ""."""
        name, rest = parse_link(url)
        if not name:
            return "not a loupedeck:plugin/ link"
        with self._lock:
            p = next((x for x in self._plugins.values() if x.name.lower() == name.lower()), None)
        if p is None:
            return "no plugin called %s" % name
        if rest.strip("/") == "reload":
            self.reload(p.name)
            return ""
        if p.conn is None:
            return "%s is not running" % p.name
        try:
            p.conn.send_json({"id": self._request("UrlCallback", {})["id"], "name": "UrlCallback",
                              "messageType": "Event", "parameters": {"url": url}})
        except (OSError, ConnectionError) as e:
            return str(e)
        return ""

    def stop(self):
        self._closing = True
        srv = getattr(self, "_url_server", None)
        if srv is not None:
            try:
                srv.close()
            except OSError:
                pass
            self._url_server = None
            try:
                os.remove(url_socket_path())
            except OSError:
                pass
        with self._lock:
            plugins = list(self._plugins.values())
        for p in plugins:
            self._stop_plugin(p)
        if self._server is not None:
            # close() alone does not wake a thread blocked in accept() on
            # Linux; shutdown() does, so the accept thread ends here too.
            try:
                self._server.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                self._server.close()
            except OSError:
                pass
            self._server = None

    def reload(self, name):
        """Restart one plugin from what is on disk now: after an install or an
        update, or to try again after it gave up."""
        self._closing = False
        with self._lock:
            old = self._plugins.pop(name, None)
        if old is not None:
            self._stop_plugin(old)
        for info in installed():
            if info["name"] == name:
                self._open_server()
                self._open_url_server()
                self._launch(info)
                return
        self._changed()

    def remove(self, name):
        """Stop a plugin and forget it (the caller uninstalls the files)."""
        with self._lock:
            old = self._plugins.pop(name, None)
        if old is not None:
            self._stop_plugin(old)
        self._changed()

    # -- what the UI reads --
    def status(self):
        """One dict per known plugin, for the preferences list."""
        with self._lock:
            plugins = sorted(self._plugins.values(), key=lambda p: p.display_name.lower())
        return [{"name": p.name, "displayName": p.display_name,
                 "version": p.version, "state": p.state, "detail": p.detail,
                 "runtime": p.runtime,
                 "actions": len(p.commands) + len(p.adjustments),
                 "accounts": [x for x in p.preferences if x.get("kind") == "account"],
                 "log": log_path(p.name)} for p in plugins]

    def account(self, plugin, name, action):
        """Ask a plugin to sign an account in or out ("login"/"logout"). The
        plugin does the work (usually by opening a browser) and reports back
        through PreferencesChanged."""
        with self._lock:
            p = self._plugins.get(plugin)
        if p is None or p.conn is None:
            return False
        return self._send(p, "PreferenceAction", {"pluginName": plugin, "name": name,
                                                  "action": action})

    def actions(self):
        """Every running plugin's actions as
        (plugin display name, label, value, kind) with kind "command" or
        "adjustment". An adjustment appears twice, once per direction."""
        out = []
        with self._lock:
            plugins = sorted(self._plugins.values(), key=lambda p: p.display_name.lower())
        for p in plugins:
            for a in p.commands:
                out.append((p.display_name, a.get("displayName") or a["name"],
                            make_value(p.name, a["name"]), "command"))
            for a in p.adjustments:
                label = a.get("displayName") or a["name"]
                out.append((p.display_name, label + " ◀",
                            make_value(p.name, a["name"], "-"), "adjustment"))
                out.append((p.display_name, label + " ▶",
                            make_value(p.name, a["name"], "+"), "adjustment"))
                # The knob's press, where the plugin has one (.NET plugins
                # say so; the Node SDK names a reset it never answers).
                if a.get("hasReset") and a.get("resetCommandName"):
                    out.append((p.display_name, label + " reset",
                                make_value(p.name, a["resetCommandName"]), "command"))
        return out

    def label_for(self, value):
        """The action's current display name, for a control's auto-label.
        Falls back to the bare action name while the plugin is not running."""
        plugin, action, _ = parse_value(value)
        with self._lock:
            p = self._plugins.get(plugin)
            a = p.action(action) if p else None
            if a is None and p is not None and action in p.texts:
                return p.texts[action]
            if a is None and p is not None and "|" in action:
                # Bound with values the list does not name; until the plugin
                # answers for this binding, the action's own name.
                a = p.action(action.partition("|")[0])
            if a is None and p is not None and action.endswith("_RESET"):
                base = p.action(action[:-len("_RESET")])
                if base is not None:
                    return (base.get("displayName") or base["name"]) + " reset"
        if a is not None:
            return a.get("displayName") or action
        return action or plugin

    def image_for(self, value):
        """A PNG to draw on a control bound to this action, or "": one the
        plugin supplied, else the package's own icon once rendered."""
        plugin, action, _ = parse_value(value)
        with self._lock:
            p = self._plugins.get(plugin)
        if p is None:
            # Not running (yet): an icon rendered on an earlier run still
            # belongs to this action, so show it rather than a blank key.
            d = os.path.join(plugins_dir(), plugin) if _NAME_RE.match(plugin or "") else ""
            cached = os.path.join(d, ".rendered", _cache_name(action)) if d else ""
            return cached if cached and os.path.isfile(cached) else ""
        supplied = p.images.get(action)
        if supplied and os.path.isfile(supplied):
            return supplied
        src = _icon_source(p.dir, action)
        if src.endswith(".png"):
            return src
        cached = os.path.join(p.cache_dir(), _cache_name(action))
        return cached if os.path.isfile(cached) else ""

    def render_icons(self):
        """Render every running plugin's SVG icons to PNG, once each. Qt does
        the rendering, so this has to be called on the Qt main thread; the app
        does it whenever a plugin reports its actions. Returns True if
        anything new was rendered."""
        with self._lock:
            plugins = list(self._plugins.values())
        rendered = False
        for p in plugins:
            # Images the plugin supplied as SVG, newest first.
            for action, raw in list(p.image_data.items()):
                svg = os.path.join(p.cache_dir(), _cache_name(action, ".supplied.svg"))
                png = os.path.join(p.cache_dir(), _cache_name(action, ".supplied.png"))
                if os.path.isfile(svg) and not os.path.isfile(png) and rasterize_svg(svg, png):
                    p.images[action] = png
                    rendered = True
            for a in p.commands + p.adjustments:
                src = _icon_source(p.dir, a["name"])
                if not src.endswith(".svg"):
                    continue
                out = os.path.join(p.cache_dir(), _cache_name(a["name"]))
                if os.path.isfile(out) and os.path.getmtime(out) >= os.path.getmtime(src):
                    continue
                rendered |= rasterize_svg(src, out)
        return rendered

    def watch(self, values):
        """The plugin actions now on screen, whose text is kept current."""
        with self._lock:
            self._watched = {parse_value(v)[:2] for v in values}

    # -- asking and waiting --
    def request(self, plugin, name, params, timeout=5.0):
        """Send a request and wait for its answer's data, for the editor UI,
        which needs an answer to draw. None if there is none in time."""
        with self._lock:
            p = self._plugins.get(plugin)
        if p is None or p.conn is None:
            return None
        msg = self._request(name, dict(params, pluginName=plugin))
        waiter = [threading.Event(), None]
        with self._lock:
            self._waiting[msg["id"]] = waiter
        try:
            p.conn.send_json(msg)
        except (OSError, ConnectionError):
            with self._lock:
                self._waiting.pop(msg["id"], None)
            return None
        if not waiter[0].wait(timeout):
            with self._lock:
                self._waiting.pop(msg["id"], None)
            return None
        answer = waiter[1] or {}
        return None if answer.get("failed") else answer.get("data")

    # -- folders (.NET PluginDynamicFolder) --
    def is_folder(self, value):
        plugin, action, _ = parse_value(value)
        with self._lock:
            p = self._plugins.get(plugin)
            a = p.action(action) if p else None
        return bool((a or {}).get("folder"))

    def folder_open(self, value):
        """Open a folder: the plugin is told (Activate) and says what goes
        where: {"navigation", "buttons", "rotate", "press"}."""
        plugin, action, _ = parse_value(value)
        return self.request(plugin, "OpenFolder", {"folder": action})

    def folder_layout(self, value):
        plugin, action, _ = parse_value(value)
        return self.request(plugin, "GetFolder", {"folder": action})

    def folder_close(self, value):
        plugin, action, _ = parse_value(value)
        with self._lock:
            p = self._plugins.get(plugin)
        if p is not None:
            self._send(p, "CloseFolder", {"pluginName": plugin, "folder": action})

    def _folder_event(self, kind, p, folder):
        """Off the socket thread: a listener that asks the plugin something
        in return (the new layout) needs this thread free to read the answer."""
        if not (self.on_folder and folder):
            return
        value = make_value(p.name, folder)

        def deliver():
            try:
                self.on_folder(kind, value)
            except Exception as e:
                print("plugin host on_folder failed: %s" % e)
        threading.Thread(target=deliver, name="plugin-folder", daemon=True).start()

    # -- per-binding values (.NET profile actions and action editors) --
    def editor(self, value):
        """The form an action is bound through, as the plugin describes it
        ({"kind": "editor", "controls": [...]} or {"kind": "profile",
        "type": "text"|"list"|"tree", "prompt": ...}), or None."""
        plugin, action, _ = parse_value(value)
        base = action.partition("|")[0]
        with self._lock:
            p = self._plugins.get(plugin)
            a = p.action(base) if p else None
        return (a or {}).get("editor")

    def editor_state(self, value):
        """The editor with what the plugin says now: list items for the
        values so far ("lists"), a profile action's choices ("items")."""
        plugin, action, _ = parse_value(value)
        base, _, rest = action.partition("|")
        kind = (self.editor(value) or {}).get("kind")
        params = {"actionName": base}
        if kind == "editor":
            params["values"] = editor_values(rest)
        return self.request(plugin, "GetEditor", params)

    def editor_changed(self, value, control, values):
        """The user changed one control: the plugin may answer by changing
        others. Returns {"values", "displayName", "enabled"} or None."""
        plugin, action, _ = parse_value(value)
        return self.request(plugin, "EditorValueChanged",
                            {"actionName": action.partition("|")[0],
                             "control": control, "values": values})

    # -- running an action --
    def execute(self, value, repeat=1):
        """Run a stored plugin action. A command runs once however fast the
        knob turned, the way a shell command does; an adjustment sends the
        turn as signed clicks, which is what the SDK hands the plugin."""
        plugin, action, direction = parse_value(value)
        with self._lock:
            p = self._plugins.get(plugin)
        if p is None or p.conn is None or p.state != "running":
            print("plugin %s is not running; %s did nothing" % (plugin or "?", value))
            return False
        if direction:
            clicks = max(1, int(repeat)) * (1 if direction == "+" else -1)
            params = {"pluginName": plugin, "actionName": action, "clicks": clicks}
            name = "ExecuteAdjustment"
        else:
            params = {"pluginName": plugin, "actionName": action}
            name = "ExecuteCommand"
        return self._send(p, name, params, action=action)

    # -- internals --
    def _changed(self):
        if self.on_change:
            try:
                self.on_change()
            except Exception as e:
                print("plugin host on_change failed: %s" % e)

    def _request(self, name, params, plugin=None, action=None):
        with self._lock:
            self._next_id += 1
            mid = self._next_id
            if plugin is not None:
                self._pending[mid] = (plugin, action)
        return {"id": mid, "name": name, "messageType": "Request",
                "parameters": params}

    def _send(self, p, name, params, action=None):
        conn = p.conn
        if conn is None:
            return False
        try:
            conn.send_json(self._request(name, params, p.name, action))
        except (OSError, ConnectionError) as e:
            print("plugin %s: could not send %s: %s" % (p.name, name, e))
            return False
        return True

    def _ask_text(self, p, action):
        self._send(p, "GetActionText",
                   {"pluginName": p.name, "actionName": action}, action=action)

    def _ask_image(self, p, action):
        self._send(p, "GetActionImage",
                   {"pluginName": p.name, "actionName": action}, action=action)

    def _open_server(self):
        if self._server is not None:
            return
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # Loopback only: the session token keeps one plugin from posing as
        # another, but nothing off this machine has any business connecting.
        srv.bind(("127.0.0.1", 0))
        srv.listen(8)
        self._server = srv
        self._port = srv.getsockname()[1]
        threading.Thread(target=self._accept_loop, args=(srv,),
                         name="plugin-host-accept", daemon=True).start()
        if self._poller is None:
            self._poller = threading.Thread(target=self._poll_loop,
                                            name="plugin-host-poll", daemon=True)
            self._poller.start()

    def _accept_loop(self, srv):
        while True:
            try:
                sock, _addr = srv.accept()
            except OSError:
                return          # server closed
            threading.Thread(target=self._serve, args=(sock,),
                             name="plugin-host-conn", daemon=True).start()

    def _poll_loop(self):
        while True:
            time.sleep(TEXT_POLL_S)
            if self._closing:
                with self._lock:
                    if self._server is None:
                        # Stopped. A later reload opens a new server and
                        # starts a new poller.
                        self._poller = None
                        return
                continue
            with self._lock:
                wanted = [(self._plugins.get(plugin), action)
                          for plugin, action in self._watched]
            for p, action in wanted:
                # Anything on screen, including names the action list does
                # not carry: a folder's items, a binding with its own values.
                if p is not None and p.state == "running" and p.conn is not None:
                    self._ask_text(p, action)

    def _launch(self, info, crashes=None):
        p = _Plugin(info)
        p.crashes = list(crashes or [])
        with self._lock:
            self._plugins[p.name] = p
        if not p.entry or not os.path.isfile(p.entry):
            p.state, p.detail = "failed", "its entry point is missing"
            self._changed()
            return
        command, error = self._command(p)
        if error:
            p.state, p.detail = "failed", error
            self._changed()
            return
        env = dict(os.environ)
        env.update({
            "LPS_SERVER_URL": "ws://127.0.0.1:%d/" % self._port,
            "LPS_SESSION_TOKEN": p.token,
            "LPS_PLUGIN_NAME": p.name,
            "LPS_PLUGIN_PACKAGE_DIRECTORY_PATH": p.dir,
            "LPS_PLUGIN_DATA_DIRECTORY": data_dir(p.name),
            # Mono keeps HKEY_LOCAL_MACHINE and HKEY_CLASSES_ROOT under
            # /etc/mono/registry, which only root can write, and Windows
            # plugins write there (Weather registers a URL protocol on
            # load). Each plugin gets a machine registry of its own instead.
            "MONO_REGISTRY_PATH": os.path.join(data_dir(p.name), "registry"),
        })
        try:
            # Appended across restarts, so the output that led to a crash is
            # still there after the restart; a fresh launch starts it over.
            log = open(log_path(p.name), "a" if p.crashes else "w", encoding="utf-8")
        except OSError:
            log = subprocess.DEVNULL
        try:
            p.proc = subprocess.Popen(command, cwd=os.path.dirname(p.entry) or p.dir,
                                      env=env, stdin=subprocess.DEVNULL, stdout=log,
                                      stderr=subprocess.STDOUT)
        except OSError as e:
            p.state, p.detail = "failed", "could not start it: %s" % e
            self._changed()
            return
        finally:
            if log is not subprocess.DEVNULL:
                log.close()
        p.state, p.detail = "starting", ""
        self._changed()
        threading.Thread(target=self._watch, args=(p,),
                         name="plugin-%s" % p.name, daemon=True).start()
        timer = threading.Timer(CONNECT_TIMEOUT_S, self._connect_timeout, args=(p,))
        timer.daemon = True
        timer.start()

    def _command(self, p):
        """(argv, error) to start a plugin."""
        if p.runtime == "dotnet":
            # .NET 8/10 plugins need the .NET runtime; .NET Framework ones
            # run best on Mono (System.Drawing, WinForms) and on .NET when
            # Mono is not there.
            framework = target_framework(p.entry)
            if framework != "core" and self.mono:
                host, error = dotnet_host()
                if not error:
                    return [self.mono, host, p.entry], ""
            if self.dotnet:
                host, error = dotnet_core_host()
                if error:
                    return None, error
                return [self.dotnet, host, p.entry], ""
            if framework == "core":
                return None, ("it is built for .NET 8 or later, which needs the .NET "
                              "SDK (sudo dnf install dotnet-sdk-10.0)")
            return None, ("it is a .NET plugin, which needs Mono or the .NET SDK "
                          "(sudo dnf install mono-complete)")
        if not self.node:
            return None, "Node.js is not installed"
        return [self.node, p.entry], ""

    def _connect_timeout(self, p):
        if p.state == "starting" and p.proc is not None and p.proc.poll() is None:
            p.detail = "started but has not connected; the log may say why"
            self._changed()

    def _current(self, p):
        with self._lock:
            return self._plugins.get(p.name) is p

    def _watch(self, p):
        code = p.proc.wait()
        p.conn = None
        if p.stopping or self._closing:
            p.state, p.detail = "stopped", ""
            self._changed()
            return
        now = time.time()
        crashes = [t for t in p.crashes if now - t < CRASH_WINDOW_S] + [now]
        if len(crashes) > len(RESTART_DELAYS_S):
            p.state = "failed"
            p.detail = ("exited %d times in %d s (last code %d), so it was left "
                        "stopped; the log has its output" % (
                            len(crashes), CRASH_WINDOW_S, code))
            self._changed()
            return
        delay = RESTART_DELAYS_S[len(crashes) - 1]
        p.state = "starting"
        p.detail = "exited with code %d; restarting in %d s" % (code, delay)
        self._changed()

        def again():
            if self._closing or not self._current(p):
                return      # reloaded, removed or shut down in the meantime
            info = next((i for i in installed() if i["name"] == p.name), None)
            if info is None:
                return
            self._launch(info, crashes=crashes)
        timer = threading.Timer(delay, again)
        timer.daemon = True
        timer.start()

    def _stop_plugin(self, p):
        p.stopping = True
        conn = p.conn
        if conn is not None:
            try:
                with self._lock:
                    self._next_id += 1
                    mid = self._next_id
                conn.send_json({"id": mid, "name": "StopPlugin",
                                "messageType": "Event", "parameters": {}})
            except (OSError, ConnectionError):
                pass
        proc = p.proc
        if proc is not None and proc.poll() is None:
            # The SDK disconnects on StopPlugin but leaves the process to exit
            # by itself, which a plugin holding a timer never does; SIGTERM
            # after a grace period covers that.
            try:
                proc.wait(timeout=STOP_GRACE_S)
            except subprocess.TimeoutExpired:
                proc.terminate()
                try:
                    proc.wait(timeout=STOP_GRACE_S)
                except subprocess.TimeoutExpired:
                    proc.kill()
        if conn is not None:
            conn.close()
        p.conn = None
        p.state = "stopped"

    def _serve(self, sock):
        sock.settimeout(None)
        try:
            if not _handshake(sock):
                sock.close()
                return
        except OSError:
            sock.close()
            return
        conn = _Connection(sock)
        plugin = None
        try:
            for text in conn.messages():
                try:
                    msg = json.loads(text)
                except ValueError:
                    continue
                if not isinstance(msg, dict):
                    continue
                if plugin is None:
                    plugin = self._on_init(conn, msg)
                    if plugin is None:
                        break
                    continue
                self._on_message(plugin, conn, msg)
        except (OSError, ConnectionError):
            pass
        finally:
            if plugin is not None:
                # Answers to anything still outstanding will never come.
                with self._lock:
                    for mid in [k for k, v in self._pending.items()
                                if v[0] == plugin.name]:
                        del self._pending[mid]
            if plugin is not None and plugin.conn is conn:
                plugin.conn = None
                if plugin.state == "running" and not plugin.stopping:
                    plugin.state, plugin.detail = "starting", "disconnected"
                    self._changed()
            conn.close()

    def _on_init(self, conn, msg):
        """The first message has to be InitConnection with a token we issued.
        Returns the plugin it belongs to, or None to hang up."""
        if msg.get("name") != "InitConnection" or msg.get("messageType") != "Request":
            return None
        params = msg.get("parameters") or {}
        token = params.get("sessionToken", "")
        with self._lock:
            p = next((x for x in self._plugins.values()
                      if secrets.compare_digest(x.token, str(token))), None)
        ok = p is not None and params.get("pluginName") == p.name
        try:
            conn.send_json({"id": msg.get("id"), "name": "InitConnection",
                            "messageType": "Response", "data": None,
                            "failed": not ok, "errorCode": 0 if ok else 10001,
                            "errorMessage": "" if ok else "unknown plugin or token"})
            if not ok:
                return None
            p.conn = conn
            conn.send_json(self._request("GetActionList", {"pluginName": p.name}))
        except (OSError, ConnectionError):
            return None
        return p

    def _on_message(self, p, conn, msg):
        name, kind = msg.get("name"), msg.get("messageType")
        if name == "ActionTextChanged" and kind in ("Event", "Request"):
            self._on_text_changed(p, conn, msg)
            return
        if kind == "Event":
            self._on_event(p, name, msg.get("parameters") or {})
            return
        if kind != "Response":
            return
        with self._lock:
            _plugin, action = self._pending.pop(msg.get("id"), (None, None))
            waiter = self._waiting.pop(msg.get("id"), None)
        if waiter is not None:
            waiter[1] = msg
            waiter[0].set()
            return
        if msg.get("failed"):
            # GetActionText for an action that went away is not worth a line
            # in the console every second.
            if name not in ("GetActionText", "GetActionImage"):
                print("plugin %s: %s failed: %s (%s)" % (
                    p.name, name, msg.get("errorMessage", ""), msg.get("errorCode")))
            return
        if name == "GetActionList":
            data = msg.get("data") or {}
            p.commands = [a for a in data.get("commands") or []
                          if isinstance(a, dict) and a.get("name")]
            p.adjustments = [a for a in data.get("adjustments") or []
                             if isinstance(a, dict) and a.get("name")]
            p.state = "running"
            if getattr(p, "status", "") not in ("Warning", "Error"):
                p.detail = ""
            # A restart that came back up has recovered; forget the backoff.
            p.crashes = []
            self._changed()
            for a in p.commands + p.adjustments:
                self._ask_image(p, a["name"])
            if p.runtime == "dotnet":
                self._send(p, "GetPreferences", {"pluginName": p.name})
        elif name in ("ExecuteCommand", "ExecuteAdjustment") and action:
            # Pressing a key is the likeliest moment for its text to change.
            self._ask_text(p, action)
            self._ask_image(p, action)
        elif name == "GetActionText" and action:
            data = msg.get("data")
            text = data.get("text") if isinstance(data, dict) else data
            self._set_text(p, action, text)
        elif name == "GetActionImage" and action:
            self._set_image(p, action, msg.get("data"))
        elif name == "GetPreferences":
            data = msg.get("data")
            p.preferences = [x for x in data if isinstance(x, dict)] if isinstance(data, list) else []
            self._changed()

    def _on_event(self, p, name, params):
        """Events the .NET host sends (dotnet/PluginApi/Host.cs)."""
        if name == "ActionImageChanged":
            action = params.get("actionName")
            if action:
                self._ask_text(p, action)
                self._ask_image(p, action)
                # Bindings of this action with their own values.
                with self._lock:
                    bound = [a for (plug, a) in self._watched
                             if plug == p.name and a.startswith(action + "|")]
                for a in bound:
                    self._ask_text(p, a)
                    self._ask_image(p, a)
        elif name == "EditorChanged":
            self._changed()
        elif name == "FolderChanged":
            self._folder_event("changed", p, params.get("folder"))
        elif name == "FolderClose":
            self._folder_event("close", p, params.get("folder"))
        elif name == "ActionListChanged":
            self._send(p, "GetActionList", {"pluginName": p.name})
        elif name == "PluginStatusChanged":
            status = str(params.get("status") or "")
            message = str(params.get("message") or "")
            # The plugin's own word on how it is; shown beside its name.
            p.detail = message if status in ("Warning", "Error") else ""
            p.status = status
            self._changed()
        elif name == "PreferencesChanged":
            self._send(p, "GetPreferences", {"pluginName": p.name})
        elif name == "SendKeyboardShortcut":
            combo = str(params.get("combo") or "")
            if combo:
                # Off the socket thread: ydotool takes a moment, and the
                # plugin's other messages should not wait behind it.
                threading.Thread(target=_send_keys, args=(p.name, combo),
                                 name="plugin-keys", daemon=True).start()
        elif name == "Scroll":
            try:
                clicks = int(params.get("clicks") or 0)
            except (TypeError, ValueError):
                clicks = 0
            if clicks:
                horizontal = bool(params.get("horizontal"))
                direction = ("right" if clicks > 0 else "left") if horizontal else ("up" if clicks > 0 else "down")
                threading.Thread(target=_scroll, args=(p.name, direction, abs(clicks)),
                                 name="plugin-keys", daemon=True).start()
        elif name == "SendText":
            text = str(params.get("text") or "")
            if text:
                threading.Thread(target=_send_text, args=(p.name, text),
                                 name="plugin-keys", daemon=True).start()

    def _on_text_changed(self, p, conn, msg):
        """A plugin announcing new text itself. The SDK this was written
        against never sends it (the name exists, nothing uses it), so both
        likely shapes are taken, and anything else is checked by asking."""
        params = msg.get("parameters") or msg.get("data") or {}
        action = params.get("actionName") if isinstance(params, dict) else None
        text = params.get("text") if isinstance(params, dict) else None
        if msg.get("messageType") == "Request":
            try:
                conn.send_json({"id": msg.get("id"), "name": msg.get("name"),
                                "messageType": "Response", "data": True,
                                "failed": False, "errorCode": 0, "errorMessage": ""})
            except (OSError, ConnectionError):
                pass
        if action and isinstance(text, str):
            self._set_text(p, action, text)
        elif action:
            self._ask_text(p, action)
        else:
            for a in p.commands + p.adjustments:
                self._ask_text(p, a["name"])

    def _set_text(self, p, action, text):
        if not isinstance(text, str) or not text:
            return
        with self._lock:
            a = p.action(action)
            if a is None:
                if p.texts.get(action) == text:
                    return
                p.texts[action] = text
            elif a.get("displayName") == text:
                return
            else:
                a["displayName"] = text
        self._changed()

    def _set_image(self, p, action, data):
        if isinstance(data, str) and data.startswith("data:image/svg+xml"):
            self._set_svg(p, action, data)
            return
        raw = _decode_image(data)
        if raw is None:
            p.image_data.pop(action, None)
            if p.images.pop(action, None) is not None:
                self._changed()
            return
        if p.image_data.get(action) == raw:
            return
        path = os.path.join(p.cache_dir(), _cache_name(action, ".supplied.png"))
        try:
            os.makedirs(p.cache_dir(), exist_ok=True)
            with Image.open(io.BytesIO(raw)) as im:
                im.convert("RGBA").save(path, "PNG")
        except Exception as e:
            print("plugin %s: could not use the image for %s: %s" % (p.name, action, e))
            return
        p.images[action] = path
        p.image_data[action] = raw
        self._changed()

    def _set_svg(self, p, action, data):
        """An SVG the plugin supplied (the .NET host passes them through
        untouched). Saved here; render_icons() turns it into the PNG the
        device needs, on the Qt thread, and then it is used like any other."""
        try:
            raw = base64.b64decode(data.partition(",")[2])
        except (ValueError, TypeError):
            return
        if p.image_data.get(action) == raw:
            return
        try:
            os.makedirs(p.cache_dir(), exist_ok=True)
            with open(os.path.join(p.cache_dir(), _cache_name(action, ".supplied.svg")), "wb") as f:
                f.write(raw)
        except OSError as e:
            print("plugin %s: could not keep the image for %s: %s" % (p.name, action, e))
            return
        p.image_data[action] = raw
        p.images.pop(action, None)
        try:
            os.remove(os.path.join(p.cache_dir(), _cache_name(action, ".supplied.png")))
        except OSError:
            pass
        self._changed()


def _send_keys(plugin, combo):
    try:
        import input_backend
        input_backend.send_hotkey(combo)
    except Exception as e:
        print("plugin %s: could not send %s: %s" % (plugin, combo, e))


def _scroll(plugin, direction, clicks):
    try:
        import input_backend
        input_backend.scroll(direction, amount=clicks)
    except Exception as e:
        print("plugin %s: could not scroll: %s" % (plugin, e))


def _send_text(plugin, text):
    try:
        import input_backend
        input_backend.type_text(text)
    except Exception as e:
        print("plugin %s: could not type text: %s" % (plugin, e))


# -- the one the app uses ------------------------------------------------------
_host = None


def set_host(host):
    global _host
    _host = host


def get_host():
    return _host


def execute(value, repeat=1):
    """Run a stored plugin action through the app's host, if it has one."""
    if _host is None:
        print("no plugin host is running; %s did nothing" % value)
        return False
    return _host.execute(value, repeat=repeat)


def label_for(value):
    if _host is not None:
        return _host.label_for(value)
    return parse_value(value)[1] or value


def image_for(value):
    if _host is not None:
        return _host.image_for(value)
    return ""


def is_folder(value):
    return _host is not None and _host.is_folder(value)


def folder_open(value):
    return _host.folder_open(value) if _host is not None else None


def folder_layout(value):
    return _host.folder_layout(value) if _host is not None else None


def folder_close(value):
    if _host is not None:
        _host.folder_close(value)


def watch(values):
    if _host is not None:
        _host.watch(values)


def _main(argv):
    """`python3 plugin_host.py install|remove|list ...`, for doing it from a
    terminal. The app picks changes up the next time it starts."""
    if len(argv) >= 2 and argv[0] == "install":
        rc = 0
        for path in argv[1:]:
            name, error = install(path)
            print(error or "installed %s" % name)
            rc |= bool(error)
        return rc
    if len(argv) == 2 and argv[0] == "remove":
        error = uninstall(argv[1])
        print(error or "removed %s" % argv[1])
        return 1 if error else 0
    if len(argv) == 2 and argv[0] == "url":
        # What the desktop runs for a loupedeck: link.
        error = send_url(argv[1])
        if error and error != "ok":
            print(error)
            return 1
        return 0
    if argv == ["list"]:
        for info in installed():
            print("%s %s  (%s)" % (info["name"], info["version"], info["dir"]))
        return 0
    print("usage: plugin_host.py install FILE.lplug4... | remove NAME | list")
    return 2


if __name__ == "__main__":
    import sys
    sys.exit(_main(sys.argv[1:]))
