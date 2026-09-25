import json
import threading

from perturbation import config, host, paths
from tests.support import IsolatedTestCase


class SaveTest(IsolatedTestCase):
    def test_a_reader_never_sees_half_a_file(self):
        """The whole point of replacing rather than rewriting: no reader gets the defaults by accident."""
        config.save({"agents": ["claude"]})
        seen = []
        stop = threading.Event()

        def write():
            agents = (["claude"], ["codex"])
            index = 0
            while not stop.is_set():
                config.save({"agents": agents[index % 2], "notifications": True})
                index += 1

        writer = threading.Thread(target=write)
        writer.start()
        try:
            for _ in range(400):
                seen.append(tuple(config.load()["agents"]))
        finally:
            stop.set()
            writer.join()
        self.assertEqual(set(seen) - {("claude",), ("codex",)}, set())

    def test_nothing_is_left_beside_the_file(self):
        config.save({"agents": ["claude"]})
        self.assertEqual([p.name for p in paths.data_dir().glob("config.json*")], ["config.json"])

    def test_a_missing_file_is_not_damaged(self):
        self.assertFalse(paths.config_file().exists())
        self.assertFalse(config.damaged())
        self.assertEqual(config.load()["agents"], [])

    def test_a_damaged_file_is_reported_and_readers_fall_back(self):
        paths.data_dir().mkdir(parents=True, exist_ok=True)
        paths.config_file().write_text("{ half a fi", encoding="utf-8")
        self.assertTrue(config.damaged())
        self.assertEqual(config.load()["agents"], [])  # readers keep working
        paths.config_file().write_text("[1, 2]", encoding="utf-8")
        self.assertTrue(config.damaged())  # valid JSON, but not settings


class PopupWriteTest(IsolatedTestCase):
    def test_the_popup_never_writes_over_a_file_it_could_not_read(self):
        paths.data_dir().mkdir(parents=True, exist_ok=True)
        paths.config_file().write_text("{ half a fi", encoding="utf-8")
        self.assertFalse(host.handle({"type": "mute", "id": "claude", "muted": True}))
        self.assertEqual(paths.config_file().read_text(), "{ half a fi")

    def test_two_popups_do_not_lose_each_others_change(self):
        """One host runs per browser, so a mute from one and a reorder from another can collide."""
        for _ in range(25):
            config.save({"agents": ["claude"], "mute": {}, "order": []})
            start = threading.Barrier(2)
            messages = ({"type": "mute", "id": "claude", "muted": True}, {"type": "order", "ids": ["codex", "claude"]})

            def send(message):
                start.wait()
                host.handle(message)

            threads = [threading.Thread(target=send, args=(m,)) for m in messages]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            settings = config.load()
            self.assertEqual((settings["mute"], settings["order"]), ({"claude": True}, ["codex", "claude"]))

    def test_the_lock_file_lives_beside_the_sessions_not_among_them(self):
        config.save({"agents": ["claude"]})
        host.handle({"type": "mute", "id": "claude", "muted": True})
        self.assertTrue((paths.data_dir() / "locks" / "config.lock").is_file())
        self.assertFalse((paths.sessions_dir() / "config").exists())
