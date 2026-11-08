import struct

def lz4_block_decompress(src, out_size):
    dst = bytearray(out_size)
    si = di = 0
    n = len(src)
    while si < n:
        tok = src[si]
        si += 1
        lit = tok >> 4
        if lit == 15:
            while True:
                b = src[si]
                si += 1
                lit += b
                if b != 255:
                    break
        dst[di:di + lit] = src[si:si + lit]
        si += lit
        di += lit
        if si >= n:
            break
        off = src[si] | (src[si + 1] << 8)
        si += 2
        ml = tok & 15
        if ml == 15:
            while True:
                b = src[si]
                si += 1
                ml += b
                if b != 255:
                    break
        ml += 4
        start = di - off
        if off >= ml:
            dst[di:di + ml] = dst[start:start + ml]
        else:
            for k in range(ml):
                dst[di + k] = dst[start + k]
        di += ml
    return bytes(dst)


def nso_text(path):
    data = open(path, "rb").read()
    assert data[:4] == b"NSO0", path
    flags = struct.unpack_from("<I", data, 0xC)[0]
    file_off, mem_off, size = struct.unpack_from("<III", data, 0x10)
    csize = struct.unpack_from("<I", data, 0x60)[0]
    raw = data[file_off:file_off + (csize if flags & 1 else size)]
    return lz4_block_decompress(raw, size) if flags & 1 else raw


def load_patterns(inc):
    pats = []
    for line in open(inc, encoding="utf-8"):
        line = line.strip()
        if not line.startswith("INST("):
            continue
        parts = line.split('"')
        name, bits = parts[1], parts[3]
        assert len(bits) == 32, line
        mask = expect = 0
        for c in bits:
            mask <<= 1
            expect <<= 1
            if c in "01":
                mask |= 1
                expect |= int(c)
        pats.append((name, mask, expect))
    return pats
