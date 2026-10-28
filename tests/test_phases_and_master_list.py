"""Phases start empty and carry their own office name and master list."""

import io
import os
import tempfile
import unittest
from datetime import date
from unittest import mock

import pandas as pd

from reporting.infrastructure import master_reference_repository as masters
from reporting.infrastructure import phase_repository as phases
from reporting.infrastructure import storage

MASTER = pd.DataFrame([
    {"District": "North", "Zone": "Hilltop", "Center": "Hilltop School"},
    {"District": "North", "Zone": "Hilltop", "Center": "River Clinic"},
    {"District": "South", "Zone": "Lakeview", "Center": "Lakeview Market"},
])


def _xlsx_bytes(df: pd.DataFrame) -> bytes:
    buffer = io.BytesIO()
    df.to_excel(buffer, index=False)
    return buffer.getvalue()


class PhaseRepositoryTests(unittest.TestCase):
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

    def test_starts_with_no_phase(self):
        self.assertIsNone(phases.get_active_phase())
        self.assertEqual(phases.list_phases(), [])
        self.assertEqual(phases.load_zone_assignments(), {})
        self.assertEqual(phases.load_center_assignments(), [])

    def test_first_phase_is_active_and_keeps_office_and_master_file(self):
        created = phases.create_phase(
            "Phase 1", date(2026, 7, 1), date(2026, 7, 10),
            office_name="Lakeside Office",
            master_bytes=_xlsx_bytes(MASTER), master_filename="centres.xlsx",
        )
        active = phases.get_active_phase()
        self.assertEqual(active["id"], created["id"])
        self.assertEqual(active["office_name"], "Lakeside Office")
        name = active["master_path"]
        master = masters.load_master(file_bytes=phases.read_master_file(name), filename=name)
        self.assertEqual(len(master), 3)
        self.assertIn("Zone_norm", master.columns)

    def test_replacing_and_deleting_master_file(self):
        created = phases.create_phase(
            "Phase 1", date(2026, 7, 1), date(2026, 7, 10),
            master_bytes=MASTER.to_csv(index=False).encode(), master_filename="list.csv",
        )
        old_file = os.path.join(self.root, phases.get_active_phase()["master_path"])
        phases.update_phase(created["id"], master_bytes=_xlsx_bytes(MASTER),
                            master_filename="list.xlsx", office_name="New Office")
        phase = phases.get_active_phase()
        self.assertFalse(os.path.exists(old_file))
        new_file = os.path.join(self.root, phase["master_path"])
        self.assertTrue(new_file.endswith(".xlsx") and os.path.exists(new_file))
        self.assertEqual(phase["office_name"], "New Office")

        ok, _ = phases.delete_phase(created["id"])
        self.assertTrue(ok)
        self.assertIsNone(phases.get_active_phase())
        self.assertFalse(os.path.exists(new_file))

    def test_rejects_other_file_types(self):
        with self.assertRaises(ValueError):
            phases.create_phase("P", date(2026, 7, 1), date(2026, 7, 2),
                                master_bytes=b"x", master_filename="list.pdf")


class MasterListTests(unittest.TestCase):
    def test_accepts_centre_spelling_and_drops_blank_rows(self):
        df = pd.DataFrame({
            " district ": ["North", "North"],
            "ZONE": ["Hilltop", ""],
            "Centre": ["Hilltop School", "Nowhere"],
        })
        data = masters.read_master_upload(_xlsx_bytes(df), "list.xlsx")
        self.assertEqual(list(data.columns), ["District", "Zone", "Center"])
        self.assertEqual(len(data), 1)

    def test_missing_columns_are_reported(self):
        df = pd.DataFrame({"Zone": ["Hilltop"]})
        with self.assertRaises(masters.MasterListError) as err:
            masters.read_master_upload(df.to_csv(index=False).encode(), "list.csv")
        self.assertIn("District", str(err.exception))

    def test_linked_sheet_takes_priority_over_file(self):
        with mock.patch.object(masters, "fetch_google_sheet", return_value=MASTER) as fetch:
            data = masters.load_master(
                sheet_url="https://example.com/sheet", file_bytes=b"x", filename="list.csv"
            )
        fetch.assert_called_once()
        self.assertEqual(len(data), 3)

    def test_unreachable_sheet_and_no_source_raise_master_list_error(self):
        with mock.patch.object(masters, "fetch_google_sheet", side_effect=RuntimeError("offline")):
            with self.assertRaises(masters.MasterListError):
                masters.load_master(sheet_url="https://example.com/sheet")
        with self.assertRaises(masters.MasterListError):
            masters.load_master()


if __name__ == "__main__":
    unittest.main()
