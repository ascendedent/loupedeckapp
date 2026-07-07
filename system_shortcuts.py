"""Read the user's configured KDE global shortcuts (best-effort).

Parses ``~/.config/kglobalshortcutsrc`` and returns ``[(label, combo)]`` where
``combo`` is in ``input_backend``'s vocabulary (e.g. ``"super+d"``), so the
config UI can offer "existing machine shortcuts" as a pick-list. Entries whose
accelerator is unset ("none") or uses a key we can't map are skipped, so every
returned combo is one the input backend can actually send. KDE-specific; returns
``[]`` on any other desktop or on error.

Qt-free (platform-adapter layer): no Qt imports, so it can be unit-tested and
reused outside the UI.
"""

import os

# KDE modifier spelling -> input_backend name
_MOD = {"meta": "super", "ctrl": "ctrl", "control": "ctrl", "alt": "alt",
        "shift": "shift"}

# KDE key spelling -> input_backend name (only keys ydotool can send)
_KEYMAP = {
    "pgup": "pageup", "pgdown": "pagedown", "pageup": "pageup",
    "pagedown": "pagedown", "return": "enter", "enter": "enter",
    "esc": "esc", "escape": "esc", "space": "space", "tab": "tab",
    "backspace": "backspace", "del": "delete", "delete": "delete",
    "ins": "insert", "insert": "insert", "home": "home", "end": "end",
    "up": "up", "down": "down", "left": "left", "right": "right",
    "print": "printscreen", "sysreq": "printscreen", "plus": "equal",
    "minus": "minus", "comma": "comma", "period": "dot", "slash": "slash",
    "backslash": "backslash",
}


def _map_token(tok):
    t = tok.strip().lower()
    if not t:
        return None
    if t in _MOD:
        return _MOD[t]
    if t in _KEYMAP:
        return _KEYMAP[t]
    if len(t) == 1 and t.isalnum():
        return t
    if len(t) >= 2 and t[0] == "f" and t[1:].isdigit() and 1 <= int(t[1:]) <= 12:
        return "f%d" % int(t[1:])
    return None


def _map_accel(accel):
    """'Meta+Ctrl+PgDown' -> 'super+ctrl+pagedown'; None if any token is
    unmappable (so we never offer a combo the backend can't send)."""
    parts = accel.replace(" ", "").split("+")
    out = []
    for p in parts:
        m = _map_token(p)
        if m is None:
            return None
        out.append(m)
    return "+".join(out) if out else None


def _pretty(section):
    return section.replace("org.kde.", "").replace(".desktop", "")


def read_shortcuts(path=None, limit=80):
    path = path or os.path.expanduser("~/.config/kglobalshortcutsrc")
    out, seen = [], set()
    try:
        with open(path, "r") as f:
            lines = f.readlines()
    except Exception:
        return out
    section = ""
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].split("][")[0]
            continue
        name, sep, spec = line.partition("=")
        if not sep or name.startswith("_k_"):   # skip friendly-name metadata rows
            continue
        fields = spec.split(",")
        accel = fields[0].split("\t")[0].strip()      # first of possibly-many binds
        if not accel or accel.lower() == "none":
            continue
        combo = _map_accel(accel)
        if not combo or combo in seen:
            continue
        display = fields[-1].strip() if len(fields) >= 3 and fields[-1].strip() else name.strip()
        label = ("%s: %s" % (_pretty(section), display)) if section else display
        out.append((label, combo))
        seen.add(combo)
        if len(out) >= limit:
            break
    return out
