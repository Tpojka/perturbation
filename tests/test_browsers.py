import io
import sys
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from perturbation import HOST_NAME, browsers, config, install
from perturbation.browsers import base
from perturbation.browsers.base import running_hosts as real_running_hosts
from perturbation.install import system
from tests.support import IsolatedTestCase

PS = b"""\
  100     1 /Applications/Google Chrome.app/Contents/MacOS/Google Chrome --enable-features=x
  101   100 /usr/bin/python3 /data/perturbation.pyz host chrome-extension://abc/
  200     1 /Applications/Chromium.app/Contents/MacOS/Chromium
  201   200 /usr/bin/python3 /data/perturbation.pyz host
  300   299 /usr/bin/python3 /data/perturbation.pyz host
  400     1 /usr/bin/python3 /data/perturbation.pyz hook claude
"""


class RegistryTest(IsolatedTestCase):
    def test_every_browser_implements_the_contract(self):
        known = browsers.known()
        self.assertEqual([b.ID for b in known], ["chrome", "edge", "brave", "opera", "vivaldi", "arc", "chromium"])
        self.assertEqual(len({b.ORDER for b in known}), len(known))
        for module in known:
            base.check(module)
            self.assertTrue(module.PAGE.endswith("://extensions"), module.ID)
            self.assertEqual(module.APPS.keys() - {"darwin", "linux", "win32"}, set())

    def test_a_browser_without_a_build_here_is_not_offered(self):
        arc = browsers.get("arc")
        self.assertEqual(base.supported(arc), sys.platform == "darwin")
        self.assertEqual(arc in browsers.supported(), sys.platform == "darwin")
        if sys.platform != "darwin":
            self.assertIsNone(base.detect(arc))

    def test_some_keeps_registry_order_and_ignores_strangers(self):
        self.assertEqual([b.ID for b in browsers.some(["brave", "chrome", "nobody"])], ["chrome", "brave"])


class DetectionTest(IsolatedTestCase):
    def test_a_profile_alone_is_reported_as_a_leftover(self):
        profile = base.profile_dir(browsers.get("brave"))
        if profile is None:
            return self.skipTest("Brave keeps no profile path on this OS")
        profile.mkdir(parents=True)
        self.assertIn("(profile only)", base.detect(browsers.get("brave")))
        self.assertEqual(list(browsers.detected()), ["brave"])

    def test_a_leftover_profile_is_listed_but_never_pre_checked(self):
        profile = base.profile_dir(browsers.get("brave"))
        if profile is None:
            return self.skipTest("Brave keeps no profile path on this OS")
        profile.mkdir(parents=True)
        self.assertIn("brave", browsers.detected())
        self.assertNotIn("brave", browsers.installed())
        self.assertEqual(install._browsers_now(), ["chrome"])

    def test_the_application_itself_wins(self):
        if sys.platform == "darwin":
            app = Path(self.home) / "Applications" / "Brave Browser.app"
            app.mkdir(parents=True)
        elif sys.platform == "linux":
            app = Path(self.home) / "brave-browser"
            app.write_text("#!/bin/sh\n")
            mock.patch("shutil.which", side_effect=lambda n, *a, **k: str(app) if n == "brave-browser" else None).start()
            self.addCleanup(mock.patch.stopall)
        else:
            return self.skipTest("Windows finds browsers through the registry")
        base.profile_dir(browsers.get("brave")).mkdir(parents=True)
        self.assertNotIn("profile only", base.detect(browsers.get("brave")))


class RegistrationTest(IsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.addCleanup(system.unregister_host)

    def install(self, *args):
        with redirect_stdout(io.StringIO()) as out:
            install.main(list(args))
        return out.getvalue()

    def test_one_registration_per_chosen_browser(self):
        out = self.install("1", "--agents=", "--browsers", "chrome,brave")
        self.assertEqual([b.ID for b, _ in system.registrations()], ["chrome", "brave"])
        self.assertIn("Native host registered for Google Chrome", out)
        self.assertIn("Native host registered for Brave", out)
        self.assertIn("brave://extensions", out)  # each browser is told where to load the extension
        self.assertEqual(config.load()["browsers"], ["chrome", "brave"])
        for _, path in system.registrations():
            self.assertEqual(path.name, f"{HOST_NAME}.json")

    def test_dropping_a_browser_takes_its_registration_away(self):
        self.install("1", "--agents=", "--browsers", "chrome,brave")
        out = self.install("set", "browsers", "chrome")
        self.assertIn("Registration removed", out)
        self.assertEqual([b.ID for b, _ in system.registrations()], ["chrome"])
        self.assertEqual(config.load()["browsers"], ["chrome"])

    def test_chrome_alone_is_the_default_and_all_means_every_supported_one(self):
        self.install("1", "--agents=")
        self.assertEqual(config.load()["browsers"], ["chrome"])
        self.install("1", "--agents=", "--browsers", "all")
        self.assertEqual(config.load()["browsers"], [b.ID for b in browsers.supported()])

    def test_a_later_run_keeps_the_browsers_already_chosen(self):
        self.install("1", "--agents=", "--browsers", "brave")
        self.install("1", "--agents=")
        self.assertEqual(config.load()["browsers"], ["brave"])

    def test_an_install_from_before_browsers_were_asked_about_keeps_working(self):
        self.install("1", "--agents=", "--browsers", "chrome")
        settings = config.load()
        del settings["browsers"]  # a config.json written by 1.2.x
        config.save(settings)
        self.install("1", "--agents=")
        self.assertEqual(config.load()["browsers"], ["chrome"])

    def test_a_browser_running_a_host_is_kept_even_without_a_registration(self):
        self.install("1", "--agents=", "--browsers", "chrome")
        settings = config.load()
        del settings["browsers"]  # nothing recorded, so the machine has to be read
        config.save(settings)
        with mock.patch("perturbation.browsers.base.running_hosts", return_value=[(browsers.get("brave"), 42)]):
            self.assertEqual(install._browsers_now(), ["chrome", "brave"])

    def test_unknown_browsers_are_refused(self):
        with self.assertRaises(SystemExit):
            self.install("1", "--agents=", "--browsers", "chrome,netscape")
        with self.assertRaises(SystemExit):
            self.install("set", "browsers", "netscape")

    def test_the_doctor_names_a_left_over_registration(self):
        from perturbation.install import doctor

        self.install("1", "--agents=", "--browsers", "chrome,brave")
        settings = config.load()
        settings["browsers"] = ["chrome"]  # unticked in config, but the file is still there
        config.save(settings)
        failures = [c.text for _, checks in doctor.checks() for c in checks if not c.ok]
        self.assertTrue(any("left-over registration" in f for f in failures), failures)

    def test_uninstall_sweeps_every_browser(self):
        self.install("1", "--agents=", "--browsers", "all")
        self.install("uninstall")
        self.assertEqual(system.registrations(), [])


class RunningHostsTest(IsolatedTestCase):
    def test_each_host_is_named_after_the_browser_that_started_it(self):
        if sys.platform == "win32":
            return self.skipTest("the process table is not read on Windows")
        with mock.patch("subprocess.run", return_value=mock.Mock(stdout=PS)):
            found = real_running_hosts()
        self.assertEqual(sorted((b.ID if b else "", pid) for b, pid in found), [("", 300), ("chrome", 101), ("chromium", 201)])

    def test_the_longest_name_wins_so_chrome_is_not_chromium(self):
        self.assertEqual(base.owner("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome").ID, "chrome")
        self.assertEqual(base.owner("/Applications/Chromium.app/Contents/MacOS/Chromium").ID, "chromium")
        self.assertIsNone(base.owner("/usr/bin/firefox"))
