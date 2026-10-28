"""Saving to local files or MongoDB, and keeping the demo off the database."""

import os
import tempfile
import unittest
from datetime import date
from unittest import mock

from reporting.infrastructure import config_repository, storage
from reporting.infrastructure import phase_repository as phases
from reporting.presentation import auth

MASTER_CSV = b"District,Zone,Center\nNorth,Hilltop,Hilltop School\n"


class MongoStorageTests(unittest.TestCase):
    def setUp(self):
        storage._client.cache_clear()
        self.tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {
            "MONGODB_URI": "mongomock://test", "MONGODB_DB": "nrbc_test", "DEMO_MODE": "",
        })
        self.root = mock.patch.object(storage, "PROJECT_ROOT", self.tmp.name)
        self.env.start()
        self.root.start()

    def tearDown(self):
        self.root.stop()
        self.env.stop()
        self.tmp.cleanup()
        storage._client.cache_clear()

    def test_mongodb_is_used_when_uri_is_set(self):
        self.assertIsInstance(storage.get_store(), storage.MongoStore)

    def test_phases_master_lists_and_corrections_live_in_mongodb(self):
        created = phases.create_phase(
            "Phase 1", date(2026, 7, 1), date(2026, 7, 10), office_name="Lakeside Office",
            master_bytes=MASTER_CSV, master_filename="list.csv",
        )
        phases.save_zone_assignment("St. Mary's $zone", "HILLTOP")  # awkward characters

        db = storage._client("mongomock://test")["nrbc_test"]
        self.assertIsNotNone(db.settings.find_one({"_id": "phases"}))
        self.assertEqual(phases.read_master_file(created["master_path"]), MASTER_CSV)
        self.assertEqual(phases.load_zone_assignments(), {"St. Mary's $zone": "HILLTOP"})
        self.assertEqual(os.listdir(self.tmp.name), [])  # nothing written locally

    def test_pin_and_column_mapping_live_in_mongodb(self):
        auth.set_pin("5678")
        config = config_repository.load_config()
        config["column_mapping"] = {"Centre Name.": "CENTER NAME"}
        config_repository.save_config(config)
        self.assertTrue(auth.verify_pin("5678"))
        self.assertEqual(config_repository.load_config()["column_mapping"],
                         {"Centre Name.": "CENTER NAME"})

    def test_database_errors_are_raised_not_treated_as_empty(self):
        broken = mock.Mock(side_effect=ConnectionError("no route"))
        store = storage.get_store()
        with mock.patch.object(store.db.settings, "find_one", broken), \
                mock.patch.object(storage, "get_store", return_value=store):
            with self.assertRaises(storage.StorageError):
                config_repository.load_config()
            with self.assertRaises(storage.StorageError):
                phases.get_active_phase()


class DemoNeverUsesDatabaseTests(unittest.TestCase):
    def test_demo_mode_ignores_mongodb_uri(self):
        env = {"MONGODB_URI": "mongodb+srv://user:pw@real-cluster.example/", "DEMO_MODE": "true"}
        with mock.patch.dict(os.environ, env), \
                mock.patch.object(storage, "_client", side_effect=AssertionError("connected")):
            self.assertIsInstance(storage.get_store(), storage.FileStore)

    def test_files_are_the_default(self):
        with mock.patch.dict(os.environ, {"MONGODB_URI": "", "DEMO_MODE": ""}):
            self.assertIsInstance(storage.get_store(), storage.FileStore)


if __name__ == "__main__":
    unittest.main()
