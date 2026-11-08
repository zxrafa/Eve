import base64
import json
import os
import socket
import tempfile
import threading
import unittest

import debug_mcp

HERE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PNG_BYTES = b"\x89PNG fake"
PNG = base64.b64encode(PNG_BYTES).decode()


class FakeEmulator:
    """The debug server's wire protocol: one JSON request line, one JSON response line."""

    def __init__(self, capture_dir):
        self.listener = socket.socket()
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen()
        self.port = self.listener.getsockname()[1]
        self.capture_dir = capture_dir
        self.requests = []
        threading.Thread(target=self.serve, daemon=True).start()

    def answer(self, request):
        method = request["method"]
        if method == "status":
            return {"result": {"title": "Test", "presents": 3}}
        if method == "screenshot":
            return {"result": {"width": 1280, "height": 720, "png_base64": PNG}}
        if method == "capture_frame":
            return {"result": {"directory": self.capture_dir, "entries_total": 1}}
        if method == "read_memory":
            return {"result": {"address": request["params"]["address"], "hex": "0000803f"}}
        if method == "read_gpu_memory":
            return {"error": "GPU address 0x5000 is not mapped"}
        if method in ("input", "input_sequence"):
            return {"result": {"controller": "player1", "frames": 3}}
        return {"error": f"unknown method \"{method}\""}

    def serve(self):
        while True:
            try:
                connection, _ = self.listener.accept()
            except OSError:
                return
            with connection, connection.makefile("rwb") as stream:
                for line in stream:
                    request = json.loads(line)
                    self.requests.append(request)
                    response = {"id": request["id"], **self.answer(request)}
                    stream.write(json.dumps(response).encode() + b"\n")
                    stream.flush()

    def close(self):
        self.listener.close()


class AdapterTestBase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.capture_dir = os.path.join(self.temp.name, "capture-1")
        os.mkdir(self.capture_dir)
        with open(os.path.join(self.capture_dir, "0001_present.png"), "wb") as file:
            file.write(b"\x89PNG present")
        self.fake = FakeEmulator(self.capture_dir)
        self.adapter = debug_mcp.Adapter(debug_mcp.Emulator(f"127.0.0.1:{self.fake.port}"))

    def tearDown(self):
        self.adapter.emulator.close()
        self.fake.close()
        self.temp.cleanup()

    def call(self, name, arguments=None):
        reply = self.adapter.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                     "params": {"name": name, "arguments": arguments or {}}})
        return reply["result"]
