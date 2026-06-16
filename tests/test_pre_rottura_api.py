import json
import os
import tempfile
import unittest

from api import pre_rottura as EP


class TestPreRotturaApi(unittest.TestCase):
    def setUp(self):
        self._root = EP.ROOT
        self._rel = EP.REL_PATH
        self.tmp = tempfile.mkdtemp()
        EP.ROOT = self.tmp
        EP.REL_PATH = "snap.json"

    def tearDown(self):
        EP.ROOT = self._root
        EP.REL_PATH = self._rel

    def _snap_path(self):
        return os.path.join(self.tmp, EP.REL_PATH)

    def test_load_latest_reads_snapshot(self):
        sample = {"ok": True, "kind": "pre_rottura", "riprese": [], "rientri": []}
        with open(self._snap_path(), "w", encoding="utf-8") as f:
            json.dump(sample, f)
        loaded = EP._load_latest()
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["kind"], "pre_rottura")

    def test_load_latest_missing_returns_none(self):
        # nessun file scritto -> None
        self.assertIsNone(EP._load_latest())

    def test_load_latest_corrupt_returns_none(self):
        with open(self._snap_path(), "w", encoding="utf-8") as f:
            f.write("{ non-json")
        self.assertIsNone(EP._load_latest())


if __name__ == "__main__":
    unittest.main()
