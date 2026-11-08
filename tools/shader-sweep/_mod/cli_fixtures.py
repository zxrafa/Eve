import struct

NATIVE_EXIT = struct.pack("<4I", 0x794D, 0, 0x03800000, 0)
MAXWELL_EXIT = 0xE30000000007000F
STAGES = ("vertex", "tess-control", "tess-eval", "geometry", "fragment", "compute")


def header(stage):
    words = [0] * 20
    words[0] = ((stage + 1) << 10) | 1
    words[2] = 1 << 24
    words[3] = 1 << 24
    words[4] = 1
    if stage == 4:
        words[18] = 15
    return struct.pack("<20I", *words)


def environment(version, stage, instructions=(MAXWELL_EXIT,), formats=()):
    code = bytearray(header(stage))
    for instruction in instructions:
        if len(code) % 32 == 0:
            code += bytes(8)
        code += struct.pack("<Q", instruction)
    counts = [len(code), 0, len(formats), 0, 0]
    if version >= 47:
        counts.append(0)
    record = struct.pack("<" + "Q" * len(counts), *counts)
    record += struct.pack("<7I", 0, 2, 80 if stage == 5 else 0, 0, len(code) - 8, 1, stage)
    record += code
    for handle, pixel_format in formats:
        record += struct.pack("<2I", handle, pixel_format)
    record += struct.pack("<4I", 1, 1, 1, 0) if stage == 5 else header(stage)
    if stage == 3:
        record += bytes(32)
    return record


def pipeline_key(raw1=0, color=0, attribute=None, dynamic_type=None):
    key = bytearray(1056)
    struct.pack_into("<II", key, 48, raw1, 7 << 1)
    struct.pack_into("<f", key, 76, 1.0)
    key[56] = color
    if attribute is not None:
        struct.pack_into("<I", key, 160, 1 | (attribute << 20))
    if dynamic_type is not None:
        struct.pack_into("<Q", key, 112, dynamic_type)
    return key


def spirv_instructions(data):
    words = struct.unpack("<" + "I" * (len(data) // 4), data)
    assert words[0] == 0x07230203
    offset = 5
    while offset < len(words):
        size, opcode = words[offset] >> 16, words[offset] & 0xFFFF
        assert size and offset + size <= len(words)
        yield opcode, words[offset + 1:offset + size]
        offset += size


def interface_type(data, storage):
    instructions = list(spirv_instructions(data))
    types = {args[0]: (op, args[1:]) for op, args in instructions if op in (21, 22, 23, 32)}
    locations = {args[0] for op, args in instructions if op == 71 and args[1:] == (30, 0)}
    for op, args in instructions:
        if op != 59 or args[1] not in locations or args[2] != storage:
            continue
        pointer = types[args[0]]
        value = types[pointer[1][1]]
        if value[0] == 23:
            value = types[value[1][0]]
        return "float" if value[0] == 22 else "signed" if value[1][1] else "unsigned"
    return None
