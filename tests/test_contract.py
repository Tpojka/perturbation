"""Every registered adapter honours the contract in agents/base.py. A new adapter gets these for free."""
from pathlib import Path

from perturbation import agents
from perturbation.agents import base
from perturbation.install import system
from tests.support import BUSY, IsolatedTestCase


class ContractTest(IsolatedTestCase):
    def test_registry(self):
        ids = agents.ids()
        self.assertEqual(ids, sorted(ids, key=lambda i: agents.get(i).ORDER))
        self.assertEqual(len(set(a.ORDER for a in agents.registered())), len(ids))
        self.assertIsNone(agents.get("nobody"))
        self.assertEqual([a.ID for a in agents.ordered(["codex", "nobody"])], ["codex"] + [i for i in ids if i != "codex"])
        self.assertEqual([a.ID for a in agents.ordered([])], ids)

    def test_check_rejects_incomplete_modules(self):
        class Half:
            __name__ = "half"
            ID = "half"

        with self.assertRaises(TypeError):
            base.check(Half)

    def test_every_adapter(self):
        for adapter in agents.registered():
            with self.subTest(agent=adapter.ID):
                self.check_adapter(adapter)

    def check_adapter(self, adapter):
        base.check(adapter)
        self.assertRegex(adapter.ID, r"^[a-z][a-z0-9_-]*$")
        self.assertTrue(adapter.NAME and adapter.SHORT)
        self.assertIsInstance(adapter.per_event_commands(), bool)
        self.assertIn(adapter.ID, BUSY, "tests/support.py needs a busy payload for every adapter")
        self.assertIn(adapter.detect(), (None,) if not adapter.detect() else (adapter.detect(),))
        self.assertIsInstance(adapter.verify(), (str, type(None)))

        # Payloads it doesn't understand are ignored, never errors.
        self.assertIsNone(adapter.parse(None, {}))
        self.assertIsNone(adapter.parse("nonsense", {"hook_event_name": "Nonsense", "type": "nonsense"}))
        event, payload = BUSY[adapter.ID]
        update = adapter.parse(event, payload)
        self.assertIsInstance(update, base.Update)
        self.assertEqual((update.session_id, update.state), ("s1", base.BUSY))

        # Install, reinstall (idempotent), uninstall (twice), all through the contract.
        commands = system.Commands(Path(self.data) / "perturbation.pyz").for_agent(adapter.ID)
        self.assertIsNone(adapter.installed())
        path = adapter.install(commands)
        self.assertTrue(path.is_file(), path)
        self.assertTrue(adapter.installed())
        before = path.read_bytes()
        self.assertEqual(adapter.install(commands), path)
        self.assertEqual(path.read_bytes(), before)
        self.assertIn(base.MARKER, before.decode("utf-8"))
        checks = adapter.doctor(commands)
        self.assertTrue(checks and all(isinstance(c, base.Check) for c in checks))
        self.assertTrue(all(c.ok for c in checks), checks)
        adapter.uninstall()
        self.assertIsNone(adapter.installed())
        adapter.uninstall()
        if hasattr(adapter, "statusline"):
            self.assertTrue(all(hasattr(adapter, n) for n in ("statusline_owner", "install_statusline", "uninstall_statusline", "settings_path")))
