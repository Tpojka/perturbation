import json
import os
import shutil
import subprocess
import sys
import textwrap
import types
import unittest
from pathlib import Path

from perturbation.agents import opencode
from perturbation.install import system
from tests.support import IsolatedTestCase

COMMANDS = system.Commands(Path("/data/perturbation.pyz")).for_agent("opencode")


def event(kind, **props):
    return {"type": kind, "properties": props}


class OpencodePluginTest(IsolatedTestCase):
    def test_location_follows_the_config_dir_variables(self):
        self.assertEqual(opencode.plugin_path(), Path(self.home) / ".config" / "opencode" / "plugins" / "perturbation.js")
        os.environ["OPENCODE_CONFIG_DIR"] = os.path.join(self.home, "elsewhere")
        self.assertEqual(opencode.plugin_path(), Path(self.home) / "elsewhere" / "plugins" / "perturbation.js")
        self.assertIsNone(opencode.detect())
        os.makedirs(opencode.config_home())
        self.assertEqual(opencode.detect(), "found ~/elsewhere")

    def test_the_plugin_carries_the_paths_and_parses(self):
        path = opencode.install(COMMANDS)
        text = path.read_text(encoding="utf-8")
        self.assertIn(f"const APP = {json.dumps(str(COMMANDS.app))};", text)
        self.assertIn(f"const PYTHON = {json.dumps(COMMANDS.python)};", text)
        self.assertNotIn("__PYTHON__", text)
        self.assertIn("perturbation.shutdown", text)
        self.assertEqual(opencode.installed(), "~/.config/opencode/plugins/perturbation.js")
        node = shutil.which("node")
        if node:
            result = subprocess.run([node, "--check", str(path)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_uninstall_removes_only_our_file(self):
        other = opencode.plugin_path().parent / "mine.js"
        other.parent.mkdir(parents=True)
        other.write_text("export const Mine = async () => ({})")
        opencode.install(COMMANDS)
        opencode.uninstall()
        opencode.uninstall()
        self.assertEqual(os.listdir(other.parent), ["mine.js"])
        self.assertIsNone(opencode.installed())

    def test_doctor(self):
        self.assertFalse(opencode.doctor(COMMANDS)[0].ok)
        opencode.install(COMMANDS)
        self.assertTrue(all(c.ok for c in opencode.doctor(COMMANDS)))
        other = system.Commands(Path("/elsewhere/perturbation.pyz")).for_agent("opencode")
        self.assertFalse(opencode.doctor(other)[1].ok)


NODE = shutil.which("node")


class OpencodePluginRunTest(IsolatedTestCase):
    @unittest.skipUnless(NODE, "needs Node.js")
    def test_the_plugin_hands_events_on_one_at_a_time_in_order(self):
        # opencode ends a turn with session.status (idle) and session.idle at once. The first hook is
        # made the slow one: if the plugin started both together, the second would finish first.
        log = os.path.join(self.home, "order.log")
        app = os.path.join(self.home, "fake_app.py")
        with open(app, "w", encoding="utf-8") as f:
            f.write(textwrap.dedent(f"""
                import json, sys, time
                event = json.loads(sys.stdin.read())
                if event["type"] == "session.status":
                    time.sleep(0.4)
                with open({log!r}, "a", encoding="utf-8") as out:
                    out.write(event["type"] + "\\n")
            """))
        plugin = os.path.join(self.home, "plugin.mjs")
        with open(plugin, "w", encoding="utf-8") as f:
            f.write(opencode.content(types.SimpleNamespace(python=sys.executable, app=app)))
        driver = os.path.join(self.home, "driver.mjs")
        with open(driver, "w", encoding="utf-8") as f:
            f.write(textwrap.dedent(f"""
                import {{ Perturbation }} from {json.dumps(Path(plugin).as_uri())};
                const hooks = await Perturbation({{}});
                await hooks.event({{ event: {{ type: "session.status", properties: {{ sessionID: "s1", status: {{ type: "idle" }} }} }} }});
                await hooks.event({{ event: {{ type: "session.idle", properties: {{ sessionID: "s1" }} }} }});
                await hooks.event({{ event: {{ type: "file.edited", properties: {{ sessionID: "s1" }} }} }});
                await hooks.dispose();
            """))
        subprocess.run([NODE, driver], check=True, timeout=60)
        with open(log, encoding="utf-8") as f:
            self.assertEqual(f.read().split(), ["session.status", "session.idle", "perturbation.shutdown"])


class OpencodeParseTest(IsolatedTestCase):
    def test_session_lifecycle(self):
        created = opencode.parse(None, event("session.created", info={"id": "s1", "directory": "/work/project"}))
        self.assertEqual((created.session_id, created.state, created.project), ("s1", "ready", "project"))
        self.assertIsNone(opencode.parse(None, event("session.created", info={"id": "s2", "parentID": "s1"})))
        self.assertEqual(opencode.parse(None, event("session.status", sessionID="s1", status={"type": "busy"})).state, "busy")
        self.assertEqual(opencode.parse(None, event("session.status", sessionID="s1", status={"type": "retry"})).state, "busy")
        self.assertEqual(opencode.parse(None, event("session.status", sessionID="s1", status={"type": "idle"})).notice, ("ready", "Task finished"))
        self.assertIsNone(opencode.parse(None, event("session.status", sessionID="s1", status={"type": "new"})))
        idle = opencode.parse(None, event("session.idle", sessionID="s1"))
        self.assertEqual((idle.state, idle.notice), ("ready", ("ready", "Task finished")))
        self.assertEqual(opencode.parse(None, event("session.deleted", info={"id": "s1"})).state, None)
        self.assertEqual(opencode.parse(None, event("perturbation.shutdown", sessionID="s1")).state, None)
        self.assertIsNone(opencode.parse(None, event("session.compacted", sessionID="s1")))

    def test_tools_and_permissions(self):
        for kind in ("tool.execute.before", "tool.execute.after", "permission.replied", "message.updated"):
            self.assertEqual(opencode.parse(None, event(kind, sessionID="s1")).state, "busy", kind)
        asked = opencode.parse(None, event("permission.updated", sessionID="s1", type="bash", title="Run: rm -rf build"))
        self.assertEqual((asked.state, asked.notice), ("waiting", ("needs_you", "Run: rm -rf build")))
        self.assertEqual(opencode.parse(None, event("permission.asked", sessionID="s1", type="edit")).notice.message, "Wants to use edit")

    def test_errors(self):
        failed = opencode.parse(None, event("session.error", sessionID="s1", error={"name": "APIError", "data": {"message": "500"}}))
        self.assertEqual((failed.state, failed.notice), ("ready", ("stopped", "APIError: 500")))
        aborted = opencode.parse(None, event("session.error", sessionID="s1", error={"name": "MessageAbortedError"}))
        self.assertEqual((aborted.state, aborted.notice), ("ready", None))
        self.assertIsNone(opencode.parse(None, event("session.error")))  # no session, nothing to record

    def test_unknown_events_and_shapes_are_ignored(self):
        self.assertIsNone(opencode.parse(None, event("file.edited", sessionID="s1")))
        self.assertIsNone(opencode.parse(None, {"type": "session.idle", "properties": "nonsense"}))
        self.assertIsNone(opencode.parse(None, {}))
