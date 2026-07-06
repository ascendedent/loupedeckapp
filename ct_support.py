"""Runtime CT support for the vendored devleaks `python-loupedeck-live` lib.

The devleaks lib targets the Loupedeck **Live** and does not know about three
things the **CT** adds:

  1. the round dial ``knobCT`` (button/knob id ``0x00``) and the CT's extra
     hardware buttons (``home``/``undo``/.../``e``, ids ``0x0f``-``0x1a``);
  2. the round 240x240 "wheel" screen (framebuffer id ``\\x00W``);
  3. wheel touch events, sent under CT-specific command headers.

Rather than fork the lib, we patch it in place at startup. ``BUTTONS`` and
``DISPLAYS`` are module-level dicts that the lib's handlers look up by name at
call time, so mutating them is sufficient; touch handlers are per-instance, so
those are installed on the device object after it is enumerated.

All of this is verified/tuned against the physical device (see
``scratch/ct_capture.py``). Cross-referenced with the foxxyz `loupedeck` JS lib.
"""

import importlib
from PIL import Image

# BUTTONS / DISPLAYS live as module-level globals in this submodule; the
# package binds the *class* of the same name to `Loupedeck.Devices.LoupedeckLive`,
# so grab the module object explicitly rather than via `from ... import`.
_mod = importlib.import_module("Loupedeck.Devices.LoupedeckLive")
from Loupedeck.Devices.LoupedeckLive import CALLBACK_KEYWORD as CBC

from DeviceProfile import CT_EXTRA_BUTTONS, DIAL_ID, WHEEL_DISPLAY, WHEEL_SIZE

# devleaks builds a 2-byte header as (0x09 << 8) | <foxxyz touch command>.
# Standard touch = 0x094D / 0x096D; the CT wheel uses foxxyz TOUCH_CT 0x52 /
# TOUCH_END_CT 0x72, i.e. these headers. (Confirmed via scratch/ct_capture.py.)
HEADER_TOUCH_CT = 0x0952
HEADER_TOUCH_END_CT = 0x0972

# CT button id map to merge into the lib's BUTTONS (foxxyz constants.js).
_CT_BUTTON_IDS = {
    0x00: DIAL_ID,
    0x0F: "home",
    0x10: "undo",
    0x11: "keyboard",
    0x12: "enter",
    0x13: "save",
    0x14: "fnL",
    0x15: "a",
    0x16: "c",
    0x17: "fnR",
    0x18: "b",
    0x19: "d",
    0x1A: "e",
}

_patched = False


def patch_library():
    """Idempotently extend the devleaks lib's global BUTTONS and DISPLAYS.

    Safe to call more than once. Returns nothing.
    """
    global _patched
    if _patched:
        return

    # 1) Buttons: dial + CT extras. The lib's on_button / on_rotate do
    #    BUTTONS[buff[0]] and would KeyError (silently, in the reader thread)
    #    for any id it doesn't know.
    for code, name in _CT_BUTTON_IDS.items():
        _mod.BUTTONS.setdefault(code, name)

    # 2) Wheel screen. draw_buffer/refresh read width/height/id/offset from
    #    this dict; to_native_format ignores the display name, so this is all
    #    that's needed for draw_image(display="wheel") to work.
    _mod.DISPLAYS.setdefault(
        WHEEL_DISPLAY,
        {
            _mod.KW_ID: b"\x00W",
            _mod.KW_WIDTH: WHEEL_SIZE[0],
            _mod.KW_HEIGHT: WHEEL_SIZE[1],
            _mod.KW_OFFSET: 0,
        },
    )
    # Keep DISPLAY_NAMES (used for validation elsewhere) in sync.
    try:
        _mod.DISPLAY_NAMES.add(WHEEL_DISPLAY)
    except Exception:
        pass
    # BUTTON_SIZES is consulted by set_key_image for grid screens; give the
    # wheel a sane full-screen entry so any set_key_image(display="wheel")
    # doesn't KeyError (we normally draw the wheel via draw_image though).
    _mod.BUTTON_SIZES.setdefault(WHEEL_DISPLAY, [WHEEL_SIZE[0], WHEEL_SIZE[1]])

    # 3) The lib's reset() hardcodes a 3-element color list and indexes it while
    #    iterating DISPLAYS; adding the wheel makes it a 4th display and trips an
    #    IndexError. Replace it with a length-safe version that also blanks the
    #    wheel.
    def _safe_reset(self):
        for display, sizes in _mod.DISPLAYS.items():
            image = Image.new("RGBA", (sizes[_mod.KW_WIDTH], sizes[_mod.KW_HEIGHT]), "black")
            self.draw_image(image, display=display, auto_refresh=True)
    _mod.LoupedeckLive.reset = _safe_reset

    _patched = True


def draw_wheel(device, image, auto_refresh=True):
    """Draw a PIL image to the CT round wheel screen with correct byte order.

    The wheel framebuffer is 16-bit 5-6-5 **big-endian**, unlike the center/side
    screens (little-endian) which the lib's ``to_native_format`` handles. We
    reuse that (tested) LE conversion and byte-swap each 16-bit pixel, then push
    the buffer straight to the wheel display.
    """
    from Loupedeck.ImageHelpers import PILHelper

    if image.size != WHEEL_SIZE:
        image = image.resize(WHEEL_SIZE)
    le = PILHelper.to_native_format(WHEEL_DISPLAY, image.convert("RGBA"))
    be = bytearray(len(le))
    be[0::2] = le[1::2]
    be[1::2] = le[0::2]
    device.draw_buffer(bytes(be), display=WHEEL_DISPLAY, auto_refresh=auto_refresh)


def _make_wheel_touch_handler(device, event):
    """Return a handler(buff) that decodes a CT wheel-touch message.

    Byte layout mirrors the lib's on_touch: x = buff[1:3], y = buff[3:5],
    finger id = buff[5], all big-endian. The distinguishing fact is the command
    header (not the coordinates), so we tag screen = 'wheel' unconditionally.
    """
    def handler(buff):
        try:
            x = int.from_bytes(buff[1:3], "big")
            y = int.from_bytes(buff[3:5], "big")
            idx = buff[5] if len(buff) > 5 else 0
        except Exception:
            return buff
        touch = {
            CBC.IDENTIFIER.value: idx,
            CBC.ACTION.value: event,
            CBC.SCREEN.value: WHEEL_DISPLAY,
            CBC.KEY.value: None,
            CBC.X.value: x,
            CBC.Y.value: y,
        }
        # Mirror on_touch's start/end bookkeeping so the app sees a single
        # touchstart per finger.
        if event == CBC.TOUCH_MOVE.value:
            if idx not in device.touches:
                touch[CBC.ACTION.value] = CBC.TOUCH_START.value
                device.touches[idx] = touch
        else:
            device.touches.pop(idx, None)
        if device.callback:
            device.callback(device, touch)
        return buff
    return handler


def install_ct_handlers(device):
    """Install CT wheel-touch handlers on an enumerated device instance.

    Idempotent per device. Call after ``DeviceManager().enumerate()`` returns
    the CT.
    """
    patch_library()
    device.handlers.setdefault(
        HEADER_TOUCH_CT, _make_wheel_touch_handler(device, CBC.TOUCH_MOVE.value)
    )
    device.handlers.setdefault(
        HEADER_TOUCH_END_CT, _make_wheel_touch_handler(device, CBC.TOUCH_END.value)
    )
