"""Unit tests for Apple Raster (image/urf) and PWG-Raster encoders."""

import struct
import unittest
import numpy as np
from PIL import Image

from g640rip.raster.urf_encoder import (
    encode_image_to_urf,
    encode_packbits_row_rgb,
    decode_packbits_row_rgb,
)
from g640rip.raster.pwg_encoder import encode_image_to_pwg


class TestRasterEncoders(unittest.TestCase):
    def test_packbits_exact_roundtrip(self):
        # Create row with literal and repeating pixels and white tail
        pixels = [
            [10, 20, 30],
            [10, 20, 30],
            [10, 20, 30],  # repeat run of 3
            [1, 2, 3],
            [4, 5, 6],     # literal run
            [255, 255, 255],
            [255, 255, 255],
            [255, 255, 255],
            [255, 255, 255],  # white fill tail
        ]
        row_arr = np.array(pixels, dtype=np.uint8)
        encoded = encode_packbits_row_rgb(row_arr)
        decoded = decode_packbits_row_rgb(encoded, len(row_arr))
        self.assertTrue(np.array_equal(row_arr, decoded))

    def test_urf_header_structure(self):
        img = Image.new("RGB", (64, 32), (255, 255, 255))
        urf = encode_image_to_urf(img, dpi=600, quality=5)

        # File header (12 bytes)
        magic, page_cnt = struct.unpack("!8sI", urf[:12])
        self.assertEqual(magic, b"UNIRAST\0")
        self.assertEqual(page_cnt, 1)

        # Page header (32 bytes: 4 B + 7 I)
        bpp, cs, duplex, qual, u0, u1, w, h, dpi, u2, u3 = struct.unpack("!BBBBIIIIIII", urf[12:44])
        self.assertEqual(bpp, 24)
        self.assertEqual(cs, 1)  # sRGB
        self.assertEqual(qual, 5)  # High
        self.assertEqual(w, 64)
        self.assertEqual(h, 32)
        self.assertEqual(dpi, 600)

    def test_pwg_header_structure(self):
        img = Image.new("RGB", (32, 16), (128, 128, 128))
        pwg = encode_image_to_pwg(img, dpi=600, quality=4)
        self.assertTrue(pwg.startswith(b"RaS2"))
        self.assertGreaterEqual(len(pwg), 1796)


if __name__ == "__main__":
    unittest.main()
