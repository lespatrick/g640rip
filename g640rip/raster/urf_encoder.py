"""Lossless Apple Raster (image/urf v1.4) encoder for Canon G640.

Implements UNIRAST file and page header generation with PackBits pixel run-length encoding
and scanline repeat compression for ultra-fast, direct IPP streaming.
"""

import io
import struct
from typing import Optional, Tuple, Union
import numpy as np
from PIL import Image


def encode_packbits_row_rgb(row_pixels: np.ndarray) -> bytes:
    """
    Encode a single row of RGB pixels (shape: [W, 3], uint8) using URF PackBits encoding.
    URF PackBits rules:
    - 0x80 (-128): Fill the remainder of the scanline with white (0xFF).
    - 0 <= code <= 127: Repeat the next pixel (code + 1) times (1 to 128).
    - -128 < code < 0: Copy (-code + 1) literal pixels (2 to 128).
    """
    width = row_pixels.shape[0]
    if width == 0:
        return b""

    # Check for trailing white pixels (255, 255, 255)
    # White check from right to left
    white_pixel = np.array([255, 255, 255], dtype=np.uint8)
    is_white = np.all(row_pixels == white_pixel, axis=1)

    trailing_whites = 0
    while trailing_whites < width and is_white[width - 1 - trailing_whites]:
        trailing_whites += 1

    # If there are at least 4 trailing white pixels, truncate row and terminate with 0x80
    active_width = width - trailing_whites if trailing_whites >= 4 else width
    has_white_fill = active_width < width

    buf = bytearray()
    i = 0

    while i < active_width:
        # Check run of identical pixels
        run_len = 1
        curr_pixel = row_pixels[i]
        while i + run_len < active_width and run_len < 128:
            if np.array_equal(row_pixels[i + run_len], curr_pixel):
                run_len += 1
            else:
                break

        if run_len >= 2:
            # Repeat run: code = run_len - 1 (0x01 to 0x7F)
            code = run_len - 1
            buf.append(code)
            buf.extend(curr_pixel.tobytes())
            i += run_len
        else:
            # Literal run
            lit_start = i
            i += 1
            while i < active_width and (i - lit_start) < 128:
                # Check if next 2+ pixels are identical (start of a repeat run)
                if i + 1 < active_width and np.array_equal(row_pixels[i], row_pixels[i + 1]):
                    break
                i += 1

            lit_len = i - lit_start
            if lit_len == 1:
                # Single pixel can be encoded as repeat 1 time (code = 0)
                buf.append(0)
                buf.extend(row_pixels[lit_start].tobytes())
            else:
                # Literal run: code = -(lit_len - 1) -> in unsigned byte: (256 - lit_len + 1) & 0xFF
                code = (256 - lit_len + 1) & 0xFF
                buf.append(code)
                buf.extend(row_pixels[lit_start:i].tobytes())

    if has_white_fill:
        buf.append(0x80)

    return bytes(buf)


def decode_packbits_row_rgb(data: bytes, width: int) -> np.ndarray:
    """Helper to decode a URF PackBits row for unit testing and verification."""
    result = np.zeros((width, 3), dtype=np.uint8)
    idx = 0
    p_out = 0

    while idx < len(data) and p_out < width:
        code_byte = data[idx]
        idx += 1
        if code_byte == 0x80:
            # Fill remainder with white
            result[p_out:] = 255
            break

        # Signed value
        code = struct.unpack("!b", bytes([code_byte]))[0]
        if code >= 0:
            # Repeat (code + 1) times
            repeat_cnt = code + 1
            pixel = data[idx:idx + 3]
            idx += 3
            result[p_out:p_out + repeat_cnt] = np.frombuffer(pixel, dtype=np.uint8)
            p_out += repeat_cnt
        else:
            # Literal (-code + 1) pixels
            lit_cnt = (-code) + 1
            lit_bytes = data[idx:idx + (lit_cnt * 3)]
            idx += lit_cnt * 3
            result[p_out:p_out + lit_cnt] = np.frombuffer(lit_bytes, dtype=np.uint8).reshape((lit_cnt, 3))
            p_out += lit_cnt

    return result


def encode_image_to_urf(
    image: Image.Image,
    dpi: int = 600,
    quality: int = 5,
    colorspace: int = 1,  # 1 = sRGB/RGB24, 0 = Grayscale
) -> bytes:
    """
    Encode PIL Image into standard Apple Raster (image/urf v1.4) binary stream.

    Parameters:
        image: PIL Image (will be converted to RGB if not already)
        dpi: Resolution (default: 600 DPI for Canon G640)
        quality: Print quality (3=Draft, 4=Normal, 5=High)
        colorspace: 1 for RGB24, 0 for Grayscale
    """
    if image.mode != "RGB":
        image = image.convert("RGB")

    width, height = image.size
    img_array = np.array(image, dtype=np.uint8)

    out = io.BytesIO()

    # 1. File Header: b"UNIRAST\0" + page_count (1 page)
    file_header = struct.pack("!8sI", b"UNIRAST\0", 1)
    out.write(file_header)

    # 2. Page Header: 28 bytes
    # uint8_t bpp (24 for RGB)
    # uint8_t colorspace (1 for sRGB)
    # uint8_t duplex (0)
    # uint8_t quality (3-5)
    # uint32_t unknown0 (0)
    # uint32_t unknown1 (0)
    # uint32_t width
    # uint32_t height
    # uint32_t dpi
    # uint32_t unknown2 (0)
    # uint32_t unknown3 (0)
    bpp = 24 if colorspace == 1 else 8
    page_header = struct.pack(
        "!BBBBIIIIIII",
        bpp,
        colorspace,
        0,       # duplex: simplex
        quality,
        0,       # unknown0
        0,       # unknown1
        width,
        height,
        dpi,
        0,       # unknown2
        0,       # unknown3
    )
    out.write(page_header)

    # 3. Body: Scanlines with line-repeat compression
    y = 0
    while y < height:
        # Calculate line repeat count for identical consecutive rows
        repeat_count = 0
        current_row = img_array[y]
        while (y + 1 + repeat_count < height) and (repeat_count < 254):
            if np.array_equal(img_array[y + 1 + repeat_count], current_row):
                repeat_count += 1
            else:
                break

        # Line repeat byte: repeat_count (0 means 1 line total)
        out.write(struct.pack("!B", repeat_count))

        # PackBits encode the row
        encoded_row = encode_packbits_row_rgb(current_row)
        out.write(encoded_row)

        y += 1 + repeat_count

    return out.getvalue()

