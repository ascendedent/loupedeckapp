# Testing on a Loupedeck Live or Live S

This app is developed against a **Loupedeck CT**, which is the only device the
author owns. Live and Live S support is written from the vendored library's
source and from published specifications, and **none of it has ever run on the
hardware**. If you have one of those devices, an hour of your time would turn a
set of educated guesses into something known.

You do not need to read the code. Three scripts do the work and print a block
of text to paste into a report.

- **Report an issue:** https://github.com/ascendedent/loupedeckapp/issues
- Title it `Live report:` or `Live S report:` so it is easy to find.

---

## What we are unsure about

Everything in this section is an assumption. The point of a report is to
replace as many of these as possible with facts.

### Loupedeck Live (`2ec2:0004`)

The vendored device library was written for this model, so the wire format is
probably right. What has never been checked is the app on top of it.

| Assumption | How confident |
|---|---|
| 360x270 centre screen, 4x3 keys, two 60x270 side strips | High: the library says so |
| Six encoders, reported as `knobTL` `knobCL` `knobBL` `knobTR` `knobCR` `knobBR` | High |
| Eight round buttons, reported as `circle` and `1`..`7` | High |
| No wheel, no dial, no lettered buttons | High |
| Side strips address at a display-relative x of 0 | Medium: fixed for the CT, never seen on a Live |
| Key images land on the key you expect | Medium |

### Loupedeck Live S (`2ec2:0006`)

This one is guesswork. The library has no Live S support at all: it reports
every model as `LoupedeckLive` and carries one screen layout.

| Assumption | How confident |
|---|---|
| 5x3 keys, fifteen in total | High: published spec |
| Two dials and four round buttons | High: published spec |
| No side screens | High: published spec |
| 480x270 single centre screen | Medium |
| Touch keys are reported as indices 0..14 across five columns | Low |
| The dials are reported as two of the six `knob*` names | Low: we do not know which |
| The round buttons are reported as `circle` and `1`..`3` | Low: they could be `1`..`4` |
| Anything drawn to the screen lands in the right place | **Low, and this is the one we most expect to be wrong** |

That last row deserves an explanation, because it is the likeliest bug. The
library treats the left, centre and right screens as **one 480-pixel-wide
framebuffer** and adds each screen's offset itself: left at 0, centre at 60,
right at 420. If the Live S centre screen really is the full 480 wide, then
everything this app draws is shifted 60 pixels right and clipped. The CT needed
its own patches for exactly this kind of difference (`ct_support.py`), and the
Live S may need the same.

---

## What to run

You need the app installed. From a checkout:

```bash
git clone https://github.com/ascendedent/loupedeckapp
cd loupedeckapp
python3 -m venv .venv
.venv/bin/pip install -e ".[device]"
```

If nothing is found later, it is almost certainly permissions. See
**Device permissions** in the README, or just start the app once
(`.venv/bin/python qml_app.py`) and read its Setup dialog, which checks this
for you and prints the commands.

**Close the app before running any of these.** It holds the serial port, and
the scripts will find nothing while it does.

### 1. What device is this? (30 seconds)

```bash
.venv/bin/python scripts/verify/probe_device.py
```

Prints the USB id, what the firmware says about itself, and what geometry this
app decided to use. Paste all of it.

### 2. What does each control send? (10 minutes)

```bash
.venv/bin/python scripts/verify/capture_events.py
```

Prompts you through one group of controls at a time and records for twelve
seconds each. Work left to right, top to bottom, and say in your report which
physical control you were touching when the order is not obvious, especially
for the dials.

It also prints any message the library could not decode. Those matter: a
control whose messages are dropped is a control this app can never support,
and finding one is the most useful thing this script does.

Nothing is bound while it runs, so pressing things cannot trigger actions on
your computer.

### 3. Where does each screen land? (5 minutes)

```bash
.venv/bin/python scripts/verify/render_test.py
```

Draws numbered, coloured patterns to the keys, the side strips, the whole
centre screen and (on a CT) the wheel, asking after each one what you actually
see. Be literal: "the ruler starts at 60 on the left and the right edge is cut
off" is worth more than "looks wrong".

Photographs of the device are extremely welcome, especially for the ruler step.

The device is reset at the end.

### 4. Does the app work? (as long as you like)

Start it and use it:

```bash
.venv/bin/python qml_app.py
```

Worth trying, roughly in order of how likely each is to break:

- Does the on-screen device match the physical one? Right number of keys,
  encoders, round buttons, no controls shown that do not exist?
- Drag an action onto a key and press **Save**. Does the image appear on the
  right key?
- Bind a hotkey to a key and press it. Does it do anything?
- Turn each encoder with something bound to rotate. Right direction? Right
  encoder?
- On a Live: touch the side strips.
- Switch workspaces with the round buttons.

---

## What to send

Paste the output blocks from steps 1 to 3, then anything you noticed in step 4.
This template covers what we need:

```
Device:            Live / Live S
USB id:            (from probe_device.py)
Firmware version:  (from probe_device.py)
Distribution and desktop:   e.g. Fedora 41, KDE Plasma 6 on Wayland

--- probe_device.py output ---
(paste)

--- capture_events.py output ---
(paste)
Notes on which physical control was which:
(e.g. "the top-right dial reported knobTR")

--- render_test.py output ---
(paste)
Photos: (attach if you can)

--- using the app ---
What worked:
What did not:
```

A partial report is worth sending. Step 1 alone confirms the USB id and the
firmware's own name for the model, and that is already more than we know now.

---

## What happens next

Reports go into `DeviceProfile.py`, which is where every per-model difference
lives, and into `ct_support.py` if the library needs patching for a model the
way it did for the CT. Where a report contradicts what is written here, the
report wins: it is the only source with hardware behind it.

The parts of the app that do not touch the device (profiles, actions, the
editor) are covered by the test suite and do not need hardware:

```bash
.venv/bin/python tests/run_all.py
```
