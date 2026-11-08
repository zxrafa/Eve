#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""MCP server (stdio) for Eve's in-process debug server (docs/nx2/debug-mcp.md).

Run Eve with EDEN_NX2_DEBUG_SERVER=127.0.0.1:6545, then register this script as a stdio MCP
server for the agent:  python3 -I tools/nx2/debug_mcp.py [--server 127.0.0.1:6545]
or run one request from a shell:
  python3 -I tools/nx2/debug_mcp.py --call '{"method":"screenshot","params":{}}' --out shot.png

Standard library only. Each tool call is forwarded as one JSON line to the emulator, which may
be restarted between calls: the adapter reconnects on demand.
"""

import argparse
import base64
import json
import os
import socket
import subprocess
import sys

import os as _os, sys as _sys
_HERE = _os.path.dirname(_os.path.abspath(__file__))
if _HERE not in _sys.path:
    _sys.path.insert(0, _HERE)

from _mod.debug_mcp_schemas_a import TOOLS_HEAD
from _mod.debug_mcp_schemas_b import BUTTONS, STICK, TOOLS_TAIL
from _mod.debug_mcp_emu import (
    DEFAULT_SERVER, Emulator, EmulatorError, PROTOCOL_VERSIONS, call_once, default_timeout, serve, text,
)

HERE = _HERE
TOOLS = [*TOOLS_HEAD, *TOOLS_TAIL]
TOOL_NAMES = {tool['name'] for tool in TOOLS}

class Adapter:
    def __init__(self, emulator):
        self.emulator = emulator
        self.captures = set()

    def run(self, name, arguments):
        """Runs one tool; returns its result and the PNG it produced, if any."""
        if name not in TOOL_NAMES:
            raise EmulatorError(f"unknown tool {name}")
        if name == "capture_image":
            return self.capture_image(arguments)
        params = dict(arguments)
        index = params.pop("index", False)
        timeout = max(int(params.get("timeout_s", default_timeout(name, params))), 1) + 30
        result = self.emulator.call(name, params, timeout)
        if name == "screenshot":
            png = result.pop("png_base64", None)
            return result, base64.b64decode(png) if png else None
        if name == "capture_frame":
            self.captures.add(os.path.realpath(result["directory"]))
            if index:
                result["index"] = self.build_index(result["directory"])
        return result, None

    def call_tool(self, name, arguments):
        result, png = self.run(name, arguments)
        content = [text(result)]
        if png is not None:
            content.insert(0, {"type": "image", "data": base64.b64encode(png).decode(),
                               "mimeType": "image/png"})
        return content

    def build_index(self, directory):
        script = os.path.join(HERE, "frame_dump_index.py")
        done = subprocess.run([sys.executable, "-I", script, directory], capture_output=True,
                              text=True, timeout=600)
        if done.returncode != 0:
            return f"frame_dump_index.py failed: {done.stderr.strip()[-2000:]}"
        return os.path.join(directory, "index.html")

    def capture_image(self, arguments):
        directory = os.path.realpath(arguments["directory"])
        if directory not in self.captures:
            raise EmulatorError("not a capture made in this session; run capture_frame first")
        path = os.path.realpath(os.path.join(directory, arguments["name"] + ".png"))
        if os.path.dirname(path) != directory or not os.path.isfile(path):
            raise EmulatorError(f"no image {arguments['name']}.png in {directory}")
        with open(path, "rb") as file:
            return {"path": path}, file.read()

    def handle(self, message):
        """Returns the response to one JSON-RPC message, or None for a notification."""
        method = message.get("method")
        if "id" not in message:
            return None
        reply = {"jsonrpc": "2.0", "id": message["id"]}
        params = message.get("params") or {}
        if method == "initialize":
            wanted = params.get("protocolVersion")
            reply["result"] = {
                "protocolVersion": wanted if wanted in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0],
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "eve-debug", "version": "1"},
            }
        elif method == "ping":
            reply["result"] = {}
        elif method == "tools/list":
            reply["result"] = {"tools": TOOLS}
        elif method == "tools/call":
            try:
                content = self.call_tool(params.get("name"), params.get("arguments") or {})
                reply["result"] = {"content": content, "isError": False}
            except (EmulatorError, KeyError, ValueError) as error:
                message_text = f"missing argument {error}" if isinstance(error, KeyError) else str(error)
                reply["result"] = {"content": [text(message_text)], "isError": True}
        else:
            reply["error"] = {"code": -32601, "message": f"method not found: {method}"}
        return reply


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--server", default=os.environ.get("EVE_DEBUG_SERVER", DEFAULT_SERVER),
                        help=f"host:port of EDEN_NX2_DEBUG_SERVER (default {DEFAULT_SERVER})")
    parser.add_argument("--call", metavar="JSON",
                        help='run one request and exit, e.g. \'{"method":"screenshot","params":{}}\'')
    parser.add_argument("--out", metavar="PNG", help="with --call: where to save the PNG")
    args = parser.parse_args()
    adapter = Adapter(Emulator(args.server))
    if args.call is not None:
        sys.exit(call_once(adapter, args.call, args.out, sys.stdout))
    serve(adapter, sys.stdin, sys.stdout)


if __name__ == "__main__":
    main()
