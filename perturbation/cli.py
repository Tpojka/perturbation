"""Entry point of the installed perturbation.pyz.

`hook <agent> [<event>]` is run by an agent's hook system, `statusline <agent>` by an agent's TUI,
`remind` by the hook itself (a deferred update), `host` by Chrome, and `version` by the doctor.
"""
import sys

USAGE = "usage: perturbation.pyz hook <agent> [<event>] | statusline <agent> | host | version"


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    command = argv[0] if argv else ""
    if command == "hook":
        from . import hook

        hook.main(argv[1:])
    elif command == "statusline":
        from . import statusline

        statusline.main(argv[1:])
    elif command == "remind":
        from . import hook

        hook.remind_main(argv[1:])
    elif command == "host":
        from . import host

        host.main()
    elif command == "version":
        from . import __version__

        print(__version__)
    else:
        sys.exit(USAGE)
