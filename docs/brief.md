# Brief: Perturbation — one Chrome button for every coding agent

Written on 2026-09-20 in a Claude Code session in `~/GitHub/Tpojka/copilonidal`.

**Name: `perturbation`** — decided 2026-09-20, see [Name](#name).

This supersedes `polyalgia-brief.md`, which is the same idea with four agents and body-part icons. Two things changed: the agent list grew to **seven**, and the toolbar icon became a single lamp in traffic-light colours — red, amber, green, grey — with the red one carrying the number of occupied sessions. `polyalgia-brief.md` is kept only for history; this document is complete on its own.

It subsumes four shipped projects: `~/GitHub/Tpojka/claudication` (2.1.0), `codexalgia` (1.0.0), `copilonidal` (1.0.0) and `antigravalgia` (in progress, brief at `~/GitHub/Tpojka/antigravalgia/docs/brief.md`).

## Goal

One repository, one installer, one Chrome toolbar button that answers a single question at a glance: **is any coding agent on this machine busy, and how many sessions are occupied?**

- **Green** — every watched agent is free.
- **Red, with a number** — at least one agent is working; the badge counts occupied sessions.
- **Grey** — the native host isn't connected, or nothing is being watched.
- Hover for a per-agent text summary; click for a list with one lamp per agent.
- The installer asks which agents to watch and pre-checks the ones it finds.
- Optional desktop notifications, with the agent named in the title.
- macOS, Ubuntu/Linux and Windows, Python 3.9+ standard library only.

## The seven agents

| Agent | Repository | Stars | Mechanism | Adapter shape | Confidence |
|---|---|---|---|---|---|
| Claude Code | (closed) | — | hooks in `~/.claude/settings.json` | config entry | **verified**, shipped as Claudication |
| Codex CLI | (closed) | — | `~/.codex/hooks.json` | config entry | **verified**, shipped as Codexalgia |
| GitHub Copilot CLI | (closed) | — | `~/.copilot/hooks/*.json` | config entry | **verified**, shipped as Copilonidal |
| Antigravity CLI | `google-antigravity/antigravity-cli` | 2.3k | `~/.gemini/config/hooks.json` + status line | config entry | **verified from docs**, not yet built |
| **opencode** | `anomalyco/opencode` | **209k** | JS/TS plugin, event bus | **plugin file** | events verified, payload shape unverified |
| **Goose** | `aaif-goose/goose` | 54k | `~/.agents/plugins/<name>/hooks/hooks.json` | config entry | event enum verified from source, payload unverified |
| **Qwen Code** | `QwenLM/qwen-code` | 28k | `packages/core/src/hooks/`, `docs/users/features/hooks.md` | config entry | **unverified — read the source first** |

Deliberately excluded: **Ollama** (a model server, not an agent — no sessions, no turns, and "busy" there would double-count the agents above), **Crush** (`charmbracelet/crush`, 28k — hooks exist but only `PreToolUse` today, so there is no way to know when work ends; revisit when they ship `Stop`), **Aider** (49k but slowing; no hooks, only `--notifications-command`, which gives a ready signal and never a busy one).

## Architecture

```
Claude Code   ──hook────┐
Codex CLI     ──hook────┤
Copilot CLI   ──hook────┤
Antigravity   ──hook────┼──► perturbation.pyz hook <agent> [<event>]
Goose         ──hook────┤              │
Qwen Code     ──hook────┤              ├──► <data>/sessions/<agent>/<session>   (busy|waiting|ready)
opencode      ──plugin──┘              └──► desktop notification (if enabled)
Antigravity   ──statusline──► perturbation.pyz statusline

Chrome ──starts──► perturbation-host ──► perturbation.pyz host
                      watches <data>/sessions/**, pushes a per-agent summary on change
                                  │  native messaging (4-byte length prefix, UTF-8 JSON)
                                  ▼
                   extension: lamp icon + badge + tooltip, popup on click
```

| Layer | Detail |
|---|---|
| State | `<data>/sessions/<agent_id>/<session_id>`, one file holding `busy`, `waiting` or `ready` |
| Host | **one** process, started by Chrome, watching the whole tree |
| Extension | **one** ID, one button, one popup |
| Agent differences | one adapter module each; nothing agent-specific anywhere else |

### Repository layout

```
perturbation/
  __init__.py          HOST_NAME, EXTENSION_ID, __version__
  cli.py               entry point of perturbation.pyz: hook | statusline | host
  hook.py              generic handler: pick adapter, parse, write state, notify
  statusline.py        Antigravity status line handler
  host.py              watches the sessions tree, speaks native messaging
  state.py             per-agent, per-session state, atomic writes, staleness
  notify.py            osascript / notify-send / PowerShell toast
  config.py            config.json
  paths.py             data directory, icons, sessions tree
  agents/
    __init__.py        ordered registry, lookup by id
    claude.py  codex.py  copilot.py  antigravity.py  goose.py  qwen.py  opencode.py
    assets/
      opencode-plugin.js   the JS shim copied into opencode's plugin directory
  install/
    __init__.py  __main__.py  system.py  migrate.py
extension/
  manifest.json  background.js  popup.html  popup.js  popup.css
  icons/  lamp-red-{16,32,48,128}.png  lamp-green-*  lamp-grey-*  lamp-amber-*  (+ .svg sources)
site/
tests/
```

## Adapter contract

Every agent is one module in `agents/`. Nothing else in the codebase knows an agent exists.

```python
ID       = "opencode"                # directory under sessions/, argv token
NAME     = "opencode"                # shown in the popup
SHORT    = "opencode"                # used in notification titles
SHAPE    = "plugin"                  # "config" | "plugin"
ORDER    = 5                         # default position in the popup

def detect() -> bool:
    """True when this agent looks installed: its config directory exists, or its binary is on PATH."""

def per_event_commands() -> bool:
    """True when the payload carries no event name, so each event needs its own argv token."""

def install(command_for) -> None:
    """Write this agent's hook configuration, or its plugin file.
    command_for(event=None) returns the OS-specific shell command, already hardened to exit 0."""

def uninstall() -> None:
    """Remove only what install() wrote."""

def verify() -> str | None:
    """A shell command the installer prints so the user can confirm registration."""

def parse(event_arg: str | None, payload: dict) -> Update | None:
    """Return Update(session_id, state, notification), or None to ignore this event."""
```

```python
Update = namedtuple("Update", "session_id state notification")
# state: state.BUSY | state.WAITING | state.READY | None   (None removes the session)
# notification: (title, message, level) or None
```

`hook.py` stays agent-agnostic:

```
argv -> agents.get(id) -> read stdin as BYTES -> json.loads -> adapter.parse()
     -> state.set/clear -> notify only when the stored state actually changed
     -> exit 0, always, printing nothing
```

Reading stdin as bytes is not optional: Windows decodes text stdin with the ANSI code page, which corrupts non-ASCII project paths.

## Per-agent specifications

### 1. Claude Code — `claude`

| | |
|---|---|
| Detect | `~/.claude` exists, or `claude` on PATH |
| Config | `~/.claude/settings.json`, `hooks` object, nested `{matcher, hooks:[{type, command, timeout}]}` groups |
| Install | Merge: back up to `settings.json.perturbation.bak`, strip entries whose command contains the marker, append ours |
| Timeout | seconds |
| Event name | `hook_event_name` in the payload |
| Session / project | `session_id` / `cwd` |

| Event | Matcher | State | Notification |
|---|---|---|---|
| `SessionStart` | — | ready | — |
| `UserPromptSubmit` | — | busy | — |
| `PreToolUse`, `PostToolUse` | `*` | busy | — |
| `Notification` | `permission_prompt\|idle_prompt\|elicitation_dialog` | waiting | "needs you", except `idle_prompt` |
| `Stop` | — | ready | "is ready" |
| `StopFailure` | — | ready | "stopped with an error" |
| `PreCompact` | `manual\|auto` | busy | — |
| `PostCompact` | `manual\|auto` | ready | "is ready" |
| `SessionEnd` | — | remove | — |

`PreCompact`/`PostCompact` and `StopFailure` are new versus Claudication 2.1.0. Without them a manual `/compact` runs for minutes with the icon still green, and a turn killed by an API error stays red until the stale rule fires. **`PreCompact` exit 2 blocks compaction**, so these may only be added with the hardened command below.

### 2. Codex CLI — `codex`

| | |
|---|---|
| Detect | `~/.codex` exists (honour `CODEX_HOME`), or `codex` on PATH |
| Config | `~/.codex/hooks.json`, own file |
| **Trust** | Codex runs a hook only after the user trusts it with `/hooks`, and remembers trust by the hook's **position in the file plus a hash of its definition**. A reinstall must rewrite each hook in place, with an identical command and timeout, or trust is silently lost |
| Timeout | 1 s default; **`SessionEnd` and `Interrupt` accept at most 3 s**; use 5 s elsewhere |
| Blocked | `[features] hooks = false` in `~/.codex/config.toml` disables everything — detect and warn |
| Verify | `/hooks` inside Codex |

| Event | State | Notification |
|---|---|---|
| `SessionStart` | ready | — |
| `UserPromptSubmit`, `PreToolUse`, `PostToolUse` | busy | — |
| `PermissionRequest` | waiting | "needs you" |
| `Stop` | ready | "is ready" |
| `Interrupt` | ready | — |
| `SessionEnd` | remove | — |

### 3. GitHub Copilot CLI — `copilot`

| | |
|---|---|
| Detect | `~/.copilot` exists (honour `COPILOT_HOME`), or `copilot` on PATH |
| Config | `~/.copilot/hooks/perturbation.json`, own file, `{"version": 1, "hooks": {…}}`, flat entry arrays |
| Entry | `{"type":"command","bash":…,"powershell":…,"timeoutSec":5}`, plus `matcher` on `notification` |
| **Danger** | `preToolUse` is **fail-closed**: a non-zero exit denies the tool call |
| Payload | PascalCase event names give `hook_event_name` + `session_id`; `notification` exists only in camelCase and gives `sessionId`. Read both |
| Bonus | The same file drives Copilot's agent in VS Code — without `Notification` or `SessionEnd` there |

| Event | State | Notification |
|---|---|---|
| `SessionStart` | ready | — |
| `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `PostToolUseFailure` | busy | — |
| `notification` (`permission_prompt\|elicitation_dialog`) | waiting | "needs you", using the payload `message` |
| `ErrorOccurred` with `recoverable: false` | ready | — |
| `Stop` | ready | "is ready" |
| `SessionEnd` | remove | — |

### 4. Antigravity CLI — `antigravity`

| | |
|---|---|
| Detect | `~/.gemini/antigravity-cli` exists, or `agy` on PATH |
| Config | `~/.gemini/config/hooks.json`, **own top-level bundle key**; merge by key, back up, never rewrite the file (it is shared with the Antigravity 2.0 GUI) |
| Events | only `PreToolUse`, `PostToolUse`, `PreInvocation`, `PostInvocation`, `Stop` |
| Payload | `conversationId`, `workspacePaths[]`, `transcriptPath`, `artifactDirectoryPath`, `modelName` — **no event name, no `cwd`**, so `per_event_commands()` is `True` |
| Timeout | seconds, default 30; write 5 |
| **Danger** | stdout is parsed as a **decision** (`deny`/`allow`/`force_ask` on `PreToolUse`, `continue` on `Stop`). Print nothing. Exit-code semantics are undocumented |
| Verify | `agy -p "/hooks" --output-format json` |

| Event | State | Notification |
|---|---|---|
| `PreInvocation`, `PostInvocation`, `PreToolUse`, `PostToolUse` (matcher `.*`) | busy | — |
| `Stop` with `fullyIdle: true` | ready | "is ready" |
| `Stop` with `fullyIdle: false` | unchanged | — |

**Status line mode (opt-in).** Antigravity's TUI runs a command *whenever the agent state changes*, piping it JSON with `session_id`, `conversation_id`, `cwd`, `agent_state` (`idle`, `thinking`, `working`, `tool_use`, `initializing`) and **`tool_confirmation_pending`** — the only route to a waiting state for this agent.

- Configure `statusLine` in `~/.gemini/antigravity-cli/settings.json`: `{"type":"command","command":"… statusline","enabled":true,"stack_with_default":true}`.
- Offer it only when `statusLine.command` is unset; never overwrite a custom status line.
- The script's stdout *is* the status line: print one short line, always exit 0, notify only on a real transition.

### 5. opencode — `opencode`

The largest agent on the list by far, and the only one that is not a shell-hook system.

| | |
|---|---|
| Detect | `~/.config/opencode` exists, or `opencode` on PATH |
| Config | a **JS/TS plugin file**: `~/.config/opencode/plugins/perturbation.js` (global) or `.opencode/plugins/` (project) |
| Runtime | opencode's own JS runtime. The plugin must spawn the hook command detached, ignore its output, and swallow every error |
| Verify | start opencode and confirm a session file appears under `<data>/sessions/opencode/` |

Events on opencode's bus (verified names):

| Event | State | Notification |
|---|---|---|
| `session.created` | ready | — |
| `tool.execute.before`, `tool.execute.after`, `message.updated` | busy | — |
| `permission.asked` | waiting | "needs you" |
| `permission.replied` | busy | — |
| `session.idle` | ready | "is ready" |
| `session.error` | ready | "stopped with an error" |
| `session.deleted` | remove | — |
| `session.compacted` | unchanged | — (it closes the compaction gap the other agents have) |

Also available and unused for now: `session.status`, `session.updated`, `session.diff`, `file.edited`, `file.watcher.updated`, `todo.updated`, `command.executed`, `lsp.*`, `tui.*`, `experimental.session.compacting`.

**The shim** (`agents/assets/opencode-plugin.js`, ~20 lines) is the only JavaScript in the project. It must:

1. subscribe to the events above,
2. spawn `<python> <data>/perturbation.pyz hook opencode <event>` with the event JSON on stdin,
3. detach, ignore stdout and stderr, and never throw — a plugin exception must not disturb opencode,
4. carry the interpreter and app paths the installer wrote into it (no lookups at runtime).

**Unverified, resolve first:** the exact event payload shape (where the session id lives — likely `event.properties.sessionID`), whether the plugin API is `export const Plugin = async ({ client, $ }) => ({ event: async ({ event }) => {} })` in the current release, and which spawn primitive is available. Discovery procedure: install a plugin that appends `JSON.stringify(event)` to a log file, run one session with a permission prompt, then read the log and fill in this table.

### 6. Goose — `goose`

| | |
|---|---|
| Detect | `~/.config/goose` or `~/.agents/plugins` exists, or `goose` on PATH |
| Config | a plugin directory: `~/.agents/plugins/perturbation/hooks/hooks.json` |
| Disable | `{"disabledPlugins": ["perturbation"]}` in Goose's config turns it off without deleting it |
| Verify | `goose session`, then confirm a session file appears |

Event enum, read from `crates/goose/src/hooks/mod.rs`: `PreToolUse`, `PreToolUseResult`, `PostToolUse`, `PostToolUseFailure`, `SessionStart`, `SessionEnd`, `UserPromptSubmit`, `BeforeReadFile`, `AfterFileEdit`, `BeforeShellExecution`, `AfterShellExecution`, `Stop`.

| Event | State | Notification |
|---|---|---|
| `SessionStart` | ready | — |
| `UserPromptSubmit` | busy | — |
| `PreToolUse`, `PostToolUse`, `PostToolUseFailure`, `BeforeShellExecution`, `AfterShellExecution` | busy | — |
| `Stop` | ready | "is ready" |
| `SessionEnd` | remove | — |

No permission or notification event exists, so **Goose has no waiting state**. Say so in the README.

**Unverified:** the payload shape and the `hooks.json` schema. The repository ships `examples/plugins/hello-hooks`, which logs every payload to `last-event.log` — copy it, run one session, read the log, then fill in this table.

### 7. Qwen Code — `qwen`

**Nothing here is verified.** Qwen Code is a fork of Gemini CLI, so its hooks are probably Gemini-shaped (`SessionStart`, `BeforeAgent`, `AfterAgent`, `BeforeTool`, `AfterTool`, `Notification`, `PreCompress`, `SessionEnd`), with `timeout` in **milliseconds** and a nested `{matcher, hooks:[…]}` schema in a `settings.json`. The config directory is most likely `~/.qwen/`.

Before writing the adapter, read, in this order:

1. `docs/users/features/hooks.md` in `QwenLM/qwen-code`
2. `packages/core/src/hooks/types.ts` for the authoritative event enum
3. `docs/design/session-source-lifecycle-hooks.md` and `docs/design/hook-process-tree-cancellation.md`, which suggest the lifecycle events have been reworked since the fork

Then fill in the same table as the others. If the events turn out to be Gemini's, note that Gemini's exit-code semantics are hostile: exit 2 on `AfterAgent` **forces a retry** using stderr as the new prompt, which is worse than a plain block.

## State layer

| Rule | Value |
|---|---|
| Path | `<data>/sessions/<agent_id>/<session_id>`, id sanitised to `[A-Za-z0-9-_]`, empty falls back to `default` |
| Write | temp file then `os.replace` — atomic, so the host never reads a half-written file |
| States | `busy`, `waiting`, `ready` |
| Busy staleness | 15 minutes without activity counts as ready (`PERTURBATION_BUSY_STALE_SECONDS`) |
| Waiting staleness | a short grace period, because approval may be granted automatically |
| Session staleness | ignored after 24 hours, for sessions that ended without an end event |
| Per agent | `summary(agent)` → `{state, busy, waiting, total}` |
| Overall | busy if any agent is busy; else waiting if any is waiting; else ready |

Agents with no end event (Antigravity, and opencode if `session.deleted` proves unreliable) depend entirely on staleness. Document that in the README.

## The lamp

### Toolbar icon

| Condition | Icon | Badge |
|---|---|---|
| Any session busy | **red** | **the number of occupied sessions**, across every watched agent |
| No session busy, at least one waiting | **amber** | the number of waiting sessions |
| Everything free | **green** | none |
| Host not connected, or no agents watched | **grey** | none |

- "Occupied" means sessions in the `busy` state. `waiting` sessions are counted separately and shown on the amber lamp. A config flag `count_waiting_as_busy` (default `false`) folds them together for anyone who prefers two states.
- The badge is capped: more than 99 shows `99+`.
- Badge colours: near-black background `#202124` with white text, which stays legible on the red lamp and on both light and dark toolbars. Use `chrome.action.setBadgeBackgroundColor` and `setBadgeTextColor`.
- Amber is a judgement call: it is the natural third lamp, but if the waiting state proves noisy, drop it and let waiting sessions count as busy. Decide before drawing the icons.

### Drawing the icons

Four families × four sizes (16, 32, 48, 128), from SVG sources.

**One lamp at a time — never the three-lamp housing.** The icon is a single disc filling the canvas, in the colour of the current state. Traffic-light colours are the metaphor, not the device: only one light is ever lit, so only one light is ever drawn. This is also the only thing that reads at 16 px, which is the size the toolbar actually uses.

| Element | Spec |
|---|---|
| Shape | one circle, ~82% of the canvas, centred, with a 1 px (at 16) to 6 px (at 128) outline in `#202124` at 35% opacity so the disc holds its edge on both light and dark toolbars |
| Red | solid disc `#d93025` |
| Amber | disc `#f9ab00` with a dark centre dot at ~30% diameter |
| Green | **ring**: `#1e8e3e` stroke at ~24% of the diameter, hollow centre |
| Grey | flat `#9aa0a6` ring, dashed, no fill |
| Never | gradients, inner shadows, or a housing — they turn to mud at 16 px |

**Colour-blind safety carries the whole design here**, because this project is nothing but red and green and there is no lamp position to fall back on:

- The fill pattern is the real signal: **solid** = busy, **hollow ring** = free, **dotted** = needs you, **dashed** = disconnected. Someone who sees no colour at all still reads the icon correctly.
- The badge appears only on red and amber, which is a second independent cue.
- Check the set in greyscale before shipping. If solid-versus-ring isn't obvious at 16 px in greyscale, thicken the ring rather than changing the colours.

The body-part icons from the four predecessors (knee, hip, tailbone, lower back) do not appear on the toolbar any more. Keep them, optionally, as small avatars in the popup rows — it is a nice nod to where the project came from, and it makes rows scannable. That is a decision, not a requirement.

### Hover

`chrome.action.setTitle` renders multi-line text (the shipped extensions already rely on this). Images are not possible in a tooltip.

```
Perturbation — 3 sessions working
● Claude Code — working, 2 of 3 sessions
● opencode — working, 1 session
◐ Codex CLI — needs you
○ Goose — ready
· Copilot CLI — not installed
```

### Click

`popup.html`, one row per agent: lamp, name, state text, session count, and a switch that mutes notifications for that agent. Rows are draggable to set priority. The footer shows the host connection state and the version.

**Chrome cannot open a popup on hover.** The action popup opens on click only; hover gives the tooltip above. That is the whole of the interaction model.

The service worker caches the last status in a module variable and in `chrome.storage.session`, and the popup asks for it with `chrome.runtime.sendMessage({type:"get"})`, so opening the popup never waits on the host. **Keep the half-minute reconnect alarm** — the open native-messaging port is what keeps an MV3 service worker alive.

## Host → extension message

Sent on connect and on every change. Agents arrive in priority order, so the extension never sorts.

```json
{
  "type": "status",
  "version": "1.0.0",
  "overall": "busy",
  "busy_sessions": 3,
  "waiting_sessions": 1,
  "agents": [
    { "id": "claude",      "name": "Claude Code",        "short": "Claude",      "installed": true,  "state": "busy",    "busy": 2, "waiting": 0, "total": 3 },
    { "id": "opencode",    "name": "opencode",           "short": "opencode",    "installed": true,  "state": "busy",    "busy": 1, "waiting": 0, "total": 1 },
    { "id": "codex",       "name": "Codex CLI",          "short": "Codex",       "installed": true,  "state": "waiting", "busy": 0, "waiting": 1, "total": 1 },
    { "id": "goose",       "name": "Goose",              "short": "Goose",       "installed": true,  "state": "ready",   "busy": 0, "waiting": 0, "total": 1 },
    { "id": "copilot",     "name": "GitHub Copilot CLI", "short": "Copilot",     "installed": false, "state": "ready",   "busy": 0, "waiting": 0, "total": 0 },
    { "id": "antigravity", "name": "Antigravity CLI",    "short": "Antigravity", "installed": false, "state": "ready",   "busy": 0, "waiting": 0, "total": 0 },
    { "id": "qwen",        "name": "Qwen Code",          "short": "Qwen",        "installed": false, "state": "ready",   "busy": 0, "waiting": 0, "total": 0 }
  ]
}
```

`busy_sessions` is what the badge shows, so the extension needs no arithmetic.

## Installer

```
Which agents should be watched?
  [x] 1) Claude Code          found ~/.claude
  [x] 2) Codex CLI            found ~/.codex
  [ ] 3) GitHub Copilot CLI   not found
  [ ] 4) Antigravity CLI      not found
  [x] 5) opencode             found ~/.config/opencode
  [x] 6) Goose                found goose on PATH
  [ ] 7) Qwen Code            not found
Toggle with 1-7, Enter to confirm:

What should be installed?
  1) Chrome extension
  2) Chrome extension + OS notifier
  3) Nothing (exit)
Choose 1, 2 or 3: 2
Play a sound with notifications? [Y/n]:
Let Antigravity show "needs you" alerts? This sets its status line command. [y/N]:
```

- Pre-check whatever `detect()` finds; let the user override either way.
- Non-interactive: `python3 -m perturbation.install 2 --agents claude,codex,opencode,goose --no-sound`.
- Copy everything into the per-user data directory, so the repository can be moved or deleted afterwards.
- Register **one** native host manifest naming the one extension ID.
- Per selected agent, print the file written and the `verify()` command.
- Then: load unpacked, pin, restart running agent sessions.

Data directory: `~/Library/Application Support/Perturbation`, `~/.local/share/perturbation` (or `$XDG_DATA_HOME`), `%LOCALAPPDATA%\Perturbation`. Override with `PERTURBATION_HOME`.

Later, without reinstalling:

```sh
python3 -m perturbation.install set agents claude,codex,opencode
python3 -m perturbation.install set sound off
python3 -m perturbation.install set notifications off
python3 -m perturbation.install status
python3 -m perturbation.install doctor
```

`doctor` earns its place with seven agents: for each one, confirm the config file exists and holds our entry, the command in it points at the installed `.pyz`, the interpreter runs, and the agent-specific traps are clear — Codex hooks not disabled in `config.toml` and the hook still trusted, opencode's plugin file present and parsable, Antigravity's bundle key intact.

### `config.json`

```json
{
  "notifications": true,
  "sound": false,
  "agents": ["claude", "codex", "opencode", "goose"],
  "order": ["claude", "opencode", "codex", "goose", "copilot", "antigravity", "qwen"],
  "mute": { "codex": true },
  "statusline": { "antigravity": false },
  "count_waiting_as_busy": false
}
```

### The hook command

One shape for every config-entry agent, hardened so a missing interpreter or a deleted app can never hurt the agent:

| OS | Command |
|---|---|
| macOS / Linux | `python3 '<data>/perturbation.pyz' hook <agent> \|\| true` |
| Windows | `& '<python>' '<data>\perturbation.pyz' hook <agent>; exit 0` |

This is not defensive decoration. Copilot denies a tool call when a `preToolUse` hook exits non-zero; Claude's `PreCompact` exit 2 blocks compaction; Antigravity's exit codes are undocumented and its `PreToolUse` gates execution; Gemini-shaped hooks (possibly Qwen's) turn exit 2 on the end-of-turn event into a forced retry. Python exits 2 when it cannot find the app.

### Migration from the four shipped projects

| Step | Action |
|---|---|
| 1 | Find predecessors: host manifests for `com.tpojka.{claudication,codexalgia,copilonidal,antigravalgia}`, their data directories, and hook entries whose command names `claudication.pyz`, `codexalgia.pyz`, `copilonidal.pyz` or `antigravalgia.pyz` |
| 2 | List everything found and ask before touching anything |
| 3 | Remove those hook entries, host manifests and data directories |
| 4 | Print the old extension IDs and tell the user to remove them at `chrome://extensions` — one extension cannot uninstall another |
| 5 | Carry over `notifications` and `sound` from whichever predecessor config is found |

## Notifications

| When | Title | Text |
|---|---|---|
| An agent finishes a turn | `{Short} is ready · {project}` | `Task finished` |
| An agent needs permission or an answer | `{Short} needs you · {project}` | the agent's own message, when it provides one |
| A turn ends with an error | `{Short} stopped · {project}` | the error type |

Notify only when the stored state actually changes; never for idle reminders that merely repeat a finished turn; honour the per-agent `mute` list. The project name comes from `cwd`, then `workspacePaths[0]`, then the process working directory.

## Hazards

| Hazard | Where | Handling |
|---|---|---|
| A failing hook blocks the agent | Copilot `preToolUse`; Claude `PreCompact`; Antigravity; possibly Qwen | The hardened command above, plus the shell-level test below |
| stdout is interpreted | Antigravity parses it as a decision; others display it | Print nothing, ever |
| A plugin exception disturbs the agent | opencode | Wrap the whole shim in try/catch, spawn detached, never await |
| Trust is position-sensitive | Codex | Rewrite hooks in place, same command, same timeout |
| Shared config files | `~/.claude/settings.json`, `~/.gemini/config/hooks.json` | Merge, back up, remove only entries carrying the marker |
| Timeout units differ | seconds (Claude, Codex, Antigravity, Goose?) vs `timeoutSec` (Copilot) vs milliseconds (Qwen?) | Each adapter owns its unit; never share a constant |
| Non-ASCII paths on Windows | all | Read stdin as bytes, decode UTF-8 |
| Blast radius | one codebase, seven agents | The full test matrix runs per adapter |
| Single host process | if it dies, everything goes grey | Keep the reconnect alarm; `doctor` reports it |

## Test matrix

| Test | Scope |
|---|---|
| Hook command runs in `sh`, `bash` and `powershell.exe`, exits 0, prints nothing, writes `busy` | per config adapter |
| Same with the `.pyz` deleted — still exit 0 | per config adapter |
| Install then uninstall leaves every foreign hook byte-identical | per adapter |
| Reinstall is idempotent; Codex keeps hook positions and hashes | codex |
| The opencode shim parses under `node --check` and survives a malformed event | opencode |
| Payload parsing, including non-ASCII project names | per adapter |
| Antigravity status line prints exactly one line and exits 0 on garbage input | antigravity |
| State: busy staleness, waiting grace, 24-hour staleness, atomic writes | shared |
| Aggregation across agents, including one with no sessions; `busy_sessions` matches the per-agent sums | shared |
| Host message matches the schema above | shared |
| Migration removes only predecessor entries | migrate |

Every test runs with a temporary `HOME`, data directory and per-agent config home (`CODEX_HOME`, `COPILOT_HOME`, `PERTURBATION_HOME`), and a data directory whose name contains a space and an apostrophe. CI: macOS, Ubuntu, Windows × Python 3.9 and latest.

The extension is not unit-tested. Keep a short manual QA checklist instead: badge count matches the tooltip, the icon goes grey when the host is killed, the popup opens instantly after a cold start, and the icon survives a Chrome restart.

## Name

**`perturbation`** — decided 2026-09-20 after a wide search. In physics and astronomy a perturbation is a small disturbance of a system by an outside influence, stated without any judgement of whether the disturbance is welcome or justified. That is exactly what this project is: it interrupts you, sometimes because an agent genuinely needs you and sometimes not, and it takes no position on which.

It was, of the two dozen candidates checked on GitHub that day, the only one with **zero exact repository-name matches**. `com.tpojka.perturbation` is a valid native messaging host name (lowercase alphanumerics, underscores and dots only — no hyphens allowed), and `perturbation.tpojka.com` is free.

The vocabulary comes with it, and should be used consistently in the code, the popup and the README:

| Term | In the project |
|---|---|
| **unperturbed** | the green state: nothing is running, nothing wants you |
| **perturbed** | the red state, with the count of perturbing sessions |
| **damping** | the staleness rules that let a stuck session settle back to unperturbed |
| **amplitude** | the badge number, if a playful word is ever wanted for it |

Runners-up, kept in case the name is ever revisited: `semafor` (traffic light in several Slavic languages, plus the concurrency primitive — the most direct name for the interface), `easement` (property law: a lawful, permanent interference with someone's enjoyment of their land), `dynohub` (the hub dynamo that lights the lamp only while the wheel turns), `lanterne` (from *lanterne rouge*, the red lamp of the Tour's last rider). All four were free on GitHub on 2026-09-20.

## Repository and release conventions

- A **private** GitHub repository under `Tpojka`, default branch `main`; public only when asked.
- Conventional commits: `docs: add project brief`, `feat: …`, `test: …`, `docs(site): …`, `chore(release): …`.
- CI matrix: macOS, Ubuntu, Windows × Python 3.9 and latest.
- Tag `v1.0.0`, MIT licence, `CHANGELOG.md` in Keep a Changelog form, crediting the four predecessors.
- `site/index.html` + `site/index.md`, matching the sibling pages.

### Hosting the landing page

DigitalOcean droplet **138.68.154.134**, Apache 2.4.52 on Ubuntu, `tpojka.com` DNS on DigitalOcean nameservers, one Let's Encrypt certificate per subdomain.

1. Dashboard → Networking → Domains → `tpojka.com` → **A** record, hostname `<name>`, pointing at the droplet, TTL 3600. No AAAA. Ports 80/443 are already open.
2. On the server: `/var/www/<name>.tpojka.com`, a vhost mirroring the existing ones (`sudo apache2ctl -S`) with `DocumentRoot`, `DirectoryIndex index.html`, `AddType text/markdown .md`, `AddCharset utf-8 .html .md`; then `sudo a2ensite`, `sudo apache2ctl configtest && sudo systemctl reload apache2`.
3. When `dig +short <name>.tpojka.com` returns the droplet IP: `sudo certbot --apache -d <name>.tpojka.com --redirect`.
4. Deploy: `rsync -av --delete site/ <user>@138.68.154.134:/var/www/<name>.tpojka.com/`; verify with `curl -I` on `/` and `/index.md`.
5. Optionally redirect the four predecessor subdomains here.

## Build order

1. Shared core: `state`, `paths`, `config`, `notify`, `host`, `cli`, plus the `claude` adapter — one agent end to end.
2. The extension: lamp icons, badge, tooltip, popup.
3. `codex`, `copilot` adapters, ported from the shipped projects.
4. `goose` — cheapest of the new three; discover its payload with `hello-hooks` first.
5. `opencode` — highest reach; discover the event payload with a logging plugin first.
6. `antigravity`, including the optional status line.
7. `qwen`, only after its hook system has been read from source.
8. `migrate`, `doctor`, the site, CI, the tag.

Ship 1–3 as `v1.0.0` if the new three take longer than expected; the adapter registry makes each later agent an additive change.

## Author preferences

- Conventional commits (`feat:`, `fix:`, `docs:`, `docs(site):`, `test:`, `chore(release):` …).
- The user is the sole author. **Never** add a `Co-Authored-By: Claude` trailer to commits, and don't add Claude attribution to PRs.
- Verify claims against primary sources before building on them. The three new adapters in this brief are marked exactly where verification is still owed.

## Sources

- The four existing repositories under `~/GitHub/Tpojka/`, and `antigravalgia/docs/brief.md`
- Claude Code hooks: https://code.claude.com/docs/en/hooks
- Copilot CLI hooks: https://docs.github.com/en/copilot/reference/hooks-reference
- Antigravity CLI: https://antigravity.google/docs/hooks/ and https://antigravity.google/docs/cli/statusline/
- Codex CLI: its own `/hooks` command and `~/.codex/config.toml`
- opencode plugins and events: https://opencode.ai/docs/plugins/ , https://github.com/anomalyco/opencode
- Goose hooks: `crates/goose/src/hooks/mod.rs` and `examples/plugins/hello-hooks/` in https://github.com/aaif-goose/goose
- Qwen Code hooks: `docs/users/features/hooks.md` and `packages/core/src/hooks/types.ts` in https://github.com/QwenLM/qwen-code
- Chrome: `chrome.action` (`setIcon`, `setTitle`, `setBadgeText`, `setBadgeBackgroundColor`, `setBadgeTextColor`, `default_popup`) and native messaging in Manifest V3
