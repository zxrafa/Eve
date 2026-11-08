# SPDX-License-Identifier: GPL-3.0-or-later

import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

import os as _os, sys as _sys
_HERE = _os.path.dirname(_os.path.abspath(__file__))
if _HERE not in _sys.path:
    _sys.path.insert(0, _HERE)

from _mod.nup_fixtures import COMPRESSED_SHADER, fixture, snapshot
from _mod.nup_cases import NupExtraCases

EXECUTABLE = None
WORK_DIR = None



class NupExportTests(NupExtraCases, unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="nup-export-", dir=WORK_DIR)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.library = self.root / "library"
        self.library.mkdir()
        self.data, self.payloads, self.catalog_bytes = fixture()
        self.source = self.library / "synthetic.nup"
        self.source.write_bytes(self.data)
        self.counter = 0

    def run_export(self, extra=(), success=True, source=None, output=None):
        source = source or self.source
        self.counter += 1
        output = output or self.root / f"out-{self.counter}"
        original = snapshot(source)
        result = subprocess.run(
            [str(EXECUTABLE), "--input", str(source), "--read-only-root", str(self.library),
             "--output", str(output), *extra],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
        self.assertEqual(result.returncode == 0, success, result.stdout + result.stderr)
        self.assertEqual(snapshot(source), original, "Source size, mtime or SHA-256 changed")
        manifest = output / "manifest.json"
        return json.loads(manifest.read_text(encoding="utf-8")) if manifest.exists() else None, output

    def test_catalog_reads_only_metadata(self):
        manifest, output = self.run_export(["--list"])
        self.assertEqual(manifest["status"], "success")
        self.assertEqual(manifest["exported_files"], 0)
        self.assertEqual([p["kind"] for p in manifest["packages"]], ["base", "update", "addon"])
        self.assertEqual([p["version"] for p in manifest["packages"]], [10, 11, 12])
        self.assertEqual(manifest["packages"][0]["title_name"], "Synthetic package 0")
        self.assertEqual(manifest["packages"][0]["title_id"], "0400000000000000")
        self.assertEqual(manifest["packages"][0]["display_version"], "1.2.3")
        self.assertFalse(manifest["packages"][2]["has_romfs"])
        self.assertEqual(len(manifest["files"]), 6)
        self.assertEqual(manifest["catalog_source_bytes_read"], self.catalog_bytes)
        self.assertEqual(manifest["source_bytes_read"], self.catalog_bytes)
        self.assertEqual(manifest["source"], self.source.resolve().as_posix())
        self.assertFalse((output / "spill").exists())
        self.assertEqual(sorted(p.name for p in output.iterdir()), ["manifest.json"])

    def test_zstd_export_preserves_name_package_and_hash(self):
        manifest, output = self.run_export(["--path", "1:/Shaders/Shader.bfsha"])
        exported = [entry for entry in manifest["files"] if entry.get("exported")]
        self.assertEqual(len(exported), 1)
        self.assertEqual(exported[0]["package"], 1)
        self.assertEqual(exported[0]["path"], "/Shaders/Shader.bfsha")
        self.assertEqual(exported[0]["output"], "packages/1/romfs/Shaders/Shader.bfsha")
        self.assertEqual((output / exported[0]["output"]).read_bytes(), self.payloads[0])
        self.assertEqual(exported[0]["sha256"], hashlib.sha256(self.payloads[0]).hexdigest())
        self.assertEqual(list((output / "spill").iterdir()), [])

    def test_raw_explicit_path_and_candidate_selection(self):
        _, output = self.run_export(["--path", "0:/readme.txt"])
        self.assertEqual((output / "packages/0/romfs/readme.txt").read_bytes(), self.payloads[1])
        manifest, _ = self.run_export(["--candidates"])
        self.assertEqual(manifest["exported_files"], 4)
        self.assertEqual(
            sorted(entry["size"] for entry in manifest["files"] if entry.get("exported")),
            [0, 0, len(self.payloads[0]), len(self.payloads[0])])

    def test_missing_selection_and_export_limits_fail_before_export(self):
        for flags in (
            ["--path", "0:/missing.bin"],
            ["--path", "0:/Shaders/Shader.bfsha", "--max-file-bytes", "10"],
            ["--candidates", "--max-total-bytes", str(len(self.payloads[0]))],
        ):
            with self.subTest(flags=flags):
                manifest, output = self.run_export(flags, success=False)
                self.assertEqual(manifest["status"], "error")
                self.assertTrue(manifest["error"])
                self.assertFalse((output / "packages").exists())

    def test_library_output_and_existing_output_are_rejected(self):
        forbidden = self.library / "must-not-create"
        self.run_export(success=False, output=forbidden)
        self.assertFalse(forbidden.exists())
        _, listing = self.run_export()
        original = (listing / "manifest.json").read_bytes()
        self.run_export(success=False, output=listing)
        self.assertEqual((listing / "manifest.json").read_bytes(), original)

    def test_output_symlink_cannot_enter_library(self):
        link = self.root / "link-to-library"
        try:
            link.symlink_to(self.library, target_is_directory=True)
        except OSError as error:
            if getattr(error, "winerror", None) == 1314:
                self.skipTest("Windows symlink privilege is unavailable")
            raise
        self.run_export(success=False, output=link / "must-not-create")
        self.assertFalse((self.library / "must-not-create").exists())



if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Synthetic NUP read-only/export regressions")
    parser.add_argument("executable", type=Path)
    parser.add_argument("--work-dir", type=Path, help="Existing parent for temporary test files")
    args, unittest_args = parser.parse_known_args()
    EXECUTABLE = args.executable.resolve(strict=True)
    WORK_DIR = args.work_dir.resolve(strict=True) if args.work_dir else None
    unittest.main(argv=[__file__, *unittest_args])
