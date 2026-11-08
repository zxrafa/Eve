import json
import os
import struct
import subprocess

KIND_SAMPLE = 1
KIND_THREAD = 2
KIND_MODULE = 3
KIND_END = 0xFF


class SampleFile:
    def __init__(self):
        self.hz = 0
        self.qpc_frequency = 0
        self.modules = []  # (base, size, path)
        self.threads = {}  # tag -> name
        self.samples = []  # (tag, qpc, frames innermost first)
        self.complete = False


def parse(data):
    if data[:8] != b"NX2SMPL1":
        raise ValueError("not an EDEN_NX2_SAMPLE_PROFILE file")
    result = SampleFile()
    _version, result.hz, result.qpc_frequency = struct.unpack_from("<IIQ", data, 8)
    offset = 24
    while offset < len(data):
        kind = data[offset]
        offset += 1
        try:
            if kind == KIND_SAMPLE:
                tag, depth, _ = struct.unpack_from("<BBB", data, offset)
                (qpc,) = struct.unpack_from("<Q", data, offset + 3)
                frames = list(struct.unpack_from("<%dQ" % depth, data, offset + 11))
                offset += 11 + 8 * depth
                result.samples.append((tag, qpc, frames))
            elif kind == KIND_THREAD:
                tag, length = struct.unpack_from("<BH", data, offset)
                result.threads[tag] = data[offset + 3:offset + 3 + length].decode("utf-8", "replace")
                offset += 3 + length
            elif kind == KIND_MODULE:
                base, size, length = struct.unpack_from("<QIH", data, offset)
                path = data[offset + 14:offset + 14 + length].decode("utf-8", "replace")
                offset += 14 + length
                result.modules.append((base, size, path))
            elif kind == KIND_END:
                result.complete = True
                break
            else:
                raise ValueError("unknown record kind %#x at %#x" % (kind, offset - 1))
        except struct.error:
            break  # cut short (the process ended while sampling)
    return result


def find_module(modules, address):
    for base, size, path in modules:
        if base <= address < base + size:
            return base, path
    return None, None


def is_exe(path, exe_name):
    return os.path.basename(path.replace("\\", "/")).lower() == exe_name.lower()


class Symbolizer:
    """Maps eve.exe RVAs to function names (innermost inline frame first)."""

    def __init__(self, exe, cache_path, symbolizer="llvm-symbolizer", inlines=True):
        self.exe = exe
        self.inlines = inlines
        self.cache_path = cache_path
        self.symbolizer = symbolizer
        self.cache = {}
        stamp = self._stamp()
        if cache_path and os.path.exists(cache_path):
            with open(cache_path) as file:
                cached = json.load(file)
            if cached.get("stamp") == stamp:
                self.cache = {int(key): value for key, value in cached["symbols"].items()}
        self.stamp = stamp

    def _stamp(self):
        if not self.exe or not os.path.exists(self.exe):
            return None
        info = os.stat(self.exe)
        return [os.path.abspath(self.exe), info.st_size, int(info.st_mtime)]

    def resolve(self, rvas):
        missing = sorted({rva for rva in rvas if rva not in self.cache})
        if missing and self.exe:
            for start in range(0, len(missing), 4096):
                batch = missing[start:start + 4096]
                output = subprocess.run(
                    [self.symbolizer, "--obj=" + self.exe, "--relative-address",
                     "--inlines" if self.inlines else "--no-inlines", "--output-style=JSON"],
                    input="\n".join("%#x" % rva for rva in batch), capture_output=True, text=True,
                    check=True).stdout
                lines = [line for line in output.splitlines() if line.strip()]
                for rva, line in zip(batch, lines):
                    symbols = json.loads(line).get("Symbol", [])
                    names = [symbol.get("FunctionName") or "??" for symbol in symbols]
                    self.cache[rva] = names or ["??"]
            if self.cache_path:
                with open(self.cache_path, "w") as file:
                    json.dump({"stamp": self.stamp, "symbols": self.cache}, file)
        return {rva: self.cache.get(rva, ["eve.exe+%#x" % rva]) for rva in rvas}
