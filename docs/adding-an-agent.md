# Adding an agent

Every agent is one module in `perturbation/agents/`. Nothing else in the codebase knows an agent exists: the hook handler, the host, the installer, the doctor and the migration all go through the registry and the contract in `perturbation/agents/base.py`.

## 1. Write the module

Copy the closest existing adapter and change what differs:

| The agent… | Start from |
| --- | --- |
| names the event in its payload and shares its settings file with other tools | `claude.py` |
| has a hooks file of its own and cares about hook identity (trust) | `codex.py` |
| loads every file in a hooks directory | `copilot.py` |
| carries no event name in its payload, or has a status line | `antigravity.py` |

The module must expose:

```python
ID       = "goose"          # directory under sessions/, argv token, config key
NAME     = "Goose"          # shown in the popup and the installer
SHORT    = "Goose"          # notification titles: "Goose is ready · project"
SHAPE    = "config"         # "config" (entries in its hooks file) or "plugin" (a plugin file of ours)
ORDER    = 6                # default position in the popup and the installer

def detect() -> Optional[str]                  # "found ~/.config/goose", or None
def per_event_commands() -> bool               # True when the payload carries no event name
def install(commands) -> Path                  # write the hooks or the plugin, return the file
def uninstall(markers=(MARKER,)) -> None       # remove only what install() wrote
def installed(markers=(MARKER,)) -> Optional[str]
def verify() -> Optional[str]                  # how the user confirms the registration
def parse(event, payload) -> Optional[Update]  # one payload -> one Update, or None
def doctor(commands) -> List[Check]
```

`commands.hook(event=None)` is the shell command to register, already hardened to exit 0 and print nothing. Use it as it is. `commands.shell` is `"bash"` or `"powershell"`, for agents whose entries name the shell.

`parse` returns an `Update(session_id, state, notice, project, delay)`:

- `state` is `BUSY`, `WAITING`, `READY`, or `None` to forget the session.
- `notice` is `Notice(kind, message)` with kind `READY`, `NEEDS_YOU` or `STOPPED`. It is sent only when the stored state actually changes, so returning one on every event is fine.
- `project` is the project name for the title, from `project_of(payload.get("cwd"))` or wherever the agent puts it.
- `delay` defers the update by that many seconds and drops it if the session changes meanwhile. Codex uses it for permission prompts it may answer itself.

For agents whose TUI runs a status line command, add `statusline(payload) -> (Update or None, text)` and the three `*_statusline` helpers; see `antigravity.py`.

Use `jsonfile.update()` for any file that belongs to the agent. It backs the file up, swaps the new version in atomically, and refuses to touch a file it can't parse.

## 2. Register it

Add the module name to `MODULES` in `perturbation/agents/__init__.py`. The registry checks the contract on import and sorts by `ORDER`.

## 3. Test it

`tests/test_contract.py` runs every registered adapter through the contract: unknown payloads are ignored, install is idempotent, uninstall leaves nothing, the doctor passes on a fresh install. Add a busy payload for the agent to `BUSY` in `tests/support.py`; that also makes `tests/test_install.py` run the generated hook command through `sh`, `bash` and PowerShell, with the app present and with it deleted, and check that it exits 0 and prints nothing.

Then add `tests/test_<id>.py` for what only this agent does: its file format, its foreign entries surviving install and uninstall byte for byte, and its event table.

## 4. Document it

Add a row to the agents table and an event table to `README.md`, and an entry to `CHANGELOG.md`. Say what the agent cannot signal (no waiting state, no session end), because the damping rules then carry it.
