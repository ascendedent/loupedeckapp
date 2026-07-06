"""Qt-free device engine: connect, render profiles, and route input.

This is the device-side logic (previously interwoven in the PyQt5 `LdApp`)
extracted so the PySide6/QML front-end can drive the real hardware without any
Qt binding. It owns the devleaks device + an `LdConfiguration`, renders a
workspace's images to the CT, and dispatches device events to bound actions and
workspace/submenu navigation.

A UI wraps this and passes callbacks:
  * on_state(kind)  - 'connected' | 'profile' | 'workspace' changed (refresh UI)
Callbacks fire on the devleaks reader thread for device-driven events; the UI
must marshal to its own main thread.
"""

import time
from math import floor

from PIL import Image

import ct_support
from DeviceProfile import DeviceProfile, DIAL_ID, WHEEL_DISPLAY, WS_KEYS
from LdConfiguration import LdConfiguration

from Loupedeck import DeviceManager
from Loupedeck.Devices import LoupedeckLive
from Loupedeck.Devices.LoupedeckLive import CALLBACK_KEYWORD as CBC

BACK_BUTTON_PATH = "Images/submenu_back_button.png"


class DeviceController:
    def __init__(self, on_state=None):
        self.device = None
        self.profile = DeviceProfile.for_model("LoupedeckLive")
        self.config = LdConfiguration()
        self.selected_ws = WS_KEYS[0]
        self.submenu_stack = []
        self.connected = False
        self.on_state = on_state

    def _emit(self, kind):
        if self.on_state:
            try:
                self.on_state(kind)
            except Exception as e:
                print("on_state(%s) failed: %s" % (kind, e))

    # -- connection --------------------------------------------------------
    def connect(self, retries=10):
        LoupedeckLive.BAUD_RATE = 460800
        devs = []
        for attempt in range(retries):
            devs = DeviceManager().enumerate()
            if devs:
                break
            time.sleep(0.5 + attempt / 10.0)
        if not devs:
            print("DeviceController: no device found")
            return False
        self.device = devs[0]
        self.profile, pid = DeviceProfile.detect(self.device)
        print("connected %s (PID %s) -> %s" % (
            self.device.DECK_TYPE, ("0x%04x" % pid) if pid else "?", self.profile.describe()))
        if self.profile.has_wheel or self.profile.has_dial:
            ct_support.install_ct_handlers(self.device)
        self.device.set_callback(self.device_callback)
        self.init_device()
        self.connected = True
        self.on_workspace_press(WS_KEYS[0])
        self._emit("connected")
        return True

    def init_device(self):
        self.device.reset()
        self.device.set_button_color("circle", "green")
        for i in range(1, 8):
            self.device.set_button_color(str(i), (63, 63, 63))
        self.device.set_brightness(40)

    def close(self):
        if self.device:
            self.device.stop()
            self.device = None
        self.connected = False

    # -- profiles ----------------------------------------------------------
    def load_profile(self, name):
        if not name:
            return
        if self.device:
            self.device.reset()
        self.config.load(name)
        self.submenu_stack.clear()
        self.selected_ws = WS_KEYS[0]
        if self.device:
            self.on_workspace_press(WS_KEYS[0])
        self._emit("profile")

    # -- geometry helpers (profile-driven) ---------------------------------
    def tb_name_to_keycode(self, name):
        if "tb" in name and len(name) == 4:
            row = int(name[2]); col = int(name[3])
            return (row - 1) * self.profile.columns + col - 1

    def td_pos_to_display_name(self, x, y):
        ch = self.profile.side_cell_size[1]
        s = "dis" + str(floor(y / ch) + 1)
        return s + ("L" if x < self.profile.side_width else "R")

    def knob_to_enc_name(self, knob):
        row = {"T": 1, "C": 2}.get(knob[4], 3)
        return "enc" + str(row) + knob[5]

    # -- rendering ---------------------------------------------------------
    def set_img_to_touchbutton(self, image_path, keycode):
        ksize = self.profile.key_size
        try:
            with open(image_path, "rb") as f:
                image = Image.open(f).convert("RGBA").resize(ksize)
        except Exception:
            image = Image.new("RGBA", ksize, "black")
        self.device.set_key_image(keycode, image)

    def set_img_to_touchdisplay(self, image_path, side, row, auto_refresh=True):
        display = self.profile.side_display_name(side)
        x = self.profile.side_display_draw_x(side)
        cw, ch = self.profile.side_cell_size
        try:
            with open(image_path, "rb") as f:
                image = Image.open(f).convert("RGBA").resize((cw, cw)).crop((0, -15, cw, cw + 15))
        except Exception:
            image = Image.new("RGBA", (cw, cw), "black")
        self.device.draw_image(image, display=display, width=cw, height=ch,
                               x=x, y=(row - 1) * ch, auto_refresh=auto_refresh)

    def set_img_to_wheel(self, image_path):
        wsize = self.profile.wheel_size
        try:
            with open(image_path, "rb") as f:
                image = Image.open(f).convert("RGBA").resize(wsize)
        except Exception:
            image = Image.new("RGBA", wsize, "black")
        ct_support.draw_wheel(self.device, image)

    def render_workspace(self, ws):
        self.device.reset()
        for key, path in ws.images.items():
            if not path:
                continue
            if key.startswith("tb"):
                self.set_img_to_touchbutton(path, self.tb_name_to_keycode(key))
            elif key.startswith("dis"):
                self.set_img_to_touchdisplay(path, key[4], int(key[3]))
            elif key == WHEEL_DISPLAY and self.profile.has_wheel:
                self.set_img_to_wheel(path)

    # -- workspace / submenu state -----------------------------------------
    def current_ws(self):
        return self.config.workspaces[WS_KEYS.index(self.selected_ws)]

    def current_menu(self):
        return self.submenu_stack[-1].action if self.submenu_stack else self.current_ws()

    def get_ws(self, key):
        return self.config.workspaces[WS_KEYS.index(key)]

    def on_workspace_press(self, ws_key):
        if self.submenu_stack:
            self.submenu_stack.clear()
        self.device.set_button_color(self.selected_ws, (63, 63, 63))
        self.selected_ws = ws_key
        self.device.set_button_color(ws_key, "green")
        self.render_workspace(self.get_ws(ws_key))
        self._emit("workspace")

    # -- event routing (mirrors LdApp.device_callback) ---------------------
    def device_callback(self, ld, message):
        if CBC.SCREEN.value in message:
            if "touchstart" in message[CBC.ACTION.value]:
                if message[CBC.SCREEN.value] == WHEEL_DISPLAY:
                    self.run_bound_action(WHEEL_DISPLAY)
                elif message[CBC.KEY.value] is not None:
                    self.on_touchkey_press(message[CBC.KEY.value])
                else:
                    self.on_touchdisplay_press(message[CBC.X.value], message[CBC.Y.value])
        elif message[CBC.IDENTIFIER.value] == DIAL_ID:
            if message[CBC.ACTION.value] is CBC.ROTATE.value:
                self.run_bound_action("dial-" + message[CBC.STATE.value][0])
            elif message[CBC.ACTION.value] is CBC.PUSH.value and message[CBC.STATE.value] == "down":
                self.run_bound_action("dial")
        elif "knob" in message[CBC.IDENTIFIER.value]:
            if message[CBC.ACTION.value] is CBC.ROTATE.value:
                self.run_bound_action(self.knob_to_enc_name(message[CBC.IDENTIFIER.value]) + "-" + message[CBC.STATE.value][0])
            elif message[CBC.ACTION.value] is CBC.PUSH.value and message[CBC.STATE.value] == "down":
                self.run_bound_action(self.knob_to_enc_name(message[CBC.IDENTIFIER.value]))
        elif message[CBC.IDENTIFIER.value] in WS_KEYS:
            if message[CBC.STATE.value] == "down" and message[CBC.IDENTIFIER.value] != self.selected_ws:
                self.on_workspace_press(message[CBC.IDENTIFIER.value])
        elif message[CBC.IDENTIFIER.value] in self.profile.extra_buttons:
            if message.get(CBC.STATE.value) == "down":
                self.run_bound_action(message[CBC.IDENTIFIER.value])

    def on_touchkey_press(self, key):
        row = floor(key / self.profile.columns) + 1
        col = key - self.profile.columns * (row - 1) + 1
        self.on_touch_press("tb" + str(row) + str(col))

    def on_touchdisplay_press(self, x, y):
        self.on_touch_press(self.td_pos_to_display_name(x, y))

    def on_touch_press(self, str_key):
        action = self.current_menu().actions.get(str_key)
        if action is None:
            return
        if action.a_type == "submenu":
            self.submenu_stack.append(action)
            self.render_workspace(action.action)
            self._emit("workspace")
        elif action.a_type == "back":
            if self.submenu_stack:
                self.submenu_stack.pop()
                self.render_workspace(self.current_menu())
                self._emit("workspace")
        else:
            action.execute()

    def run_bound_action(self, str_key):
        action = self.current_menu().actions.get(str_key)
        if action is not None:
            if action.a_type in ("submenu", "back"):
                self.on_touch_press(str_key)
            else:
                action.execute()
