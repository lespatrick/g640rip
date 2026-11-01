"""PWG-Raster (image/pwg-raster IEEE-ISTO 5102.4) encoder for Canon G640."""

import io
import struct
import numpy as np
from PIL import Image


def encode_pwg_packbits_bytes(raw_bytes: bytes) -> bytes:
    """Encode bytes using standard PWG-Raster PackBits compression."""
    n = len(raw_bytes)
    if n == 0:
        return b""

    buf = bytearray()
    i = 0
    while i < n:
        # Check repeated byte run
        run_len = 1
        curr = raw_bytes[i]
        while (i + run_len < n) and (run_len < 128) and (raw_bytes[i + run_len] == curr):
            run_len += 1

        if run_len >= 3:
            # Repeat run: code = -(run_len - 1) -> (256 - run_len + 1)
            code = (256 - run_len + 1) & 0xFF
            buf.append(code)
            buf.append(curr)
            i += run_len
        else:
            # Literal run
            lit_start = i
            i += 1
            while i < n and (i - lit_start) < 128:
                if i + 2 < n and raw_bytes[i] == raw_bytes[i + 1] == raw_bytes[i + 2]:
                    break
                i += 1
            lit_len = i - lit_start
            # Literal run: code = lit_len - 1
            buf.append(lit_len - 1)
            buf.extend(raw_bytes[lit_start:i])

    return bytes(buf)


def encode_image_to_pwg(
    image: Image.Image,
    dpi: int = 600,
    quality: int = 5,
    media_type: str = "photographic",
) -> bytes:
    """
    Encode PIL Image into standard PWG-Raster binary stream.
    """
    if image.mode != "RGB":
        image = image.convert("RGB")

    width, height = image.size
    bytes_per_line = width * 3

    out = io.BytesIO()
    # File synchronization string: b"RaS2"
    out.write(b"RaS2")

    # Page Header (1796 bytes)
    header = bytearray(1796)

    # MediaColor (offset 0..63)
    # MediaType (offset 64..127)
    med_bytes = media_type.encode("utf-8")[:63]
    header[64 : 64 + len(med_bytes)] = med_bytes

    # PrintQuality (offset 404, uint32 big endian)
    struct.pack_into("!I", header, 404, quality)

    # HWResolution (offset 416, 420: HWResolutionX, HWResolutionY)
    struct.pack_into("!II", header, 416, dpi, dpi)

    # PageSize (offset 428, 432: PageSizeX, PageSizeY in points)
    pt_w = int(width * 72 / dpi)
    pt_h = int(height * 72 / dpi)
    struct.pack_into("!II", header, 428, pt_w, pt_h)

    # CupsWidth, CupsHeight (offset 444, 448)
    struct.pack_into("!II", header, 444, width, height)

    # CupsBitsPerColor (offset 452) = 8
    struct.pack_into("!I", header, 452, 8)

    # CupsBitsPerPixel (offset 456) = 24
    struct.pack_into("!I", header, 456, 24)

    # CupsBytesPerLine (offset 460) = bytes_per_line
    struct.pack_into("!I", header, 460, bytes_per_line)

    # CupsColorOrder (offset 464) = 0 (Chunked)
    struct.pack_into("!I", header, 464, 0)

    # CupsColorSpace (offset 468) = 19 (sRGB)
    struct.pack_into("!I", header, 468, 19)

    # CupsNumColors (offset 476) = 3
    struct.pack_into("!I", header, 476, 3)

    # TotalPageCount (offset 480) = 1
    struct.pack_into("!I", header, 480, 1)

    out.write(header)

    # Body: Lines with repeat count byte
    img_array = np.array(image, dtype=np.uint8)
    y = 0
    while y < height:
        repeat_count = 0
        curr_row = img_array[y]
        while (y + 1 + repeat_count < height) and (repeat_count < 254):
            if np.array_equal(img_array[y + 1 + repeat_count], curr_row):
                repeat_count += 1
            else:
                break

        out.write(struct.pack("!B", repeat_count))
        compressed_line = encode_pwg_packbits_bytes(curr_row.tobytes())
        out.write(compressed_line)

        y += 1 + repeat_count

    return out.getvalue()

