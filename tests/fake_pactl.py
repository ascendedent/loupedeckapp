#!/usr/bin/env python3
"""A pactl that answers from a small made-up machine and logs every change,
for tests of the AudioSwitcher stand-in (dotnet/shims/AudioSwitcher.*), so
nothing touches the real audio. State lives in $FAKE_PACTL_STATE (JSON);
changes are appended to $FAKE_PACTL_LOG."""
import json
import os
import sys

STATE = os.environ["FAKE_PACTL_STATE"]
LOG = os.environ.get("FAKE_PACTL_LOG", "")

DEFAULT = {
    "sinks": [
        {"name": "alsa_output.speakers", "description": "Speakers", "volume": 65, "mute": False},
        {"name": "alsa_output.headset", "description": "Headset", "volume": 30, "mute": True},
    ],
    "sources": [
        {"name": "alsa_input.mic", "description": "Microphone", "volume": 80, "mute": False},
        {"name": "alsa_output.speakers.monitor", "description": "Monitor of Speakers", "volume": 100,
         "mute": False, "monitor": "alsa_output.speakers"},
    ],
    "default-sink": "alsa_output.speakers",
    "default-source": "alsa_input.mic",
}


def load():
    try:
        with open(STATE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return json.loads(json.dumps(DEFAULT))


def save(state):
    with open(STATE, "w") as f:
        json.dump(state, f)


def log(*words):
    if LOG:
        with open(LOG, "a") as f:
            f.write(" ".join(words) + "\n")


def find(state, kind, name):
    return next((d for d in state[kind + "s"] if d["name"] == name), None)


def main(args):
    state = load()
    if args[:1] == ["list"] and len(args) > 1:
        kind = args[1]
        title = "Sink" if kind == "sinks" else "Source"
        for i, d in enumerate(state[kind]):
            print("%s #%d" % (title, i + 1))
            print("\tState: SUSPENDED")
            print("\tName: %s" % d["name"])
            print("\tDescription: %s" % d["description"])
            print("\tMute: %s" % ("yes" if d["mute"] else "no"))
            v = int(65536 * d["volume"] / 100)
            print("\tVolume: front-left: %d / %3d%% / 0.00 dB,   front-right: %d / %3d%% / 0.00 dB"
                  % (v, d["volume"], v, d["volume"]))
            print("\t        balance 0.00")
            if kind == "sources":
                print("\tMonitor of Sink: %s" % d.get("monitor", "n/a"))
            print("\tProperties:")
            print("\t\tdevice.description = \"%s\"" % d["description"])
            print()
        return 0
    if len(args) == 1 and args[0] in ("get-default-sink", "get-default-source"):
        print(state[args[0][len("get-"):]])
        return 0
    if len(args) == 2 and args[0].startswith("get-") and args[0].endswith(("-volume", "-mute")):
        _get, kind, what = args[0].split("-")
        d = find(state, kind, args[1])
        if d is None:
            return 1
        if what == "volume":
            v = int(65536 * d["volume"] / 100)
            print("Volume: front-left: %d / %3d%% / 0.00 dB,   front-right: %d / %3d%% / 0.00 dB"
                  % (v, d["volume"], v, d["volume"]))
        else:
            print("Mute: %s" % ("yes" if d["mute"] else "no"))
        return 0
    if len(args) == 3 and args[0].startswith("set-") and args[0].endswith(("-volume", "-mute")):
        _set, kind, what = args[0].split("-")
        d = find(state, kind, args[1])
        if d is None:
            return 1
        if what == "volume":
            d["volume"] = int(args[2].rstrip("%"))
        else:
            d["mute"] = args[2] in ("1", "yes", "true")
        save(state)
        log(*args)
        return 0
    if len(args) == 2 and args[0] in ("set-default-sink", "set-default-source"):
        state[args[0][len("set-"):]] = args[1]
        save(state)
        log(*args)
        return 0
    print("fake pactl: unsupported %r" % (args,), file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
