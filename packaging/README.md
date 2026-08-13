# packaging

Files for installing the app on a Linux desktop. None of them are needed to run
from a checkout.

| File | Purpose |
|------|---------|
| `99-loupedeck.rules` | udev rule so the device is usable without `sudo` (all three PIDs) |
| `ydotool-user-socket.conf` | systemd drop-in putting the ydotool socket where the app can reach it |
| `loupedeckapp.desktop` | desktop entry, for the app to appear in a launcher |

Each file carries its own install instructions in a comment at the top.

Flatpak and AppImage bundles are not built yet. The obstacle for Flatpak is
input: `ydotool` writes to `/dev/uinput`, which a sandboxed app cannot reach, so
a bundle needs either a host-side daemon or a portal that does not exist. Worth
knowing before starting.
