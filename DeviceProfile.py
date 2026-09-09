"""Per-model device geometry and capabilities for Loupedeck devices.

This is the single source of truth for everything that differs between the
Loupedeck CT and the Loupedeck Live so the rest of the app never hardcodes
screen sizes, offsets, or button maps (see docs/PLAN.md workstream A / M1).

Deliberately **Qt-agnostic**: nothing here may import PyQt/PySide (PLAN 4.2 -
"no Qt imports below the UI layer"). Depends only on pyserial for USB PID
detection.

Coordinate note for side displays
----------------------------------
The vendored devleaks lib addresses left/center/right as one 480px-wide
framebuffer and *already* adds each display's own offset in ``draw_buffer``
(left 0, center 60, right 420). So callers must pass a display-*relative* x of
0 for both the left and the right side display; passing an absolute 480 for the
right display (as the Live-era code did) lands it off-screen at x=900. Use
``side_display_draw_x`` instead of hardcoding.

Coordinate note for the centre screen
-------------------------------------
That same framebuffer is laid out differently on a Live S, which has no side
screens: its centre screen is the whole 480 pixels, and its five 90px keys
start 15 pixels in rather than at the edge. Two numbers describe that -
``center_origin_x`` (where the centre screen starts in the framebuffer) and
``key_inset_x`` (how far into it the first key column starts) - and
``live_s_support`` reads them to correct a library that knows only the Live's
60/360 layout. Confirmed against hardware in issue #3.
"""

from __future__ import annotations

# USB product IDs (vendor is always 0x2EC2). Cross-checked against the foxxyz
# `loupedeck` JS lib (device.js) which documents the full CT/Live/LiveS map.
PID_CT = 0x0003
PID_LIVE = 0x0004
PID_LIVE_S = 0x0006

MODEL_CT = "LoupedeckCT"
MODEL_LIVE = "LoupedeckLive"
MODEL_LIVE_S = "LoupedeckLiveS"

_PID_TO_MODEL = {
    PID_CT: MODEL_CT,
    PID_LIVE: MODEL_LIVE,
    PID_LIVE_S: MODEL_LIVE_S,
}

# The CT's touch/dial "wheel" screen (foxxyz id "\x00W"). 240x240, and the CT
# firmware wants this one big-endian (the main screens are otherwise the same
# framebuffer the Live uses).
WHEEL_DISPLAY = "wheel"
WHEEL_SIZE = (240, 240)

# Round dial unique to the CT. Reported as button/knob id 0x00 -> "knobCT".
DIAL_ID = "knobCT"

# Physical buttons bound to workspaces on the CT/Live: 'circle' + '1'..'7'.
# Shared constant so the (Qt-free) config model doesn't depend on the UI layer.
WS_KEYS = ["circle"] + [str(i) for i in range(1, 8)]

# Extra hardware buttons the CT has and the Live lacks (foxxyz BUTTONS 0x0f-0x1a).
CT_EXTRA_BUTTONS = [
    "home", "undo", "keyboard", "enter", "save",
    "fnL", "fnR", "a", "b", "c", "d", "e",
]


# Name of an environment variable that forces a model. Two uses: checking the
# device view against a model we do not have on the desk, and giving anyone
# whose USB PID is missing from the table above a way to say what they own.
FORCE_MODEL_ENV = "LOUPEDECKAPP_MODEL"

_MODEL_ALIASES = {
    "ct": MODEL_CT, "loupedeckct": MODEL_CT,
    "live": MODEL_LIVE, "loupedecklive": MODEL_LIVE,
    "lives": MODEL_LIVE_S, "live-s": MODEL_LIVE_S, "loupedecklives": MODEL_LIVE_S,
}


def forced_model():
    """Model named by the environment, or None. Unknown names are ignored."""
    import os
    raw = (os.environ.get(FORCE_MODEL_ENV) or "").strip().lower()
    if not raw:
        return None
    model = _MODEL_ALIASES.get(raw.replace(" ", "").replace("_", "-"))
    if model is None:
        model = _MODEL_ALIASES.get(raw.replace(" ", "").replace("_", "").replace("-", ""))
    if model is None:
        print("%s=%r is not a known model; ignoring" % (FORCE_MODEL_ENV, raw))
    return model


def pid_for_path(path):
    """Return the USB product id for a serial port path, or None.

    ``path`` is what the devleaks lib stores as ``device.path`` (e.g.
    ``/dev/ttyACM0``). We match it against pyserial's port enumeration, which
    carries USB VID/PID metadata.
    """
    try:
        import serial.tools.list_ports
    except Exception:
        return None
    for p in serial.tools.list_ports.comports():
        if p.device == path:
            return p.pid
    return None


class DeviceProfile:
    """Geometry + capability description for one Loupedeck model."""

    def __init__(
        self,
        model,
        display_name,
        columns=4,
        rows=3,
        key_size=(90, 90),
        center_size=(360, 270),
        center_origin_x=60,
        key_inset_x=0,
        side_width=60,
        side_cell_size=(60, 90),
        has_wheel=False,
        has_dial=False,
        wheel_size=WHEEL_SIZE,
        extra_buttons=(),
        encoders_left=("enc1L", "enc2L", "enc3L"),
        encoders_right=("enc1R", "enc2R", "enc3R"),
        side_cells=3,
        workspace_buttons=8,
        buttons_left=(),
        buttons_right=(),
    ):
        self.model = model
        self.display_name = display_name
        self.columns = columns
        self.rows = rows
        self.key_size = key_size
        self.center_size = center_size
        # Framebuffer x of the centre screen, and of the first key column
        # inside it. See the module docstring; only a Live S differs.
        self.center_origin_x = center_origin_x
        self.key_inset_x = key_inset_x
        self.side_width = side_width
        self.side_cell_size = side_cell_size
        self.has_wheel = has_wheel
        self.has_dial = has_dial
        self.wheel_size = wheel_size
        self.extra_buttons = list(extra_buttons)
        # Which controls this model physically has, in mirror order. The Live S
        # has no side screens and two dials rather than six encoders, so the
        # device view has to render from these rather than assume the CT.
        self.encoders_left = list(encoders_left)
        self.encoders_right = list(encoders_right)
        self.side_cells = side_cells
        self.workspace_buttons = workspace_buttons
        # Round buttons that sit beside the screen rather than under it. The
        # CT and Live put all eight in a row below; a Live S has one under its
        # dials on the left and three in a column on the right (issue #3).
        self.buttons_left = list(buttons_left)
        self.buttons_right = list(buttons_right)

    # -- workspace / button keys -------------------------------------------
    @property
    def workspace_keys(self):
        """Physical buttons bound to workspaces: 'circle' + '1'..'7'."""
        return list(WS_KEYS)

    @property
    def visible_workspace_keys(self):
        """The round buttons this model actually has.

        A profile always stores all eight workspaces (see ``workspace_keys``)
        so a file written on a CT still opens on a Live S; this is only what
        the device view should draw.
        """
        return list(WS_KEYS[: self.workspace_buttons])

    @property
    def buttons_below(self):
        """Round buttons the device view draws in a row under the screen.

        Everything this model has that is not placed at one side, so a model
        that says nothing about placement keeps the row it always had.
        """
        beside = set(self.buttons_left) | set(self.buttons_right)
        return [k for k in self.visible_workspace_keys if k not in beside]

    # -- control inventory --------------------------------------------------
    @property
    def has_side_displays(self):
        return self.side_width > 0 and self.side_cells > 0

    def side_cell_keys(self, side):
        """Touch cells on one side display, top to bottom ('L' or 'R')."""
        if not self.has_side_displays:
            return []
        return ["dis%d%s" % (i + 1, side) for i in range(self.side_cells)]

    @property
    def touch_keys(self):
        """Center-screen key names in reading order ('tb<row><col>')."""
        return ["tb%d%d" % (r + 1, c + 1)
                for r in range(self.rows) for c in range(self.columns)]

    # -- side-display geometry ---------------------------------------------
    def side_display_draw_x(self, side):
        """Display-relative x to pass to ``draw_image`` for a side display.

        Always 0: the vendored lib adds the framebuffer offset itself (see the
        module docstring). ``side`` ("L"/"R") is accepted for symmetry / future
        models that might differ.
        """
        return 0

    def side_display_name(self, side):
        return "left" if side == "L" else "right"

    # -- construction ------------------------------------------------------
    @classmethod
    def for_model(cls, model):
        if model == MODEL_CT:
            return cls(
                MODEL_CT, "Loupedeck CT",
                has_wheel=True, has_dial=True,
                extra_buttons=CT_EXTRA_BUTTONS,
            )
        if model == MODEL_LIVE_S:
            # Live S: one screen that is the whole framebuffer, five columns
            # starting 15px in, no side screens, two dials instead of six
            # encoders and four round buttons instead of eight.
            #
            # The dials report knobTL and knobCL, which is to say they are on
            # the left; an earlier reading of the spec put them on the right,
            # so a dial the device view offered could never fire. The round
            # buttons are one below the dials and three in a column on the
            # right: 'circle' lit the left one and '1'..'3' the right column
            # top to bottom when a Live S owner ran render_test.py (issue #3).
            return cls(
                MODEL_LIVE_S, "Loupedeck Live S",
                columns=5, center_size=(480, 270),
                center_origin_x=0, key_inset_x=15, side_width=0,
                encoders_left=("enc1L", "enc2L"), encoders_right=(),
                side_cells=0, workspace_buttons=4,
                buttons_left=("circle",), buttons_right=("1", "2", "3"),
            )
        # Default to Live geometry (same 360 center as CT, no wheel/dial).
        return cls(MODEL_LIVE, "Loupedeck Live")

    @classmethod
    def for_pid(cls, pid):
        return cls.for_model(_PID_TO_MODEL.get(pid, MODEL_LIVE))

    @classmethod
    def detect(cls, device):
        """Build a profile for a connected devleaks device.

        Uses the USB PID (the devleaks lib reports both CT and Live as
        DECK_TYPE 'LoupedeckLive', so the PID is the only reliable signal).
        Falls back to Live geometry if the PID can't be read.
        """
        pid = pid_for_path(getattr(device, "path", None))
        forced = forced_model()
        if forced is not None:
            return cls.for_model(forced), pid
        if pid is None:
            return cls.for_model(MODEL_LIVE), None
        return cls.for_pid(pid), pid

    def describe(self):
        caps = []
        if self.has_wheel:
            caps.append("wheel %dx%d" % self.wheel_size)
        if self.has_dial:
            caps.append("dial")
        return "%s (%dx%d center, %d cols%s)" % (
            self.display_name, self.center_size[0], self.center_size[1],
            self.columns, ", " + " + ".join(caps) if caps else "",
        )
