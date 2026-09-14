"""scripts/gifwrite.py — [IO] a GIF89a encoder, standard library only.

There is no ffmpeg, no ImageMagick and no Pillow on this machine, and the README
wants a short silent loop of the product working. Rather than add a dependency
to ship one documentation artefact, this writes the file: PNG in, quantised
palette, LZW, GIF out.

It is not a general-purpose encoder. It assumes what these frames are — 8-bit
RGB or RGBA screenshots of a mostly static page — and leans on that:

- **Median cut** to 256 colours. A UI is flat; the colours that matter are text
  antialiasing, and a 256-entry palette holds them without visible banding.
- **Bounding-box sub-frames.** After the first frame only the rectangle that
  changed is stored, which is what makes a 20-second loop of a page where one
  panel animates a few megabytes rather than a few dozen.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path


# --------------------------------------------------------------------------- #
# PNG in
# --------------------------------------------------------------------------- #
def read_png(path: Path | str) -> tuple[int, int, bytearray]:
    """Decode an 8-bit RGB/RGBA PNG to (width, height, RGB bytes)."""
    data = Path(path).read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"not a PNG: {path}")
    pos, idat, width, height, channels = 8, [], 0, 0, 0
    while pos < len(data):
        length = struct.unpack(">I", data[pos : pos + 4])[0]
        kind = data[pos + 4 : pos + 8]
        body = data[pos + 8 : pos + 8 + length]
        if kind == b"IHDR":
            width, height, depth, colour = struct.unpack(">IIBB", body[:10])
            if depth != 8:
                raise ValueError(f"{path}: {depth}-bit, expected 8")
            channels = {0: 1, 2: 3, 4: 2, 6: 4}[colour]
        elif kind == b"IDAT":
            idat.append(body)
        elif kind == b"IEND":
            break
        pos += 12 + length

    raw = zlib.decompress(b"".join(idat))
    stride = width * channels
    rgb = bytearray(width * height * 3)
    previous = bytearray(stride)
    at = 0
    for y in range(height):
        filter_type = raw[at]
        at += 1
        line = bytearray(raw[at : at + stride])
        at += stride
        if filter_type == 1:
            for i in range(channels, stride):
                line[i] = (line[i] + line[i - channels]) & 255
        elif filter_type == 2:
            for i in range(stride):
                line[i] = (line[i] + previous[i]) & 255
        elif filter_type == 3:
            for i in range(stride):
                left = line[i - channels] if i >= channels else 0
                line[i] = (line[i] + ((left + previous[i]) >> 1)) & 255
        elif filter_type == 4:
            for i in range(stride):
                a = line[i - channels] if i >= channels else 0
                b = previous[i]
                c = previous[i - channels] if i >= channels else 0
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                pred = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pred) & 255
        out = y * width * 3
        if channels >= 3:
            for x in range(width):
                src = x * channels
                rgb[out + x * 3 : out + x * 3 + 3] = line[src : src + 3]
        else:  # greyscale
            for x in range(width):
                v = line[x * channels]
                rgb[out + x * 3 : out + x * 3 + 3] = bytes((v, v, v))
        previous = line
    return width, height, rgb


def scale(width: int, height: int, rgb: bytearray, target_width: int) -> tuple[int, int, bytearray]:
    """Nearest-neighbour downscale. Box filtering blurs text more than it helps."""
    if target_width >= width:
        return width, height, rgb
    target_height = max(1, round(height * target_width / width))
    out = bytearray(target_width * target_height * 3)
    for y in range(target_height):
        sy = min(height - 1, y * height // target_height)
        row, srow = y * target_width * 3, sy * width * 3
        for x in range(target_width):
            sx = min(width - 1, x * width // target_width)
            out[row + x * 3 : row + x * 3 + 3] = rgb[srow + sx * 3 : srow + sx * 3 + 3]
    return target_width, target_height, out


# --------------------------------------------------------------------------- #
# Palette — median cut over the colours actually present
# --------------------------------------------------------------------------- #
def build_palette(
    frames: list[bytearray], limit: int = 256
) -> tuple[list[tuple[int, int, int]], dict]:
    """One global palette for every frame, so sub-frames stay cheap.

    Counting first and cutting on the counts keeps a colour that covers a large
    flat area from being merged away by thousands of antialiasing shades that
    each cover one pixel.
    """
    counts: dict[tuple[int, int, int], int] = {}
    for rgb in frames:
        for i in range(0, len(rgb), 3):
            key = (rgb[i], rgb[i + 1], rgb[i + 2])
            counts[key] = counts.get(key, 0) + 1

    boxes = [list(counts.items())]
    while len(boxes) < limit:
        # Split the box with the largest spread on its widest channel.
        target, widest, channel = None, -1, 0
        for box in boxes:
            if len(box) < 2:
                continue
            for c in range(3):
                values = [colour[c] for colour, _ in box]
                spread = max(values) - min(values)
                if spread > widest:
                    target, widest, channel = box, spread, c
        if target is None or widest <= 0:
            break
        target.sort(key=lambda item: item[0][channel])
        half = len(target) // 2
        boxes.remove(target)
        boxes.extend([target[:half], target[half:]])

    palette: list[tuple[int, int, int]] = []
    lookup: dict[tuple[int, int, int], int] = {}
    for index, box in enumerate(boxes):
        total = sum(n for _, n in box) or 1
        r = sum(colour[0] * n for colour, n in box) // total
        g = sum(colour[1] * n for colour, n in box) // total
        b = sum(colour[2] * n for colour, n in box) // total
        palette.append((r, g, b))
        for colour, _ in box:
            lookup[colour] = index
    while len(palette) < 2:
        palette.append((0, 0, 0))
    return palette, lookup


# --------------------------------------------------------------------------- #
# LZW, as GIF specifies it
# --------------------------------------------------------------------------- #
def lzw(indices: bytes, code_size: int) -> bytes:
    clear, end = 1 << code_size, (1 << code_size) + 1
    table = {bytes([i]): i for i in range(clear)}
    next_code, width = end + 1, code_size + 1

    bits, acc, out = 0, 0, bytearray()

    def emit(code: int) -> None:
        nonlocal bits, acc
        acc |= code << bits
        bits += width
        while bits >= 8:
            out.append(acc & 0xFF)
            acc >>= 8
            bits -= 8

    emit(clear)
    buffer = b""
    for byte in indices:
        candidate = buffer + bytes([byte])
        if candidate in table:
            buffer = candidate
            continue
        emit(table[buffer])
        table[candidate] = next_code
        next_code += 1
        if next_code > (1 << width) and width < 12:
            width += 1
        elif next_code > 4095:
            emit(clear)
            table = {bytes([i]): i for i in range(clear)}
            next_code, width = end + 1, code_size + 1
        buffer = bytes([byte])
    if buffer:
        emit(table[buffer])
    emit(end)
    if bits:
        out.append(acc & 0xFF)

    blocked = bytearray()
    for i in range(0, len(out), 255):
        chunk = out[i : i + 255]
        blocked.append(len(chunk))
        blocked.extend(chunk)
    blocked.append(0)
    return bytes(blocked)


# --------------------------------------------------------------------------- #
# GIF89a out
# --------------------------------------------------------------------------- #
def _bbox(a: bytes, b: bytes, width: int, height: int) -> tuple[int, int, int, int] | None:
    """The rectangle in which two indexed frames differ, or None if identical."""
    top = next(
        (
            y
            for y in range(height)
            if a[y * width : (y + 1) * width] != b[y * width : (y + 1) * width]
        ),
        None,
    )
    if top is None:
        return None
    bottom = next(
        y
        for y in range(height - 1, -1, -1)
        if a[y * width : (y + 1) * width] != b[y * width : (y + 1) * width]
    )
    left, right = width, -1
    for y in range(top, bottom + 1):
        row_a, row_b = a[y * width : (y + 1) * width], b[y * width : (y + 1) * width]
        for x in range(width):
            if row_a[x] != row_b[x]:
                left = min(left, x)
                break
        for x in range(width - 1, -1, -1):
            if row_a[x] != row_b[x]:
                right = max(right, x)
                break
    return left, top, right - left + 1, bottom - top + 1


def write_gif(
    frames: list[tuple[int, int, bytearray]], path: Path | str, delays_cs: list[int]
) -> int:
    """Write an looping GIF89a. `delays_cs` is hundredths of a second per frame."""
    width, height, _ = frames[0]
    palette, lookup = build_palette([rgb for _, _, rgb in frames])

    indexed = [
        bytes(lookup[(rgb[i], rgb[i + 1], rgb[i + 2])] for i in range(0, len(rgb), 3))
        for _, _, rgb in frames
    ]

    out = bytearray(b"GIF89a")
    out += struct.pack("<HH", width, height)
    out += bytes((0xF7, 0, 0))  # global table, 256 entries, 8-bit colour
    for r, g, b in palette:
        out += bytes((r, g, b))
    out += b"\x00" * (3 * (256 - len(palette)))
    out += b"\x21\xff\x0bNETSCAPE2.0\x03\x01\x00\x00\x00"  # loop forever

    previous: bytes | None = None
    pending = 0
    for frame, delay in zip(indexed, delays_cs, strict=True):
        if previous is None:
            x, y, w, h = 0, 0, width, height
            data = frame
        else:
            box = _bbox(previous, frame, width, height)
            if box is None:
                # Nothing moved: lengthen the frame already on screen rather
                # than storing another copy of it.
                pending += delay
                continue
            x, y, w, h = box
            data = b"".join(
                frame[(y + row) * width + x : (y + row) * width + x + w] for row in range(h)
            )

        out += b"\x21\xf9\x04\x00" + struct.pack("<H", delay + pending) + b"\x00\x00"
        pending = 0
        out += b"\x2c" + struct.pack("<HHHH", x, y, w, h) + b"\x00"
        out += bytes((8,)) + lzw(data, 8)
        previous = frame

    out += b"\x3b"
    Path(path).write_bytes(out)
    return len(out)
