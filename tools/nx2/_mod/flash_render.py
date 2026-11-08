import base64
import struct
import zlib

WINDOW = 5
CENTER = 2
LABELS = ["N-2", "N-1", "N", "N+1", "N+2"]


def png(width, height, rgb):
    rows = b"".join(b"\x00" + rgb[y * width * 3:(y + 1) * width * 3] for y in range(height))

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(rows, 9))
            + chunk(b"IEND", b""))


def tile_means(output, tiles):
    """Mean of the finite texels of each tile, or None when the tile has none."""
    gx, gy = output["grid"]
    width, height = output["width"], output["height"]
    means = []
    for index, (total, _peak, bad, _hot) in enumerate(tiles):
        x, y = index % gx, index // gx
        texels = (((x + 1) * width // gx - x * width // gx)
                  * ((y + 1) * height // gy - y * height // gy)) - bad
        means.append(total / texels if texels > 0 else None)
    return means


def thumbnails(output, blob):
    gx, gy = output["grid"]
    count = gx * gy
    present = [output["region"]["mean"][f] is not None for f in range(WINDOW)]
    frames = []
    for f in range(WINDOW):
        start = (output["tiles"] + f * count) * 16
        frames.append(list(struct.iter_unpack("<ffII", blob[start:start + count * 16])))
    means = [tile_means(output, tiles) for tiles in frames]
    around = [m for f in range(WINDOW) if present[f] and f != CENTER for m in means[f] if m]
    scale = max(around, default=0.0) or max((m for m in means[CENTER] if m), default=0.0) or 1.0
    images = []
    for f in range(WINDOW):
        if not present[f]:
            images.append(None)
            continue
        rgb = bytearray()
        for (_total, _peak, bad, hot), mean in zip(frames[f], means[f]):
            if bad:
                rgb += b"\xff\x00\xff"
            elif hot:
                rgb += b"\xff\x80\x00"
            else:
                level = int(min(1.0, max(0.0, (mean or 0.0) / scale)) ** (1 / 2.2) * 255 + 0.5)
                rgb += bytes((level, level, level))
        images.append(base64.b64encode(png(gx, gy, bytes(rgb))).decode())
    return images


def fmt_values(values):
    return " ".join("-" if v is None else f"{v:.3g}" if isinstance(v, float) else str(v)
                    for v in values)


def describe(output):
    kind = output["type"]
    where = f'{output["format"]} {output["width"]}x{output["height"]} {output["gpu_addr"]}'
    if kind == "pass":
        return f'pass {output["pass"]} rt{output["slot"]} {where}, {output["draws"]} draws'
    if kind == "dispatch":
        return f'dispatch {output["dispatch"]} img{output["slot"]} {where}'
    return f'present {output["present"]} {where}'
