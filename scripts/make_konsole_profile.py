"""Konsole decks for the commands this machine actually runs.

    .venv/bin/python scripts/make_konsole_profile.py            # into the repo
    .venv/bin/python scripts/make_konsole_profile.py --install  # and into your config

The copy in Profiles/ ships with the app. The paths below are this machine's,
which is what the built-in deck is for.

The GitHub profile is the one Konsole opens with. Its first page is the git
and GitHub commands. Dev, Agents and Projects are separate profiles under the
same application, for the Ops Hub / LOTGEN scripts, the agent CLIs, and the
project directories that show up in the shell history.

Every command is typed into the focused terminal and then Enter is pressed.
Nothing is launched beside Konsole. Commit stops before Enter so the message
can be typed. Paths are absolute, so a key works no matter which directory
the terminal is in.

Assumptions, Linux Konsole on this machine:
- Copy, paste, tabs and clear-scrollback are Konsole's defaults
  (Ctrl+Shift+C, Ctrl+Shift+V, Ctrl+Shift+T, Ctrl+Shift+W, Ctrl+Shift+K).
- "Push merge" is `git push` and then `gh pr merge --merge`. Operations Hub
  promotion does not go that way: `npm run push-main` is the key for that,
  because the plain `gh pr merge` is refused by the repo ruleset.
- "Full stack" is status, then pull, then `npm run push-main`.
- Ops Hub means Github/operations-hub--Main-JM, the checkout the history uses.
- Updates types each tool's own updater. Claude Desktop, Grok Bot and gh are
  Fedora packages, so those keys use dnf and wait for a sudo password.
  Token Meter's updater only fast-forwards a clean checkout of main.
- The CT's A–E keys switch profile on every page: A Projects, B Agents,
  C GitHub, D Dev, E Updates.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app_paths                                                  # noqa: E402
import input_backend                                              # noqa: E402
import macro                                                      # noqa: E402
from LdConfiguration import LdConfiguration, LdAction             # noqa: E402

APP = "Konsole"
MATCH = "konsole"
DEFAULT = "GitHub"

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(REPO, "Profiles", APP)

BLUE, GREEN, AMBER, RED, GREY, PURPLE = (
    "#1e3a8a", "#14532d", "#78350f", "#7f1d1d", "#27272a", "#4c1d95")

HUB = "/home/jm/projects/Github/operations-hub--Main-JM"
LOTGEN = "/home/jm/projects/LOTGEN"
PROJECTS = "/home/jm/projects"


def key(ws, slot, a_type, value, label, color=GREY):
    ws.actions[slot] = LdAction(action_type=a_type, action=value)
    ws.labels[slot] = {"text": label, "pos": "bottom", "mode": "bar"}
    ws.bg_colors[slot] = color


def hotkey(ws, slot, combo, label, color=GREY):
    key(ws, slot, "hotkey", combo, label, color)


def run(ws, slot, command, label, color=GREY):
    """Type a command into the focused terminal and press Enter."""
    key(ws, slot, "macro",
        "text %s\nwait 40\nhotkey return" % command, label, color)


def type_only(ws, slot, command, label, color=GREY):
    """Type a command and leave the cursor there. Enter is the user's."""
    key(ws, slot, "text", command, label, color)


def rotate(ws, control, left, right, press=None):
    ws.actions[control + "-l"] = LdAction(action_type=left[0], action=left[1])
    ws.actions[control + "-r"] = LdAction(action_type=right[0], action=right[1])
    if press:
        ws.actions[control] = LdAction(action_type=press[0], action=press[1])


def chrome(ws, title):
    """The same terminal controls on every page, in the same places.

    Scroll on the left knob, command history on the lower knob, interrupt on
    the dial press. The side cells are Konsole's own tab and clipboard keys.
    """
    rotate(ws, "enc1L", ("scroll", "up"), ("scroll", "down"))
    rotate(ws, "enc2R", ("scroll", "up"), ("scroll", "down"))
    rotate(ws, "enc2L", ("hotkey", "up"), ("hotkey", "down"),
           press=("hotkey", "ctrl+r"))
    rotate(ws, "enc1R", ("hotkey", "up"), ("hotkey", "down"),
           press=("hotkey", "ctrl+c"))
    rotate(ws, "dial", ("scroll", "up"), ("scroll", "down"),
           press=("hotkey", "ctrl+c"))
    rotate(ws, "enc3L", ("hotkey", "ctrl+minus"), ("hotkey", "ctrl+shift+="),
           press=("hotkey", "ctrl+0"))
    rotate(ws, "enc3R", ("hotkey", "ctrl+minus"), ("hotkey", "ctrl+shift+="),
           press=("hotkey", "ctrl+0"))
    hotkey(ws, "dis1L", "ctrl+shift+c", "Copy", BLUE)
    hotkey(ws, "dis2L", "ctrl+shift+v", "Paste", BLUE)
    hotkey(ws, "dis3L", "ctrl+shift+t", "New tab", GREEN)
    hotkey(ws, "dis1R", "ctrl+shift+w", "Close", AMBER)
    hotkey(ws, "dis2R", "ctrl+shift+f", "Find", GREY)
    hotkey(ws, "dis3R", "ctrl+c", "Stop", RED)
    ws.labels["wheel"] = {"text": title, "pos": "middle", "mode": "over"}


def updates(ws):
    """One page of the updaters for the tools used from this machine.

    Each key types that tool's own command into the focused terminal.
    """
    ws.name = "Updates"
    run(ws, "tb11", "sudo dnf upgrade -y claude-desktop-unofficial",
        "Claude app", AMBER)
    run(ws, "tb12", "claude update", "Claude Code", GREEN)
    run(ws, "tb13", "codex update", "Codex", GREEN)
    run(ws, "tb14", "grok update", "Grok", GREEN)
    run(ws, "tb21", "sudo dnf upgrade -y grok-bot", "Grok Bot", AMBER)
    run(ws, "tb22", "paperclipai update", "Paperclip", GREEN)
    run(ws, "tb23",
        "/home/jm/.local/share/token-meter/runtime/scripts/update "
        "/home/jm/.local/share/token-meter/source",
        "Token meter", BLUE)
    run(ws, "tb24", "sudo dnf upgrade -y gh", "gh", AMBER)
    run(ws, "tb31", "npm install -g npm@latest", "npm", GREY)
    run(ws, "tb32", "npm install -g vercel@latest", "Vercel", GREY)
    run(ws, "tb33", "npm install -g bailian-cli@latest", "Bailian", GREY)
    run(ws, "tb34", "flatpak update -y", "Flatpak", AMBER)
    chrome(ws, "Updates")


# The CT's A–E keys. The same five bindings on every page, so leaving a
# profile does not take the way back with it.
PROFILE_KEYS = (
    ("a", "Projects", "#2563eb"),
    ("b", "Agents", "#7c3aed"),
    ("c", "GitHub", "#16a34a"),
    ("d", "Dev", "#d97706"),
    ("e", "Updates", "#78350f"),
)


def stamp_profile_keys(cfg):
    for ws in cfg.workspaces:
        for key, name, color in PROFILE_KEYS:
            ws.actions[key] = LdAction(
                action_type="profile", action=app_paths.make_ref(APP, name),
                summary=name)
            ws.led_colors[key] = color


def leds(ws, colours):
    names = ["circle", "1", "2", "3", "4", "5", "6", "7"]
    for name, colour in zip(names, colours):
        ws.led_colors[name] = colour


def cd(path):
    return "cd %s" % path if " " not in path else "cd '%s'" % path


def build_github():
    cfg = LdConfiguration(profile=app_paths.make_ref(APP, "GitHub"))
    git, branch = cfg.workspaces[:2]

    git.name = "GitHub"
    run(git, "tb11", "git pull", "Pull", BLUE)
    run(git, "tb12", "git push", "Push", GREEN)
    run(git, "tb13", "git push && gh pr merge --merge", "Push merge", AMBER)
    run(git, "tb14", "npm run push-main", "push-main", GREEN)
    run(git, "tb21", "git status && git pull && npm run push-main",
        "Full stack", GREEN)
    run(git, "tb22", "git status", "Status", BLUE)
    run(git, "tb23", "git fetch --prune", "Fetch", BLUE)
    run(git, "tb24", "git diff", "Diff", GREY)
    run(git, "tb31", "git log --oneline -20", "Log", GREY)
    run(git, "tb32", "git add -A", "Stage", BLUE)
    type_only(git, "tb33", 'git commit -m "', "Commit", AMBER)
    run(git, "tb34", "gh pr checks", "PR checks", GREY)
    chrome(git, "GitHub")

    branch.name = "Branch"
    run(branch, "tb11", "git status", "Status", BLUE)
    run(branch, "tb12", "git branch -vv", "Branches", BLUE)
    run(branch, "tb13", "git stash push -u", "Stash", AMBER)
    run(branch, "tb14", "git stash pop", "Stash pop", AMBER)
    run(branch, "tb21", "git checkout -", "Last branch", GREY)
    type_only(branch, "tb22", "git checkout ", "Checkout", GREY)
    run(branch, "tb23", "gh pr status", "PR status", BLUE)
    run(branch, "tb24", "gh pr list", "PR list", BLUE)
    type_only(branch, "tb31", "gh pr checkout ", "PR checkout", GREY)
    run(branch, "tb32", "git fetch origin", "Fetch origin", BLUE)
    run(branch, "tb33", "git log --oneline --graph -20", "Graph", GREY)
    run(branch, "tb34", "npm run git:clean", "git clean", AMBER)
    chrome(branch, "Branch")

    for ws in (git, branch):
        leds(ws, ("#2563eb", "#16a34a"))
    return cfg


def build_dev():
    cfg = LdConfiguration(profile=app_paths.make_ref(APP, "Dev"))
    hub, lot = cfg.workspaces[:2]

    hub.name = "Ops Hub"
    run(hub, "tb11", cd(HUB), "Hub dir", BLUE)
    run(hub, "tb12", "%s && npm run dev" % cd(HUB), "Dev", GREEN)
    run(hub, "tb13", "%s && npm run build" % cd(HUB), "Build", GREY)
    run(hub, "tb14", "%s && npm run lint" % cd(HUB), "Lint", GREY)
    run(hub, "tb21", "%s && npm run test" % cd(HUB), "Test", BLUE)
    run(hub, "tb22", "%s && npm run gates" % cd(HUB), "Gates", AMBER)
    run(hub, "tb23", "%s && npm run git:clean" % cd(HUB), "git clean", AMBER)
    run(hub, "tb24", "%s && npm run tunnel" % cd(HUB), "Tunnel", GREY)
    run(hub, "tb31", "%s && npm run start" % cd(HUB), "Start", GREEN)
    run(hub, "tb32", "%s && npm run push-main" % cd(HUB), "push-main", GREEN)
    run(hub, "tb33", "git status", "Status", BLUE)
    run(hub, "tb34", "git diff", "Diff", GREY)
    chrome(hub, "Ops Hub")

    lot.name = "LOTGEN"
    run(lot, "tb11", cd(LOTGEN), "LOTGEN", BLUE)
    run(lot, "tb12", "%s && pnpm dev" % cd(LOTGEN), "Dev", GREEN)
    run(lot, "tb13", "%s && pnpm dev:up" % cd(LOTGEN), "Stack up", GREEN)
    run(lot, "tb14", "%s && pnpm dev:infra" % cd(LOTGEN), "Infra", BLUE)
    run(lot, "tb21", "%s && pnpm --filter @lotgen/web dev" % cd(LOTGEN),
        "Web", GREEN)
    run(lot, "tb22", "%s && pnpm lint" % cd(LOTGEN), "Lint", GREY)
    run(lot, "tb23", "%s && pnpm typecheck" % cd(LOTGEN), "Types", GREY)
    run(lot, "tb24", "%s && pnpm smoke:drive" % cd(LOTGEN), "Smoke drive", BLUE)
    run(lot, "tb31", "%s && pnpm db:migrate" % cd(LOTGEN), "Migrate", AMBER)
    run(lot, "tb32", "%s && pnpm health" % cd(LOTGEN), "Health", BLUE)
    run(lot, "tb33", "git status", "Status", BLUE)
    run(lot, "tb34", "git diff", "Diff", GREY)
    chrome(lot, "LOTGEN")

    for ws in (hub, lot):
        leds(ws, ("#2563eb", "#d97706"))
    return cfg


def build_agents():
    cfg = LdConfiguration(profile=app_paths.make_ref(APP, "Agents"))
    agents = cfg.workspaces[0]
    agents.name = "Agents"
    run(agents, "tb11", "claude", "Claude", PURPLE)
    run(agents, "tb12", "claude /resume", "Resume", PURPLE)
    run(agents, "tb13", "claude --continue", "Continue", PURPLE)
    run(agents, "tb14", "grok", "Grok", BLUE)
    run(agents, "tb21", "grok /resume", "Grok resume", BLUE)
    run(agents, "tb22", "codex", "Codex", GREEN)
    run(agents, "tb23", "codex remote-control start", "Remote", GREEN)
    hotkey(agents, "tb24", "ctrl+c", "Stop", RED)
    hotkey(agents, "tb31", "ctrl+shift+k", "Clear", GREY)
    run(agents, "tb32", "gh auth switch", "gh auth", AMBER)
    run(agents, "tb33", "gcloud auth login", "gcloud", AMBER)
    run(agents, "tb34", "gcloud config set project lotgen", "lotgen proj", GREY)
    chrome(agents, "Agents")
    leds(agents, ("#7c3aed",))
    return cfg


def build_updates():
    cfg = LdConfiguration(profile=app_paths.make_ref(APP, "Updates"))
    updates(cfg.workspaces[0])
    leds(cfg.workspaces[0], ("#78350f",))
    return cfg


def build_projects():
    cfg = LdConfiguration(profile=app_paths.make_ref(APP, "Projects"))
    jump, term = cfg.workspaces[:2]

    jump.name = "Jump"
    run(jump, "tb11", cd(PROJECTS), "Projects", BLUE)
    run(jump, "tb12", cd(PROJECTS + "/Github"), "Github", BLUE)
    run(jump, "tb13", cd(HUB), "Ops Hub", GREEN)
    run(jump, "tb14", cd(LOTGEN), "LOTGEN", GREEN)
    run(jump, "tb21", cd(PROJECTS + "/Finance Dashboard"), "Finance", GREY)
    run(jump, "tb22", cd(PROJECTS + "/loupedeckapp"), "Loupedeck", GREY)
    run(jump, "tb23", cd(PROJECTS + "/QuestMaster"), "QuestMaster", GREY)
    run(jump, "tb24", cd(PROJECTS + "/Scribe alternative"), "Scribe", GREY)
    run(jump, "tb31", cd(PROJECTS + "/VidSwipe"), "VidSwipe", GREY)
    run(jump, "tb32", "ls", "ls", BLUE)
    run(jump, "tb33", "pwd", "pwd", BLUE)
    hotkey(jump, "tb34", "ctrl+shift+k", "Clear", GREY)
    chrome(jump, "Jump")

    term.name = "Terminal"
    hotkey(term, "tb11", "ctrl+shift+c", "Copy", BLUE)
    hotkey(term, "tb12", "ctrl+shift+v", "Paste", BLUE)
    hotkey(term, "tb13", "ctrl+shift+t", "New tab", GREEN)
    hotkey(term, "tb14", "ctrl+shift+w", "Close tab", AMBER)
    hotkey(term, "tb21", "shift+left", "Prev tab", BLUE)
    hotkey(term, "tb22", "shift+right", "Next tab", BLUE)
    hotkey(term, "tb23", "ctrl+shift+f", "Find", GREY)
    hotkey(term, "tb24", "ctrl+shift+k", "Clear", GREY)
    hotkey(term, "tb31", "ctrl+c", "Stop", RED)
    hotkey(term, "tb32", "ctrl+d", "Exit", AMBER)
    hotkey(term, "tb33", "ctrl+r", "History", GREY)
    hotkey(term, "tb34", "ctrl+l", "Redraw", GREY)
    chrome(term, "Terminal")

    for ws in (jump, term):
        leds(ws, ("#2563eb", "#a1a1aa"))
    return cfg


PROFILES = (
    ("GitHub", build_github),
    ("Dev", build_dev),
    ("Agents", build_agents),
    ("Projects", build_projects),
    ("Updates", build_updates),
)


def validate(cfg):
    """Raise if a binding would be refused when the key is pressed."""
    problems = []
    for ws in cfg.workspaces:
        for slot, action in ws.actions.items():
            if action.a_type == "hotkey":
                try:
                    if not input_backend._parse_combo(action.action):
                        problems.append("%s %s parsed empty" % (slot, action.action))
                except KeyError as e:
                    problems.append("%s hotkey %s (%s)" % (slot, action.action, e))
            elif action.a_type == "macro":
                steps, errors = macro.parse(action.action)
                if errors or not steps:
                    problems.append("%s macro %s" % (slot, errors or "empty"))
                for kind, value in steps:
                    if kind == "hotkey":
                        try:
                            input_backend._parse_combo(value)
                        except KeyError as e:
                            problems.append("%s macro hotkey %s (%s)" % (slot, value, e))
            elif action.a_type == "scroll" and action.action not in (
                    "up", "down", "left", "right"):
                problems.append("%s scroll %s" % (slot, action.action))
    if problems:
        raise SystemExit("invalid profile %s:\n%s" % (
            cfg.profile, "\n".join(problems)))


def write(directory, name, cfg):
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, name + ".json")
    with open(path, "w") as f:
        json.dump(cfg.to_JSON(), f, indent=True, sort_keys=True)
        f.write("\n")
    return path


def write_meta(directory):
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, app_paths.APP_META)
    with open(path, "w") as f:
        json.dump({"match": [MATCH], "default_profile": DEFAULT}, f, indent=True)
        f.write("\n")
    return path


def main():
    built = [(name, fn()) for name, fn in PROFILES]
    for name, cfg in built:
        stamp_profile_keys(cfg)
        validate(cfg)
    targets = [OUT_DIR]
    if "--install" in sys.argv:
        targets.append(app_paths.ensure_user_app_dir(APP))
    for directory in targets:
        write_meta(directory)
        for name, cfg in built:
            path = write(directory, name, cfg)
            print("wrote %s" % path)


if __name__ == "__main__":
    main()
