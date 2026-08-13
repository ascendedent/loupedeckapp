"""Tuning inherited into submenus, and preservation of unknown tuning keys."""
import json
import sys

from _harness import Checks, controller

from LdConfiguration import (LdWorkspace, LdSubmenu, LdAction, DEFAULT_TUNING,
                             normalize_tuning, preset_to_tuning)

c = Checks()

# -- unknown keys survive a load/save round-trip ------------------------------
# Stand-ins for fields a *newer* build might add; curve and max_steps are real
# fields now, so they cannot serve as the example.
t = normalize_tuning({"invert": True, "detents_per_step": 2,
                      "detent_deadzone_ms": 25, "haptics": "soft"})
c.eq("an unknown numeric key is preserved", t.get("detent_deadzone_ms"), 25)
c.eq("an unknown string key is preserved", t.get("haptics"), "soft")
c.eq("known keys are still normalised alongside", t["detents_per_step"], 2)

ws = LdWorkspace()
ws.tuning["enc1L"] = normalize_tuning({"haptics": "soft", "steps_per_detent": 2})
ws2 = LdWorkspace.from_JSON(json.loads(json.dumps(ws.to_JSON())))
c.eq("an unknown key survives save and load",
     ws2.tuning_for("enc1L").get("haptics"), "soft")

ws3 = LdWorkspace(); ws3.set_tuning("enc1L", {"haptics": "soft"})
c.eq("an entry holding only unknown keys is kept", "enc1L" in ws3.tuning, True)
ws4 = LdWorkspace(); ws4.set_tuning("enc1L", DEFAULT_TUNING)
c.eq("a genuinely default entry is still dropped", "enc1L" in ws4.tuning, False)


# -- inheritance ---------------------------------------------------------------
def enter_submenu(dc):
    sub = LdSubmenu(name="sub", action=LdWorkspace())
    dc.submenu_stack.append(sub)
    return sub.action


dc, ws = controller()
ws.set_tuning("enc1L", preset_to_tuning("fast3"))
c.eq("workspace tuning applies at the top level",
     dc.effective_tuning("enc1L")["steps_per_detent"], 3)

sub = enter_submenu(dc)
c.eq("a submenu inherits the workspace's feel",
     dc.effective_tuning("enc1L")["steps_per_detent"], 3)
c.eq("inherited_tuning reports the parent's value",
     dc.inherited_tuning("enc1L")["steps_per_detent"], 3)

dc.set_tuning("enc1L", preset_to_tuning("slow2"))
c.eq("a submenu override wins", dc.effective_tuning("enc1L")["detents_per_step"], 2)
c.eq("the override is stored on the submenu, not the workspace",
     "enc1L" in sub.tuning and ws.tuning_for("enc1L")["steps_per_detent"] == 3, True)

# The case that motivated comparing against the inherited value rather than the
# default: an explicit Original under a Fast 3x workspace must stick.
dc.set_tuning("enc1L", preset_to_tuning("original"))
c.eq("an explicit Original in a submenu is stored", "enc1L" in sub.tuning, True)
c.eq("and actually takes effect rather than re-inheriting",
     dc.effective_tuning("enc1L")["steps_per_detent"], 1)

dc.submenu_stack.pop()
c.eq("leaving the submenu restores the workspace feel",
     dc.effective_tuning("enc1L")["steps_per_detent"], 3)
dc.set_tuning("enc1L", preset_to_tuning("original"))
c.eq("Original at the top level drops the entry", "enc1L" in ws.tuning, False)
dc.close()

dc, ws = controller()
ws.set_tuning("enc2R", preset_to_tuning("fast2"))
s1 = enter_submenu(dc); s2 = enter_submenu(dc)
c.eq("a nested submenu inherits from the workspace",
     dc.effective_tuning("enc2R")["steps_per_detent"], 2)
dc.submenu_stack.pop()
dc.set_tuning("enc2R", preset_to_tuning("slow3"))
dc.submenu_stack.append(LdSubmenu(name="s2", action=s2))
c.eq("a deeper level inherits the nearer override",
     dc.effective_tuning("enc2R")["detents_per_step"], 3)
dc.close()

calls = []


def rec(key):
    class A(LdAction):
        def __init__(self):
            LdAction.__init__(self, action_type="hotkey", action="ctrl+c")

        def execute(self, repeat=1):
            calls.append((key, repeat))
    return A()


dc, ws = controller()
ws.set_tuning("enc1L", preset_to_tuning("fast3"))
sub = enter_submenu(dc)
for d in ("l", "r"):
    sub.actions["enc1L-" + d] = rec("enc1L-" + d)
dc.on_rotate("enc1L", "r")
c.eq("dispatch inside a submenu uses the inherited repeat", calls, [("enc1L-r", 3)])
dc.close()

sys.exit(c.done())
