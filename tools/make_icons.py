"""Render the app's simple geometric icon, without third-party dependencies."""
import struct
import zlib
from pathlib import Path


def chunk(kind, data):
    return struct.pack('!I', len(data)) + kind + data + struct.pack('!I', zlib.crc32(kind + data) & 0xffffffff)


for size in (192, 512):
    pixels = bytearray()
    for y in range(size):
        pixels.append(0)
        for x in range(size):
            a, b = x / size, y / size
            color = (16, 44, 66)
            if .25 <= a <= .75 and max(.19 + abs(a-.5)*.52, .19) <= b <= .76:
                color = (7, 135, 140)
            if any(left <= a <= left+.08 and top <= b <= top+.09 for left, top in ((.35,.35),(.57,.35),(.35,.52),(.57,.52),(.46,.66))):
                color = (255, 255, 255)
            pixels.extend(color)
    header = struct.pack('!2I5B', size, size, 8, 2, 0, 0, 0)
    png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', header) + chunk(b'IDAT', zlib.compress(pixels)) + chunk(b'IEND', b'')
    (Path(__file__).resolve().parents[1] / 'public' / f'icon-{size}.png').write_bytes(png)
