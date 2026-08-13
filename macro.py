"""Macros: a sequence of actions on one control.

A macro is written as plain text, one step per line, because the alternative
(a structured list in the profile) would need a schema change and a list editor
in the UI to be usable at all. Text keeps `LdAction.action` a string, so macros
save, load, import and export through everything that already exists.

    hotkey ctrl+c
    wait 200
    hotkey alt+tab
    text hello world

Steps run on a worker thread, never the caller's. A button press arrives on the
device's message thread, and a macro with waits in it would block that thread
for as long as the macro lasts, delaying every other device event behind it.
The worker also serialises macros, so pressing the button twice runs them one
after the other rather than interleaved.

Qt-free.
"""

import queue
import threading
import time

import input_backend
import virtual_keyboard

# Longest a single wait may be. A typo of "wait 60000" should not wedge the
# worker for a minute with no way to stop it.
MAX_WAIT_MS = 5000

# Steps that take the rest of the line verbatim (text may contain spaces).
_VERBATIM = ("text", "command", "launch")


def parse(text):
    """Text to a list of (kind, value) steps. Unknown lines are skipped, and
    returned separately so the UI can point at them rather than failing
    silently."""
    steps, errors = [], []
    for lineno, raw in enumerate(str(text or "").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        head, _, rest = line.partition(" ")
        kind = head.strip().lower()
        value = rest.strip()
        if kind == "wait":
            try:
                ms = max(0, min(MAX_WAIT_MS, int(float(value))))
            except (TypeError, ValueError):
                errors.append((lineno, "wait needs a number of milliseconds"))
                continue
            steps.append(("wait", ms))
        elif kind in ("hotkey", "scroll", "media", "keyboard"):
            if not value:
                errors.append((lineno, "%s needs a value" % kind))
                continue
            steps.append((kind, value))
        elif kind in _VERBATIM:
            steps.append((kind, value))
        else:
            errors.append((lineno, "unknown step %r" % head))
    return steps, errors


# The kinds a step may have, in the order the UI offers them.
STEP_KINDS = ("hotkey", "text", "wait", "scroll", "media", "keyboard",
              "command", "launch")


def steps_for_ui(text):
    """Parsed steps as dicts, for a list editor. Values are strings, including
    waits, so one editor widget handles every kind."""
    steps, _errors = parse(text)
    return [{"kind": kind, "value": str(value)} for kind, value in steps]


def to_text(steps):
    """Serialise steps back to the text form. Round-trips with `parse`, which
    is what lets a list editor and a text editor edit the same value."""
    lines = []
    for step in steps or []:
        if isinstance(step, dict):
            kind = str(step.get("kind", "")).strip().lower()
            value = str(step.get("value", "")).strip()
        else:
            kind, value = str(step[0]).lower(), str(step[1])
        if kind not in STEP_KINDS:
            continue
        lines.append(("%s %s" % (kind, value)).rstrip())
    return "\n".join(lines)


def describe(text):
    """One-line summary for the UI, e.g. '3 steps, 1 problem'."""
    steps, errors = parse(text)
    out = "%d step%s" % (len(steps), "" if len(steps) == 1 else "s")
    if errors:
        out += ", %d problem%s" % (len(errors), "" if len(errors) == 1 else "s")
    return out


def run_step(kind, value):
    if kind == "wait":
        time.sleep(value / 1000.0)
    elif kind == "hotkey":
        input_backend.send_hotkey(value)
    elif kind == "text":
        input_backend.type_text(value)
    elif kind == "scroll":
        direction, _, amount = value.partition(" ")
        try:
            n = max(1, int(amount)) if amount.strip() else 1
        except (TypeError, ValueError):
            n = 1
        input_backend.scroll(direction, amount=n)
    elif kind == "media":
        input_backend.media(value)
    elif kind == "keyboard":
        if value == "show":
            virtual_keyboard.set_active(True)
        elif value == "hide":
            virtual_keyboard.set_active(False)
        else:
            virtual_keyboard.toggle()
    elif kind in ("command", "launch"):
        input_backend.launch_app(value)


class MacroRunner:
    def __init__(self):
        self._q = queue.Queue()
        self._thread = None
        self._stop = threading.Event()

    def _ensure(self):
        if self._thread is None or not self._thread.is_alive():
            self._stop.clear()
            self._thread = threading.Thread(target=self._loop, name="ld-macro",
                                            daemon=True)
            self._thread.start()

    def _loop(self):
        while not self._stop.is_set():
            steps = self._q.get()
            if steps is None:
                return
            for kind, value in steps:
                if self._stop.is_set():
                    break
                try:
                    run_step(kind, value)
                except Exception as e:
                    # One bad step must not abandon the rest of the macro, nor
                    # kill the worker and silently break every later macro.
                    print("macro step %s %r failed: %s: %s"
                          % (kind, value, type(e).__name__, e))

    def run(self, steps):
        if not steps:
            return
        self._ensure()
        self._q.put(list(steps))

    def run_text(self, text):
        steps, errors = parse(text)
        for lineno, msg in errors:
            print("macro line %d: %s" % (lineno, msg))
        self.run(steps)

    def stop(self):
        self._stop.set()
        self._q.put(None)
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None


_runner = MacroRunner()


def run_text(text):
    _runner.run_text(text)


def stop():
    _runner.stop()
