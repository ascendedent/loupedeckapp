"""Runtime Live S support for the vendored devleaks `python-loupedeck-live` lib.

The lib is written for the Loupedeck **Live** and hardcodes that model's screen
layout in three places:

  1. the centre display starts 60 pixels into the 480-pixel framebuffer and is
     360 wide, because the Live puts a side screen either side of it;
  2. ``set_key_image`` lays keys out four to a row from that same offset;
  3. ``on_touch`` assigns a touch to a key with the same four-column
     arithmetic, and calls anything outside it the left or right side screen.

All three are wrong for a **Live S**, which has no side screens: its one screen
is the whole framebuffer, and its five 90px keys start 15 pixels in.

What that looked like on real hardware (issue #3, the first Live S report):
every key image landed two thirds of a key to the right, so each physical key
showed part of two images and the labels sat on the seams between keys; the
ruler drawn across the whole screen started 60 pixels in and lost its right
hand end; and a touch reported either the wrong key or a side screen the model
does not have.

Patched in place rather than forked, the way ``ct_support`` does it: ``DISPLAYS``
is a module-level dict the lib reads at call time, ``set_key_image`` is looked up
on the instance, and touch handlers live in a per-device dict. Geometry comes
from ``DeviceProfile`` and was cross-checked against the foxxyz `loupedeck` JS
lib (``device.js``, ``class LoupedeckLiveS``), the only source that carries this
model's numbers.

Applying this to a CT or a Live would move their centre screen to the edge of
the framebuffer and lose their side screens, so every entry point checks the
model first and does nothing for anything else.
"""

# Through device_lib so a missing device library is a message rather than a
# traceback at import; see that module, and ct_support which does the same.
from device_lib import CBC, module as _mod

from DeviceProfile import MODEL_LIVE_S

_patched = False


def _is_live_s(profile):
    return getattr(profile, "model", None) == MODEL_LIVE_S


def patch_library(profile):
    """Point the lib's centre display at the whole framebuffer.

    Idempotent. The Live's two side screens are removed rather than left in
    place: they do not exist on this model, and either one would address 60
    pixels of the key grid if some code path still asked for it.
    """
    global _patched
    if _patched:
        return
    width, height = profile.center_size
    _mod.DISPLAYS[_mod.KW_CENTER] = {
        _mod.KW_ID: bytes("\x00M".encode("ascii")),
        _mod.KW_WIDTH: width,
        _mod.KW_HEIGHT: height,
        _mod.KW_OFFSET: profile.center_origin_x,
    }
    for name in (_mod.KW_LEFT, _mod.KW_RIGHT):
        _mod.DISPLAYS.pop(name, None)
        _mod.BUTTON_SIZES.pop(name, None)
        try:
            _mod.DISPLAY_NAMES.discard(name)
        except Exception:
            pass
    _mod.BUTTON_SIZES[_mod.KW_CENTER] = list(profile.key_size)
    _patched = True


def _make_set_key_image(device, profile):
    """A five-column ``set_key_image`` that starts at the first real key.

    x is display-relative: ``draw_buffer`` adds the centre screen's own offset
    (0 on this model), so what is passed is the inset before the first column.
    """
    cols, rows = profile.columns, profile.rows
    key_w, key_h = profile.key_size
    inset = profile.key_inset_x

    def set_key_image(idx, image):
        try:
            index = int(idx)
        except (TypeError, ValueError):
            print("set_key_image: %r is not a key index on a %s"
                  % (idx, profile.display_name))
            return
        if not 0 <= index < cols * rows:
            return
        device.draw_image(
            image, display=_mod.KW_CENTER, width=key_w, height=key_h,
            x=inset + (index % cols) * key_w,
            y=(index // cols) * key_h)

    return set_key_image


def _make_touch_handler(device, profile, event):
    """Decode a touch against this model's key grid.

    The 15px strip either side of the keys is not a control and not a screen,
    so a touch there is reported as nothing at all rather than as the side
    display the lib would have guessed. Touch-end always clears its finger,
    even when it lands in that strip, or a drag off the edge would leave the
    finger open and swallow the next press on that slot.
    """
    cols, rows = profile.columns, profile.rows
    key_w, key_h = profile.key_size
    first_x = profile.center_origin_x + profile.key_inset_x
    last_x = first_x + cols * key_w
    last_y = rows * key_h
    ending = event == CBC.TOUCH_END.value

    def handler(buff):
        try:
            x = int.from_bytes(buff[1:3], "big")
            y = int.from_bytes(buff[3:5], "big")
            idx = buff[5] if len(buff) > 5 else 0
        except Exception:
            return buff

        action = event
        if ending:
            device.touches.pop(idx, None)
        elif idx not in device.touches:
            action = CBC.TOUCH_START.value

        if x < first_x or x >= last_x or y < 0 or y >= last_y:
            return buff
        key = (y // key_h) * cols + (x - first_x) // key_w

        touch = {
            CBC.IDENTIFIER.value: idx,
            CBC.ACTION.value: action,
            CBC.SCREEN.value: _mod.KW_CENTER,
            CBC.KEY.value: key,
            CBC.X.value: x,
            CBC.Y.value: y,
        }
        if action == CBC.TOUCH_START.value:
            device.touches[idx] = touch
        if device.callback:
            device.callback(device, touch)
        return buff

    return handler


def install(device, profile):
    """Give an enumerated Live S the geometry the vendored lib does not have.

    Does nothing for any other model, so callers do not each have to remember
    the check. Idempotent per device. Call after ``DeviceManager().enumerate()``
    and before anything is drawn.
    """
    if not _is_live_s(profile):
        return False
    patch_library(profile)
    device.set_key_image = _make_set_key_image(device, profile)
    device.handlers[_mod.HEADERS["TOUCH"]] = _make_touch_handler(
        device, profile, CBC.TOUCH_MOVE.value)
    device.handlers[_mod.HEADERS["TOUCH_END"]] = _make_touch_handler(
        device, profile, CBC.TOUCH_END.value)
    return True
