#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later

import base64
import io
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import unittest

import debug_mcp

HERE = os.path.dirname(os.path.abspath(__file__))

import os as _os, sys as _sys
_HERE = _os.path.dirname(_os.path.abspath(__file__))
if _HERE not in _sys.path:
    _sys.path.insert(0, _HERE)

from _mod.fake_debug_emu import AdapterTestBase, FakeEmulator, PNG, PNG_BYTES
from _mod.debug_mcp_cases_extra import AdapterExtraCases


class AdapterTest(AdapterExtraCases, AdapterTestBase):
    def test_initialize_and_list(self):
        reply = self.adapter.handle({"jsonrpc": "2.0", "id": 0, "method": "initialize",
                                     "params": {"protocolVersion": "2025-03-26"}})
        self.assertEqual(reply["result"]["protocolVersion"], "2025-03-26")
        self.assertIn("tools", reply["result"]["capabilities"])
        newer = self.adapter.handle({"id": 0, "method": "initialize",
                                     "params": {"protocolVersion": "2099-01-01"}})
        self.assertEqual(newer["result"]["protocolVersion"], debug_mcp.PROTOCOL_VERSIONS[0])
        self.assertIsNone(self.adapter.handle({"method": "notifications/initialized"}))
        names = [tool["name"] for tool in self.adapter.handle({"id": 2, "method": "tools/list"})
                 ["result"]["tools"]]
        self.assertEqual(names, ["status", "screenshot", "log_tail", "log_filter", "capture_frame",
                                 "capture_image", "reject_shaders", "sample", "read_memory",
                                 "search_memory", "read_gpu_memory", "input",
                                 "input_sequence"])
        self.assertEqual(self.adapter.handle({"id": 3, "method": "bogus"})["error"]["code"], -32601)

    def test_status_is_forwarded(self):
        result = self.call("status", {"fps_window_ms": 0})
        self.assertFalse(result["isError"])
        self.assertEqual(json.loads(result["content"][0]["text"])["title"], "Test")
        self.assertEqual(self.fake.requests[-1]["params"], {"fps_window_ms": 0})

    def test_memory_reads_are_forwarded(self):
        arguments = {"address": "0x8000001000", "size": 4, "as": "hex"}
        result = self.call("read_memory", arguments)
        self.assertFalse(result["isError"])
        self.assertEqual(json.loads(result["content"][0]["text"])["hex"], "0000803f")
        self.assertEqual(self.fake.requests[-1]["params"], arguments)
        unmapped = self.call("read_gpu_memory", {"gpu_address": "0x5000", "size": 4})
        self.assertTrue(unmapped["isError"])
        self.assertIn("0x5000 is not mapped", unmapped["content"][0]["text"])

    def test_input_waits_as_long_as_the_emulator(self):
        self.assertEqual(debug_mcp.default_timeout("input", {"frames": 600}), 40)
        sequence = {"steps": [{"frames": 300}, {"frames": 300, "buttons": ["A"]}]}
        self.assertEqual(debug_mcp.default_timeout("input_sequence", sequence), 40)
        self.assertEqual(debug_mcp.default_timeout("status", {}), 5)
        result = self.call("input_sequence", sequence)
        self.assertFalse(result["isError"])
        self.assertEqual(self.fake.requests[-1]["params"], sequence)

    def test_screenshot_becomes_image_content(self):
        result = self.call("screenshot")
        self.assertEqual(result["content"][0], {"type": "image", "data": PNG,
                                                "mimeType": "image/png"})
        self.assertNotIn("png_base64", result["content"][1]["text"])

    def test_emulator_errors_are_tool_errors(self):
        result = self.call("log_filter", {"filter": "*:Debug"})
        self.assertTrue(result["isError"])
        self.assertIn("unknown method", result["content"][0]["text"])

    def test_capture_image_only_reads_this_sessions_captures(self):
        self.assertTrue(self.call("capture_image", {"directory": self.capture_dir,
                                                    "name": "0001_present"})["isError"])
        self.assertFalse(self.call("capture_frame")["isError"])
        image = self.call("capture_image", {"directory": self.capture_dir, "name": "0001_present"})
        self.assertFalse(image["isError"])
        self.assertEqual(base64.b64decode(image["content"][0]["data"]), b"\x89PNG present")
        escape = self.call("capture_image", {"directory": self.capture_dir, "name": "../../etc"})
        self.assertTrue(escape["isError"])



if __name__ == "__main__":
    unittest.main()
