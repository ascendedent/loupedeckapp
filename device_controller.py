"""Qt-free device engine: connect, render profiles, and route input.

This is the device-side logic (previously interwoven in the old PyQt5 UI)
extracted so the PySide6/QML front-end can drive the real hardware without any
Qt binding. It owns the devleaks device + an `LdConfiguration`, renders a
workspace's images to the CT, and dispatches device events to bound actions and
workspace/submenu navigation.

A UI wraps this and passes callbacks:
  * on_state(kind)  - 'connected' | 'profile' | 'workspace' changed (refresh UI)
Callbacks fire on the devleaks reader thread for device-driven events; the UI
must marshal to its own main thread.
"""

import queue
import threading
import time
from math import floor

from PIL import Image

import ct_support
import label_render
from DeviceProfile import DeviceProfile, DIAL_ID, WHEEL_DISPLAY, WS_KEYS
from LdConfiguration import (LdConfiguration, LdAction, LdSubmenu,
                             DEFAULT_TUNING, DIAL_KEY, ROTATE_CONTROLS,
                             accel_steps)

from Loupedeck import DeviceManager
from Loupedeck.Devices import LoupedeckLive
from Loupedeck.Devices.LoupedeckLive import CALLBACK_KEYWORD as CBC

BACK_BUTTON_PATH = "Images/submenu_back_button.png"


class DeviceController:
    # Sentinel telling the dispatch thread to exit (a plain object so it can
    # never collide with a real (control, direction) tuple).
    _ROT_STOP = object()

    def __init__(self, on_state=None):
        self.device = None
        self.profile = DeviceProfile.for_model("LoupedeckLive")
        self.config = LdConfiguration()
        self.selected_ws = WS_KEYS[0]
        self.submenu_stack = []
        self.connected = False
        self.on_state = on_state
        # Banked detents per rotate control for the Slow presets:
        # control -> (direction, count). Runtime feel, not persisted state.
        # Written by the dispatch thread, cleared from the message thread.
        self._rot_accum = {}
        self._rot_lock = threading.Lock()
        self._rot_q = queue.Queue()
        self._rot_thread = None
        # Speed signal for the acceleration curve: when each detent arrived, and
        # a smoothed interval between them, per control. Timed on the message
        # thread at arrival so it measures the hand and not our dispatch.
        self._rot_last_ts = {}
        self._rot_interval = {}
        # Draft/staging: edits mutate the in-memory config (so the on-screen
        # mirror updates live) but are not written to disk or pushed to the
        # hardware until save(); revert() reloads the on-disk profile.
        self.dirty = False

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
        if self._rot_thread is not None and self._rot_thread.is_alive():
            self._rot_q.put(self._ROT_STOP)
            self._rot_thread.join(timeout=2.0)
            self._rot_thread = None
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
        self._drain_rotate_queue()
        with self._rot_lock:
            self._rot_accum.clear()
            self._rot_last_ts.clear()
            self._rot_interval.clear()
        self.submenu_stack.clear()
        self.selected_ws = WS_KEYS[0]
        self.dirty = False
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

    # -- labels ------------------------------------------------------------
    def _auto_label_text(self, action):
        """Friendly text for the auto-label: the action's summary (e.g. the
        library name 'Copy'), falling back to the raw action string."""
        t = getattr(action, "a_type", "none")
        if t == "submenu":
            return getattr(action, "name", "") or "menu"
        if t == "back":
            return "Back"
        summary = (getattr(action, "summary", "") or "").strip()
        if summary and summary != "none":
            return summary
        s = str(getattr(action, "action", "") or "")
        if t in ("command", "launch") and s:
            return s.split()[0].rsplit("/", 1)[-1]
        return s or t

    def effective_label(self, menu, key):
        """The label to render for a control. An explicit entry's position/mode
        always apply; its text falls back to an auto-label derived from the
        bound action when there's no explicit text and no image."""
        entry = menu.labels.get(key) or {}
        if entry.get("off"):
            return None             # label explicitly turned off for this control
        text = (entry.get("text") or "").strip()
        pos = entry.get("pos", "bottom")
        mode = entry.get("mode", "over")
        if mode == "shrink" and pos == "middle":
            mode = "over"           # shrink needs a top/bottom band
        if not text:
            # labels are ON by default: derive from the bound action, shown even
            # over an image (the user turns it off per-control via set_label_enabled)
            act = menu.actions.get(key)
            if act is not None and getattr(act, "a_type", "none") != "none":
                text = self._auto_label_text(act)
        if not text:
            return None
        result = {"text": text, "pos": pos, "mode": mode}
        bc = entry.get("bar_color")
        if not bc and mode == "shrink":
            bc = self.effective_bg(menu, key)   # shrink band defaults to the bg colour
        if bc:
            result["bar_color"] = bc
        return result

    def effective_bg(self, menu, key):
        """The background fill colour ('#rrggbb') for a control, or None."""
        return (getattr(menu, "bg_colors", {}) or {}).get(key, "") or None

    # -- rendering ---------------------------------------------------------
    @staticmethod
    def _load_fit(path, size, bg_color=None):
        """Load ``path`` and FIT it (preserve aspect, no crop/spill) centred on a
        ``bg_color`` (or black) canvas of ``size``. Returns a bg-only canvas when
        there is no image. Resizing to the exact size is left to the user (the UI
        shows the target dimensions); we never crop or distort."""
        base = label_render._rgb(bg_color) if bg_color else (0, 0, 0)
        canvas = Image.new("RGBA", size, base + (255,))
        if not path:
            return canvas
        try:
            with open(path, "rb") as f:
                im = Image.open(f).convert("RGBA")
        except Exception:
            return canvas
        sc = min(size[0] / im.width, size[1] / im.height)
        nw, nh = max(1, round(im.width * sc)), max(1, round(im.height * sc))
        im = im.resize((nw, nh), Image.LANCZOS)
        canvas.paste(im, ((size[0] - nw) // 2, (size[1] - nh) // 2), im)
        return canvas

    def set_img_to_touchbutton(self, image_path, keycode, label=None, bg_color=None):
        image = self._load_fit(image_path, self.profile.key_size, bg_color)
        label_render.draw_label(image, label, bg_color)
        self.device.set_key_image(keycode, image)

    def set_img_to_touchdisplay(self, image_path, side, row, label=None, bg_color=None, auto_refresh=True):
        display = self.profile.side_display_name(side)
        x = self.profile.side_display_draw_x(side)
        cw, ch = self.profile.side_cell_size
        image = self._load_fit(image_path, (cw, ch), bg_color)
        label_render.draw_label(image, label, bg_color)
        self.device.draw_image(image, display=display, width=cw, height=ch,
                               x=x, y=(row - 1) * ch, auto_refresh=auto_refresh)

    def set_img_to_wheel(self, image_path, label=None, bg_color=None):
        image = self._load_fit(image_path, self.profile.wheel_size, bg_color)
        label_render.draw_label(image, label, bg_color)
        ct_support.draw_wheel(self.device, image)

    def render_workspace(self, ws):
        self.device.reset()
        for key in ws.images.keys():   # every image-bearing control (tb/dis/wheel)
            path = ws.images.get(key, "")
            label = self.effective_label(ws, key)
            bg = self.effective_bg(ws, key)
            if not path and not label and not bg:
                continue
            if key.startswith("tb"):
                self.set_img_to_touchbutton(path, self.tb_name_to_keycode(key), label, bg)
            elif key.startswith("dis"):
                self.set_img_to_touchdisplay(path, key[4], int(key[3]), label=label, bg_color=bg)
            elif key == WHEEL_DISPLAY and self.profile.has_wheel:
                self.set_img_to_wheel(path, label, bg)
        self.apply_leds(ws)

    # -- physical-button RGB LEDs ------------------------------------------
    @staticmethod
    def _hex_rgb(s):
        s = str(s).lstrip("#")
        if len(s) == 8:      # #aarrggbb -> drop alpha
            s = s[2:]
        try:
            return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
        except Exception:
            return (63, 63, 63)

    def apply_leds(self, ws):
        """Colour the physical button LEDs: custom colours from the workspace,
        with the CT extra buttons taking their colour directly and the workspace
        buttons showing green for the selected page / their colour (or grey)
        otherwise."""
        colors = getattr(ws, "led_colors", {}) or {}
        for key in self.profile.extra_buttons:
            c = colors.get(key)
            if c:
                self.device.set_button_color(key, self._hex_rgb(c))
        for key in WS_KEYS:
            if key == self.selected_ws:
                self.device.set_button_color(key, "green")
            else:
                c = colors.get(key)
                self.device.set_button_color(key, self._hex_rgb(c) if c else (63, 63, 63))

    # -- editing (draft; mutates the in-memory menu, staged until save) -----
    def set_action(self, slot_key, a_type, value, summary=None):
        """Bind (or clear, when a_type=='none') an action on the currently
        displayed menu. Staged only: not written to disk until save().

        ``summary`` is an optional friendly name (e.g. a library action's
        'Copy') used for the auto-label; falls back to the value otherwise.
        'submenu' creates/renames a nested page (an LdSubmenu whose contents are
        edited by navigating into it); 'back' returns to the parent menu."""
        menu = self.current_menu()
        if slot_key not in menu.actions and a_type == "none":
            return
        if a_type == "submenu":
            existing = menu.actions.get(slot_key)
            if isinstance(existing, LdSubmenu):
                existing.setName(value or existing.name)   # preserve contents
            else:
                menu.actions[slot_key] = LdSubmenu(name=value or "submenu")
        elif a_type == "back":
            menu.actions[slot_key] = LdAction(action_type="back")
        elif a_type == "none":
            menu.actions[slot_key] = LdAction()
        else:
            menu.actions[slot_key] = LdAction(action_type=a_type, action=value,
                                              summary=summary or "")
        self.dirty = True

    # -- UI-side submenu navigation (mirrors device press handling) --------
    def open_submenu(self, slot_key):
        """Navigate the app into the submenu bound at slot_key (edits then
        target the nested page). Also renders it on the device if connected."""
        action = self.current_menu().actions.get(slot_key)
        if action is None or action.a_type != "submenu":
            return False
        self.submenu_stack.append(action)
        if self.device:
            self.render_workspace(action.action)
        self._emit("workspace")
        return True

    def close_submenu(self):
        """Pop one level of submenu navigation."""
        if not self.submenu_stack:
            return False
        self.submenu_stack.pop()
        if self.device:
            self.render_workspace(self.current_menu())
        self._emit("workspace")
        return True

    def set_image(self, key, path):
        """Set (or clear, when path is falsy) the image for an image-bearing
        control. Staged only: the on-screen mirror reflects it immediately, but
        the hardware is not repainted until save()."""
        menu = self.current_menu()
        if key not in menu.images:
            return
        menu.images[key] = path or ""
        self.dirty = True

    def set_label(self, key, text, pos="bottom", mode="over", bar_color=""):
        """Set (or clear, when text is blank) an explicit text label on an
        image-bearing control. ``bar_color`` ('#rrggbb') tints the band in
        bar/shrink modes. Staged until save()."""
        menu = self.current_menu()
        if key not in menu.images:
            return
        off = bool((menu.labels.get(key) or {}).get("off"))   # preserve on/off state
        text = (text or "").strip()
        pos = pos or "bottom"
        mode = mode or "over"
        if mode == "shrink" and pos == "middle":
            mode = "over"           # shrink needs a top/bottom band
        bar_color = self._norm_hex(bar_color) if bar_color else ""
        # keep the entry whenever text OR a non-default position/mode/bar-colour
        # or the off flag is set; only drop it when everything is default (fall
        # back to pure auto-label, which is on).
        if not off and not text and pos == "bottom" and mode == "over" and not bar_color:
            menu.labels.pop(key, None)
        else:
            entry = {"text": text, "pos": pos, "mode": mode}
            if bar_color:
                entry["bar_color"] = bar_color
            if off:
                entry["off"] = True
            menu.labels[key] = entry
        self.dirty = True

    def set_label_enabled(self, key, enabled):
        """Show/hide a control's label. Labels are ON by default (auto text from
        the bound action, shown even over an image); this only stores an explicit
        off flag and never discards typed text/placement."""
        menu = self.current_menu()
        if key not in menu.images:
            return
        entry = dict(menu.labels.get(key) or {})
        if enabled:
            entry.pop("off", None)
        else:
            entry["off"] = True
        if entry:
            menu.labels[key] = entry
        else:
            menu.labels.pop(key, None)
        self.dirty = True

    def set_bg(self, key, color):
        """Set (or clear, when color is blank) a background fill colour
        ('#rrggbb') for an image-bearing control. Staged until save()."""
        menu = self.current_menu()
        if key not in menu.images:
            return
        if color:
            menu.bg_colors[key] = self._norm_hex(color)
        else:
            menu.bg_colors.pop(key, None)
        self.dirty = True

    @staticmethod
    def _norm_hex(s):
        """Normalise any colour string (#rgb variants / Qt's #aarrggbb) to
        #rrggbb so both PIL and QML read it consistently."""
        return "#%02x%02x%02x" % DeviceController._hex_rgb(s)

    def set_led(self, key, color):
        """Set (or clear, when color is blank) a physical button's RGB LED
        colour ('#rrggbb'). Staged until save()."""
        if key not in WS_KEYS and key not in self.profile.extra_buttons:
            return
        menu = self.current_menu()
        if color:
            c = str(color)
            menu.led_colors[key] = c if c.startswith("#") else "#" + c
        else:
            menu.led_colors.pop(key, None)
        self.dirty = True

    def set_tuning(self, control, tuning):
        """Set a rotate control's feel (schema v5). Staged until save().

        Unlike images and LEDs this never touches the hardware: tuning only
        changes how incoming rotate events are interpreted, so there is nothing
        to repaint. Banked detents are dropped, otherwise a count taken under
        the old setting would be spent under the new one.
        """
        if control not in ROTATE_CONTROLS:
            return
        menu = self.current_menu()
        menu.set_tuning(control, tuning, inherited=self.inherited_tuning(control))
        with self._rot_lock:
            self._rot_accum.pop(control, None)
        self.dirty = True

    def save(self):
        """Commit staged edits: write the profile file and repaint the device
        with the current menu's images."""
        if not self.config.profile:
            return
        self.config.save(self.config.profile)
        if self.device:
            self.render_workspace(self.current_menu())
        self.dirty = False

    def revert(self):
        """Discard staged edits by reloading the on-disk profile."""
        if not self.config.profile:
            return
        self.config.load(self.config.profile)
        self.submenu_stack.clear()
        if self.device:
            self.render_workspace(self.current_menu())
        self.dirty = False

    # -- workspace / submenu state -----------------------------------------
    def current_ws(self):
        return self.config.workspaces[WS_KEYS.index(self.selected_ws)]

    def current_menu(self):
        return self.submenu_stack[-1].action if self.submenu_stack else self.current_ws()

    def get_ws(self, key):
        return self.config.workspaces[WS_KEYS.index(key)]

    def on_workspace_press(self, ws_key):
        # Banked detents belong to the workspace that banked them; tuning can
        # differ per workspace, so carrying a partial count across is wrong,
        # as is replaying queued detents against the new menu.
        self._drain_rotate_queue()
        with self._rot_lock:
            self._rot_accum.clear()
            self._rot_last_ts.clear()
            self._rot_interval.clear()
        if self.submenu_stack:
            self.submenu_stack.clear()
        self.selected_ws = ws_key
        # render_workspace applies images + LED colours (incl. selected=green)
        self.render_workspace(self.get_ws(ws_key))
        self._emit("workspace")

    # -- event routing -----------------------------------------------------
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
                self._enqueue_rotate(DIAL_KEY, message[CBC.STATE.value][0])
            elif message[CBC.ACTION.value] is CBC.PUSH.value and message[CBC.STATE.value] == "down":
                self.run_bound_action("dial")
        elif "knob" in message[CBC.IDENTIFIER.value]:
            if message[CBC.ACTION.value] is CBC.ROTATE.value:
                self._enqueue_rotate(
                    self.knob_to_enc_name(message[CBC.IDENTIFIER.value]),
                    message[CBC.STATE.value][0])
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

    # -- encoder feel resolution (schema v5) -------------------------------
    def _menu_chain(self):
        """Workspace first, then each open submenu, deepest last."""
        return [self.current_ws()] + [s.action for s in self.submenu_stack]

    def _resolve_tuning(self, control, chain):
        """Nearest explicit entry wins; nothing set anywhere means defaults."""
        for menu in reversed(chain):
            if control in getattr(menu, "tuning", {}):
                return menu.tuning_for(control)
        return dict(DEFAULT_TUNING)

    def effective_tuning(self, control):
        """How `control` actually behaves right now.

        A submenu is its own LdWorkspace, so without inheritance a knob set to
        Fast 3x on a workspace would silently drop back to 1:1 the moment you
        opened a submenu. Feel is a property of the hardware, so it carries
        down the stack unless a submenu overrides it deliberately.
        """
        return self._resolve_tuning(control, self._menu_chain())

    def inherited_tuning(self, control):
        """What `control` would resolve to if the *current* menu said nothing,
        i.e. what an entry here has to differ from to be worth storing."""
        return self._resolve_tuning(control, self._menu_chain()[:-1])

    def on_rotate(self, control, direction, count=1):
        """Apply schema v5 tuning, then dispatch the rotate slot.

        The device reports direction only, never magnitude, so both halves of
        "sensitivity" are synthesised here: `detents_per_step` divides (bank
        detents until the threshold is reached) and `steps_per_detent`
        multiplies (one action carrying a repeat count).

        `count` is the number of detents this call represents. It is 1 for a
        single event and larger when the dispatcher has coalesced a backlog.
        """
        tuning = self.effective_tuning(control)

        if tuning["invert"]:
            direction = "r" if direction == "l" else "l"

        n = max(1, int(count))
        per_step = tuning["detents_per_step"]
        with self._rot_lock:
            if per_step > 1:
                last_dir, banked = self._rot_accum.get(control, (None, 0))
                # Reset on reversal: otherwise turning a Slow 1/3 control back
                # the other way spends detents banked in the old direction.
                banked = banked + n if last_dir == direction else n
                steps, banked = divmod(banked, per_step)
                self._rot_accum[control] = (direction, banked)
                if steps == 0:
                    return
            else:
                self._rot_accum.pop(control, None)
                steps = n

        repeat = accel_steps(steps * tuning["steps_per_detent"],
                             self.detent_interval_ms(control), tuning)
        if n > 1:
            # A coalesced batch means dispatch is already behind the hand. Left
            # unbounded, a fast spin on Fast 3x becomes a single repeat of ~100,
            # which blocks for over half a second and keeps moving long after
            # the hand stops (measured: 1.56s of overshoot). Capping only the
            # backlog case is the compromise: what a *single* detent asks for is
            # never discarded, because that is literal user intent, but what a
            # backlog asks for is already unachievable at this rate.
            repeat = min(repeat, tuning["max_steps"])
        self.run_bound_action(control + "-" + direction, repeat=repeat)

    # -- coalescing dispatch queue -----------------------------------------
    def _enqueue_rotate(self, control, direction):
        """Hand a rotate event to the dispatch thread.

        Actions block (a subprocess, or a shell command that can take as long
        as it likes). Running them on the device's message thread means a
        backlog drains *after* the user's hand stops and the control keeps
        moving past where they left it. The queue moves that work off the
        message thread; coalescing keeps the backlog from being replayed
        detent-by-detent once it exists.
        """
        self._note_detent(control)
        self._ensure_dispatcher()
        self._rot_q.put((control, direction))

    # A pause longer than this ends the current turn: the next detent starts
    # fresh rather than inheriting the speed of a spin that already finished.
    IDLE_GAP_S = 0.4

    # Smoothing on the inter-detent interval. Raw gaps are jittery enough that
    # a single slow click mid-spin would otherwise drop the multiplier to 1.
    _INTERVAL_ALPHA = 0.5

    def _note_detent(self, control):
        """Record when this detent arrived and update the smoothed interval."""
        now = time.perf_counter()
        with self._rot_lock:
            last = self._rot_last_ts.get(control)
            self._rot_last_ts[control] = now
            if last is None or (now - last) > self.IDLE_GAP_S:
                self._rot_interval.pop(control, None)   # new turn
                return
            gap = now - last
            prev = self._rot_interval.get(control)
            self._rot_interval[control] = (
                gap if prev is None
                else prev + self._INTERVAL_ALPHA * (gap - prev))

    def detent_interval_ms(self, control):
        """Smoothed ms between detents on `control`, or None if it is not
        currently mid-turn."""
        with self._rot_lock:
            v = self._rot_interval.get(control)
        return None if v is None else v * 1000.0

    def _ensure_dispatcher(self):
        if self._rot_thread is None or not self._rot_thread.is_alive():
            self._rot_thread = threading.Thread(
                target=self._dispatch_loop, name="ld-rotate", daemon=True)
            self._rot_thread.start()

    def _dispatch_loop(self):
        while True:
            item = self._rot_q.get()
            if item is self._ROT_STOP:
                return
            batch = {}
            stopping = self._fold(item, batch)
            # Take whatever else is already waiting. Nothing is *waited* for, so
            # an idle control still dispatches one detent immediately; batching
            # only happens when events genuinely piled up behind an action.
            while True:
                try:
                    nxt = self._rot_q.get_nowait()
                except queue.Empty:
                    break
                stopping = self._fold(nxt, batch) or stopping
            for control, net in batch.items():
                if not net:
                    continue          # equal turns both ways cancel out
                try:
                    self.on_rotate(control, "r" if net > 0 else "l",
                                   count=abs(net))
                except Exception as e:
                    print("rotate dispatch for %r failed: %s: %s"
                          % (control, type(e).__name__, e))
            if stopping:
                return

    def _fold(self, item, batch):
        """Accumulate one queued event into `batch`. Returns True for the stop
        sentinel. Opposite detents cancel: the net is where the knob ended up,
        which is the honest reading for a continuous control."""
        if item is self._ROT_STOP:
            return True
        control, direction = item
        batch[control] = batch.get(control, 0) + (1 if direction == "r" else -1)
        return False

    def _drain_rotate_queue(self):
        """Drop pending rotate events (workspace switch / profile load): they
        were aimed at a menu that is no longer on screen."""
        while True:
            try:
                self._rot_q.get_nowait()
            except queue.Empty:
                return

    def run_bound_action(self, str_key, repeat=1):
        action = self.current_menu().actions.get(str_key)
        if action is not None:
            if action.a_type in ("submenu", "back"):
                # Navigation never repeats: N steps into the same submenu is
                # still one submenu.
                self.on_touch_press(str_key)
            else:
                action.execute(repeat=repeat)
