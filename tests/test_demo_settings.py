"""Settings-driven setup for hosted and demo deployments."""

import json
import os
import tempfile
import unittest
from unittest import mock

from reporting.infrastructure import google_sheets, storage
from reporting.infrastructure import master_reference_repository as masters
from reporting.infrastructure import phase_repository as phases
from reporting.presentation import auth

INITIAL = {
    "office_name": "Lakeside District Registration Office (Demo)",
    "title": "Outreach phase 1",
    "start_date": "2026-07-06",
    "end_date": "2026-07-15",
    "response_sheet_url": "examples/demo/responses.csv",
    "master_sheet_url": "examples/demo/master_list.csv",
}


class InitialPhaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self.patches = [
            mock.patch.object(storage, "PROJECT_ROOT", self.root),
            mock.patch.dict(os.environ, {"MONGODB_URI": "", "DEMO_MODE": ""}),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def test_initial_phase_setting_creates_the_first_phase(self):
        with mock.patch.dict(os.environ, {"initial_phase": json.dumps(INITIAL)}):
            phase = phases.get_active_phase()
        self.assertEqual(phase["office_name"], INITIAL["office_name"])
        self.assertEqual(phase["google_sheet_url"], INITIAL["response_sheet_url"])
        self.assertTrue(os.path.exists(os.path.join(self.root, "phases.json")))

    def test_existing_phases_win_over_the_setting(self):
        with mock.patch.dict(os.environ, {"initial_phase": json.dumps(INITIAL)}):
            phases.get_active_phase()
            phases.update_active_phase(title="Renamed")
            self.assertEqual(phases.get_active_phase()["title"], "Renamed")

    def test_invalid_setting_is_ignored(self):
        bad = dict(INITIAL, start_date="not a date")
        with mock.patch.dict(os.environ, {"initial_phase": json.dumps(bad)}):
            self.assertIsNone(phases.get_active_phase())


class AdminPinSettingTests(unittest.TestCase):
    def test_admin_pin_setting_replaces_stored_pin(self):
        with mock.patch.dict(os.environ, {"ADMIN_PIN": "2468"}):
            self.assertTrue(auth.verify_pin("2468"))
            self.assertFalse(auth.verify_pin("1234"))
            self.assertFalse(auth.is_default_pin_active())
            with self.assertRaises(RuntimeError):
                auth.set_pin("9999")


class DemoDataTests(unittest.TestCase):
    def test_project_csv_files_load_and_outside_paths_do_not(self):
        responses = google_sheets.fetch_google_sheet("examples/demo/responses.csv")
        self.assertGreater(len(responses), 250)
        master = masters.load_master(sheet_url="examples/demo/master_list.csv")
        self.assertEqual(len(master), 33)
        self.assertIsNone(google_sheets._direct_csv_source("../outside.csv"))


if __name__ == "__main__":
    unittest.main()
