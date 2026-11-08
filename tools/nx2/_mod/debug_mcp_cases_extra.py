import io
import json
import os
import socket
import subprocess
import sys

import debug_mcp
from .fake_debug_emu import HERE_DIR as HERE, PNG_BYTES


class AdapterExtraCases:
    def test_restarted_emulator_is_reconnected(self):
        self.call("status")
        self.adapter.emulator.sock.close()
        self.adapter.emulator.sock = socket.create_connection(("127.0.0.1", self.fake.port))
        self.adapter.emulator.sock.close()
        self.adapter.emulator.sock = None
        self.assertFalse(self.call("status")["isError"])

    def test_missing_emulator_explains_how_to_start_it(self):
        self.fake.close()
        probe = socket.socket()
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
        probe.close()
        adapter = debug_mcp.Adapter(debug_mcp.Emulator(f"127.0.0.1:{port}"))
        reply = adapter.handle({"id": 1, "method": "tools/call",
                                "params": {"name": "status", "arguments": {}}})
        self.assertTrue(reply["result"]["isError"])
        self.assertIn("EDEN_NX2_DEBUG_SERVER", reply["result"]["content"][0]["text"])

    def test_stdio_framing(self):
        stdin = io.StringIO('{"jsonrpc":"2.0","id":1,"method":"ping"}\n\nnot json\n')
        stdout = io.StringIO()
        debug_mcp.serve(self.adapter, stdin, stdout)
        lines = [json.loads(line) for line in stdout.getvalue().splitlines()]
        self.assertEqual(lines[0], {"jsonrpc": "2.0", "id": 1, "result": {}})
        self.assertEqual(lines[1]["error"]["code"], -32700)

    def test_runs_as_a_process(self):
        done = subprocess.run([sys.executable, "-I", os.path.join(HERE, "debug_mcp.py"),
                               "--server", f"127.0.0.1:{self.fake.port}"],
                              input='{"jsonrpc":"2.0","id":5,"method":"tools/call","params":'
                                    '{"name":"status","arguments":{}}}\n',
                              capture_output=True, text=True, timeout=30)
        self.assertEqual(done.returncode, 0, done.stderr)
        reply = json.loads(done.stdout)
        self.assertEqual(reply["id"], 5)
        self.assertFalse(reply["result"]["isError"])


    def test_call_once_saves_the_screenshot(self):
        out = os.path.join(self.temp.name, "shot.png")
        stdout = io.StringIO()
        code = debug_mcp.call_once(self.adapter, '{"method":"screenshot","params":{"height":360}}',
                                   out, stdout)
        self.assertEqual(code, 0)
        result = json.loads(stdout.getvalue())
        self.assertEqual(result["width"], 1280)
        self.assertNotIn("png_base64", result)
        self.assertEqual(result["png"], os.path.abspath(out).replace("\\", "/"))
        with open(out, "rb") as file:
            self.assertEqual(file.read(), PNG_BYTES)
        self.assertEqual(self.fake.requests[-1]["params"], {"height": 360})

    def test_call_once_without_out_says_where_the_png_went(self):
        stdout = io.StringIO()
        self.assertEqual(debug_mcp.call_once(self.adapter, '{"method":"screenshot"}', None, stdout), 0)
        self.assertIn("--out", json.loads(stdout.getvalue())["png"])

    def test_call_once_reports_errors_as_json(self):
        for request in ('{"method":"log_filter","params":{"filter":"*:Debug"}}', '{"params":{}}',
                        'not json', '{"method":"bogus"}', '[1]'):
            stdout = io.StringIO()
            self.assertEqual(debug_mcp.call_once(self.adapter, request, None, stdout), 1, request)
            self.assertIn("error", json.loads(stdout.getvalue()), request)

    def test_call_runs_from_the_command_line(self):
        out = os.path.join(self.temp.name, "cli.png")
        script = os.path.join(HERE, "debug_mcp.py")
        server = f"127.0.0.1:{self.fake.port}"
        done = subprocess.run([sys.executable, "-I", script, "--server", server, "--call",
                               '{"method":"screenshot"}', "--out", out],
                              capture_output=True, text=True, timeout=30)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(json.loads(done.stdout)["height"], 720)
        self.assertTrue(os.path.isfile(out))
        failed = subprocess.run([sys.executable, "-I", script, "--server", server, "--call",
                                 '{"method":"log_filter","params":{"filter":"x"}}'],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(failed.returncode, 1)
        self.assertIn("unknown method", json.loads(failed.stdout)["error"])

