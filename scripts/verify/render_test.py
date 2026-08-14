"""Draw known patterns to every screen, so a tester can say what appeared.

Reading input tells us what the device sends. This tells us where things land,
which is the other half of supporting a model: the library addresses the left,
centre and right screens as one framebuffer and adds each one's offset itself,
so a model whose screen is a different width puts everything in the wrong
place, and nothing about that is visible from code.

Nothing is bound and no input is injected. The device is reset at the end, so
the app will redraw over all of this next time it starts.

    .venv/bin/python scripts/verify/render_test.py

Close the main app first, or it will already have the serial port open.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))

from PIL import Image, ImageDraw                                  # noqa: E402

import ct_support                                                 # noqa: E402
import device_lib                                                 # noqa: E402
from DeviceProfile import DeviceProfile                           # noqa: E402

# Distinguishable at a glance and nameable in a report, which "#3a7bd5" is not.
COLORS = [("red", (200, 40, 40)), ("green", (40, 170, 70)),
          ("blue", (50, 90, 220)), ("yellow", (220, 190, 40)),
          ("purple", (150, 60, 190)), ("white", (240, 240, 240))]


def tile(size, color, text):
    img = Image.new("RGB", size, color)
    d = ImageDraw.Draw(img)
    # Default bitmap font: no font file to find, and legible at these sizes.
    tw, th = d.textbbox((0, 0), text)[2:]
    d.text(((size[0] - tw) / 2, (size[1] - th) / 2), text, fill="black")
    d.rectangle([0, 0, size[0] - 1, size[1] - 1], outline="black")
    return img


def ask(question):
    print("\n  ?  %s" % question)
    try:
        answer = input("     > ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return ""
    return answer


def main():
    if not device_lib.available():
        print(device_lib.health()[1])
        return 1

    devs = []
    for attempt in range(10):
        devs = device_lib.DeviceManager().enumerate()
        if devs:
            break
        time.sleep(0.5 + attempt / 10.0)
    if not devs:
        print("No device found. Close the main app first: it holds the port.")
        return 1

    device = devs[0]
    profile, pid = DeviceProfile.detect(device)
    print("Device: %s, USB %s -> %s" % (
        device.DECK_TYPE, ("0x%04x" % pid) if pid else "?", profile.describe()))
    ct_support.install_ct_handlers(device)
    device.reset()
    device.set_brightness(80)

    answers = []

    # -- touch keys ---------------------------------------------------------
    print("\n== Touch keys ==")
    print("  Numbering every key by the index the library uses. If the numbers")
    print("  do not read 1,2,3... left to right and top to bottom, say so.")
    count = profile.columns * profile.rows
    for index in range(count):
        name, rgb = COLORS[index % len(COLORS)]
        device.set_key_image(index, tile(profile.key_size, rgb, str(index + 1)))
    answers.append(("touch keys", ask(
        "How many keys lit up, in what grid, and did the numbers run in order "
        "left to right and top to bottom?")))

    # -- side displays ------------------------------------------------------
    if profile.has_side_displays:
        print("\n== Side screens ==")
        cw, ch = profile.side_cell_size
        for side, color in (("L", (200, 40, 40)), ("R", (50, 90, 220))):
            for row in range(profile.side_cells):
                device.draw_image(
                    tile((cw, ch), color, "%s%d" % (side, row + 1)),
                    display=profile.side_display_name(side),
                    width=cw, height=ch,
                    x=profile.side_display_draw_x(side), y=row * ch)
        answers.append(("side screens", ask(
            "Is the left strip red and numbered L1 to L3 top to bottom, and the "
            "right strip blue and numbered R1 to R3? Anything off-screen or in "
            "the wrong place?")))
    else:
        print("\n== Side screens: this model has none, skipping ==")

    # -- the whole centre screen -------------------------------------------
    print("\n== Centre screen as one image ==")
    cw, ch = profile.center_size
    band = Image.new("RGB", (cw, ch), (20, 20, 30))
    d = ImageDraw.Draw(band)
    for i in range(0, cw, 40):
        d.line([(i, 0), (i, ch)], fill=(90, 90, 120))
        d.text((i + 3, 4), str(i), fill=(200, 200, 220))
    d.rectangle([0, 0, cw - 1, ch - 1], outline=(255, 255, 255))
    d.text((6, ch // 2), "CENTRE %dx%d" % (cw, ch), fill=(255, 255, 255))
    device.draw_image(band, display="center", width=cw, height=ch, x=0, y=0)
    answers.append(("centre screen", ask(
        "Does the ruler fill the whole main screen edge to edge? Which number "
        "is at the far left edge, and which is at the far right?")))

    # -- wheel --------------------------------------------------------------
    if profile.has_wheel:
        print("\n== Wheel screen ==")
        ww, wh = profile.wheel_size
        ct_support.draw_wheel(device, tile((ww, wh), (40, 170, 70), "WHEEL"))
        answers.append(("wheel", ask(
            "Is the round screen green with WHEEL on it, and the right way up?")))

    # -- button LEDs --------------------------------------------------------
    print("\n== Button lights ==")
    for i, key in enumerate(profile.visible_workspace_keys):
        try:
            device.set_button_color(key, COLORS[i % len(COLORS)][0])
        except Exception as e:
            print("  set_button_color(%r) raised %s: %s" % (key, type(e).__name__, e))
    answers.append(("button lights", ask(
        "How many round buttons lit up, and in what colours left to right?")))

    print("\nResetting the device.")
    try:
        device.reset()
        device.stop()
    except Exception:
        pass

    print("\n" + "=" * 68)
    print("PASTE EVERYTHING BELOW INTO YOUR REPORT")
    print("=" * 68)
    print("device: %s  USB %s  model detected: %s" % (
        device.DECK_TYPE, ("0x%04x" % pid) if pid else "?", profile.model))
    print("geometry the app assumed: %s" % profile.describe())
    for title, answer in answers:
        print("\n-- %s\n   %s" % (title, answer or "(no answer)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
