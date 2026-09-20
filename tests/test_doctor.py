import io
import os
from contextlib import redirect_stdout

from perturbation import install, paths
from perturbation.agents import claude, codex
from perturbation.install import doctor, system
from tests.support import IsolatedTestCase, read_json, write_json


class DoctorTest(IsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.addCleanup(system.unregister_host)

    def run_installer(self, *args):
        with redirect_stdout(io.StringIO()) as out:
            install.main(list(args))
        return out.getvalue()

    def failures(self):
        return [c.text for _, checks in doctor.checks() for c in checks if not c.ok]

    def test_a_fresh_install_is_healthy(self):
        self.run_installer("1", "--agents", "claude,codex")
        self.assertEqual(self.failures(), [])
        sections = [name for name, _ in doctor.checks()]
        self.assertEqual(sections, ["Perturbation", "Chrome", "Claude Code", "Codex CLI"])
        with redirect_stdout(io.StringIO()) as out:
            self.assertEqual(doctor.run(), 0)
        self.assertIn("All good", out.getvalue())

    def test_nothing_installed(self):
        with redirect_stdout(io.StringIO()) as out:
            self.assertEqual(doctor.run(), 1)
        self.assertIn("run the installer", out.getvalue())

    def test_problems_are_named(self):
        self.run_installer("1", "--agents", "claude,codex")
        data = read_json(claude.settings_path())
        data["disableAllHooks"] = True
        write_json(claude.settings_path(), data)
        (codex.codex_home() / "config.toml").write_text("[features]\nhooks = false\n")
        manifest = read_json(paths.extension_dir() / "manifest.json")
        manifest["version"] = "0.0.1"
        write_json(paths.extension_dir() / "manifest.json", manifest)
        failures = self.failures()
        self.assertTrue(any("disableAllHooks" in f for f in failures))
        self.assertTrue(any("turned off" in f for f in failures))
        self.assertTrue(any("0.0.1" in f for f in failures))
        os.remove(paths.app_file())
        self.assertTrue(any("missing" in f for f in self.failures()))

    def test_stale_hook_commands_are_flagged(self):
        self.run_installer("1", "--agents", "codex")
        data = read_json(codex.hooks_path())
        data["hooks"]["Stop"][0]["hooks"][0]["command"] = "python3 '/old/perturbation.pyz' hook codex || true"
        write_json(codex.hooks_path(), data)
        self.assertTrue(any("old command" in f for f in self.failures()))
