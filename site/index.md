# Perturbation

**Red while an agent works. Amber when one needs you. Green when they're all free.**

One browser toolbar lamp for every coding agent on your machine: Claude Code, Codex CLI, GitHub Copilot CLI and Antigravity CLI, plus opencode, Goose and Qwen Code on the free tier. Optional desktop notifications. It works on macOS, Ubuntu and Windows.

> *perturbation* (n.): in physics and astronomy, a small disturbance of a system by an outside influence, stated without any judgement of whether the disturbance is welcome. That is what this does: it interrupts you, sometimes because an agent genuinely needs you and sometimes not, and takes no position on which.

- Website: <https://perturbation.tpojka.com>
- Source: <https://github.com/Tpojka/perturbation>

---

## One lamp, four states

| Lamp | State | Meaning |
| :-: | --- | --- |
| 🔴 | **Perturbed** | At least one agent is working. The badge counts the busy sessions |
| 🟡 | **Needs you** | Nothing is working, but a session is waiting for a permission or an answer |
| 🟢 | **Unperturbed** | Every watched agent is free |
| ⚪ | **Not connected** | The local helper isn't running, or no agent is watched. Run the installer |

Only one lamp is ever lit, and the fill pattern carries the meaning without colour: solid is busy, dotted needs you, a ring is free, dashes are disconnected. Hover for a per-agent summary; click for a list with one lamp per agent.

## What you get

- **One button for every agent:** the four earlier projects (Claudication, Codexalgia, Copilonidal, Antigravalgia) become one host, one extension, one lamp. The installer removes the old ones for you.
- **A count, not a colour:** the badge shows how many sessions are busy across every agent, so the lamp answers "how much" and not only "whether".
- **Needs you, separately:** amber is its own state, so an agent blocked on a permission never hides behind one that is still working.
- **A popup you can shape:** one row per agent, a mute switch each, and drag rows into the order you want.
- **Three platforms:** macOS, Ubuntu/Linux and Windows. The installer detects which one you're on and which agents you have.
- **Stays out of the way:** hooks that always exit 0 and print nothing, merged into files that stay yours, backed up first.
- **Fully local:** nothing leaves your machine. The status goes from each agent's hooks to the browser over native messaging.

## Install

Requires Python 3.9 or newer and a Chromium browser: Chrome, Edge, Brave, Opera, Vivaldi, Arc or Chromium.

**macOS**

```sh
git clone https://github.com/Tpojka/perturbation.git
cd perturbation
./install.sh
```

**Ubuntu**

```sh
sudo apt install python3 libnotify-bin   # notify-send, for the notifier
git clone https://github.com/Tpojka/perturbation.git
cd perturbation
./install.sh
```

**Windows**

```bat
winget install Python.Python.3.12
git clone https://github.com/Tpojka/perturbation.git
cd perturbation
install.cmd
```

The installer asks:

```
Which agents should be watched?
  [x] 1) Claude Code            found ~/.claude
  [x] 2) Codex CLI              found ~/.codex
  [ ] 3) GitHub Copilot CLI     not found
  [x] 4) Antigravity CLI        found ~/.gemini/antigravity-cli
  [x] 5) opencode               found ~/.config/opencode
  [ ] 6) Goose                  not found
  [ ] 7) Qwen Code              not found
Space or 1-7 toggles, ↑/↓ moves, a: all, n: none, Enter confirms:

Which browsers should the lamp work in?
  [x] 1) Google Chrome    /Applications/Google Chrome.app
  [ ] 2) Microsoft Edge   not found
  [x] 3) Brave            /Applications/Brave Browser.app
  [ ] 4) Opera            not found
  [ ] 5) Vivaldi          not found
  [ ] 6) Arc              not found
  [ ] 7) Chromium         not found
Space or 1-7 toggles, ↑/↓ moves, a: all, n: none, Enter confirms:

What should be installed?
  1) Browser extension
  2) Browser extension + OS notifier
  3) Nothing (exit)
Choose 1, 2 or 3: 2
Play a sound with notifications? [Y/n]:
Let Antigravity show "needs you" alerts? This sets its status line command. [y/N]:
```

Then load the extension, once per browser you ticked:

1. Open the browser's extensions page (`chrome://extensions`, `edge://extensions`, `brave://extensions`, …) and turn on **Developer mode**.
2. Click **Load unpacked** and pick the `extension` folder itself, the path the installer printed — not the folder above it.
3. Pin **Perturbation** to the toolbar.
4. Restart any running agent sessions so they load the hooks. In Codex, run `/hooks` and trust the new hooks.

The same folder is loaded into every browser, and one lamp per browser shows the same thing. You still get a single notification, because notifications come from the agent's hook rather than from the browser. No Chrome needed: tick Brave alone and Brave alone is registered.

If you had Claudication, Codexalgia, Copilonidal or Antigravalgia installed, the installer lists what they left behind and offers to remove it, keeps your notification settings, and prints the old extension IDs to remove on your browser's extensions page.

## OS notifier

You get a notification when an agent finishes a turn and when it needs you. The title names the agent and the project.

| When | Title | Text |
| --- | --- | --- |
| An agent finishes a turn | *Claude* is ready · *project* | the first line of its last message, or "Task finished" |
| An agent needs a permission or an answer | *Codex* needs you · *project* | the prompt, or what it wants to run |
| A turn ends with an error | *Claude* stopped · *project* | the error type |

Notifications are sent only when a session's state actually changes, never for a reminder that repeats a finished turn, and each agent can be muted in the popup.

### Change settings any time

Run these from the repository. They take effect at once, with no restart:

```sh
python3 -m perturbation.install set agents claude,codex      # watch exactly these
python3 -m perturbation.install set sound off
python3 -m perturbation.install set notifications off
python3 -m perturbation.install mute codex on                # silence one agent, keep its lamp
python3 -m perturbation.install statusline antigravity on    # "needs you" alerts for Antigravity
python3 -m perturbation.install status
python3 -m perturbation.install doctor
```

On Windows, use `py -3` instead of `python3`.

## How it works

```
Claude Code   ──hook──┐
Codex CLI     ──hook──┤
Copilot CLI   ──hook──┼──► perturbation.pyz hook <agent> ──► sessions/<agent>/<session>  (busy | waiting | ready)
Antigravity   ──hook──┘                                 └──► desktop notification (optional)

browser ──starts──► perturbation.pyz host
                      watches sessions/, pushes a per-agent summary on change
                                  │  native messaging
                                  ▼
                   extension: lamp + badge + tooltip, popup on click
```

Each agent is one small adapter that knows its hook file and its events. Everything else is shared: one hook handler, one state tree, one host, one lamp.

| Agent | Busy | Needs you | Ready |
| --- | --- | --- | --- |
| Claude Code | prompts, tool calls, compaction | permission prompts, questions | `Stop`, a manual compaction, an error |
| Codex CLI | prompts, tool calls | permission requests unanswered for 5 s | `Stop`, `Interrupt` |
| GitHub Copilot CLI | prompts, tool calls | permission prompts, questions | `Stop`, an unrecoverable error |
| Antigravity CLI | invocations, tool calls | its status line, when you turn it on | `Stop` when fully idle |
| opencode | session status, tool calls | permission prompts | `session.idle`, an error |
| Goose | prompts, tool calls, file and shell steps | never: Goose has no permission event | `Stop` |
| Qwen Code | prompts, tool calls, compaction | permission prompts and requests | `Stop`, a manual compaction, an error |

Every hook command exits 0 and prints nothing, even when Python or the app is missing. Copilot denies a tool call when a hook fails, Claude's `PreCompact` blocks compaction on exit 2, and Antigravity reads a hook's stdout as a decision, so this is what keeps the agents unharmed. A busy session with no activity for 15 minutes counts as ready, and one waiting for an hour does too, for the agents that never say goodbye.

---

Perturbation 1.2.2 · [MIT](https://github.com/Tpojka/perturbation/blob/main/LICENSE) © 2026 Goran Grbic · An independent project, not affiliated with Anthropic, OpenAI, GitHub or Google.
