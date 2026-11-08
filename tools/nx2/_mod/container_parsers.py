import struct

from shader_archive import ArchiveError
from .container_codec import (
    MAX_ALLOCATION, STAGES, dcx_decompress, extent, lz4_block,
)

def parse_bnd4(data):
    extent(data, 0, 64)
    if data[:4] != b"BND4" or data[9:12] != b"\0\1\0" or data[48:52] != b"\1t\0\0":
        raise ArchiveError("unsupported BND4 byte order or file-record format")
    count, = struct.unpack_from("<I", data, 12)
    header, record_size = struct.unpack_from("<Q8xQ", data, 16)
    if header != 64 or record_size != 36 or count > 100000:
        raise ArchiveError("unsupported BND4 record size or count")
    extent(data, 64, count * record_size)
    result = []
    for index in range(count):
        record = 64 + index * record_size
        if data[record:record + 8] not in (b"\x40\0\0\0\xff\xff\xff\xff", b"\xc0\0\0\0\xff\xff\xff\xff"):
            raise ArchiveError("unsupported BND4 member flags")
        size, unpacked, offset, ident, name = struct.unpack_from("<QQIII", data, record + 8)
        if size > MAX_ALLOCATION or unpacked > MAX_ALLOCATION or name % 2:
            raise ArchiveError("invalid BND4 member size or name")
        end = name
        while extent(data, end, 2) != b"\0\0":
            end += 2
            if end - name > 65536:
                raise ArchiveError("excessive BND4 filename")
        filename = data[name:end].decode("utf-16-le")
        payload = extent(data, offset, size)
        if data[record] == 0xc0:
            payload = dcx_decompress(payload)
        if len(payload) != unpacked:
            raise ArchiveError("BND4 member size mismatch")
        result.append((filename, payload))
    return result


def graphics_record(code, control, **metadata):
    if len(code) <= 128 or (len(code) - 128) % 16:
        raise ArchiveError("unsupported native graphics allocation")
    stage = (struct.unpack_from("<I", code)[0] >> 10) & 15
    if not 1 <= stage <= 5:
        raise ArchiveError("native envelope is not a verified graphics header")
    if len(control) < 8 or control[:8] != bytes.fromhex("34127698c9000000"):
        raise ArchiveError("unsupported native shader control version")
    return {"stage": STAGES[stage - 1], "code": code, "control": control, **metadata}


def parse_cgsb(data):
    extent(data, 0, 24)
    if data[:8] != b"CGSB\x33\x22\x11\0":
        raise ArchiveError("unsupported CGSB version")
    count, shader_stage = struct.unpack_from("<HH", data, 8)
    table, = struct.unpack_from("<Q", data, 16)
    if not 1 <= count <= 16:
        raise ArchiveError("invalid CGSB record count")
    if shader_stage > 7:
        raise ArchiveError(f"unsupported CGSB stage {shader_stage}")
    extent(data, table, count * 80)
    result = []
    for index in range(count):
        record = table + index * 80
        if data[record:record + 8] != b"NVN \1\0\0\0":
            raise ArchiveError("unsupported CGSB shader platform")
        code_offset, code_size, control_offset, control_size = struct.unpack_from("<4Q", data, record + 16)
        if shader_stage >= 5:
            stage = ("compute", "task", "mesh")[shader_stage - 5]
            result.append({"stage": stage, "code": extent(data, code_offset, code_size),
                           "control": extent(data, control_offset, control_size),
                           "variation": index, "envelope": f"unverified-{stage}",
                           "code_offset": code_offset, "control_offset": control_offset})
        else:
            item = graphics_record(extent(data, code_offset, code_size),
                                   extent(data, control_offset, control_size),
                                   variation=index, code_offset=code_offset, control_offset=control_offset)
            if item["stage"] != STAGES[shader_stage]:
                raise ArchiveError("CGSB stage disagrees with native header")
            result.append(item)
    return result


def parse_shn(data):
    extent(data, 0, 68)
    if data[:4] != b"SHN!":
        raise ArchiveError("not a SHN shader container")
    blocks = []
    for descriptor in (4, 36):
        offset, compressed, size = struct.unpack_from("<III", data, descriptor)
        blocks.append(lz4_block(extent(data, offset, compressed), size))
    metadata, code = blocks
    if metadata[:8] != b"SHDROUNC" or len(metadata) < 64:
        raise ArchiveError("unsupported SHN metadata format")
    version, variations = struct.unpack_from("<II", metadata, 8)
    if version != 20241128 or not 1 <= variations <= 65536:
        raise ArchiveError("unsupported SHDROUNC version or variation count")
    extent(metadata, 16, variations * 80)
    result = []
    for variation in range(variations):
        table, = struct.unpack_from("<Q", metadata, 48 + variation * 80)
        extent(metadata, table, 9 * 80)
        for index in range(9):
            record = table + index * 80
            code_offset, control_offset = struct.unpack_from("<QQ", metadata, record)
            code_size, control_size = struct.unpack_from("<II", metadata, record + 64)
            if not code_size and not control_size:
                continue
            payload = extent(code, code_offset, code_size)
            control = extent(metadata, control_offset, control_size)
            origin = {"variation": variation, "slot": index, "code_offset": code_offset,
                      "control_offset": control_offset}
            if index == 2:
                result.append({"stage": "compute", "code": payload, "control": control,
                               "envelope": "unverified-compute", **origin})
            elif index in (0, 1):
                item = graphics_record(payload, control, **origin)
                if item["stage"] != ("vertex", "fragment")[index]:
                    raise ArchiveError("SHDROUNC stage disagrees with native header")
                result.append(item)
            else:
                result.append({"stage": f"unknown-shdrounc-slot-{index}", "code": payload,
                               "control": control, "envelope": "unverified-shdrounc-slot", **origin})
    if not result:
        raise ArchiveError("SHDROUNC contains no supported shader records")
    return result
