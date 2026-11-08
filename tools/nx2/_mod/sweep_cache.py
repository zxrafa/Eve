from collections import Counter
import json
import re
import struct
import subprocess

from .sweep_consts import (
    CacheError, GAMES, GRAPHICS_KEY_SIZE, MAP_MAGIC, STAGES, digest,
)

def parse_cache(data):
    if len(data) < 12 or data[:8] != b"yuzucach":
        raise CacheError("not a serialized shader-environment cache")
    version, = struct.unpack_from("<I", data, 8)
    if version not in (46, 47, 48, 49, 50):
        raise CacheError(f"unsupported cache version {version}")
    cursor = 12
    entry = 0
    while cursor < len(data):
        if cursor + 4 > len(data):
            raise CacheError(f"truncated pipeline count at {cursor}")
        count, = struct.unpack_from("<I", data, cursor)
        cursor += 4
        if not 1 <= count <= 6:
            raise CacheError(f"invalid environment count {count} at {cursor - 4}")
        environments = []
        for index in range(count):
            begin = cursor
            header = struct.Struct("<" + "Q" * (6 if version >= 47 else 5) + "7I")
            if cursor + header.size > len(data):
                raise CacheError(f"truncated environment header at {cursor}")
            fields = header.unpack_from(data, cursor)
            sizes, params = fields[:-7], fields[-7:]
            code_size, textures, formats, constants = sizes[:4]
            pointers, replacements = sizes[4:] if version >= 47 else (0, sizes[4])
            local, bound, start, low, high, viewport, stage = params
            if stage >= len(STAGES) or code_size > 64 * 1024 * 1024 or code_size % 8:
                raise CacheError(f"invalid stage/code size at {cursor}")
            if any(n > 1_000_000 for n in sizes[1:]):
                raise CacheError(f"excessive context count at {cursor}")
            cursor += header.size
            code = data[cursor:cursor + code_size]
            cursor += code_size + textures * 8 + formats * 8 + constants * 12
            cursor += pointers * 9 + replacements * 12
            cursor += 16 if stage == 5 else 80 + (32 if stage == 3 else 0)
            if cursor > len(data):
                raise CacheError(f"truncated environment at {begin}")
            environments.append({"version": version, "entry": entry, "index": index,
                                 "stage": STAGES[stage], "offset": begin,
                                 "bytes": data[begin:cursor], "code": code})
        compute = environments[0]["stage"] == "compute"
        if compute and count != 1:
            raise CacheError(f"compute pipeline has {count} environments")
        key_size = 24 if compute else GRAPHICS_KEY_SIZE
        if cursor + key_size > len(data):
            raise CacheError(f"truncated pipeline key at {cursor}")
        key = data[cursor:cursor + key_size]
        cursor += key_size
        for env in environments:
            env["key"] = key
            yield env
        entry += 1


def unpack_native_code(code):
    if len(code) < 96 or len(code) % 8:
        return None
    words = struct.unpack("<" + "Q" * (len(code) // 8), code)
    if words[-1] != MAP_MAGIC:
        return None
    count = words[-2]
    if not 0 < count <= 65536 or count + 2 >= len(words):
        raise CacheError("invalid native address map")
    end = len(words) - count - 3
    return b"".join(struct.pack("<Q", words[i]) for i in range(10, end) if i % 4)


def invoke(command, timeout):
    try:
        proc = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"status": "error", "phase": "timeout", "error": {"message": "compiler timeout"}}
    try:
        result = json.loads(proc.stdout)
    except json.JSONDecodeError:
        result = {"status": "error", "phase": "process", "error": {
            "message": f"compiler exited {proc.returncode}: {proc.stderr[-2000:]}"}}
    result["returncode"] = proc.returncode
    if proc.returncode and result.get("status") == "ok":
        result.update(status="error", phase="process", error={"message": "nonzero compiler exit"})
    return result


def failure(phase, message):
    return {"status": "error", "phase": phase, "error": {"message": message}}


def summarize(results):
    counts = Counter()
    for row in results:
        message = row.get("error", {}).get("message", "ok")
        message = re.sub(r"%\d+", "%id", message)
        message = re.sub(r"0x[0-9a-fA-F]+", "0x...", message)
        counts[(row["game"], row.get("stage") or "unknown", row["phase"],
                row.get("opcode", ""), message)] += 1
    lines = ["| Game | Stage | Phase | Opcode | Cause | Count |", "|---|---|---|---|---|---:|"]
    for (game, stage, phase, opcode, cause), count in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
        cause = cause.replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {game} | {stage} | {phase} | {opcode} | {cause} | {count} |")
    return "\n".join(lines) + "\n"
