"""Macros: parsing, execution off the caller's thread, and failure handling."""
import sys
import threading
import time

from _harness import Checks

import macro

c = Checks()

# -- parsing -------------------------------------------------------------------
steps, errors = macro.parse("hotkey ctrl+c\nwait 200\ntext hello world")
c.eq("steps parse in order", steps,
     [("hotkey", "ctrl+c"), ("wait", 200), ("text", "hello world")])
c.eq("nothing is flagged", errors, [])

steps, _ = macro.parse("  \n# a comment\n\nhotkey ctrl+v\n")
c.eq("blank lines and comments are skipped", steps, [("hotkey", "ctrl+v")])

# text takes the rest of the line, including spaces and anything that looks
# like another step
steps, _ = macro.parse("text wait 200 is not a step here")
c.eq("text is verbatim", steps, [("text", "wait 200 is not a step here")])

steps, errors = macro.parse("bogus thing\nwait later\nhotkey")
c.eq("bad lines are dropped, not guessed at", steps, [])
c.eq("and each is reported with its line number",
     [e[0] for e in errors], [1, 2, 3])

c.eq("a huge wait is clamped rather than wedging the worker",
     macro.parse("wait 999999")[0], [("wait", macro.MAX_WAIT_MS)])
c.eq("a negative wait floors at zero", macro.parse("wait -5")[0], [("wait", 0)])
c.eq("describe counts steps and problems",
     macro.describe("hotkey a\nbogus b"), "1 step, 1 problem")

# -- list form -----------------------------------------------------------------
# The list editor and the text editor edit the same value, so the conversion
# has to round-trip exactly or switching views would quietly rewrite a macro.
TEXT = "hotkey ctrl+c\nwait 200\ntext hello world\nscroll down 3"
ui = macro.steps_for_ui(TEXT)
c.eq("steps come back as dicts", ui[0], {"kind": "hotkey", "value": "ctrl+c"})
c.eq("wait values are strings too, so one widget edits every kind",
     ui[1], {"kind": "wait", "value": "200"})
c.eq("text keeps its spaces", ui[2]["value"], "hello world")
c.eq("text to list to text is unchanged", macro.to_text(ui), TEXT)

c.eq("an empty macro gives no steps", macro.steps_for_ui(""), [])
c.eq("and no text", macro.to_text([]), "")

c.eq("an unknown kind is dropped rather than written back",
     macro.to_text([{"kind": "bogus", "value": "x"},
                    {"kind": "hotkey", "value": "a"}]), "hotkey a")
c.eq("a step with no value still serialises",
     macro.to_text([{"kind": "text", "value": ""}]), "text")
c.eq("tuples work as well as dicts",
     macro.to_text([("hotkey", "ctrl+v")]), "hotkey ctrl+v")

# editing through the list form produces text the parser accepts
edited = macro.steps_for_ui(TEXT)
edited[1]["value"] = "50"
edited.append({"kind": "media", "value": "next"})
steps, errors = macro.parse(macro.to_text(edited))
c.eq("an edited list parses cleanly", errors, [])
c.eq("with the edit applied", steps[1], ("wait", 50))
c.eq("and the addition", steps[-1], ("media", "next"))

# a macro the text view cannot fully read still round-trips its good steps
c.eq("bad lines do not survive a list round-trip",
     macro.to_text(macro.steps_for_ui("hotkey a\nbogus b\nhotkey c")),
     "hotkey a\nhotkey c")

# -- execution -----------------------------------------------------------------
sent = []


class FakeBackend:
    @staticmethod
    def send_hotkey(combo, repeat=1): sent.append(("hotkey", combo))
    @staticmethod
    def type_text(text): sent.append(("text", text))
    @staticmethod
    def scroll(direction, amount=1): sent.append(("scroll", direction, amount))
    @staticmethod
    def media(action): sent.append(("media", action))
    @staticmethod
    def launch_app(cmd): sent.append(("launch", cmd))


real = macro.input_backend
macro.input_backend = FakeBackend


def wait_for(fn, timeout=4.0):
    end = time.time() + timeout
    while time.time() < end:
        if fn():
            return True
        time.sleep(0.02)
    return False


try:
    # four steps, but `wait` produces no output of its own
    macro.run_text("hotkey ctrl+c\nwait 30\ntext hi\nscroll down 3")
    c.eq("every acting step runs", wait_for(lambda: len(sent) == 3), True)
    c.eq("in the order written", [s[0] for s in sent],
         ["hotkey", "text", "scroll"])
    c.eq("scroll carries its count", sent[-1], ("scroll", "down", 3))

    # The caller must not be blocked: a macro with a wait in it returns at once.
    del sent[:]
    t0 = time.perf_counter()
    macro.run_text("wait 300\nhotkey ctrl+v")
    elapsed = time.perf_counter() - t0
    c.eq("run_text returns immediately, off the caller's thread", elapsed < 0.15, True)
    c.eq("and the macro still completes", wait_for(lambda: len(sent) == 1), True)

    # A failing step must not abandon the rest, nor kill the worker.
    del sent[:]
    calls = {"n": 0}

    def boom(combo, repeat=1):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("nope")
        sent.append(("hotkey", combo))

    FakeBackend.send_hotkey = staticmethod(boom)
    macro.run_text("hotkey a\nhotkey b")
    c.eq("a failing step does not stop the macro",
         wait_for(lambda: sent == [("hotkey", "b")]), True)

    FakeBackend.send_hotkey = staticmethod(
        lambda combo, repeat=1: sent.append(("hotkey", combo)))
    del sent[:]
    macro.run_text("hotkey later")
    c.eq("the worker survives to run the next macro",
         wait_for(lambda: sent == [("hotkey", "later")]), True)

    # Two macros queued together run one after the other, not interleaved.
    del sent[:]
    macro.run_text("hotkey 1\nwait 20\nhotkey 2")
    macro.run_text("hotkey 3\nhotkey 4")
    c.eq("macros are serialised",
         wait_for(lambda: len(sent) == 4)
         and [s[1] for s in sent] == ["1", "2", "3", "4"], True)

    del sent[:]
    macro.run_text("")
    time.sleep(0.2)
    c.eq("an empty macro does nothing at all", sent, [])
finally:
    macro.input_backend = real
    macro.stop()

sys.exit(c.done())
