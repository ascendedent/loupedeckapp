# scripts/verify

Hardware checks that need a device but no test framework. They read and draw;
none of them bind an action or inject input, so nothing they do can reach your
desktop.

Close the main app first: it holds the serial port.

| Script | What it answers |
|---|---|
| `probe_device.py` | What is attached, what the firmware says, what geometry the app picked |
| `capture_events.py` | What each control sends, and which messages the library cannot decode |
| `render_test.py` | Where images actually land on each screen |

`probe_device.py` is also the quickest way to tell a permissions problem from a
missing device: it lists USB serial ports before it tries to enumerate, so a
Loupedeck that shows up as a port but not as a device is a permissions problem.

If you have a Loupedeck Live or Live S, [docs/LIVE-TESTING.md](../../docs/LIVE-TESTING.md)
walks through all three and says what to report.
