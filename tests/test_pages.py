"""Pages of keys (schema v9): a workspace's further pages, turned by swiping
the screen, by a "page" action or in the editor, sharing the workspace's
knobs and buttons. Run on a DeviceController with no device, fed the touch
messages the device library sends."""
import json

from _harness import Checks, controller

from LdConfiguration import LdAction, LdConfiguration, LdWorkspace, SCHEMA_VERSION
from device_lib import CBC

c = Checks()

if CBC is None:
    print("%-58s %s" % ("pages (the device library is not installed)", "skipped"))
    raise SystemExit(c.done())

dc, ws = controller()
pressed = []


class Press(LdAction):
    def __init__(self, name):
        super().__init__(action_type="hotkey", action=name)
        self.name = name

    def execute(self, repeat=1):
        pressed.append(self.name)


ws.actions["tb11"] = Press("first-tb11")
ws.actions["enc1L-l"] = Press("knob")
c.eq("one page to begin with", dc.page_info()[1:], (1, 1))

# -- making pages ----------------------------------------------------------------
c.eq("a page is added, and shown", dc.add_page(), True)
c.eq("page 2 of 2", dc.page_info()[1:], (2, 2))
page2 = ws.pages[0]
c.eq("it starts with no keys", page2.actions["tb11"].a_type, "none")
c.eq("but with the workspace's knobs", page2.actions["enc1L-l"].a_type, "hotkey")
page2.actions["tb11"] = Press("second-tb11")
dc.add_page()
ws.pages[1].actions["tb11"] = Press("third-tb11")
c.eq("a third", dc.page_info()[1:], (3, 3))
c.eq("pages are not counted as submenus",
     len([s for s in dc.submenu_stack if getattr(s, "page_of", None) is None]), 0)

# -- turning ---------------------------------------------------------------------
dc.turn_page("1")
c.eq("to a page by number", dc.page_info()[1], 1)
c.eq("the first page is the workspace itself", dc.current_menu() is ws, True)
dc.turn_page("next")
c.eq("next", (dc.page_info()[1], dc.current_menu() is page2), (2, True))
dc.turn_page("previous")
dc.turn_page("previous")
c.eq("stays put at the start", dc.page_info()[1], 1)
dc.turn_page("3")
dc.turn_page("next")
c.eq("and at the end", dc.page_info()[1], 3)


def touch(action, x, y, key, ident=1):
    dc.device_callback(None, {CBC.IDENTIFIER.value: ident, CBC.ACTION.value: action,
                              CBC.SCREEN.value: "center", CBC.KEY.value: key,
                              CBC.X.value: x, CBC.Y.value: y})


# -- the screen: swipes turn, taps press on lifting --------------------------------
dc.turn_page("1")
del pressed[:]
touch("touchstart", 100, 40, 0)
c.eq("a tap does not press until the finger lifts", pressed, [])
touch("touchend", 102, 42, 0)
c.eq("then presses the key it started on", pressed, ["first-tb11"])
touch("touchstart", 300, 40, 2)
touch("touchmove", 200, 45, 1)
touch("touchend", 120, 50, 0)
c.eq("a swipe to the left turns to the next page", dc.page_info()[1], 2)
c.eq("without pressing anything", pressed, ["first-tb11"])
touch("touchstart", 100, 40, 0)
touch("touchend", 104, 40, 0)
c.eq("a tap on page 2 presses page 2's key", pressed, ["first-tb11", "second-tb11"])
touch("touchstart", 100, 40, 0)
touch("touchend", 300, 60, 2)
c.eq("a swipe to the right turns back", dc.page_info()[1], 1)
touch("touchstart", 100, 40, 0)
touch("touchend", 120, 250, 8)
c.eq("a mostly vertical drag is not a swipe", (dc.page_info()[1], pressed[-1]), (1, "first-tb11"))

# -- a key that turns the page ---------------------------------------------------------
ws.actions["tb12"] = LdAction(action_type="page", action="3")
dc.on_touch_press("tb12")
c.eq("a page action turns to its page", dc.page_info()[1], 3)
dc.on_touch_press("tb11")
c.eq("and that page's keys are live", pressed[-1], "third-tb11")

# -- without pages, a touch presses at once, as always ---------------------------------
dc2, ws2 = controller()
pressed2 = []
ws2.actions["tb11"] = LdAction(action_type="hotkey", action="x")
ws2.actions["tb11"].execute = lambda repeat=1: pressed2.append("now")
dc2.device_callback(None, {CBC.IDENTIFIER.value: 1, CBC.ACTION.value: "touchstart",
                           CBC.SCREEN.value: "center", CBC.KEY.value: 0, CBC.X.value: 100, CBC.Y.value: 40})
c.eq("without pages a key fires on touch", pressed2, ["now"])

# -- removing, and switching workspace -------------------------------------------------
dc.turn_page("2")
c.eq("the page shown is removed", dc.remove_page(), True)
c.eq("leaving two, on the one before", dc.page_info()[1:], (1, 2))
c.eq("the first page cannot be removed", dc.remove_page(), False)
dc.turn_page("2")
dc.on_workspace_press("1")
c.eq("another workspace starts on its first page", dc.page_info()[1:], (1, 1))

# -- saved and loaded ------------------------------------------------------------
cfg = LdConfiguration()
cfg.workspaces[0].actions["tb11"] = LdAction(action_type="hotkey", action="a")
p = cfg.workspaces[0].new_page()
p.actions["tb11"] = LdAction(action_type="hotkey", action="b")
cfg.workspaces[0].pages.append(p)
data = json.loads(json.dumps(cfg.to_JSON()))
c.eq("the schema says it has pages", data["schema_version"], SCHEMA_VERSION)
back = LdConfiguration()
back.from_JSON(data)
c.eq("pages survive saving and loading",
     [pg.actions["tb11"].action for pg in back.workspaces[0].pages], ["b"])
c.eq("a workspace without pages saves none", "pages" in LdWorkspace().to_JSON(), False)

raise SystemExit(c.done())
