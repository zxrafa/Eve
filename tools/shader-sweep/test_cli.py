# SPDX-License-Identifier: GPL-3.0-or-later

import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest


BINARY = Path(sys.argv.pop(1)).resolve()

import os as _os, sys as _sys
_HERE = _os.path.dirname(_os.path.abspath(__file__))
if _HERE not in _sys.path:
    _sys.path.insert(0, _HERE)

from _mod.cli_fixtures import (
    MAXWELL_EXIT, NATIVE_EXIT, STAGES, environment, header,
    interface_type, pipeline_key, spirv_instructions,
)
from _mod.cli_cases_oot import OotCliCases
from _mod.cli_cases_core import CoreCliCases


class CliTests(OotCliCases, CoreCliCases, unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.output = self.root / "output.spv"

    def write(self, name, data):
        path = self.root / name
        path.write_bytes(data)
        return path

    def run_cli(self, *args, code=0):
        result = subprocess.run([str(BINARY), *map(str, args)], capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        diagnostic = json.loads(result.stdout)
        self.assertEqual(diagnostic["schema_version"], 1)
        self.assertEqual(diagnostic["status"], "ok" if code == 0 else "error")
        return diagnostic

    def validate(self):
        validator = shutil.which("spirv-val")
        if validator:
            result = subprocess.run([validator, "--target-env", "vulkan1.2", str(self.output)],
                                    capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_lower_only_unknown_stage(self):
        source = self.write("native.bin", NATIVE_EXIT)
        result = self.run_cli(source, "--lower-only", self.output)
        self.assertIsNone(result["stage"])
        self.assertEqual(self.output.read_bytes(), struct.pack("<Q", MAXWELL_EXIT))


    def test_trap_requires_context(self):
        source = self.write("trap.bin", struct.pack("<4I", 0x795C, 0, 0, 0) + NATIVE_EXIT)
        result = self.run_cli(source, "--stage", "compute", "--lower-only", self.output, code=1)
        self.assertEqual(result["phase"], "context")

    def test_output_cannot_overwrite_input(self):
        source = self.write("native.bin", NATIVE_EXIT)
        self.run_cli(source, "--lower-only", source, code=2)
        self.assertEqual(source.read_bytes(), NATIVE_EXIT)

    def test_static_and_dynamic_vertex_types(self):
        ald = 0xEFD8000000070000 | (255 << 8) | (128 << 20) | (255 << 39)
        ast = 0xEFF0000000070000 | (255 << 8) | (112 << 20) | (255 << 39)
        capture = self.write("vertex.env", environment(47, 0, (ald, ast, MAXWELL_EXIT)))
        for dynamic in (False, True):
            for raw, expected in ((1, "float"), (2, "signed"), (3, "unsigned")):
                with self.subTest(dynamic=dynamic, expected=expected):
                    key = pipeline_key(raw1=1 << 5, dynamic_type=raw) if dynamic else pipeline_key(attribute={1: 7, 2: 3, 3: 4}[raw])
                    path = self.write("pipeline.key", key)
                    self.run_cli("--environment", capture, "--cache-version", 47, "--pipeline-key", path, "--output", self.output)
                    self.assertEqual(interface_type(self.output.read_bytes(), 1), expected)
                    self.validate()

    def test_fragment_attachment_types(self):
        capture = self.write("fragment.env", environment(47, 4))
        for color, expected in ((0xD5, "float"), (0xD8, "signed"), (0xD9, "unsigned")):
            with self.subTest(expected=expected):
                key = self.write("pipeline.key", pipeline_key(color=color))
                self.run_cli("--environment", capture, "--cache-version", 47, "--pipeline-key", key, "--output", self.output)
                self.assertEqual(interface_type(self.output.read_bytes(), 3), expected)
                self.validate()

    def test_missing_constant_value_is_context_error(self):
        mov = 0x4C98000000070000 | (15 << 39) | (1 << 34) | (0x10 << 20)
        ast = 0xEFF0000000070000 | (255 << 8) | (112 << 20) | (255 << 39)
        capture = self.write("vertex.env", environment(47, 0, (mov, ast, MAXWELL_EXIT)))
        result = self.run_cli("--environment", capture, "--cache-version", 47, "--output", self.output, code=1)
        self.assertEqual(result["phase"], "context")
        self.assertIn("constant buffer", result["error"]["message"])

    def test_static_allocation_uses_runtime_capture_boundary(self):
        source = self.write("allocation.bin", header(0) + bytes(48) + NATIVE_EXIT + bytes(256))
        result = self.run_cli(source, "--format", "native-header", "--capture-extent",
                              "--lower-only", self.output)
        self.assertEqual(result["source_bytes"], 16)
        self.assertEqual(result["allocation_bytes"], 272)

    def test_static_allocation_does_not_guess_a_missing_branch_target(self):
        branch = struct.pack("<4I", 0x7947, 0x80, 0x03800000, 0)
        source = self.write("allocation.bin", header(0) + bytes(48) + branch + NATIVE_EXIT)
        result = self.run_cli(source, "--format", "native-header", "--capture-extent",
                              "--lower-only", self.output, code=1)
        self.assertEqual(result["phase"], "context")
        self.assertIn("complete runtime capture", result["error"]["message"])


if __name__ == "__main__":
    unittest.main()
