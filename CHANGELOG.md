# Changelog

All notable changes to this project are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/).

## [1.1.0] - 2026-09-20

Three free-tier agents join the four pro-tier ones, and the installer's agent question becomes a picker.

### Added

- **opencode** (`opencode`): a plugin file, `~/.config/opencode/plugins/perturbation.js`, the only JavaScript in the project. It forwards `session.created`, `session.status`, `session.idle`, `session.error`, `session.deleted`, `session.compacted`, `permission.updated`/`permission.asked` and `permission.replied`, plus the `tool.execute.*` hooks, to `perturbation.pyz hook opencode` from a detached process it never awaits; it skips subagent sessions and forgets its sessions when opencode shuts down. Event shapes verified against `@opencode-ai/sdk` 1.18.10 and opencode 1.18.31. Honours `OPENCODE_CONFIG_DIR`.
- **Goose** (`goose`): a plugin directory, `~/.agents/plugins/perturbation/`, with `plugin.json` and `hooks/hooks.json`. Goose names the event in its payload and runs every hook through `sh -c` on every OS, so its command is written for a POSIX shell even on Windows. No permission event, so no waiting state. `doctor` notices `disabledPlugins`. Verified against `crates/goose/src/hooks/mod.rs` and the plugin guide in `aaif-goose/goose`.
- **Qwen Code** (`qwen`): hooks merged into `~/.qwen/settings.json`. Its hooks are Claude-shaped (`hook_event_name`, `session_id`, `cwd`, seconds, exit 2 blocks), with `PermissionRequest` and `Notification`/`permission_prompt` both giving "needs you", `StopFailure` giving "stopped", and a `shell` field that asks for PowerShell on Windows. Verified against `docs/users/features/hooks.md` in `QwenLM/qwen-code`.
- **Tiers.** Every adapter declares `TIER`: `pro` (Claude Code, Codex CLI, Copilot CLI, Antigravity CLI) or `free` (opencode, Goose, Qwen Code).
- **A picker for the agent question.** The arrow keys (or `j`/`k`) move a cursor and **Space** toggles the agent under it; number keys still toggle directly. The free-tier agents stay folded behind one `+` row until one is found on the machine or already watched, or until `+` is pressed, the way opencode's provider picker keeps its long tail behind "Other". Outside a terminal the picker reads whole lines, so pipes and tests keep working.
- **The project name is remembered per session.** Not every event carries it (Goose's `Stop`, opencode's `session.idle`), so the state file keeps the last one seen and the "is ready" title still names the project.
- `Commands.hook(..., shell="sh")` for adapters whose agent runs hooks through a POSIX shell regardless of the OS.
- 161 tests; the opencode plugin is parsed with `node --check` in the tests and by `doctor` when Node is present.

## [1.0.0] - 2026-09-20

The first release. It replaces four shipped projects, one per agent, with one repository, one installer, one native host and one Chrome toolbar button: [Claudication](https://github.com/Tpojka/claudication) 2.1.0 (Claude Code), [Codexalgia](https://github.com/Tpojka/codexalgia) 1.0.0 (Codex CLI), [Copilonidal](https://github.com/Tpojka/copilonidal) 1.0.0 (GitHub Copilot CLI) and [Antigravalgia](https://github.com/Tpojka/antigravalgia) 1.0.0 (Antigravity CLI). Everything those four verified against their agents is carried over; the differences are listed below.

### Added

- **One lamp for every agent.** A single toolbar disc in traffic-light colours: red while any watched agent works, with the number of busy sessions as the badge; amber when nothing works but a session needs you, with that count; green when everything is free; grey when the host isn't connected or nothing is watched. Only one lamp is ever lit, and the fill pattern (solid, dotted, ring, dashed) carries the meaning without colour.
- **A tooltip per agent** on hover, and **a popup** on click with one row per agent: its lamp, state and session count, a switch that mutes its notifications, and drag-to-reorder for the order of the popup and the tooltip. Both write to the installed `config.json` through the native host, so the settings survive.
- **An adapter contract** (`perturbation/agents/base.py`) and a registry. Every agent is one module; the hook handler, host, installer, doctor and migration know none of them by name. `docs/adding-an-agent.md` explains the steps, and `tests/test_contract.py` runs every registered adapter through the same checks.
- **A multi-select installer**: it detects each agent, pre-checks the ones it finds, and lets you toggle them by number. Non-interactive form: `python3 -m perturbation.install 2 --agents claude,codex --no-sound --statusline --migrate`. Agents you uncheck lose their hooks on reinstall.
- **`set agents`, `mute`, `set waiting-as-busy`, `status` and `doctor`** commands. `doctor` checks the installed app and extension versions, the host registration and launcher, and per agent that the config holds our entries, that they point at the installed app, and the agent-specific traps: Claude's `disableAllHooks`, Codex's `[features] hooks = false`, Antigravity's bundle and status line ownership.
- **Migration** from the four predecessors: the installer (and `migrate`) finds their host manifests, data directories and hook entries, lists them, removes them on request, carries over `notifications` and `sound`, and prints the old extension IDs to remove at `chrome://extensions`.
- **Claude Code:** `PreCompact` keeps a session busy and `PostCompact` ends a manual compaction with an "is ready" notification while an automatic one stays busy, so a `/compact` no longer runs for minutes under a green lamp. `StopFailure` ends a turn killed by an API error with a "stopped" notification instead of leaving it red until the damping rule fires. `agent_needs_input` and `elicitation_url_dialog` count as "needs you". The "is ready" notification carries the first line of the last message, as Codexalgia's did.
- **Codex CLI:** the permission grace period is now a deferred update in the shared hook handler (`Update.delay`), so the lamp turns amber only when a request is still unanswered after five seconds. Reinstalls rewrite hooks in place, as before, and the installer says when the file was unchanged so the trust you gave survives.
- **Copilot CLI and Antigravity CLI:** ported as shipped, on the shared contract.
- **Damping:** a waiting session with no activity for 60 minutes counts as ready (`PERTURBATION_WAITING_STALE_SECONDS`), alongside the 15-minute busy rule and the 24-hour session rule.
- **One hardened hook command everywhere** (`|| true`, `; exit 0`), because one codebase now feeds four agents and Copilot, Claude and Antigravity all punish a failing hook. Every test that runs the command does so with the app present and deleted.
- A 128-test unittest suite, CI on macOS, Ubuntu and Windows with Python 3.9 and latest (which also parses the extension scripts with Node), the landing page in `site/`, and the project brief in `docs/`.

### Changed from the predecessors

- The state tree is `<data>/sessions/<agent>/<session>`; the host message has a `type`, `overall`, `busy_sessions`, `waiting_sessions` and an `agents` array, already in the user's order.
- `waiting` is a third visible state. The predecessors folded it into ready (Copilonidal, Antigravalgia) or busy (Codexalgia). `set waiting-as-busy on` restores the two-state view.
- Notifications are sent only when a session's stored state changes, for every agent. The predecessors notified on every qualifying event.
- Its own identifiers: native host `com.tpojka.perturbation`, extension ID `jbibmafopagpblieglanmabkegglkpgo`, data directory `Perturbation`, app `perturbation.pyz`, config marker `perturbation.pyz`, env vars `PERTURBATION_*`.

[1.1.0]: https://github.com/Tpojka/perturbation/releases/tag/v1.1.0
[1.0.0]: https://github.com/Tpojka/perturbation/releases/tag/v1.0.0
