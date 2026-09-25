import io
import os
import sys
from contextlib import redirect_stdout
from unittest import mock

from perturbation import browsers, config, install
from perturbation.agents import antigravity, claude, codex, copilot
from perturbation.install import migrate, system
from tests.support import IsolatedTestCase, read_json, write_json

FOREIGN = {"type": "command", "command": "say done"}


def plant_predecessors():
    """Leave behind what the four shipped projects leave behind."""
    write_json(claude.settings_path(), {"model": "opus", "hooks": {"Stop": [{"hooks": [FOREIGN, {"type": "command", "command": 'python3 "/x/claudication.pyz" hook'}]}]}})
    write_json(codex.hooks_path(), {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": 'python3 "/x/codexalgia.pyz" hook'}, FOREIGN]}]}})
    write_json(copilot.hooks_path("copilonidal.pyz"), {"version": 1, "hooks": {}})
    write_json(copilot.hooks_path().parent / "mine.json", {"version": 1, "hooks": {}})
    write_json(antigravity.hooks_path(), {"antigravalgia": {"Stop": []}, "mine": {"Stop": []}})
    write_json(antigravity.settings_path(), {"statusLine": {"type": "command", "command": "python3 '/x/antigravalgia.pyz' statusline"}, "trustedWorkspaces": ["/w"]})
    for name, settings in (("Claudication", {"notifications": True, "sound": False}), ("Codexalgia", {"notifications": False, "sound": True})):
        write_json(migrate.data_dir_of(name) / "config.json", settings)
    if sys.platform != "win32":
        for host in ("com.tpojka.claudication", "com.tpojka.antigravalgia"):
            directory = browsers.base.host_dir(browsers.get("chrome"))
            directory.mkdir(parents=True, exist_ok=True)
            write_json(directory / f"{host}.json", system.host_manifest("/x/host", host, "old"))


class MigrateTest(IsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.addCleanup(system.unregister_host)

    def test_nothing_to_find_on_a_clean_machine(self):
        self.assertEqual(migrate.find(), [])
        self.assertEqual(migrate.carried_over([]), {})

    def test_finds_everything_the_predecessors_left(self):
        plant_predecessors()
        found = {f.name: f for f in migrate.find()}
        self.assertEqual(set(found), {"Claudication", "Codexalgia", "Copilonidal", "Antigravalgia"})
        self.assertEqual(found["Claudication"].hooks, "1 hook entries in ~/.claude/settings.json")
        self.assertEqual(found["Codexalgia"].hooks, "1 hook entries in ~/.codex/hooks.json")
        self.assertEqual(found["Copilonidal"].hooks, "~/.copilot/hooks/copilonidal.json")
        self.assertEqual(found["Antigravalgia"].hooks, "bundle 'antigravalgia' in ~/.gemini/config/hooks.json")
        self.assertTrue(found["Claudication"].data_dir)
        self.assertIsNone(found["Copilonidal"].data_dir)
        self.assertEqual(found["Claudication"].settings, {"notifications": True, "sound": False})
        self.assertEqual(found["Claudication"].extension_id, "hpoodlefheijkfkpebmooehgnjkibdnc")
        if sys.platform != "win32":
            self.assertEqual(len(found["Claudication"].manifests), 1)
            self.assertEqual(found["Codexalgia"].manifests, [])
        self.assertEqual(migrate.carried_over(migrate.find()), {"notifications": True, "sound": False})
        self.assertTrue(any("native host manifest" in i or "data directory" in i for i in found["Claudication"].items()))

    def test_remove_takes_only_what_is_theirs(self):
        plant_predecessors()
        for found in migrate.find():
            self.assertEqual(migrate.remove(found), [])
        self.assertEqual(migrate.find(), [])
        self.assertEqual(read_json(claude.settings_path()), {"model": "opus", "hooks": {"Stop": [{"hooks": [FOREIGN]}]}})
        self.assertEqual(read_json(codex.hooks_path()), {"hooks": {"Stop": [{"hooks": [FOREIGN]}]}})
        self.assertEqual(os.listdir(copilot.hooks_path().parent), ["mine.json"])
        self.assertEqual(read_json(antigravity.hooks_path()), {"mine": {"Stop": []}})
        self.assertEqual(read_json(antigravity.settings_path()), {"trustedWorkspaces": ["/w"]})
        self.assertFalse(migrate.data_dir_of("Claudication").exists())
        if sys.platform != "win32":
            self.assertFalse((browsers.base.host_dir(browsers.get("chrome")) / "com.tpojka.claudication.json").exists())

    def run_installer(self, *args):
        with redirect_stdout(io.StringIO()) as out:
            install.main(list(args))
        return out.getvalue()

    def test_the_installer_offers_the_migration(self):
        plant_predecessors()
        with mock.patch("builtins.input", side_effect=["", "", "2", "", "y"]) as ask:
            out = self.run_installer()
        questions = " ".join(call.args[0] for call in ask.call_args_list)
        self.assertIn("Remove them now?", questions)
        self.assertIn("Play a sound with notifications? [y/N]", questions)  # Claudication had sound off
        self.assertIn("Found earlier installs", out)
        self.assertIn("Removed Claudication", out)
        self.assertIn("hpoodlefheijkfkpebmooehgnjkibdnc", out)
        self.assertEqual(migrate.find(), [])
        self.assertEqual(read_json(claude.settings_path())["model"], "opus")

    def test_the_installer_keeps_predecessors_unless_told(self):
        plant_predecessors()
        self.run_installer("1", "--agents", "claude")
        self.assertEqual(len(migrate.find()), 4)
        out = self.run_installer("1", "--agents", "claude", "--migrate")
        self.assertIn("Removed Codexalgia", out)
        self.assertEqual(migrate.find(), [])
        self.assertTrue(claude.installed())

    def test_migrate_command(self):
        self.assertIn("No earlier installs", self.run_installer("migrate"))
        plant_predecessors()
        with mock.patch("builtins.input", return_value="n"):
            self.assertIn("Nothing removed", self.run_installer("migrate"))
        self.assertEqual(len(migrate.find()), 4)
        self.run_installer("1", "--agents", "claude")
        out = self.run_installer("migrate", "--yes")
        self.assertIn("Carried over: notifications on, sound off", out)
        self.assertEqual(migrate.find(), [])
        settings = config.load()
        self.assertEqual((settings["notifications"], settings["sound"]), (True, False))
