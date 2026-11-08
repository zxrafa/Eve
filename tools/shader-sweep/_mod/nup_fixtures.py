import hashlib
import struct

COMPRESSED_SHADER = bytes.fromhex(
    "28b52ffd8058c0912100f40000b073796e746865746963207368616465722062797465730100ceff339f4d"
    "4c000008790100fcff3910024c000008650100fcff3910024c000008730100fcff3910024c000008740100"
    "fcff3910024c0000086e0100fcff3910024c000008650100fcff3910024c000008200100fcff3910024c0000"
    "08610100fcff3910024c000008630100fcff3910024c000008680100fcff3910024c000008730100fcff3910"
    "024c000008790100fcff3910024c000008650100fcff3910024c000008730100fcff3910024c000008740100"
    "fcff3910024d0000086e0100bc91391002"
)


def fixture(filename='Shader.bfsha', corrupt=False):
    payloads = [b'synthetic shader bytes' * 100000, b'not a candidate' * 200000, b'']
    names = ['root', 'Shaders', filename, 'readme.txt', 'empty.bnsh']
    pool = b''
    strings = []
    for name in names:
        encoded = name.encode()
        strings.append((len(pool), len(encoded)))
        pool += encoded
    packages = 3
    dirs = 2
    files = len(payloads)
    children = [1, dirs + 1, dirs, dirs + 2]
    toc_size = 0x30 + packages * 0x40 + dirs * 0x18 + files * 0x50 + len(children) * 4 + len(pool)
    blob = (0x80 + toc_size + 15) & ~15
    data = bytearray(blob)
    def put(offset, value, width=8):
        data[offset:offset+width] = value.to_bytes(width, 'little')
    data[:4] = b'NUP\x01'
    put(4, 0x80, 2)
    put(8, 0x80)
    put(16, toc_size)
    put(0x38, blob)
    put(0x48, packages, 4)
    data[0x80:0x84] = b'TOC\x01'
    put(0x84, packages, 4)
    put(0x88, dirs)
    put(0x90, files)
    put(0x98, toc_size - len(pool))
    put(0xa0, len(pool))
    pos = 0xb0 + packages * 0x40
    for i, (start, count) in enumerate([(0, 2), (2, 2)]):
        off, size = strings[i]
        put(pos, off, 4)
        put(pos + 4, size, 4)
        put(pos + 8, start, 4)
        put(pos + 12, count, 4)
        pos += 0x18
    for i, payload in enumerate(payloads):
        off, size = strings[i+2]
        put(pos, off, 4)
        put(pos + 4, size, 4)
        put(pos + 8, len(payload))
        encoded = (b'broken zstd' if corrupt else COMPRESSED_SHADER) if i == 0 else payload
        if payload:
            put(pos + 16, len(data))
            put(pos + 24, len(encoded))
            data += encoded
            data += b'\x00' * (-len(data) % 16)
        data[pos + 32:pos + 64] = hashlib.sha256(payload).digest()
        put(pos + 64, int(i == 0), 1)
        pos += 0x50
    for child in children:
        put(pos, child, 4)
        pos += 4
    data[pos:pos+len(pool)] = pool
    for i in range(packages):
        p = 0xb0 + i * 0x40
        put(p, 0x0400000000000000 + i)
        put(p + 12, 0xffffffff, 4)
        put(p + 16, 0 if i < 2 else 0xffffffff, 4)
        put(p + 20, i + 10, 4)
        put(p + 24, i, 1)
        metadata = b''
        for kind, value in [(5, f'Synthetic package {i}'.encode()), (4, b'1.2.3')]:
            metadata += struct.pack('<HHI', kind, 0, len(value)) + value
        put(p + 32, len(data))
        put(p + 40, len(metadata), 4)
        data += metadata
    put(0x40, len(data))
    data[0x18:0x38] = hashlib.sha256(data[0x80:0x80+toc_size]).digest()
    return bytes(data), payloads, 0x80 + toc_size + sum(8+len(f'Synthetic package {i}')+8+5 for i in range(packages))


def snapshot(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return path.stat().st_size, path.stat().st_mtime_ns, digest.hexdigest()

