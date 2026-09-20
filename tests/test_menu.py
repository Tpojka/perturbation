import io
from contextlib import redirect_stdout
from unittest import mock

from perturbation import agents
from perturbation.install import menu
from tests.support import IsolatedTestCase

ADAPTERS = agents.registered()
NONE = {}


class AgentMenuTest(IsolatedTestCase):
    def test_all_seven_are_listed_alike_by_default(self):
        picker = menu.AgentMenu(ADAPTERS, {"claude"}, NONE)
        self.assertTrue(picker.expanded)
        self.assertEqual(picker.numbers(), 7)
        self.assertEqual(len(picker.lines()), 7)
        self.assertTrue(picker.lines()[6].startswith("  [ ] 7) Qwen Code"))
        self.assertNotIn("+ shows more", picker.prompt())

    def test_free_tier_can_still_be_folded_on_request(self):
        picker = menu.AgentMenu(ADAPTERS, {"claude"}, NONE, fold_free=True)
        self.assertFalse(picker.expanded)
        self.assertEqual(picker.numbers(), 4)
        lines = picker.lines()
        self.assertEqual(len(lines), 5)
        self.assertTrue(lines[0].startswith("> [x] 1) Claude Code"))
        self.assertIn("+) 3 more, free tier: opencode, Goose, Qwen Code", lines[4])
        self.assertIn("+ shows more", picker.prompt())
        picker.key("+")
        self.assertTrue(picker.expanded)
        self.assertEqual(len(picker.lines()), 7)
        self.assertNotIn("+ shows more", picker.prompt())

    def test_a_free_agent_on_the_machine_or_already_watched_unfolds_the_tier(self):
        self.assertTrue(menu.AgentMenu(ADAPTERS, set(), {"goose": "found goose on PATH"}, fold_free=True).expanded)
        self.assertTrue(menu.AgentMenu(ADAPTERS, {"qwen"}, NONE, fold_free=True).expanded)
        self.assertTrue(menu.AgentMenu(ADAPTERS, set(), NONE).expanded)
        self.assertFalse(menu.AgentMenu(ADAPTERS, set(), {"claude": "found ~/.claude"}, fold_free=True).expanded)

    def test_numbers_toggle_and_reveal(self):
        picker = menu.AgentMenu(ADAPTERS, set(), NONE, fold_free=True)
        picker.key("2")
        picker.key("5")  # a folded agent: the tier unfolds and the agent is checked
        self.assertTrue(picker.expanded)
        self.assertEqual(picker.result(), ["codex", "opencode"])
        picker.key("2")
        picker.key("9")  # no such agent
        self.assertEqual(picker.result(), ["opencode"])

    def test_cursor_and_space(self):
        picker = menu.AgentMenu(ADAPTERS, set(), NONE, fold_free=True)
        picker.key("up")  # already at the top
        self.assertEqual(picker.cursor, 0)
        picker.key("space")
        picker.key("down")
        picker.key("j")
        picker.key("space")
        self.assertEqual(picker.result(), ["claude", "copilot"])
        for _ in range(10):
            picker.key("down")
        self.assertEqual(picker.cursor, 4)  # the "more" row is the last one while folded
        picker.key("space")  # on the "more" row: unfolds, nothing toggled
        self.assertTrue(picker.expanded)
        self.assertEqual(picker.result(), ["claude", "copilot"])
        picker.key("down")
        picker.key("down")
        picker.key("space")
        self.assertEqual(picker.result(), ["claude", "copilot", "qwen"])
        picker.key("k")
        picker.key("space")
        self.assertEqual(picker.result(), ["claude", "copilot", "goose", "qwen"])

    def test_all_none_confirm_cancel(self):
        picker = menu.AgentMenu(ADAPTERS, set(), NONE)
        picker.key("a")
        self.assertEqual(picker.result(), ["claude", "codex", "copilot", "antigravity", "opencode", "goose", "qwen"])
        picker.key("n")
        self.assertEqual(picker.result(), [])
        self.assertEqual(picker.key("enter"), menu.CONFIRM)
        self.assertEqual(picker.key("esc"), menu.CANCEL)
        self.assertEqual(picker.key("q"), menu.CANCEL)
        self.assertIsNone(picker.key("x"))


class PickerTest(IsolatedTestCase):
    def pick(self, keys, fold_free=False):
        with mock.patch("perturbation.install.menu.interactive", return_value=True):
            with mock.patch("perturbation.install.menu.read_key", side_effect=keys):
                with redirect_stdout(io.StringIO()) as out:
                    result = menu.choose_agents(ADAPTERS, {"claude"}, {"claude": "found ~/.claude"}, fold_free)
        return result, out.getvalue()

    def test_keys_drive_the_picker(self):
        result, out = self.pick(["down", "space", "+", "7", "enter"])
        self.assertEqual(result, ["claude", "codex", "qwen"])
        self.assertIn("\x1b[", out)  # redrawn in place
        self.assertIn("Space or 1-7 toggles", out)

    def test_cancel_and_interrupt(self):
        self.assertIsNone(self.pick(["space", "esc"])[0])
        self.assertIsNone(self.pick([KeyboardInterrupt()])[0])

    def test_lines_drive_the_picker_outside_a_terminal(self):
        with mock.patch("perturbation.install.menu.interactive", return_value=False):
            with mock.patch("builtins.input", side_effect=["2", "6", ""]):
                with redirect_stdout(io.StringIO()) as out:
                    result = menu.choose_agents(ADAPTERS, {"claude"}, NONE)
        self.assertEqual(result, ["claude", "codex", "goose"])
        self.assertIn("  [x] 1) Claude Code", out.getvalue())
        self.assertNotIn(">", out.getvalue())
        with mock.patch("perturbation.install.menu.interactive", return_value=False):
            with mock.patch("builtins.input", side_effect=["q"]):
                with redirect_stdout(io.StringIO()):
                    self.assertIsNone(menu.choose_agents(ADAPTERS, set(), NONE))

    def test_interactive_needs_a_terminal_on_both_ends(self):
        with mock.patch("sys.stdin") as stdin, mock.patch("sys.stdout") as stdout:
            stdin.isatty.return_value = True
            stdout.isatty.return_value = False
            self.assertFalse(menu.interactive())
            stdout.isatty.return_value = True
            with mock.patch.dict("os.environ", {"TERM": "xterm"}):
                self.assertTrue(menu.interactive())
            with mock.patch.dict("os.environ", {"PERTURBATION_PLAIN_MENU": "1"}):
                self.assertFalse(menu.interactive())
