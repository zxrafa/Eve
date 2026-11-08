# SPDX-License-Identifier: GPL-3.0-or-later

from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib

from shader_archive import ArchiveError
from shader_containers import dcx_decompress, lz4_block, parse_bnd4, parse_cgsb, parse_shn


import os as _os, sys as _sys
_HERE = _os.path.dirname(_os.path.abspath(__file__))
if _HERE not in _sys.path:
    _sys.path.insert(0, _HERE)

from _mod.container_cases import ContainerExtraTests, cgsb, graphics, literals


class ContainerTests(ContainerExtraTests, unittest.TestCase):
    def test_lz4_literals_and_overlapping_matches(self):
        for data in (b"", b"abc", b"x" * 600):
            self.assertEqual(lz4_block(literals(data), len(data)), data)
        self.assertEqual(lz4_block(b"\x13a\x01\x00", 8), b"a" * 8)
        for data, size in ((b"\x00\x00\x00", 4), (b"\xf0", 15), (b"\x20a", 2), (b"\x10a", 0)):
            with self.assertRaises(ArchiveError):
                lz4_block(data, size)

    def test_cgsb_vertex_and_fragment_have_independent_stage_bits(self):
        for stage, name in ((0, "vertex"), (4, "fragment")):
            records = parse_cgsb(cgsb(stage))
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["stage"], name)
            self.assertEqual(records[0]["code"], graphics(stage))

    def test_cgsb_rejects_bad_extents_and_stage_conflicts(self):
        source = cgsb()
        for size in (0, 23, 103, len(source) - 1):
            with self.assertRaises(ArchiveError):
                parse_cgsb(source[:size])
        data = bytearray(source)
        struct.pack_into("<H", data, 10, 4)
        with self.assertRaises(ArchiveError):
            parse_cgsb(data)

    def test_cgsb_preserves_mesh_allocation_without_assuming_vertex_header(self):
        data = bytearray(cgsb())
        struct.pack_into("<H", data, 10, 7)
        record, = parse_cgsb(data)
        self.assertEqual(record["stage"], "mesh")
        self.assertEqual(record["envelope"], "unverified-mesh")
        self.assertEqual(record["code"], graphics(0))
        self.assertEqual(record["code_offset"], 104)
        self.assertEqual(record["control_offset"], 104 + len(graphics(0)))

    def test_dcx_declared_size_and_stream_bounds(self):
        raw = b"bounded shader fixture" * 20
        compressed = zlib.compress(raw)
        header = bytearray(76)
        header[:4] = b"DCX\0"
        struct.pack_into(">I", header, 20, 76)
        header[24:28] = b"DCS\0"
        struct.pack_into(">II", header, 28, len(raw), len(compressed))
        header[36:44] = b"DCP\0DFLT"
        self.assertEqual(dcx_decompress(header + compressed), raw)
        struct.pack_into(">I", header, 28, len(raw) - 1)
        with self.assertRaises(ArchiveError):
            dcx_decompress(header + compressed)

    def test_binder_preserves_names_and_payloads(self):
        payload = cgsb(4)
        name = "fragment.ppo".encode("utf-16-le") + bytes(2)
        offset = 100 + len(name)
        header = bytearray(64)
        header[:4] = b"BND4"
        header[10] = 1
        struct.pack_into("<I", header, 12, 1)
        struct.pack_into("<Q", header, 16, 64)
        struct.pack_into("<Q", header, 32, 36)
        header[48:52] = b"\1t\0\0"
        record = b"\x40\0\0\0\xff\xff\xff\xff" + struct.pack("<QQIII", len(payload), len(payload), offset, 0, 100)
        self.assertEqual(parse_bnd4(header + record + name + payload), [("fragment.ppo", payload)])



if __name__ == "__main__":
    unittest.main()
