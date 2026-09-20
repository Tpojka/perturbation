"""Installer: copies the app and extension into the per-user data directory, then wires up Chrome and
every agent you choose to watch.

Usage: python3 -m perturbation.install                            interactive
       python3 -m perturbation.install 1|2|3 [--agents a,b | --all] [--no-sound] [--statusline] [--migrate]
       python3 -m perturbation.install set agents claude,codex      change the watched set
       python3 -m perturbation.install set sound|notifications|waiting-as-busy on|off
       python3 -m perturbation.install mute <agent> on|off          silence one agent's notifications
       python3 -m perturbation.install statusline <agent> on|off    add or remove an agent's status line
       python3 -m perturbation.install status                       what is installed and what is running
       python3 -m perturbation.install doctor                       per-agent health checks
       python3 -m perturbation.install migrate [--yes]              remove the four predecessor installs
       python3 -m perturbation.install uninstall                    remove everything
"""
import shutil
import sys
import tempfile
import zipapp
from pathlib import Path

from .. import __version__, agents, config, notify, paths, state
from ..agents.base import ConfigError, describe
from . import doctor, menu, migrate, system

REPO = Path(__file__).resolve().parents[2]

OPTIONS = {"sound": "sound", "notifications": "notifications", "waiting-as-busy": "count_waiting_as_busy"}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    arg = argv[0] if argv else None
    if arg == "uninstall":
        return uninstall()
    if arg == "set":
        return set_option(*argv[1:3])
    if arg == "mute":
        return set_mute(*argv[1:3])
    if arg == "statusline":
        return set_statusline(*argv[1:3])
    if arg == "status":
        return status()
    if arg == "doctor":
        sys.exit(doctor.run())
    if arg == "migrate":
        return migrate_command(ask=not ("--yes" in argv or "-y" in argv))
    if arg in ("1", "2", "3"):
        return _non_interactive(arg, argv[1:])
    return _interactive()


def _non_interactive(choice, flags):
    if choice == "3":
        print("Nothing installed.")
        return
    selected = _agents_flag(flags)
    statusline = {a.ID: True for a in _statusline_agents(selected)} if "--statusline" in flags else {}
    predecessors = migrate.find() if "--migrate" in flags else []
    install(selected, notifications=choice == "2", sound="--no-sound" not in flags, statusline=statusline, predecessors=predecessors)


def _agents_flag(flags):
    known = agents.ids()
    if "--all" in flags:
        return known
    for i, flag in enumerate(flags):
        if flag == "--agents" and i + 1 < len(flags):
            value = flags[i + 1]
        elif flag.startswith("--agents="):
            value = flag.split("=", 1)[1]
        else:
            continue
        wanted = [v.strip() for v in value.split(",") if v.strip()]
        unknown = [v for v in wanted if v not in known]
        if unknown:
            sys.exit(f"unknown agent{'s' if len(unknown) > 1 else ''}: {', '.join(unknown)}. Known: {', '.join(known)}")
        return [i for i in known if i in wanted]
    return [a.ID for a in agents.registered() if a.detect()]


def _interactive():
    adapters = agents.registered()
    predecessors = migrate.find()
    carried = migrate.carried_over(predecessors)
    detected = {a.ID: a.detect() for a in adapters}
    if paths.config_file().exists():
        preselected = set(config.load()["agents"])
    else:
        preselected = {i for i, found in detected.items() if found}
    selected = menu.choose_agents(adapters, preselected, detected)
    if selected is None:
        print("Nothing installed.")
        return
    choice = menu.choose_install()
    if choice == "3":
        print("Nothing installed.")
        return
    notifications = choice == "2"
    sound = notifications and menu.ask_yes_no("Play a sound with notifications?", default=carried.get("sound", True))
    statusline = {}
    if notifications:
        for adapter in _statusline_agents(selected):
            if _statusline_free(adapter):
                statusline[adapter.ID] = menu.ask_yes_no(f'Let {adapter.SHORT} show "needs you" alerts? This sets its status line command.', default=False)
    if predecessors:
        print()
        print("Found earlier installs that this project replaces:")
        for found in predecessors:
            for item in found.items():
                print(f"  {found.name}: {item}")
        if not menu.ask_yes_no("Remove them now? Their hooks, host registrations and data directories go; nothing else does."):
            predecessors = []
    install(selected, notifications=notifications, sound=sound, statusline=statusline, predecessors=predecessors)


def _statusline_agents(selected):
    return [a for a in agents.registered() if a.ID in selected and hasattr(a, "statusline")]


def _statusline_free(adapter):
    """True when no one owns the agent's status line, or we already do."""
    return adapter.statusline_owner() in (None, "ours")


def install(selected, notifications, sound=True, statusline=None, predecessors=()):
    data = paths.data_dir()
    data.mkdir(parents=True, exist_ok=True)
    _copy_extension()
    app = _build_app()
    print(f"✓ Installed to {data}")

    for manifest in system.register_host(system.write_host_launcher(app)):
        print(f"✓ Native host registered: {manifest}")

    if predecessors:
        _remove_predecessors(predecessors)

    commands = system.Commands(app)
    watched = []
    for adapter in agents.registered():
        agent_commands = commands.for_agent(adapter.ID)
        try:
            if adapter.ID in selected:
                unchanged = hasattr(adapter, "changed") and not adapter.changed(agent_commands)
                path = adapter.install(agent_commands)
                watched.append(adapter.ID)
                note = " (unchanged, so Codex keeps trusting them)" if unchanged else ""
                print(f"✓ {adapter.NAME}: hooks in {describe(path)}{note}")
                if adapter.verify():
                    print(f"    check: {adapter.verify()}")
            elif adapter.installed():
                adapter.uninstall()
                print(f"✓ {adapter.NAME}: hooks removed, not watched")
        except ConfigError as error:
            print(f"! {adapter.NAME}: {error}")
            print("  Fix that file by hand, then run the installer again.")

    settings = config.load()
    settings.update({"notifications": notifications, "sound": sound, "agents": watched})
    settings["order"] = settings["order"] or agents.ids()
    settings["statusline"] = {}
    for adapter in _statusline_agents(watched):
        wanted = (statusline or {}).get(adapter.ID, False)
        if wanted and _install_statusline(adapter, commands):
            settings["statusline"][adapter.ID] = True
        elif not wanted and adapter.statusline_owner() == "ours":
            adapter.uninstall_statusline()  # a status line nobody asked for this time is a leftover
            print(f"✓ {adapter.NAME}: status line removed")
    config.save(settings)

    if notifications:
        print(f"✓ OS notifier on, {'with' if sound else 'without'} sound: a notification appears when an agent finishes or needs you")
        hint = notify.setup_hint()
        if hint:
            print(f"  ! {hint}")
    else:
        print("✓ OS notifier off")
    if not watched:
        print("! No agents are watched, so the lamp stays grey. Run the installer again or use `set agents`.")

    print(
        f"""
Next, if the extension isn't loaded yet: open chrome://extensions, turn on Developer mode,
click "Load unpacked" and pick: {paths.extension_dir()}
Then pin the lamp to the toolbar. Restart running agent sessions so they load the hooks."""
    )


def _remove_predecessors(predecessors):
    for found in predecessors:
        problems = migrate.remove(found)
        print(f"✓ Removed {found.name}" + (f" ({'; '.join(problems)})" if problems else ""))
    print("  Remove their extensions at chrome://extensions yourself; one extension can't uninstall another:")
    for found in predecessors:
        print(f"    {found.name}: {found.extension_id}")


def _install_statusline(adapter, commands):
    """Write our status line unless someone else's is already there. Returns True when it was written."""
    command = commands.statusline(adapter.ID)
    if not _statusline_free(adapter):
        print(f"! {adapter.NAME} already has a custom status line in {describe(adapter.settings_path())}; left it alone.")
        print(f"  To use Perturbation's instead, set statusLine.command to:")
        print(f"    {command}")
        return False
    try:
        adapter.install_statusline(command)
    except ConfigError as error:
        print(f"! {adapter.NAME}: {error}")
        return False
    print(f'✓ {adapter.NAME}: status line on, "{adapter.SHORT} needs you" alerts stacked under its own line')
    return True


def uninstall():
    for adapter in agents.registered():
        try:
            adapter.uninstall()
        except ConfigError as error:
            print(f"! {adapter.NAME}: {error}")
    system.unregister_host()
    shutil.rmtree(paths.data_dir(), ignore_errors=True)
    print("✓ Perturbation removed. Remove the extension itself from chrome://extensions.")


def _require_install():
    if not paths.app_file().exists():
        sys.exit("Perturbation isn't installed. Run the installer first.")


def set_option(name=None, value=None):
    """Change one setting of the installed app; the hook and the host pick it up on their next run."""
    if name == "agents":
        return set_agents(value)
    if name not in OPTIONS or value not in ("on", "off"):
        sys.exit("usage: python3 -m perturbation.install set agents <ids> | sound|notifications|waiting-as-busy on|off")
    _require_install()
    settings = config.load()
    settings[OPTIONS[name]] = value == "on"
    config.save(settings)
    print(f"✓ {name.replace('-', ' ').capitalize()} {value}")


def set_agents(value=None):
    """Watch exactly these agents: install hooks for new ones, remove them from dropped ones."""
    _require_install()
    known = agents.ids()
    wanted = [v.strip() for v in (value or "").split(",") if v.strip()]
    unknown = [v for v in wanted if v not in known]
    if unknown or value is None:
        sys.exit(f"usage: python3 -m perturbation.install set agents <ids>   (known: {', '.join(known)})")
    settings = config.load()
    commands = system.Commands(paths.app_file())
    watched = []
    for adapter in agents.registered():
        try:
            if adapter.ID in wanted:
                path = adapter.install(commands.for_agent(adapter.ID))
                watched.append(adapter.ID)
                print(f"✓ {adapter.NAME}: hooks in {describe(path)}")
            elif adapter.installed():
                adapter.uninstall()
                settings["statusline"].pop(adapter.ID, None)
                print(f"✓ {adapter.NAME}: hooks removed")
        except ConfigError as error:
            print(f"! {adapter.NAME}: {error}")
    settings["agents"] = watched
    config.save(settings)


def set_mute(agent_id=None, value=None):
    if agents.get(agent_id) is None or value not in ("on", "off"):
        sys.exit(f"usage: python3 -m perturbation.install mute <agent> on|off   (agents: {', '.join(agents.ids())})")
    _require_install()
    settings = config.load()
    if value == "on":
        settings["mute"][agent_id] = True
    else:
        settings["mute"].pop(agent_id, None)
    config.save(settings)
    print(f"✓ {agents.get(agent_id).NAME} notifications {'muted' if value == 'on' else 'unmuted'}")


def set_statusline(agent_id=None, value=None):
    adapter = agents.get(agent_id)
    capable = [a.ID for a in agents.registered() if hasattr(a, "statusline")]
    if adapter is None or not hasattr(adapter, "statusline") or value not in ("on", "off"):
        sys.exit(f"usage: python3 -m perturbation.install statusline <agent> on|off   (agents with a status line: {', '.join(capable)})")
    _require_install()
    settings = config.load()
    try:
        if value == "off":
            adapter.uninstall_statusline()
            settings["statusline"].pop(agent_id, None)
            print(f"✓ {adapter.NAME}: status line removed")
        elif _install_statusline(adapter, system.Commands(paths.app_file())):
            settings["statusline"][agent_id] = True
    except ConfigError as error:
        sys.exit(f"! {error}")
    config.save(settings)


def status():
    settings = config.load()
    installed = paths.app_file().exists()
    print(f"Perturbation {__version__} · {'installed in' if installed else 'not installed; data directory would be'} {paths.data_dir()}")
    manifests = system.registered_manifests()
    print(f"Native host: {', '.join(describe(m) for m in manifests) if manifests else 'not registered'}")
    print(f"Notifications: {'on' if settings['notifications'] else 'off'}, sound {'on' if settings['sound'] else 'off'}, waiting counts as busy: {'yes' if settings['count_waiting_as_busy'] else 'no'}")
    print("Agents:")
    for adapter in agents.ordered(settings["order"]):
        watched = adapter.ID in settings["agents"]
        try:
            where = adapter.installed()
        except ConfigError as error:
            where = str(error)
        summary = state.summary(adapter.ID)
        line = f"  {_glyph(summary['state']) if watched else '·'} {adapter.NAME:<22} {'watched' if watched else 'not watched':<11}"
        if watched:
            line += f" {_describe(summary)}"
            if settings["mute"].get(adapter.ID):
                line += ", muted"
            if settings["statusline"].get(adapter.ID):
                line += ", status line on"
        if where:
            line += f"  ({where})"
        print(line.rstrip())
    predecessors = migrate.find()
    if predecessors:
        print("Predecessors still installed: " + ", ".join(f.name for f in predecessors) + "  (run: python3 -m perturbation.install migrate)")


def _glyph(value):
    return {state.BUSY: "●", state.WAITING: "◐", state.READY: "○"}[value]


def _describe(summary):
    if summary["total"] == 0:
        return "no sessions"
    parts = []
    if summary["busy"]:
        parts.append(f"{summary['busy']} working")
    if summary["waiting"]:
        parts.append(f"{summary['waiting']} waiting for you")
    return (", ".join(parts) or "ready") + f" of {summary['total']} session{'s' if summary['total'] != 1 else ''}"


def migrate_command(ask=True):
    found = migrate.find()
    if not found:
        print("No earlier installs found.")
        return
    print("Found earlier installs that this project replaces:")
    for item in found:
        for line in item.items():
            print(f"  {item.name}: {line}")
    if ask and not menu.ask_yes_no("Remove them now?"):
        print("Nothing removed.")
        return
    _remove_predecessors(found)
    carried = migrate.carried_over(found)
    if carried and paths.config_file().exists():
        settings = config.load()
        settings.update(carried)
        config.save(settings)
        print(f"✓ Carried over: " + ", ".join(f"{k} {'on' if v else 'off'}" for k, v in carried.items()))


def _copy_extension():
    # Chrome loads the unpacked extension from here, so the repository can be moved or deleted.
    target = paths.extension_dir()
    shutil.rmtree(target, ignore_errors=True)
    shutil.copytree(REPO / "extension", target, ignore=shutil.ignore_patterns("*.svg", ".DS_Store"))


def _build_app():
    # Pack the runtime modules into one file that hooks, status lines and the native host run directly.
    target = paths.app_file()
    with tempfile.TemporaryDirectory() as staging:
        shutil.copytree(
            REPO / "perturbation",
            Path(staging) / "perturbation",
            ignore=shutil.ignore_patterns("__pycache__", "install"),
        )
        zipapp.create_archive(staging, target, main="perturbation.cli:main")
    return target
