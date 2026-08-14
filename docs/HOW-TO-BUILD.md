# How to build a deck

Everything about setting this app up: applications, profiles, pages, workspaces,
and the actions that go on the keys. Written to be read straight through once,
and then dipped into.

The last section is for an **AI assistant** working on someone's behalf, because
the fastest way to build a profile is to generate it, and a generated profile
that binds a key nobody can press is worse than no profile.

**Contents**

1. [The shape of it](#1-the-shape-of-it)
2. [Applications](#2-applications)
3. [Profiles](#3-profiles)
4. [Workspaces and submenus](#4-workspaces-and-submenus)
5. [Actions](#5-actions)
6. [Making a key look like something](#6-making-a-key-look-like-something)
7. [Encoders, the dial and the wheel](#7-encoders-the-dial-and-the-wheel)
8. [Dynamic switching](#8-dynamic-switching)
9. [When something does not work](#9-when-something-does-not-work)
10. [For an AI assistant building a profile](#10-for-an-ai-assistant-building-a-profile)

---

## 1. The shape of it

Four levels, from the outside in:

| | What it is | How you get there |
|---|---|---|
| **Application** | Premiere Pro, VS Code, or **Default** for everything else | Focus that application, or pick it in the app selector |
| **Profile** | One complete deck: every key, knob, label and colour | Click it in the profile list |
| **Workspace** | One page of that deck. Eight per profile | Press a round key on the device, click one in the app, or `Ctrl+1`..`Ctrl+8` |
| **Control** | A key, an encoder, the dial, the wheel, a side cell | Tap it on the on-screen device |

A **page** is a fifth thing that sits beside profiles rather than under them: a
rule that says "when this application's window title looks like *this*, use
*that* profile". Premiere Pro is one application, but Cut, Edit and Sound each
want a different deck.

On disk it is directories, so you can look at it, copy it, or put it in git:

```
~/.config/loupedeckapp/Profiles/
├── Default/
│   ├── app.json                 what focuses this app, and which profile it uses
│   └── Starter.json
└── Visual Studio Code/
    ├── app.json
    └── Visual Studio Code.json
```

---

## 2. Applications

**Add one** with the **+** beside the app selector. The dialog lists what is
actually installed on the machine; pick one and its name and window class are
filled in together. That matters, because the window class is what dynamic mode
matches on and almost nobody knows theirs from memory: a Chrome window reports
`google-chrome`, a VS Code window reports `Code`.

If the application is not listed, type a name and add the window class
afterwards with **Add \<focused app\>**, which binds whatever you were last
looking at.

**Default** is the catch-all. It has no window classes on purpose: it is what
you get when nothing else claims the window, so "nothing focuses Default yet" is
the correct state, not a problem to fix.

An application can have several window classes. Add them all: one application
often ships more than one binary, and a Flatpak reports something different
again.

---

## 3. Profiles

A profile is one complete deck. Profiles belong to an application, so
`Premiere Pro/Edit` and `VS Code/Edit` are two different things with the same
name, which is the point.

- **New** makes an empty one, with the CT's labelled buttons wired up.
- **Duplicate** copies what is *on disk*, not your unsaved edits. Duplicating
  something you are mid-change on gives you the saved version deliberately.
- **Rename** and **Delete** do what they say. A profile that ships with the app
  can be edited (which writes your own copy) but not deleted from the
  installation. Deleting keeps a copy in `Deleted/` inside your config
  directory, so a misclick is undone by moving the file back; the twenty most
  recent are kept.
- **Import** / **Export** move one profile as a `.json` file. Importing checks
  the file before it appears in the list, and never overwrites: a name that is
  taken gets a numbered suffix.
- **Export app** / **Import app**, above the profile list, move a whole
  application: every profile in it, its window classes and its pages, in one
  file. That is what to send somebody when you want to hand over a setup rather
  than a single deck. An imported application always arrives as a new one, so
  someone else's Premiere cannot land on top of yours.

Edits are a **draft** until you press **Save**. The on-screen device updates as
you go; the hardware does not change until you save. **Revert** throws the draft
away. Nothing discards a draft without asking.

---

## 4. Workspaces and submenus

Eight workspaces per profile, on the eight round keys. Name them: eight numbered
keys tell you nothing about what is on them, and the name shows in the header
and in the app. Click the workspace chip in the top bar, or use the field in the
inspector when a round key is selected.

Select a round key and you get **Copy page**, **Paste page** and **Clear**.
Pasting replaces everything on the target, its name included, which is what
makes a second page that is mostly like the first a two-click job rather than
twelve single-control copies. Clearing keeps the name, and nothing is written
until you press Save, so **Revert** undoes either.

**Submenus** go deeper. Bind a key to a *Submenu* action and pressing it opens a
fresh page of keys, with a back key already placed. Good for the long tail:
sixteen emoji, a rarely-used export menu, anything that would otherwise crowd
the top level.

---

## 5. Actions

Drag one from the library on the left onto a control, or select the control and
choose in the inspector.

| Type | What it does | Example |
|---|---|---|
| `hotkey` | Sends a key combination | `ctrl+shift+p` |
| `text` | Types a string | `git commit -m ""` |
| `command` | Runs a shell command, detached | `spectacle` |
| `launch` | Same, for starting an application | `code` |
| `media` | Play/pause, next, previous, stop, via MPRIS | `play-pause` |
| `scroll` | Scroll wheel, with a magnitude | `down` |
| `keyboard` | Shows or hides the on-screen keyboard | `toggle` |
| `workspace` | Switches to a workspace of this profile | `circle` |
| `submenu` | Opens a nested page | `Emoji` |
| `back` | Leaves a submenu | |
| `macro` | Several steps in order | see below |

**Key names** in a hotkey are `+`-separated: `ctrl`, `shift`, `alt`, `super`
(which is Command on macOS), letters, digits, `f1`..`f12`, `up`/`down`/
`left`/`right`, `home`, `end`, `pageup`, `pagedown`, `tab`, `space`, `escape`,
`enter`, `backspace`, `delete`, and punctuation either by name (`minus`,
`equal`, `slash`, `backslash`, `grave`, `bracketleft`, `bracketright`) or as the
character itself (`-`, `=`, `/`, `\`, `` ` ``, `[`, `]`). A name the app does not
know is refused rather than guessed at.

**Macros** are one step per line, and are how you do the things a single combo
cannot:

```
hotkey ctrl+k
wait 120
hotkey z
```

That is a VS Code *chord*: two presses, not one combo. The wait is not
decoration, the editor has to register the first press before the second
arrives. Steps are `hotkey`, `text`, `wait <ms>`, `scroll <dir> [n]`, `media`,
`keyboard`, `command`, `launch`. The inspector will edit a macro as a list or as
text, whichever you prefer.

The other thing macros are for is driving an application's own command palette,
which reaches everything an application can do rather than only what it has a
shortcut for:

```
hotkey ctrl+shift+p
wait 250
text Git: Commit
wait 350
hotkey return
```

---

## 6. Making a key look like something

A key with no picture and no label is a black square. Give it one:

- **Image**: any PNG or JPG. It is scaled to fit, never cropped, so the size
  hint in the inspector is the size to make for a pixel-perfect fill.
- **Label**: text over the image, on a bar, or on a band beside a shrunken
  image. Position it top, middle or bottom.
- **Background colour**: fills behind the image. On its own, with a label, it is
  the fastest way to make a readable key without drawing anything.
- **LED colour**: the physical round keys and the CT's lettered keys light up.

Colour by *role* rather than by taste and the deck becomes readable at a glance:
destructive in red or amber, the one you press most in green, navigation in
blue, everything else neutral. Both shipped profiles do this.

Side displays are three cells each by default, or **one tall image** for the
whole strip: pick per workspace and per side in the inspector.

---

## 7. Encoders, the dial and the wheel

Each encoder has three bindings: turn left, turn right, and press. Drop an
action onto the top, middle or bottom third of a knob in the app to set each.

**Encoder feel** is per control, under **Advanced** in the inspector:

- **Invert** if it turns the wrong way for you.
- **Speed**: Original, Slow 1/2 and 1/3 (bank detents, fire once per N), Fast 2x
  and 3x (one detent does N).
- **Acceleration**, off by default. Turning normally behaves exactly as usual;
  spinning ramps up to 10x. Speed is measured from the gap between detents, so
  the first click of a turn is never accelerated.

Acceleration pays off most on **scroll**, where the whole magnitude rides in one
call. On a hotkey it is limited by how fast keystrokes can be delivered.

Put scroll on the same knob in every workspace. Muscle memory is the point of a
deck, and a knob that means something different on each page is a knob you have
to look at.

The **CT wheel** is a round screen you can touch, and the dial around it turns
and presses like an encoder.

---

## 8. Dynamic switching

Turn on **Dynamic** in the top bar. Then, when the focused window changes:

1. The window class is matched against every application's list. First exact
   match wins, then substring, so an app matching `chrome` claims
   `google-chrome`.
2. Inside that application, its **pages** are tried in order against the window
   *title*. First match wins, so the order of your pages is their precedence.
3. No page matched? The application's own **Uses** profile loads.
4. No application matched? The **Fallback** profile loads.

**Pages** are how one application gets several decks. Add one with **+** beside
Pages: give it a name, some text that appears in the window title when you want
it, and the profile to load. The dialog pre-fills the title of the window you
were last in, so focus the thing you want a page for, then come back and add it.

For example, Premiere Pro's window title ends with the name of its workspace:

| Page | Title contains | Profile |
|---|---|---|
| Cutting | `Editing` | Cut |
| Audio | `Audio` | Sound |

The window title is the only signal a Linux compositor gives us that is finer
than the window class. If an application does not put its state in its title,
pages cannot see it, and the answer is a workspace on the deck instead.

A switch never discards unsaved work. If dynamic mode wants to change profile
while you have a draft open, it **waits** and says so in the top bar; save or
revert and the switch happens.

---

## 9. When something does not work

**Nothing happens when I press a key.** Almost always the input backend. Open
the gear, then **Setup**: it checks whether keystrokes can be delivered at all
and prints the commands to fix it. On Wayland that means `ydotool` and a running
`ydotoold`; on macOS it means granting Accessibility permission.

**The device is not found.** Also in **Setup**: on Linux this is the udev rule
and the `dialout` group, and a group change only applies after you log back in.

**An app under-delivers a repeat.** You turn one detent expecting three steps
and it moves one. Some applications collapse identical keypresses that arrive
with no gap. Raise `repeat_delay_ms` in `input_backend.py`; the README's
Troubleshooting section has the measurements.

**Dynamic mode does not switch.** First, can the app read the focused window at
all? Setup says, and what it needs differs by desktop: `kdotool` on KDE, a shell
extension on GNOME (which gives applications no other way to ask), `xprop` on
X11, Accessibility permission on macOS. If it can read it, check the app's
window classes match what the watcher actually reports: the
**Add \<focused app\>** button names it.

**A page never fires.** Pages match on the title, in order, and the first match
wins: a broad page above a narrow one swallows it. Reorder with the arrows.

---

## 10. For an AI assistant building a profile

If you are an AI assistant building a profile for someone, the failure mode is
specific: you will produce a plausible deck that binds a key name the app
refuses, or an action for an application shortcut that does not exist. Both look
finished and do nothing. What follows is how not to do that.

**Generate it, do not hand-write it.** A full profile is a few hundred bound
slots. `scripts/make_starter_profiles.py` and `scripts/make_vscode_profile.py`
are worked examples: build an `LdConfiguration`, set actions, labels and
colours, and dump it. Keep the script, so the profile can be regenerated rather
than hand-patched.

**Validate every binding before you hand it over.** Nothing else in the test
suite will catch a bad profile, because a profile is data:

```python
import input_backend, macro
input_backend._parse_combo("ctrl+shift+p")   # raises KeyError on a bad name
macro.parse(text)                            # returns (steps, errors)
```

`tests/test_starter.py` does exactly this for every profile in `Profiles/`, so
a profile added to the repo is checked automatically. A profile written into a
user's config directory is not, so check it yourself.

**Key names are a closed set.** `input_backend.KEY` is the whole vocabulary. Do
not invent `ctrl+plus` or `cmd+opt+k`; look it up. A chord (`ctrl+k` then `z`)
is a macro with two `hotkey` steps and a wait between them, never one combo.

**Get the window class from the machine, not from memory.**
`installed_apps.list_installed()` reads the system's own records and returns the
authoritative match key for each application: `StartupWMClass` on Linux, the
bundle identifier on macOS.

**Check the shortcuts exist in the application** you are targeting, for the
platform the user is on. VS Code's defaults differ between Linux and macOS by
more than swapping Ctrl for Command. If a command has no default shortcut, drive
it through the application's command palette with a macro rather than inventing
a keybinding the user has not configured.

**Lay it out for a person.** Same action in the same place across workspaces
(scroll on the same knob, views on the same side cells), colour by role, and a
label on every key that has an action. Five well-organised workspaces beat eight
crowded ones.

**Say what you assumed.** Which platform, which application version, which
shortcuts you could not verify. A profile is a set of claims about someone
else's machine; the ones you are unsure of should be the ones they check first.
