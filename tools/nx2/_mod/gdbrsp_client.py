import socket
import struct

REGS = [f"x{i}" for i in range(31)] + ["sp", "pc", "cpsr"]


class Rsp:
    def __init__(self, port):
        import time
        for _ in range(240):  # wait up to ~2 min for the stub to listen
            try:
                self.s = socket.create_connection(("127.0.0.1", port), timeout=3)
                self.s.settimeout(None)  # a stop can be hours of play away
                break
            except OSError:
                time.sleep(0.5)
        else:
            raise SystemExit("gdbstub not reachable")
        self.buf = b""

    def _read_packet(self):
        while True:
            while b"$" not in self.buf or b"#" not in self.buf[self.buf.index(b"$"):]:
                chunk = self.s.recv(65536)
                if not chunk:
                    raise EOFError
                self.buf += chunk
            start = self.buf.index(b"$")
            end = self.buf.index(b"#", start)
            if len(self.buf) < end + 3:
                self.buf += self.s.recv(65536)
                continue
            data = self.buf[start + 1:end]
            self.buf = self.buf[end + 3:]
            self.s.sendall(b"+")
            return data.decode(errors="replace")

    def cmd(self, c):
        pkt = c.encode()
        self.s.sendall(b"$" + pkt + b"#" + f"{sum(pkt) & 0xff:02x}".encode())
        return self._read_packet()

    def regs(self):
        r = self.cmd("g")
        vals = {}
        off = 0
        for name in REGS:
            n = 8 if name != "cpsr" else 4
            if off + n * 2 > len(r):
                break
            vals[name] = int.from_bytes(bytes.fromhex(r[off:off + n * 2]), "little")
            off += n * 2
        return vals

    def mem(self, addr, length):
        r = self.cmd(f"m{addr:x},{length:x}")
        try:
            return bytes.fromhex(r)
        except ValueError:
            return b""
