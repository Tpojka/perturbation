# Perturbation

One Chrome toolbar lamp for every coding agent on your machine, with optional desktop notifications. It answers one question at a glance: **is any agent busy, and how many sessions are occupied?** It works on macOS, Ubuntu/Linux and Windows.

Website: <https://perturbation.tpojka.com>

| Lamp | Meaning |
| --- | --- |
| <img src="extension/icons/lamp-red-48.png" width="24"> **Red, with a number** | Perturbed: at least one agent is working. The badge counts the sessions that are busy |
| <img src="extension/icons/lamp-amber-48.png" width="24"> **Amber, with a number** | Needs you: nothing is working, but a session is waiting for a permission or an answer |
| <img src="extension/icons/lamp-green-48.png" width="24"> **Green** | Unperturbed: every watched agent is free |
| <img src="extension/icons/lamp-grey-48.png" width="24"> **Grey** | The native host isn't connected, or no agent is watched. Run the installer |

Only one lamp is ever lit, and the fill pattern carries the meaning on its own: solid is busy, dotted needs you, a ring is free, dashes are disconnected. Hover for a per-agent summary; click for a list with one lamp per agent, a mute switch each, and rows you can drag into the order you want.

It watches seven agents: four pro-tier ones and three free-tier ones, all listed alike in the installer.

Perturbation subsumes four earlier projects, one per agent: [Claudication](https://github.com/Tpojka/claudication) (Claude Code), [Codexalgia](https://github.com/Tpojka/codexalgia) (Codex CLI), [Copilonidal](https://github.com/Tpojka/copilonidal) (GitHub Copilot CLI) and [Antigravalgia](https://github.com/Tpojka/antigravalgia) (Antigravity CLI). Four hosts, four extensions and four toolbar buttons become one, and the installer removes the old ones for you.

> *perturbation* (n.): in physics and astronomy, a small disturbance of a system by an outside influence, stated without any judgement of whether the disturbance is welcome. That is what this does: it interrupts you, sometimes because an agent genuinely needs you and sometimes not, and takes no position on which.

## The agents

| Agent | Detected by | Where its hooks go | Waiting state | Session end |
| --- | --- | --- | --- | --- |
| Claude Code | `~/.claude` or `claude` on PATH | merged into `~/.claude/settings.json` | permission prompts, questions | yes |
| Codex CLI | `~/.codex` or `codex` on PATH | `~/.codex/hooks.json` | permission requests, after a 5 s grace | yes |
| GitHub Copilot CLI | `~/.copilot` or `copilot` on PATH | `~/.copilot/hooks/perturbation.json` | permission prompts, questions | yes |
| Antigravity CLI | `~/.gemini/antigravity-cli` or `agy` on PATH | one bundle in `~/.gemini/config/hooks.json` | only with its [status line](#antigravitys-status-line-needs-you-alerts) | no, damping only |
| opencode (free tier) | `~/.config/opencode` or `opencode` on PATH | a plugin file, `~/.config/opencode/plugins/perturbation.js` | permission prompts | when opencode exits, or a session is deleted |
| Goose (free tier) | `~/.config/goose` or `goose` on PATH | a plugin directory, `~/.agents/plugins/perturbation/` | none: Goose has no permission event | yes |
| Qwen Code (free tier) | `~/.qwen` or `qwen` on PATH | merged into `~/.qwen/settings.json` | permission prompts and requests | yes |

Each agent is one adapter module with a `TIER`; see [Adding an agent](docs/adding-an-agent.md).

## Install

Requires Python 3.9 or newer and Google Chrome. macOS ships Python as `/usr/bin/python3`; on Windows install it from python.org or with `winget install Python.Python.3.12`.

```sh
./install.sh        # macOS / Ubuntu
install.cmd         # Windows
```

The installer looks for each agent, pre-checks the ones it finds, and asks:

```
Which agents should be watched?
> [x] 1) Claude Code            found ~/.claude
  [x] 2) Codex CLI              found ~/.codex
  [ ] 3) GitHub Copilot CLI     not found
  [x] 4) Antigravity CLI        found ~/.gemini/antigravity-cli
  [x] 5) opencode               found ~/.config/opencode
  [ ] 6) Goose                  not found
  [ ] 7) Qwen Code              not found
Space or 1-7 toggles, ↑/↓ moves, a: all, n: none, Enter confirms:

What should be installed?
  1) Chrome extension
  2) Chrome extension + OS notifier
  3) Nothing (exit)
Choose 1, 2 or 3: 2
Play a sound with notifications? [Y/n]:
Let Antigravity show "needs you" alerts? This sets its status line command. [y/N]:
```

Number keys toggle an agent directly; the arrow keys (or `j`/`k`) move the cursor and **Space** toggles the agent under it. All seven agents are listed the same way, the free-tier ones last. Outside a terminal, in a pipe or a script, the same picker reads whole lines: `2 6` toggles Codex and Goose.

If it finds Claudication, Codexalgia, Copilonidal or Antigravalgia, it lists what they left behind and offers to remove it; see [Coming from the four earlier projects](#coming-from-the-four-earlier-projects).

To skip the prompts, pass the choice and the agents directly:

```sh
python3 -m perturbation.install 2 --agents claude,codex     # with sound
python3 -m perturbation.install 2 --all --no-sound --statusline
python3 -m perturbation.install 1 --migrate                 # the detected agents, and remove the predecessors
python3 -m perturbation.install 2 --agents claude,opencode,goose,qwen
```

Everything is copied into a per-user data directory, so you can move or delete the repository afterwards:

| OS | Data directory |
| --- | --- |
| macOS | `~/Library/Application Support/Perturbation` |
| Ubuntu/Linux | `~/.local/share/perturbation` (or `$XDG_DATA_HOME/perturbation`) |
| Windows | `%LOCALAPPDATA%\Perturbation` |

Then load the extension from that directory (only needed once):

1. Open `chrome://extensions` and turn on **Developer mode**.
2. Click **Load unpacked** and select the `extension` folder inside the data directory. The installer prints the exact path.
3. Pin **Perturbation** to the toolbar.
4. Restart any running agent sessions so they load the hooks.

Per agent, the installer prints how to confirm the registration: `/hooks` inside Claude Code, Codex (where you also have to **trust** the new hooks, or Codex skips them) and Qwen Code, a restart for Copilot, `agy -p "/hooks" --output-format json` for Antigravity, and for opencode and Goose a session file appearing under `sessions/` in the data directory once you start them.

Running the installer again is safe. It updates the installed copy and rewrites its own entries; agents you uncheck lose their hooks, and Codex's hooks are rewritten in place so the trust you gave them survives.

### What it writes

| Agent | File | How |
| --- | --- | --- |
| Claude Code | `~/.claude/settings.json` | merged: your other settings and hooks stay, a `.perturbation.bak` copy is kept, and uninstalling removes only entries whose command names `perturbation.pyz` |
| Codex CLI | `~/.codex/hooks.json` | merged the same way; our hooks keep their position and definition across reinstalls, because Codex remembers trust by both |
| GitHub Copilot CLI | `~/.copilot/hooks/perturbation.json` | a file of its own, so there is nothing to merge; Copilot's agent in VS Code reads it too |
| Antigravity CLI | `~/.gemini/config/hooks.json` | one top-level bundle named `perturbation`, merged by key; the file is shared with the `/hooks` command, the Antigravity 2.0 app and the IDE |
| Antigravity CLI, opt-in | `~/.gemini/antigravity-cli/settings.json` | a `statusLine` block with `stack_with_default`, and never over a status line you already have |
| opencode | `~/.config/opencode/plugins/perturbation.js` | a plugin file of its own, with the interpreter and app paths baked in; it forwards session events to the hook from a detached process and never throws |
| Goose | `~/.agents/plugins/perturbation/` | a plugin directory of its own (`plugin.json` and `hooks/hooks.json`); turn it off without deleting it by listing `perturbation` under `disabledPlugins` in `~/.config/goose/settings.json` |
| Qwen Code | `~/.qwen/settings.json` | merged like Claude's, each entry named `perturbation`; on Windows the entries ask for PowerShell with `"shell": "powershell"` |

Claude Code honours `CLAUDE_CONFIG_DIR`, Codex `CODEX_HOME`, Copilot `COPILOT_HOME` and opencode `OPENCODE_CONFIG_DIR`; on Windows the dot-directories live under `%USERPROFILE%`. Goose runs every hook through `sh -c`, on Windows too, so its command is written for a POSIX shell (Git Bash) with forward slashes. A file that can't be parsed is left byte-identical and reported, and the rest of the install goes ahead.

### Coming from the four earlier projects

The installer finds every trace of Claudication, Codexalgia, Copilonidal and Antigravalgia (their native host manifests, data directories and hook entries), lists them, and removes them only when you say so. Their `notifications` and `sound` settings become the defaults for the questions above. Chrome extensions can't uninstall one another, so it prints the four old extension IDs for you to remove at `chrome://extensions`. Later, or non-interactively:

```sh
python3 -m perturbation.install migrate          # lists, then asks
python3 -m perturbation.install migrate --yes
```

## OS notifier

When the OS notifier is on, an agent that finishes or needs you raises a desktop notification. The title names the agent and the project; the text is the agent's own message when it has one.

| When | Title | Text |
| --- | --- | --- |
| An agent finishes a turn | *Claude* is ready · *project* | the first line of its last message, or "Task finished" |
| An agent needs a permission or an answer | *Codex* needs you · *project* | the prompt, or what it wants to run |
| A turn ends with an error (Claude Code) | *Claude* stopped · *project* | the error type |

Notifications are sent only when a session's stored state actually changes, so a repeated prompt or an idle reminder never adds one. An "is ready" or "stopped" notification also needs the session to have been busy or waiting first. When an agent reports one ending twice, such as opencode's two idle events or Antigravity's Stop hook and status line, you get one notification: hooks for the same agent take turns under a lock. Codex asks for permission before it decides whether to grant it itself, so its "needs you" waits five seconds and is dropped if the session moves on (`PERTURBATION_APPROVAL_GRACE_SECONDS`).

How each OS shows them:

- **macOS:** built-in `osascript`, with the Glass sound. The first time, allow notifications for **Script Editor** in System Settings → Notifications.
- **Ubuntu/Linux:** `notify-send` (`sudo apt install libnotify-bin`), with the freedesktop "complete" sound through `paplay` when available.
- **Windows:** a toast through built-in PowerShell, with the default notification sound. No modules are needed.

### Settings

Change them from the repository, without reinstalling or restarting anything:

```sh
python3 -m perturbation.install set agents claude,codex      # watch exactly these; hooks are added and removed to match
python3 -m perturbation.install set sound off
python3 -m perturbation.install set notifications off
python3 -m perturbation.install set waiting-as-busy on       # fold "needs you" into the red lamp
python3 -m perturbation.install mute codex on                # silence one agent, keep its lamp
python3 -m perturbation.install statusline antigravity on|off
python3 -m perturbation.install status                       # what is installed and what is running
python3 -m perturbation.install doctor                       # per-agent health checks
```

On Windows, use `py -3` instead of `python3`.

The popup does two of these too: the switch on each row mutes that agent, and dragging rows sets the order of the popup and the tooltip. Both are written to `config.json` in the data directory, which you can also edit by hand:

```json
{
  "notifications": true,
  "sound": false,
  "agents": ["claude", "codex", "antigravity"],
  "order": ["claude", "codex", "copilot", "antigravity"],
  "mute": {"codex": true},
  "statusline": {"antigravity": true},
  "count_waiting_as_busy": false
}
```

### Antigravity's status line: "needs you" alerts

Antigravity's hooks never report that the agent is waiting for you. Its **status line** does: whenever the agent state changes, the TUI runs a command of your choosing, pipes it a payload carrying `agent_state` and `tool_confirmation_pending`, and renders what it prints. So the status line is an opt-in precision mode on top of the hooks. It adds one short line under Antigravity's own, telling you only what that line can't know:

```
perturbation · ready · 1 of 2 sessions working
```

It never overwrites a status line you already have: if `statusLine.command` is set to something else, the installer says so and prints the command to set by hand. It only runs while the TUI is drawing, so it does nothing in headless `agy -p` runs; the hooks cover those.

## How it works

```
Claude Code   ──hook────┐
Codex CLI     ──hook────┤
Copilot CLI   ──hook────┤
Antigravity   ──hook────┼──► perturbation.pyz hook <agent> [<event>]
Goose         ──hook────┤              │
Qwen Code     ──hook────┤              ├──► <data>/sessions/<agent>/<session>   (busy | waiting | ready)
opencode      ──plugin──┘              └──► desktop notification (if enabled, and the state changed)
Antigravity   ──status line──► perturbation.pyz statusline antigravity

Chrome ──starts──► perturbation-host ──► perturbation.pyz host
                      watches <data>/sessions/**, pushes a per-agent summary on change
                                  │  native messaging (4-byte length prefix, UTF-8 JSON)
                                  ▼
                   extension: lamp + badge + tooltip, popup on click
```

One hook handler serves every agent: it picks the adapter from the command line, parses the payload, records the session's state, and notifies only on a real transition. One host process watches the whole tree and sends the extension a message like this, agents already in your order:

```json
{"type": "status", "overall": "busy", "busy_sessions": 3, "waiting_sessions": 1,
 "agents": [{"id": "claude", "name": "Claude Code", "watched": true, "state": "busy", "busy": 2, "waiting": 0, "total": 3}, "…"]}
```

### Which events it listens to

**Claude Code** (`hook_event_name` in the payload):

| Event | Matcher | Session becomes | Notification |
| --- | --- | --- | --- |
| `SessionStart` | | ready | |
| `UserPromptSubmit`, `PreToolUse`, `PostToolUse` | `*` on tools | busy | |
| `Notification` | `permission_prompt`, `elicitation_dialog`, `elicitation_url_dialog`, `agent_needs_input` | waiting | needs you |
| `Notification` | `idle_prompt` | ready | none: it only repeats a finished turn |
| `Stop` | | ready | is ready, with the last message |
| `StopFailure` | | ready | stopped, with the error type |
| `PreCompact` | `manual`, `auto` | busy | |
| `PostCompact` | `manual` | ready | is ready |
| `PostCompact` | `auto` | busy | none: the turn carries on |
| `SessionEnd` | | forgotten | |

**Codex CLI** (`hook_event_name`):

| Event | Session becomes | Notification |
| --- | --- | --- |
| `SessionStart` | ready | |
| `UserPromptSubmit`, `PreToolUse`, `PostToolUse` | busy | |
| `PermissionRequest` | waiting, after 5 s untouched | needs you, naming the tool or command |
| `Stop` | ready | is ready, with the last message |
| `Interrupt` | ready | |
| `SessionEnd` | forgotten | |

**GitHub Copilot CLI** (`hook_event_name`; the `notification` event alone sends `sessionId` instead of `session_id`):

| Event | Session becomes | Notification |
| --- | --- | --- |
| `SessionStart` | ready | |
| `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `PostToolUseFailure` | busy | |
| `notification` with `permission_prompt` or `elicitation_dialog` | waiting | needs you, with the message |
| `ErrorOccurred` with `recoverable: false` | ready | stopped, with the error |
| `Stop` | ready | is ready |
| `SessionEnd` | forgotten | |

**Antigravity CLI** (no event name in the payload, so each event registers its own argv token):

| Event | Token | Session becomes | Notification |
| --- | --- | --- | --- |
| `PreInvocation`, `PostInvocation`, `PreToolUse`, `PostToolUse` | `busy` | busy | |
| `Stop` with `fullyIdle: true` | `stop` | ready | is ready |
| `Stop` with `fullyIdle: false` | `stop` | unchanged | |
| status line `tool_confirmation_pending` | | waiting | needs you |
| status line `thinking`, `working`, `tool_use` | | busy | |
| status line `idle` | | ready | is ready, unless the `Stop` hook said so first |
| status line `initializing` | | ready | |

**opencode** (events from the plugin; `sessionID` or `info.id` in the properties; subagent sessions are never counted):

| Event | Session becomes | Notification |
| --- | --- | --- |
| `session.created` | ready | |
| `session.status` `busy` or `retry`, `tool.execute.before`, `tool.execute.after`, `permission.replied` | busy | |
| `permission.updated` or `permission.asked` | waiting | needs you, with the permission's title |
| `session.status` idle, or `session.idle` | ready | is ready, once for the pair |
| `session.error` | ready | stopped, with the error name (none for an abort) |
| `session.deleted`, or opencode shutting down | forgotten | |
| `session.compacted` | unchanged | |

**Goose** (`event` in the payload; `working_dir` arrives only on tool events, so the last one seen is remembered for the "is ready" title):

| Event | Session becomes | Notification |
| --- | --- | --- |
| `SessionStart` | ready | |
| `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `PostToolUseFailure`, `BeforeShellExecution`, `AfterShellExecution`, `BeforeReadFile`, `AfterFileEdit` | busy | |
| `Stop` | ready | is ready, with the last message |
| `SessionEnd` | forgotten | |

Goose has no permission or notification event, so it never turns the lamp amber.

**Qwen Code** (`hook_event_name`, Claude-shaped):

| Event | Matcher | Session becomes | Notification |
| --- | --- | --- | --- |
| `SessionStart` | | ready | |
| `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `PostToolUseFailure` | `*` on tools | busy | |
| `Notification` | `permission_prompt` | waiting | needs you |
| `Notification` | `idle_prompt` | ready | |
| `PermissionRequest` | `*` | waiting | needs you, naming the tool or command |
| `Stop` | | ready | is ready, with the last message |
| `StopFailure` | | ready | stopped, with the error |
| `PreCompact` / `PostCompact` | `manual`, `auto` | busy / ready (manual) or busy (auto) | is ready after a manual one |
| `SessionEnd` | | forgotten | |

### Damping

Not every agent signals an interrupt, a crash or a closed terminal, so the state settles on its own:

| Rule | Default | Override |
| --- | --- | --- |
| A busy session with no activity counts as ready after | 15 minutes | `PERTURBATION_BUSY_STALE_SECONDS` |
| A waiting session with no activity counts as ready after | 60 minutes | `PERTURBATION_WAITING_STALE_SECONDS` |
| A session with no activity at all is forgotten after | 24 hours | |

Antigravity has no session-end event, so its sessions rely on these entirely. opencode keeps its sessions on disk, so its plugin forgets them when opencode shuts down; a session that ends any other way is damped like Antigravity's.

### Never in the way

Every hook command is hardened: `python3 '…/perturbation.pyz' hook <agent> || true` on macOS and Linux, `& '<python>' '…\perturbation.pyz' hook <agent>; exit 0` in PowerShell. It prints nothing and exits 0 even when Python or the app is missing. This is not decoration: Copilot denies a tool call when a `preToolUse` hook exits non-zero, Claude's and Qwen's `PreCompact` exit 2 blocks compaction, Qwen adds whatever a hook prints on exit 0 to the model's context, Goose reads a `Stop` hook's stdout as a decision that can keep the turn going, and Antigravity parses a hook's stdout as a decision (`allow`, `deny`, `force_ask`) with undocumented exit codes. The opencode plugin wraps everything in try/catch, spawns the hook detached and never awaits it. The status line likewise never prints an error, because its stdout *is* the status line. Payloads are read as UTF-8 bytes, because Windows would decode text stdin with the ANSI code page and corrupt non-ASCII project names.

The extension's `key` in `extension/manifest.json` fixes its ID to `jbibmafopagpblieglanmabkegglkpgo`, the only extension the native host accepts. The open native-messaging port keeps the service worker alive; a half-minute alarm reconnects after a crash, and the popup answers from the worker's cached status, so it never waits on the host.

## Project layout

```
perturbation/            Python package (standard library only)
  cli.py                 entry point of the installed perturbation.pyz: hook | statusline | host
  hook.py                the one hook handler: adapter, parse, record, notify on change
  statusline.py          status line handler for agents that have one
  host.py                Chrome native messaging host, one for every agent
  state.py               per-agent, per-session files, atomic writes, damping
  notify.py              desktop notifications per OS
  config.py, paths.py    installed settings and locations
  agents/                one adapter module per agent, and the contract they follow
    base.py              the contract: Update, Notice, Check, helpers
    jsonfile.py          careful edits to files that belong to an agent
    claude.py  codex.py  copilot.py  antigravity.py     pro tier
    opencode.py  goose.py  qwen.py                      free tier
    assets/opencode-plugin.js                           the one piece of JavaScript: opencode's plugin
  install/               installer, agent picker, migration, doctor, OS specifics
extension/               Chrome extension (Manifest V3): lamp, badge, tooltip, popup
site/                    landing page for perturbation.tpojka.com
docs/                    the project brief and the adapter guide
tests/                   unittest suite
```

## Development

```sh
python3 -m unittest -v
```

The tests are self-contained: every test uses a temporary home and data directory (with a space and a quote in its name), so your real install and your agents' real config files aren't touched. They run the generated hook commands through `sh`, `bash` and PowerShell with real payloads, with the app present and deleted. CI runs them on macOS, Ubuntu and Windows with Python 3.9 and the latest Python 3.

To use a data directory other than the default, set `PERTURBATION_HOME`.

The extension has no unit tests. Before a release, check by hand that the badge count matches the tooltip, that the lamp goes grey when the host is killed, that the popup opens instantly after a cold start, and that the lamp survives a Chrome restart.

## Uninstall

```sh
./uninstall.sh      # macOS / Ubuntu
uninstall.cmd       # Windows
```

This removes every hook entry it wrote, Antigravity's status line if it is still ours, the native host registration and the data directory. Your other hooks and settings stay. Then remove the extension from `chrome://extensions`.

See [CHANGELOG.md](CHANGELOG.md) for release history.

## License

[MIT](LICENSE) © 2026 Goran Grbic. An independent project, not affiliated with Anthropic, OpenAI, GitHub or Google.
