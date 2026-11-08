import json
import os
import socket

PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
DEFAULT_SERVER = "127.0.0.1:6545"

class EmulatorError(Exception):
    pass


class Emulator:
    """One JSON line per request to the debug server, reconnecting when the game restarted."""

    def __init__(self, address):
        host, _, port = address.rpartition(":")
        self.host = host.strip("[]") or "127.0.0.1"
        self.port = int(port)
        self.sock = None
        self.buffer = b""
        self.next_id = 1

    def close(self):
        if self.sock is not None:
            self.sock.close()
        self.sock = None
        self.buffer = b""

    def call(self, method, params, timeout):
        for attempt in (0, 1):
            try:
                if self.sock is None:
                    self.sock = socket.create_connection((self.host, self.port), timeout=5)
                self.sock.settimeout(timeout)
                request_id = self.next_id
                self.next_id += 1
                line = json.dumps({"id": request_id, "method": method, "params": params})
                self.sock.sendall(line.encode() + b"\n")
                while b"\n" not in self.buffer:
                    chunk = self.sock.recv(1 << 20)
                    if not chunk:
                        raise ConnectionResetError("the emulator closed the connection")
                    self.buffer += chunk
                raw, _, self.buffer = self.buffer.partition(b"\n")
                response = json.loads(raw)
                break
            except (ConnectionRefusedError, socket.timeout) as error:
                self.close()
                if isinstance(error, socket.timeout):
                    raise EmulatorError(f"no answer within {timeout} s") from error
                raise EmulatorError(
                    f"nothing listens on {self.host}:{self.port}: start Eve with "
                    f"EDEN_NX2_DEBUG_SERVER={self.host}:{self.port} and boot a game") from error
            except OSError as error:
                # A stale connection from an earlier boot: reconnect once.
                self.close()
                if attempt == 1:
                    raise EmulatorError(str(error)) from error
        if "error" in response:
            raise EmulatorError(response["error"])
        return response.get("result")


def default_timeout(name, params):
    """The emulator's own timeout_s default, so the adapter waits at least as long."""
    if name == "capture_frame":
        return 120
    if name == "sample":
        return int(params.get("seconds", 10)) + 90
    if name == "timeline":
        return int(params.get("seconds", 5)) + 60
    if name in ("input", "input_sequence"):
        steps = params.get("steps", []) if name == "input_sequence" else [params]
        return sum(int(step.get("frames", 0)) for step in steps) // 20 + 10
    return 5


def text(value):
    return {"type": "text", "text": value if isinstance(value, str) else json.dumps(value, indent=1)}


def serve(adapter, stdin, stdout):
    for line in stdin:
        if not line.strip():
            continue
        try:
            message = json.loads(line)
        except ValueError:
            response = {"jsonrpc": "2.0", "id": None,
                        "error": {"code": -32700, "message": "parse error"}}
        else:
            response = adapter.handle(message)
        if response is not None:
            stdout.write(json.dumps(response) + "\n")
            stdout.flush()


def call_once(adapter, request_text, out, stdout):
    """--call: one request, its JSON result on stdout, its PNG (if any) saved to `out`."""
    try:
        request = json.loads(request_text)
        result, png = adapter.run(request["method"], request.get("params") or {})
    except (EmulatorError, KeyError, ValueError, TypeError, AttributeError) as error:
        message = f"missing {error} in the request" if isinstance(error, KeyError) else str(error)
        stdout.write(json.dumps({"error": message}) + "\n")
        return 1
    if png is not None:
        if out:
            with open(out, "wb") as file:
                file.write(png)
            result["png"] = os.path.abspath(out).replace("\\", "/")
        else:
            result["png"] = "not saved: pass --out <path>"
    stdout.write(json.dumps(result, indent=1) + "\n")
    return 0


