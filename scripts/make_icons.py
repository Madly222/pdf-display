import struct
import sys
import zlib
from pathlib import Path

BLUE = (0x2F, 0x6F, 0xEB)
WHITE = (0xFF, 0xFF, 0xFF)
FOLD = (0xB9, 0xCF, 0xFB)


def in_round_rect(x, y, x0, y0, x1, y1, r):
    if not (x0 <= x <= x1 and y0 <= y <= y1):
        return False
    cx = min(max(x, x0 + r), x1 - r)
    cy = min(max(y, y0 + r), y1 - r)
    return (x - cx) ** 2 + (y - cy) ** 2 <= r * r


def color_at(x, y, rounded=True):
    if rounded and not in_round_rect(x, y, 0, 0, 64, 64, 14):
        return None
    in_page = 17 <= x <= 48 and 12 <= y <= 53 and x - y <= 25
    if not in_page:
        return BLUE
    if x >= 37 and y <= 23:
        return FOLD
    for y0, width in ((31, 19), (38, 19), (45, 12)):
        if in_round_rect(x, y, 23, y0, 23 + width, y0 + 3.5, 1.75):
            return BLUE
    return WHITE


def render(size, ss=4, rounded=True):
    rows = []
    for py in range(size):
        row = bytearray([0])
        for px in range(size):
            acc = [0, 0, 0, 0]
            for sy in range(ss):
                for sx in range(ss):
                    c = color_at((px + (sx + 0.5) / ss) * 64 / size, (py + (sy + 0.5) / ss) * 64 / size, rounded)
                    if c:
                        acc[0] += c[0]; acc[1] += c[1]; acc[2] += c[2]; acc[3] += 1
            n = acc[3]
            row += bytes([acc[0] // n, acc[1] // n, acc[2] // n, n * 255 // (ss * ss)] if n else [0, 0, 0, 0])
        rows.append(bytes(row))
    return png(size, b"".join(rows))


def png(size, raw):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


def ico(images):
    out = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    for size, data in images:
        out += struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    return out + b"".join(data for _, data in images)


def main():
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    (out / "favicon.ico").write_bytes(ico([(s, render(s)) for s in (16, 32, 48)]))
    (out / "apple-touch-icon.png").write_bytes(render(180, ss=2, rounded=False))


if __name__ == "__main__":
    main()
