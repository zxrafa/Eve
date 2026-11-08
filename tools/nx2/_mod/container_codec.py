import ctypes
import ctypes.util
import struct
import zlib

from shader_archive import ArchiveError

MAX_ALLOCATION = 512 * 1024 * 1024
STAGES = ("vertex", "tess-control", "tess-eval", "geometry", "fragment")


def extent(data, offset, size):
    if offset < 0 or size < 0 or offset > len(data) or size > len(data) - offset:
        raise ArchiveError(f"extent {offset:#x}+{size:#x} outside {len(data):#x} bytes")
    return data[offset:offset + size]


def zstd_decompress(data):
    try:
        from compression import zstd
    except ImportError:
        library = ctypes.CDLL(ctypes.util.find_library("zstd"))
        library.ZSTD_getFrameContentSize.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
        library.ZSTD_getFrameContentSize.restype = ctypes.c_ulonglong
        size = library.ZSTD_getFrameContentSize(data, len(data))
        if size > MAX_ALLOCATION:
            raise ArchiveError("unknown or excessive zstd decompressed size")
        output = ctypes.create_string_buffer(size)
        library.ZSTD_decompress.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
        library.ZSTD_decompress.restype = ctypes.c_size_t
        actual = library.ZSTD_decompress(output, size, data, len(data))
        if actual != size:
            raise ArchiveError("zstd decompression failed; a dictionary may be required")
        return output.raw[:actual]
    size = zstd.get_frame_info(data).decompressed_size
    if size is None or size > MAX_ALLOCATION:
        raise ArchiveError("unknown or excessive zstd decompressed size")
    result = zstd.ZstdDecompressor().decompress(data, max_length=size + 1)
    if len(result) != size:
        raise ArchiveError("zstd decompressed size mismatch")
    return result


def lz4_block(data, expected):
    if expected > MAX_ALLOCATION:
        raise ArchiveError("excessive LZ4 allocation")
    output = bytearray()
    cursor = 0

    def length(initial):
        nonlocal cursor
        value = initial
        if initial == 15:
            while True:
                if cursor >= len(data):
                    raise ArchiveError("truncated LZ4 length")
                extra = data[cursor]
                cursor += 1
                value += extra
                if extra != 255:
                    break
        return value

    while cursor < len(data):
        token = data[cursor]
        cursor += 1
        literals = length(token >> 4)
        if len(output) + literals > expected:
            raise ArchiveError("LZ4 literals exceed allocation")
        output.extend(extent(data, cursor, literals))
        cursor += literals
        if cursor == len(data):
            break
        distance, = struct.unpack("<H", extent(data, cursor, 2))
        cursor += 2
        count = length(token & 15) + 4
        if not distance or distance > len(output) or len(output) + count > expected:
            raise ArchiveError("invalid LZ4 match")
        while count:
            size = min(distance, count)
            output.extend(output[-distance:][:size])
            count -= size
    if len(output) != expected:
        raise ArchiveError("LZ4 decompressed size mismatch")
    return bytes(output)


def dcx_decompress(data):
    extent(data, 0, 0x30)
    if data[:4] != b"DCX\0" or data[0x18:0x1c] != b"DCS\0" or data[0x24:0x28] != b"DCP\0":
        raise ArchiveError("unsupported DCX header")
    offset, = struct.unpack_from(">I", data, 0x14)
    size, compressed = struct.unpack_from(">II", data, 0x1c)
    if size > MAX_ALLOCATION:
        raise ArchiveError("excessive DCX allocation")
    payload = extent(data, offset, compressed)
    if data[0x28:0x2c] == b"ZSTD":
        result = zstd_decompress(payload)
    elif data[0x28:0x2c] == b"DFLT":
        decoder = zlib.decompressobj()
        result = decoder.decompress(payload, size + 1)
        if not decoder.eof or decoder.unused_data:
            raise ArchiveError("incomplete or trailing DCX zlib stream")
    else:
        raise ArchiveError(f"unsupported DCX compressor {data[0x28:0x2c]!r}")
    if len(result) != size:
        raise ArchiveError("DCX decompressed size mismatch")
    return result
