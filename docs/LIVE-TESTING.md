# Testing on a Loupedeck Live or Live S

This app is developed against a **Loupedeck CT**, which is the only device the
author owns. Live and Live S support is written from the vendored library's
source, from published specifications, and now from one Live S report; the code
that came out of that report has still **never run on the hardware**. If you
have one of those devices, an hour of your time would turn a set of educated
guesses into something known.

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

**One report in, and it found the bug this section predicted.** Issue #3 is a
Live S on Fedora 44 / KDE. What it settled:

| Was | Is |
|---|---|
| 5x3 keys, fifteen in total | Confirmed |
| No side screens | Confirmed |
| 480x270 single centre screen | Confirmed, and it is the **whole** framebuffer: no 60px offset |
| Keys start at the left edge | **Wrong.** They start 15px in, five 90px columns ending 15px short of the right |
| The dials are two of the six `knob*` names, we do not know which | `knobTL` and `knobCL`: both on the **left**, which the app had on the right |
| The round buttons are `circle` and `1`..`3` | Confirmed, and `circle` is the one under the dials, `1`..`3` the column on the right |
| Anything drawn lands in the right place | **Wrong, as expected.** Every key image was two thirds of a key too far right |

The screen was the big one. The library treats left, centre and right as one
480-pixel framebuffer and adds each screen's offset itself: left at 0, centre
at 60, right at 420. A Live S has only the one screen, so everything the app
drew was 60 pixels right and clipped, keys were laid out four to a row instead
of five, a touch was assigned to a key by the same four-column arithmetic, and
a CT profile's side strips were painted straight over the outer key columns.

That is fixed in `live_s_support.py`, which patches the library for this model
the way `ct_support.py` does for the CT. **It has never run on the hardware**:
it is arithmetic that matches what the report described, checked by
`tests/test_lives.py` and against the foxxyz `loupedeck` JS lib, which is the
only source that carries this model's numbers.

Still unknown, and worth a second report:

| Question | Why it is open |
|---|---|
| Which physical dial is `knobTL` and which is `knobCL` | Both are on the left; the app assumes upper is `knobTL` (`enc1L`) and lower is `knobCL` (`enc2L`) |
| Whether the dials' rotate direction is the right way round | Never seen |
| Whether pressing a dial reports anything | Never seen |
| Whether a touch on the 15px strip either side does anything | The app now ignores it |

`capture_events.py` answers all four, and it is the script the first report did
not include.

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

The ruler carries red lines where the app thinks each key column begins. If
those line up with the gaps between your keys, the geometry is right; if they
sit inside the keys, say by how much.

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
lives, and into a `*_support.py` module if the library needs patching for a
model the way it did for the CT (`ct_support.py`) and the Live S
(`live_s_support.py`). Where a report contradicts what is written here, the
report wins: it is the only source with hardware behind it.

The parts of the app that do not touch the device (profiles, actions, the
editor) are covered by the test suite and do not need hardware:

```bash
.venv/bin/python tests/run_all.py
```
